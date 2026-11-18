"""Overlap views (lx-overlapviews-b): drawn Map areas compared over a window, words and deletions that also appear on
another phone in Conversations, and money around chosen events. Read-only, case view; mounted under the Corroborate
router so the paths sit beside the other Corroborate reads."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import require_case_view

router = APIRouter()


class Area(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    ring: list[list[float]] = Field(min_length=3, max_length=500)


class AreaCompareRequest(BaseModel):
    areas: list[Area] = Field(min_length=1, max_length=6)
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    nights: list[date] | None = Field(default=None, max_length=400)
    period_from: date | None = None
    period_to: date | None = None
    documents: dict[int, list[UUID]] | None = None


@router.post("/{case_id}/corroborate/area-compare", dependencies=[Depends(require_case_view)])
def area_compare(case_id: UUID, request: AreaCompareRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Each drawn area over the same hours on every night of one weekday: who is in each and in what order,
    everything inside by kind, night by night, against the other nights of that weekday."""
    from services.corroborate.area_compare import compare_areas
    from services.corroborate.store import CaseStore
    period = (request.period_from, request.period_to) if request.period_from and request.period_to else None
    docs = {i: [str(d) for d in v] for i, v in request.documents.items()} if request.documents is not None else None
    try:
        return compare_areas(CaseStore(db, case_id), [a.model_dump() for a in request.areas], weekday=request.weekday,
                             start=request.start, end=request.end,
                             nights=[d.isoformat() for d in request.nights] if request.nights is not None else None,
                             period=period, documents=docs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{case_id}/corroborate/shared-words", dependencies=[Depends(require_case_view)])
def shared_words(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Words on two or more phones on few dates and deletions kept on another phone, for the Conversations side
    panel (files and pictures are read apart: ``shared-words/files``)."""
    from services.corroborate.shared_words import shared_content
    from services.corroborate.store import CaseStore
    return shared_content(CaseStore(db, case_id))


@router.get("/{case_id}/corroborate/shared-words/files", dependencies=[Depends(require_case_view)])
def shared_words_files(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Files with the same bytes on two or more phones and pictures that only look alike, with full counts."""
    from services.corroborate.shared_words import shared_files
    from services.corroborate.store import CaseStore
    return shared_files(CaseStore(db, case_id))


@router.get("/{case_id}/corroborate/shared-words/thread", dependencies=[Depends(require_case_view)])
def shared_words_thread(case_id: UUID, extraction_id: UUID, thread_key: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Marks for one open thread: shared words per message, the saved names of its numbers, and what the same
    numbers sent or received on other phones meanwhile."""
    from services.corroborate.shared_words import thread_marks
    from services.corroborate.store import CaseStore
    if len(thread_key) > 400:
        raise HTTPException(status_code=422, detail="That thread key is too long.")
    return thread_marks(CaseStore(db, case_id), str(extraction_id), thread_key)


class AroundEvent(BaseModel):
    date: date
    label: str | None = Field(default=None, max_length=200)


class AroundEventRequest(BaseModel):
    events: list[AroundEvent] = Field(min_length=1, max_length=60)


@router.post("/{case_id}/corroborate/around-event", dependencies=[Depends(require_case_view)])
def around_event(case_id: UUID, request: AroundEventRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Money from each chosen event to a week after: one column per payment pattern, bank and phone sources marked,
    statement pages not in the case named, and every other week counted."""
    from services.corroborate.around_event import around_events
    from services.corroborate.store import CaseStore
    try:
        return around_events(CaseStore(db, case_id), [{"date": e.date.isoformat(), "label": e.label} for e in request.events])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{case_id}/corroborate/around-event/choices", dependencies=[Depends(require_case_view)])
def around_event_choices(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Dates to choose as events: from theories and findings, and the dates documents state."""
    from services.corroborate.around_event import event_choices
    from services.corroborate.store import CaseStore
    return {"choices": event_choices(CaseStore(db, case_id))}
