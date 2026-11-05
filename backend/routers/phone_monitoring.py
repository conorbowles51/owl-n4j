"""Monitoring apps on a case's phones (agent-evidence-rest E): the indicators with their basis, and a person's edits
of the sourced list for this case. Reads need ``case:view``, edits ``case:edit``."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.manual_changes import records

router = APIRouter(prefix="/api/phone-monitoring", tags=["phone-monitoring"])


class Edit(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=255)
    action: Literal['add', 'reviewed', 'set_aside']
    reason: str = Field(..., min_length=1, max_length=4000)
    label: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=2000)


def _edge(day: date | None, end=False):
    if day is None:
        return None
    return datetime.combine(day, time.max if end else time.min, tzinfo=timezone.utc)


def _call(db, fn):
    from services.phone_analysis.monitoring_apps import MonitoringError
    try:
        return fn()
    except MonitoringError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/{case_id}", dependencies=[Depends(require_case_view)])
def read_indicators(case_id: UUID, start: date | None = Query(None), end: date | None = Query(None),
                    db: Session = Depends(get_db)):
    from services.phone_analysis import monitoring_apps as MA
    out = MA.indicators(db.connection(), db, case_id, start=_edge(start), end=_edge(end, True))
    out['list_summary'] = MA.list_summary(db, case_id)
    return out


@router.post("/{case_id}/entries", dependencies=[Depends(require_case_edit)])
@records('monitoring_app_list_edit', 'change', subject_type='monitoring_app', subject=lambda c: c['body'].get('identifier'))
def edit_list(case_id: UUID, body: Edit, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_db_user)):
    from services.phone_analysis import monitoring_apps as MA
    return _call(db, lambda: MA.edit(db, case_id=case_id, identifier=body.identifier, action=body.action,
                                     reason=body.reason, reviewer=current_user, label=body.label, source=body.source))


@router.delete("/{case_id}/entries/{entry_id}", dependencies=[Depends(require_case_edit)])
@records('monitoring_app_list_edit', 'change', subject_type='monitoring_app', subject=lambda c: c['kw'].get('entry_id'))
def remove_edit(case_id: UUID, entry_id: UUID, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_db_user)):
    from services.phone_analysis import monitoring_apps as MA
    return _call(db, lambda: MA.remove(db, case_id=case_id, edit_id=entry_id, reviewer=current_user))
