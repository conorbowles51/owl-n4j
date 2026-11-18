"""Leads (lx-leads): the one list of leads, filtered to a selection for "Leads already here", the side menu's count,
a person's state changes, corrections and confirming a lead into a theory, and running the lead finder. Reads need
case view; writes need case edit. Every id is checked against the case in the path."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.leads import store

router = APIRouter(prefix="/api/cases", tags=["leads"])


def _fail(exc: store.LeadError):
    raise HTTPException(status_code=exc.status, detail=str(exc))


def _split(v: str | None) -> list[str] | None:
    if v is None:
        return None
    return [x for x in (s.strip() for s in v.split(",")) if x]


@router.get("/{case_id}/leads", dependencies=[Depends(require_case_view)])
def list_leads(case_id: UUID, records: str | None = Query(default=None, max_length=200_000),
               people: str | None = Query(default=None, max_length=20_000),
               date_from: str | None = Query(default=None, alias="from", max_length=10),
               date_to: str | None = Query(default=None, alias="to", max_length=10),
               kinds: str | None = Query(default=None, max_length=500),
               db: Session = Depends(get_db), user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    period = (date_from, date_to or date_from) if date_from else None
    leads = store.list_leads(db, case_id, records=_split(records), people=_split(people), period=period,
                             kinds=_split(kinds), me=user.id)
    return {"leads": leads, "total": len(leads), "finder": _finder_state(db, case_id)}


def _finder_state(db, case_id) -> dict[str, Any]:
    from services.leads import finder
    return finder.last_run(db, case_id)


@router.get("/{case_id}/leads/count", dependencies=[Depends(require_case_view)])
def lead_count(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return store.count(db, case_id)


@router.get("/{case_id}/leads/{lead_id}", dependencies=[Depends(require_case_view)])
def read_lead(case_id: UUID, lead_id: UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return store.get(db, case_id, lead_id, user.id)
    except store.LeadError as exc:
        _fail(exc)


@router.post("/{case_id}/leads/{lead_id}:seen", dependencies=[Depends(require_case_view)])
def lead_seen(case_id: UUID, lead_id: UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return store.mark_seen(db, case_id, lead_id, user)
    except store.LeadError as exc:
        _fail(exc)


class StateRequest(BaseModel):
    state: str = Field(max_length=16)
    why: str | None = Field(default=None, max_length=500)


@router.post("/{case_id}/leads/{lead_id}:state", dependencies=[Depends(require_case_edit)])
def lead_state(case_id: UUID, lead_id: UUID, request: StateRequest, db: Session = Depends(get_db),
               user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return store.set_state(db, case_id, lead_id, state=request.state, user=user, why=request.why)
    except store.LeadError as exc:
        _fail(exc)


class CorrectRequest(BaseModel):
    field: str = Field(max_length=16)
    value: str = Field(min_length=1, max_length=4000)


@router.post("/{case_id}/leads/{lead_id}:correct", dependencies=[Depends(require_case_edit)])
def lead_correct(case_id: UUID, lead_id: UUID, request: CorrectRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return store.correct(db, case_id, lead_id, field=request.field, value=request.value, user=user)
    except store.LeadError as exc:
        _fail(exc)


class ConfirmRequest(BaseModel):
    theory_id: UUID
    why: str | None = Field(default=None, max_length=1000)


@router.post("/{case_id}/leads/{lead_id}:confirm", dependencies=[Depends(require_case_edit)])
def lead_confirm(case_id: UUID, lead_id: UUID, request: ConfirmRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    from services.theory_additions import AdditionError
    from services.workspace_entry_service import WorkspaceEntryNotFound, WorkspaceEntryValidationError
    try:
        return store.confirm(db, case_id, lead_id, theory_id=request.theory_id, user=user, why=request.why)
    except store.LeadError as exc:
        db.rollback()
        _fail(exc)
    except WorkspaceEntryNotFound:
        db.rollback()
        raise HTTPException(status_code=404, detail="That theory is not in this case.")
    except (AdditionError, WorkspaceEntryValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{case_id}/leads:find", dependencies=[Depends(require_case_edit)])
def run_finder(case_id: UUID, db: Session = Depends(get_db),
               user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    """Start the lead finder over the case (it runs in the background; the list's ``finder`` says how far it is)."""
    from services.leads import finder
    return finder.start(db, case_id, user=user)
