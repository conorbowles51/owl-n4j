from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound
from services.dossier_service import (
    DossierConflict, DossierNotFound, add_media, archive_dossier, create_assessment,
    create_dossier, create_interview, delete_assessment, delete_interview, delete_media,
    add_evidence_links, get_dossier, link_dossier, list_dossiers,
    remove_evidence_link, reorder_media, replace_links,
    update_dossier, update_interview, update_media,
)


router = APIRouter(prefix="/api/dossiers", tags=["dossiers"])


class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    template_key: str | None = None


class LinkIn(BaseModel):
    target_type: str
    target_id: str
    relationship_type: str | None = None
    label: str | None = None
    source_anchor: dict[str, Any] = Field(default_factory=dict)


class DossierCreate(BaseModel):
    case_id: UUID
    dossier_type: str | None = None
    display_name: str | None = Field(default=None, max_length=255)
    canonical_entity_key: str | None = Field(default=None, max_length=512)
    summary: str | None = None
    importance: str | None = Field(default=None, max_length=255)
    status: str = "active"
    roles: list[RoleIn] = Field(default_factory=list)


class DossierUpdate(BaseModel):
    dossier_type: str | None = None
    display_name: str | None = Field(default=None, max_length=255)
    summary: str | None = None
    importance: str | None = Field(default=None, max_length=255)
    status: str | None = None
    roles: list[RoleIn] | None = None


class LinkDossierRequest(BaseModel):
    entity_key: str = Field(min_length=1, max_length=512)


class LinksRequest(BaseModel):
    links: list[LinkIn] = Field(default_factory=list, max_length=500)


class EvidenceLinksRequest(BaseModel):
    evidence_file_ids: list[UUID] = Field(min_length=1, max_length=500)


class AssessmentCreate(BaseModel):
    category: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    assessment_date: date | None = None
    supporting_links: list[LinkIn] = Field(default_factory=list, max_length=100)


class MediaCreate(BaseModel):
    evidence_file_id: UUID
    is_cover: bool = False
    ordinal: int | None = Field(default=None, ge=0)
    caption: str | None = None
    focal_x: float | None = Field(default=None, ge=0, le=1)
    focal_y: float | None = Field(default=None, ge=0, le=1)
    crop_metadata: dict[str, Any] = Field(default_factory=dict)
    source_anchor: dict[str, Any] = Field(default_factory=dict)


class MediaUpdate(BaseModel):
    is_cover: bool | None = None
    ordinal: int | None = Field(default=None, ge=0)
    caption: str | None = None
    focal_x: float | None = Field(default=None, ge=0, le=1)
    focal_y: float | None = Field(default=None, ge=0, le=1)
    crop_metadata: dict[str, Any] | None = None
    source_anchor: dict[str, Any] | None = None


class MediaOrder(BaseModel):
    media_ids: list[UUID] = Field(min_length=1, max_length=500)


class InterviewEvidenceIn(BaseModel):
    evidence_file_id: UUID
    source_anchor: dict[str, Any] = Field(default_factory=dict)


class InterviewCreate(BaseModel):
    interview_date: datetime | None = None
    participants: list[dict[str, Any] | str] = Field(default_factory=list, max_length=100)
    interviewer_user_ids: list[UUID] = Field(default_factory=list, max_length=50)
    status: str = "planned"
    working_notes: str | None = None
    evidence_links: list[InterviewEvidenceIn] = Field(default_factory=list, max_length=100)


class InterviewUpdate(BaseModel):
    interview_date: datetime | None = None
    participants: list[dict[str, Any] | str] | None = Field(default=None, max_length=100)
    interviewer_user_ids: list[UUID] | None = Field(default=None, max_length=50)
    status: str | None = None
    working_notes: str | None = None
    evidence_links: list[InterviewEvidenceIn] | None = Field(default=None, max_length=100)


def _payload(model: BaseModel, *, exclude_unset: bool = False) -> dict[str, Any]:
    return model.model_dump(exclude_unset=exclude_unset, mode="python")


def _error(exc: Exception) -> None:
    if isinstance(exc, (CaseNotFound, DossierNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=403, detail="Access denied") from exc
    if isinstance(exc, DossierConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("")
def dossiers(case_id: UUID = Query(...), q: str | None = None, dossier_type: str | None = None,
             linkage_state: str | None = None, linked_evidence_file_id: UUID | None = None,
             include_archived: bool = False,
             limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
             db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try:
        return list_dossiers(db, case_id=case_id, user=user, query=q, dossier_type=dossier_type,
                             linkage_state=linkage_state,
                             linked_evidence_file_id=linked_evidence_file_id,
                             include_archived=include_archived, limit=limit, offset=offset)
    except Exception as exc: _error(exc)


@router.post("", status_code=201)
def create(request: DossierCreate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return create_dossier(db, case_id=request.case_id, user=user, data=_payload(request))
    except Exception as exc: _error(exc)


@router.get("/{dossier_id}")
def get(dossier_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return get_dossier(db, dossier_id=dossier_id, user=user)
    except Exception as exc: _error(exc)


@router.patch("/{dossier_id}")
def update(dossier_id: UUID, request: DossierUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return update_dossier(db, dossier_id=dossier_id, user=user, data=_payload(request, exclude_unset=True))
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/link")
def link(dossier_id: UUID, request: LinkDossierRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return link_dossier(db, dossier_id=dossier_id, entity_key=request.entity_key, user=user)
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/archive")
def archive(dossier_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return archive_dossier(db, dossier_id=dossier_id, user=user, archived=True)
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/restore")
def restore(dossier_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return archive_dossier(db, dossier_id=dossier_id, user=user, archived=False)
    except Exception as exc: _error(exc)


@router.put("/{dossier_id}/links")
def put_links(dossier_id: UUID, request: LinksRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return replace_links(db, dossier_id=dossier_id, user=user, links=_payload(request)["links"])
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/evidence")
def add_evidence(dossier_id: UUID, request: EvidenceLinksRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try:
        return add_evidence_links(
            db,
            dossier_id=dossier_id,
            evidence_file_ids=request.evidence_file_ids,
            user=user,
        )
    except Exception as exc: _error(exc)


@router.delete("/{dossier_id}/evidence/{evidence_file_id}")
def remove_evidence(dossier_id: UUID, evidence_file_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try:
        return remove_evidence_link(
            db,
            dossier_id=dossier_id,
            evidence_file_id=evidence_file_id,
            user=user,
        )
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/assessments", status_code=201)
def assessment(dossier_id: UUID, request: AssessmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return create_assessment(db, dossier_id=dossier_id, user=user, data=_payload(request))
    except Exception as exc: _error(exc)


@router.delete("/{dossier_id}/assessments/{assessment_id}", status_code=204)
def remove_assessment(dossier_id: UUID, assessment_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: delete_assessment(db, dossier_id=dossier_id, assessment_id=assessment_id, user=user); return Response(status_code=204)
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/media", status_code=201)
def media(dossier_id: UUID, request: MediaCreate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return add_media(db, dossier_id=dossier_id, user=user, data=_payload(request))
    except Exception as exc: _error(exc)


@router.patch("/{dossier_id}/media/{media_id}")
def patch_media(dossier_id: UUID, media_id: UUID, request: MediaUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return update_media(db, dossier_id=dossier_id, media_id=media_id, user=user, data=_payload(request, exclude_unset=True))
    except Exception as exc: _error(exc)


@router.put("/{dossier_id}/media-order")
def order_media(dossier_id: UUID, request: MediaOrder, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return reorder_media(db, dossier_id=dossier_id, user=user, media_ids=request.media_ids)
    except Exception as exc: _error(exc)


@router.delete("/{dossier_id}/media/{media_id}", status_code=204)
def remove_media(dossier_id: UUID, media_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: delete_media(db, dossier_id=dossier_id, media_id=media_id, user=user); return Response(status_code=204)
    except Exception as exc: _error(exc)


@router.post("/{dossier_id}/interviews", status_code=201)
def interview(dossier_id: UUID, request: InterviewCreate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return create_interview(db, dossier_id=dossier_id, user=user, data=_payload(request))
    except Exception as exc: _error(exc)


@router.patch("/{dossier_id}/interviews/{interview_id}")
def patch_interview(dossier_id: UUID, interview_id: UUID, request: InterviewUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: return update_interview(db, dossier_id=dossier_id, interview_id=interview_id, user=user, data=_payload(request, exclude_unset=True))
    except Exception as exc: _error(exc)


@router.delete("/{dossier_id}/interviews/{interview_id}", status_code=204)
def remove_interview(dossier_id: UUID, interview_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    try: delete_interview(db, dossier_id=dossier_id, interview_id=interview_id, user=user); return Response(status_code=204)
    except Exception as exc: _error(exc)
