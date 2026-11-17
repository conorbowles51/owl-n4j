"""Cast a wide net (plan R2b): every candidate from every kind of case material, each with its whole text.

Lists gathered, each in its own order:
- meaning and words over every embedded area (``embed_all.search.meaning_hits`` / ``word_hits``): phone message
  windows, ledger rows, accounts, judgement calls, trails, statement pages, notes and findings, timeline, parties,
  transcripts, document passages. Run for the question, for each other phrasing (meaning only) and for each name
  expansion (words only);
- documents by their words (``meaning_search.word_search_documents``), which the embedded-area word search does not
  cover;
- graph entities by name, key, summary and alias (``graph_service.search_nodes``, once per name or term) and by
  meaning (the entity vectors).

The lists are fused by reciprocal rank fusion (``retrieval_fusion.K``). Each candidate keeps the text the source
returned in full (``text``); ``units`` makes it a whole unit and ``rerank`` reads an excerpt of it.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from services.retrieval_fusion import K

logger = logging.getLogger(__name__)

# The kinds a caller asks for, and the embedded areas each covers.
KIND_AREAS: dict[str, tuple[str, ...]] = {
    "phones": ("phone_text", "parties", "transcripts"),
    "documents": ("documents", "statement_pages"),
    "ledger": ("ledger", "accounts", "judgements", "trails"),
    "graph": (),
    "timeline": ("timeline",),
    "casework": ("casework",),
}
KINDS = tuple(KIND_AREAS)
AREA_KIND = {a: k for k, areas in KIND_AREAS.items() for a in areas}
KIND_LABEL = {"phone_text": "phone messages", "parties": "phone contact", "transcripts": "transcript",
              "documents": "document passage", "statement_pages": "statement page", "ledger": "statement row",
              "accounts": "bank account", "judgements": "judgement call", "trails": "money trail",
              "timeline": "timeline event", "casework": "note or finding", "graph": "graph entity"}
FETCH = 60
GRAPH_TERMS = 4


def _rrf(lists: list[list[dict]]) -> list[dict]:
    """One list from many: a candidate scores sum(1 / (K + rank)) over the lists it is in; its sources are kept."""
    score: dict[tuple, float] = {}
    best: dict[tuple, dict] = {}
    for lst in lists:
        for rank, h in enumerate(lst, 1):
            k = (h["area"], h["key"])
            score[k] = score.get(k, 0.0) + 1.0 / (K + rank)
            if k not in best:
                best[k] = dict(h, sources=set(h.get("sources") or ()))
            else:
                b = best[k]
                b["sources"] |= set(h.get("sources") or ())
                if len(h.get("text") or "") > len(b.get("text") or ""):
                    b["text"] = h["text"]
    out = []
    for k in sorted(score, key=lambda k: -score[k]):
        h = best[k]
        h["fused"] = round(score[k], 6)
        h["sources"] = sorted(h["sources"])
        out.append(h)
    return out


def _embedded(conn, case_id, query, areas, *, embed_query, collections, words=True, meaning=True, phone=None,
              person=None, date_from=None, date_to=None, tag="") -> tuple[list[dict], list[dict], list[str]]:
    from services.embed_all import search as ES
    from services.phone import chat_retrieval
    notes: list[str] = []
    m: list[dict] = []
    w: list[dict] = []
    if meaning and collections is not None:
        try:
            vec = embed_query(query)
            m = ES.meaning_hits(case_id, vec, collections[0], collections[1], list(areas), phone=phone, person=person,
                                date_from=date_from, date_to=date_to)
            m.sort(key=lambda h: h["distance"])
            for h in m:
                h["sources"] = ["meaning" + tag]
        except Exception as exc:  # noqa: BLE001
            try:
                from services.meaning_search import describe_failure
                reason = describe_failure(exc)[1]
            except Exception:  # noqa: BLE001
                reason = str(exc)[:160]
            notes.append("Meaning search unavailable (%s); searched the words only." % reason)
            m = []
    if words:
        terms = chat_retrieval.terms(query)
        try:
            w = ES.word_hits(conn, case_id, terms, list(areas), phone=phone, person=person, date_from=date_from,
                             date_to=date_to)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Word search failed", exc_info=True)
            notes.append("Word search of the embedded records failed (%s)." % str(exc)[:160])
            w = []
        w.sort(key=lambda h: -h.get("words", 0))
        for h in w:
            h["sources"] = ["words" + tag]
    return m, w, notes


def _documents_by_words(conn, case_id, query) -> tuple[list[dict], dict]:
    from sqlalchemy.orm import Session

    from sqlalchemy import text

    from services.meaning_search import word_search_documents
    # Phone conversation files are searched by their message windows (the embedded-area word search); reading them
    # again here cost 11 s a term on the demo case under load (91 of 243 s, profiled 17 Nov).
    ids = [r[0] for r in conn.execute(text(
        "SELECT id FROM evidence_files WHERE case_id = :c AND deleted_at IS NULL AND coalesce(source_type, '') <> "
        "'phone_text'"), {"c": str(case_id)})]
    if not ids:
        return [], {"total_documents": 0, "terms": [], "not_searched": []}
    with Session(bind=conn) as db:
        found = word_search_documents(db, case_id=case_id, query=query, limit=20, offset=0, snippet_context=1200,
                                      max_matches_per_document=3, evidence_ids=ids)
    out = []
    for doc in found.get("documents") or []:
        for mt in doc.get("matches") or []:
            page = mt.get("page_number")
            out.append({"area": "documents", "key": "%s:p%s:%s" % (doc["evidence_file_id"], page, mt.get("start_char")),
                        "title": doc.get("filename") or "", "text": mt.get("snippet") or "",
                        "cite": "doc://%s/%s" % (doc["evidence_file_id"], page or ""), "person": "", "as_read": False,
                        "sources": ["document words"], "page": page})
    return out, {"total_documents": found.get("total_documents"), "terms": found.get("terms_searched"),
                 "not_searched": found.get("terms_not_searched")}


def _graph(case_id, query, names, terms, *, embed_query) -> tuple[list[dict], list[dict], list[str]]:
    notes: list[str] = []
    by_words: list[dict] = []
    seen: dict[str, dict] = {}
    try:
        from services.neo4j.graph_service import graph_service
        probes = list(dict.fromkeys(list(names) + list(terms)))[:GRAPH_TERMS]
        for p in probes:
            for n in graph_service.search_nodes(p, limit=10, case_id=str(case_id)):
                key = n.get("key")
                if not key:
                    continue
                if key in seen:
                    seen[key]["words"] += 1
                    continue
                h = {"area": "graph", "key": key, "title": "%s (%s)" % (n.get("name") or key, n.get("type") or "entity"),
                     "cite": "entity://%s" % key, "person": n.get("name") or "", "as_read": True,
                     "text": " ".join(x for x in (n.get("name"), n.get("summary")) if x), "words": 1,
                     "sources": ["graph names"]}
                seen[key] = h
                by_words.append(h)
        by_words.sort(key=lambda h: -h["words"])
    except Exception as exc:  # noqa: BLE001
        notes.append("Graph entities could not be searched by name (%s)." % str(exc)[:160])
    by_meaning: list[dict] = []
    try:
        from services.vector_db_service import get_vector_db_service
        res = get_vector_db_service().search_entities(embed_query(query), top_k=20,
                                                      filter_metadata={"case_id": str(case_id)})
        for r in res or []:
            if not r.get("id"):
                continue
            by_meaning.append({"area": "graph", "key": r["id"], "title": (r.get("metadata") or {}).get("name") or r["id"],
                               "cite": "entity://%s" % r["id"], "person": "", "as_read": True,
                               "text": r.get("text") or "", "sources": ["graph meaning"]})
    except Exception as exc:  # noqa: BLE001
        notes.append("Graph entities could not be searched by meaning (%s)." % str(exc)[:160])
    return by_words, by_meaning, notes


def gather(conn, case_id, question: str, understood: dict, kinds: tuple[str, ...], *, areas=None, phone=None,
           person=None,
           date_from=None, date_to=None, embed_query: Callable[[str], list[float]] | None = None,
           collections=None) -> dict[str, Any]:
    """Every candidate, fused, with ``searched``/``not_searched``/``notes`` for the result."""
    notes: list[str] = []
    searched: list[str] = []
    not_searched: list[str] = []
    only = set(areas or ())
    if only:
        kinds = tuple(k for k in kinds if k != "graph" or "graph" in only)
    areas = [a for k in kinds for a in KIND_AREAS[k] if not only or a in only]
    if date_from is not None or date_to is not None:
        notes.append("Only records dated inside the dates asked for were searched; phone messages and document "
                     "passages carry no single date, so they were searched without the dates.")
    cache: dict[str, list[float]] = {}
    base_embed = embed_query

    def embed(q: str) -> list[float]:
        nonlocal base_embed
        if q not in cache:
            if base_embed is None:
                from services.embedding_service import EmbeddingService
                base_embed = EmbeddingService().generate_embedding
            cache[q] = base_embed(q)
        return cache[q]

    if collections is None and areas:
        try:
            from services.embed_all.core import COLLECTION
            from services.vector_db_service import get_vector_db_service
            svc = get_vector_db_service()
            collections = (svc.client.get_or_create_collection(name=COLLECTION), svc.chunk_collection)
        except Exception as exc:  # noqa: BLE001
            notes.append("Meaning search unavailable (the vector store did not answer: %s); searched the words only."
                         % str(exc)[:120])
            collections = None
    lists: list[list[dict]] = []
    clock: dict[str, float] = {}
    meaning_ok = collections is not None
    dated = [a for a in areas if a in ("phone_text", "documents")]
    undated = [a for a in areas if a not in ("phone_text", "documents")]
    t0 = time.time()
    if areas:
        # the question itself: meaning and words; dated records inside the dates asked for, messages and passages not
        m, w, n = _embedded(conn, case_id, question, undated, embed_query=embed, collections=collections, phone=phone,
                            person=person, date_from=date_from, date_to=date_to)
        m2, w2, n2 = _embedded(conn, case_id, question, dated, embed_query=embed, collections=collections,
                               phone=phone, person=person) if dated else ([], [], [])
        lists += [m + m2, w + w2]
        for x in n + n2:
            if x not in notes:
                notes.append(x)
        if any(x.startswith("Meaning search unavailable") for x in n + n2):
            meaning_ok = False
        for p in understood.get("phrasings") or []:
            pm, _, pn = _embedded(conn, case_id, p, areas, embed_query=embed, collections=collections, words=False,
                                  phone=phone, person=person, tag=" (other phrasing)")
            lists.append(pm)
        for e in understood.get("expansions") or []:
            _, ew, _ = _embedded(conn, case_id, '"%s"' % e["term"] if " " in e["term"] else e["term"], areas,
                                 embed_query=embed, collections=None, meaning=False, phone=phone, person=person,
                                 tag=" (name tie: %s)" % e["term"])
            lists.append(ew)
        searched += ["%s (%s)" % (k, "meaning and words" if meaning_ok else "words only") for k in kinds
                     if KIND_AREAS[k]]
    clock["embedded_areas"] = round(time.time() - t0, 2)
    t0 = time.time()
    doc_words = None
    if "documents" in kinds and (not only or "documents" in only):
        try:
            dw, doc_words = _documents_by_words(conn, case_id, question)
            lists.append(dw)
            searched.append("documents by their words")
        except Exception as exc:  # noqa: BLE001
            not_searched.append("documents by their words (%s)" % str(exc)[:120])
    clock["document_words"] = round(time.time() - t0, 2)
    t0 = time.time()
    if "graph" in kinds:
        gw, gm, gn = _graph(case_id, question, understood.get("names") or [], understood.get("terms") or [],
                            embed_query=embed)
        lists += [gw, gm]
        notes += gn
        searched.append("graph entities by name, alias and meaning")
    clock["graph"] = round(time.time() - t0, 2)
    for k in KINDS:
        if k not in kinds:
            not_searched.append("%s (not asked for)" % k)
    return {"candidates": _rrf([l for l in lists if l]), "searched": searched, "not_searched": not_searched,
            "notes": notes, "meaning_search": meaning_ok, "documents_by_words": doc_words, "clock": clock}
