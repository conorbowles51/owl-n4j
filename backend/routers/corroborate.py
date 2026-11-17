"""Corroborate. Starting one from any selection: what Loupe takes from it and which questions fit, and a pasted list
matched to the case (lx-corroselect). Running the question, case facts, Keep watching and a document's dated rows
(lx-corroengine). Reads need case view; writes need case edit. Every id is checked against the case in the path. The
run goes through the relation-queries runner (one engine, one result row): its result carries ``corroboration``
beside the link analysis."""
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
from services.corroborate import area, facts, pasted, preview, questions, subsets
from services.corroborate import scope as scope_rules
from services.relations import runs

router = APIRouter(prefix="/api/cases", tags=["corroborate"])


class Member(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=512)
    label: str | None = Field(default=None, max_length=300)
    quote: str | None = Field(default=None, max_length=2000)


class PreviewRequest(BaseModel):
    members: list[Member] = Field(min_length=1, max_length=case_selections.MAX_MEMBERS)
    scope: dict[str, Any] | None = None


@router.post("/{case_id}/corroborate/preview", dependencies=[Depends(require_case_view)])
def read_preview(case_id: UUID, request: PreviewRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    from services.corroborate.store import CaseStore
    members = [m.model_dump(exclude_none=True) for m in request.members]
    try:
        composed = preview.preview(db, case_id, members, scope=request.scope)
    except (case_selections.SelectionError, scope_rules.ScopeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    kept = (composed.get("scope") or {}).get("kept")
    return questions.enrich(CaseStore(db, case_id), kept if kept is not None else members, composed)


class ListRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)


@router.post("/{case_id}/corroborate/match-list", dependencies=[Depends(require_case_view)])
def match_list(case_id: UUID, request: ListRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return pasted.match(db, case_id, request.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class AreaRequest(BaseModel):
    areas: list[list[list[float]]] = Field(min_length=1, max_length=50)


@router.post("/{case_id}/corroborate/area", dependencies=[Depends(require_case_view)])
def read_area(case_id: UUID, request: AreaRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Every phone position, photo and place inside the drawn areas, as members of a selection."""
    try:
        return area.members_in_areas(db.connection(), case_id, request.areas)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{case_id}/corroborate/document-rows/{file_id}", dependencies=[Depends(require_case_view)])
def document_rows(case_id: UUID, file_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """A document's dated rows (a badge log's lines), each a member of type ``document_row`` with id
    ``<file id>:<index>``, so a selection can hold single rows rather than the whole file."""
    from services.corroborate import model as M
    from services.corroborate.store import CaseStore
    store = CaseStore(db, case_id)
    rows = store.document_rows(str(file_id))
    names = {p["key"]: p["label"] for p in store.people()}
    return {"zone": store.zone(), "rows": [
        {"member": {"type": "document_row", "id": f"{file_id}:{r['index']}", "label": r["text"][:120]},
         "index": r["index"], "at": M.iso(r["at"]), "text": r["text"], "people": [names.get(k, k) for k in r["parties"]]}
        for r in rows]}


class Question(BaseModel):
    kind: str | None = Field(default=None, max_length=40)
    text: str | None = Field(default=None, max_length=500)
    chips: dict[str, Any] = Field(default_factory=dict)


class RunRequest(BaseModel):
    members: list[Member] = Field(min_length=1, max_length=case_selections.MAX_MEMBERS)
    question: Question = Field(default_factory=Question)
    surface: str = Field(default="corroborate", max_length=40)
    extends: UUID | None = None


@router.post("/{case_id}/corroborate/run", dependencies=[Depends(require_case_edit)])
def run(case_id: UUID, request: RunRequest, db: Session = Depends(get_db),
        user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    kind = request.question.kind
    if kind is not None and questions.canonical(kind) is None:
        raise HTTPException(status_code=422, detail="That question is not one Corroborate asks.")
    try:
        group = runs.save_group(db, case_id=case_id, members=[m.model_dump(exclude_none=True) for m in request.members],
                                user=user, extends=str(request.extends) if request.extends else None,
                                surface=request.surface, question=request.question.model_dump())
        started = runs.start(db, case_id=case_id, selection_id=group["id"], user=user)
    except case_selections.SelectionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    return {"group": group, "run": started}


class FactRequest(BaseModel):
    kind: str = Field(max_length=32)
    text: str = Field(min_length=1, max_length=500)
    people: list[str] = Field(default_factory=list, max_length=50)
    phrase: str | None = Field(default=None, max_length=300)
    run_id: UUID | None = None


@router.get("/{case_id}/corroborate/facts", dependencies=[Depends(require_case_view)])
def list_facts(case_id: UUID, include_withdrawn: bool = False, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"facts": facts.list_facts(db, case_id, include_withdrawn=include_withdrawn)}


@router.post("/{case_id}/corroborate/facts", dependencies=[Depends(require_case_edit)])
def add_fact(case_id: UUID, request: FactRequest, db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return facts.add_fact(db, case_id=case_id, kind=request.kind, text_=request.text, people=request.people,
                              phrase=request.phrase, user=user, run_id=request.run_id)
    except facts.FactError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{case_id}/corroborate/facts/{fact_id}:withdraw", dependencies=[Depends(require_case_edit)])
def withdraw_fact(case_id: UUID, fact_id: UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return facts.withdraw_fact(db, case_id=case_id, fact_id=fact_id, user=user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class WatchRequest(BaseModel):
    run_id: UUID


@router.post("/{case_id}/corroborate/watches", dependencies=[Depends(require_case_edit)])
def keep_watching(case_id: UUID, request: WatchRequest, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        run_view = runs.view(db, case_id, str(request.run_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    corro = (run_view.get("result") or {}).get("corroboration")
    if not corro:
        raise HTTPException(status_code=422, detail="That run has no Corroborate result to watch yet.")
    q = corro.get("question") or {}
    return facts.watch(db, case_id=case_id, selection_id=run_view["selection_id"],
                       question={"kind": q.get("kind"), "chips": {k: v for k, v in (q.get("chips") or {}).items()
                                                                   if k not in ("when",)}},
                       level=corro.get("level") or {}, user=user)


@router.get("/{case_id}/corroborate/watches", dependencies=[Depends(require_case_view)])
def watches(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The case's watched results, each re-checked first when the case's material changed since its last check."""
    return {"watches": facts.recheck(db, case_id)}


@router.post("/{case_id}/corroborate/watches/{watch_id}:seen", dependencies=[Depends(require_case_view)])
def watch_seen(case_id: UUID, watch_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return facts.mark_seen(db, case_id, watch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{case_id}/corroborate/watches/{watch_id}:stop", dependencies=[Depends(require_case_edit)])
def watch_stop(case_id: UUID, watch_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return facts.stop(db, case_id, watch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class SubsetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    members: list[Member] = Field(min_length=1, max_length=case_selections.MAX_MEMBERS)


@router.get("/{case_id}/corroborate/subsets", dependencies=[Depends(require_case_view)])
def list_subsets(case_id: UUID, db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"subsets": subsets.listing(db, case_id)}


@router.post("/{case_id}/corroborate/subsets", dependencies=[Depends(require_case_edit)])
def save_subset(case_id: UUID, request: SubsetRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)) -> dict[str, Any]:
    try:
        return subsets.save(db, case_id=case_id, name=request.name, members=[m.model_dump(exclude_none=True) for m in request.members], user=user)
    except case_selections.SelectionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


class CombineRequest(BaseModel):
    first: UUID
    second: UUID
    op: str


@router.post("/{case_id}/corroborate/subsets/combine", dependencies=[Depends(require_case_view)])
def combine_subsets(case_id: UUID, request: CombineRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return subsets.combine(db, case_id, str(request.first), str(request.second), request.op)
    except case_selections.SelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
