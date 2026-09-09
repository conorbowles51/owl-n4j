"""Canonical typed Workspace entry API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.workspace_entry_service import (
    WorkspaceEntryConflict,
    WorkspaceEntryNotFound,
    WorkspaceEntryValidationError,
    add_entry_link,
    change_confidence,
    change_lifecycle,
    change_significance,
    convert_theory_to_finding,
    create_entry,
    get_entry,
    list_entries,
    list_entry_authors,
    remove_entry_link,
    restore_entry,
    search_attachment_options,
    soft_delete_entry,
    update_entry,
    update_entry_link,
)


router = APIRouter(prefix="/api/workspace", tags=["workspace-entries"])

EntryType = Literal["note", "finding", "theory"]
FindingSignificance = Literal["high", "medium", "low"]
LinkRelationship = Literal["unclassified", "supports", "contradicts", "context"]
LinkTargetType = Literal[
    "evidence",
    "graph_entity",
    "dossier",
    "entry",
    "task",
    "deadline",
    "timeline_event",
    "agent_artifact",
    "witness",
]


class EntryLinkInput(BaseModel):
    target_type: LinkTargetType
    target_id: str = Field(min_length=1, max_length=512)
    target_label: str | None = Field(default=None, max_length=512)
    relationship: LinkRelationship = "unclassified"
    source_anchor: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EntryLinkResponse(EntryLinkInput):
    id: str
    entry_id: str
    case_id: str
    created_by_user_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class EntryRevisionResponse(BaseModel):
    id: str
    entry_id: str
    revision_number: int
    entry_type: EntryType
    title: str | None = None
    body: str
    tags: list[str] = Field(default_factory=list)
    lifecycle_state: str | None = None
    significance: str | None = None
    confidence: int | None = None
    confidence_rationale: str | None = None
    review_state: str
    editor_user_id: str | None = None
    editor_email: str | None = None
    editor_name: str | None = None
    created_at: str


class EntryEventResponse(BaseModel):
    id: str
    entry_id: str
    event_type: str
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None
    actor_user_id: str | None = None
    actor_email: str | None = None
    actor_name: str | None = None
    created_at: str


class EntryResponse(BaseModel):
    id: str
    case_id: str
    entry_type: EntryType
    title: str | None = None
    body: str
    tags: list[str] = Field(default_factory=list)
    lifecycle_state: str | None = None
    significance: str | None = None
    confidence: int | None = None
    confidence_rationale: str | None = None
    review_state: str
    author_user_id: str | None = None
    author_email: str | None = None
    author_name: str | None = None
    updated_by_user_id: str | None = None
    updated_by_email: str | None = None
    updated_by_name: str | None = None
    version: int
    source_theory_entry_id: str | None = None
    legacy_source: str | None = None
    legacy_id: str | None = None
    migration_metadata: dict[str, Any] = Field(default_factory=dict)
    needs_migration_review: bool = False
    deleted_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    links: list[EntryLinkResponse] = Field(default_factory=list)
    revisions: list[EntryRevisionResponse] = Field(default_factory=list)
    events: list[EntryEventResponse] = Field(default_factory=list)


class EntryListResponse(BaseModel):
    entries: list[EntryResponse]
    total: int


class AttachmentOptionResponse(BaseModel):
    target_type: LinkTargetType
    target_id: str
    label: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttachmentOptionListResponse(BaseModel):
    items: list[AttachmentOptionResponse]


class EntryAuthorResponse(BaseModel):
    user_id: str
    name: str | None = None
    email: str | None = None
    label: str


class EntryCreateRequest(BaseModel):
    entry_type: EntryType
    title: str | None = Field(default=None, max_length=255)
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    lifecycle_state: str | None = None
    significance: FindingSignificance | None = None
    confidence: int | None = Field(default=None, ge=0, le=100, multiple_of=5)
    confidence_rationale: str | None = None
    links: list[EntryLinkInput] = Field(default_factory=list)


class EntryUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    links: list[EntryLinkInput] | None = None


class EntryLifecycleRequest(BaseModel):
    expected_version: int = Field(ge=1)
    lifecycle_state: str = Field(min_length=1, max_length=32)
    rationale: str | None = None


class EntryConfidenceRequest(BaseModel):
    expected_version: int = Field(ge=1)
    confidence: int | None = Field(default=None, ge=0, le=100, multiple_of=5)
    rationale: str | None = None


class EntrySignificanceRequest(BaseModel):
    expected_version: int = Field(ge=1)
    significance: FindingSignificance


class EntryVersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class TheoryConversionRequest(EntryVersionRequest):
    significance: FindingSignificance
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=1)


class TheoryConversionResponse(BaseModel):
    theory: EntryResponse
    finding: EntryResponse


class EntryLinkCreateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    link: EntryLinkInput


class EntryLinkUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    relationship: LinkRelationship
    source_anchor: dict[str, Any] | None = None


def _raise_entry_error(db: Session, exc: Exception) -> None:
    if isinstance(exc, WorkspaceEntryNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceEntryConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, WorkspaceEntryValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, IntegrityError):
        db.rollback()
        raise HTTPException(
            status_code=409, detail="A conflicting Workspace entry or link already exists"
        ) from exc
    raise exc


@router.get(
    "/{case_id}/entries",
    response_model=EntryListResponse,
    dependencies=[Depends(require_case_view)],
)
def list_case_entries(
    case_id: UUID,
    entry_type: EntryType | None = Query(None),
    lifecycle_state: str | None = Query(None),
    significance: FindingSignificance | None = Query(None),
    confidence_min: int | None = Query(None, ge=0, le=100, multiple_of=5),
    confidence_max: int | None = Query(None, ge=0, le=100, multiple_of=5),
    author_user_id: UUID | None = Query(None),
    q: str | None = Query(None),
    updated_since: datetime | None = Query(None),
    include_deleted: bool = Query(False),
    sort_by: Literal["updated_at", "created_at", "title", "confidence", "significance"] = Query("updated_at"),
    sort_direction: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_entries(
        db,
        case_id=case_id,
        entry_type=entry_type,
        lifecycle_state=lifecycle_state,
        significance=significance,
        confidence_min=confidence_min,
        confidence_max=confidence_max,
        author_user_id=author_user_id,
        query_text=q,
        updated_since=updated_since,
        include_deleted=include_deleted,
        sort_by=sort_by,
        sort_direction=sort_direction,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{case_id}/attachment-options",
    response_model=AttachmentOptionListResponse,
    dependencies=[Depends(require_case_view)],
)
def list_case_attachment_options(
    case_id: UUID,
    target_type: LinkTargetType = Query(...),
    q: str | None = Query(None),
    target_ids: list[str] | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    try:
        return {
            "items": search_attachment_options(
                db,
                case_id=case_id,
                target_type=target_type,
                query_text=q,
                target_ids=target_ids,
                limit=limit,
            )
        }
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.get(
    "/{case_id}/entry-authors",
    response_model=list[EntryAuthorResponse],
    dependencies=[Depends(require_case_view)],
)
def list_case_entry_authors(
    case_id: UUID,
    db: Session = Depends(get_db),
):
    return list_entry_authors(db, case_id=case_id)


@router.get(
    "/{case_id}/entries/{entry_id}",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_view)],
)
def get_case_entry(
    case_id: UUID,
    entry_id: UUID,
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return get_entry(
            db, case_id=case_id, entry_id=entry_id, include_deleted=include_deleted
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries",
    response_model=EntryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_case_edit)],
)
def create_case_entry(
    case_id: UUID,
    request: EntryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return create_entry(
            db,
            case_id=case_id,
            current_user=current_user,
            **request.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.patch(
    "/{case_id}/entries/{entry_id}",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def update_case_entry(
    case_id: UUID,
    entry_id: UUID,
    request: EntryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        values = request.model_dump(exclude_unset=True)
        expected_version = values.pop("expected_version")
        return update_entry(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            expected_version=expected_version,
            **values,
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/lifecycle",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def change_case_entry_lifecycle(
    case_id: UUID,
    entry_id: UUID,
    request: EntryLifecycleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return change_lifecycle(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            **request.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/confidence",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def change_case_entry_confidence(
    case_id: UUID,
    entry_id: UUID,
    request: EntryConfidenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return change_confidence(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            **request.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/significance",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def change_case_entry_significance(
    case_id: UUID,
    entry_id: UUID,
    request: EntrySignificanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return change_significance(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            **request.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/convert-to-finding",
    response_model=TheoryConversionResponse,
    dependencies=[Depends(require_case_edit)],
)
def convert_case_theory(
    case_id: UUID,
    entry_id: UUID,
    request: TheoryConversionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return convert_theory_to_finding(
            db,
            case_id=case_id,
            theory_id=entry_id,
            current_user=current_user,
            **request.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.delete(
    "/{case_id}/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_case_edit)],
)
def delete_case_entry(
    case_id: UUID,
    entry_id: UUID,
    expected_version: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        soft_delete_entry(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            expected_version=expected_version,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/restore",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def restore_case_entry(
    case_id: UUID,
    entry_id: UUID,
    request: EntryVersionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return restore_entry(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            expected_version=request.expected_version,
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/links",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def create_case_entry_link(
    case_id: UUID,
    entry_id: UUID,
    request: EntryLinkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return add_entry_link(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            expected_version=request.expected_version,
            link=request.link.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.patch(
    "/{case_id}/entries/{entry_id}/links/{link_id}",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def update_case_entry_link(
    case_id: UUID,
    entry_id: UUID,
    link_id: UUID,
    request: EntryLinkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return update_entry_link(
            db,
            case_id=case_id,
            entry_id=entry_id,
            link_id=link_id,
            current_user=current_user,
            **request.model_dump(),
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.delete(
    "/{case_id}/entries/{entry_id}/links/{link_id}",
    response_model=EntryResponse,
    dependencies=[Depends(require_case_edit)],
)
def delete_case_entry_link(
    case_id: UUID,
    entry_id: UUID,
    link_id: UUID,
    expected_version: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return remove_entry_link(
            db,
            case_id=case_id,
            entry_id=entry_id,
            link_id=link_id,
            current_user=current_user,
            expected_version=expected_version,
        )
    except Exception as exc:
        _raise_entry_error(db, exc)
