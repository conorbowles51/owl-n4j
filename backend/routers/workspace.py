"""Canonical Workspace context and mandate endpoints.

Legacy Workspace notes, findings, theories, witnesses, tasks, deadlines, pins,
timeline, and graph-building routes were retired at the Phase 8 cutover. Their
supported replacements live in the workspace-entries, dossiers, work,
workspace-overview, and workspace-ai routers.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, get_case_if_allowed
from services.mandate_context_service import (
    CaseContextValidationError,
    mandate_context_service,
)
from services.system_log_service import LogOrigin, LogType, system_log_service

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class CaseContextUpdate(BaseModel):
    case_summary: str | None = None
    background: str | None = None
    investigation_type: str | None = None
    jurisdiction: str | None = None
    active_template_key: str = "generic"
    custom_values: dict[str, Any] = Field(default_factory=dict)


class MandateVersionCreate(BaseModel):
    objective: str | None = None
    key_questions: list[str] = Field(default_factory=list)
    in_scope: str | None = None
    out_of_scope: str | None = None
    perspective: str | None = None
    success_criteria: str | None = None
    constraints: str | None = None


def _case_id_or_404(case_id: str) -> UUID:
    try:
        return UUID(case_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Case not found")


@router.get("/{case_id}/context")
async def get_case_context(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Return the canonical case context and active mandate."""
    canonical_case_id = _case_id_or_404(case_id)
    try:
        get_case_if_allowed(db=db, case_id=canonical_case_id, user=current_user)
    except (CaseNotFound, CaseAccessDenied):
        raise HTTPException(status_code=404, detail="Case not found")
    return mandate_context_service.get_context(db, case_id=canonical_case_id)


@router.put("/{case_id}/context", dependencies=[Depends(require_case_edit)])
async def update_case_context(
    case_id: str,
    context: CaseContextUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update canonical case context fields."""
    canonical_case_id = _case_id_or_404(case_id)
    try:
        get_case_if_allowed(db=db, case_id=canonical_case_id, user=current_user)
    except (CaseNotFound, CaseAccessDenied):
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        updated = mandate_context_service.update_context(
            db,
            case_id=canonical_case_id,
            user=current_user,
            payload=context.model_dump(),
        )
        system_log_service.log(
            log_type=LogType.CASE_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Update Case Context",
            details={"case_id": case_id},
            user=current_user.email,
            success=True,
        )
        db.commit()
        return updated
    except CaseContextValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{case_id}/context/mandates")
async def list_mandate_versions(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List immutable mandate versions newest first."""
    canonical_case_id = _case_id_or_404(case_id)
    try:
        get_case_if_allowed(db=db, case_id=canonical_case_id, user=current_user)
    except (CaseNotFound, CaseAccessDenied):
        raise HTTPException(status_code=404, detail="Case not found")
    return {
        "versions": mandate_context_service.list_versions(
            db, case_id=canonical_case_id
        )
    }


@router.post(
    "/{case_id}/context/mandates",
    dependencies=[Depends(require_case_edit)],
)
async def create_mandate_version(
    case_id: str,
    mandate: MandateVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create and activate a new immutable mandate version."""
    canonical_case_id = _case_id_or_404(case_id)
    try:
        version = mandate_context_service.create_version(
            db,
            case_id=canonical_case_id,
            user=current_user,
            payload=mandate.model_dump(),
        )
        db.commit()
        return version
    except CaseContextValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
