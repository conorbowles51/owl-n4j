"""Guidance settings (lx-guide): tours, tips and next steps follow a person to any browser; a case admin sets the
case default."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services import guidance

router = APIRouter(prefix="/api/guidance", tags=["guidance"])


class GuidanceBody(BaseModel):
    guidance: Literal["on", "off"]
    case_id: Optional[UUID] = None


class TipBody(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    case_id: Optional[UUID] = None


class TourBody(BaseModel):
    state: Optional[Literal["done", "skipped", "reset"]] = None
    step: Optional[int] = Field(default=None, ge=0, le=50)
    case_id: Optional[UUID] = None


class HistoryBody(BaseModel):
    collapsed: bool
    case_id: Optional[UUID] = None


class CaseDefaultBody(BaseModel):
    guidance: Optional[Literal["on", "off"]] = None


def _case(db, case_id, user):
    if case_id is not None:
        authorize_case(db, case_id, user, ("case", "view"))
    return case_id


def _run(db, fn):
    try:
        out = fn(db.connection())
    except guidance.GuidanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return out


@router.get("/me")
def my_guidance(case_id: Optional[UUID] = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_db_user)):
    """This person's guidance: on or off and why, hidden tip kinds, and where each tour stands."""
    return guidance.read(db.connection(), user.id, _case(db, case_id, user))


@router.put("/me")
def set_my_guidance(body: GuidanceBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    case_id = _case(db, body.case_id, user)
    return _run(db, lambda c: guidance.set_guidance(c, user.id, body.guidance, case_id))


@router.post("/me/tips-off")
def hide_tip(body: TipBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """"Don't show tips like this"."""
    case_id = _case(db, body.case_id, user)
    return _run(db, lambda c: guidance.hide_tip(c, user.id, body.kind, case_id))


@router.post("/me/show-again")
def show_again(case_id: Optional[UUID] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_db_user)):
    """"Show again": hidden tips and finished or skipped tours come back."""
    case_id = _case(db, case_id, user)
    return _run(db, lambda c: guidance.show_tips_again(c, user.id, case_id))


@router.put("/me/tours/{area}")
def set_tour(area: str, body: TourBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    case_id = _case(db, body.case_id, user)
    return _run(db, lambda c: guidance.set_tour(c, user.id, area, state=body.state, step=body.step, case_id=case_id))


@router.put("/me/history")
def set_history(body: HistoryBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Fold the step history strip to one History button, or open it again; kept per person."""
    case_id = _case(db, body.case_id, user)
    return _run(db, lambda c: guidance.set_history_collapsed(c, user.id, body.collapsed, case_id))


@router.put("/cases/{case_id}/default")
def set_case_default(case_id: UUID, body: CaseDefaultBody, db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    """A case admin's default for everyone in the case (people who chose for themselves keep their choice)."""
    authorize_case(db, case_id, user, ("collaborators", "invite"))
    _run(db, lambda c: guidance.set_case_default(c, case_id, body.guidance, user.id))
    return guidance.read(db.connection(), user.id, case_id)


@router.get("/cases/{case_id}/start")
def start_here(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """What the case has, so "Start here" offers only steps that lead somewhere."""
    authorize_case(db, case_id, user, ("case", "view"))
    return guidance.start_counts(db.connection(), case_id)
