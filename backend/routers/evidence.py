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
from services.wiretap_tracking import list_processed_wiretaps, is_wiretap_processed, mark_wiretap_processed
from services.wiretap_service import check_wiretap_suitable, process_wiretap_folder_async
from services.background_task_storage import background_task_storage, TaskStatus
from services.neo4j_service import neo4j_service
from services.case_storage import case_storage
from services.cypher_generator import generate_cypher_from_graph
from .auth import get_current_user
from routers.users import get_current_db_user
from fastapi import Query, status
from postgres.session import get_db
from postgres.models.user import User
from sqlalchemy.orm import Session
from config import BASE_DIR
from datetime import datetime


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
    summary: Optional[str] = None  # Document summary if available


class EvidenceListResponse(BaseModel):
    files: List[EvidenceRecord]


class UploadResponse(BaseModel):
    """Response for file uploads - can be synchronous or background."""
    files: Optional[List[EvidenceRecord]] = None  # For synchronous uploads
    task_id: Optional[str] = None  # Single task ID (for backwards compatibility)
    task_ids: Optional[List[str]] = None  # Multiple task IDs (for folder uploads)
    message: Optional[str] = None  # Status message


class ProcessRequest(BaseModel):
    case_id: Optional[str] = None
    file_ids: List[str]
    profile: Optional[str] = None  # LLM profile name (e.g., "fraud", "generic")
    max_workers: Optional[int] = None  # Maximum parallel files to process


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
        
        # Get document summaries for processed files
        if files and case_id:
            processed_files = [f for f in files if f.get("status") == "processed"]
            if processed_files:
                try:
                    # Get summaries from Neo4j
                    doc_names = [f.get("original_filename", "") for f in processed_files]
                    summaries = neo4j_service.get_document_summaries_batch(doc_names, case_id)
                    
                    # Add summaries to file records
                    for file in files:
                        if file.get("status") == "processed":
                            filename = file.get("original_filename", "")
                            if filename in summaries:
                                file["summary"] = summaries[filename]
                except Exception as e:
                    # Don't fail the entire request if summary retrieval fails
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to load document summaries: {str(e)}")
        
        return {"files": files}
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
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Upload one or more evidence files for a case.

    Files are stored under the ingestion data directory so they can be
    processed by the ingestion pipeline.

    If is_folder is 'true' or more than 5 files are uploaded, creates background tasks.
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

        # Check if this is a folder upload or should be background task
        is_folder_upload = is_folder and is_folder.lower() == 'true'
        use_background = is_folder_upload or len(files) > 5

        if use_background:
            # Extract files with relative paths for folder uploads
            uploads = []
            
            # Note: FastAPI doesn't easily allow access to arbitrary form fields when using Form()/File()
            # For folder uploads, the frontend sends file_path_{index} fields, but we can't access them here.
            # We'll rely on the filename potentially containing the path, or use the original filename.
            # The relative_path might be None for some files, but upload_folders_background handles that.
            for index, uf in enumerate(files):
                content = await uf.read()
                filename = uf.filename or ""
                
                # For folder uploads, try to extract relative path from filename
                # The frontend may send the path as part of the filename
                relative_path = None
                if '/' in filename or '\\' in filename:
                    # Path separators present - treat as relative path
                    relative_path = filename.replace('\\', '/')
                    # Extract just the filename (last component) for original_filename
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
                # Use upload_folders_background for folder uploads (groups by top-level folder)
                task_ids = evidence_service.upload_folders_background(
                    case_id=case_id,
                    files=uploads,
                    owner=current_user.email,
                )
                return UploadResponse(
                    task_id=task_ids[0] if task_ids else None,  # First task ID for backwards compatibility
                    task_ids=task_ids,
                    message=f"Uploading {len(task_ids)} folder(s) in background" if task_ids else "No folders to upload",
                )
            else:
                # Use upload_files_background for large file uploads
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
            # Synchronous upload for small file sets
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/process/background")
async def process_evidence_background(
    request: ProcessRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Process selected evidence files in the background.

    Returns immediately with a task ID. Use the background-tasks API
    to monitor progress.
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

        task_id = evidence_service.process_files_background(
            evidence_ids=request.file_ids,
            case_id=request.case_id,
            owner=current_user.email,
            profile=request.profile,
            max_workers=request.max_workers,
        )
        return {"task_id": task_id, "message": "Processing started in background"}
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

    Deduplicates by file hash so identical files are only ingested once.
    For multiple files, consider using /process/background instead.
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

        # Run the potentially long-running ingestion work in a threadpool
        # so that other requests (like /evidence/logs) can still be served
        # while processing is ongoing.
        summary = await run_in_threadpool(
            evidence_service.process_files,
            request.file_ids,
            request.case_id,
            current_user.email,
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

        logs = evidence_log_storage.list_logs(case_id=case_id, limit=limit)
        return {"logs": logs}
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
                # Get document summary if available
                summary = None
                if case_id:
                    try:
                        summary = neo4j_service.get_document_summary(filename, case_id)
                    except Exception:
                        # Summary retrieval is optional
                        pass
                
                return {
                    "found": True,
                    "evidence_id": record.get("id"),
                    "case_id": record.get("case_id"),
                    "original_filename": record.get("original_filename"),
                    "stored_path": record.get("stored_path"),
                    "summary": summary,
                }
        
        return {"found": False, "message": f"No evidence file found with name: {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/{filename}")
async def get_document_summary(
    filename: str,
    case_id: str = Query(..., description="Case ID"),
    user: dict = Depends(get_current_user),
):
    """
    Get the AI-generated summary for a document.
    
    Returns the summary stored in Neo4j for the document with the given filename.
    """
    try:
        summary = neo4j_service.get_document_summary(filename, case_id)
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
     - "role": Role of the file ("audio", "metadata", "interpretation", "document", etc.)
     - For audio: "actions": ["transcribe", "translate"], "transcribe_languages": [...], "translate_languages": [...], "whisper_model": "base"
     - For metadata: "parser": "sri" (or other), "metadata_extraction": {{...}}
     - For interpretation: "parser": "rtf", "extract_participants": true, "extract_interpretation": true
   - "processing_rules": Text description explaining how files relate and how to process them
   - "output_format": "wiretap_structured" or "combined" or "custom"
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