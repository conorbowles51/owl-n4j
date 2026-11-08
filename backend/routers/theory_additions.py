"""Add anything in a case to a theory, singly or as a group, and let each addition explain itself (lx-theorybuild).

Routes over services.theory_additions: add (or start a new theory from) an item or a group; read the theory as a
whole; view one addition through its Loupe; write, infer and confirm narratives. Writes need case edit; reads need
case view. Every group and narrative is checked against the case in the path.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres import link_types
from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user
from routers.workspace_entries import _raise_entry_error
from services import case_selections, theory_additions as T

router = APIRouter(prefix="/api/workspace", tags=["theory-additions"])

Surface = Literal[tuple(T.SURFACES)]  # type: ignore[valid-type]
GroupType = Literal[link_types.GROUP_TYPES]  # type: ignore[valid-type]
LinkTargetType = Literal[link_types.WORKSPACE_TYPES]  # type: ignore[valid-type]
Relationship = Literal["unclassified", "supports", "contradicts", "context"]


class ItemInput(BaseModel):
    target_type: LinkTargetType
    target_id: str = Field(min_length=1, max_length=512)
    target_label: str | None = Field(default=None, max_length=512)
    source_anchor: dict[str, Any] = Field(default_factory=dict)


class MemberInput(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    id: str = Field(min_length=1, max_length=512)
    label: str | None = Field(default=None, max_length=300)


class GroupInput(BaseModel):
    group_type: GroupType
    # Every member is sent; a group larger than the service's limit is refused with that number, never cut.
    members: list[MemberInput] = Field(min_length=1, max_length=case_selections.MAX_MEMBERS)
    how: dict[str, Any] = Field(default_factory=dict)
    words: str = Field(min_length=1, max_length=case_selections.MAX_WORDS)


class AdditionRequest(BaseModel):
    surface: Surface
    why: str | None = Field(default=None, max_length=T.MAX_WHY)
    items: list[ItemInput] | None = Field(default=None, max_length=500)
    group: GroupInput | None = None
    narrative: str | None = Field(default=None, max_length=T.MAX_NARRATIVE)
    relationship: Relationship = "unclassified"


class NewTheoryRequest(AdditionRequest):
    title: str = Field(min_length=1, max_length=300)
    statement: str | None = Field(default=None, max_length=20000)


class NarrativeRequest(BaseModel):
    link_id: UUID | None = None
    text: str = Field(min_length=1, max_length=T.MAX_NARRATIVE)


class InferRequest(BaseModel):
    link_id: UUID | None = None


def _raise(db: Session, exc: Exception):
    if isinstance(exc, T.AdditionError):
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _raise_entry_error(db, exc)


def _addition_kwargs(request: AdditionRequest) -> dict[str, Any]:
    return dict(surface=request.surface, why=request.why, relationship=request.relationship,
                narrative=request.narrative,
                items=[i.model_dump() for i in request.items] if request.items else None,
                group=request.group.model_dump() if request.group else None)


@router.post("/{case_id}/entries/{entry_id}/additions", dependencies=[Depends(require_case_edit)])
def add_to_entry(case_id: UUID, entry_id: UUID, request: AdditionRequest, db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)):
    """Add one item, several, or a group to a theory (or finding, or note), each knowing why it was chosen."""
    try:
        return T.add(db, case_id=case_id, entry_id=entry_id, user=user, **_addition_kwargs(request))
    except Exception as exc:  # noqa: BLE001 - mapped to the person's words
        _raise(db, exc)


@router.post("/{case_id}/theories:from", dependencies=[Depends(require_case_edit)])
def new_theory_from(case_id: UUID, request: NewTheoryRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """A new theory built from this item or group."""
    try:
        return T.new_theory(db, case_id=case_id, user=user, title=request.title, statement=request.statement,
                            **_addition_kwargs(request))
    except Exception as exc:  # noqa: BLE001
        _raise(db, exc)


@router.get("/{case_id}/entries/{entry_id}/reading", dependencies=[Depends(require_case_view)])
def read_entry(case_id: UUID, entry_id: UUID, db: Session = Depends(get_db)):
    try:
        return T.reading(db, case_id=case_id, entry_id=entry_id)
    except Exception as exc:  # noqa: BLE001
        _raise(db, exc)


@router.get("/{case_id}/entries/{entry_id}/additions/{link_id}", dependencies=[Depends(require_case_view)])
def view_through_loupe(case_id: UUID, entry_id: UUID, link_id: UUID,
                       member_limit: int = Query(2000, ge=1, le=case_selections.MAX_MEMBERS),
                       db: Session = Depends(get_db)):
    try:
        return T.loupe(db, case_id=case_id, entry_id=entry_id, link_id=link_id, member_limit=member_limit)
    except Exception as exc:  # noqa: BLE001
        _raise(db, exc)


@router.post("/{case_id}/entries/{entry_id}/narratives", dependencies=[Depends(require_case_edit)])
def write_narrative(case_id: UUID, entry_id: UUID, request: NarrativeRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    try:
        return T.write_narrative(db, case_id=case_id, entry_id=entry_id, link_id=request.link_id, text=request.text,
                                 user=user)
    except Exception as exc:  # noqa: BLE001
        _raise(db, exc)


@router.post("/{case_id}/entries/{entry_id}/narratives:infer", dependencies=[Depends(require_case_edit)])
def infer_narrative(case_id: UUID, entry_id: UUID, request: InferRequest, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """The model's reading, with citations to the members it was given; saved as a model reading, unconfirmed."""
    try:
        return T.infer_narrative(db, case_id=case_id, entry_id=entry_id, link_id=request.link_id, user=user)
    except Exception as exc:  # noqa: BLE001
        _raise(db, exc)


@router.post("/{case_id}/entries/{entry_id}/narratives/{narrative_id}:confirm",
             dependencies=[Depends(require_case_edit)])
def confirm_narrative(case_id: UUID, entry_id: UUID, narrative_id: UUID, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    try:
        return T.confirm_narrative(db, case_id=case_id, entry_id=entry_id, narrative_id=narrative_id, user=user)
    except Exception as exc:  # noqa: BLE001
        _raise(db, exc)


@router.get("/{case_id}/selections/{selection_id}", dependencies=[Depends(require_case_view)])
def describe_selection(case_id: UUID, selection_id: UUID,
                       member_limit: int = Query(2000, ge=1, le=case_selections.MAX_MEMBERS),
                       db: Session = Depends(get_db)):
    found = case_selections.describe(db, case_id, selection_id, member_limit=member_limit)
    if found is None:
        raise HTTPException(status_code=404, detail="That group was not found in this case")
    return found
