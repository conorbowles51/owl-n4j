"""Phone analysis API, prefix ``/api/phone-analysis`` (docs/cellebrite/05 section 3.4).

Every path takes the case id and reads only that case. A run or result of another case is 404, never 403, so ids
do not leak across cases. Viewing needs case view; requesting a run, cancelling it and deciding need case edit.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services.financial.quarantine_row import ActorError, actor_from_user
from services.phone_analysis import approaches, framework as F

router = APIRouter(prefix="/api/phone-analysis", tags=["phone-analysis"])


def _ready():
    approaches.install()


def _actor(user):
    try:
        return actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _fail(exc: F.AnalysisError):
    raise HTTPException(status_code=exc.status, detail=str(exc))


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    approach: str = Field(min_length=1, max_length=40)
    parameters: Optional[dict] = None


class KeepBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    decision: Literal["confirmed", "rejected", "not_pursued"]
    reason: str = Field(min_length=1, max_length=4000)


class MeasureBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    approach: str = Field(min_length=1, max_length=40)


@router.post("/runs")
def request_run(body: RunBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """200 with the existing run when the same inputs and settings were run before; 202 when queued."""
    from fastapi.responses import JSONResponse
    _ready()
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        run, created = F.request_run(db.connection(), body.case_id, body.approach, body.parameters,
                                     _actor(user).email)
    except F.AnalysisError as exc:
        db.rollback()
        _fail(exc)
    db.commit()
    return JSONResponse(status_code=202 if created else 200, content=run)


@router.get("/runs")
def list_runs(case_id: UUID = Query(...), approach: Optional[str] = Query(None, max_length=40),
              db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    _ready()
    authorize_case(db, case_id, user, ("case", "view"))
    return {"items": F.list_runs(db.connection(), case_id, approach)}


@router.get("/runs/{run_id}")
def get_run(run_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
            user: User = Depends(get_current_db_user)):
    _ready()
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return F.get_run(db.connection(), case_id, run_id)
    except F.AnalysisError as exc:
        _fail(exc)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
               user: User = Depends(get_current_db_user)):
    _ready()
    authorize_case(db, case_id, user, ("case", "edit"))
    try:
        out = F.cancel(db.connection(), case_id, run_id)
    except F.AnalysisError as exc:
        db.rollback()
        _fail(exc)
    db.commit()
    return out


@router.get("/runs/{run_id}/results")
def run_results(run_id: UUID, case_id: UUID = Query(...), kind: Optional[str] = Query(None, max_length=48),
                strength: Optional[str] = Query(None, max_length=24), from_: Optional[str] = Query(None, alias="from"),
                to: Optional[str] = Query(None), phone: Optional[UUID] = Query(None),
                identity: Optional[str] = Query(None, max_length=512), offset: int = Query(0, ge=0),
                limit: int = Query(100, ge=1, le=F.MAX_LIMIT), db: Session = Depends(get_db),
                user: User = Depends(get_current_db_user)):
    """``total`` is always the full count under the filter (plan 10.2)."""
    _ready()
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return F.results(db.connection(), case_id, run_id, kind=kind, strength=strength, start=from_, end=to,
                         phone=str(phone) if phone else None, identity=identity, offset=offset, limit=limit)
    except F.AnalysisError as exc:
        _fail(exc)


@router.get("/results/{result_id}")
def result_detail(result_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    _ready()
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return F.result_detail(db.connection(), case_id, result_id)
    except F.AnalysisError as exc:
        _fail(exc)


@router.post("/results/{result_id}/keep")
def keep(result_id: UUID, body: KeepBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Freeze one result as a kept phone analysis (``phone_analysis`` link target; 02 decision 50)."""
    from services.phone_analysis import keep as K
    _ready()
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = K.keep(db, body.case_id, result_id, user)
    except F.AnalysisError as exc:
        db.rollback()
        _fail(exc)
    db.commit()
    return out


@router.get("/kept")
def kept(case_id: UUID = Query(...), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
         db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The case's kept analysis results, newest first, with the full count."""
    from services.phone_analysis import keep as K
    authorize_case(db, case_id, user, ("case", "view"))
    return K.list_kept(db.connection(), case_id, limit, offset)


@router.post("/results/{result_id}/decisions")
def decide(result_id: UUID, body: DecisionBody, db: Session = Depends(get_db),
           user: User = Depends(get_current_db_user)):
    _ready()
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = F.decide(db, body.case_id, result_id, body.decision, body.reason, _actor(user))
    except F.AnalysisError as exc:
        db.rollback()
        _fail(exc)
    db.commit()
    return out


@router.get("/coverage")
def coverage(case_id: UUID = Query(...), approach: str = Query(..., max_length=40), db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)):
    """The coverage statement without running anything (3.6)."""
    _ready()
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return F.coverage(db.connection(), case_id, approach)
    except F.AnalysisError as exc:
        _fail(exc)


@router.post("/measurements")
def measure(body: MeasureBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Run the approach's gate measurement on the case (read-only, counts only) and record it (3.3)."""
    from services.phone_analysis import measurements as M
    _ready()
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = M.record(db.connection(), "case", body.case_id, body.approach, _actor(user).email)
    except F.AnalysisError as exc:
        db.rollback()
        _fail(exc)
    db.commit()
    return out


@router.get("/measurements")
def measurements(case_id: Optional[UUID] = Query(None), approach: Optional[str] = Query(None, max_length=40),
                 db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    from services.phone_analysis import measurements as M
    if case_id is None:
        from routers.users import require_admin  # corpus measurements: admins only
        require_admin(user)
    else:
        authorize_case(db, case_id, user, ("case", "view"))
    return {"items": M.rows(db.connection(), case_id, approach)}


# ---- approach 1 (05 section 4): the ledger side, the directory and case aliases --------------------------------------

class PhoneLinksBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    transaction_ids: list[UUID] = Field(max_length=500)


@router.post("/money/ledger-links")
def ledger_links(body: PhoneLinksBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """"Also recorded on phone" for ledger rows (05 4.4): per transaction, the phone readings of the current run that
    corroborate it, each with its record link. A link only: the row's class is unchanged."""
    from services.phone_analysis import money_signals
    authorize_case(db, body.case_id, user, ("case", "view"))
    return {"links": money_signals.phone_links(db.connection(), body.case_id, body.transaction_ids)}


@router.get("/money/directory")
def directory(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The institution directory as this case uses it: every entry with whether it is reviewed (an unreviewed entry is
    never used), and the case's aliases."""
    from services.phone_analysis import institutions as INST
    authorize_case(db, case_id, user, ("case", "view"))
    d = INST.load()
    return {"version": d["version"], "entries": [
        {"institution_id": e["institution_id"], "display_name": e["display_name"], "kind": e["kind"],
         "reviewed": INST.reviewed(e), "review": e.get("review")} for e in d["entries"]],
        "aliases": [dict(a, created_at=a["created_at"].isoformat()) for a in INST.aliases(db.connection(), case_id)]}


class AliasBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    institution_id: str = Field(min_length=6, max_length=120)
    channel: Literal["app_package", "web_domain", "sms_sender", "email_domain"]
    value: str = Field(min_length=1, max_length=320)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/money/aliases")
def add_alias(body: AliasBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """A person's "this sender is this institution" in this case, with a reason (05 4.3.1). The next run reads it."""
    from services.phone_analysis import institutions as INST
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = INST.add_alias(db.connection(), body.case_id, institution_id=body.institution_id, channel=body.channel,
                             value=body.value, reason=body.reason, actor=_actor(user).email)
    except INST.DirectoryError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return out
