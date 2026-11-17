"""One search across every area, by meaning and by words together (lx-embedall D).

Meaning: the question's vector against the ``case_items`` collection (every area but phone conversations and documents)
and the ``chunks`` collection (phone conversation windows and document passages). Words: the question's folded terms
against the stored item text, and the phone thread documents through ``chat_retrieval.windows``. The two ranked lists are
fused by reciprocal rank fusion with the constant lx-retrieval uses (``retrieval_fusion.K``). Each hit says why it matched
(``meaning``, ``words`` or ``both``). The result lists what was searched and what was not, and says when meaning search
was unavailable and only words were searched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import text

from services.embed_all import phone as phone_area
from services.embed_all.core import COLLECTION
from services.embed_all.sources import AREAS
from services.retrieval_fusion import K, similarity

logger = logging.getLogger(__name__)

ALL_AREAS = tuple(AREAS) + ("phone_text", "documents")
MAX_DISTANCE = 1.44  # squared L2 of unit vectors: cosine 0.28 and above. Measured on the demo case, 17 Nov: relevant hits
# score cosine 0.31 to 0.50, a query with no answer ("burner") scores 0.22 to 0.24 against the nearest unrelated text
SNIPPET = 400
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
    body = body or ""
    at = -1
    low = body.casefold()
    for t in terms:
        at = low.find(t.casefold())
        if at >= 0:
            break
    start = max(0, at - SNIPPET // 3) if at >= 0 else 0
    return body[start:start + SNIPPET].strip()


def _where(case_id, areas, date_from, date_to):
    conds = [{"case_id": str(case_id)}]
    conds.append({"area": areas[0]} if len(areas) == 1 else {"area": {"$in": list(areas)}})
    if date_from is not None:
        conds.append({"item_ts": {"$gte": _ts(date_from)}})
    if date_to is not None:
        conds.append({"item_ts": {"$lte": _ts(date_to)}})
    return {"$and": conds}


def meaning_hits(case_id, query_vector, items_collection, chunks_collection, areas, *, phone=None, person=None,
                 date_from=None, date_to=None) -> list[dict]:
    hits: list[dict] = []
    item_areas = [a for a in areas if a not in ("phone_text", "documents")]
    over = FETCH * 3 if person else FETCH
    if item_areas and items_collection is not None:
        res = items_collection.query(query_embeddings=[query_vector], n_results=over,
                                     where=_where(case_id, item_areas, date_from, date_to),
                                     include=["documents", "metadatas", "distances"])
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            hits.append({"area": meta["area"], "key": meta["item_key"], "title": meta.get("title", ""),
                         "cite": meta.get("cite", ""), "text": doc, "distance": dist, "person": meta.get("person", ""),
                         "as_read": bool(meta.get("as_read"))})
    chunk_areas = [a for a in areas if a in ("phone_text", "documents")]
    if chunk_areas and chunks_collection is not None and (date_from is None and date_to is None):
        conds = [{"case_id": str(case_id)}, {"ingestion_state": "active"}]
        if chunk_areas == ["phone_text"]:
            conds.append({"source_kind": "phone_text"})
        if phone:
            conds.append({"extraction_id": str(phone)})
        res = chunks_collection.query(query_embeddings=[query_vector], n_results=over,
                                      where={"$and": conds}, include=["documents", "metadatas", "distances"])
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
            is_phone = meta.get("source_kind") == "phone_text"
            area = "phone_text" if is_phone else "documents"
            if area not in chunk_areas:
                continue
            cite = meta.get("url") if is_phone else "doc://%s/%s" % (meta.get("evidence_file_id") or meta.get("doc_id"),
                                                                     meta.get("page_start") or "")
            hits.append({"area": area, "key": "%s:%s" % (meta.get("evidence_file_id"), meta.get("chunk_index")),
                         "title": meta.get("doc_name") or meta.get("file_name") or "", "cite": cite or "",
                         "text": doc, "distance": dist, "person": "", "as_read": False})
    if person:
        who = person.casefold()
        hits = [h for h in hits if who in (h["person"] + " " + h["text"]).casefold()]
    kept, seen = [], set()
    for h in sorted((h for h in hits if h["distance"] is not None and h["distance"] <= MAX_DISTANCE),
                    key=lambda h: h["distance"]):
        one = (h["area"], h["cite"] or h["key"], h["title"])  # two passages of one page are one hit: the nearer stays
        if h["area"] in ("documents",) and one in seen:
            continue
        seen.add(one)
        kept.append(h)
    return kept


def word_hits(conn, case_id, terms: list[str], areas, *, phone=None, person=None, date_from=None, date_to=None) -> list[dict]:
    hits: list[dict] = []
    item_areas = [a for a in areas if a not in ("phone_text", "documents")]
    if terms and item_areas:
        params: dict[str, Any] = {"c": str(case_id), "areas": item_areas}
        conds = []
        for i, t in enumerate(terms):
            params["t%d" % i] = "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            conds.append("(body_folded LIKE :t%d)::int" % i)
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
    for rank, h in enumerate(sorted(meaning, key=lambda h: h["distance"]), 1):
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
        if items_collection is None or chunks_collection is None:
            from services.vector_db_service import get_vector_db_service
            svc = get_vector_db_service()
            items_collection = items_collection or svc.client.get_or_create_collection(name=COLLECTION)
            chunks_collection = chunks_collection or svc.chunk_collection
        meaning = meaning_hits(case_id, vector, items_collection, chunks_collection, wanted, phone=phone,
                               person=person, date_from=date_from, date_to=date_to)
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
