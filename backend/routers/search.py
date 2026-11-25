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


@router.get("/meaning")
def search_meaning(case_id: UUID = Query(...), q: str = Query(..., min_length=1, max_length=500),
                   areas: Optional[str] = None, phones: Optional[str] = None, person: Optional[str] = None,
                   start: Optional[str] = Query(None, alias="from"), end: Optional[str] = Query(None, alias="to"),
                   offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db),
                   user: User = Depends(get_current_db_user)):
    """The case search (lx-casesearch; ``services.case_search``): meaning and words together across every kind of
    case material, each hit scored against the question with a grade and a reason, best first, counted and paged.
    The fields the Search dialog read before (``hits[].snippet``, ``matched``, ``areas_searched``) are kept."""
    authorize_case(db, case_id, user, ("case", "view"))
    from datetime import date
    from services import case_search
    from services.agent.phone_tools import _phone_ids
    try:
        a = date.fromisoformat(start) if start else None
        b = date.fromisoformat(end) if end else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates are written YYYY-MM-DD.")
    ext_ids, unknown = _phone_ids(db.connection(), case_id, _phones(phones) or [])
    if unknown:
        raise HTTPException(status_code=422, detail="There is no phone %s in this case." % ", ".join(unknown))
    wanted = [x for x in (areas or "").split(",") if x]
    from services.agent.phone_cross_tools import _AREA_KIND
    kinds = tuple(dict.fromkeys(_AREA_KIND[x] for x in wanted if x in _AREA_KIND)) or None
    # the dialog searches as a person types: the ranking model scores the hits, other phrasings are not asked for
    res = case_search.search(db.connection(), case_id, q, kinds=kinds, areas=wanted or None,
                             phone=(ext_ids[0] if ext_ids else None), person=person, date_from=a, date_to=b,
                             offset=offset, limit=limit, phrase=False)
    return search_page_result(res)


def search_page_result(res: dict) -> dict:
    """The case search result with the Search dialog's older fields beside the shared shape."""
    hits = []
    for h in res["hits"]:
        how = {s.split(" (")[0] for s in h.get("matched") or []}
        by_meaning = bool(how & {"meaning", "graph meaning"})
        by_words = bool(how - {"meaning", "graph meaning"})
        hits.append({**h, "key": "%s:%s" % (h["area"], h["n"]) if not h.get("cite") else h["cite"],
                     "snippet": " ".join((h.get("text") or "").split())[:400],
                     "matched": "both" if by_meaning and by_words else "meaning" if by_meaning else "words",
                     "sources": h.get("matched") or [], "as_read": h.get("read_by_a_model", False)})
    return {**{k: v for k, v in res.items() if k != "hits"}, "query": res.get("question", ""), "hits": hits,
            "areas_searched": res.get("searched") or []}


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


# ---- Search every phone (Phones screen 2) ---------------------------------------------------------------------------

@router.get("/phones")
def search_phones(case_id: UUID = Query(...), q: str = Query(..., max_length=500), exact: bool = False,
                  phones: Optional[str] = None, start: Optional[str] = Query(None, alias="from"),
                  end: Optional[str] = Query(None, alias="to"), db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    """Every part of every phone in scope: counts by kind and phone, the first hits of each kind, people saved
    differently on each phone, and next steps (services/search/phone_search.py)."""
    authorize_case(db, case_id, user, ("case", "view"))
    from services.search import phone_search as P
    try:
        out = P.phone_search(db.connection(), case_id, q, exact=exact, phones=_phones(phones), start=start, end=end)
    except P.PhoneSearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.phone import review_share
    review_share.record_search(db, case_id, user, q, exact=exact, surface="phone_search", hits=int(out["total"]))
    return out


@router.get("/phones/kind")
def search_phones_kind(case_id: UUID = Query(...), q: str = Query(..., max_length=500), kind: str = Query(...),
                       cursor: Optional[str] = None, limit: int = 200, exact: bool = False,
                       phones: Optional[str] = None, start: Optional[str] = Query(None, alias="from"),
                       end: Optional[str] = Query(None, alias="to"), db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    if cursor is not None and not cursor.isdigit():
        raise HTTPException(status_code=422, detail="That page marker is not one this search gave.")
    from services.search import phone_search as P
    try:
        return P.kind_page(db.connection(), case_id, q, kind, cursor=cursor, limit=limit, exact=exact,
                           phones=_phones(phones), start=start, end=end)
    except P.PhoneSearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/phones/elsewhere")
def search_phones_elsewhere(case_id: UUID = Query(...), q: str = Query(..., max_length=500), exact: bool = False,
                            db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The same words in the case's documents and payments, and the corroborate step, asked after the first results
    because it reads every document text of the case."""
    authorize_case(db, case_id, user, ("case", "view"))
    from services.search import phone_search as P
    try:
        return P.elsewhere_step(db.connection(), case_id, q, exact=exact)
    except P.PhoneSearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/phones/context")
def search_phones_context(case_id: UUID = Query(...), event_uid: UUID = Query(...), db: Session = Depends(get_db),
                          user: User = Depends(get_current_db_user)):
    """A message, call or email hit with the messages around it in its thread, on its day."""
    authorize_case(db, case_id, user, ("case", "view"))
    from services.search import phone_search as P
    try:
        return P.hit_context(db.connection(), case_id, event_uid)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


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


class GroupSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    q: str = Field(min_length=1, max_length=500)
    group: str = Field(min_length=1, max_length=40)
    exact: bool = False
    phones: list[str] = Field(default_factory=list, max_length=200)


@router.post("/group/selection")
def freeze_search_group(body: GroupSelection, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Keep a whole search group as one selection for Add to… (07 J-5), with its counts. Needs edit access, because it
    is made to be added somewhere."""
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return S.freeze_group(db, user, body.case_id, body.q, body.group, exact=body.exact, phones=body.phones or None)
    except (S.SearchError, ValueError, KeyError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


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
