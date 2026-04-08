import hashlib
import mimetypes
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


@router.post("/cases/{case_id}/files", response_model=list[JobResponse], status_code=201)
async def upload_files(
    case_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
    llm_profile: str | None = Form(None),
    folder_context: str | None = Form(None),
    sibling_files: str | None = Form(None),
    processing_metadata: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more files for processing.

    All files in a single request are processed as a batch: extracted in
    parallel, then deduplicated together in a single unified pass.
    """
    batch_id = uuid.uuid4()
    jobs: list[Job] = []
    import json as _json

    parsed_processing_metadata: list[dict] | None = None
    if processing_metadata:
        try:
            parsed_processing_metadata = _json.loads(processing_metadata)
            if not isinstance(parsed_processing_metadata, list):
                parsed_processing_metadata = None
        except (ValueError, TypeError):
            parsed_processing_metadata = None

    for index, file in enumerate(files):
        job_id = uuid.uuid4()

        # Save file to disk: {storage_path}/{case_id}/{job_id}/{filename}
        dir_path = os.path.join(settings.storage_path, case_id, str(job_id))
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, file.filename)

        content = await file.read()
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        # Compute file metadata
        file_size = len(content)
        mime_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
        sha256 = hashlib.sha256(content).hexdigest()

        metadata = None
        if parsed_processing_metadata and index < len(parsed_processing_metadata):
            candidate = parsed_processing_metadata[index]
            if isinstance(candidate, dict):
                metadata = candidate

        # Parse sibling_files JSON if provided
        parsed_siblings = None
        if sibling_files:
            try:
                parsed_siblings = _json.loads(sibling_files)
            except (ValueError, TypeError):
                parsed_siblings = None
        if metadata and isinstance(metadata.get("sibling_files"), list):
            parsed_siblings = metadata.get("sibling_files")

        # Create job record
        job = Job(
            id=job_id,
            case_id=case_id,
            batch_id=batch_id,
            file_name=file.filename,
            file_path=file_path,
            llm_profile=llm_profile,
            folder_context=folder_context,
            sibling_files=parsed_siblings,
            effective_context=(metadata or {}).get("effective_context"),
            effective_mandatory_instructions=(metadata or {}).get("effective_mandatory_instructions"),
            effective_special_entity_types=(metadata or {}).get("effective_special_entity_types"),
            source_folder_id=(metadata or {}).get("source_folder_id"),
            requested_by_user_id=(metadata or {}).get("requested_by_user_id"),
            source_evidence_file_id=(metadata or {}).get("source_evidence_file_id"),
            file_size=file_size,
            mime_type=mime_type,
            sha256=sha256,
        )
        db.add(job)
        jobs.append(job)

    await db.commit()
    for job in jobs:
        await db.refresh(job)

    # Enqueue batch processor
    pool = request.app.state.arq_pool
    await pool.enqueue_job("process_batch", str(batch_id), case_id)

    return jobs
