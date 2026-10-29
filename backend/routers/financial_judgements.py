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
    # The preview only reads what the reviewer already has open.
    if request.method == "GET" or request.url.path.endswith("/preview"):
        return ("case", "view")
    return ("case", "edit")


router = APIRouter(prefix="/api/financial/judgements", tags=["financial"],
                   dependencies=[Depends(get_current_db_user), Depends(case_access_dependency(_permission))])


class Confirm(BaseModel):
    reason: str = Field(default='', max_length=2000)


class Preview(BaseModel):
    statement_id: str = Field(default='', max_length=200)
    currency: str = Field(default='', max_length=3)
    reading_rows: list[dict] = Field(default_factory=list, max_length=20000)
    review_rows: list[dict] = Field(default_factory=list, max_length=20000)


class Correct(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)
    adjudication_id: UUID | None = None


def _actor(user):
    try:
        return actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
def list_judgement_calls(case_id: UUID = Query(...), source_document_id: UUID | None = None,
                               statement_period_id: UUID | None = None, subject_id: list[UUID] | None = Query(None),
                               q: str = Query('', max_length=256), status: list[str] | None = Query(None),
                               strength: list[str] | None = Query(None), origin: list[str] | None = Query(None),
                               category: list[str] | None = Query(None), rule_id: list[str] | None = Query(None),
                               file_id: list[UUID] | None = Query(None), account_id: list[UUID] | None = Query(None),
                               offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000),
                               db: Session = Depends(get_db)):
    """One page of the case's judgement calls with counts per status, type, strength and maker (each counted
    under every other active filter). Searches file name, account, period, payment and the call's sentence."""
    return judgements.search(db, case_id, q=q, statuses=status or (), strengths=strength or (),
                             origins=origin or (), categories=category or (), rule_ids=rule_id or (),
                             file_ids=file_id or (), account_ids=account_id or (),
                             source_document_id=source_document_id, statement_period_id=statement_period_id,
                             subject_ids=subject_id, offset=offset, limit=limit)


@router.get("/rows")
def judgement_rows(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Which ledger payments each call touches, for the whole case in one read (the ledger's marks and filter)."""
    return judgements.row_map(db, case_id)


@router.post("/preview")
async def preview_judgement_calls(body: Preview, case_id: UUID = Query(...)):
    """The calls the rules make on a statement reading before it is saved (review queue). Stores nothing."""
    return dict(items=judgements.preview(body.reading_rows, body.review_rows, currency=body.currency,
                                         statement_id=body.statement_id))


@router.get("/counts")
def judgement_counts(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    return judgements.counts(db, case_id)


@router.get("/rules")
def processor_rules(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Per rule: confirmed / corrected / open, in this case and in every case."""
    return dict(case=judgements.track_record(db, case_id), all_cases=judgements.track_record(db, None))


@router.get("/statements")
def model_work_statements(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Every statement a model saved or entered for a person, with whether a person has confirmed it."""
    return dict(case_id=str(case_id), statements=judgements.model_work_statements(db, case_id))


@router.post("/statements/{source_document_id}/confirm")
async def confirm_statement(source_document_id: UUID, body: Confirm | None = None, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """A person confirms, in one action, a statement Claude saved or entered for a person."""
    try:
        return judgements.confirm_statement(db, case_id=case_id, source_document_id=source_document_id,
                                            actor=_actor(current_user), reason=(body.reason if body else ''))
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
