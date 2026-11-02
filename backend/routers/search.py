"""Loupe-wide search, prefix ``/api/search`` (03 section 11.4). Anyone who can view the case."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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
        return S.search(db.connection(), case_id, q, exact=exact, groups=wanted, phones=_phones(phones), start=start,
                        end=end)
    except S.SearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


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
