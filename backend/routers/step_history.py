"""The step history strip (lx-guide H-K): one person's steps through one case, private to them."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services import step_history as H

router = APIRouter(prefix="/api/history", tags=["step-history"])


class StepItem(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=300)
    label: Optional[str] = Field(default=None, max_length=300)


class StepBody(BaseModel):
    name: str = Field(min_length=1, max_length=H.MAX_NAME)
    screen: str = Field(min_length=1, max_length=40)
    path: str = Field(min_length=1, max_length=H.MAX_PATH)
    state: dict[str, Any] = Field(default_factory=dict)
    item: Optional[StepItem] = None
    replaces: Optional[UUID] = None


def _view(db, case_id, user):
    authorize_case(db, case_id, user, ("case", "view"))


@router.get("/cases/{case_id}")
def my_steps(case_id: UUID, limit: int = Query(8, ge=1, le=H.LIST_MAX), offset: int = Query(0, ge=0),
             q: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)):
    """This person's steps in the case, newest first; ``total`` says how many there are in all."""
    _view(db, case_id, user)
    return H.listing(db.connection(), user.id, case_id, limit=limit, q=q, offset=offset)


@router.post("/cases/{case_id}")
def add_step(case_id: UUID, body: StepBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    _view(db, case_id, user)
    try:
        out = H.record(db.connection(), user.id, case_id, name=body.name, screen=body.screen, path=body.path,
                       state=body.state, item=body.item.model_dump() if body.item else None, replaces=body.replaces)
    except H.StepError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return out


@router.get("/cases/{case_id}/steps/{step_id}")
def one_step(case_id: UUID, step_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    _view(db, case_id, user)
    out = H.get(db.connection(), user.id, case_id, step_id)
    if out is None:
        raise HTTPException(status_code=404, detail="That step is not in your history for this case.")
    return out


@router.delete("/cases/{case_id}")
def clear_steps(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Clear this person's history for the case. Trails already added to a theory keep their steps."""
    _view(db, case_id, user)
    removed = H.clear(db.connection(), user.id, case_id)
    db.commit()
    return {"removed": removed}
