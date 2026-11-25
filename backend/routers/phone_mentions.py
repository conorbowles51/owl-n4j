"""Mentions in phone texts, checked against the case (lx-mentions, screen 8 of the phones redesign)."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.mentions import service

router = APIRouter(prefix="/api/cases", tags=["phone-mentions"])


def _fail(exc: service.MentionError):
    raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/{case_id}/phone-mentions", dependencies=[Depends(require_case_view)])
def list_mentions(case_id: UUID, phones: str | None = Query(None, max_length=4000), kind: str | None = Query(None, max_length=20),
                  outcome: str | None = Query(None, max_length=24), limit: int = Query(100, ge=1, le=500),
                  offset: int = Query(0, ge=0), db: Session = Depends(get_db)) -> dict[str, Any]:
    """Counts by kind and outcome, the mentions (contradictions first), each phone's reading and the next steps."""
    ph = [p for p in (phones or "").split(",") if p] or None
    return service.listing(db, case_id, phones=ph, kind=kind, outcome=outcome, limit=limit, offset=offset)


@router.get("/{case_id}/phone-mentions/marks", dependencies=[Depends(require_case_view)])
def mention_marks(case_id: UUID, records: str = Query("", max_length=40_000), db: Session = Depends(get_db)) -> dict[str, Any]:
    """The mentions on each of the given records, for the mark on a message wherever it is shown."""
    return service.marks(db, case_id, [r for r in records.split(",") if r])


@router.get("/{case_id}/phone-mentions/{mention_id}", dependencies=[Depends(require_case_view)])
def read_mention(case_id: UUID, mention_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return service.detail(db, case_id, mention_id)
    except service.MentionError as exc:
        _fail(exc)


class RunRequest(BaseModel):
    phone: UUID
    reader: Literal["rules", "model"] = "rules"


@router.post("/{case_id}/phone-mentions/runs", dependencies=[Depends(require_case_edit)])
def start_run(case_id: UUID, request: RunRequest, db: Session = Depends(get_db),
              user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    """Read one phone's texts for mentions (or carry on a stopped reading). The model reads only a phone whose
    Outside services are allowed."""
    try:
        return service.start(db, case_id, request.phone, user=user, reader=request.reader)
    except service.MentionError as exc:
        _fail(exc)


class DecisionRequest(BaseModel):
    action: Literal["correct", "confirm", "reject", "restore"]
    values: dict[str, Any] | None = None
    reason: str | None = Field(None, max_length=1000)


@router.post("/{case_id}/phone-mentions/{mention_id}/decision", dependencies=[Depends(require_case_edit)])
def decide(case_id: UUID, mention_id: UUID, request: DecisionRequest, db: Session = Depends(get_db),
           user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    """A person corrects, confirms or rejects Loupe's reading; the reading stays beside the correction."""
    try:
        return service.correct(db, case_id, mention_id, values=request.values, action=request.action,
                               reason=request.reason, user=user)
    except service.MentionError as exc:
        _fail(exc)


@router.post("/{case_id}/phone-mentions/{mention_id}/check", dependencies=[Depends(require_case_view)])
def check_again(case_id: UUID, mention_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return service.recheck(db, case_id, mention_id)
    except service.MentionError as exc:
        _fail(exc)
