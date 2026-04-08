"""
Evidence Folders Router

REST API for folder CRUD, profile management, and processing operations.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user
from services.evidence_db_storage import EvidenceDBStorage
from services.evidence_processing_service import process_db_files
from services.folder_context_service import resolve_effective_profile
from services.processing_profile_service import (
    normalize_instruction_list,
    normalize_special_entity_types,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evidence-folders", tags=["evidence-folders"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateFolderRequest(BaseModel):
    case_id: str
    name: str
    parent_id: Optional[str] = None


class RenameFolderRequest(BaseModel):
    name: str


class MoveFolderRequest(BaseModel):
    new_parent_id: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    context_instructions: Optional[str] = None
    mandatory_instructions: Optional[List[str]] = None
    profile_overrides: Optional[Dict[str, Any]] = None


class ProcessFolderRequest(BaseModel):
    case_id: str
    recursive: bool = True
    reprocess_completed: bool = False


class FolderSummary(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    file_count: int = 0
    subfolder_count: int = 0
    has_profile: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class BreadcrumbItem(BaseModel):
    id: str
    name: str


def _normalize_folder_profile_payload(req: UpdateProfileRequest) -> dict[str, Any]:
    normalized_overrides = None
    if req.profile_overrides:
        special_entity_types = normalize_special_entity_types(
            req.profile_overrides.get("special_entity_types")
        )
        if special_entity_types:
            normalized_overrides = {"special_entity_types": special_entity_types}

    return {
        "context_instructions": req.context_instructions,
        "mandatory_instructions": normalize_instruction_list(req.mandatory_instructions),
        "profile_overrides": normalized_overrides,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tree")
async def get_folder_tree(
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return the full folder tree for the sidebar."""
    try:
        _check_case_access(db, case_id, current_user)
        tree = EvidenceDBStorage.get_folder_tree(db, uuid.UUID(case_id))
        return {"tree": tree}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/contents")
async def get_folder_contents(
    folder_id: str,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Return contents of a specific folder (or root if folder_id is 'root')."""
    try:
        _check_case_access(db, case_id, current_user)

        fid = None if folder_id == "root" else uuid.UUID(folder_id)
        contents = EvidenceDBStorage.list_contents(db, uuid.UUID(case_id), fid)

        # Build breadcrumbs
        breadcrumbs: List[Dict[str, str]] = []
        folder_info = None
        if fid:
            crumbs = EvidenceDBStorage.get_folder_breadcrumbs(db, fid)
            breadcrumbs = [{"id": str(f.id), "name": f.name} for f in crumbs]
            folder_obj = EvidenceDBStorage.get_folder(db, fid)
            if folder_obj:
                folder_info = {
                    "id": str(folder_obj.id),
                    "name": folder_obj.name,
                    "parent_id": str(folder_obj.parent_id) if folder_obj.parent_id else None,
                    "has_profile": bool(
                        folder_obj.context_instructions
                        or folder_obj.mandatory_instructions
                        or folder_obj.profile_overrides
                    ),
                }

        return {
            "folder": folder_info,
            "breadcrumbs": breadcrumbs,
            "folders": contents["folders"],
            "files": contents["files"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
async def create_folder(
    req: CreateFolderRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Create a new folder."""
    try:
        _check_case_access(db, req.case_id, current_user, permission=("evidence", "upload"))
        parent_id = uuid.UUID(req.parent_id) if req.parent_id else None
        folder = EvidenceDBStorage.create_folder(
            db,
            case_id=uuid.UUID(req.case_id),
            name=req.name,
            parent_id=parent_id,
            created_by_id=current_user.id,
        )
        db.commit()
        return {
            "id": str(folder.id),
            "name": folder.name,
            "parent_id": str(folder.parent_id) if folder.parent_id else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{folder_id}")
async def rename_folder(
    folder_id: str,
    req: RenameFolderRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Rename a folder."""
    try:
        folder = EvidenceDBStorage.get_folder(db, uuid.UUID(folder_id))
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_case_access(db, str(folder.case_id), current_user, permission=("evidence", "upload"))

        updated = EvidenceDBStorage.rename_folder(db, uuid.UUID(folder_id), req.name)
        db.commit()
        return {"id": str(updated.id), "name": updated.name}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: str,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Delete a folder and all its contents recursively."""
    try:
        _check_case_access(db, case_id, current_user, permission=("evidence", "delete"))
        stored_paths = EvidenceDBStorage.delete_folder(
            db, uuid.UUID(folder_id), uuid.UUID(case_id)
        )

        # Clean up physical files
        from pathlib import Path
        deleted_files = 0
        for path_str in stored_paths:
            try:
                p = Path(path_str)
                if p.exists():
                    p.unlink()
                    deleted_files += 1
            except Exception as e:
                logger.warning("Failed to delete file %s: %s", path_str, e)

        db.commit()
        return {
            "deleted_files": deleted_files,
            "deleted_folders": 1,  # The root folder
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{folder_id}/move")
async def move_folder(
    folder_id: str,
    req: MoveFolderRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Move a folder to a new parent."""
    try:
        folder = EvidenceDBStorage.get_folder(db, uuid.UUID(folder_id))
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_case_access(db, str(folder.case_id), current_user, permission=("evidence", "upload"))

        new_parent = uuid.UUID(req.new_parent_id) if req.new_parent_id else None

        # Prevent moving folder into its own descendant (or itself)
        if new_parent:
            if new_parent == uuid.UUID(folder_id):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot move a folder into itself",
                )
            ancestors = EvidenceDBStorage.get_folder_breadcrumbs(db, new_parent)
            ancestor_ids = {a.id for a in ancestors}
            if uuid.UUID(folder_id) in ancestor_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot move a folder into its own descendant",
                )

        updated = EvidenceDBStorage.move_folder(db, uuid.UUID(folder_id), new_parent)
        EvidenceDBStorage.mark_folder_subtree_stale(db, uuid.UUID(folder_id))
        db.commit()
        return {
            "id": str(updated.id),
            "name": updated.name,
            "parent_id": str(updated.parent_id) if updated.parent_id else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/profile")
async def get_folder_profile(
    folder_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get the folder's own context_instructions and profile_overrides."""
    try:
        profile = EvidenceDBStorage.get_folder_profile(db, uuid.UUID(folder_id))
        return profile
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{folder_id}/profile")
async def update_folder_profile(
    folder_id: str,
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Update folder's context instructions and profile overrides."""
    try:
        folder = EvidenceDBStorage.get_folder(db, uuid.UUID(folder_id))
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        _check_case_access(db, str(folder.case_id), current_user, permission=("evidence", "upload"))

        payload = _normalize_folder_profile_payload(req)
        EvidenceDBStorage.update_folder_profile(
            db,
            uuid.UUID(folder_id),
            context_instructions=payload["context_instructions"],
            mandatory_instructions=payload["mandatory_instructions"],
            profile_overrides=payload["profile_overrides"],
        )
        EvidenceDBStorage.mark_folder_subtree_stale(db, uuid.UUID(folder_id))
        db.commit()
        return EvidenceDBStorage.get_folder_profile(db, uuid.UUID(folder_id))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{folder_id}/effective-profile")
async def get_effective_profile(
    folder_id: str,
    case_id: str = Query(..., description="Case ID"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Compute and return the effective profile by walking the ancestor chain."""
    try:
        _check_case_access(db, case_id, current_user)
        result = resolve_effective_profile(db, uuid.UUID(folder_id), uuid.UUID(case_id))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{folder_id}/process")
async def process_folder(
    folder_id: str,
    req: ProcessFolderRequest,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Process all files in a folder (optionally recursive)."""
    try:
        _check_case_access(db, req.case_id, current_user, permission=("evidence", "process"))

        # Collect file IDs
        if folder_id == "root":
            fid = None
            if req.recursive:
                from sqlalchemy import select
                from postgres.models.evidence import EvidenceFile as EF

                file_ids = list(
                    db.scalars(
                        select(EF.id).where(EF.case_id == uuid.UUID(req.case_id))
                    ).all()
                )
            else:
                from sqlalchemy import select
                from postgres.models.evidence import EvidenceFile as EF

                file_ids = list(
                    db.scalars(
                        select(EF.id).where(
                            EF.case_id == uuid.UUID(req.case_id),
                            EF.folder_id.is_(None),
                        )
                    ).all()
                )
        else:
            fid = uuid.UUID(folder_id)
            if req.recursive:
                file_ids = EvidenceDBStorage.collect_recursive_file_ids(db, fid)
            else:
                from sqlalchemy import select
                from postgres.models.evidence import EvidenceFile as EF

                file_ids = list(
                    db.scalars(select(EF.id).where(EF.folder_id == fid)).all()
                )

        if not file_ids:
            return {"job_ids": [], "file_count": 0, "message": "No files found in folder"}

        # Filter out already-processed files unless reprocess requested
        if not req.reprocess_completed:
            from sqlalchemy import select
            from postgres.models.evidence import EvidenceFile as EF
            pending = db.scalars(
                select(EF.id).where(
                    EF.id.in_(file_ids),
                    (EF.status != "processed") | (EF.processing_stale.is_(True)),
                )
            ).all()
            file_ids = list(pending)

        if not file_ids:
            return {"job_ids": [], "file_count": 0, "message": "All files already processed"}

        result = await process_db_files(
            db,
            case_id=uuid.UUID(req.case_id),
            file_ids=file_ids,
            force_reprocess=req.reprocess_completed,
            requested_by_user_id=current_user.id,
        )
        result["effective_profile"] = resolve_effective_profile(
            db, fid, uuid.UUID(req.case_id)
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/files/{file_id}/move")
async def move_file(
    file_id: str,
    new_folder_id: Optional[str] = Query(None, description="Target folder ID, or null for root"),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Move a file to a different folder."""
    try:
        ef = EvidenceDBStorage.get(db, uuid.UUID(file_id))
        if not ef:
            raise HTTPException(status_code=404, detail="File not found")
        _check_case_access(db, str(ef.case_id), current_user, permission=("evidence", "upload"))

        target = uuid.UUID(new_folder_id) if new_folder_id else None
        EvidenceDBStorage.move_file(db, uuid.UUID(file_id), target)
        EvidenceDBStorage.mark_files_stale(db, [uuid.UUID(file_id)])
        db.commit()
        return {"id": file_id, "folder_id": new_folder_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/files/move-batch")
async def move_files_batch(
    file_ids: List[str],
    new_folder_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Move multiple files to a different folder."""
    try:
        if not file_ids:
            raise HTTPException(status_code=400, detail="No file IDs provided")

        # Access check on first file
        ef = EvidenceDBStorage.get(db, uuid.UUID(file_ids[0]))
        if not ef:
            raise HTTPException(status_code=404, detail="File not found")
        _check_case_access(db, str(ef.case_id), current_user, permission=("evidence", "upload"))

        target = uuid.UUID(new_folder_id) if new_folder_id else None
        EvidenceDBStorage.move_files(db, [uuid.UUID(fid) for fid in file_ids], target)
        EvidenceDBStorage.mark_files_stale(db, [uuid.UUID(fid) for fid in file_ids])
        db.commit()
        return {"moved": len(file_ids), "folder_id": new_folder_id}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_case_access(
    db: Session,
    case_id: str,
    current_user: User,
    permission: tuple | None = None,
) -> None:
    """Check that the user has access to the specified case."""
    from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
    try:
        check_case_access(
            db, uuid.UUID(case_id), current_user,
            required_permission=permission,
        )
    except (CaseNotFound, CaseAccessDenied) as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
