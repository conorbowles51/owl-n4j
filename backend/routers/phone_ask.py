"""Ask the phones a question (lx-phoneask, phones redesign screen 7). Asking and reading need case view: a question
reads the case and keeps only the question and its answer. Every id is checked against the case in the path."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_view
from routers.users import get_current_db_user
from services.phone import ask_runs

router = APIRouter(prefix="/api/cases", tags=["phone-ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=ask_runs.MAX_QUESTION)
    phones: list[UUID] | None = Field(default=None, max_length=200)


@router.post("/{case_id}/phones/ask", dependencies=[Depends(require_case_view)])
def ask_phones(case_id: UUID, request: AskRequest, db: Session = Depends(get_db),
               user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    """Start answering the question over the phones asked for (default: every phone in the case)."""
    try:
        return ask_runs.start(db, case_id=case_id, question=request.question,
                              phones=[str(p) for p in request.phones] if request.phones else None, user=user)
    except ask_runs.AskError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/{case_id}/phones/ask", dependencies=[Depends(require_case_view)])
def earlier_questions(case_id: UUID, offset: int = Query(0, ge=0), limit: int = Query(ask_runs.LIST_LIMIT, ge=1, le=100),
                      db: Session = Depends(get_db)) -> dict[str, Any]:
    return ask_runs.earlier(db, case_id, offset=offset, limit=limit)


@router.get("/{case_id}/phones/ask/{ask_id}", dependencies=[Depends(require_case_view)])
def read_question(case_id: UUID, ask_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    got = ask_runs.read(db, case_id, ask_id)
    if got is None:
        raise HTTPException(status_code=404, detail="That question is not in this case.")
    return got
