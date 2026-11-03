"""The case agent's drafted Workspace work, held for a person to decide (agent-proposals B, C).

Listing needs ``case:view``; opening a cited source, accepting and rejecting need ``case:edit``. Accepting creates
the Workspace work under the person, carrying the model origin; what the person opened first is recorded.
"""
from __future__ import annotations

from datetime import date, datetime
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

router = APIRouter(prefix="/api/workspace", tags=["agent-proposals"])


class Opened(BaseModel):
    citation: str = Field(..., min_length=1, max_length=600)


class Accept(BaseModel):
    via: Literal['ui', 'api'] = 'api'
    due_at: datetime | date | None = None
    title: str | None = Field(default=None, max_length=255)
    body: str | None = Field(default=None, max_length=8000)


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
                                    due_at=body.due_at, edits=dict(title=body.title, body=body.body)))


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
