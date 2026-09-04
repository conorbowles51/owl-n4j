"""Durable cited AI assistance endpoints for Workspace."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.workspace_ai_service import (
    WorkspaceAIConflict,
    WorkspaceAIError,
    WorkspaceAINotFound,
    accept_output,
    cancel_output,
    create_output,
    get_output,
    list_outputs,
    reject_output,
    retry_output,
    run_output_in_background,
)


router = APIRouter(prefix="/api/workspace", tags=["workspace-ai"])


class WorkspaceAIStartRequest(BaseModel):
    target_type: Literal["dossier", "theory"]
    target_id: UUID
    output_type: Literal["statement_summary", "statement_comparison", "theory_analysis"]
    interview_ids: list[UUID] = Field(default_factory=list, max_length=20)


class WorkspaceAIRejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class WorkspaceAIOutputResponse(BaseModel):
    id: str
    case_id: str
    target_type: str
    target_id: str
    output_type: str
    version: int
    parent_output_id: str | None = None
    job_status: str
    review_status: str
    citation_status: str
    progress: int
    cancel_requested: bool
    content: dict[str, Any]
    citations: list[dict[str, Any]]
    source_set: list[dict[str, Any]]
    proposed_actions: list[dict[str, Any]]
    accepted_targets: list[dict[str, Any]]
    model_metadata: dict[str, Any]
    error_message: str | None = None
    rejection_reason: str | None = None
    mandate_version_id: str
    mandate_version_number: int | None = None
    requested_by_user_id: str | None = None
    requested_by_name: str | None = None
    reviewed_by_user_id: str | None = None
    reviewed_by_name: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    reviewed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class WorkspaceAIOutputListResponse(BaseModel):
    outputs: list[WorkspaceAIOutputResponse]
    total: int
    limit: int
    offset: int


def _raise_workspace_ai_error(db: Session, exc: Exception) -> None:
    db.rollback()
    if isinstance(exc, WorkspaceAINotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceAIConflict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceAIError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.post(
    "/{case_id}/ai-outputs",
    response_model=WorkspaceAIOutputResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_case_edit)],
)
def start_workspace_ai_output(
    case_id: UUID,
    request: WorkspaceAIStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        result = create_output(
            db,
            case_id=case_id,
            target_type=request.target_type,
            target_id=request.target_id,
            output_type=request.output_type,
            requested_by=current_user,
            interview_ids=request.interview_ids,
        )
        background_tasks.add_task(run_output_in_background, UUID(result["id"]))
        return result
    except Exception as exc:
        _raise_workspace_ai_error(db, exc)


@router.get(
    "/{case_id}/ai-outputs",
    response_model=WorkspaceAIOutputListResponse,
    dependencies=[Depends(require_case_view)],
)
def list_workspace_ai_outputs(
    case_id: UUID,
    target_type: Literal["dossier", "theory"] | None = None,
    target_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_outputs(
        db,
        case_id=case_id,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{case_id}/ai-outputs/{output_id}",
    response_model=WorkspaceAIOutputResponse,
    dependencies=[Depends(require_case_view)],
)
def get_workspace_ai_output(
    case_id: UUID,
    output_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return get_output(db, case_id=case_id, output_id=output_id)
    except Exception as exc:
        _raise_workspace_ai_error(db, exc)


@router.post(
    "/{case_id}/ai-outputs/{output_id}/cancel",
    response_model=WorkspaceAIOutputResponse,
    dependencies=[Depends(require_case_edit)],
)
def cancel_workspace_ai_output(
    case_id: UUID,
    output_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return cancel_output(db, case_id=case_id, output_id=output_id)
    except Exception as exc:
        _raise_workspace_ai_error(db, exc)


@router.post(
    "/{case_id}/ai-outputs/{output_id}/retry",
    response_model=WorkspaceAIOutputResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_case_edit)],
)
def retry_workspace_ai_output(
    case_id: UUID,
    output_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        result = retry_output(
            db,
            case_id=case_id,
            output_id=output_id,
            requested_by=current_user,
        )
        background_tasks.add_task(run_output_in_background, UUID(result["id"]))
        return result
    except Exception as exc:
        _raise_workspace_ai_error(db, exc)


@router.post(
    "/{case_id}/ai-outputs/{output_id}/accept",
    response_model=WorkspaceAIOutputResponse,
    dependencies=[Depends(require_case_edit)],
)
def accept_workspace_ai_output(
    case_id: UUID,
    output_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return accept_output(
            db,
            case_id=case_id,
            output_id=output_id,
            reviewer=current_user,
        )
    except Exception as exc:
        _raise_workspace_ai_error(db, exc)


@router.post(
    "/{case_id}/ai-outputs/{output_id}/reject",
    response_model=WorkspaceAIOutputResponse,
    dependencies=[Depends(require_case_edit)],
)
def reject_workspace_ai_output(
    case_id: UUID,
    output_id: UUID,
    request: WorkspaceAIRejectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return reject_output(
            db,
            case_id=case_id,
            output_id=output_id,
            reviewer=current_user,
            reason=request.reason,
        )
    except Exception as exc:
        _raise_workspace_ai_error(db, exc)
