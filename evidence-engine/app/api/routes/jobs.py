import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.job import Job, JobStatus
from app.schemas.job import JobResponse

router = APIRouter()


@router.get("/jobs/{job_id}", response_model=JobResponse)
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
