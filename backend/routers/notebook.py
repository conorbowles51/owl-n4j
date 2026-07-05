"""Case notebook router."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access, get_case_if_allowed
from services.notebook_service import (
    NOTEBOOK_TARGET_TYPES,
    NotebookNoteNotFound,
    create_note,
    delete_note,
    list_notes,
    update_note,
)


router = APIRouter(prefix="/api/notebook", tags=["notebook"])

NotebookTargetType = Literal["entity", "evidence", "document", "timeline_event", "agent_artifact"]


class NotebookLinkIn(BaseModel):
    target_type: NotebookTargetType
    target_id: str = Field(..., min_length=1, max_length=512)
    target_label: str | None = Field(default=None, max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotebookLinkResponse(NotebookLinkIn):
    id: str
    note_id: str
    case_id: str
    created_at: str | None = None


class NotebookNoteCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    links: list[NotebookLinkIn] = Field(default_factory=list)


class NotebookNoteUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    links: list[NotebookLinkIn] | None = None


class NotebookNoteResponse(BaseModel):
    id: str
    case_id: str
    title: str | None = None
    body: str
    tags: list[str] = []
    visibility: str
    author_user_id: str | None = None
    author_email: str | None = None
    author_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    links: list[NotebookLinkResponse] = []


class NotebookListResponse(BaseModel):
    notes: list[NotebookNoteResponse]
    total: int


def _handle_notebook_error(exc: Exception) -> None:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    if isinstance(exc, NotebookNoteNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook note not found") from exc
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


def _require_case_view(db: Session, case_id: UUID, current_user: User) -> None:
    get_case_if_allowed(db=db, case_id=case_id, user=current_user)


def _require_case_edit(db: Session, case_id: UUID, current_user: User) -> None:
    check_case_access(db=db, case_id=case_id, user=current_user, required_permission=("case", "edit"))


@router.get("/{case_id}/notes", response_model=NotebookListResponse)
def list_case_notebook_notes(
    case_id: UUID,
    mine: bool = Query(False),
    q: str | None = Query(None),
    linked_type: NotebookTargetType | None = Query(None),
    linked_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List public notebook notes for a case."""
    try:
        _require_case_view(db, case_id, current_user)
        return list_notes(
            db,
            case_id=case_id,
            current_user=current_user,
            mine=mine,
            query_text=q,
            linked_type=linked_type,
            linked_id=linked_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        _handle_notebook_error(exc)


@router.get("/{case_id}/targets/{target_type}/{target_id:path}/notes", response_model=NotebookListResponse)
def list_target_notebook_notes(
    case_id: UUID,
    target_type: NotebookTargetType,
    target_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List notes linked to a specific entity, evidence file, timeline event, or artifact."""
    try:
        if target_type not in NOTEBOOK_TARGET_TYPES:
            raise ValueError(f"Unsupported note link type: {target_type}")
        _require_case_view(db, case_id, current_user)
        return list_notes(
            db,
            case_id=case_id,
            current_user=current_user,
            linked_type=target_type,
            linked_id=target_id,
            limit=limit,
        )
    except Exception as exc:
        _handle_notebook_error(exc)


@router.post("/{case_id}/notes", response_model=NotebookNoteResponse, status_code=status.HTTP_201_CREATED)
def create_case_notebook_note(
    case_id: UUID,
    request: NotebookNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a public notebook note for a case."""
    try:
        _require_case_edit(db, case_id, current_user)
        return create_note(
            db,
            case_id=case_id,
            current_user=current_user,
            title=request.title,
            body=request.body,
            tags=request.tags,
            links=[link.model_dump() for link in request.links],
        )
    except Exception as exc:
        _handle_notebook_error(exc)


@router.patch("/{case_id}/notes/{note_id}", response_model=NotebookNoteResponse)
def update_case_notebook_note(
    case_id: UUID,
    note_id: UUID,
    request: NotebookNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update a public notebook note."""
    try:
        _require_case_edit(db, case_id, current_user)
        data = request.model_dump(exclude_unset=True)
        return update_note(
            db,
            case_id=case_id,
            note_id=note_id,
            current_user=current_user,
            title=data.get("title"),
            body=data.get("body"),
            tags=data.get("tags"),
            links=[link.model_dump() for link in request.links] if request.links is not None else None,
        )
    except Exception as exc:
        _handle_notebook_error(exc)


@router.delete("/{case_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_notebook_note(
    case_id: UUID,
    note_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Soft-delete a public notebook note."""
    try:
        _require_case_edit(db, case_id, current_user)
        delete_note(db, case_id=case_id, note_id=note_id, current_user=current_user)
    except Exception as exc:
        _handle_notebook_error(exc)
