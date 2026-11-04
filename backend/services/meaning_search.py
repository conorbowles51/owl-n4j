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
   when the service answers again (``record_success`` -> ``run_gap_backfill``).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from uuid import UUID

logger = logging.getLogger(__name__)

SERVICE = "meaning_search"
MAX_TERMS = 8
GAP_CACHE_SECONDS = 600
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
) -> dict[str, Any]:
    """The case's documents holding the query's words, ranked and paged by document with totals.

    Ranking counts each term's documents in the database (``matching_documents``: no text loaded); only the page's
    documents are then read through ``search_case_text`` for their hits."""
    from services.evidence_text_search_service import matching_documents, search_case_text
    case_uuid = case_id if isinstance(case_id, UUID) else UUID(str(case_id))
    searches, not_searched = _searches(query)
    documents: dict[Any, dict[str, Any]] = {}
    for kind, value in searches:
        for evidence_id, name, count in matching_documents(db, case_id=case_uuid, query=value):
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
                            search_nodes: Callable[..., list[dict[str, Any]]] | None = None) -> list[str]:
    """Entity keys found by the existing graph name search (``graph_service.search_nodes``) for each term."""
    if search_nodes is None:
        from services.neo4j.graph_service import graph_service
        search_nodes = graph_service.search_nodes
    keys: list[str] = []
    for kind, value in _searches(question)[0]:
        for row in search_nodes(value, limit=limit, case_id=case_id) or []:
            key = row.get("key")
            if key and key not in keys:
                keys.append(key)
    return keys


# ------------------------------------------------------------------------------------------------- vector gaps

_gap_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_gap_lock = threading.Lock()


def _searchable_vector_refs(collection, case_id: str) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    names: set[str] = set()
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
            for key in ("evidence_file_id", "doc_id"):
                if meta.get(key):
                    ids.add(str(meta[key]))
            for key in ("doc_name", "file_name", "filename"):
                if meta.get(key):
                    names.add(str(meta[key]))
        offset += len(got)
    return ids, names


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

        def rows(session):
            return session.execute(
                select(EvidenceFile.id, EvidenceFile.original_filename)
                .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
                .where(EvidenceFile.case_id == UUID(case_id),
                       EvidenceFile.source_type.is_distinct_from("phone_text"))
            ).all()

        if db is None:
            from postgres.session import get_background_session
            with get_background_session() as session:
                files = rows(session)
        else:
            files = rows(db)
        ids, names = _searchable_vector_refs(collection, case_id)
        missing = [str(fid) for fid, name in files if str(fid) not in ids and str(name) not in names]
        gap = {"documents_with_text": len(files), "documents_with_vector": len(files) - len(missing),
               "documents_without_vector": len(missing), "missing_evidence_file_ids": missing,
               "measured_at": _now().isoformat()}
    except Exception:
        logger.exception("Meaning-search vector gap could not be measured for case %s", case_id)
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
    return {k: v for k, v in gap.items() if k != "missing_evidence_file_ids"}


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
    """Remember that meaning search answered. The call that ends an outage starts the gap backfill (decision 3)."""
    with _memo_lock:
        if _memo["status"] == "up" and _memo["checked_pending"]:
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
    successes = [v for v in ((row or {}).get("last_success_at"), last_cost) if v is not None]
    last_success = max(successes) if successes else None
    out = {"status": (row or {}).get("status") or "unknown",
           "reason_code": (row or {}).get("reason_code"), "reason": (row or {}).get("reason"),
           "down_since": _iso((row or {}).get("down_since")),
           "last_failure_at": _iso((row or {}).get("last_failure_at")),
           "last_success_at": _iso(last_success),
           "failures_since_down": int((row or {}).get("failures_since_down") or 0),
           "backfill_pending": bool((row or {}).get("backfill_pending"))}
    if out["status"] != "down":
        out["reason"] = out["reason_code"] = None
        out["down_since"] = None
    return out


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


def run_gap_backfill(*, case_ids: Iterable[str] | None = None, backfill: Callable | None = None,
                     gap: Callable | None = None, session_factory: Callable | None = None,
                     log: Callable[[str, str], None] | None = None, lock: bool = True) -> dict[str, Any]:
    """Embed every document with text and no vector, case by case, one document at a time, through the existing
    chunk backfill (``scripts.backfill_chunk_embeddings``). Stops at the first failure that would repeat; the
    pending flag stays set, so the next successful call starts it again."""
    from sqlalchemy import text
    _lower_priority()
    if backfill is None:
        from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings as backfill
    gap = gap or vector_gap
    log = log or _system_log
    factory = session_factory or _session_factory
    summary: dict[str, Any] = {"cases": 0, "documents_embedded": 0, "chunks": 0, "stopped": None}
    with factory() as db:
        if lock and db.get_bind().dialect.name == "postgresql":
            if not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": BACKFILL_LOCK_KEY}).scalar():
                summary["stopped"] = "another gap backfill is running"
                return summary
        try:
            cases = list(case_ids) if case_ids is not None else _gap_cases(db)
            log("info", "Meaning-search gap backfill started over %d case(s)" % len(cases))
            for case_id in cases:
                found = gap(case_id, fresh=True)
                missing = (found or {}).get("missing_evidence_file_ids") or []
                if not missing:
                    continue
                summary["cases"] += 1
                log("info", "Case %s: %d document(s) with text and no meaning-search vector" % (case_id, len(missing)))
                result = backfill(case_id=case_id, evidence_file_ids=missing, prefer_stored_text=True,
                                  stop_on_failure=True, pause_seconds=BACKFILL_PAUSE_SECONDS,
                                  log_callback=log)
                stats = result.get("stats") or {}
                summary["documents_embedded"] += int(stats.get("processed") or 0)
                summary["chunks"] += int(stats.get("total_chunks_created") or 0)
                with _gap_lock:
                    _gap_cache.pop(str(case_id), None)
                if result.get("stopped"):
                    summary["stopped"] = result["stopped"]
                    break
            if summary["stopped"] is None:
                db.execute(text("UPDATE service_health_states SET backfill_pending = false, updated_at = :now "
                                "WHERE service = :service"), {"service": SERVICE, "now": _now()})
                db.commit()
            log("info" if summary["stopped"] is None else "warning",
                "Meaning-search gap backfill %s: %d document(s), %d chunk(s) embedded in %d case(s)%s" % (
                    "finished" if summary["stopped"] is None else "stopped", summary["documents_embedded"],
                    summary["chunks"], summary["cases"],
                    "" if summary["stopped"] is None else "; stopped: %s" % summary["stopped"]))
        finally:
            if lock and db.get_bind().dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": BACKFILL_LOCK_KEY})
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
