"""Timeline Router - endpoints for timeline visualization data."""

from typing import Any, Literal, Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access, get_case_if_allowed
from services.neo4j_service import neo4j_service
from services.timeline_view_service import (
    TimelineViewNotFound,
    batch_update_view_events,
    create_timeline_view,
    delete_timeline_view,
    export_timeline,
    get_timeline_view,
    list_timeline_views,
    update_timeline_view,
)

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


class TimelineViewEventResponse(BaseModel):
    id: str
    view_id: str
    case_id: str
    event_key: str
    event_snapshot: dict[str, Any]
    sort_date: str | None = None
    sort_time: str | None = None
    position: int
    created_at: str | None = None
    updated_at: str | None = None


class TimelineViewResponse(BaseModel):
    id: str
    case_id: str
    title: str
    description: str | None = None
    visibility: str
    owner_user_id: str | None = None
    owner_email: str | None = None
    owner_name: str | None = None
    filter_snapshot: dict[str, Any]
    export_defaults: dict[str, Any]
    event_count: int
    created_at: str | None = None
    updated_at: str | None = None
    events: list[TimelineViewEventResponse] = []


class TimelineViewListResponse(BaseModel):
    views: list[TimelineViewResponse]
    total: int


class TimelineViewCreate(BaseModel):
    case_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    event_keys: list[str] = Field(default_factory=list)
    filter_snapshot: dict[str, Any] = Field(default_factory=dict)
    export_defaults: dict[str, Any] = Field(default_factory=dict)


class TimelineViewUpdate(BaseModel):
    case_id: UUID
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    filter_snapshot: dict[str, Any] | None = None
    export_defaults: dict[str, Any] | None = None


class TimelineViewEventsBatch(BaseModel):
    case_id: UUID
    action: Literal["add", "remove", "set"]
    event_keys: list[str] = Field(default_factory=list)


class TimelineExportRequest(BaseModel):
    case_id: UUID
    source: Literal["view", "selection", "filtered"]
    format: Literal["pdf", "csv"] = "pdf"
    view_id: UUID | None = None
    event_keys: list[str] = Field(default_factory=list)
    title: str | None = Field(default=None, max_length=255)
    detail_level: Literal["compact", "standard", "detailed"] = "standard"
    fields: dict[str, bool] = Field(default_factory=dict)
    footer_label: str = Field(default="Confidential", max_length=80)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    if isinstance(exc, TimelineViewNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Timeline view not found") from exc
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("")
async def get_timeline(
    types: Optional[str] = Query(
        None,
        description="Comma-separated event types to include (e.g., 'Transaction,Payment')"
    ),
    start_date: Optional[str] = Query(
        None,
        description="Filter events on or after this date (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None,
        description="Filter events on or before this date (YYYY-MM-DD)"
    ),
    case_id: UUID = Query(
        ...,
        description="REQUIRED: Filter to events in this case"
    ),
    limit: int = Query(500, ge=1, le=2000, description="Maximum events to return"),
    cursor: Optional[str] = Query(None, description="Opaque cursor from a previous response"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Get timeline events sorted chronologically for a specific case.

    Returns events (Transaction, Payment, Communication, etc.) that have dates,
    along with their connected entities.
    """
    try:
        get_case_if_allowed(db=db, case_id=case_id, user=current_user)
        event_types = None
        if types:
            event_types = [t.strip() for t in types.split(",") if t.strip()]

        return neo4j_service.get_timeline_page(
            event_types=event_types,
            start_date=start_date,
            end_date=end_date,
            case_id=str(case_id),
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:
        _handle_error(exc)


@router.get("/views", response_model=TimelineViewListResponse)
def list_case_timeline_views(
    case_id: UUID = Query(...),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        get_case_if_allowed(db=db, case_id=case_id, user=current_user)
        return list_timeline_views(db, case_id=case_id, limit=limit, offset=offset)
    except Exception as exc:
        _handle_error(exc)


@router.post("/views", response_model=TimelineViewResponse, status_code=status.HTTP_201_CREATED)
def create_case_timeline_view(
    request: TimelineViewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(db=db, case_id=request.case_id, user=current_user, required_permission=("case", "edit"))
        return create_timeline_view(
            db,
            case_id=request.case_id,
            current_user=current_user,
            title=request.title,
            description=request.description,
            event_keys=request.event_keys,
            filter_snapshot=request.filter_snapshot,
            export_defaults=request.export_defaults,
        )
    except Exception as exc:
        _handle_error(exc)


@router.get("/views/{view_id}", response_model=TimelineViewResponse)
def get_case_timeline_view(
    view_id: UUID,
    case_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        get_case_if_allowed(db=db, case_id=case_id, user=current_user)
        return get_timeline_view(db, case_id=case_id, view_id=view_id)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/views/{view_id}", response_model=TimelineViewResponse)
def update_case_timeline_view(
    view_id: UUID,
    request: TimelineViewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(db=db, case_id=request.case_id, user=current_user, required_permission=("case", "edit"))
        data = request.model_dump(exclude_unset=True)
        return update_timeline_view(
            db,
            case_id=request.case_id,
            view_id=view_id,
            current_user=current_user,
            title=data.get("title"),
            description=data.get("description"),
            filter_snapshot=data.get("filter_snapshot"),
            export_defaults=data.get("export_defaults"),
        )
    except Exception as exc:
        _handle_error(exc)


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_timeline_view(
    view_id: UUID,
    case_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(db=db, case_id=case_id, user=current_user, required_permission=("case", "edit"))
        delete_timeline_view(db, case_id=case_id, view_id=view_id, current_user=current_user)
    except Exception as exc:
        _handle_error(exc)


@router.post("/views/{view_id}/events:batch", response_model=TimelineViewResponse)
def batch_update_case_timeline_view_events(
    view_id: UUID,
    request: TimelineViewEventsBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(db=db, case_id=request.case_id, user=current_user, required_permission=("case", "edit"))
        return batch_update_view_events(
            db,
            case_id=request.case_id,
            view_id=view_id,
            current_user=current_user,
            action=request.action,
            event_keys=request.event_keys,
        )
    except Exception as exc:
        _handle_error(exc)


@router.post("/export")
def export_case_timeline(
    request: TimelineExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        case = get_case_if_allowed(db=db, case_id=request.case_id, user=current_user)
        exported = export_timeline(
            db,
            case_id=request.case_id,
            case_name=case.title,
            current_user=current_user,
            export_format=request.format,
            source=request.source,
            view_id=request.view_id,
            event_keys=request.event_keys,
            title=request.title,
            detail_level=request.detail_level,
            fields=request.fields,
            footer_label=request.footer_label,
        )
        ascii_filename = exported.filename.encode("ascii", "ignore").decode("ascii") or "timeline-export"
        disposition = (
            f'attachment; filename="{ascii_filename}"; '
            f"filename*=UTF-8''{quote(exported.filename)}"
        )
        return Response(
            content=exported.content,
            media_type=exported.media_type,
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        _handle_error(exc)


@router.get("/types")
async def get_event_types():
    """
    Get available event types that can appear on the timeline.
    
    Returns types and counts for events that have dates.
    """
    # This could be dynamic based on what's in the DB,
    # but for now return the standard event types
    return {
        "event_types": [
            "Transaction",
            "Transfer", 
            "Payment",
            "Communication",
            "Email",
            "PhoneCall",
            "Meeting",
        ]
    }
