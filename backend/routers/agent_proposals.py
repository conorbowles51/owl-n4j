"""The case agent's drafted Workspace work, held for a person to decide (agent-proposals B, C).

Listing needs ``case:view``; opening a cited source, accepting and rejecting need ``case:edit``. Accepting creates
the Workspace work under the person, carrying the model origin; what the person opened first is recorded.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services.manual_changes import records

router = APIRouter(prefix="/api/workspace", tags=["agent-proposals"])


class Opened(BaseModel):
    citation: str = Field(..., min_length=1, max_length=600)


class Accept(BaseModel):
    via: Literal['ui', 'api'] = 'api'
    due_at: datetime | date | None = None
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=8000)
    schedule: str | None = Field(default=None, max_length=8000)
    meaning: str | None = Field(default=None, max_length=8000)


class Withdraw(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)


class Reject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=4000)


def _call(db, fn):
    from services.agent.proposals import ProposalError
    try:
        return fn()
    except ProposalError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/{case_id}/proposals", dependencies=[Depends(require_case_view)])
def list_agent_proposals(case_id: UUID, status: str = Query('pending_review', max_length=32),
                         output_type: list[str] | None = Query(None), limit: int = Query(50, ge=1, le=100),
                         offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    from services.agent.workspace_proposals import list_proposals
    return list_proposals(db, case_id=case_id, status=None if status == 'all' else status,
                          output_types=output_type, limit=limit, offset=offset)


@router.post("/{case_id}/proposals/{output_id}/opened", dependencies=[Depends(require_case_edit)])
def agent_proposal_opened(case_id: UUID, output_id: UUID, body: Opened, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_db_user)):
    from services.agent.proposals import record_open
    return _call(db, lambda: record_open(db, case_id=case_id, proposal_type='workspace_ai', proposal_id=output_id,
                                         citation=body.citation, user=current_user))


@router.post("/{case_id}/proposals/{output_id}/accept", dependencies=[Depends(require_case_edit)])
@records('agent_proposal_accept', 'confirm', subject_type='workspace_ai_output',
         subject=lambda c: c['kw'].get('output_id'), field='agent_proposal')
def accept_agent_proposal(case_id: UUID, output_id: UUID, body: Accept | None = None, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_db_user)):
    from services.agent.workspace_proposals import accept
    body = body or Accept()
    return _call(db, lambda: accept(db, case_id=case_id, output_id=output_id, reviewer=current_user, via=body.via,
                                    due_at=body.due_at, edits=dict(title=body.title, body=body.body, schedule=body.schedule, meaning=body.meaning)))


@router.post("/{case_id}/proposals/{output_id}/reject", dependencies=[Depends(require_case_edit)])
@records('workspace_ai_reject', 'set_aside', subject_type='workspace_ai_output',
         subject=lambda c: c['kw'].get('output_id'), field='agent_proposal')
def reject_agent_proposal(case_id: UUID, output_id: UUID, body: Reject, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_db_user)):
    from services.agent.workspace_proposals import reject
    return _call(db, lambda: reject(db, case_id=case_id, output_id=output_id, reviewer=current_user,
                                    reason=body.reason))


class RedCell(BaseModel):
    theory_id: UUID


@router.post("/{case_id}/proposals/red-cell", dependencies=[Depends(require_case_edit)])
def run_red_cell(case_id: UUID, body: RedCell, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_db_user)):
    """An "away from the suspect" sweep of one theory on a model other than the case agent's. Each explanation it
    finds is a proposal pending review; nothing else changes."""
    from services.agent.red_cell import sweep
    return _call(db, lambda: sweep(db, case_id=case_id, theory_id=body.theory_id, requested_by=current_user))


class Disconfirm(BaseModel):
    theory_id: UUID


class DisconfirmStart(BaseModel):
    limit: int | None = Field(default=None, ge=1)


@router.post("/{case_id}/proposals/disconfirm", dependencies=[Depends(require_case_edit)])
def plan_disconfirm(case_id: UUID, body: Disconfirm, background: BackgroundTasks, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_db_user)):
    """Look across the whole case for what breaks a theory. One model call derives what the theory leads you to
    expect, code searches for it, and the sweep stops with the exact number of model reads stated."""
    from services.agent import disconfirm
    result = _call(db, lambda: disconfirm.create(db, case_id=case_id, theory_id=body.theory_id, requested_by=current_user))
    if result.get('created'):
        background.add_task(disconfirm.plan_in_background, UUID(result['id']))
    return result


@router.get("/{case_id}/proposals/disconfirm", dependencies=[Depends(require_case_view)])
def read_disconfirm(case_id: UUID, theory_id: UUID, db: Session = Depends(get_db)):
    """The theory's latest sweep (null when none has run), its counter-arguments, and the counts by what people
    decided, beside the red cell's."""
    from services.agent import disconfirm
    return _call(db, lambda: dict(sweep=disconfirm.latest_view(db, case_id=case_id, theory_id=theory_id),
                                  tally=disconfirm.tally(db, case_id, theory_id),
                                  counter_arguments=disconfirm.counter_arguments(db, case_id=case_id,
                                                                                 theory_id=theory_id)))


@router.post("/{case_id}/proposals/disconfirm/{sweep_id}/start", dependencies=[Depends(require_case_edit)])
def start_disconfirm(case_id: UUID, sweep_id: UUID, body: DisconfirmStart, background: BackgroundTasks,
                     db: Session = Depends(get_db)):
    """Start the reads the plan counted, or only the first ``limit`` of them, or the ones left after a stop."""
    from services.agent import disconfirm
    result = _call(db, lambda: disconfirm.start(db, case_id=case_id, sweep_id=sweep_id, limit=body.limit))
    if result['job_status'] == 'queued':
        background.add_task(disconfirm.read_in_background, UUID(result['id']))
    return result


@router.post("/{case_id}/proposals/disconfirm/{sweep_id}/stop", dependencies=[Depends(require_case_edit)])
def stop_disconfirm(case_id: UUID, sweep_id: UUID, db: Session = Depends(get_db)):
    from services.agent import disconfirm
    return _call(db, lambda: disconfirm.stop(db, case_id=case_id, sweep_id=sweep_id))


@router.get("/{case_id}/glossary", dependencies=[Depends(require_case_view)])
def list_glossary(case_id: UUID, db: Session = Depends(get_db)):
    """The code words a person confirmed, each with its mentions and the ledger rows they join to."""
    from services.agent import glossary
    return glossary.read(db.connection(), db, case_id)


@router.post("/{case_id}/glossary/{term_id}/withdraw", dependencies=[Depends(require_case_edit)])
@records('glossary_term_withdraw', 'set_aside', subject_type='glossary_term', subject=lambda c: c['kw'].get('term_id'))
def withdraw_glossary_term(case_id: UUID, term_id: UUID, body: Withdraw, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_db_user)):
    from services.agent import glossary
    try:
        return glossary.withdraw(db, case_id=case_id, term_id=term_id, reviewer=current_user, reason=body.reason)
    except glossary.GlossaryError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
