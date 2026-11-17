"""Corroborate: save a group of items from any screen, run the link analysis on it, read the result
(lx-overlaps). Writes need case edit; reads need case view. Every group and run is checked against the case in the path.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from services import case_selections
from services.relations import matrix, runs, together

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
    question: dict[str, Any] | None = None


@router.post("/{case_id}/relation-queries", dependencies=[Depends(require_case_edit)])
def create_query(case_id: UUID, request: QueryRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        group = runs.save_group(db, case_id=case_id, members=[m.model_dump(exclude_none=True) for m in request.members],
                                user=user, extends=str(request.extends) if request.extends else None, surface=request.surface,
                                question=request.question)
        run = runs.start(db, case_id=case_id, selection_id=group["id"], user=user) if request.run else None
    except case_selections.SelectionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return {"group": group, "run": run}


@router.get("/{case_id}/relation-overlaps", dependencies=[Depends(require_case_view)])
def read_overlaps(case_id: UUID, phones: str = Query(..., max_length=2000), from_: str | None = Query(None, alias="from"),
                  to: str | None = Query(None), parts: str | None = Query(None, max_length=100),
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    """Where two or more phones were together, the people they share and relay chains (lx-phonetogether B)."""
    try:
        return together.read(db, case_id, [p.strip() for p in phones.split(",")], from_, to,
                             [x.strip() for x in parts.split(",") if x.strip()] if parts else None)
    except together.TogetherError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


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


@router.get("/{case_id}/relation-runs/{run_id}/rows", dependencies=[Depends(require_case_view)])
def read_rows(case_id: UUID, run_id: UUID, section: str, offset: int = 0, limit: int = runs.PAGE,
              db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return runs.rows(db, case_id, str(run_id), section, offset, limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{case_id}/relation-runs/{run_id}", dependencies=[Depends(require_case_view)])
def read_run(case_id: UUID, run_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return runs.view(db, case_id, str(run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{case_id}/relation-queries/{selection_id}/trail", dependencies=[Depends(require_case_view)])
def read_trail(case_id: UUID, selection_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    from services.relations import trail
    out = trail.build(db, case_id, str(selection_id))
    if not out["steps"]:
        raise HTTPException(status_code=404, detail="That query is not in this case.")
    return out


@router.get("/{case_id}/relation-runs/{run_id}/lanes", dependencies=[Depends(require_case_view)])
def read_lanes(case_id: UUID, run_id: UUID, instance: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Story lanes for one instance of a Corroborate result: the records the grid cites for it, one lane per person."""
    from services.corroborate.store import CaseStore
    from services.relations import lanes
    result = runs.full_result(db, case_id, str(run_id))
    corroboration = (result or {}).get("corroboration")
    if not corroboration:
        raise HTTPException(status_code=404, detail="That run has no Corroborate result.")
    try:
        return lanes.build(CaseStore(db, case_id), corroboration, instance)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class AcceptRequest(BaseModel):
    entry_id: UUID
    relationship: str = Field(pattern="^(supports|contradicts)$")


@router.post("/{case_id}/relation-runs/{run_id}/hypotheses/{number}:accept", dependencies=[Depends(require_case_edit)])
def accept_hypothesis(case_id: UUID, run_id: UUID, number: int, request: AcceptRequest, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    from services.relations import hypotheses
    try:
        return hypotheses.accept(db, case_id=case_id, run_id=run_id, number=number, entry_id=request.entry_id,
                                 relationship=request.relationship, user=user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (hypotheses.HypothesisError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


class ReportRequest(BaseModel):
    privilege_marking: str = "unmarked"


@router.post("/{case_id}/relation-runs/{run_id}/report", dependencies=[Depends(require_case_view)])
def report(case_id: UUID, run_id: UUID, request: ReportRequest, db: Session = Depends(get_db),
           user: User = Depends(get_current_db_user)):
    from datetime import datetime
    from urllib.parse import quote

    from fastapi.responses import Response

    from postgres.models.case import Case
    from services.relations import report as R
    try:
        run = runs.view(db, case_id, str(run_id), with_result=False)
        run["result"] = runs.full_result(db, case_id, str(run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    group = case_selections.describe(db, case_id, run["selection_id"], member_limit=10**9)
    case = db.query(Case).filter(Case.id == case_id).first()
    lanes = None
    corroboration = (run["result"] or {}).get("corroboration")
    if corroboration:
        from services.corroborate.store import CaseStore
        from services.relations import lanes as L
        store, lanes = CaseStore(db, case_id), []
        for inst in corroboration["comparison"]["incident"] + corroboration["comparison"]["ordinary"]:
            try:
                lanes.append(L.build(store, corroboration, inst["id"]))
            except LookupError as exc:
                lanes.append({"instance": {"id": inst["id"], "label": inst["label"]}, "lanes": [], "error": str(exc)})
    try:
        content = R.render_pdf(case_name=case.title if case else "", generated_by=user.name or user.email,
                               group=group, run=run, privilege_marking=request.privilege_marking, lanes=lanes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    name = f"link-analysis-{datetime.now().strftime('%Y%m%d')}.pdf"
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"; filename*=UTF-8\'\'{quote(name)}'})
