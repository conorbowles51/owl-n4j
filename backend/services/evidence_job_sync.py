from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

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
        return 0

    predicates = []
    if engine_job_ids:
        predicates.append(EvidenceFile.engine_job_id.in_(engine_job_ids))
    if source_evidence_file_ids:
        predicates.append(EvidenceFile.id.in_(source_evidence_file_ids))
    db_records = list(
        db.scalars(
            select(EvidenceFile).where(or_(*predicates))
        ).all()
    )
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

    updated = 0
    for _, db_rec, job in latest_jobs_by_record_id.values():
        changed = False
        job_id = str(job.get("id") or "")
        if job_id and db_rec.engine_job_id != job_id:
            db_rec.engine_job_id = job_id
            changed = True
        if _sync_db_record_from_job(db_rec, job):
            changed = True
        if changed:
            updated += 1

    if updated:
        db.flush()
    return updated


async def reconcile_case_jobs(db: Session, case_id: str) -> int:
    try:
        jobs = await evidence_engine_client.list_jobs(case_id)
    except Exception:
        return 0

    updated = reconcile_jobs_payload(db, jobs)
    if updated:
        db.commit()
    return updated


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

    if reconcile_jobs_payload(db, case_jobs):
        db.commit()
    return job
