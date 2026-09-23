import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.job import Job, JobStatus
from app.schemas.job import JobDetailResponse, JobResponse

router = APIRouter()


@router.post("/jobs/{job_id}/{action}")
async def control_job(job_id: uuid.UUID, action: str, request: Request,
                      case_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    if action not in {"pause", "resume"}:
        raise HTTPException(404, "Unknown job action")
    job = await db.get(Job, job_id)
    if job is None or job.case_id != case_id:
        raise HTTPException(404, "Job not found in this case")
    if job.job_type not in {"ingestion", "pdf_review"}:
        raise HTTPException(409, "This processing type does not yet support checkpoint recovery")
    predicate = Job.batch_id == job.batch_id if job.batch_id else Job.id == job.id
    result = await db.execute(select(Job).where(predicate, Job.case_id == case_id)
                              .order_by(Job.id).with_for_update())
    jobs = [item for item in result.scalars().all() if item.status != JobStatus.COMPLETED]
    if not jobs:
        return {"state": "completed", "affected_jobs": 0}
    if action == "pause":
        queued = all(item.status == JobStatus.PENDING for item in jobs)
        for item in jobs:
            item.pause_requested = True
            if queued:
                item.paused = True
                item.resumable = True
        await db.commit()
        return {"state": "paused" if queued else "pausing", "affected_jobs": len(jobs)}
    if any(item.pause_requested and not item.paused for item in jobs):
        raise HTTPException(409, "Pausing: the current work unit is still finishing. Resume will be available when it has stopped.")
    if not all(item.paused or item.status == JobStatus.FAILED for item in jobs):
        # Repeated Resume after a lost response does not create a new attempt.
        return {"state": "running", "affected_jobs": len(jobs)}
    if not all(item.resumable for item in jobs):
        raise HTTPException(409, "This older run has no saved ingestion checkpoints. Use Retry to process the original file again.")
    generation = max(item.resume_generation for item in jobs) + 1
    for item in jobs:
        item.pause_requested = False
        item.paused = False
        item.status = JobStatus.PENDING
        item.error_message = None
        item.resume_generation = generation
    owner = jobs[0]
    from app.services.pipeline_run_state import transition_batch_dispatch
    state = dict(owner.pipeline_state or {})
    state.pop("batch_dispatch", None)
    state = transition_batch_dispatch(state, dispatch_state="ready",
        batch_id=str(owner.batch_id or owner.id), case_id=case_id)
    state["batch_dispatch"]["queue_job_id"] = f"evidence-resume:{owner.batch_id or owner.id}:{generation}"
    state["batch_dispatch"]["function"] = "process_batch" if owner.batch_id else "process_file"
    owner.pipeline_state = state
    await db.commit()
    from app.services.batch_dispatch import dispatch_ingestion_batch
    await dispatch_ingestion_batch(owner, db, request.app.state.arq_pool)
    return {"state": "queued", "affected_jobs": len(jobs)}


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/cases/{case_id}/jobs", response_model=list[JobResponse])
async def list_jobs(case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job).where(Job.case_id == case_id).order_by(Job.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(status_code=409, detail="Only completed or failed jobs can be deleted")
    await db.delete(job)
    await db.commit()
    return {"deleted": 1, "job_id": str(job_id)}


@router.delete("/cases/{case_id}/jobs")
async def clear_case_jobs(
    case_id: str,
    terminal_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    stmt = delete(Job).where(Job.case_id == case_id)
    if terminal_only:
        stmt = stmt.where(Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED]))
    result = await db.execute(stmt)
    await db.commit()
    return {"deleted": result.rowcount or 0, "case_id": case_id}
