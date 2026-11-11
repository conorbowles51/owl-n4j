"""Document meaning search (OpenAI embeddings) and what every caller does when it fails (lx-docsearch).

Meaning search turns the question into a vector and finds the document chunks whose vectors are near it. When the
service that makes vectors fails (on live since 2026-10-28: 429 "insufficient quota, no credits remaining"), each
caller searches the words of the question through the existing case word search
(``evidence_text_search_service.search_case_text``) and says so, in its result and in the answer:

    Meaning search unavailable (<reason>); searched the words instead: N of M documents searchable.

Word hits are literal matches of a term or the phrase; they are never presented as meaning matches.

Decisions (LX-DOCSEARCH-STATUS.md; each reversible):
1. Every caller falls back to word search and says so. Reverse if meaning search moves to a service that is up.
2. Word search runs each significant term of the query, then the whole phrase; documents are ranked by phrase hit,
   then by how many terms they hold, then by hit count, and paged with totals. Terms beyond ``MAX_TERMS`` are listed
   as not searched, never dropped silently.
3. A document whose text has no meaning-search vector is never treated as absent: ``vector_gap`` counts them per
   case, the count is shown wherever meaning search is used, and they are embedded by the existing chunk backfill
   when the service answers again (``record_success`` -> ``run_gap_backfill``). A file ingested during an outage holds
   its chunks in ``pending_chunk_vectors``; the evidence engine's sweep embeds those, and they count in the gap.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from uuid import UUID

logger = logging.getLogger(__name__)

SERVICE = "meaning_search"
MAX_TERMS = 8
GAP_CACHE_SECONDS = 600
PENDING_RECHECK_SECONDS = 600
BACKFILL_LOCK_KEY = 7310402  # pg advisory lock: one gap backfill at a time across workers
BACKFILL_PAUSE_SECONDS = 0.5
BACKFILL_NICE = 15

STOPWORDS = frozenset("""
a about above after again against all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each else every few find for from further get had has have having he
her here hers him his how i if in into is it its itself just look me more most my no nor not now of off on once only
or other our ours out over own per please same she should show so some such tell than that the their theirs them
then there these they this those through to too under until up upon us very via was we were what when where which
while who whom why will with within without would you your yours any anything something
""".split())

_TERM_RE = re.compile(r"[^\W_](?:[\w'@./&-]*[^\W_])?", re.UNICODE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------------------------- failure reasons

def describe_failure(exc: BaseException) -> tuple[str, str]:
    """(code, plain reason) for a failed meaning-search call."""
    text = str(exc)
    low = text.lower()
    status = getattr(exc, "status_code", None)
    if "insufficient_quota" in low or "credit_balance_exhausted" in low or "no credits remaining" in low:
        return "quota", "the search service (OpenAI) has no credits left: 429 insufficient quota"
    if status == 429 or "error code: 429" in low:
        return "rate_limited", "the search service (OpenAI) is refusing requests: 429 too many requests"
    if status in (401, 403) or "incorrect api key" in low or "invalid api key" in low:
        return "key_rejected", "the search service (OpenAI) rejected its API key"
    if "not connected" in low or "not configured" in low:
        return "not_configured", "the search service (OpenAI) is not connected"
    return "error", "the search service failed: %s: %s" % (type(exc).__name__, text[:160])


# Codes after which a backfill stops at once (every further call would fail the same way).
STOP_CODES = frozenset({"quota", "rate_limited", "key_rejected", "not_configured"})


def fallback_note(reason: str, *, searchable_documents: int, case_documents: int) -> str:
    return ("Meaning search unavailable (%s); searched the words instead: %d of %d documents searchable."
            % (reason, searchable_documents, case_documents))


# ------------------------------------------------------------------------------------------------- word search

def search_terms(query: str) -> tuple[list[str], list[str]]:
    """(significant terms to search, significant terms beyond MAX_TERMS that are not searched)."""
    seen: set[str] = set()
    terms: list[str] = []
    for raw in _TERM_RE.findall(query or ""):
        low = raw.lower()
        if low in seen or low in STOPWORDS:
            continue
        if len(low) < 3 and not any(ch.isdigit() for ch in low):
            continue
        seen.add(low)
        terms.append(raw)
    return terms[:MAX_TERMS], terms[MAX_TERMS:]


def _searches(query: str) -> tuple[list[tuple[str, str]], list[str]]:
    terms, not_searched = search_terms(query)
    phrase = " ".join((query or "").split())
    searches = [("term", t) for t in terms]
    if phrase and phrase.lower() not in {t.lower() for t in terms}:
        searches.append(("phrase", phrase))
    return searches, not_searched


def word_search_documents(
    db,
    *,
    case_id: str | UUID,
    query: str,
    limit: int,
    offset: int = 0,
    snippet_context: int = 300,
    max_matches_per_document: int = 3,
    evidence_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """The case's documents holding the query's words, ranked and paged by document with totals.

    Ranking counts each term's documents in the database (``matching_documents``: no text loaded); only the page's
    documents are then read through ``search_case_text`` for their hits."""
    from services.evidence_text_search_service import matching_documents, search_case_text
    case_uuid = case_id if isinstance(case_id, UUID) else UUID(str(case_id))
    searches, not_searched = _searches(query)
    documents: dict[Any, dict[str, Any]] = {}
    for kind, value in searches:
        for evidence_id, name, count in matching_documents(db, case_id=case_uuid, query=value,
                                                           evidence_ids=evidence_ids):
            entry = documents.setdefault(evidence_id, {"evidence_id": evidence_id, "filename": name,
                                                       "phrase_matched": False, "terms": [], "total_matches": 0})
            if kind == "phrase":
                entry["phrase_matched"] = True
            entry["terms"].append((kind, value))
            entry["total_matches"] += count
    ranked = sorted(documents.values(), key=lambda e: (
        not e["phrase_matched"], -sum(1 for k, _ in e["terms"] if k == "term"), -e["total_matches"],
        str(e["filename"]).lower(), str(e["evidence_id"])))
    page = ranked[offset:offset + limit]
    hits: dict[Any, list[dict[str, Any]]] = {e["evidence_id"]: [] for e in page}
    details: dict[Any, dict[str, Any]] = {}
    counts = None
    for kind, value in searches:
        wanted = [e["evidence_id"] for e in page if (kind, value) in e["terms"]]
        if not wanted and counts is not None:
            continue
        found = search_case_text(db, case_id=case_uuid, query=value, document_limit=max(1, len(wanted)),
                                 document_offset=0, snippet_context=snippet_context, evidence_ids=wanted)
        counts = (int(found.get("case_documents") or 0), int(found.get("searchable_documents") or 0))
        for doc in found.get("documents") or []:
            key = next((k for k in hits if str(k) == doc["evidence_id"]), None)
            if key is None:
                continue
            details[key] = doc
            hits[key].extend(dict(m, term=value, term_kind=kind) for m in doc.get("matches") or [])
    if counts is None:  # the query had nothing to search
        found = search_case_text(db, case_id=case_uuid, query=query or " ", document_limit=1, document_offset=0,
                                 evidence_ids=[])
        counts = (int(found.get("case_documents") or 0), int(found.get("searchable_documents") or 0))
    results = []
    for entry in page:
        matches = sorted(hits[entry["evidence_id"]], key=lambda m: m["term_kind"] != "phrase")
        picked, terms_seen = [], set()
        for match in matches:  # one hit per term first, so each term the document holds is shown
            if match["term"].lower() not in terms_seen and len(picked) < max_matches_per_document:
                picked.append(match)
                terms_seen.add(match["term"].lower())
        for match in matches:
            if len(picked) >= max_matches_per_document:
                break
            if match not in picked:
                picked.append(match)
        detail = details.get(entry["evidence_id"]) or {}
        results.append({
            "evidence_file_id": str(entry["evidence_id"]), "filename": entry["filename"],
            "folder_path": detail.get("folder_path"), "source_type": detail.get("source_type"),
            "phrase_matched": entry["phrase_matched"],
            "terms_matched": [v for k, v in entry["terms"] if k == "term"],
            "total_matches": entry["total_matches"], "matches_shown": len(picked),
            "matches_truncated": entry["total_matches"] > len(picked), "matches": picked})
    total = len(ranked)
    return {
        "search": "word",
        "query": query,
        "terms_searched": [v for k, v in searches if k == "term"],
        "phrase_searched": next((v for k, v in searches if k == "phrase"), None),
        "terms_not_searched": not_searched,
        "case_documents": counts[0],
        "searchable_documents": counts[1],
        "total_documents": total,
        "returned_documents": len(results),
        "offset": offset,
        "next_offset": offset + len(results) if offset + len(results) < total else None,
        "documents": results,
    }


def exact_words_documents(db, *, case_id: str | UUID, query: str, limit: int, offset: int = 0,
                          snippet_context: int = 300, max_matches_per_document: int = 3) -> dict[str, Any]:
    """The case's documents holding exactly these words (one literal phrase, any case), most occurrences first, paged
    by document with true totals. Counted in the database, so only the returned documents' text is read."""
    from services.evidence_text_search_service import matching_documents, search_case_text
    case_uuid = case_id if isinstance(case_id, UUID) else UUID(str(case_id))
    ranked = sorted(matching_documents(db, case_id=case_uuid, query=query),
                    key=lambda row: (-row[2], str(row[1]).lower(), str(row[0])))
    page = ranked[offset:offset + limit]
    wanted = [row[0] for row in page]
    found = search_case_text(db, case_id=case_uuid, query=query, document_limit=max(1, len(wanted)), document_offset=0,
                             snippet_context=snippet_context, evidence_ids=wanted)
    by_id = {doc["evidence_id"]: doc for doc in found["documents"]}
    documents = []
    for evidence_id, _, _ in page:
        doc = by_id.get(str(evidence_id))
        if doc is not None:
            documents.append({"evidence_file_id": doc["evidence_id"], "filename": doc["document_name"],
                              "folder_path": doc["folder_path"], "total_matches": doc["total_matches"],
                              "matches_shown": min(len(doc["matches"]), max_matches_per_document),
                              "matches_truncated": doc["total_matches"] > max_matches_per_document,
                              "matches": doc["matches"][:max_matches_per_document]})
    return {"query": query, "case_documents": int(found["case_documents"]),
            "searchable_documents": int(found["searchable_documents"]), "total_documents": len(ranked),
            "total_matches": sum(int(row[2]) for row in ranked), "returned_documents": len(documents),
            "offset": offset, "next_offset": offset + len(page) if offset + len(page) < len(ranked) else None,
            "documents": documents}


def word_hit_chunks(found: dict[str, Any]) -> list[dict[str, Any]]:
    """Word-search hits shaped as retrieval chunks (chat context and sources), marked as word matches."""
    chunks = []
    for doc in found.get("documents") or []:
        for match in doc.get("matches") or []:
            chunks.append({
                "id": match.get("id"),
                "text": match.get("snippet") or "",
                "_word_match": True,  # no "distance": a word hit has no meaning score
                "metadata": {k: v for k, v in {
                    "doc_name": doc["filename"], "filename": doc["filename"],
                    "evidence_file_id": doc["evidence_file_id"], "page_start": match.get("page_number"),
                    "record_uid": match.get("record_uid"), "extraction_id": match.get("extraction_id"),
                    "start_char": match.get("start_char"), "end_char": match.get("end_char"),
                    "match": "word", "matched_term": match.get("term")}.items() if v is not None},
            })
    return chunks


def word_search_entity_keys(question: str, *, case_id: str, limit: int,
                            search_nodes: Callable[..., list[dict[str, Any]]] | None = None) -> tuple[list[str], int]:
    """(entity keys, how many matched in all) by the existing graph name search (``graph_service.search_nodes``),
    run for each term and the phrase; keys holding more of the terms (and the phrase) come first."""
    if search_nodes is None:
        from services.neo4j.graph_service import graph_service
        search_nodes = graph_service.search_nodes
    score: dict[str, list[int]] = {}
    for position, (kind, value) in enumerate(_searches(question)[0]):
        for rank, row in enumerate(search_nodes(value, limit=limit, case_id=case_id) or []):
            key = row.get("key")
            if not key:
                continue
            entry = score.setdefault(key, [0, 0, position, rank])
            entry[0 if kind == "phrase" else 1] += 1
    ordered = sorted(score, key=lambda k: (-score[k][0], -score[k][1], score[k][2], score[k][3]))
    return ordered[:limit], len(ordered)


# ------------------------------------------------------------------------------------------------- vector gaps

_gap_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_gap_lock = threading.Lock()


def _searchable_vector_refs(collection, case_id: str) -> list[tuple[set[str], str | None]]:
    """(ids, file name) of every searchable chunk of the case."""
    refs: list[tuple[set[str], str | None]] = []
    offset = 0
    while True:
        res = collection.get(where={"case_id": case_id}, include=["metadatas"], limit=5000, offset=offset)
        got = res.get("ids") or []
        if not got:
            break
        for meta in res.get("metadatas") or []:
            meta = meta or {}
            if meta.get("ingestion_state") not in (None, "", "active"):
                continue  # staged drafts and retired revisions are not searched
            ids = {str(meta[k]) for k in ("evidence_file_id", "doc_id") if meta.get(k)}
            name = next((str(meta[k]) for k in ("doc_name", "file_name", "filename") if meta.get(k)), None)
            refs.append((ids, name))
        offset += len(got)
    return refs


def pending_chunk_counts(db, *, evidence_ids: Iterable[Any] | None = None, case_id: str | None = None) -> dict[str, int]:
    """{evidence file id: published chunks waiting for their vector}. Their file has been ingested; the engine's sweep
    (evidence-engine app/services/pending_chunks.py) embeds them when the service answers, so a file here is never
    shown as fully searchable. ``draft`` rows belong to a run that has not published and are not counted."""
    from sqlalchemy import func, select
    from postgres.models.evidence import PendingChunkVector as Pending
    query = (select(Pending.evidence_file_id, func.count())
             .where(Pending.publication_state == "active", Pending.evidence_file_id.is_not(None))
             .group_by(Pending.evidence_file_id))
    if evidence_ids is not None:
        wanted = [e if isinstance(e, UUID) else UUID(str(e)) for e in evidence_ids]
        if not wanted:
            return {}
        query = query.where(Pending.evidence_file_id.in_(wanted))
    if case_id is not None:
        query = query.where(Pending.case_id == str(case_id))
    return {str(file_id): int(count) for file_id, count in db.execute(query).all()}


def vector_gap(case_id: str, *, db=None, collection=None, fresh: bool = False) -> dict[str, Any] | None:
    """Documents of the case with stored text and no searchable meaning-search vector. Phone thread text is left
    out: it is never embedded by design (docs/cellebrite/02 section 9.8). None when it could not be measured."""
    case_id = str(case_id)
    if not fresh:
        with _gap_lock:
            hit = _gap_cache.get(case_id)
            if hit and time.monotonic() - hit[0] < GAP_CACHE_SECONDS:
                return hit[1]
    try:
        from sqlalchemy import select
        from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
        if collection is None:
            from services.vector_db_service import get_vector_db_service
            service = get_vector_db_service()
            if service is None:
                return None
            collection = service.chunk_collection

        from sqlalchemy import func
        from services.financial.source_lineage import visible_evidence_condition

        def rows(session):
            # Only documents a person sees: an internal statement copy (same bytes as its original, hidden from
            # Evidence) is searched through its original. A document whose reading found no text (a photo, a
            # handwritten plan) has nothing to embed; it is counted on its own, never as a missing vector.
            found = session.execute(
                select(EvidenceFile.id, EvidenceFile.original_filename,
                       func.coalesce(EvidenceDocumentText.character_count,
                                     func.char_length(EvidenceDocumentText.content)))
                .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
                .where(EvidenceFile.case_id == UUID(case_id), visible_evidence_condition())
            ).all()
            return [(fid, name) for fid, name, size in found if size], sum(1 for *_, size in found if not size)

        if db is None:
            from postgres.session import get_background_session
            with get_background_session() as session:
                files, empty = rows(session)
                pending = pending_chunk_counts(session, case_id=case_id)
        else:
            files, empty = rows(db)
            pending = pending_chunk_counts(db, case_id=case_id)
        refs = _searchable_vector_refs(collection, case_id)
        file_ids = {str(fid) for fid, _ in files}
        ids = set().union(*(r for r, _ in refs)) if refs else set()
        # A chunk names its file by id; only an older chunk whose ids are none of this case's files (a graph
        # document id) is matched by file name, so a repeated name never hides a document with no vector.
        names = {name for r, name in refs if name and not (r & file_ids)}
        # A file with waiting chunks is not fully searchable, whatever else of it has a vector.
        missing = [str(fid) for fid, name in files
                   if str(fid) in pending or (str(fid) not in ids and str(name) not in names)]
        gap = {"documents_with_text": len(files), "documents_with_vector": len(files) - len(missing),
               "documents_without_vector": len(missing), "missing_evidence_file_ids": missing,
               "documents_without_text": empty,
               "documents_with_pending_chunks": len(pending), "pending_chunks": sum(pending.values()),
               "pending_evidence_file_ids": sorted(pending),
               "measured_at": _now().isoformat()}
    except Exception:
        logger.exception("Meaning-search vector gap could not be measured for case %s", case_id)
        with _gap_lock:
            _gap_cache[case_id] = (time.monotonic(), None)  # not re-scanned on every request
        return None
    with _gap_lock:
        _gap_cache[case_id] = (time.monotonic(), gap)
    return gap


def gap_sentence(gap: dict[str, Any] | None) -> str | None:
    if gap is None:
        return "Whether every document of this case has a meaning-search vector could not be measured."
    if not gap["documents_without_vector"]:
        return None
    return ("%d of %d documents with text in this case have no meaning-search vector, so meaning search cannot "
            "find them; they are embedded when the search service answers again."
            % (gap["documents_without_vector"], gap["documents_with_text"]))


def public_gap(gap: dict[str, Any] | None) -> dict[str, Any] | None:
    """The gap without its id list (for results put before a model or a person)."""
    if gap is None:
        return None
    return {k: v for k, v in gap.items() if k not in ("missing_evidence_file_ids", "pending_evidence_file_ids")}


# ------------------------------------------------------------------------------------------------- health

_memo: dict[str, Any] = {"status": None, "checked_pending": False}
_memo_lock = threading.Lock()


def _session_factory():
    from postgres.session import get_background_session
    return get_background_session()


def record_failure(exc: BaseException, *, session_factory: Callable | None = None) -> None:
    """Remember that meaning search failed, and since when (the first failure of the current outage)."""
    code, reason = describe_failure(exc)
    now = _now()
    try:
        from sqlalchemy import text
        with (session_factory or _session_factory)() as db:
            db.execute(text("""
                INSERT INTO service_health_states
                    (service, status, reason_code, reason, down_since, last_failure_at, failures_since_down,
                     updated_at)
                VALUES (:service, 'down', :code, :reason, :now, :now, 1, :now)
                ON CONFLICT (service) DO UPDATE SET
                    down_since = CASE WHEN service_health_states.status = 'down'
                                      THEN service_health_states.down_since ELSE EXCLUDED.down_since END,
                    failures_since_down = CASE WHEN service_health_states.status = 'down'
                                               THEN service_health_states.failures_since_down + 1 ELSE 1 END,
                    status = 'down', reason_code = EXCLUDED.reason_code, reason = EXCLUDED.reason,
                    last_failure_at = EXCLUDED.last_failure_at, updated_at = EXCLUDED.updated_at
            """), {"service": SERVICE, "code": code, "reason": reason, "now": now})
            db.commit()
        with _memo_lock:
            _memo["status"] = "down"
    except Exception as err:  # health is a report; it never breaks the search that failed
        logger.warning("Meaning-search failure could not be recorded: %s", err)


def record_success(*, session_factory: Callable | None = None, start_backfill: Callable | None = None) -> None:
    """Remember that meaning search answered. The call that ends an outage starts the gap backfill (decision 3), and
    so does the first call after the evidence engine asked for it, which this process would otherwise not see."""
    with _memo_lock:
        if (_memo["status"] == "up" and _memo["checked_pending"]
                and time.monotonic() - _memo.get("checked_at", 0.0) < PENDING_RECHECK_SECONDS):
            return
    now = _now()
    try:
        from sqlalchemy import text
        with (session_factory or _session_factory)() as db:
            db.execute(text("""
                INSERT INTO service_health_states (service, status, last_success_at, updated_at)
                VALUES (:service, 'up', :now, :now)
                ON CONFLICT (service) DO UPDATE SET
                    backfill_pending = service_health_states.backfill_pending
                                       OR service_health_states.status = 'down',
                    status = 'up', last_success_at = EXCLUDED.last_success_at, failures_since_down = 0,
                    updated_at = EXCLUDED.updated_at
            """), {"service": SERVICE, "now": now})
            pending = db.execute(text("SELECT backfill_pending FROM service_health_states WHERE service = :service"),
                                 {"service": SERVICE}).scalar()
            db.commit()
        with _memo_lock:
            _memo["status"] = "up"
            _memo["checked_pending"] = True
            _memo["checked_at"] = time.monotonic()
        if pending:
            (start_backfill or start_gap_backfill)()
    except Exception as err:
        logger.warning("Meaning-search success could not be recorded: %s", err)


def health(*, db=None) -> dict[str, Any]:
    """What a person needs to see: up or down, why, since when, and the last call that worked."""
    from sqlalchemy import text

    def read(session):
        row = session.execute(text("""
            SELECT status, reason_code, reason, down_since, last_failure_at, last_success_at, failures_since_down,
                   backfill_pending
            FROM service_health_states WHERE service = :service"""), {"service": SERVICE}).mappings().first()
        # The last embedding the cost ledger recorded: a successful call made before this state was kept.
        last_cost = session.execute(text(
            "SELECT max(created_at) FROM cost_records WHERE operation_kind = 'embedding'")).scalar()
        return row, last_cost

    try:
        if db is None:
            with _session_factory() as session:
                row, last_cost = read(session)
        else:
            row, last_cost = read(db)
    except Exception as err:
        logger.warning("Meaning-search health could not be read: %s", err)
        return {"status": "unknown", "reason": "The meaning-search state could not be read."}
    tracked_success = (row or {}).get("last_success_at")
    successes = [v for v in (tracked_success, last_cost) if v is not None]
    last_success = max(successes) if successes else None
    first_recorded = (row or {}).get("down_since")
    # The outage start is known only when this table saw the service answer and then recorded the first failure.
    # When the state table began during an outage (live: shipped 4 Nov while every call had been refused since
    # 28 Oct), its first row is only the first *recorded* failure; the start lies after the last call that worked
    # (followups m11040828134070, rule 1: never more certain than it is).
    start_known = bool(first_recorded is not None and tracked_success is not None
                       and _aware(tracked_success) <= _aware(first_recorded))
    out = {"status": (row or {}).get("status") or "unknown",
           "reason_code": (row or {}).get("reason_code"), "reason": (row or {}).get("reason"),
           "down_since": _iso(first_recorded) if start_known else None,
           "down_since_known": start_known,
           "first_recorded_failure_at": _iso(first_recorded),
           "last_failure_at": _iso((row or {}).get("last_failure_at")),
           "last_success_at": _iso(last_success),
           "failures_since_down": int((row or {}).get("failures_since_down") or 0),
           "backfill_pending": bool((row or {}).get("backfill_pending"))}
    if out["status"] != "down":
        out["reason"] = out["reason_code"] = None
        out["down_since"] = out["first_recorded_failure_at"] = None
        out["down_since_known"] = False
    return out


def _aware(value):
    """Compare stored times whatever their zone: a naive time is UTC (SQLite in tests, timestamptz on live)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def report(ok: bool, exc: BaseException | None = None) -> None:
    """Called by the embedding service after every call."""
    if ok:
        record_success()
    elif exc is not None:
        record_failure(exc)


# ------------------------------------------------------------------------------------------------- gap backfill

def start_gap_backfill() -> threading.Thread:
    thread = threading.Thread(target=run_gap_backfill, name="meaning-search-gap-backfill", daemon=True)
    thread.start()
    return thread


_resume_thread: threading.Thread | None = None
RESUME_FIRST_DELAY_SECONDS = 120
RESUME_INTERVAL_SECONDS = 600


def resume_if_pending(*, session_factory: Callable | None = None,
                      start_backfill: Callable | None = None) -> bool:
    """Start the gap backfill when it is owed and the service is up, without waiting for a search to answer.

    A restart ends a running backfill (its thread dies with the process) and only a later successful embedding call
    started it again: on 8 Nov one stopped at 12:01 in a release, 2,316 of a case's 3,150 documents done, and on
    5-8 Nov one lay idle 2.5 days because nobody searched. The advisory lock keeps it to one per host; a thread still
    running in this process is not started twice."""
    global _resume_thread
    from sqlalchemy import text
    if _resume_thread is not None and _resume_thread.is_alive():
        return False
    with (session_factory or _session_factory)() as db:
        row = db.execute(text("SELECT status, backfill_pending FROM service_health_states WHERE service = :service"),
                         {"service": SERVICE}).first()
    if row is None or row[0] != "up" or not row[1]:
        return False
    _resume_thread = (start_backfill or start_gap_backfill)()
    return True


async def resume_backfill_forever() -> None:
    """Lifespan loop: after a start-up delay, and then every RESUME_INTERVAL_SECONDS, resume an owed backfill."""
    import asyncio
    await asyncio.sleep(RESUME_FIRST_DELAY_SECONDS)
    while True:
        try:
            await asyncio.to_thread(resume_if_pending)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.warning("Meaning-search backfill resume check failed: %s", err)
        await asyncio.sleep(RESUME_INTERVAL_SECONDS)


def _lower_priority() -> None:
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), BACKFILL_NICE)  # this thread only (Linux)
    except Exception:
        pass


def _gap_cases(session) -> list[str]:
    from sqlalchemy import select, func
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    return [str(c) for c, _ in session.execute(
        select(EvidenceFile.case_id, func.count())
        .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
        .where(EvidenceFile.source_type.is_distinct_from("phone_text"))
        .group_by(EvidenceFile.case_id).order_by(func.count())).all()]


def _entity_cases(session) -> list[str]:
    """Every case the entity pass visits: entity vectors go stale by graph edits, so a case with no document gap
    (a phone-only or spreadsheet-only case) still has vectors to refresh."""
    from sqlalchemy import select
    from postgres.models.case import Case
    return [str(c) for c in session.execute(select(Case.id).where(Case.deleted_at.is_(None)).order_by(Case.id)).scalars()]


@contextmanager
def _backfill_lock():
    """One gap backfill at a time across workers: a session-level advisory lock on a dedicated autocommit
    connection held for the whole run (never a pooled session, whose connection can change or time out)."""
    from sqlalchemy import text
    from postgres.session import _get_background_engine
    engine = _get_background_engine()
    if engine.dialect.name != "postgresql":
        yield True
        return
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": BACKFILL_LOCK_KEY}).scalar())
        try:
            yield got
        finally:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": BACKFILL_LOCK_KEY})


@contextmanager
def _no_lock():
    yield True


def run_gap_backfill(*, case_ids: Iterable[str] | None = None, backfill: Callable | None = None,
                     gap: Callable | None = None, session_factory: Callable | None = None,
                     log: Callable[[str, str], None] | None = None, lock: bool = True,
                     entities: Callable | None = None) -> dict[str, Any]:
    """Embed every document with text and no vector, case by case, one document at a time, through the existing
    chunk backfill (``scripts.backfill_chunk_embeddings``); then re-embed every entity vector older than the graph
    (``entity_vectors.backfill_case``: an edit whose re-embed was refused). Stops at the first failure that would
    repeat; the pending flag stays set, so the next successful call starts it again. A caller that passes its own
    ``backfill`` runs the entity pass only when it passes ``entities`` too."""
    from sqlalchemy import text
    _lower_priority()
    if backfill is None:
        from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings as backfill
        if entities is None:
            from services.entity_vectors import backfill_case as entities
    gap = gap or vector_gap
    log = log or _system_log
    factory = session_factory or _session_factory
    summary: dict[str, Any] = {"cases": 0, "documents_embedded": 0, "chunks": 0, "documents_activated": 0,
                               "entities_embedded": 0, "stopped": None}
    with (_backfill_lock() if lock else _no_lock()) as got:
        if not got:
            summary["stopped"] = "another gap backfill is running"
            return summary
        if case_ids is not None:
            cases = list(case_ids)
            entity_cases = cases
        else:
            with factory() as db:
                cases = _gap_cases(db)
                entity_cases = _entity_cases(db)
        log("info", "Meaning-search gap backfill started over %d case(s)" % len(cases))
        for case_id in cases:
            found = gap(case_id, fresh=True)
            # Files with kept chunks are the engine's sweep's to embed: this path would index the same text twice.
            kept = set((found or {}).get("pending_evidence_file_ids") or [])
            missing = [fid for fid in (found or {}).get("missing_evidence_file_ids") or [] if fid not in kept]
            if not missing:
                continue
            summary["cases"] += 1
            log("info", "Case %s: %d document(s) with text and no meaning-search vector" % (case_id, len(missing)))
            result = backfill(case_id=case_id, evidence_file_ids=missing, prefer_stored_text=True,
                              stop_on_failure=True, pause_seconds=BACKFILL_PAUSE_SECONDS, log_callback=log)
            stats = result.get("stats") or {}
            summary["documents_embedded"] += int(stats.get("processed") or 0)
            summary["chunks"] += int(stats.get("total_chunks_created") or 0)
            summary["documents_activated"] += int(stats.get("staged_activated") or 0)
            with _gap_lock:
                _gap_cache.pop(str(case_id), None)
            if result.get("stopped"):
                summary["stopped"] = result["stopped"]
                break
        if summary["stopped"] is None and entities is not None:
            for case_id in entity_cases:
                result = entities(case_id, log=log) or {}
                summary["entities_embedded"] += int(result.get("embedded") or 0)
                if result.get("stopped"):
                    summary["stopped"] = "entity vectors: %s" % result["stopped"]
                    break
        if summary["stopped"] is None:
            with factory() as db:
                db.execute(text("UPDATE service_health_states SET backfill_pending = false, updated_at = :now "
                                "WHERE service = :service"), {"service": SERVICE, "now": _now()})
                db.commit()
        log("info" if summary["stopped"] is None else "warning",
            "Meaning-search gap backfill %s: %d document(s), %d chunk(s) embedded, %d document(s) activated from "
            "staged chunks in %d case(s), %d entity vector(s) refreshed%s" % (
                "finished" if summary["stopped"] is None else "stopped", summary["documents_embedded"],
                summary["chunks"], summary["documents_activated"], summary["cases"], summary["entities_embedded"],
                "" if summary["stopped"] is None else "; stopped: %s" % summary["stopped"]))
    return summary


def _system_log(level: str, message: str) -> None:
    logger.info("[meaning-search backfill] %s", message)
    try:
        from services.system_log_service import LogOrigin, LogType, system_log_service
        system_log_service.log(log_type=LogType.DOCUMENT_INGESTION, origin=LogOrigin.BACKEND,
                               action="Meaning-search gap backfill: %s" % message, details={"level": level},
                               success=level != "error")
    except Exception:
        pass
