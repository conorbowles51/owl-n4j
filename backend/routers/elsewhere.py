"""Elsewhere in the case, prefix ``/api/cases`` (``services.elsewhere``).

``GET /{case_id}/elsewhere/record/{record_uid}``: what the other phones, the financial records, the documents and
the case timeline hold about one phone record. ``POST /{case_id}/elsewhere/statement``: the same for a statement
(people, period, places, amounts, check numbers, account endings, cited records). ``part`` asks for one source, so
a screen can fill each as it arrives; without it every source is checked in one response. Anyone who can view the
case may ask; nothing is written and no model is called. A record of another case is 404 (ids do not leak).
"""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services.elsewhere import service, subject as S
from services.elsewhere import words as W

router = APIRouter(prefix="/api/cases", tags=["elsewhere"])
Part = Literal["phones", "financial", "documents", "timeline"]


class PersonIn(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    numbers: List[str] = Field(default_factory=list, max_length=10)
    emails: List[str] = Field(default_factory=list, max_length=10)


class PeriodIn(BaseModel):
    start: Optional[str] = Field(None, max_length=32)
    end: Optional[str] = Field(None, max_length=32)


class AmountIn(BaseModel):
    minor: int = Field(..., ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)


class PlaceIn(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    radius_m: Optional[float] = Field(None, gt=0, le=100000)


class StatementIn(BaseModel):
    text: Optional[str] = Field(None, max_length=4000)
    record_uids: List[UUID] = Field(default_factory=list, max_length=S.MAX_RECORDS)
    people: List[PersonIn] = Field(default_factory=list, max_length=20)
    period: Optional[PeriodIn] = None
    amounts: List[AmountIn] = Field(default_factory=list, max_length=20)
    places: List[PlaceIn] = Field(default_factory=list, max_length=10)
    references: List[str] = Field(default_factory=list, max_length=20)
    accounts: List[str] = Field(default_factory=list, max_length=10)


def _zone(db, case_id):
    from services.phone import streams
    return streams.case_zone(db.connection(), str(case_id))["name"]


def _parts(part):
    return (part,) if part else W.PARTS


@router.get("/{case_id}/elsewhere/record/{record_uid}")
def elsewhere_record(case_id: UUID, record_uid: UUID, part: Optional[Part] = Query(None),
                     db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    conn = db.connection()
    try:
        subj = S.from_record(conn, str(case_id), str(record_uid))
    except S.NotFound:
        raise HTTPException(status_code=404, detail="This record is not in this case.")
    return service.run(conn, str(case_id), subj, _parts(part), _zone(db, case_id))


@router.post("/{case_id}/elsewhere/statement")
def elsewhere_statement(case_id: UUID, body: StatementIn, part: Optional[Part] = Query(None),
                        db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    conn = db.connection()
    payload = body.model_dump()
    payload["record_uids"] = [str(u) for u in body.record_uids]
    try:
        subj = S.from_statement(conn, str(case_id), payload)
    except S.NotFound:
        raise HTTPException(status_code=404, detail="A cited record is not in this case.")
    except S.BadSubject as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return service.run(conn, str(case_id), subj, _parts(part), _zone(db, case_id))
