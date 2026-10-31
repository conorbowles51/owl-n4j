from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session, load_only
from starlette.concurrency import run_in_threadpool

from postgres.models.evidence import EvidenceFile
from services import evidence_engine_client


_ACTIVE_JOB_STATUSES = {
    "pending",
    "extracting_text",
    "chunking",
    "extracting_entities",
    "resolving_entities",
    "resolving_relationships",
    "generating_summaries",
    "writing_graph",
}


def _sync_db_record_from_job(db_rec: EvidenceFile, job: dict[str, Any]) -> bool:
    changed = False
    status = str(job.get("status", "") or "")
    now = datetime.now(timezone.utc)

    if status in _ACTIVE_JOB_STATUSES:
        if db_rec.status != "processing":
            db_rec.status = "processing"
            changed = True
        if db_rec.last_error is not None:
            db_rec.last_error = None
            changed = True
        return changed

    if status == "completed":
        if db_rec.status != "processed":
            db_rec.status = "processed"
            changed = True
        if db_rec.last_error is not None:
            db_rec.last_error = None
            changed = True
        if db_rec.processing_stale:
            db_rec.processing_stale = False
            changed = True
        if db_rec.processed_at is None:
            db_rec.processed_at = now
            changed = True

        document_summary = job.get("document_summary")
        if document_summary and db_rec.summary != document_summary:
            db_rec.summary = document_summary
            changed = True

        transcription = job.get("transcription")
        if transcription is not None and db_rec.transcription != transcription:
            db_rec.transcription = transcription
            changed = True

        transcription_segments = job.get("transcription_segments")
        if (
            transcription_segments is not None
            and db_rec.transcription_segments != transcription_segments
        ):
            db_rec.transcription_segments = transcription_segments
            changed = True

        entity_count = job.get("entity_count")
        if entity_count is not None and db_rec.entity_count != entity_count:
            db_rec.entity_count = entity_count
            changed = True

        relationship_count = job.get("relationship_count")
        if relationship_count is not None and db_rec.relationship_count != relationship_count:
            db_rec.relationship_count = relationship_count
            changed = True

        return changed

    if status == "failed":
        error_message = str(job.get("error_message") or "Processing failed").strip()
        if db_rec.status != "failed":
            db_rec.status = "failed"
            changed = True
        if db_rec.last_error != error_message:
            db_rec.last_error = error_message
            changed = True
        if db_rec.processed_at is not None:
            db_rec.processed_at = None
            changed = True
        return changed

    return changed


def _created_at_timestamp(job: dict[str, Any]) -> float | None:
    value = job.get("created_at")
    if isinstance(value, datetime):
        created_at = value
    elif isinstance(value, str):
        try:
            created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.timestamp()


def reconcile_jobs_payload(db: Session, jobs: list[dict[str, Any]]) -> int:
    return _reconcile(db, jobs)[0]


def _reconcile(db: Session, jobs: list[dict[str, Any]]) -> tuple[int, bool]:
    """Apply each file's newest accepted engine attempt to its record. Returns (records updated, settled): settled is
    False when a record that should change was held by another writer and is left for the next run."""
    engine_job_ids = [str(job.get("id")) for job in jobs if job.get("id")]
    source_evidence_file_ids: list[uuid.UUID] = []
    for job in jobs:
        source_id = job.get("source_evidence_file_id")
        if not source_id:
            continue
        try:
            source_evidence_file_ids.append(uuid.UUID(str(source_id)))
        except (ValueError, TypeError):
            continue
    if not engine_job_ids and not source_evidence_file_ids:
        return 0, True

    predicates = []
    if engine_job_ids:
        predicates.append(EvidenceFile.engine_job_id.in_(engine_job_ids))
    if source_evidence_file_ids:
        predicates.append(EvidenceFile.id.in_(source_evidence_file_ids))
    # Only the columns this sync compares or writes: whole rows carry the profile snapshot, metadata and text
    # (26 MB for 6,108 rows on the largest case). Rows already in the session keep what they have loaded.
    db_records = list(
        db.scalars(
            select(EvidenceFile)
            .options(load_only(EvidenceFile.id, EvidenceFile.case_id,
                               *(getattr(EvidenceFile, field) for field in _SYNCED_FIELDS)))
            .where(or_(*predicates))
        ).all()
    )
    accepted_request_ids = _accepted_request_ids(db, predicates)
    records_by_job_id = {
        str(record.engine_job_id): record
        for record in db_records
        if record.engine_job_id
    }
    records_by_source_id = {str(record.id): record for record in db_records}

    # Reprocessing creates several jobs for the same evidence file. Applying
    # every historical attempt would allow an old failure to overwrite the
    # latest success, so only the newest attempt may control the file record.
    latest_jobs_by_record_id: dict[
        str, tuple[tuple[float, int], EvidenceFile, dict[str, Any]]
    ] = {}
    for payload_index, job in enumerate(jobs):
        db_rec = records_by_job_id.get(str(job.get("id")))
        if not db_rec:
            db_rec = records_by_source_id.get(
                str(job.get("source_evidence_file_id") or "")
            )
        if not db_rec:
            continue

        if accepted_request_ids is None:
            request_id = (getattr(db_rec, "last_processed_profile_snapshot", None) or {}).get("ingestion_request_id")
        else:
            request_id = accepted_request_ids.get(db_rec.id)
        if request_id and (job.get("pipeline_state") or {}).get("ingestion_request_id") != request_id:
            # The current upload may not yet have an engine job, or this may
            # be a delayed response from before that upload. Only its accepted
            # request can control this file's status; historical runs remain
            # visible in the jobs list without replacing the current attempt.
            continue

        created_at = _created_at_timestamp(job)
        # Missing/unparseable timestamps retain the documented payload order,
        # where the first item is the newest.
        order_key = (
            created_at if created_at is not None else float("-inf"),
            -payload_index,
        )
        record_id = str(db_rec.id)
        selected = latest_jobs_by_record_id.get(record_id)
        if selected is None or order_key > selected[0]:
            latest_jobs_by_record_id[record_id] = (order_key, db_rec, job)

    pending = [(db_rec, job) for _, db_rec, job in latest_jobs_by_record_id.values()
               if _record_would_change(db_rec, job)]
    if not pending:
        return 0, True
    wanted = len(pending)
    claimed = _claim_without_waiting(db, [db_rec for db_rec, _ in pending])
    if claimed is not None:
        pending = [(db_rec, job) for db_rec, job in pending if db_rec.id in claimed]

    updated = 0
    for db_rec, job in pending:
        if _apply_job(db_rec, job):
            updated += 1

    if updated:
        db.flush()
    return updated, len(pending) == wanted


def _accepted_request_ids(db: Session, predicates) -> dict | None:
    """The ingestion request each matched file last accepted, read as one JSON field instead of loading the whole
    profile snapshot. Pending in-session changes are flushed first (autoflush), so this is what the record holds.
    None for a stand-in session without SQL, where the record's own snapshot is read instead."""
    if not isinstance(db, Session):
        return None
    request_id = EvidenceFile.last_processed_profile_snapshot["ingestion_request_id"].as_string()
    rows = db.execute(select(EvidenceFile.id, request_id).where(or_(*predicates), request_id.is_not(None))).all()
    return {row[0]: row[1] for row in rows if row[1]}


def _apply_job(db_rec: EvidenceFile, job: dict[str, Any]) -> bool:
    changed = False
    job_id = str(job.get("id") or "")
    if job_id and db_rec.engine_job_id != job_id:
        db_rec.engine_job_id = job_id
        changed = True
    if _sync_db_record_from_job(db_rec, job):
        changed = True
    return changed


def _record_would_change(db_rec: EvidenceFile, job: dict[str, Any]) -> bool:
    return _apply_job(_detached_copy(db_rec), job)


_SYNCED_FIELDS = ("engine_job_id", "status", "last_error", "processing_stale", "processed_at", "summary",
                  "transcription", "transcription_segments", "entity_count", "relationship_count")


def _detached_copy(db_rec: EvidenceFile):
    return SimpleNamespace(**{field: getattr(db_rec, field) for field in _SYNCED_FIELDS})


def _claim_without_waiting(db: Session, records: list[EvidenceFile]) -> set | None:
    """Lock the records this sync will write, without ever waiting for a lock.

    Every evidence write appends to its case's audit chain under a per-case
    advisory lock, taken by the trigger after the row lock. This sync writes
    many rows in one transaction, so waiting here (for the chain or for a row
    an import holds) is the shared edge of every deadlock seen live. It is a
    catch-up of engine state that the next poll repeats, so it takes the
    chain first and only if free, then only rows nobody holds; the rest wait
    for the next poll. Returns None when there is nothing to lock (not Postgres).
    """
    bind = db.get_bind() if hasattr(db, "get_bind") else None
    if bind is None or bind.dialect.name != "postgresql":
        return None
    claimed: set = set()
    for case_id in sorted({str(r.case_id) for r in records}):
        held = db.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended('loupe.financial.audit:' || CAST(:case_id AS text), 0))"),
                          dict(case_id=case_id)).scalar()
        if not held:
            continue
        ids = [r.id for r in records if str(r.case_id) == case_id]
        claimed.update(db.scalars(select(EvidenceFile.id).where(EvidenceFile.id.in_(ids))
                                  .order_by(EvidenceFile.id).with_for_update(skip_locked=True)).all())
    if claimed:
        # Re-read what was claimed: another writer may have changed it since the first read.
        list(db.scalars(select(EvidenceFile).where(EvidenceFile.id.in_(claimed))
                        .execution_options(populate_existing=True)).all())
    return claimed


# A case's job list is polled every few seconds from every open Evidence or Financial batch page. Reconciling the
# whole history on each poll reads and claims every file of the case (1,593 jobs on the largest case), so a poll
# reconciles only when the engine's list changed since this process last settled it, or after RECHECK seconds (a
# record changed by another writer is still repaired within that time). One poll per case at a time.
POLL_RECHECK_SECONDS = 30.0
_poll_settled: dict[str, tuple[str, float]] = {}
_poll_locks: dict[str, threading.Lock] = {}
_poll_locks_guard = threading.Lock()

# Every job field the reconcile reads.
_FINGERPRINT_FIELDS = ("id", "source_evidence_file_id", "status", "created_at", "error_message", "document_summary",
                       "transcription", "transcription_segments", "entity_count", "relationship_count")


def _jobs_fingerprint(jobs: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for job in jobs:
        fields = [job.get(name) for name in _FINGERPRINT_FIELDS]
        fields.append((job.get("pipeline_state") or {}).get("ingestion_request_id"))
        digest.update(json.dumps(fields, sort_keys=True, default=str).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def reconcile_case_poll(db: Session, case_id: str, jobs: list[dict[str, Any]]) -> int:
    """Reconcile a polled job list for one case and commit; skipped while the list is unchanged and settled.
    Blocking (database work): call it from a worker thread."""
    fingerprint = _jobs_fingerprint(jobs)
    with _poll_locks_guard:
        lock = _poll_locks.setdefault(case_id, threading.Lock())
    with lock:
        settled = _poll_settled.get(case_id)
        if settled and settled[0] == fingerprint and time.monotonic() - settled[1] < POLL_RECHECK_SECONDS:
            return 0
        _poll_settled.pop(case_id, None)
        started = time.monotonic()
        updated, all_applied = _reconcile(db, jobs)
        db.commit()
        if all_applied:
            _poll_settled[case_id] = (fingerprint, started)
        return updated


def _reconcile_and_commit(db: Session, jobs: list[dict[str, Any]]) -> int:
    updated = reconcile_jobs_payload(db, jobs)
    if updated:
        db.commit()
    return updated


async def reconcile_case_jobs(db: Session, case_id: str) -> int:
    try:
        jobs = await evidence_engine_client.list_jobs(case_id)
    except Exception:
        return 0

    return await run_in_threadpool(_reconcile_and_commit, db, jobs)


async def reconcile_job_by_id(db: Session, job_id: str) -> dict[str, Any]:
    job = await evidence_engine_client.get_job(job_id)
    case_id = str(job.get("case_id") or "")
    if not case_id:
        return job

    try:
        case_jobs = await evidence_engine_client.list_jobs(case_id)
    except Exception:
        # A single historical attempt is not enough context to safely update
        # the file: it may have been superseded by a newer reprocessing job.
        return job

    await run_in_threadpool(_reconcile_and_commit, db, case_jobs)
    return job
