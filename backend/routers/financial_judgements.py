"""Financial judgement calls: what the processor decided that the page does not print outright (fin-judgements).

Reading needs ``case:view``; answering (Looks right / Correct it) needs ``case:edit``, as every other decision a
person takes on the record. Nothing here changes a saved value: a correction is made through the existing
correction path, which writes its own adjudication; this router links it and keeps the person's reason.
"""
import logging
from uuid import UUID

from services.manual_changes import records
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
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
    # The statement's file and the holder being saved: a call read from the file's page-image outcome (the holder kept
    # as printed, printed_holders) is shown before the save too.
    file_id: UUID | None = None
    holder: str = Field(default='', max_length=500)


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
                               priority: list[int] | None = Query(None),
                               offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000),
                               db: Session = Depends(get_db)):
    """One page of the case's judgement calls with counts per status, type, strength and maker (each counted
    under every other active filter). Searches file name, account, period, payment and the call's sentence."""
    return judgements.search(db, case_id, q=q, statuses=status or (), strengths=strength or (),
                             origins=origin or (), categories=category or (), rule_ids=rule_id or (),
                             file_ids=file_id or (), account_ids=account_id or (),
                             source_document_id=source_document_id, statement_period_id=statement_period_id,
                             subject_ids=subject_id, priorities=priority or (), offset=offset, limit=limit)


@router.get("/export")
def export_judgement_calls(case_id: UUID = Query(...), q: str = Query('', max_length=256),
                           status: list[str] | None = Query(None), strength: list[str] | None = Query(None),
                           origin: list[str] | None = Query(None), category: list[str] | None = Query(None),
                           rule_id: list[str] | None = Query(None), file_id: list[UUID] | None = Query(None),
                           account_id: list[UUID] | None = Query(None), priority: list[int] | None = Query(None),
                           db: Session = Depends(get_db)):
    """Every call matching the page's filters (not one page of them), focus-first, with its priority (CSV)."""
    page = judgements.search(db, case_id, q=q, statuses=status or (), strengths=strength or (),
                             origins=origin or (), categories=category or (), rule_ids=rule_id or (),
                             file_ids=file_id or (), account_ids=account_id or (), priorities=priority or (),
                             everything=True)
    return Response(content=judgements.export_csv(page), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             f'attachment; filename="judgement-calls-{str(case_id)[:8]}.csv"'})


@router.get("/rows")
def judgement_rows(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Which ledger payments each call touches, for the whole case in one read (the ledger's marks and filter)."""
    return judgements.row_map(db, case_id)


@router.post("/preview")
def preview_judgement_calls(body: Preview, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """The calls the rules make on a statement reading before it is saved (review queue). Stores nothing."""
    from postgres.models.evidence import EvidenceFile
    file = db.get(EvidenceFile, body.file_id) if body.file_id else None
    if file is not None and file.case_id != case_id:
        file = None  # another case's file is never read here
    return dict(items=judgements.preview(body.reading_rows, body.review_rows, currency=body.currency,
                                         statement_id=body.statement_id, file=file, holder=body.holder))


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
@records('model_statement_confirm', 'confirm', field='model_statement')
def confirm_statement(source_document_id: UUID, body: Confirm | None = None, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    """A person confirms, in one action, a statement Claude saved or entered for a person."""
    try:
        return judgements.confirm_statement(db, case_id=case_id, source_document_id=source_document_id,
                                            actor=_actor(current_user), reason=(body.reason if body else ''))
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/{judgement_id}/confirm")
@records('judgement_confirm', 'confirm', field=lambda c: str((c['result'] or {}).get('target_key') or '') if isinstance(c['result'], dict) else '')
def confirm_judgement(judgement_id: UUID, body: Confirm | None = None, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return judgements.confirm(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user),
                                  reason=(body.reason if body else ''))
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/{judgement_id}/correct")
def correct_judgement(judgement_id: UUID, body: Correct, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        result = judgements.correct(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user),
                                    reason=body.reason, adjudication_id=body.adjudication_id)
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    try:
        from services.manual_changes import record_judgement_correction
        record_judgement_correction(db, result, committed=True, actor=current_user)
    except Exception:  # noqa: BLE001 - the inbox is refreshed by its periodic script too
        logger.exception('Appending judgement correction %s to the lessons inbox failed', judgement_id)
    return result


@router.post("/{judgement_id}/reopen")
@records('judgement_reopen', 'change', field='status')
def reopen_judgement(judgement_id: UUID, case_id: UUID = Query(...),
                           current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    try:
        return judgements.reopen(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user))
    except judgements.JudgementError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# The case agent's proposals (services.agent.proposals): accept, reject, open a cited source, precision trend.
# ---------------------------------------------------------------------------

class Accept(BaseModel):
    reason: str = Field(default='', max_length=2000)
    # 'ui': the screen, whose accept button enables only after a cited source was opened. Anything else is 'api'.
    via: str = Field(default='api', max_length=8)


class Reject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)


class Opened(BaseModel):
    citation: str = Field(..., min_length=1, max_length=600)


def _proposal_call(fn):
    from services.agent.proposals import ProposalError
    try:
        return fn()
    except (ProposalError, judgements.JudgementError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/proposals/precision")
def proposal_precision(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Per proposal kind, what people did with the case agent's proposals (accepted / corrected / rejected) per week,
    and how many confirmations were made after a cited source was opened. This case and every case."""
    from services.agent.proposals import precision
    return dict(case=precision(db, case_id), all_cases=precision(db, None))


@router.post("/{judgement_id}/opened")
def proposal_source_opened(judgement_id: UUID, body: Opened, case_id: UUID = Query(...),
                           current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.agent.proposals import record_open
    return _proposal_call(lambda: record_open(db, case_id=case_id, proposal_type='judgement',
                                              proposal_id=judgement_id, citation=body.citation, user=current_user))


@router.post("/{judgement_id}/accept")
@records('agent_proposal_accept', 'confirm', subject_type='judgement',
         field=lambda c: str((c['result'] or {}).get('rule_id') or '') if isinstance(c['result'], dict) else '')
def accept_proposal(judgement_id: UUID, body: Accept | None = None, case_id: UUID = Query(...),
                    current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.agent import proposals
    body = body or Accept()

    def run():
        try:
            return proposals.confirm(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user),
                                     user=current_user, reason=body.reason, via=body.via)
        except Exception:
            db.rollback()
            raise
    return _proposal_call(run)


@router.post("/{judgement_id}/reject")
def reject_proposal(judgement_id: UUID, body: Reject, case_id: UUID = Query(...),
                    current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.agent import proposals

    def run():
        try:
            return proposals.reject(db, case_id=case_id, judgement_id=judgement_id, actor=_actor(current_user),
                                    user=current_user, reason=body.reason)
        except Exception:
            db.rollback()
            raise
    result = _proposal_call(run)
    try:
        from services.manual_changes import record_judgement_correction
        record_judgement_correction(db, result, committed=True, actor=current_user)
    except Exception:  # noqa: BLE001 - the inbox is refreshed by its periodic script too
        logger.exception('Appending rejected proposal %s to the lessons inbox failed', judgement_id)
    return result


# ---------------------------------------------------------------------------
# Proceeds calculations (services.financial.proceeds): every assumption a judgement call a person sets.
# ---------------------------------------------------------------------------

class ProceedsCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    currency: str = Field(..., min_length=3, max_length=3)
    period_start: str | None = None
    period_end: str | None = None
    deposit_categories: list[str] = Field(default_factory=list, max_length=50)


class AssumptionSet(BaseModel):
    low: str = Field(..., min_length=1, max_length=40)
    high: str = Field(..., min_length=1, max_length=40)
    source: str = Field(..., min_length=1, max_length=600)
    reason: str = Field(default='', max_length=2000)


def _proceeds_call(db, fn):
    from services.financial.proceeds import ProceedsError
    try:
        return fn()
    except ProceedsError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _day(value):
    from datetime import date
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Give dates as YYYY-MM-DD.') from exc


@router.get("/proceeds/list")
def proceeds_list(case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.proceeds import list_calculations
    return list_calculations(db, case_id=case_id)


@router.get("/proceeds/{calculation_id}")
def proceeds_view(calculation_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db)):
    from services.financial.proceeds import view
    return _proceeds_call(db, lambda: view(db, case_id=case_id, calculation_id=calculation_id))


@router.post("/proceeds")
def proceeds_create(body: ProceedsCreate, case_id: UUID = Query(...), current_user=Depends(get_current_db_user),
                    db: Session = Depends(get_db)):
    from services.financial.proceeds import create
    return _proceeds_call(db, lambda: create(db, case_id=case_id, title=body.title, currency=body.currency,
                                             actor=_actor(current_user), period_start=_day(body.period_start),
                                             period_end=_day(body.period_end),
                                             deposit_categories=body.deposit_categories))


@router.post("/proceeds/{calculation_id}/assumptions/{key}")
@records('proceeds_assumption', 'change', subject_type='calculation', subject=lambda c: c['kw'].get('calculation_id'),
         field=lambda c: str(c['kw'].get('key') or ''))
def proceeds_set_assumption(calculation_id: UUID, key: str, body: AssumptionSet, case_id: UUID = Query(...),
                            current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.proceeds import set_assumption
    return _proceeds_call(db, lambda: set_assumption(db, case_id=case_id, calculation_id=calculation_id, key=key,
                                                     low=body.low, high=body.high, source=body.source,
                                                     reason=body.reason, actor=_actor(current_user)))


@router.post("/proceeds/{calculation_id}/assumptions/{key}/{judgement_id}/confirm")
def proceeds_confirm_assumption(calculation_id: UUID, key: str, judgement_id: UUID, case_id: UUID = Query(...),
                                current_user=Depends(get_current_db_user), db: Session = Depends(get_db)):
    from services.financial.proceeds import confirm_assumption
    return _proceeds_call(db, lambda: confirm_assumption(db, case_id=case_id, calculation_id=calculation_id,
                                                         judgement_id=judgement_id, actor=_actor(current_user)))
