"""Production numbers (Bates numbers), prefix ``/api/production-numbers``. Reading needs view access to the case;
issuing, entering, confirming, withdrawing and stamping need the right to add evidence."""
from __future__ import annotations

from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services import activity_trail, production_numbers as P

router = APIRouter(prefix="/api/production-numbers", tags=["production-numbers"])

VIEW = ("case", "view")
WRITE = ("evidence", "upload")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


class SetRequest(Strict):
    name: str = Field(min_length=1, max_length=120)
    prefix: str = Field(min_length=1, max_length=32)
    start: int = Field(default=1, ge=0)
    padding: int = Field(default=6, ge=1, le=12)


class AssignRequest(Strict):
    file_ids: List[UUID] = Field(min_length=1)
    level: Literal["page", "file"] = "page"


class WithdrawRequest(Strict):
    reason: str = Field(min_length=1, max_length=2000)


class ReceivedRequest(Strict):
    evidence_file_id: UUID
    first: str = Field(min_length=1, max_length=64)
    last: Optional[str] = Field(default=None, max_length=64)


class SuggestionRequest(Strict):
    evidence_file_id: UUID
    first_text: str = Field(min_length=1, max_length=64)
    last_text: str = Field(min_length=1, max_length=64)
    confirm: bool


class ImportRequest(Strict):
    content: str = Field(min_length=1, max_length=8_000_000)


class WithdrawReceivedRequest(Strict):
    note: Optional[str] = Field(default=None, max_length=2000)


class CaseOnly(Strict):
    pass


def _refused(exc: P.ProductionNumberError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _saved(db: Session, user: User, case_id: UUID, action: str, **details) -> None:
    activity_trail.record(action, db=db, user=user, case_id=case_id, details=details)
    db.commit()


@router.get("")
def overview(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Every set and every file's numbers, once for the whole case: the Evidence list joins this to its rows."""
    authorize_case(db, case_id, user, VIEW)
    return {"sets": [P.set_view(row) for row in P.list_sets(db, case_id)], **P.case_numbers(db, case_id)}


@router.get("/file/{evidence_file_id}")
def one_file(evidence_file_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, VIEW)
    try:
        numbers = P.file_numbers(db, case_id, evidence_file_id)
    except P.ProductionNumberError as exc:
        raise _refused(exc) from exc
    ids = [item["id"] for item in numbers["assigned"]]
    copies = [P.stamped_view(row) for row in P.stamped_copies(db, case_id) if str(row.assignment_id) in ids]
    return {**numbers, "stamped_copies": copies}


@router.get("/find")
def find(case_id: UUID = Query(...), q: str = Query(..., min_length=1, max_length=130), db: Session = Depends(get_db),
         user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, VIEW)
    return P.find_number(db, case_id, q)


@router.post("/sets")
def create_set(body: SetRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        row = P.create_set(db, body.case_id, name=body.name, prefix=body.prefix, start=body.start, padding=body.padding,
                           user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "production_set_created", set_id=str(row.id), prefix=row.prefix)
    return P.set_view(row)


@router.post("/sets/{set_id}/assign")
def assign(set_id: UUID, body: AssignRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        out = P.assign(db, body.case_id, set_id, body.file_ids, level=body.level, user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "production_numbers_assigned", set_id=str(set_id), issued=len(out["issued"]),
           skipped=len(out["skipped"]), ranges=[item["text"] for item in out["issued"]][:200])
    return out


@router.post("/assignments/{assignment_id}/withdraw")
def withdraw(assignment_id: UUID, body: WithdrawRequest, db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        row = P.withdraw_assignment(db, body.case_id, assignment_id, reason=body.reason, user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "production_number_withdrawn", assignment_id=str(row.id), reason=body.reason)
    return {"id": str(row.id), "withdrawn": True}


@router.post("/assignments/{assignment_id}/stamped-copy")
def stamp(assignment_id: UUID, body: CaseOnly, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        row = P.stamp_copy(db, body.case_id, assignment_id, user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "production_copy_stamped", copy_id=str(row.id), sha256=row.sha256,
           source_sha256=row.source_sha256)
    return P.stamped_view(row)


@router.get("/stamped-copies/{copy_id}/file")
def stamped_file(copy_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, VIEW)
    try:
        row, path = P.stamped_path(db, case_id, copy_id)
    except P.ProductionNumberError as exc:
        raise _refused(exc) from exc
    return FileResponse(path, media_type="application/pdf", filename=row.file_name)


@router.post("/received")
def enter_received(body: ReceivedRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        row = P.enter_received(db, body.case_id, body.evidence_file_id, first=body.first, last=body.last, user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "received_number_entered", evidence_file_id=str(body.evidence_file_id),
           range=P.range_text(row.first_text, row.last_text))
    return P.received_view(row)


@router.post("/received/import")
def import_received(body: ImportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        out = P.import_received(db, body.case_id, body.content, user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "received_numbers_imported", imported=len(out["imported"]),
           problems=len(out["problems"]))
    return out


@router.post("/suggestions/decide")
def decide(body: SuggestionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        row = P.decide_suggestion(db, body.case_id, body.evidence_file_id, first_text=body.first_text,
                                  last_text=body.last_text, confirm=body.confirm, user=user)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "received_number_confirmed" if body.confirm else "received_number_rejected",
           evidence_file_id=str(body.evidence_file_id), range=P.range_text(row.first_text, row.last_text))
    return P.received_view(row)


@router.post("/received/{row_id}/withdraw")
def withdraw_received(row_id: UUID, body: WithdrawReceivedRequest, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, WRITE)
    try:
        row = P.withdraw_received(db, body.case_id, row_id, user=user, note=body.note)
    except P.ProductionNumberError as exc:
        db.rollback()
        raise _refused(exc) from exc
    _saved(db, user, body.case_id, "received_number_withdrawn", row_id=str(row.id))
    return P.received_view(row)
