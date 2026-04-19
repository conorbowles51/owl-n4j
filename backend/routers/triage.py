"""
Triage Router

API endpoints for the Evidence Triage Workbench.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user
from sqlalchemy.orm import Session

from models.triage_models import (
    CreateTriageCaseRequest,
    StartScanRequest,
    UploadHashSetRequest,
    CreateStageRequest,
    ExecuteStageRequest,
    CreateTemplateRequest,
    ApplyTemplateRequest,
    AdvisorChatRequest,
    IngestRequest,
    TriageCaseResponse,
    TriageFileListResponse,
    ScanStatsResponse,
    ClassificationStatsResponse,
)
from services.triage.triage_service import triage_service

router = APIRouter(prefix="/api/triage", tags=["triage"])


# ── Filesystem Browse ──────────────────────────────────────────────────

@router.get("/browse")
async def browse_directory(
    path: str = Query("/", description="Directory path to list"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Browse server filesystem directories for source path selection."""
    from pathlib import Path as P
    import os

    target = P(path).resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    entries = []
    try:
        with os.scandir(str(target)) as it:
            for entry in it:
                if entry.name.startswith(".") and entry.name != ".":
                    continue  # skip hidden files but allow current dir
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                entries.append({
                    "name": entry.name,
                    "is_dir": is_dir,
                    "path": str(P(entry.path).resolve()),
                })
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {path}")

    # Sort: directories first, then alphabetical
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))

    return {
        "current_path": str(target),
        "parent_path": str(target.parent) if target != target.parent else None,
        "entries": entries,
    }


# ── Case CRUD ──────────────────────────────────────────────────────────

@router.post("/cases", response_model=TriageCaseResponse)
async def create_triage_case(
    request: CreateTriageCaseRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Create a new triage case for scanning a directory."""
    try:
        case = triage_service.create_case(
            name=request.name,
            description=request.description,
            source_path=request.source_path,
            created_by=current_user.email,
        )
        return case
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cases")
async def list_triage_cases(
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """List triage cases for the current user."""
    cases = triage_service.list_cases(owner=current_user.email)
    return {"cases": cases}


@router.get("/cases/{case_id}")
async def get_triage_case(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get a triage case by ID."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    return case


@router.delete("/cases/{case_id}")
async def delete_triage_case(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Delete a triage case and all its Neo4j data."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    triage_service.delete_case(case_id)
    return {"status": "deleted"}


# ── Scan (Stage 0) ────────────────────────────────────────────────────

@router.post("/cases/{case_id}/scan")
async def start_scan(
    case_id: str,
    request: StartScanRequest = StartScanRequest(),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Start or resume scanning the source directory."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        task_id = triage_service.start_scan(case_id, resume=request.resume)
        return {"task_id": task_id, "message": "Scan started"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cases/{case_id}/stats")
async def get_scan_stats(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get scan statistics for a triage case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        stats = triage_service.get_scan_stats(case_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/files")
async def get_files(
    case_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    sort_by: str = Query("relative_path"),
    sort_dir: str = Query("asc"),
    category: Optional[str] = Query(None),
    extension: Optional[str] = Query(None),
    hash_classification: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    path_prefix: Optional[str] = Query(None),
    is_system_file: Optional[bool] = Query(None),
    is_user_file: Optional[bool] = Query(None),
    user_account: Optional[str] = Query(None),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get paginated file list for a triage case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")

    result = triage_service.get_files(
        case_id=case_id,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_dir=sort_dir,
        category=category,
        extension=extension,
        hash_classification=hash_classification,
        search=search,
        path_prefix=path_prefix,
        is_system_file=is_system_file,
        is_user_file=is_user_file,
        user_account=user_account,
    )
    return result


# ── Classification (Stage 1) ─────────────────────────────────────────

@router.post("/cases/{case_id}/classify")
async def start_classification(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Start file classification (hash lookups + path analysis)."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        task_id = triage_service.start_classification(case_id)
        return {"task_id": task_id, "message": "Classification started"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cases/{case_id}/classification")
async def get_classification_stats(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get classification statistics for a triage case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        stats = triage_service.get_classification_stats(case_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/hash-sets")
async def upload_hash_set(
    case_id: str,
    request: UploadHashSetRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Upload a custom hash set for classification."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    count = triage_service.upload_hash_set(request.name, request.hashes)
    return {"name": request.name, "valid_hashes": count}


@router.get("/hash-sets")
async def list_hash_sets(
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """List available custom hash sets."""
    sets = triage_service.list_hash_sets()
    return {"hash_sets": sets}


# ── Profile (Stage 2) ────────────────────────────────────────────────

@router.post("/cases/{case_id}/profile")
async def generate_profile(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Generate triage profile/dashboard data."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        task_id = triage_service.generate_profile(case_id)
        return {"task_id": task_id, "message": "Profile generation started"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cases/{case_id}/profile")
async def get_profile(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get stored profile data for a triage case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    profile = triage_service.get_profile(case_id)
    if not profile:
        return {"message": "Profile not generated yet"}
    return profile


@router.get("/cases/{case_id}/timeline")
async def get_timeline(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get activity timeline for a triage case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"timeline": triage_service.get_timeline(case_id)}


@router.get("/cases/{case_id}/artifacts")
async def get_artifacts(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get detected high-value forensic artifacts."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"artifacts": triage_service.get_artifacts(case_id)}


@router.get("/cases/{case_id}/mismatches")
async def get_mismatches(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get files with extension mismatches."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"mismatches": triage_service.get_mismatches(case_id)}


# ── Processors & Custom Stages (Phase 4) ─────────────────────────────

@router.get("/processors")
async def list_processors(
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """List available file processors."""
    return {"processors": triage_service.list_processors()}


@router.post("/cases/{case_id}/stages")
async def create_stage(
    case_id: str,
    request: CreateStageRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Create a custom processing stage."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        stage = triage_service.create_custom_stage(
            case_id,
            name=request.name,
            processor_name=request.processor_name,
            config=request.config,
            file_filter=request.file_filter,
        )
        return stage
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cases/{case_id}/stages/{stage_id}/execute")
async def execute_stage(
    case_id: str,
    stage_id: str,
    request: ExecuteStageRequest = ExecuteStageRequest(),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Execute a custom processing stage."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        task_id = triage_service.execute_stage(
            case_id, stage_id,
            max_workers=request.max_workers or 4,
        )
        return {"task_id": task_id, "message": "Stage execution started"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/cases/{case_id}/stages/{stage_id}/results")
async def get_stage_results(
    case_id: str,
    stage_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get artifacts produced by a processing stage."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    results = triage_service.get_stage_results(case_id, stage_id)
    return {"artifacts": results}


@router.get("/cases/{case_id}/files/{file_path:path}/provenance")
async def get_file_provenance(
    case_id: str,
    file_path: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get provenance chain for a specific file."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    return triage_service.get_file_provenance(case_id, file_path)


@router.get("/cases/{case_id}/files/{file_path:path}/artifacts")
async def get_file_artifacts(
    case_id: str,
    file_path: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get all artifacts for a specific file."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"artifacts": triage_service.get_file_artifacts(case_id, file_path)}


# ── Advisor (Phase 5) ────────────────────────────────────────────────

@router.post("/cases/{case_id}/advisor/chat")
async def advisor_chat(
    case_id: str,
    request: AdvisorChatRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Ask the triage advisor a question about the case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    result = triage_service.advisor_chat(
        case_id,
        question=request.question,
        model_provider=request.model_provider,
        model_id=request.model_id,
    )
    return result


@router.get("/cases/{case_id}/advisor/suggest")
async def advisor_suggest(
    case_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get auto-suggested next steps for the case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    suggestions = triage_service.advisor_suggest(case_id)
    return {"suggestions": suggestions}


# ── Templates (Phase 5) ──────────────────────────────────────────────

@router.post("/cases/{case_id}/templates")
async def save_template(
    case_id: str,
    request: CreateTemplateRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Save current case's custom stages as a reusable template."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        template = triage_service.save_template(
            case_id,
            name=request.name,
            description=request.description,
            created_by=current_user.email,
        )
        return template
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/templates")
async def list_templates(
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """List all workflow templates."""
    return {"templates": triage_service.list_templates()}


@router.post("/cases/{case_id}/apply-template")
async def apply_template(
    case_id: str,
    request: ApplyTemplateRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Apply a workflow template to a case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        stages = triage_service.apply_template(request.template_id, case_id)
        return {"stages": stages, "message": f"Applied {len(stages)} stages"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Delete a workflow template."""
    deleted = triage_service.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "deleted"}


# ── Ingestion Bridge (Phase 6) ──────────────────────────────────────

@router.post("/cases/{case_id}/ingest-preview")
async def ingest_preview(
    case_id: str,
    request: IngestRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Preview what would be ingested into an Owl case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    result = triage_service.ingest_preview(
        case_id,
        target_case_id=request.target_case_id,
        file_ids=request.file_ids or None,
        file_filter=request.file_filter,
        include_artifacts=request.include_artifacts,
    )
    return result


@router.post("/cases/{case_id}/ingest")
async def ingest_to_case(
    case_id: str,
    request: IngestRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Ingest selected triage files into an Owl investigation case."""
    case = triage_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Triage case not found")
    if case.get("created_by") != current_user.email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        task_id = triage_service.ingest_to_case(
            case_id,
            target_case_id=request.target_case_id,
            file_ids=request.file_ids or None,
            file_filter=request.file_filter,
            include_artifacts=request.include_artifacts,
            owner=current_user.email,
        )
        return {"task_id": task_id, "message": "Ingestion started"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
