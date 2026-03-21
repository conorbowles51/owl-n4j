"""
File management routes — list, serve, and delete evidence files.
"""

import logging
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/cases/{case_id}/files", response_model=list[JobResponse])
async def list_files(
    case_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all uploaded files (jobs) for a case, ordered by creation date descending."""
    result = await db.execute(
        select(Job)
        .where(Job.case_id == case_id)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    return jobs


@router.get("/cases/{case_id}/files/{job_id}")
async def serve_file(
    case_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve/download an evidence file by job ID."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.case_id == case_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    media_type = job.mime_type or "application/octet-stream"

    return FileResponse(
        path=job.file_path,
        filename=job.file_name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{job.file_name}"',
        },
    )


@router.delete("/cases/{case_id}/files/{job_id}", status_code=204)
async def delete_file(
    case_id: str,
    job_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete an evidence file from storage and its job record.

    Note: Neo4j/ChromaDB cleanup is the backend's responsibility.
    This only removes the physical file and the job record.
    """
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.case_id == case_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="File not found")

    # Delete file from disk
    if os.path.exists(job.file_path):
        try:
            os.remove(job.file_path)
            # Remove the job directory if empty
            job_dir = os.path.dirname(job.file_path)
            if os.path.isdir(job_dir) and not os.listdir(job_dir):
                shutil.rmtree(job_dir, ignore_errors=True)
        except OSError as e:
            logger.warning("Failed to delete file %s: %s", job.file_path, e)

    # Delete job record
    await db.delete(job)
    await db.commit()
