"""Start a Corroborate from any selection: what Loupe takes from it and which questions fit, and a pasted list
matched to the case (lx-corroselect). Read-only; every read is checked against the case in the path."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import require_case_view
from services import case_selections
from services.corroborate import pasted, preview

router = APIRouter(prefix="/api/cases", tags=["corroborate"])


class Member(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=512)
    label: str | None = Field(default=None, max_length=300)
    quote: str | None = Field(default=None, max_length=2000)


class PreviewRequest(BaseModel):
    members: list[Member] = Field(min_length=1, max_length=case_selections.MAX_MEMBERS)


@router.post("/{case_id}/corroborate/preview", dependencies=[Depends(require_case_view)])
def read_preview(case_id: UUID, request: PreviewRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return preview.preview(db, case_id, [m.model_dump(exclude_none=True) for m in request.members])
    except case_selections.SelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class ListRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


@router.post("/{case_id}/corroborate/match-list", dependencies=[Depends(require_case_view)])
def match_list(case_id: UUID, request: ListRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return pasted.match(db, case_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
