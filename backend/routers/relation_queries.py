"""Look into how these relate: save a group of items from any screen, run the link analysis on it, read the result
(lx-overlaps). Writes need case edit; reads need case view. Every group and run is checked against the case in the path.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services import case_selections
from services.relations import matrix, runs

router = APIRouter(prefix="/api/cases", tags=["relation-queries"])


class Member(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=512)
    label: str | None = Field(default=None, max_length=300)
    quote: str | None = Field(default=None, max_length=2000)


class QueryRequest(BaseModel):
    members: list[Member] = Field(min_length=1, max_length=case_selections.MAX_MEMBERS)
    extends: UUID | None = None
    surface: str = Field(default="relation", max_length=40)
    run: bool = True


@router.post("/{case_id}/relation-queries", dependencies=[Depends(require_case_edit)])
def create_query(case_id: UUID, request: QueryRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        group = runs.save_group(db, case_id=case_id, members=[m.model_dump(exclude_none=True) for m in request.members],
                                user=user, extends=str(request.extends) if request.extends else None, surface=request.surface)
        run = runs.start(db, case_id=case_id, selection_id=group["id"], user=user) if request.run else None
    except case_selections.SelectionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return {"group": group, "run": run}


@router.get("/{case_id}/relation-queries/matrix", dependencies=[Depends(require_case_view)])
def read_matrix(case_id: UUID) -> dict[str, Any]:
    return {"types": matrix.TYPES, "analyses": {k: {x: v[x] for x in ("title", "key", "existing", "base")}
                                                 for k, v in matrix.ANALYSES.items()}, "cells": matrix.table()}


@router.get("/{case_id}/relation-queries/{selection_id}", dependencies=[Depends(require_case_view)])
def read_query(case_id: UUID, selection_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    group = case_selections.describe(db, case_id, str(selection_id), member_limit=10**9)
    if group is None or group["group_type"] != "relation_query":
        raise HTTPException(status_code=404, detail="That query is not in this case.")
    run_id = runs.latest_for(db, case_id, selection_id)
    return {"group": group, "run": runs.view(db, case_id, run_id) if run_id else None}


@router.post("/{case_id}/relation-queries/{selection_id}/runs", dependencies=[Depends(require_case_edit)])
def rerun(case_id: UUID, selection_id: UUID, db: Session = Depends(get_db),
          user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return runs.start(db, case_id=case_id, selection_id=str(selection_id), user=user)
    except case_selections.SelectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{case_id}/relation-runs/{run_id}", dependencies=[Depends(require_case_view)])
def read_run(case_id: UUID, run_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return runs.view(db, case_id, str(run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
