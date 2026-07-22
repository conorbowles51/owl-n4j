import hashlib
import mimetypes
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models.job import Job
from app.schemas.job import JobResponse
from app.services.batch_dispatch import dispatch_ingestion_batch
from app.services.pipeline_run_state import transition_batch_dispatch

router = APIRouter()


def _safe_upload_name(file_name: str) -> str:
    candidate = str(file_name or "")
    if (
        not candidate
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or "\x00" in candidate
        or len(candidate) > 255
    ):
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    return candidate


def _storage_directory(storage_root: str, case_id: str, job_id: uuid.UUID) -> Path:
    try:
        canonical_case_id = str(uuid.UUID(case_id))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(status_code=400, detail="case_id must be a UUID") from exc

    root = Path(storage_root).resolve()
    target = (root / canonical_case_id / str(job_id)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload storage path") from exc
    return target


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
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(files) > settings.max_upload_batch_files:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"A batch may contain at most {settings.max_upload_batch_files} files",
        )

    batch_id = uuid.uuid4()
    jobs: list[Job] = []
    created_files: list[Path] = []
    created_directories: list[Path] = []
    batch_size = 0
    import json as _json

    parsed_processing_metadata: list[dict] | None = None
    if processing_metadata:
        try:
            parsed_processing_metadata = _json.loads(processing_metadata)
            if not isinstance(parsed_processing_metadata, list):
                parsed_processing_metadata = None
        except (ValueError, TypeError):
            parsed_processing_metadata = None

    try:
        for index, file in enumerate(files):
            job_id = uuid.uuid4()
            safe_name = _safe_upload_name(file.filename or "")

            # Save file to disk: {storage_path}/{case_id}/{job_id}/{filename}
            dir_path = _storage_directory(settings.storage_path, case_id, job_id)
            dir_path.mkdir(parents=True, exist_ok=False)
            created_directories.append(dir_path)
            file_path = dir_path / safe_name
            created_files.append(file_path)

            hasher = hashlib.sha256()
            file_size = 0
            async with aiofiles.open(file_path, "wb") as output:
                while chunk := await file.read(max(1, settings.upload_read_chunk_bytes)):
                    file_size += len(chunk)
                    batch_size += len(chunk)
                    if file_size > settings.max_upload_file_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                f"{safe_name} exceeds the {settings.max_upload_file_bytes}-byte upload limit"
                            ),
                        )
                    if batch_size > settings.max_upload_batch_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=(
                                "The combined upload exceeds the configured "
                                f"{settings.max_upload_batch_bytes}-byte batch limit"
                            ),
                        )
                    hasher.update(chunk)
                    await output.write(chunk)

            mime_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
            sha256 = hasher.hexdigest()

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
            ingestion_request_id = str(
                (metadata or {}).get("ingestion_request_id") or ""
            ).strip()
            job = Job(
                id=job_id,
                case_id=case_id,
                batch_id=batch_id,
                file_name=safe_name,
                file_path=str(file_path),
                llm_profile=llm_profile,
                folder_context=folder_context,
                sibling_files=parsed_siblings,
                effective_context=(metadata or {}).get("effective_context"),
                effective_mandatory_instructions=(metadata or {}).get("effective_mandatory_instructions"),
                effective_special_entity_types=(metadata or {}).get("effective_special_entity_types"),
                source_folder_id=(metadata or {}).get("source_folder_id"),
                requested_by_user_id=(metadata or {}).get("requested_by_user_id"),
                source_evidence_file_id=(metadata or {}).get("source_evidence_file_id"),
                pipeline_state=(
                    {"ingestion_request_id": ingestion_request_id}
                    if ingestion_request_id
                    else {}
                ),
                file_size=file_size,
                mime_type=mime_type,
                sha256=sha256,
            )
            db.add(job)
            jobs.append(job)
        jobs[0].pipeline_state = transition_batch_dispatch(
            jobs[0].pipeline_state,
            dispatch_state="ready",
            batch_id=str(batch_id),
            case_id=case_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        for created_file in reversed(created_files):
            try:
                if created_file.exists():
                    created_file.unlink()
            except OSError:
                pass
        for created_directory in reversed(created_directories):
            try:
                created_directory.rmdir()
            except OSError:
                pass
        raise

    for job in jobs:
        await db.refresh(job)

    # Dispatch through a durable job-embedded outbox. A temporary Redis failure
    # does not invalidate an accepted upload; the worker recovery cron retries it.
    pool = request.app.state.arq_pool
    await dispatch_ingestion_batch(jobs[0], db, pool)

    return jobs
