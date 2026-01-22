"""
Cases Router

Handles saving and retrieving investigation cases with versioning.

Note: With case_id-based graph isolation, graph data persists in Neo4j
and is filtered by case_id. Cases now just store metadata (name, snapshots, notes).
Cypher queries are no longer stored since data persists in the database.
"""

from datetime import datetime
from typing import List, Optional
from io import BytesIO
from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.case_storage import case_storage
from services.neo4j_service import neo4j_service
from services.system_log_service import system_log_service, LogType, LogOrigin
from services.backup_service import backup_service
from .auth import get_current_user

router = APIRouter(prefix="/api/cases", tags=["cases"])


class CaseCreate(BaseModel):
    """Request model for creating/saving a case version."""
    case_id: Optional[str] = None  # None to create new case
    case_name: str
    snapshots: List[dict] = []  # Full snapshot data, not just IDs
    save_notes: str = ""


class CaseVersionData(BaseModel):
    """Data structure for a case version."""
    version: int
    snapshots: List[dict]  # Full snapshot data
    save_notes: str
    timestamp: str


class CaseData(BaseModel):
    """Data structure for a case."""
    id: str
    name: str
    created_at: str
    updated_at: str
    versions: List[CaseVersionData]


class CaseResponse(BaseModel):
    """Response model for case listing."""
    id: str
    name: str
    created_at: str
    updated_at: str
    version_count: int
    latest_version: int


@router.post("", response_model=dict)
async def save_case(case: CaseCreate, user: dict = Depends(get_current_user)):
    """
    Save a new version of a case.

    Note: Graph data persists in Neo4j with case_id property.
    This endpoint just saves case metadata (name, snapshots, notes).
    """
    try:
        username = user["username"]

        # Save case version (no longer storing Cypher - data persists in Neo4j)
        result = case_storage.save_case_version(
            case_id=case.case_id,
            case_name=case.case_name,
            snapshots=case.snapshots,
            save_notes=case.save_notes,
            owner=username,
        )
        
        # Log the operation
        system_log_service.log(
            log_type=LogType.CASE_MANAGEMENT,
            origin=LogOrigin.FRONTEND,
            action=f"Save Case: {case.case_name}",
            details={
                "case_id": result["case_id"],
                "case_name": case.case_name,
                "version": result["version"],
                "is_new_case": case.case_id is None,
            },
            user=username,
            success=True,
        )
        
        return result
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.CASE_MANAGEMENT,
            origin=LogOrigin.FRONTEND,
            action=f"Save Case Failed: {case.case_name}",
            details={
                "case_name": case.case_name,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Failed to save case: {str(e)}")


@router.get("", response_model=List[CaseResponse])
async def list_cases(user: dict = Depends(get_current_user)):
    """List all cases for the current user."""
    try:
        # Reload cases from disk to ensure we have the latest data
        # This is fast for JSON files unless they're extremely large
        case_storage.reload()
        
        username = user["username"]
        cases = []
        all_cases = case_storage.get_all(owner=username)
        
        # Process cases efficiently
        for case_id, case_data in all_cases.items():
            versions = case_data.get("versions", [])
            # Get latest version efficiently
            latest_version = max([v.get("version", 0) for v in versions], default=0) if versions else 0
            
            cases.append(CaseResponse(
                id=case_data["id"],
                name=case_data["name"],
                created_at=case_data["created_at"],
                updated_at=case_data.get("updated_at", case_data["created_at"]),
                version_count=len(versions),
                latest_version=latest_version,
            ))
        
        # Sort by updated_at descending (most recently updated first)
        cases.sort(key=lambda x: x.updated_at, reverse=True)
        return cases
    except Exception as e:
        # Log the error and return empty list rather than timing out
        print(f"Error listing cases: {e}")
        return []


@router.get("/{case_id}", response_model=CaseData)
async def get_case(case_id: str, user: dict = Depends(get_current_user)):
    """Get a specific case with all versions."""
    case = case_storage.get_case(case_id)

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    # Enforce ownership
    if case.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Case not found")

    # Convert versions to CaseVersionData (no longer includes cypher_queries)
    versions = [
        CaseVersionData(
            version=v.get("version", 0),
            snapshots=v.get("snapshots", []),  # Full snapshot data
            save_notes=v.get("save_notes", ""),
            timestamp=v.get("timestamp", ""),
        )
        for v in case.get("versions", [])
    ]

    return CaseData(
        id=case["id"],
        name=case["name"],
        created_at=case["created_at"],
        updated_at=case.get("updated_at", case["created_at"]),
        versions=versions,
    )


@router.get("/{case_id}/versions/{version}", response_model=CaseVersionData)
async def get_case_version(case_id: str, version: int, user: dict = Depends(get_current_user)):
    """Get a specific version of a case."""
    case = case_storage.get_case(case_id)

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    # Enforce ownership
    if case.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Case not found")

    versions = case.get("versions", [])
    version_data = next((v for v in versions if v.get("version") == version), None)

    if version_data is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    return CaseVersionData(
        version=version_data.get("version", 0),
        snapshots=version_data.get("snapshots", []),  # Full snapshot data
        save_notes=version_data.get("save_notes", ""),
        timestamp=version_data.get("timestamp", ""),
    )


@router.get("/{case_id}/backup")
async def backup_case(
    case_id: str,
    include_files: bool = Query(False, description="Include actual file contents in backup"),
    user: dict = Depends(get_current_user),
):
    """
    Create a backup of a case including all Neo4j data, vector DB data, and metadata.
    
    Returns a ZIP file containing:
    - backup.json: All case data (nodes, relationships, documents, metadata)
    - files/: Actual file contents (if include_files=True)
    """
    try:
        # Verify case exists and user has access
        case = case_storage.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        
        if case.get("owner") != user["username"]:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Create backup file
        backup_zip = backup_service.create_backup_file(case_id, include_files=include_files)
        
        # Generate filename
        case_name = case.get("name", "case").replace(" ", "_").replace("/", "-")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{case_name}_{case_id}_{timestamp}.zip"
        
        # Log the backup operation
        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Case Backup Created",
            details={
                "case_id": case_id,
                "case_name": case.get("name"),
                "include_files": include_files
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return StreamingResponse(
            backup_zip,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")


@router.post("/{case_id}/restore")
async def restore_case(
    case_id: str,
    backup_file: UploadFile = File(...),
    overwrite: bool = Query(False, description="Overwrite existing case data"),
    user: dict = Depends(get_current_user),
):
    """
    Restore a case from a backup file.
    
    The backup file should be a ZIP file created by the backup endpoint.
    """
    try:
        # Verify case exists and user has access (if not overwriting)
        if not overwrite:
            case = case_storage.get_case(case_id)
            if case:
                if case.get("owner") != user["username"]:
                    raise HTTPException(status_code=403, detail="Access denied")
                raise HTTPException(
                    status_code=400,
                    detail="Case already exists. Use overwrite=true to replace it."
                )
        
        # Read backup file
        file_content = await backup_file.read()
        backup_zip = BytesIO(file_content)
        
        # Import backup
        results = backup_service.import_from_file(
            backup_zip,
            new_case_id=case_id,
            overwrite=overwrite
        )
        
        # Log the restore operation
        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Case Restored",
            details={
                "case_id": case_id,
                "overwrite": overwrite,
                "nodes_imported": results.get("nodes_imported", 0),
                "relationships_imported": results.get("relationships_imported", 0),
                "documents_imported": results.get("documents_imported", 0),
            },
            user=user.get("username", "unknown"),
            success=len(results.get("errors", [])) == 0,
        )
        
        return {
            "success": len(results.get("errors", [])) == 0,
            "case_id": case_id,
            "results": results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore backup: {str(e)}")


@router.delete("/{case_id}")
async def delete_case(case_id: str, user: dict = Depends(get_current_user)):
    """
    Delete a case and all its associated graph data from Neo4j.
    """
    case = case_storage.get_case(case_id)
    if case is None or case.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Case not found")

    case_name = case.get("name", "Unknown")

    # Delete case data from Neo4j first
    try:
        deletion_result = neo4j_service.delete_case_data(case_id)
        nodes_deleted = deletion_result.get("nodes_deleted", 0)
        relationships_deleted = deletion_result.get("relationships_deleted", 0)
    except Exception as e:
        # Log error but continue with case metadata deletion
        system_log_service.log(
            log_type=LogType.CASE_MANAGEMENT,
            origin=LogOrigin.FRONTEND,
            action=f"Delete Case Neo4j Data Failed: {case_name}",
            details={"case_id": case_id, "error": str(e)},
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        nodes_deleted = 0
        relationships_deleted = 0

    # Delete case metadata from storage
    if not case_storage.delete_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")

    # Log successful deletion
    system_log_service.log(
        log_type=LogType.CASE_MANAGEMENT,
        origin=LogOrigin.FRONTEND,
        action=f"Delete Case: {case_name}",
        details={
            "case_id": case_id,
            "case_name": case_name,
            "nodes_deleted": nodes_deleted,
            "relationships_deleted": relationships_deleted,
        },
        user=user.get("username", "unknown"),
        success=True,
    )

    return {
        "status": "deleted",
        "id": case_id,
        "nodes_deleted": nodes_deleted,
        "relationships_deleted": relationships_deleted,
    }

