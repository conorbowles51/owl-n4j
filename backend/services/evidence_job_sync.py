from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
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


def reconcile_jobs_payload(db: Session, jobs: list[dict[str, Any]]) -> int:
    engine_job_ids = [str(job.get("id")) for job in jobs if job.get("id")]
    if not engine_job_ids:
        return 0

    db_records = list(
        db.scalars(
            select(EvidenceFile).where(EvidenceFile.engine_job_id.in_(engine_job_ids))
        ).all()
    )
    records_by_job_id = {
        str(record.engine_job_id): record
        for record in db_records
        if record.engine_job_id
    }

    updated = 0
    for job in jobs:
        db_rec = records_by_job_id.get(str(job.get("id")))
        if not db_rec:
            continue
        if _sync_db_record_from_job(db_rec, job):
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
    if reconcile_jobs_payload(db, [job]):
        db.commit()
    return job
