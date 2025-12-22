"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
"""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from services.evidence_service import evidence_service
from services.evidence_storage import evidence_storage
from services.evidence_log_storage import evidence_log_storage
from .auth import get_current_user


router = APIRouter(prefix="/api/evidence", tags=["evidence"])


class EvidenceRecord(BaseModel):
    id: str
    case_id: str
    original_filename: str
    stored_path: str
    size: int
    sha256: str
    status: str
    duplicate_of: Optional[str] = None
    created_at: str
    processed_at: Optional[str] = None
    last_error: Optional[str] = None


class EvidenceListResponse(BaseModel):
    files: List[EvidenceRecord]


class ProcessRequest(BaseModel):
    case_id: Optional[str] = None
    file_ids: List[str]
    profile: Optional[str] = None  # LLM profile name (e.g., "fraud", "generic")


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
    status: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    List evidence files.

    Args:
        case_id: Optional case ID to filter by.
        status: Optional status filter
            ('unprocessed', 'processing', 'processed', 'duplicate', 'failed').
    """
    try:
        files = evidence_service.list_files(
            case_id=case_id,
            status=status,
            owner=user["username"],
        )
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=EvidenceListResponse)
async def upload_evidence(
    case_id: str = Form(..., description="Associated case ID"),
    files: List[UploadFile] = File(..., description="Evidence files to upload"),
    user: dict = Depends(get_current_user),
):
    """
    Upload one or more evidence files for a case.

    Files are stored under the ingestion data directory so they can be
    processed by the ingestion pipeline.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    try:
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
            owner=user["username"],
        )
        return {"files": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/background")
async def process_evidence_background(
    request: ProcessRequest,
    user: dict = Depends(get_current_user),
):
    """
    Process selected evidence files in the background.

    Returns immediately with a task ID. Use the background-tasks API
    to monitor progress.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    try:
        task_id = evidence_service.process_files_background(
            evidence_ids=request.file_ids,
            case_id=request.case_id,
            owner=user["username"],
            profile=request.profile,
        )
        return {"task_id": task_id, "message": "Processing started in background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=ProcessResponse)
async def process_evidence(
    request: ProcessRequest,
    user: dict = Depends(get_current_user),
):
    """
    Process selected evidence files synchronously.

    Deduplicates by file hash so identical files are only ingested once.
    For multiple files, consider using /process/background instead.
    """
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="No file_ids provided")

    try:
        # Run the potentially long-running ingestion work in a threadpool
        # so that other requests (like /evidence/logs) can still be served
        # while processing is ongoing.
        summary = await run_in_threadpool(
            evidence_service.process_files,
            request.file_ids,
            request.case_id,
            user["username"],
            request.profile,
        )
        return ProcessResponse(**summary)
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion pipeline not available: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=EvidenceLogListResponse)
async def get_evidence_logs(
    case_id: Optional[str] = None,
    limit: int = 200,
):
    """
    Get recent evidence ingestion logs, optionally filtered by case_id.
    """
    try:
        logs = evidence_log_storage.list_logs(case_id=case_id, limit=limit)
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evidence_id}/file")
async def get_evidence_file(
    evidence_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Serve the actual file content for a given evidence ID.
    
    Returns the PDF/document file with appropriate content type headers.
    Used by the document viewer to display original source documents.
    """
    try:
        # Get the evidence record
        record = evidence_storage.get(evidence_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Evidence not found")
        
        # Check ownership
        if record.get("owner") and record.get("owner") != user["username"]:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get the stored file path
        stored_path = record.get("stored_path")
        if not stored_path:
            raise HTTPException(status_code=404, detail="File path not found")
        
        file_path = Path(stored_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        
        # Determine content type based on file extension
        filename = record.get("original_filename", file_path.name)
        extension = file_path.suffix.lower()
        
        content_type_map = {
            ".pdf": "application/pdf",
            ".txt": "text/plain",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        
        content_type = content_type_map.get(extension, "application/octet-stream")
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename=\"{filename}\"",
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-filename/{filename}")
async def get_evidence_by_filename(
    filename: str,
    case_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Find evidence by original filename and return file info.
    
    This endpoint helps the frontend locate evidence IDs from document names
    stored in entity citations.
    """
    try:
        # Search for files matching the filename
        all_files = evidence_storage.list_files(
            case_id=case_id,
            owner=user["username"]
        )
        
        # Find matching file
        for record in all_files:
            if record.get("original_filename") == filename:
                return {
                    "found": True,
                    "evidence_id": record.get("id"),
                    "case_id": record.get("case_id"),
                    "original_filename": record.get("original_filename"),
                    "stored_path": record.get("stored_path"),
                }
        
        return {"found": False, "message": f"No evidence file found with name: {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


