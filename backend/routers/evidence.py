"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
File storage and AI processing are delegated to the evidence engine when enabled.
"""

import asyncio
import logging
import mimetypes
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from services.evidence_service import evidence_service
from services.evidence_storage import evidence_storage, EVIDENCE_ROOT_DIR
from services.evidence_log_storage import evidence_log_storage
from services.wiretap_tracking import list_processed_wiretaps, is_wiretap_processed, mark_wiretap_processed
from services.wiretap_service import check_wiretap_suitable, process_wiretap_folder_async
from services.background_task_storage import background_task_storage, TaskStatus
from services.neo4j_service import neo4j_service
from services.case_storage import case_storage
from services.cypher_generator import generate_cypher_from_graph
from services import evidence_engine_client
from .auth import get_current_user
from routers.users import get_current_db_user
from fastapi import Query, status
from postgres.session import get_db
from postgres.models.user import User
from sqlalchemy.orm import Session
from config import BASE_DIR, USE_EVIDENCE_ENGINE
from datetime import datetime

logger = logging.getLogger(__name__)


# Hard limit on file IDs per single processing request.
# Clients must split larger batches into chunks of this size.
MAX_BATCH_SIZE = 50

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceRecord(BaseModel):
    id: str
    case_id: str
    original_filename: str
    stored_path: str = ""
    size: int
    sha256: str
    status: str
    duplicate_of: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    last_error: Optional[str] = None
    summary: Optional[str] = None  # Document summary if available
    entity_count: Optional[int] = None
    relationship_count: Optional[int] = None
    engine_job_id: Optional[str] = None  # Evidence engine job ID for progress tracking


class EvidenceListResponse(BaseModel):
    files: List[EvidenceRecord]


class UploadResponse(BaseModel):
    """Response for file uploads - can be synchronous or background."""
    files: Optional[List[EvidenceRecord]] = None  # For synchronous uploads
    task_id: Optional[str] = None  # Single task ID (for backwards compatibility)
    task_ids: Optional[List[str]] = None  # Multiple task IDs (for folder uploads)
    job_ids: Optional[List[str]] = None  # Evidence engine job IDs (for WebSocket progress)
    message: Optional[str] = None  # Status message


class ProcessRequest(BaseModel):
    case_id: Optional[str] = None
    file_ids: List[str]
    profile: Optional[str] = None  # LLM profile name (e.g., "fraud", "generic")
    max_workers: Optional[int] = None  # Maximum parallel files to process
    image_provider: Optional[str] = None  # "tesseract" (local OCR) or "openai" (GPT-4 Vision)


class ProcessResponse(BaseModel):
    processed: int
    skipped: int
    errors: int
    # Case version info may be present when case_id is provided
    case_id: Optional[str] = None
    case_version: Optional[int] = None
    case_timestamp: Optional[str] = None


class EvidenceLog(BaseModel):
    id: str
    case_id: Optional[str] = None
    evidence_id: Optional[str] = None
    filename: Optional[str] = None
    level: str
    message: str
    timestamp: str
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None


class EvidenceLogListResponse(BaseModel):
    logs: List[EvidenceLog]


@router.get("", response_model=EvidenceListResponse)
async def list_evidence(
    case_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List evidence files.

    Args:
        case_id: Optional case ID to filter by.
        status_filter: Optional status filter
            ('unprocessed', 'processing', 'processed', 'duplicate', 'failed').
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        if not case_id:
            return {"files": []}
        db_files = EvidenceDBStorage.list_files(db, case_id=UUID(case_id), status=status_filter)
        files = []
        for f in db_files:
            files.append({
                "id": str(f.id),
                "case_id": str(f.case_id),
                "original_filename": f.original_filename,
                "stored_path": f.stored_path or "",
                "size": f.size,
                "sha256": f.sha256,
                "status": f.status,
                "duplicate_of": str(f.duplicate_of_id) if f.duplicate_of_id else None,
                "created_at": f.created_at.isoformat() if f.created_at else "",
                "processed_at": f.processed_at.isoformat() if f.processed_at else None,
                "last_error": f.last_error,
                "engine_job_id": f.engine_job_id,
                "summary": f.summary,
                "entity_count": f.entity_count,
                "relationship_count": f.relationship_count,
            })

        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/sync-filesystem")
async def sync_filesystem(
    case_id: str = Query(..., description="Case ID to sync"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Sync the filesystem with evidence records.

    Scans the case's data directory for files that don't have corresponding
    evidence records and creates 'unprocessed' records for them.
    This handles cases where files exist on disk but weren't properly registered.
    """
    import hashlib
    import logging

    logger = logging.getLogger(__name__)

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_dir = EVIDENCE_ROOT_DIR / case_id
        if not case_dir.exists() or not case_dir.is_dir():
            return {"created": 0, "message": "Case directory does not exist"}

        from services.evidence_db_storage import EvidenceDBStorage

        # Get existing evidence records for this case from Postgres
        db_files = EvidenceDBStorage.list_files(db, case_id=UUID(case_id))

        # Build a set of known stored paths
        known_stored_paths = set()
        for rec in db_files:
            sp = rec.stored_path or ""
            if sp:
                known_stored_paths.add(sp)
                try:
                    known_stored_paths.add(str(Path(sp).resolve()))
                except Exception:
                    pass

        # Walk the case directory for files without evidence records
        created_count = 0
        file_infos = []
        for file_path in case_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith('.'):
                continue

            abs_path_str = str(file_path)
            resolved_str = str(file_path.resolve())

            if abs_path_str in known_stored_paths or resolved_str in known_stored_paths:
                continue

            # Read file content for hash computation
            try:
                content = file_path.read_bytes()
            except (OSError, PermissionError) as e:
                logger.warning(f"Cannot read file {file_path}: {e}")
                continue

            import hashlib
            sha256 = hashlib.sha256(content).hexdigest()

            file_infos.append({
                "original_filename": file_path.name,
                "stored_path": str(file_path),
                "sha256": sha256,
                "size": len(content),
            })

        if file_infos:
            new_records = EvidenceDBStorage.add_files(
                db, case_id=UUID(case_id),
                files_data=file_infos, owner=current_user.email,
            )
            db.commit()
            created_count = len(new_records)
            logger.info(f"Filesystem sync: created {created_count} evidence records for case {case_id}")

        return {"created": created_count, "message": f"Synced {created_count} file(s)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/duplicates/{sha256}", response_model=EvidenceListResponse)
async def find_duplicates(
    sha256: str,
    user: dict = Depends(get_current_user),
):
    """
    Find all files with the same SHA256 hash (duplicates).
    """
    try:
        files = evidence_service.find_duplicates(sha256)
        # Filter by owner to only show user's files
        files = [f for f in files if f.get("owner") == user["username"]]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=UploadResponse)
async def upload_evidence(
    case_id: str = Form(..., description="Associated case ID"),
    files: List[UploadFile] = File(..., description="Evidence files to upload"),
    is_folder: Optional[str] = Form(None, description="Whether this is a folder upload"),
    folder_id: Optional[str] = Form(None, description="Target folder ID for file placement"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Upload one or more evidence files for a case.

    When the evidence engine is enabled, files are forwarded to it for storage
    and automatic AI processing. Otherwise, files are stored locally and must
    be processed separately.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # --- Evidence Engine path: forward files for storage + auto-processing ---
        if USE_EVIDENCE_ENGINE:
            return await _upload_via_engine(
                case_id, files, current_user.email,
                folder_id=folder_id, db=db,
            )

        # --- Legacy path (deprecated): store locally, process separately ---
        logger.warning("USE_EVIDENCE_ENGINE=false: using deprecated legacy upload path")
        # Check if this is a folder upload or should be background task
        is_folder_upload = is_folder and is_folder.lower() == 'true'
        use_background = is_folder_upload or len(files) > 5

        if use_background:
            uploads = []
            for index, uf in enumerate(files):
                content = await uf.read()
                filename = uf.filename or ""

                relative_path = None
                if '/' in filename or '\\' in filename:
                    relative_path = filename.replace('\\', '/')
                    path_parts = relative_path.split('/')
                    original_filename = path_parts[-1] if path_parts else filename
                else:
                    original_filename = filename

                uploads.append(
                    {
                        "original_filename": original_filename,
                        "content": content,
                        "relative_path": relative_path,
                    }
                )

            if is_folder_upload:
                task_ids = evidence_service.upload_folders_background(
                    case_id=case_id,
                    files=uploads,
                    owner=current_user.email,
                )
                return UploadResponse(
                    task_id=task_ids[0] if task_ids else None,
                    task_ids=task_ids,
                    message=f"Uploading {len(task_ids)} folder(s) in background" if task_ids else "No folders to upload",
                )
            else:
                task_id = evidence_service.upload_files_background(
                    case_id=case_id,
                    files=uploads,
                    owner=current_user.email,
                )
                return UploadResponse(
                    task_id=task_id,
                    message=f"Uploading {len(files)} file(s) in background",
                )
        else:
            uploads = []
            for uf in files:
                content = await uf.read()
                uploads.append(
                    {
                        "original_filename": uf.filename,
                        "content": content,
                    }
                )

            records = evidence_service.add_uploaded_files(
                case_id=case_id,
                uploads=uploads,
                owner=current_user.email,
            )
            return UploadResponse(files=records)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _upload_via_engine(
    case_id: str,
    files: List[UploadFile],
    owner: str,
    folder_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> UploadResponse:
    """
    Store files locally and send to the evidence engine for processing.

    The backend owns file storage (disk + Postgres). The evidence engine is
    a processing pipeline: it receives file contents, extracts entities and
    relationships, and writes them to Neo4j/ChromaDB.

    When folder_id is provided, resolves the effective profile for that folder
    and passes folder context + sibling file info to the engine for prompt enrichment.
    """
    import hashlib
    import json as _json
    import uuid as _uuid
    from services.folder_context_service import resolve_effective_profile, gather_sibling_files
    from services.evidence_db_storage import EvidenceDBStorage

    fid_uuid = _uuid.UUID(folder_id) if folder_id else None
    case_uuid = _uuid.UUID(case_id)

    # --- Step 1: Read file contents and store to backend disk ---
    case_dir = EVIDENCE_ROOT_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    file_tuples = []  # (filename, content, content_type) for engine
    db_files_data = []  # For Postgres record creation

    for uf in files:
        content = await uf.read()
        filename = uf.filename or "unknown"
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        # Store file to backend disk
        stored_path = case_dir / filename
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(content)

        # Compute metadata locally
        sha256 = hashlib.sha256(content).hexdigest()

        file_tuples.append((filename, content, content_type))
        db_files_data.append({
            "original_filename": filename,
            "stored_path": str(stored_path),
            "sha256": sha256,
            "size": len(content),
        })

    # --- Step 2: Create EvidenceFile records in Postgres ---
    db_records = []
    if db and db_files_data:
        db_records = EvidenceDBStorage.add_files(
            db,
            case_id=case_uuid,
            files_data=db_files_data,
            owner=owner,
            folder_id=fid_uuid,
        )
        for db_rec in db_records:
            db_rec.status = "processing"
        db.flush()

    # --- Step 3: Resolve folder context for engine prompt enrichment ---
    folder_context: Optional[str] = None
    sibling_files_json: Optional[str] = None
    llm_profile: Optional[str] = None

    if fid_uuid and db:
        effective = resolve_effective_profile(db, fid_uuid, case_uuid)
        if effective["merged_context"]:
            folder_context = effective["merged_context"]
        if effective["merged_overrides"].get("llm_profile"):
            llm_profile = effective["merged_overrides"]["llm_profile"]
        siblings = gather_sibling_files(db, fid_uuid)
        if siblings:
            sibling_files_json = _json.dumps(siblings)

    # --- Step 4: Send files to evidence engine for processing ---
    jobs = await evidence_engine_client.upload_files_batch(
        case_id=case_id,
        files=file_tuples,
        llm_profile=llm_profile,
        folder_context=folder_context,
        sibling_files=sibling_files_json,
    )

    # --- Step 5: Link engine job IDs back to our Postgres records ---
    job_ids = []
    for db_rec, job in zip(db_records, jobs):
        db_rec.engine_job_id = str(job["id"])
        job_ids.append(str(job["id"]))

    if db:
        db.commit()

    # Build response records (matching UploadResponse.files shape)
    records = []
    for db_rec, fd in zip(db_records, db_files_data):
        records.append({
            "id": str(db_rec.id),
            "case_id": case_id,
            "original_filename": fd["original_filename"],
            "stored_path": fd["stored_path"],
            "sha256": fd["sha256"],
            "size": fd["size"],
            "status": "processing",
            "engine_job_id": db_rec.engine_job_id,
            "created_at": datetime.now().isoformat(),
        })

    # Register jobs with the Redis subscriber for status tracking
    if job_ids:
        from services.job_status_subscriber import get_subscriber
        try:
            subscriber = get_subscriber()
            await subscriber.track_jobs(job_ids, case_id)
        except Exception as e:
            logger.warning("Failed to register jobs with subscriber: %s", e)

    return UploadResponse(
        files=records,
        job_ids=job_ids if job_ids else None,
        message=f"Processing {len(records)} file(s)" if job_ids else None,
    )


@router.post("/process/background")
async def process_evidence_background(
    request: ProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process selected evidence files in the background.

    For engine-managed files, processing is automatic (started on upload).
    This endpoint returns job status for those files.
    For legacy files, starts background processing via the ingestion pipeline.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    if len(request.file_ids) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(request.file_ids)}). Maximum {MAX_BATCH_SIZE} files per request. Please batch your requests.",
        )

    try:
        if request.case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # Separate engine-managed files from legacy files
        engine_ids, legacy_ids = _split_engine_legacy(request.file_ids, db)

        if engine_ids and not legacy_ids:
            # All engine-managed — processing is automatic, return status
            return {
                "task_id": None,
                "message": f"{len(engine_ids)} file(s) are already being processed by the evidence engine",
            }

        if legacy_ids:
            # Process legacy files via the old pipeline
            task_id = evidence_service.process_files_background(
                evidence_ids=legacy_ids,
                case_id=request.case_id,
                owner=current_user.email,
                profile=request.profile,
                max_workers=request.max_workers,
                image_provider=request.image_provider,
            )
            msg = f"Processing {len(legacy_ids)} legacy file(s) in background"
            if engine_ids:
                msg += f"; {len(engine_ids)} file(s) already processing via evidence engine"
            return {"task_id": task_id, "message": msg}

        return {"task_id": None, "message": "No files to process"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=ProcessResponse)
async def process_evidence(
    request: ProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process selected evidence files synchronously.

    For engine-managed files, processing is automatic. This returns their
    current status counts. Legacy files are processed via the ingestion pipeline.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    try:
        if request.case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        engine_ids, legacy_ids = _split_engine_legacy(request.file_ids, db)

        processed = len(engine_ids)  # engine files are already processing/processed
        skipped = 0
        errors = 0

        if legacy_ids:
            summary = await run_in_threadpool(
                evidence_service.process_files,
                legacy_ids,
                request.case_id,
                current_user.email,
                request.profile,
            )
            processed += summary.get("processed", 0)
            skipped += summary.get("skipped", 0)
            errors += summary.get("errors", 0)

        return ProcessResponse(processed=processed, skipped=skipped, errors=errors)
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion pipeline not available: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _split_engine_legacy(file_ids: List[str], db: Session) -> tuple:
    """Split file IDs into engine-managed and legacy lists."""
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    engine_ids = []
    legacy_ids = []
    for fid in file_ids:
        rec = None
        try:
            rec = EvidenceDBStorage.get(db, UUID(fid))
        except (ValueError, AttributeError):
            rec = EvidenceDBStorage.get_by_legacy_id(db, fid)
        if rec and rec.engine_job_id:
            engine_ids.append(fid)
        else:
            legacy_ids.append(fid)
    return engine_ids, legacy_ids


@router.get("/logs", response_model=EvidenceLogListResponse)
async def get_evidence_logs(
    case_id: Optional[str] = None,
    limit: int = 200,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Get recent evidence ingestion logs, optionally filtered by case_id.
    """
    try:
        if case_id:
            from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
            from uuid import UUID
            try:
                check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
            except (CaseNotFound, CaseAccessDenied) as e:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        from services.evidence_db_storage import EvidenceDBStorage
        from uuid import UUID
        case_uuid = UUID(case_id) if case_id else None
        db_logs = EvidenceDBStorage.list_logs(db, case_id=case_uuid, limit=limit)
        logs = []
        for log in db_logs:
            logs.append({
                "id": str(log.id),
                "case_id": str(log.case_id) if log.case_id else None,
                "evidence_id": str(log.evidence_file_id) if log.evidence_file_id else None,
                "filename": log.filename,
                "level": log.level,
                "message": log.message,
                "timestamp": log.created_at.isoformat() if log.created_at else "",
            })
        return {"logs": logs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/engine/jobs")
async def list_engine_jobs(
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Proxy: list all processing jobs from the evidence engine for a case."""
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        if not USE_EVIDENCE_ENGINE:
            return []

        jobs = await evidence_engine_client.list_jobs(case_id)
        return jobs
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to list engine jobs: %s", e)
        return []


@router.get("/engine/jobs/{job_id}")
async def get_engine_job(
    job_id: str,
    current_user: User = Depends(get_current_db_user),
):
    """Proxy: get status of a single processing job from the evidence engine."""
    try:
        if not USE_EVIDENCE_ENGINE:
            raise HTTPException(status_code=404, detail="Evidence engine not enabled")

        job = await evidence_engine_client.get_job(job_id)
        return job
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wiretap/check")
async def check_wiretap_folder(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Check if a folder is suitable for wiretap processing.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # Build full path to folder
        case_data_dir = BASE_DIR / "ingestion" / "data" / case_id
        full_folder_path = case_data_dir / folder_path
        
        # Security check: ensure path is within case directory
        try:
            full_folder_path.resolve().relative_to(case_data_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")
        
        # Check suitability
        result = check_wiretap_suitable(full_folder_path)
        
        # Check if folder has been processed as wiretap
        result["processed"] = is_wiretap_processed(case_id, folder_path)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class WiretapProcessRequest(BaseModel):
    """Request to process wiretap folders."""
    case_id: str
    folder_paths: List[str]  # List of folder paths relative to case data directory
    whisper_model: str = "base"  # Whisper model size


class WiretapProcessResponse(BaseModel):
    """Response from wiretap processing."""
    success: bool
    message: str
    task_id: Optional[str] = None  # First task ID for backwards compatibility


@router.post("/wiretap/process", response_model=WiretapProcessResponse)
async def process_wiretap_folders(
    request: WiretapProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process one or more wiretap folders.

    Creates a separate background task for each folder. Each folder is processed independently.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / request.case_id

        # Do minimal validation (just path format check) - full validation happens in background
        # This allows the endpoint to return quickly
        validated_paths = []
        for folder_path in request.folder_paths:
            # Basic path sanitization check
            if not folder_path or not isinstance(folder_path, str):
                raise HTTPException(status_code=400, detail=f"Invalid folder path: {folder_path}")
            # Check for path traversal attempts
            if ".." in folder_path or folder_path.startswith("/"):
                raise HTTPException(status_code=403, detail=f"Path outside case directory: {folder_path}")
            validated_paths.append(folder_path)

        # Always use background processing for wiretap folders
        # Create a separate background task for each folder
        task_ids = []

        # Capture email outside the closure for use in background tasks
        user_email = current_user.email

        for folder_path in validated_paths:
            # Create a background task for this folder
            task = background_task_storage.create_task(
                task_type="wiretap_processing",
                task_name=f"Process wiretap folder: {folder_path.split('/')[-1] or folder_path}",
                case_id=request.case_id,
                owner=user_email,
                metadata={
                    "folder_path": folder_path,  # Single folder path for this task
                    "whisper_model": request.whisper_model,
                }
            )
            task_id = task["id"]
            task_ids.append(task_id)
            
            def create_background_task(fp, tid):
                """Create a background task function with proper closure."""
                async def process_single_wiretap_folder_background():
                    """Background task function to process a single wiretap folder."""
                    from services.evidence_log_storage import evidence_log_storage
                    
                    # Full validation happens here in the background
                    full_path = case_data_dir / fp
                    try:
                        # Resolve and check it's within case directory
                        resolved = full_path.resolve()
                        case_resolved = case_data_dir.resolve()
                        resolved.relative_to(case_resolved)
                    except (ValueError, OSError) as e:
                        evidence_log_storage.add_log(
                            case_id=request.case_id,
                            evidence_id=None,
                            filename=None,
                            level="error",
                            message=f"Invalid folder path: {fp} - {str(e)}"
                        )
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error=f"Invalid path: {str(e)}",
                            completed_at=datetime.now().isoformat()
                        )
                        return
                    
                    if not full_path.exists():
                        evidence_log_storage.add_log(
                            case_id=request.case_id,
                            evidence_id=None,
                            filename=None,
                            level="error",
                            message=f"Folder not found: {fp}"
                        )
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error="Folder not found",
                            completed_at=datetime.now().isoformat()
                        )
                        return
                    
                    if not full_path.is_dir():
                        evidence_log_storage.add_log(
                            case_id=request.case_id,
                            evidence_id=None,
                            filename=None,
                            level="error",
                            message=f"Path is not a directory: {fp}"
                        )
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error="Not a directory",
                            completed_at=datetime.now().isoformat()
                        )
                        return
                    
                    # Update task status to running
                    background_task_storage.update_task(
                        tid,
                        status=TaskStatus.RUNNING.value,
                        started_at=datetime.now().isoformat(),
                        progress_total=1
                    )
                    
                    try:
                        def log_callback(message: str):
                            evidence_log_storage.add_log(
                                case_id=request.case_id,
                                evidence_id=None,
                                filename=None,
                                level="info",
                                message=f"[{full_path.name}] {message}"
                            )
                        
                        # Use async version to avoid blocking the event loop
                        result = await process_wiretap_folder_async(
                            full_path,
                            request.case_id,
                            request.whisper_model,
                            log_callback
                        )
                        
                        if result["success"]:
                            # Mark folder as processed
                            mark_wiretap_processed(
                                request.case_id,
                                fp
                            )
                            
                            background_task_storage.update_task(
                                tid,
                                progress_completed=1,
                                status=TaskStatus.COMPLETED.value,
                                completed_at=datetime.now().isoformat()
                            )
                            
                            # Save case version after successful processing
                            try:
                                # Look up case name (fallback to case_id if not found)
                                case = case_storage.get_case(request.case_id)
                                case_name = case["name"] if case and case.get("name") else request.case_id
                                
                                # Save as a new version on this case
                                # Note: Cypher queries are no longer stored - graph data persists in Neo4j
                                case_result = case_storage.save_case_version(
                                    case_id=request.case_id,
                                    case_name=case_name,
                                    snapshots=[],
                                    save_notes=f"Auto-save after processing wiretap folder: {fp}",
                                    owner=user_email,
                                )
                                
                                evidence_log_storage.add_log(
                                    case_id=request.case_id,
                                    evidence_id=None,
                                    filename=None,
                                    level="info",
                                    message=(
                                        "Saved new case version after wiretap processing: "
                                        f"case_id={case_result.get('case_id')}, "
                                        f"version={case_result.get('version')}."
                                    ),
                                )
                            except Exception as e:
                                # Do not fail wiretap processing if case saving fails; just log
                                print(f"Warning: failed to attach graph Cypher to case {request.case_id}: {e}")
                                evidence_log_storage.add_log(
                                    case_id=request.case_id,
                                    evidence_id=None,
                                    filename=None,
                                    level="error",
                                    message=f"Failed to save case version after wiretap processing: {e}",
                                )
                        else:
                            # Include output in error message for debugging
                            error_msg = result.get("error", "Unknown error")
                            output = result.get("output", "")
                            if output:
                                # Append last few lines of output to error for context
                                output_lines = output.split('\n')
                                last_lines = '\n'.join(output_lines[-10:])  # Last 10 lines
                                error_msg = f"{error_msg}\n\nScript output:\n{last_lines}"
                            
                            # Log the full error to evidence logs
                            evidence_log_storage.add_log(
                                case_id=request.case_id,
                                evidence_id=None,
                                filename=None,
                                level="error",
                                message=f"Wiretap processing failed: {error_msg}"
                            )
                            
                            background_task_storage.update_task(
                                tid,
                                status=TaskStatus.FAILED.value,
                                error=error_msg,
                                completed_at=datetime.now().isoformat()
                            )
                    except Exception as e:
                        background_task_storage.update_task(
                            tid,
                            status=TaskStatus.FAILED.value,
                            error=str(e),
                            completed_at=datetime.now().isoformat()
                        )
                
                return process_single_wiretap_folder_background
            
            # Schedule the background task for this folder with proper closure
            background_tasks.add_task(create_background_task(folder_path, task_id))
        
        # Return first task ID for backwards compatibility
        return WiretapProcessResponse(
            success=True,
            message=f"Processing {len(validated_paths)} wiretap folder(s) in background ({len(task_ids)} task(s) created)",
            task_id=task_ids[0] if task_ids else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{evidence_id}")
async def delete_evidence_file(
    evidence_id: str,
    case_id: str = Query(..., description="Case ID for scoping"),
    delete_exclusive_entities: bool = Query(True, description="Also delete entities only mentioned in this file"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Delete an evidence file and optionally its exclusive entities.

    This will:
    1. Remove the evidence record from storage
    2. Delete the physical file from disk
    3. Delete the Document node from Neo4j
    4. If delete_exclusive_entities=True, delete entities that are ONLY
       mentioned in this document (not shared with other documents)
    5. Clean up related embeddings from ChromaDB
    6. Exclusive entities are soft-deleted to the recycling bin
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        # 1. Get the evidence record from Postgres
        from services.evidence_db_storage import EvidenceDBStorage
        from uuid import UUID

        db_record = None
        try:
            db_record = EvidenceDBStorage.get(db, UUID(evidence_id))
        except (ValueError, AttributeError):
            db_record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)

        # Fallback to legacy JSON storage during migration
        legacy_record = None
        if not db_record:
            legacy_record = evidence_storage.get(evidence_id)
            if not legacy_record:
                raise HTTPException(status_code=404, detail="Evidence file not found")
            if legacy_record.get("case_id") != case_id:
                raise HTTPException(status_code=403, detail="Evidence file does not belong to this case")
        elif str(db_record.case_id) != case_id:
            raise HTTPException(status_code=403, detail="Evidence file does not belong to this case")

        # Check if file is currently being processed
        record = db_record or legacy_record
        if db_record and db_record.status == "processing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete file while it is being processed. Wait for processing to complete."
            )

        filename = db_record.original_filename if db_record else legacy_record.get("original_filename", "")
        stored_path = db_record.stored_path if db_record else legacy_record.get("stored_path")
        engine_job_id = db_record.engine_job_id if db_record else legacy_record.get("engine_job_id")
        result_info = {
            "evidence_id": evidence_id,
            "filename": filename,
            "file_deleted": False,
            "document_deleted": False,
            "exclusive_entities_recycled": [],
            "shared_entities_unlinked": [],
            "chromadb_cleaned": False,
        }

        # 2. Delete from Neo4j (Document node + exclusive entities)
        try:
            doc_node = neo4j_service.find_document_node(filename, case_id)
            if doc_node:
                doc_key = doc_node["key"]

                if delete_exclusive_entities:
                    # Find exclusive entities BEFORE deleting doc, then soft-delete them
                    exclusive = neo4j_service.find_exclusive_entities(doc_key, case_id)

                    # Soft-delete exclusive entities to recycling bin first
                    for entity in exclusive:
                        try:
                            neo4j_service.soft_delete_entity(
                                node_key=entity["key"],
                                case_id=case_id,
                                deleted_by=current_user.email,
                                reason=f"file_delete:{filename}",
                            )
                            result_info["exclusive_entities_recycled"].append(entity)
                        except Exception as e:
                            logger.warning(f"Failed to recycle entity {entity['key']}: {e}")

                # Find shared entities (for response info) before deleting doc
                try:
                    shared = neo4j_service.find_document_node(doc_key, case_id)  # just to verify
                except Exception:
                    pass

                # Remove MENTIONED_IN relationships from remaining entities
                # and delete the Document node itself
                neo4j_service.delete_node(doc_key, case_id=case_id)
                result_info["document_deleted"] = True

                # 3. Clean up ChromaDB embeddings
                try:
                    from services.vector_db_service import get_vector_db_service
                    vector_db = get_vector_db_service()
                    if vector_db:
                        # Delete all chunk embeddings for this document
                        vector_db.delete_chunks_by_doc(doc_key)
                        # Delete exclusive entity embeddings
                        for entity in result_info["exclusive_entities_recycled"]:
                            vector_db.delete_entity(entity["key"])
                        result_info["chromadb_cleaned"] = True
                except Exception as e:
                    logger.warning(f"ChromaDB cleanup error: {e}")
            else:
                logger.info(f"No Document node found in Neo4j for {filename}")
        except ValueError as e:
            logger.info(f"Neo4j document deletion: {e}")
        except Exception as e:
            logger.warning(f"Neo4j cleanup error: {e}")

        # 4. Delete physical file from backend disk
        if stored_path:
            file_path = Path(stored_path)
            if file_path.exists():
                try:
                    file_path.unlink()
                    result_info["file_deleted"] = True
                except Exception as e:
                    logger.warning("Failed to delete physical file: %s", e)

        # 5. Tell evidence engine to clean up its processing copy
        if engine_job_id:
            try:
                await evidence_engine_client.delete_file(case_id, engine_job_id)
            except Exception as e:
                logger.warning("Failed to delete file from evidence engine: %s", e)

        # 6. Delete evidence record from Postgres
        if db_record:
            EvidenceDBStorage.delete_record(db, db_record.id)
            db.commit()

        # Legacy cleanup (remove once JSON storage is fully deprecated)
        if legacy_record:
            evidence_storage.delete_record(evidence_id)

        return result_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evidence_id}/file")
async def get_evidence_file(
    evidence_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Serve the actual file content for a given evidence ID.

    All files are served from the backend's local disk (EVIDENCE_ROOT_DIR).
    """
    from services.evidence_db_storage import EvidenceDBStorage

    try:
        # Look up by UUID or legacy ID
        record = None
        try:
            from uuid import UUID
            record = EvidenceDBStorage.get(db, UUID(evidence_id))
        except (ValueError, AttributeError):
            record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)

        if not record:
            # Fallback to legacy JSON storage during migration
            legacy_rec = evidence_storage.get(evidence_id)
            if not legacy_rec:
                raise HTTPException(status_code=404, detail="Evidence not found")
            # Serve legacy file via old path
            stored_path = legacy_rec.get("stored_path", "")
            filename = legacy_rec.get("original_filename", "file")
            if not stored_path or not Path(stored_path).exists():
                # Try engine proxy as last resort for old engine-managed files
                engine_job_id = legacy_rec.get("engine_job_id")
                if engine_job_id:
                    resp = await evidence_engine_client.download_file(
                        legacy_rec.get("case_id", ""), engine_job_id
                    )
                    media_type = resp.headers.get("content-type", "application/octet-stream")
                    return Response(
                        content=resp.content,
                        media_type=media_type,
                        headers={"Content-Disposition": f'inline; filename="{filename}"'},
                    )
                raise HTTPException(status_code=404, detail="File not found on disk")
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            return FileResponse(
                path=stored_path, filename=filename, media_type=content_type,
                headers={"Content-Disposition": f'inline; filename="{filename}"'},
            )

        # Primary path: serve from backend disk
        filename = record.original_filename or "file"
        stored_path = record.stored_path

        if not stored_path or not Path(stored_path).exists():
            raise HTTPException(status_code=404, detail="File not found on disk")

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            path=stored_path,
            filename=filename,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


FRAMES_CACHE_DIR = BASE_DIR / "data" / "video_frames"


def _extract_video_frames(video_path: Path, output_dir: Path, interval: int = 30, max_frames: int = 50) -> List[dict]:
    """Extract key frames from a video file using ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_cmd = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe_cmd = shutil.which("ffprobe") or "ffprobe"

    # Get duration
    duration = 0.0
    try:
        probe = subprocess.run(
            [ffprobe_cmd, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(probe.stdout.strip() or 0)
    except Exception:
        pass

    if duration > 0 and interval > duration:
        interval = max(1, int(duration / 5))

    try:
        subprocess.run(
            [ffmpeg_cmd, "-i", str(video_path), "-vf", f"fps=1/{interval}",
             "-frames:v", str(max_frames), "-q:v", "2", "-y",
             str(output_dir / "frame_%04d.jpg")],
            capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg not found. Install ffmpeg to extract video frames.")

    frames = []
    for idx, fp in enumerate(sorted(output_dir.glob("frame_*.jpg"))):
        ts = idx * interval
        mins, secs = divmod(ts, 60)
        hrs, mins = divmod(mins, 60)
        frames.append({
            "frame_number": idx + 1,
            "timestamp_seconds": ts,
            "timestamp_str": f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}",
            "filename": fp.name,
        })
    return frames


@router.get("/{evidence_id}/frames")
async def get_video_frames(
    evidence_id: str,
    interval: int = Query(30, description="Seconds between frame captures"),
    max_frames: int = Query(50, description="Maximum number of frames"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Extract and return key frames from a video evidence file.
    Frames are cached so subsequent requests are instant.
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    record = None
    try:
        record = EvidenceDBStorage.get(db, UUID(evidence_id))
    except (ValueError, AttributeError):
        record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)
    if not record:
        raise HTTPException(status_code=404, detail="Evidence not found")

    stored_path = record.stored_path
    if not stored_path:
        raise HTTPException(status_code=404, detail="File path not found")

    video_path = Path(stored_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found on disk")

    video_exts = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".flv", ".wmv"}
    if video_path.suffix.lower() not in video_exts:
        raise HTTPException(status_code=400, detail="File is not a video")

    cache_dir = FRAMES_CACHE_DIR / evidence_id
    frames_meta = []

    if cache_dir.exists() and any(cache_dir.glob("frame_*.jpg")):
        for idx, fp in enumerate(sorted(cache_dir.glob("frame_*.jpg"))):
            ts = idx * interval
            mins, secs = divmod(ts, 60)
            hrs, mins = divmod(mins, 60)
            frames_meta.append({
                "frame_number": idx + 1,
                "timestamp_seconds": ts,
                "timestamp_str": f"{hrs:02d}:{mins:02d}:{secs:02d}" if hrs else f"{mins:02d}:{secs:02d}",
                "filename": fp.name,
            })
    else:
        frames_meta = await run_in_threadpool(
            _extract_video_frames, video_path, cache_dir, interval, max_frames
        )

    return {
        "evidence_id": evidence_id,
        "filename": record.original_filename or video_path.name,
        "frame_count": len(frames_meta),
        "frames": frames_meta,
    }


@router.get("/{evidence_id}/frames/{filename}")
async def get_video_frame_image(
    evidence_id: str,
    filename: str,
    user: dict = Depends(get_current_user),
):
    """Serve an individual extracted frame image."""
    if not filename.startswith("frame_") or not filename.endswith(".jpg"):
        raise HTTPException(status_code=400, detail="Invalid frame filename")

    frame_path = FRAMES_CACHE_DIR / evidence_id / filename
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="Frame not found. Extract frames first via GET /{evidence_id}/frames")

    return FileResponse(frame_path, media_type="image/jpeg")


class SetRelevanceRequest(BaseModel):
    evidence_ids: List[str]
    is_relevant: bool


@router.put("/relevance")
async def set_evidence_relevance(
    body: SetRelevanceRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark evidence files as relevant or non-relevant."""
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    if not body.evidence_ids:
        raise HTTPException(status_code=400, detail="No evidence IDs provided")
    file_uuids = []
    for eid in body.evidence_ids:
        try:
            file_uuids.append(UUID(eid))
        except ValueError:
            rec = EvidenceDBStorage.get_by_legacy_id(db, eid)
            if rec:
                file_uuids.append(rec.id)
    updated = EvidenceDBStorage.set_relevance(db, file_uuids, body.is_relevant)
    db.commit()
    return {"updated": updated, "is_relevant": body.is_relevant}


@router.put("/relevance/from-theory")
async def set_relevance_from_theory(
    case_id: str = Query(..., description="Case ID"),
    theory_id: str = Query(..., description="Theory ID"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark all evidence files linked to a theory as relevant.
    Collects IDs from attached_evidence_ids, attached_document_ids,
    and any evidence files referenced by graph nodes in the theory's snapshot.
    """
    from services.workspace_service import workspace_service
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    theory = workspace_service.get_theory(case_id, theory_id)
    if not theory:
        raise HTTPException(status_code=404, detail="Theory not found")

    evidence_ids = set()

    for field in ("attached_evidence_ids", "attached_document_ids"):
        for eid in (theory.get(field) or []):
            evidence_ids.add(eid)

    snapshot_id = theory.get("attached_snapshot_ids", [None])
    if snapshot_id and isinstance(snapshot_id, list):
        snapshot_id = snapshot_id[0] if snapshot_id else None
    if snapshot_id:
        try:
            from services.snapshot_storage import snapshot_storage
            snapshot = snapshot_storage.get(snapshot_id)
            if snapshot:
                nodes = snapshot.get("graph_data", {}).get("nodes", [])
                all_files = EvidenceDBStorage.list_files(db, case_id=UUID(case_id))
                filename_to_id = {
                    (f.original_filename or "").lower(): str(f.id) for f in all_files
                }
                for node in nodes:
                    for prop_key in ("source", "source_doc", "source_document", "file"):
                        val = node.get("properties", {}).get(prop_key)
                        if val and isinstance(val, str):
                            match = filename_to_id.get(val.lower())
                            if match:
                                evidence_ids.add(match)
        except Exception:
            pass

    updated = 0
    if evidence_ids:
        file_uuids = []
        for eid in evidence_ids:
            try:
                file_uuids.append(UUID(eid))
            except ValueError:
                rec = EvidenceDBStorage.get_by_legacy_id(db, eid)
                if rec:
                    file_uuids.append(rec.id)
        if file_uuids:
            updated = EvidenceDBStorage.set_relevance(db, file_uuids, True)
            db.commit()

    return {"updated": updated, "theory_id": theory_id, "evidence_ids_marked": list(evidence_ids)}


@router.get("/wiretap/processed")
async def list_wiretap_processed(
    case_id: Optional[str] = Query(None, description="Case ID to filter by (optional)"),
    user: dict = Depends(get_current_user),
):
    """
    List all successfully processed wiretap folders.
    
    Args:
        case_id: Optional case ID to filter by. If not provided, returns all processed wiretaps.
    
    Returns:
        List of processed wiretap folders with case_id, folder_path, and processed_at
    """
    try:
        return list_processed_wiretaps(case_id=case_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-filename/{filename}")
async def get_evidence_by_filename(
    filename: str,
    case_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Find evidence by original filename and return file info.

    This endpoint helps the frontend locate evidence IDs from document names
    stored in entity citations.
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        case_uuid = UUID(case_id) if case_id else None
        record = EvidenceDBStorage.find_by_filename(db, filename, case_id=case_uuid)
        if record:
            return {
                "found": True,
                "evidence_id": str(record.id),
                "case_id": str(record.case_id),
                "original_filename": record.original_filename,
                "stored_path": record.stored_path,
                "summary": record.summary,
            }

        return {"found": False, "message": f"No evidence file found with name: {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{filename}")
async def get_document_summary(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the AI-generated summary for a document.

    Returns the summary stored on the EvidenceFile record in Postgres.
    """
    from services.evidence_db_storage import EvidenceDBStorage
    from uuid import UUID

    try:
        case_uuid = UUID(case_id)
        record = EvidenceDBStorage.find_by_filename(db, filename, case_id=case_uuid)
        summary = record.summary if record else None
        return {
            "filename": filename,
            "case_id": case_id,
            "summary": summary,
            "has_summary": summary is not None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder-summary/{folder_name}")
async def get_folder_summary(
    folder_name: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get the AI-generated summary for a processed folder by folder name.
    
    Args:
        folder_name: Folder name (e.g., "00000128")
        case_id: Case ID to filter by
    
    Returns:
        Folder summary if found
    """
    try:
        summary = neo4j_service.get_folder_summary(folder_name, case_id)
        return {
            "folder_name": folder_name,
            "case_id": case_id,
            "summary": summary,
            "has_summary": summary is not None,
        }
    except HTTPException:
        raise


@router.get("/transcription-translation")
async def get_transcription_translation(
    case_id: str = Query(..., description="Case ID"),
    folder_name: str = Query(..., description="Wiretap folder name (e.g. 00000128)"),
    user: dict = Depends(get_current_user),
):
    """
    Get wiretap Spanish transcription and English translation for a folder, when available.
    """
    try:
        result = neo4j_service.get_transcription_translation(folder_name, case_id)
        return {
            "folder_name": folder_name,
            "case_id": case_id,
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Folder Profile Management Endpoints

class FolderFileInfo(BaseModel):
    name: str
    path: str
    type: str  # "file" or "directory"
    size: Optional[int] = None


class FolderFilesResponse(BaseModel):
    files: List[FolderFileInfo]
    folder_path: str


class FolderProfileGenerateRequest(BaseModel):
    folder_path: str
    case_id: str
    user_instructions: str
    file_list: List[FolderFileInfo]


class FolderProfileTestRequest(BaseModel):
    folder_path: str
    case_id: str
    profile_name: str


@router.get("/folder/files", response_model=FolderFilesResponse)
async def list_folder_files(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    List files in a folder for profile creation.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(case_id), current_user, required_permission=("case", "view"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / case_id
        if not case_data_dir.exists():
            raise HTTPException(status_code=404, detail="Case data directory not found")
        
        full_folder_path = (case_data_dir / folder_path).resolve()
        case_resolved = case_data_dir.resolve()
        
        try:
            full_folder_path.relative_to(case_resolved)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")
        
        if not full_folder_path.exists() or not full_folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")
        
        files = []
        for item_path in sorted(full_folder_path.iterdir()):
            if item_path.name.startswith('.'):
                continue
            
            relative_path = item_path.relative_to(full_folder_path)
            files.append(FolderFileInfo(
                name=item_path.name,
                path=str(relative_path),
                type="directory" if item_path.is_dir() else "file",
                size=item_path.stat().st_size if item_path.is_file() else None
            ))
        
        return FolderFilesResponse(files=files, folder_path=folder_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folder/profile/generate")
async def generate_folder_profile(
    request: FolderProfileGenerateRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Generate a folder processing profile from natural language instructions.
    Uses LLM to interpret user instructions and create a profile structure.
    """
    import json
    import logging

    logger = logging.getLogger(__name__)

    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        from services.llm_service import llm_service
        
        # Validate that we have files to work with
        if not request.file_list:
            raise HTTPException(status_code=400, detail="No files provided in file_list")
        
        # Validate user instructions
        if not request.user_instructions or not request.user_instructions.strip():
            raise HTTPException(status_code=400, detail="User instructions cannot be empty")
        
        logger.info(f"Generating folder profile for case {request.case_id}, folder {request.folder_path} with {len(request.file_list)} files")
        
        # Build prompt for LLM
        file_list_str = "\n".join([f"- {f.name} ({f.type})" for f in request.file_list])
        
        prompt = f"""You are helping a user configure a folder processing profile.

The user has uploaded a folder with these files:
{file_list_str}

The user wants this processing:
{request.user_instructions}

Generate a JSON profile structure that defines how to process this folder. The profile should include:
1. A "folder_processing" section with:
   - "type": "special" (to indicate files are related)
   - "file_rules": Array of rules, each with:
     - "pattern": File pattern (e.g., "*.wav,*.mp3" or "*.sri")
     - "role": Role of the file ("audio", "metadata", "interpretation", "document", "image", "video", etc.)
     - For audio: "actions": ["transcribe", "translate"], "transcribe_languages": [...], "translate_languages": [...], "whisper_model": "base"
     - For metadata: "parser": "sri" (or other), "metadata_extraction": {{...}}
     - For interpretation: "parser": "rtf", "extract_participants": true, "extract_interpretation": true
     - For image: "provider": "tesseract" (local OCR) or "openai" (GPT-4 Vision for rich scene descriptions)
     - For video: "actions": ["transcribe", "analyze_frames"] (transcribe audio + extract/analyze key frames)
   - "processing_rules": Text description explaining how files relate and how to process them
   - "output_format": "wiretap_structured" or "combined" or "media_structured" or "custom"
   - "related_files_indicator": true

Respond with valid JSON only, matching this structure:
{{
  "folder_processing": {{
    "type": "special",
    "file_rules": [...],
    "processing_rules": "...",
    "output_format": "...",
    "related_files_indicator": true
  }}
}}"""
        
        logger.info("Calling LLM service to generate profile...")
        
        # Call LLM with JSON mode and timeout
        # Note: LLM calls can take 30-90 seconds depending on the model and prompt complexity
        # This is expected behavior - the request will show "Waiting for Server" during this time
        llm_timeout = 90  # Increased to 90 seconds to accommodate slower models
        
        try:
            # Run LLM call in thread pool to avoid blocking the event loop
            llm_response = await run_in_threadpool(
                llm_service.call,
                prompt=prompt,
                temperature=0.3,
                json_mode=True,
                timeout=llm_timeout
            )
            logger.info(f"LLM service responded (length: {len(llm_response) if llm_response else 0})")
        except Exception as llm_err:
            logger.error(f"LLM service call failed: {str(llm_err)}")
            # Check if it's a timeout error
            error_str = str(llm_err).lower()
            if 'timeout' in error_str or 'timed out' in error_str or '504' in str(llm_err):
                raise HTTPException(
                    status_code=504,
                    detail=f"LLM service timeout: Profile generation took longer than {llm_timeout} seconds. The LLM call is taking longer than expected. Please try again with simpler instructions or check if your LLM service is responding."
                )
            raise HTTPException(
                status_code=500,
                detail=f"LLM service error: {str(llm_err)}. This might be due to a timeout or service unavailability. Please check your LLM configuration."
            )
        
        if not llm_response:
            raise HTTPException(status_code=500, detail="LLM service returned empty response")
        
        # Parse LLM response
        try:
            profile_data = json.loads(llm_response)
        except json.JSONDecodeError as json_err:
            logger.warning(f"Failed to parse LLM response as JSON: {str(json_err)}")
            logger.debug(f"LLM response content: {llm_response[:500]}")
            # Try to extract JSON from response if it's wrapped
            import re
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                try:
                    profile_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to parse LLM response as JSON. Response preview: {llm_response[:200]}"
                    )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"LLM response is not valid JSON. Response preview: {llm_response[:200]}"
                )
        
        folder_processing = profile_data.get("folder_processing", {})
        
        if not folder_processing:
            logger.warning("Generated profile does not contain folder_processing section")
            # Create a basic structure if missing
            folder_processing = {
                "type": "special",
                "file_rules": [],
                "processing_rules": request.user_instructions,
                "output_format": "combined",
                "related_files_indicator": True
            }
        
        logger.info("Profile generation completed successfully")
        
        return {
            "success": True,
            "profile": folder_processing,
            "raw_response": llm_response[:500] if len(llm_response) > 500 else llm_response  # Truncate for response
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error generating folder profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate profile: {str(e)}")


@router.post("/folder/profile/test")
async def test_folder_profile(
    request: FolderProfileTestRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Test a folder processing profile on a folder (dry run or full processing).
    Returns a background task ID for processing.
    """
    try:
        from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
        from uuid import UUID
        try:
            check_case_access(db, UUID(request.case_id), current_user, required_permission=("evidence", "upload"))
        except (CaseNotFound, CaseAccessDenied) as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

        case_data_dir = BASE_DIR / "ingestion" / "data" / request.case_id
        if not case_data_dir.exists():
            raise HTTPException(status_code=404, detail="Case data directory not found")

        full_folder_path = (case_data_dir / request.folder_path).resolve()
        case_resolved = case_data_dir.resolve()

        try:
            full_folder_path.relative_to(case_resolved)
        except ValueError:
            raise HTTPException(status_code=403, detail="Path outside case directory")

        if not full_folder_path.exists() or not full_folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")

        # Create background task for testing
        task = background_task_storage.create_task(
            task_type="folder_profile_test",
            task_name=f"Test folder profile: {request.folder_path}",
            case_id=request.case_id,
            owner=current_user.email,
            metadata={
                "folder_path": request.folder_path,
                "profile_name": request.profile_name,
            }
        )
        task_id = task["id"]
        
        # Import and run folder ingestion in background
        def test_folder_profile_background():
            from pathlib import Path
            import sys
            INGESTION_SCRIPTS_PATH = BASE_DIR / "ingestion" / "scripts"
            if str(INGESTION_SCRIPTS_PATH) not in sys.path:
                sys.path.insert(0, str(INGESTION_SCRIPTS_PATH))
            
            from folder_ingestion import ingest_folder_with_profile
            
            def log_callback(message: str):
                evidence_log_storage.add_log(
                    case_id=request.case_id,
                    evidence_id=None,
                    filename=None,
                    level="info",
                    message=f"[Profile Test] {message}"
                )
            
            try:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.RUNNING.value,
                    started_at=datetime.now().isoformat(),
                )
                
                result = ingest_folder_with_profile(
                    folder_path=full_folder_path,
                    profile_name=request.profile_name,
                    case_id=request.case_id,
                    log_callback=log_callback
                )
                
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=datetime.now().isoformat(),
                    metadata={
                        "result": result
                    }
                )
            except Exception as e:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    error=str(e),
                    completed_at=datetime.now().isoformat(),
                )
        
        import threading
        thread = threading.Thread(target=test_folder_profile_background, daemon=False)
        thread.start()
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Folder profile test started"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))