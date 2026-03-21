import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.job import Job
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
