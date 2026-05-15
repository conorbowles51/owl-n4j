from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_profile_service import (
    CaseProfileNotFound,
    archive_case_profile,
    create_case_profile,
    delete_case_profile,
    get_case_profile,
    get_case_profile_context,
    list_case_profiles,
    update_case_profile,
)
from services.case_service import CaseAccessDenied, CaseNotFound


router = APIRouter(prefix="/api/case-profiles", tags=["case-profiles"])

ProfileType = Literal["person", "address", "event", "device", "organisation", "vehicle", "other"]
AttributeKind = Literal[
    "alias",
    "tag",
    "phone",
    "email",
    "address",
    "identifier",
    "device",
    "vehicle",
    "organisation",
    "date",
    "custom",
]


class CaseProfileAttributeIn(BaseModel):
    kind: AttributeKind = "custom"
    name: str | None = None
    value: str


class CaseProfileAttributeResponse(CaseProfileAttributeIn):
    id: UUID
    ordinal: int


class GraphNodeLinkIn(BaseModel):
    node_key: str
    node_name: str | None = None
    node_type: str | None = None
    relationship_type: str | None = None


class GraphNodeLinkResponse(GraphNodeLinkIn):
    id: UUID
    created_at: datetime | None = None


class EvidenceLinkIn(BaseModel):
    evidence_file_id: UUID
    relationship_type: str | None = None
    excerpt: str | None = None
    page: int | None = None


class EvidenceSummary(BaseModel):
    id: UUID
    case_id: UUID
    original_filename: str
    status: str
    summary: str | None = None
    source_type: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None


class EvidenceLinkResponse(EvidenceLinkIn):
    id: UUID
    created_at: datetime | None = None
    evidence: EvidenceSummary | None = None


class NoteLinkIn(BaseModel):
    note_id: str
    relationship_type: str | None = None


class NoteLinkResponse(NoteLinkIn):
    id: UUID
    created_at: datetime | None = None


class FindingLinkIn(BaseModel):
    finding_id: str
    relationship_type: str | None = None


class FindingLinkResponse(FindingLinkIn):
    id: UUID
    created_at: datetime | None = None


class CaseProfileCreate(BaseModel):
    case_id: UUID
    profile_type: ProfileType = "other"
    display_name: str = Field(..., min_length=1, max_length=255)
    summary: str | None = None
    importance: str | None = None
    aliases: list[str] = []
    tags: list[str] = []
    attributes: list[CaseProfileAttributeIn] = []
    graph_node_links: list[GraphNodeLinkIn] = []
    evidence_links: list[EvidenceLinkIn] = []
    note_links: list[NoteLinkIn] = []
    finding_links: list[FindingLinkIn] = []


class CaseProfileUpdate(BaseModel):
    profile_type: ProfileType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    importance: str | None = None
    aliases: list[str] | None = None
    tags: list[str] | None = None
    attributes: list[CaseProfileAttributeIn] | None = None
    graph_node_links: list[GraphNodeLinkIn] | None = None
    evidence_links: list[EvidenceLinkIn] | None = None
    note_links: list[NoteLinkIn] | None = None
    finding_links: list[FindingLinkIn] | None = None


class CaseProfileResponse(BaseModel):
    id: UUID
    case_id: UUID
    profile_type: ProfileType
    display_name: str
    summary: str | None = None
    importance: str | None = None
    aliases: list[str] = []
    tags: list[str] = []
    attributes: list[CaseProfileAttributeResponse] = []
    graph_node_links: list[GraphNodeLinkResponse] = []
    evidence_links: list[EvidenceLinkResponse] = []
    note_links: list[NoteLinkResponse] = []
    finding_links: list[FindingLinkResponse] = []
    archived_at: datetime | None = None
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CaseProfileListResponse(BaseModel):
    profiles: list[CaseProfileResponse]
    total: int


class WorkspaceLinkedRow(BaseModel):
    id: str
    title: str | None = None
    content: str | None = None
    created_at: str | datetime | None = None
    updated_at: str | datetime | None = None


class CaseProfileContextResponse(BaseModel):
    profile: CaseProfileResponse
    graph_node_links: list[GraphNodeLinkResponse]
    graph_nodes: list[dict[str, Any]]
    evidence_links: list[EvidenceLinkResponse]
    notes: list[WorkspaceLinkedRow]
    findings: list[WorkspaceLinkedRow]
    timeline_nodes: list[dict[str, Any]]


def _handle_access_error(exc: Exception) -> None:
    if isinstance(exc, (CaseNotFound, CaseProfileNotFound)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case profile not found") from exc
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=CaseProfileListResponse)
def list_profiles(
    case_id: UUID = Query(...),
    q: str | None = Query(None, description="Search display name, summary, aliases, tags, and attributes"),
    profile_type: ProfileType | None = None,
    include_archived: bool = False,
    linked_graph_node_key: str | None = None,
    linked_evidence_file_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return list_case_profiles(
            db,
            case_id=case_id,
            user=current_user,
            query=q,
            profile_type=profile_type,
            include_archived=include_archived,
            linked_graph_node_key=linked_graph_node_key,
            linked_evidence_file_id=linked_evidence_file_id,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        _handle_access_error(exc)


@router.post("", response_model=CaseProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    request: CaseProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return create_case_profile(
            db,
            case_id=request.case_id,
            user=current_user,
            data=request.model_dump(),
        )
    except Exception as exc:
        _handle_access_error(exc)


@router.get("/{profile_id}", response_model=CaseProfileResponse)
def get_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return get_case_profile(db, profile_id=profile_id, user=current_user)
    except Exception as exc:
        _handle_access_error(exc)


@router.patch("/{profile_id}", response_model=CaseProfileResponse)
def update_profile(
    profile_id: UUID,
    request: CaseProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return update_case_profile(
            db,
            profile_id=profile_id,
            user=current_user,
            data=request.model_dump(exclude_unset=True),
        )
    except Exception as exc:
        _handle_access_error(exc)


@router.post("/{profile_id}/archive", response_model=CaseProfileResponse)
def archive_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return archive_case_profile(db, profile_id=profile_id, user=current_user, archived=True)
    except Exception as exc:
        _handle_access_error(exc)


@router.post("/{profile_id}/restore", response_model=CaseProfileResponse)
def restore_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return archive_case_profile(db, profile_id=profile_id, user=current_user, archived=False)
    except Exception as exc:
        _handle_access_error(exc)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        delete_case_profile(db, profile_id=profile_id, user=current_user)
    except Exception as exc:
        _handle_access_error(exc)


@router.get("/{profile_id}/context", response_model=CaseProfileContextResponse)
def get_profile_context(
    profile_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        return get_case_profile_context(db, profile_id=profile_id, user=current_user)
    except Exception as exc:
        _handle_access_error(exc)
