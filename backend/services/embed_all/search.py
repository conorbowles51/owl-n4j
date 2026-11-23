"""One search across every area, by meaning and by words together (lx-embedall D).

Meaning: the question's vector against the ``case_items`` collection (every area but phone conversations and documents)
and the ``chunks`` collection (phone conversation windows and document passages). Words: the question's folded terms
against the stored item text, and the phone thread documents through ``chat_retrieval.windows``. The two ranked lists are
fused by reciprocal rank fusion with the constant lx-retrieval uses (``retrieval_fusion.K``). Each hit says why it matched
(``meaning``, ``words`` or ``both``). The result lists what was searched and what was not, and says when meaning search
was unavailable and only words were searched.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import text

from services.embed_all import phone as phone_area
from services.embed_all.core import COLLECTION
from services.embed_all.sources import AREAS
from services.retrieval_fusion import K, similarity

logger = logging.getLogger(__name__)

ALL_AREAS = tuple(AREAS) + ("phone_text", "documents", "entities")
MAX_DISTANCE = 1.44  # squared L2 of unit vectors: cosine 0.28 and above. Measured on the demo case, 17 Nov: relevant hits
# score cosine 0.31 to 0.50, a query with no answer ("burner") scores 0.22 to 0.24 against the nearest unrelated text
SNIPPET = 400
DERIVED_AREAS = frozenset({"relationships"})  # graph text the engine wrote from a source; the source record ranks first
ENTITY_WEIGHT = 0.6  # a graph entity (a bare name) scores below a source record with the same evidence; measured 17 Nov
ALSO_SHOWN = 5  # connections folded into one hit: their titles and openings stay on the hit
ALSO_CHARS = 240
DERIVED_OFFSET = 0  # measured 17 Nov: an offset moved a statement-page record out of the first ten; collapse alone keeps the order
FETCH = 60


def _ts(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(value.timestamp())
    return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())


def _snippet(body: str, terms: list[str]) -> str:
    """The window of the text that holds the most of the question's terms (a statement page of 40 lines shows the
    line that matched, not the first line that has one of the words)."""
    body = body or ""
    low = body.casefold()
    wanted = [t.casefold() for t in terms if t]
    spots: list[int] = []
    for t in wanted:
        at, n = low.find(t), 0
        while at >= 0 and n < 100:
            spots.append(at)
            at, n = low.find(t, at + 1), n + 1
    if not spots:
        return body[:SNIPPET].strip()
    best, best_start = -1, 0
    for at in sorted(set(spots)):
        start = max(0, at - SNIPPET // 3)
        window = low[start:start + SNIPPET]
        got = sum(1 for t in wanted if t in window)
        if got > best:
            best, best_start = got, start
    return body[best_start:best_start + SNIPPET].strip()


def _where(case_id, areas, date_from, date_to):
    conds = [{"case_id": str(case_id)}]
    conds.append({"area": areas[0]} if len(areas) == 1 else {"area": {"$in": list(areas)}})
    if date_from is not None:
        conds.append({"item_ts": {"$gte": _ts(date_from)}})
    if date_to is not None:
        conds.append({"item_ts": {"$lte": _ts(date_to)}})
    return {"$and": conds}


QUERY_WORKERS = 8  # Chroma queries of one search sent side by side
# The vector store's queries in flight from this process, every search together: three overlapping searches sent 36
# at once and the store answered "pool timed out while waiting for an open connection" (demo case, 23 Nov 02:38).
_STORE_SLOTS = threading.BoundedSemaphore(QUERY_WORKERS)

# A case with at most this many rows in a collection is scored here, not by the vector store. Measured on the demo case
# (23 Nov, load 7): a filtered store query took 3.9-5.3 s over 193 chunks; reading the case's chunks took 0.3 s, and
# exact distances gave the same hits.
LOCAL_MAX_ROWS = 5000
# Only the passages collection: there the store's filtered query is slowest (3.9-5.3 s) and exact distances gave the
# store's own hits. On case_items, exact distances found records the store's index does not return, and the relevance
# gate (23 Nov) ranked 9 answers one to three places lower and 1 higher; the items stay with the store.
LOCAL_COLLECTIONS = frozenset({"chunks"})
_VECTOR_CACHE_MAX = 20000  # vectors kept per process, by row id and text (float32: about 120 MB at most)
_vectors: "OrderedDict[tuple, Any]" = OrderedDict()
_vectors_lock = threading.Lock()
_large: dict[tuple, float] = {}  # (collection, case) found over LOCAL_MAX_ROWS -> when; asked again after LARGE_TTL_S
LARGE_TTL_S = 600


def _matches(meta: dict, where: dict | None) -> bool:
    """Chroma's metadata filter, for the operators this module sends. A key the row lacks fails every test but $ne
    and $nin, as in the store."""
    if not where:
        return True
    for k, cond in where.items():
        if k == "$and":
            if not all(_matches(meta, c) for c in cond):
                return False
            continue
        if k == "$or":
            if not any(_matches(meta, c) for c in cond):
                return False
            continue
        ops = cond if isinstance(cond, dict) else {"$eq": cond}
        has, v = k in meta and meta[k] is not None, meta.get(k)
        for op, want in ops.items():
            if op == "$eq":
                ok = has and v == want
            elif op == "$ne":
                ok = not has or v != want
            elif op == "$in":
                ok = has and v in want
            elif op == "$nin":
                ok = not has or v not in want
            elif op in ("$gt", "$gte", "$lt", "$lte"):
                try:
                    ok = has and {"$gt": v > want, "$gte": v >= want, "$lt": v < want, "$lte": v <= want}[op]
                except TypeError:
                    ok = False
            else:
                raise ValueError("filter operator %s is not scored here" % op)
            if not ok:
                return False
    return True


def _l2_space(collection) -> bool:
    space = ((getattr(collection, "metadata", None) or {}).get("hnsw:space") or "l2")
    try:  # chromadb 1.x keeps it in the collection's configuration
        cfg = getattr(collection, "configuration_json", None) or {}
        space = (cfg.get("hnsw") or {}).get("space") or space
    except Exception:  # noqa: BLE001
        pass
    return space == "l2"


def _case_rows(collection, case_id: str):
    """The case's rows of one collection with their vectors, or None when the case is too large to score here (or the
    collection cannot be read this way). Metadata and text are read fresh every time; a vector is reused while its
    row's id and text are unchanged."""
    import numpy as np
    name = getattr(collection, "name", None)
    if name not in LOCAL_COLLECTIONS or not hasattr(collection, "get") or not _l2_space(collection):
        return None
    big = (name, case_id)
    if time.time() - _large.get(big, -1e9) < LARGE_TTL_S:
        return None
    got = collection.get(where={"case_id": case_id}, include=["metadatas", "documents"], limit=LOCAL_MAX_ROWS + 1)
    ids = got.get("ids") or []
    if len(ids) > LOCAL_MAX_ROWS:
        _large[big] = time.time()
        return None
    docs, metas = got.get("documents") or [None] * len(ids), got.get("metadatas") or [{}] * len(ids)
    keys = [(name, i, hashlib.sha1((d or "").encode()).hexdigest()) for i, d in zip(ids, docs)]
    with _vectors_lock:
        missing = [k for k in keys if k not in _vectors]
    if missing:
        fetched = collection.get(ids=[k[1] for k in missing], include=["embeddings", "documents"])
        by_id = {}
        for i, e, d in zip(fetched["ids"], fetched["embeddings"], fetched.get("documents") or []):
            by_id[(name, i, hashlib.sha1((d or "").encode()).hexdigest())] = np.asarray(e, dtype=np.float32)
        with _vectors_lock:
            for k, v in by_id.items():
                _vectors[k] = v
            while len(_vectors) > _VECTOR_CACHE_MAX:
                _vectors.popitem(last=False)
    rows = []
    with _vectors_lock:
        for k, d, m in zip(keys, docs, metas):
            v = _vectors.get(k)
            if v is None:  # changed between the two reads: the store has the newer row; ask it
                return None
            _vectors.move_to_end(k)
            rows.append((k[1], d, m or {}, v))
    return rows


def _local_query(rows, query_vector, n_results: int, where: dict | None) -> dict:
    """One store query answered from the case's rows: squared L2 distance, the store's measure for these
    collections, nearest first."""
    import numpy as np
    keep = [r for r in rows if _matches(r[2], where)]
    if not keep:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    q = np.asarray(query_vector, dtype=np.float32)
    dist = ((np.stack([r[3] for r in keep]) - q) ** 2).sum(axis=1)
    order = np.argsort(dist, kind="stable")[:n_results]
    return {"ids": [[keep[i][0] for i in order]], "documents": [[keep[i][1] for i in order]],
            "metadatas": [[keep[i][2] for i in order]], "distances": [[float(dist[i]) for i in order]]}


def meaning_hits(case_id, query_vector, items_collection, chunks_collection, areas, *, phone=None, person=None,
                 date_from=None, date_to=None, entities_collection=None) -> list[dict]:
    # Every Chroma query is sent at once and read back in this order (lx-casesearch 17 Nov: 12 queries one after
    # another took 5.5 s at load 7 and 42-107 s at load 50-75; side by side 2.4 s at load 7, the same hits).
    include = ["documents", "metadatas", "distances"]
    jobs: list[tuple[str, Any, dict]] = []
    if "entities" in areas and entities_collection is not None and date_from is None and date_to is None:
        jobs.append(("entities", entities_collection, dict(n_results=FETCH // 2, where={"case_id": str(case_id)})))
    areas = [a for a in areas if a != "entities"]
    item_areas = [a for a in areas if a not in ("phone_text", "documents")]
    over = FETCH * 3 if person else FETCH
    if item_areas and items_collection is not None:
        for area in item_areas:  # one query per area: a crowded area cannot push another out of the candidates
            jobs.append(("items", items_collection, dict(n_results=over // 2,
                                                         where=_where(case_id, [area], date_from, date_to))))
    chunk_areas = [a for a in areas if a in ("phone_text", "documents")]
    if chunk_areas and chunks_collection is not None and (date_from is None and date_to is None):
        # One query per kind: 169,000 phone windows in the collection pushed document passages out of one shared
        # candidate list (lx-embedall 17 Nov: the gate lost a police-interview passage that sat at rank 36).
        for kind_area in chunk_areas:
            conds = [{"case_id": str(case_id)}, {"ingestion_state": "active"}]
            if kind_area == "phone_text":
                conds.append({"source_kind": "phone_text"})
                if phone:
                    conds.append({"extraction_id": str(phone)})
            else:
                conds.append({"source_kind": {"$ne": "phone_text"}})
            jobs.append(("chunks", chunks_collection, dict(n_results=over, where={"$and": conds})))

    # small cases are scored here from their rows, read once per collection; large ones ask the store
    local: dict[int, Any] = {}
    for coll in {id(j[1]): j[1] for j in jobs}.values():
        try:
            local[id(coll)] = _case_rows(coll, str(case_id))
        except Exception:  # noqa: BLE001 - the store's own query still answers
            logger.warning("Case rows could not be read for local scoring; asking the vector store", exc_info=True)
            local[id(coll)] = None

    def run(job):
        rows = local.get(id(job[1]))
        if rows is not None:
            return _local_query(rows, query_vector, job[2]["n_results"], job[2].get("where"))
        with _STORE_SLOTS:
            return job[1].query(query_embeddings=[query_vector], include=include, **job[2])
    if len(jobs) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(QUERY_WORKERS, len(jobs))) as pool:
            results = list(pool.map(run, jobs))
    else:
        results = [run(j) for j in jobs]
    hits: list[dict] = []
    for (kind, _, _), res in zip(jobs, results):
        if kind == "entities":
            for eid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
                hits.append({"area": "entities", "key": eid, "title": meta.get("name") or eid,
                             "cite": "/cases/%s/graph" % case_id, "text": doc, "distance": dist,
                             "person": meta.get("name") or "", "as_read": False})
        elif kind == "items":
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                hits.append({"area": meta["area"], "key": meta["item_key"], "title": meta.get("title", ""),
                             "cite": meta.get("cite", ""), "text": doc, "distance": dist,
                             "person": meta.get("person", ""), "as_read": bool(meta.get("as_read"))})
        else:
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                is_phone = meta.get("source_kind") == "phone_text"
                area = "phone_text" if is_phone else "documents"
                if area not in chunk_areas:
                    continue
                cite = meta.get("url") if is_phone else "doc://%s/%s" % (
                    meta.get("evidence_file_id") or meta.get("doc_id"), meta.get("page_start") or "")
                hits.append({"area": area, "key": "%s:%s" % (meta.get("evidence_file_id"), meta.get("chunk_index")),
                             "title": meta.get("doc_name") or meta.get("file_name") or "", "cite": cite or "",
                             "text": doc, "distance": dist, "person": "", "as_read": False})
    if person:
        who = person.casefold()
        hits = [h for h in hits if who in (h["person"] + " " + h["text"]).casefold()]
    kept, seen, subjects, keys = [], set(), {}, set()
    # Each area's own order: the best hit of every area comes before the second hit of any. Measured on the demo case,
    # one list by raw similarity let phone call lines ("Phone 4 | Phone") crowd out a voice-note transcript that says
    # "do not call the other phone" for the query "the other phone".
    for h in sorted((h for h in hits if h["distance"] is not None and h["distance"] <= MAX_DISTANCE),
                    key=lambda h: h["distance"]):
        if (h["area"], h["key"]) in keys:
            continue
        keys.add((h["area"], h["key"]))
        one = (h["area"], h["cite"] or h["key"], h["title"])  # two passages of one page are one hit: the nearer stays
        if h["area"] in ("documents",) and one in seen:
            continue
        if h["area"] in DERIVED_AREAS:  # connections of one subject and one source are one fact told five ways
            who = _subject(h)
            first = subjects.setdefault((h["area"], h["cite"], who), h)
            if first is not h:
                first["also"] = first.get("also", 0) + 1
                if len(first.setdefault("also_hits", [])) < ALSO_SHOWN:  # the collapsed facts stay readable
                    first["also_hits"].append({"title": h["title"], "text": h["text"][:ALSO_CHARS]})
                continue
        seen.add(one)
        kept.append(h)
    counts: dict[str, int] = {}
    for h in kept:  # kept is in distance order: the count so far in the area is its rank there
        counts[h["area"]] = counts.get(h["area"], 0) + 1
        h["area_rank"] = counts[h["area"]] + (DERIVED_OFFSET if h["area"] in DERIVED_AREAS else 0)
    return kept


def _subject(h: dict) -> str:
    """The first node of a connection: its title is ``<a> <kind> <b>`` and its person field is ``<a> <b>``."""
    title, person = (h.get("title") or "").casefold(), (h.get("person") or "").casefold()
    n = 0
    while n < min(len(title), len(person)) and title[n] == person[n]:
        n += 1
    cut = title[:n]
    if n < len(title) and title[n] != " " and " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip() or title


def word_hits(conn, case_id, terms: list[str], areas, *, phone=None, person=None, date_from=None, date_to=None) -> list[dict]:
    """Records holding the terms, most terms first. A term is a folded string, or a loose group
    (``case_search.loose.groups``: ``inside`` forms found anywhere, ``whole`` forms as whole words only); a record
    holds a group when it holds any of its forms."""
    hits: list[dict] = []
    item_areas = [a for a in areas if a not in ("phone_text", "documents")]
    groups = [t if isinstance(t, dict) else {"term": t, "inside": [t], "whole": []} for t in terms or []]
    terms = [g["term"] for g in groups]
    if terms and item_areas:
        params: dict[str, Any] = {"c": str(case_id), "areas": item_areas}
        conds = []

        def esc(s):
            return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        for i, g in enumerate(groups):
            ors = []
            for j, f in enumerate(g["inside"]):
                params["t%d_%d" % (i, j)] = "%" + esc(f) + "%"
                ors.append(":t%d_%d" % (i, j))
            for j, f in enumerate(g["whole"]):
                params["w%d_%d" % (i, j)] = "% " + esc(f) + " %"
                ors.append("w:w%d_%d" % (i, j))
            # whole-word forms are matched with the text padded by a space on each side (folded text has single spaces)
            conds.append("(%s)::int" % " OR ".join("(' ' || body_folded || ' ') LIKE %s" % o[1:] if o.startswith("w:") else "body_folded LIKE %s" % o for o in ors))
        extra = ""
        if person:
            params["p"] = "%" + person.replace("%", "\\%").replace("_", "\\_") + "%"
            extra += " AND (person ILIKE :p OR body ILIKE :p)"
        if date_from is not None:
            params["df"] = date_from
            extra += " AND item_date >= :df"
        if date_to is not None:
            params["dt"] = date_to
            extra += " AND item_date <= :dt"
        score = " + ".join(conds)
        rows = conn.execute(text(
            "SELECT area, item_key, title, cite, body, person, (%s) AS score FROM embed_items WHERE case_id = :c AND "
            "area = ANY(:areas) AND body_folded IS NOT NULL AND (%s) > 0%s ORDER BY 7 DESC, item_key LIMIT %d"
            % (score, score, extra, FETCH)), params).fetchall()
        for r in rows:
            hits.append({"area": r.area, "key": r.item_key, "title": r.title or "", "cite": r.cite or "", "text": r.body,
                         "words": int(r.score), "person": r.person or "", "as_read": False})
    if terms and "phone_text" in areas and date_from is None and date_to is None:
        from services.phone import chat_retrieval
        question = " ".join('"%s"' % t if " " in t else t for t in terms)
        for w in chat_retrieval.windows(conn, case_id, question, max_windows=20):
            m = w["metadata"]
            if phone and str(m.get("extraction_id")) != str(phone):
                continue
            if person and person.casefold() not in w["text"].casefold():
                continue
            hits.append({"area": "phone_text", "key": "%s:%s" % (m.get("evidence_file_id"), m.get("start_char")),
                         "title": m.get("doc_name") or "", "cite": m.get("url") or "", "text": w["text"],
                         "words": len(m.get("matched_terms") or []), "person": "", "as_read": False})
    return hits


def fuse(meaning: list[dict], words: list[dict], limit: int) -> list[dict]:
    """Reciprocal rank fusion of the two lists; a hit in both says ``both``."""
    scores: dict[tuple, float] = {}
    byk: dict[tuple, dict] = {}
    for rank, h in enumerate(sorted(meaning, key=lambda h: (h.get("area_rank", 1), h["distance"])), 1):
        k = (h["area"], h["key"])
        byk[k] = dict(h, matched="meaning", similarity=round(similarity(h["distance"]) or 0, 3))
        scores[k] = scores.get(k, 0) + 1.0 / (K + rank)
    for rank, h in enumerate(sorted(words, key=lambda h: -h["words"]), 1):
        k = (h["area"], h["key"])
        if k in byk:
            byk[k]["matched"] = "both"
            byk[k]["words"] = h["words"]
        else:
            byk[k] = dict(h, matched="words")
        scores[k] = scores.get(k, 0) + 1.0 / (K + rank)
    for k in scores:
        if k[0] == "entities":
            scores[k] *= ENTITY_WEIGHT
    out = []
    for k in sorted(scores, key=lambda k: -scores[k])[:limit]:
        h = byk[k]
        h["score"] = round(scores[k], 5)
        out.append(h)
    return out


def search(engine, case_id, query: str, *, conn=None, areas: Iterable[str] | None = None, phone: str | None = None,
           person: str | None = None, date_from=None, date_to=None, limit: int = 20,
           embed_query: Callable[[str], list[float]] | None = None, items_collection=None,
           chunks_collection=None) -> dict[str, Any]:
    """The hits, best first, with why each matched and what was not searched."""
    wanted = [a for a in (areas or ALL_AREAS) if a in ALL_AREAS]
    unknown = [a for a in (areas or []) if a not in ALL_AREAS]
    notes: list[str] = []
    if unknown:
        notes.append("Not searched, unknown area: %s." % ", ".join(unknown))
    not_searched: list[str] = []
    if phone and "phone_text" not in wanted:
        notes.append("The phone filter only applies to phone messages, which were not in the areas asked for.")
    if (date_from is not None or date_to is not None) and any(a in wanted for a in ("phone_text", "documents")):
        not_searched += [a for a in ("phone_text", "documents") if a in wanted]
        wanted = [a for a in wanted if a not in ("phone_text", "documents")]
        notes.append("Phone messages and documents were not searched by meaning inside a date window: their passages "
                     "carry no single date. Search them without the dates.")
    from services.phone import chat_retrieval
    terms = chat_retrieval.terms(query)
    meaning: list[dict] = []
    meaning_ok = True
    try:
        if embed_query is None:
            from services.embedding_service import EmbeddingService
            embed_query = EmbeddingService().generate_embedding
        vector = embed_query(query)
        entities_collection = None
        if items_collection is None or chunks_collection is None:
            from services.vector_db_service import get_vector_db_service
            svc = get_vector_db_service()
            items_collection = items_collection or svc.client.get_or_create_collection(name=COLLECTION)
            chunks_collection = chunks_collection or svc.chunk_collection
            entities_collection = svc.entity_collection
        meaning = meaning_hits(case_id, vector, items_collection, chunks_collection, wanted, phone=phone,
                               person=person, date_from=date_from, date_to=date_to,
                               entities_collection=entities_collection)
    except Exception as exc:  # the service refused or is unreachable: words only, said so
        meaning_ok = False
        try:
            from services.meaning_search import describe_failure
            reason = describe_failure(exc)[1]
        except Exception:
            reason = str(exc)[:200]
        notes.append("Meaning search unavailable (%s); searched the words only." % reason)
    if conn is not None:
        words = word_hits(conn, case_id, terms, wanted, phone=phone, person=person, date_from=date_from, date_to=date_to)
    else:
        with engine.connect() as own:
            words = word_hits(own, case_id, terms, wanted, phone=phone, person=person, date_from=date_from,
                              date_to=date_to)
    if "documents" in wanted:
        not_searched.append("documents by words (use the document search for exact words)")
    hits = fuse(meaning, words, limit)
    for h in hits:
        h["snippet"] = _snippet(h.pop("text", ""), terms)
        h.pop("distance", None)
    return {"query": query, "hits": hits, "terms": terms, "areas_searched": wanted, "not_searched": not_searched,
            "meaning_search": meaning_ok, "notes": notes,
            "counts": {"meaning": len(meaning), "words": len(words), "returned": len(hits)}}
