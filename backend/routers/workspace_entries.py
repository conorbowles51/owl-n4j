"""Canonical typed Workspace entry API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from postgres import link_types
from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.workspace_entry_service import (
    WorkspaceEntryConflict,
    WorkspaceEntryNotFound,
    WorkspaceEntryValidationError,
    add_entry_link,
    batch_add_entry_links,
    ENTRY_LINKS_BATCH_LIMIT,
    change_confidence,
    change_lifecycle,
    change_significance,
    convert_theory_to_finding,
    create_entry,
    get_entry,
    list_entries,
    list_financial_payment_links,
    list_entry_authors,
    remove_entry_link,
    remove_entry_links,
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
LinkTargetType = Literal[link_types.WORKSPACE_TYPES]  # type: ignore[valid-type]


class EntryLinkInput(BaseModel):
    target_type: LinkTargetType
    target_id: str = Field(min_length=1, max_length=512)
    target_label: str | None = Field(default=None, max_length=512)
    relationship: LinkRelationship = "unclassified"
    source_anchor: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_anchor", "metadata", mode="before")
    @classmethod
    def _none_is_empty(cls, value):
        return {} if value is None else value


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
    actor_origin: dict[str, Any] | None = None
    origin_label: str | None = None
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
    # A model drafted this entry (services/financial/model_work.model_origin shape); it stays on the entry.
    actor_origin: dict[str, Any] | None = None


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
    significance: FindingSignificance | None


class EntryVersionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class TheoryConversionRequest(EntryVersionRequest):
    significance: FindingSignificance | None = None
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, min_length=1)


class TheoryConversionResponse(BaseModel):
    theory: EntryResponse
    finding: EntryResponse


class EntryLinksRemoveRequest(BaseModel):
    # The service refuses more than ENTRY_LINKS_BATCH_LIMIT with a stated message; nothing is cut.
    link_ids: list[UUID] = Field(default_factory=list)
    expected_version: int = Field(ge=1)


class EntryLinkBatchRequest(BaseModel):
    # The service refuses more than ENTRY_LINKS_BATCH_LIMIT with a stated message; nothing is cut.
    links: list[EntryLinkInput] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=500)
    expected_version: int | None = Field(default=None, ge=1)


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
    "/{case_id}/collections",
    dependencies=[Depends(require_case_view)],
)
def case_collections(
    case_id: UUID,
    target_type: str = Query(..., min_length=1, max_length=64),
    target_ids: list[str] = Query(..., alias="target_ids[]"),
    db: Session = Depends(get_db),
):
    """Where each target is used in this case: findings, theories, notes, dossiers, interviews, tasks, and the
    selections that hold it. At most 200 ids per request; more is refused with a stated message."""
    from services import collection_lookup

    try:
        return collection_lookup.lookup(db, case_id=case_id, target_type=target_type, target_ids=target_ids)
    except collection_lookup.LookupRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    tag: str | None = Query(None, min_length=1, max_length=64),
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
        tag=tag,
        updated_since=updated_since,
        include_deleted=include_deleted,
        sort_by=sort_by,
        sort_direction=sort_direction,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/financial-payment-links", dependencies=[Depends(require_case_view)])
def financial_payment_links(
    case_id: UUID,
    limit: int = Query(200, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_financial_payment_links(db, case_id=case_id, limit=limit, offset=offset)


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


class CaseworkReportRequest(BaseModel):
    sections: list[str] = Field(default_factory=lambda: ["findings", "theories", "notes"])
    privilege_marking: str = "unmarked"


def _link_names(db: Session, case_id: UUID, target_type: str, ids: set[str]) -> dict[str, str]:
    """Current names of linked items in this case, for links saved without a label (casework report)."""
    def uuids() -> list[UUID]:
        out = []
        for value in ids:
            try:
                out.append(UUID(value))
            except ValueError:
                pass
        return out

    if target_type == "graph_entity":
        from services.neo4j.driver import driver

        with driver.session() as session:
            rows = session.run(
                "MATCH (n) WHERE n.case_id = $case_id AND n.key IN $keys RETURN n.key AS key, n.name AS name",
                case_id=str(case_id), keys=sorted(ids),
            )
            return {r["key"]: r["name"] for r in rows if r["name"]}
    if target_type == "evidence":
        from postgres.models.evidence import EvidenceFile

        rows = db.query(EvidenceFile.id, EvidenceFile.original_filename).filter(
            EvidenceFile.case_id == case_id, EvidenceFile.id.in_(uuids())
        )
    elif target_type == "entry":
        from postgres.models.workspace_entry import WorkspaceEntry

        rows = db.query(WorkspaceEntry.id, WorkspaceEntry.title).filter(
            WorkspaceEntry.case_id == case_id, WorkspaceEntry.id.in_(uuids())
        )
    elif target_type == "dossier":
        from postgres.models.case_profile import CaseProfile

        rows = db.query(CaseProfile.id, CaseProfile.display_name).filter(
            CaseProfile.case_id == case_id, CaseProfile.id.in_(uuids())
        )
    else:
        return {}
    return {str(row[0]): row[1] for row in rows.all() if row[1]}


@router.post("/{case_id}/report", dependencies=[Depends(require_case_view)])
def casework_report_pdf(
    case_id: UUID,
    request: CaseworkReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Findings first (by default) with the evidence linked to each, then the other chosen sections, as a PDF."""
    from urllib.parse import quote

    from postgres.models.case import Case
    from services import casework_report
    from services.snapshot_report import SnapshotReportError

    try:
        sections = casework_report.normalise_sections(request.sections)
        entries = {
            section: casework_report.collect_entries(
                lambda entry_type, limit, offset: list_entries(
                    db, case_id=case_id, entry_type=entry_type, sort_by="created_at", sort_direction="asc",
                    limit=limit, offset=offset,
                ),
                casework_report.SECTIONS[section],
            )
            for section in sections
        }
        casework_report.fill_missing_link_labels(entries, lambda t, ids: _link_names(db, case_id, t, ids))
        case = db.query(Case).filter(Case.id == case_id).first()
        content = casework_report.render_casework_report_pdf(
            entries,
            sections=sections,
            case_name=case.title if case else "",
            generated_by=current_user.name or current_user.email,
            privilege_marking=request.privilege_marking,
        )
    except (casework_report.CaseworkReportError, SnapshotReportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    filename = f"casework-report-{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'},
    )


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


@router.post(
    "/{case_id}/entries/{entry_id}/links:batch",
    dependencies=[Depends(require_case_edit)],
)
def batch_case_entry_links(
    case_id: UUID,
    entry_id: UUID,
    request: EntryLinkBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Add links a person chose, with their rationale. Returns the added and skipped counts."""
    if len(request.links) > ENTRY_LINKS_BATCH_LIMIT:
        # Refused before anything is read or written, never cut; the caller sends the rest in parts.
        raise HTTPException(status_code=413, detail=(
            f"{len(request.links):,} links were sent; one request takes at most {ENTRY_LINKS_BATCH_LIMIT:,}. "
            "Send them in parts; nothing was added."))
    try:
        return batch_add_entry_links(
            db,
            case_id=case_id,
            entry_id=entry_id,
            current_user=current_user,
            links=[link.model_dump() for link in request.links],
            rationale=request.rationale,
            expected_version=request.expected_version,
        )
    except Exception as exc:
        _raise_entry_error(db, exc)


@router.post(
    "/{case_id}/entries/{entry_id}/links:remove",
    dependencies=[Depends(require_case_edit)],
)
def remove_case_entry_links(
    case_id: UUID,
    entry_id: UUID,
    request: EntryLinksRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Remove these links as one change: all of them, or none (the Undo of Add to)."""
    try:
        return remove_entry_links(
            db,
            case_id=case_id,
            entry_id=entry_id,
            link_ids=request.link_ids,
            current_user=current_user,
            expected_version=request.expected_version,
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
