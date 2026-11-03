"""Loupe-wide search, prefix ``/api/search`` (03 section 11.4). Anyone who can view the case."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services.search import search as S

router = APIRouter(prefix="/api/search", tags=["search"])


def _phones(phones):
    return [p for p in (phones or "").split(",") if p] or None


@router.get("")
def search(case_id: UUID = Query(...), q: str = Query(..., max_length=500), exact: bool = False,
           groups: Optional[str] = None, phones: Optional[str] = None, start: Optional[str] = Query(None, alias="from"),
           end: Optional[str] = Query(None, alias="to"), db: Session = Depends(get_db),
           user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    wanted = tuple(g for g in (groups or "").split(",") if g) or S.GROUPS
    try:
        out = S.search(db.connection(), case_id, q, exact=exact, groups=wanted, phones=_phones(phones), start=start,
                       end=end)
    except S.SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # searches run, for the phone review coverage summary (07 J-13 step 6); a failed record never fails the search
    from services.phone import review_share
    review_share.record_search(db, case_id, user, q, exact=exact, surface="search",
                               hits=sum(int(g.get("total") or 0) for g in out.get("groups") or []))
    return out


@router.get("/group")
def search_group(case_id: UUID = Query(...), q: str = Query(..., max_length=500), group: str = Query(...),
                 cursor: Optional[str] = None, limit: int = 200, exact: bool = False, phones: Optional[str] = None,
                 start: Optional[str] = Query(None, alias="from"), end: Optional[str] = Query(None, alias="to"),
                 db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    if cursor is not None and not cursor.isdigit():
        raise HTTPException(status_code=422, detail="That page marker is not one this search gave.")
    try:
        return S.group_page(db.connection(), case_id, q, group, cursor=cursor, limit=limit, exact=exact,
                            phones=_phones(phones), start=start, end=end)
    except S.SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ---- Saved keyword lists (03 section 11.2; 07 J-6, section 14) -----------------------------------------------------

class KeywordListRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    name: str = Field(min_length=1, max_length=240)
    terms: List[str] = Field(min_length=1, max_length=200)
    exact: bool = False
    note: Optional[str] = Field(default=None, max_length=4000)


class AttachTheoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    theory_id: UUID


@router.get("/keyword-lists")
def keyword_lists(case_id: UUID = Query(...), theory: Optional[UUID] = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    """The case's keyword lists with their last run; ``theory`` gives the lists attached to that theory."""
    from services.search import keyword_lists as K
    authorize_case(db, case_id, user, ("case", "view"))
    return K.list_for_case(db.connection(), case_id, theory=theory)


@router.post("/keyword-lists")
def save_keyword_list(body: KeywordListRequest, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    """Save a search as a keyword list: a Workspace note and the terms it runs on every phone of the case."""
    from routers.case_access import authorize_case_edit
    from services.search import keyword_lists as K
    from services.workspace_entry_service import WorkspaceEntryValidationError
    authorize_case_edit(db, body.case_id, user)
    try:
        return K.create(db, body.case_id, user, name=body.name, terms=body.terms, exact=body.exact, note=body.note)
    except K.KeywordListError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    except WorkspaceEntryValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/keyword-lists/{entry_id}")
def keyword_list(entry_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)):
    from services.search import keyword_lists as K
    authorize_case(db, case_id, user, ("case", "view"))
    out = K.get(db.connection(), case_id, entry_id)
    if out is None:
        raise HTTPException(status_code=404, detail="That keyword list is not in this case.")
    return out


@router.post("/keyword-lists/{entry_id}/theories")
def attach_keyword_list(entry_id: UUID, body: AttachTheoryRequest, db: Session = Depends(get_db),
                        user: User = Depends(get_current_db_user)):
    """Attach the list to a theory (07 section 14): a Workspace link from the theory to the list's note."""
    from routers.case_access import authorize_case_edit
    from services.search import keyword_lists as K
    from services.workspace_entry_service import WorkspaceEntryConflict, WorkspaceEntryNotFound
    authorize_case_edit(db, body.case_id, user)
    try:
        return K.attach_theory(db, body.case_id, entry_id, body.theory_id, user)
    except K.KeywordListError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    except WorkspaceEntryNotFound:
        db.rollback()
        raise HTTPException(status_code=404, detail="That theory is not in this case.")
    except WorkspaceEntryConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
