"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
"""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from services.evidence_service import evidence_service
from services.evidence_log_storage import evidence_log_storage


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
):
    """
    List evidence files.

    Args:
        case_id: Optional case ID to filter by.
        status: Optional status filter
            ('unprocessed', 'processing', 'processed', 'duplicate', 'failed').
    """
    try:
        files = evidence_service.list_files(case_id=case_id, status=status)
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=EvidenceListResponse)
async def upload_evidence(
    case_id: str = Form(..., description="Associated case ID"),
    files: List[UploadFile] = File(..., description="Evidence files to upload"),
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

        records = evidence_service.add_uploaded_files(case_id=case_id, uploads=uploads)
        return {"files": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process", response_model=ProcessResponse)
async def process_evidence(request: ProcessRequest):
    """
    Process selected evidence files.

    Deduplicates by file hash so identical files are only ingested once.
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


