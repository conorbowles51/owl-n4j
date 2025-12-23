"""
Evidence Router

Handles uploading evidence files and triggering ingestion processing.
"""

from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from services.evidence_service import evidence_service
from services.evidence_log_storage import evidence_log_storage
from services.wiretap_tracking import list_processed_wiretaps, is_wiretap_processed, mark_wiretap_processed
from services.wiretap_service import check_wiretap_suitable, process_wiretap_folder_async
from services.background_task_storage import background_task_storage, TaskStatus
from services.neo4j_service import neo4j_service
from services.case_storage import case_storage
from services.cypher_generator import generate_cypher_from_graph
from .auth import get_current_user
from fastapi import Query
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


@router.post("/upload", response_model=UploadResponse)
async def upload_evidence(
    case_id: str = Form(..., description="Associated case ID"),
    files: List[UploadFile] = File(..., description="Evidence files to upload"),
    is_folder: Optional[str] = Form(None, description="Whether this is a folder upload"),
    user: dict = Depends(get_current_user),
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
                    owner=user["username"],
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
                    owner=user["username"],
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
                owner=user["username"],
            )
            return UploadResponse(files=records)
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


@router.get("/wiretap/check")
async def check_wiretap_folder(
    case_id: str = Query(..., description="Case ID"),
    folder_path: str = Query(..., description="Relative folder path from case data directory"),
    user: dict = Depends(get_current_user),
):
    """
    Check if a folder is suitable for wiretap processing.
    """
    try:
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
    user: dict = Depends(get_current_user),
):
    """
    Process one or more wiretap folders.
    
    Creates a separate background task for each folder. Each folder is processed independently.
    """
    try:
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
        
        for folder_path in validated_paths:
            # Create a background task for this folder
            task = background_task_storage.create_task(
                task_type="wiretap_processing",
                task_name=f"Process wiretap folder: {folder_path.split('/')[-1] or folder_path}",
                case_id=request.case_id,
                owner=user["username"],
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
                            
                            # Save Cypher queries to case after successful processing
                            try:
                                # Get current full graph (nodes + links)
                                graph_data = neo4j_service.get_full_graph()
                                
                                # Generate Cypher to recreate this graph
                                cypher_queries = generate_cypher_from_graph(graph_data)
                                
                                # Look up case name (fallback to case_id if not found)
                                case = case_storage.get_case(request.case_id)
                                case_name = case["name"] if case and case.get("name") else request.case_id
                                
                                # Save as a new version on this case
                                case_result = case_storage.save_case_version(
                                    case_id=request.case_id,
                                    case_name=case_name,
                                    cypher_queries=cypher_queries,
                                    snapshots=[],
                                    save_notes=f"Auto-save after processing wiretap folder: {fp}",
                                    owner=user["username"],
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
                            background_task_storage.update_task(
                                tid,
                                status=TaskStatus.FAILED.value,
                                error=result.get("error", "Unknown error"),
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


