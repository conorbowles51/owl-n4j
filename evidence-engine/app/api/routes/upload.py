import os
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobResponse

router = APIRouter()


@router.post("/cases/{case_id}/files", response_model=JobResponse, status_code=201)
async def upload_file(
    case_id: str,
    request: Request,
    file: UploadFile = File(...),
    llm_profile: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    job_id = uuid.uuid4()

    # Save file to disk: {storage_path}/{case_id}/{job_id}/{filename}
    dir_path = os.path.join(settings.storage_path, case_id, str(job_id))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, file.filename)

    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # Create job record
    job = Job(
        id=job_id,
        case_id=case_id,
        file_name=file.filename,
        file_path=file_path,
        llm_profile=llm_profile,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Enqueue processing task
    pool = request.app.state.arq_pool
    await pool.enqueue_job("process_file", str(job.id))

    return job
