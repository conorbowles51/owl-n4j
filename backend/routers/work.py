from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound
from services.work_service import (
    PinNotFound,
    TaskNotFound,
    WorkValidationError,
    bulk_pin_evidence,
    create_task,
    get_task,
    get_pin_status,
    get_work_view,
    list_pins,
    list_tasks,
    pin_evidence,
    restore_task,
    soft_delete_task,
    unpin_evidence,
    update_task,
)


router = APIRouter(prefix="/api/workspace", tags=["workspace-work"])


class TaskLinkInput(BaseModel):
    target_type: str
    target_id: str
    label: str | None = None
    source_anchor: dict[str, Any] = Field(default_factory=dict)


class TaskCreateInput(BaseModel):
    title: str
    description: str | None = None
    status: str = "todo"
    priority: str = "standard"
    assignee_user_id: UUID | None = None
    due_at: datetime | None = None
    parent_task_id: UUID | None = None
    deadline_id: UUID | None = None
    links: list[TaskLinkInput] = Field(default_factory=list)


class TaskUpdateInput(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_user_id: UUID | None = None
    due_at: datetime | None = None
    parent_task_id: UUID | None = None
    deadline_id: UUID | None = None
    links: list[TaskLinkInput] | None = None


class BulkPinInput(BaseModel):
    evidence_file_ids: list[UUID]


def _raise_work_error(exc: Exception) -> None:
    if isinstance(exc, (TaskNotFound, PinNotFound)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, WorkValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Case edit permission required")
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    raise exc


@router.get("/{case_id}/tasks")
def list_case_tasks(
    case_id: UUID,
    task_status: str | None = Query(None, alias="status"),
    assignee_user_id: UUID | None = None,
    due_before: datetime | None = None,
    include_deleted: bool = False,
    limit: int = Query(100, ge=1, le=250),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        tasks, total = list_tasks(
            db,
            case_id=case_id,
            user=current_user,
            status=task_status,
            assignee_user_id=assignee_user_id,
            due_before=due_before,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        return {"tasks": tasks, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        _raise_work_error(exc)


@router.get("/{case_id}/tasks/{task_id}")
def get_case_task(
    case_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return get_task(db, case_id=case_id, task_id=task_id, user=current_user)
    except Exception as exc:
        _raise_work_error(exc)


@router.post("/{case_id}/tasks", dependencies=[Depends(require_case_edit)])
def create_case_task(
    case_id: UUID,
    payload: TaskCreateInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return create_task(
            db,
            case_id=case_id,
            user=current_user,
            data=payload.model_dump(),
        )
    except Exception as exc:
        _raise_work_error(exc)


@router.put("/{case_id}/tasks/{task_id}", dependencies=[Depends(require_case_edit)])
@router.patch("/{case_id}/tasks/{task_id}", dependencies=[Depends(require_case_edit)])
def update_case_task(
    case_id: UUID,
    task_id: UUID,
    payload: TaskUpdateInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return update_task(
            db,
            case_id=case_id,
            task_id=task_id,
            user=current_user,
            updates=payload.model_dump(exclude_unset=True),
        )
    except Exception as exc:
        _raise_work_error(exc)


@router.delete(
    "/{case_id}/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_case_edit)],
)
def delete_case_task(
    case_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        soft_delete_task(db, case_id=case_id, task_id=task_id, user=current_user)
    except Exception as exc:
        _raise_work_error(exc)


@router.post("/{case_id}/tasks/{task_id}/restore", dependencies=[Depends(require_case_edit)])
def restore_case_task(
    case_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return restore_task(db, case_id=case_id, task_id=task_id, user=current_user)
    except Exception as exc:
        _raise_work_error(exc)


@router.get("/{case_id}/work")
def get_case_work(
    case_id: UUID,
    include_tasks: bool = True,
    include_deadlines: bool = True,
    task_status: str | None = None,
    assignee_user_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=250),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return get_work_view(
            db,
            case_id=case_id,
            user=current_user,
            include_tasks=include_tasks,
            include_deadlines=include_deadlines,
            task_status=task_status,
            assignee_user_id=assignee_user_id,
            limit=limit,
        )
    except Exception as exc:
        _raise_work_error(exc)


@router.get("/{case_id}/pinned")
def list_case_pins(
    case_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        pins, total = list_pins(
            db,
            case_id=case_id,
            user=current_user,
            limit=limit,
            offset=offset,
        )
        return {"pinned_items": pins, "total": total, "limit": limit, "offset": offset}
    except Exception as exc:
        _raise_work_error(exc)


@router.get("/{case_id}/pinned/status")
def get_case_pin_status(
    case_id: UUID,
    evidence_file_ids: list[UUID] = Query(default_factory=list),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return {
            "pins": get_pin_status(
                db,
                case_id=case_id,
                evidence_file_ids=evidence_file_ids,
                user=current_user,
            )
        }
    except Exception as exc:
        _raise_work_error(exc)


@router.post("/{case_id}/pinned", dependencies=[Depends(require_case_edit)])
def pin_case_evidence(
    case_id: UUID,
    item_id: UUID,
    item_type: str = Query("evidence"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    if item_type not in {"evidence", "document"}:
        raise HTTPException(status_code=400, detail="Only evidence can be pinned")
    try:
        pin, created = pin_evidence(
            db,
            case_id=case_id,
            evidence_file_id=item_id,
            user=current_user,
        )
        return {**pin, "created": created, "success": True}
    except Exception as exc:
        _raise_work_error(exc)


@router.post("/{case_id}/pinned/bulk", dependencies=[Depends(require_case_edit)])
def bulk_pin_case_evidence(
    case_id: UUID,
    payload: BulkPinInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return bulk_pin_evidence(
            db,
            case_id=case_id,
            evidence_file_ids=payload.evidence_file_ids,
            user=current_user,
        )
    except Exception as exc:
        _raise_work_error(exc)


@router.delete(
    "/{case_id}/pinned/{pin_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_case_edit)],
)
def unpin_case_evidence(
    case_id: UUID,
    pin_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        unpin_evidence(db, case_id=case_id, pin_id=pin_id, user=current_user)
    except Exception as exc:
        _raise_work_error(exc)
