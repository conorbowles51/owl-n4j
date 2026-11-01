"""Phone intake endpoints (01 section 4.3): detect, create a capture job, cancel, re-reconcile."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.job import Job, JobStatus
from app.phone import detect, paths
from app.schemas.job import JobResponse
from app.services.processing_queues import PHONE_CAPTURE_QUEUE

router = APIRouter()


class DetectRequest(BaseModel):
    path: str


class PhoneJobRequest(BaseModel):
    request_id: uuid.UUID
    container_path: str
    root_path: str = ""
    evidence_folder_id: uuid.UUID | None = None
    container_evidence_id: uuid.UUID
    requested_by_user_id: uuid.UUID | None = None
    original_name: str | None = None
    upload_sha256: str | None = None
    upload_group_id: uuid.UUID | None = None


@router.post("/cases/{case_id}/phone/detect")
async def detect_phone(case_id: str, body: DetectRequest):
    """The 01 section 2.5 classification. Detection never writes and never extracts."""
    _, full = paths.resolve(case_id, body.path)
    return await asyncio.to_thread(detect.classify, str(full))


def _payload(body: PhoneJobRequest, container_rel: str, root_rel: str) -> dict:
    return {
        "container_path": container_rel,
        "root_path": root_rel,
        "evidence_folder_id": str(body.evidence_folder_id) if body.evidence_folder_id else None,
        "container_evidence_id": str(body.container_evidence_id),
        "requested_by_user_id": str(body.requested_by_user_id) if body.requested_by_user_id else None,
        "original_name": body.original_name,
        "upload_sha256": body.upload_sha256,
        "upload_group_id": str(body.upload_group_id) if body.upload_group_id else None,
    }


@router.post("/cases/{case_id}/phone/jobs", response_model=JobResponse, status_code=201)
async def create_phone_job(case_id: str, body: PhoneJobRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Idempotent on ``request_id`` (PA-7 to PA-10)."""
    container_rel, full = paths.resolve(case_id, body.container_path)
    root_rel = paths.clean(body.root_path)
    if root_rel and any(p in ("", ".", "..") for p in root_rel.split("/")):
        raise HTTPException(403, paths.OUTSIDE)
    payload = _payload(body, container_rel, root_rel)
    identity = body.request_id
    job = await db.get(Job, identity)
    if job is None:
        from app.services.pipeline_run_state import transition_batch_dispatch
        state = transition_batch_dispatch({}, dispatch_state="ready", batch_id=str(identity), case_id=case_id)
        state["batch_dispatch"].update(function="process_phone_capture", queue_job_id=f"phone-capture:{identity}")
        state["processing_queue"] = PHONE_CAPTURE_QUEUE
        state["phone"] = {"stage": "received"}
        job = Job(id=identity, case_id=case_id, job_type="phone_capture",
                  file_name=body.original_name or full.name, file_path=str(full),
                  source_folder_id=str(body.evidence_folder_id) if body.evidence_folder_id else None,
                  requested_by_user_id=body.requested_by_user_id,
                  source_evidence_file_id=body.container_evidence_id, merge_payload=payload,
                  pipeline_state=state, status=JobStatus.PENDING)
        db.add(job)
        try:
            await db.commit()
            await db.refresh(job)
        except IntegrityError:  # PA-9: a concurrent first request created it
            await db.rollback()
            job = await db.get(Job, identity)
            if job is None:
                raise
    if job.case_id != case_id or job.job_type != "phone_capture" or job.merge_payload != payload:
        raise HTTPException(409, "This processing request belongs to another selection")  # PA-8
    from app.services.batch_dispatch import dispatch_ingestion_batch
    if (job.pipeline_state or {}).get("batch_dispatch", {}).get("state") != "dispatched":  # PA-10
        await dispatch_ingestion_batch(job, db, request.app.state.arq_pool)
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_phone_job(job_id: uuid.UUID, case_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    """01 section 10.6. Only a ``pending`` extraction's rows are removed; an active one is never cancelled away."""
    job = (await db.execute(select(Job).where(Job.id == job_id).with_for_update())).scalar_one_or_none()
    if job is None or job.case_id != case_id:
        raise HTTPException(404, "Job not found in this case")
    if job.job_type != "phone_capture":
        raise HTTPException(409, "Only phone report readings can be cancelled")
    standing = await _standing(db, job.id)
    if standing in ("active", "superseded"):
        raise HTTPException(409, "This phone report is already in the case and cannot be cancelled. Use Replace or "
                                 "Retire on the extraction.")
    state = dict(job.pipeline_state or {})
    phone = dict(state.get("phone") or {})
    if phone.get("cancelled"):
        return {"state": "cancelled"}
    phone["cancel_requested"] = True
    state["phone"] = phone
    job.pipeline_state = state
    job.pause_requested = True
    running = job.status not in (JobStatus.PENDING, JobStatus.FAILED, JobStatus.COMPLETED) or (
        job.status == JobStatus.PENDING and state.get("batch_dispatch", {}).get("state") == "dispatched"
        and not job.paused)
    await db.commit()
    if running:
        return {"state": "cancelling"}
    from app.phone.job import cancel_rows, CANCELLED_MESSAGE, _extraction_for_job
    from app.phone.store import connect

    def go():
        conn = connect(settings.database_url)
        try:
            ext = _extraction_for_job(conn, job.id)
            return cancel_rows(conn, ext) if ext is not None else True
        finally:
            conn.close()
    await asyncio.to_thread(go)
    phone["cancelled"] = True
    state["phone"] = phone
    job.pipeline_state = dict(state)
    job.status = JobStatus.FAILED
    job.error_message = CANCELLED_MESSAGE
    job.pause_requested = False
    job.paused = False
    await db.commit()
    return {"state": "cancelled"}


async def _standing(db, job_id):
    from sqlalchemy import text
    row = (await db.execute(text("SELECT standing FROM phone_extractions WHERE engine_job_id = :j"),
                            {"j": job_id})).first()
    return row[0] if row else None


@router.post("/cases/{case_id}/phone/extractions/{extraction_id}/reconcile")
async def reconcile_again(case_id: str, extraction_id: uuid.UUID):
    """01 section 8.5: re-run both sides and add a new reconciliation row per document."""
    from app.phone.counter import count_stream
    from app.phone.reconcile import reconcile, store_reconciliation
    from app.phone.recount import recount_document
    from app.phone.store import connect

    def go():
        conn = connect(settings.database_url)
        try:
            row = conn.execute("SELECT e.case_id, c.stored_path, l.root_path FROM phone_extractions e JOIN "
                               "phone_extraction_container_links l ON l.extraction_id = e.id JOIN "
                               "phone_extraction_containers c ON c.id = l.container_id WHERE e.id = %s "
                               "ORDER BY l.linked_at LIMIT 1", (extraction_id,)).fetchone()
            if row is None or str(row[0]) != str(case_id):
                return None
            _, full = paths.resolve(case_id, row[1])
            source = detect.open_source(str(full))
            out = []
            try:
                docs = conn.execute("SELECT document_index, path FROM phone_extraction_documents WHERE "
                                    "extraction_id = %s AND parse_state <> 'empty' ORDER BY 1",
                                    (extraction_id,)).fetchall()
                for i, path in docs:
                    with source.open(path) as fh:
                        src = count_stream(fh)
                    cap = recount_document(conn, extraction_id, i)
                    result, diffs = reconcile(src, cap)
                    with conn.transaction():
                        store_reconciliation(conn, extraction_id, i, src, cap, result, diffs)
                    out.append({"document_index": i, "result": result, "difference_count": len(diffs)})
            finally:
                source.close()
            return out
        finally:
            conn.close()
    out = await asyncio.to_thread(go)
    if out is None:
        raise HTTPException(404, "Extraction not found in this case")
    return {"documents": out}
