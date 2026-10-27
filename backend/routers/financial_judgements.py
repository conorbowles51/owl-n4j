"""Financial judgement calls: what the processor decided that the page does not print outright (fin-judgements).

Reading needs ``case:view``; answering (Looks right / Correct it) needs ``case:edit``, as every other decision a
person takes on the record. Nothing here changes a saved value: a correction is made through the existing
correction path, which writes its own adjudication; this router links it and keeps the person's reason.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import case_access_dependency
from routers.users import get_current_db_user
from services.financial import judgements
from services.financial.quarantine_row import ActorError, actor_from_user

logger = logging.getLogger(__name__)


def _permission(request: Request, payload: dict):
    return ("case", "view") if request.method == "GET" else ("case", "edit")


router = APIRouter(prefix="/api/financial/judgements", tags=["financial"],
                   dependencies=[Depends(get_current_db_user), Depends(case_access_dependency(_permission))])


class Confirm(BaseModel):
    reason: str = Field(default='', max_length=2000)


class Correct(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)
    adjudication_id: UUID | None = None


def _actor(user):
    try:
        return actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
async def list_judgement_calls(case_id: UUID = Query(...), source_document_id: UUID | None = None,
                               statement_period_id: UUID | None = None, subject_id: list[UUID] | None = Query(None),
                               status: str | None = None, strength: str | None = None, rule_id: str | None = None,
                               origin: str | None = None, limit: int = 500, db: Session = Depends(get_db)):
    return dict(items=judgements.list_judgements(
        db, case_id, source_document_id=source_document_id, statement_period_id=statement_period_id,
        subject_ids=subject_id, status=status, strength=strength, rule_id=rule_id, origin=origin, limit=limit))


@router.get("/counts")
async def judgement_counts(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    return judgements.counts(db, case_id)


@router.get("/rules")
async def processor_rules(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Per rule: confirmed / corrected / open, in this case and in every case."""
    return dict(case=judgements.track_record(db, case_id), all_cases=judgements.track_record(db, None))


@router.post("/{judgement_id}/confirm")
async def confirm_judgement(judgement_id: UUID, body: Confirm | None = None, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return judgements.confirm(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user),
                                  reason=(body.reason if body else ''))
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/{judgement_id}/correct")
async def correct_judgement(judgement_id: UUID, body: Correct, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        result = judgements.correct(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user),
                                    reason=body.reason, adjudication_id=body.adjudication_id)
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    try:
        from services.financial.judgement_inbox import append_correction
        append_correction(db, result)
    except Exception:  # noqa: BLE001 - the inbox is refreshed by its periodic script too
        logger.exception('Appending judgement correction %s to the lessons inbox failed', judgement_id)
    return result


@router.post("/{judgement_id}/reopen")
async def reopen_judgement(judgement_id: UUID, case_id: UUID = Query(...),
                           current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return judgements.reopen(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user))
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
