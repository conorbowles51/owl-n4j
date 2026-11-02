"""Pattern of life API, prefix ``/api/pattern`` (docs/cellebrite/04-pattern-of-life.md section 10).

Reads need case view, writes case edit. Times in and out are ISO 8601 with offset. ``subject`` is a JSON object in
the query string: ``{"kind": "extraction", "extraction_id": ...}`` or ``{"kind": "dossier", "dossier_id": ...}``.
Errors: 400 invalid range or subject, 404 unknown subject, 409 projection building (the body states progress).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from datetime import date as date_type

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import require_case_edit, require_case_view
from routers.users import get_current_db_user, require_admin
from services.pattern_of_life import availability, grid, subjects

router = APIRouter(prefix="/api/pattern", tags=["pattern-of-life"])

MAX_RANGE_DAYS = 3660  # a request over ten years is refused as an invalid range, never clipped


def _iso(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return v


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, datetime):
        return _iso(o)
    if isinstance(o, UUID):
        return str(o)
    return o


def parse_subject(raw: str) -> dict:
    try:
        s = json.loads(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="The subject must be a JSON object.")
    return s


def resolve(db, case_id, raw):
    try:
        return subjects.resolve(db.connection(), case_id, parse_subject(raw))
    except subjects.SubjectError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


def parse_instant(v: str, name: str) -> datetime:
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise HTTPException(status_code=400, detail="%s must be an ISO 8601 time with its offset." % name)
    if d.tzinfo is None:
        raise HTTPException(status_code=400, detail="%s must carry its offset (or Z)." % name)
    return d.astimezone(timezone.utc)


def parse_range(start: str, end: str):
    a, b = parse_instant(start, "start"), parse_instant(end, "end")
    if b <= a:
        raise HTTPException(status_code=400, detail="The end must be after the start.")
    if b - a > timedelta(days=MAX_RANGE_DAYS):
        raise HTTPException(status_code=400, detail="The range is longer than ten years; choose a shorter one.")
    return a, b


@router.get("/{case_id}/subjects")
def list_subjects(case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    conn = db.connection()
    exts = subjects.extractions(conn, case_id)
    people = subjects.dossiers(conn, case_id, exts)
    return _jsonable({"extractions": exts, "dossiers": people, "total_extractions": len(exts),
                      "total_dossiers": len(people)})


@router.get("/{case_id}/availability")
def get_availability(subject: str = Query(...), start: str = Query(...), end: str = Query(...),
                     case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    r = resolve(db, case_id, subject)
    a, b = parse_range(start, end)
    conn = db.connection()
    out = []
    for e in r["extraction_ids"]:
        out.append({"extraction_id": e,
                    "bands": availability.bands(conn, e, a, b),
                    "pieces": availability.window_pieces(conn, e, a, b),
                    "streams": availability.streams(conn, e),
                    "selection": availability.NO_SELECTION_STATED})
    return _jsonable({"subject": r["subject"], "start": a, "end": b, "extractions": out,
                      "labels": availability.UI_COPY, "max_gap_s": availability.MAX_GAP_S})


MAX_GRID_DAYS = 1500  # longer than the largest phone's span (P14: 546 observed days); a longer request is refused


def parse_date(v: str, name: str):
    from datetime import date
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="%s must be a date (YYYY-MM-DD)." % name)


@router.get("/{case_id}/grid")
def get_grid(subject: str = Query(...), start_date: str = Query(...), end_date: str = Query(...),
             zone: str = Query("device"), min_strength: str = Query("moderate"),
             classes: str = Query("interaction"), include_physical: bool = Query(False),
             case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    r = resolve(db, case_id, subject)
    a, b = parse_date(start_date, "start_date"), parse_date(end_date, "end_date")
    if b < a:
        raise HTTPException(status_code=400, detail="The end date must not be before the start date.")
    if (b - a).days + 1 > MAX_GRID_DAYS:
        raise HTTPException(status_code=400, detail="The range is longer than %d days; choose a shorter one."
                            % MAX_GRID_DAYS)
    if min_strength not in grid.STRENGTH_ORDER:
        raise HTTPException(status_code=400, detail="min_strength is weak, moderate or strong.")
    cls = tuple(c for c in classes.split(",") if c)
    if not set(cls) <= {"interaction", "device_state"}:
        raise HTTPException(status_code=400, detail="classes are interaction and device_state.")
    conn = db.connection()
    from services.phone import readings
    labels = {str(k): v for k, v in readings.phone_labels(conn, case_id).items()}
    try:
        out = grid.grid(conn, r["extraction_ids"], labels, a, b, zone, min_strength, cls, include_physical)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _jsonable(dict(out, subject=r["subject"]))


PLACE_PAGE = 1000


@router.get("/{case_id}/places")
def get_places(subject: str = Query(...), start: str = Query(...), end: str = Query(...), kinds: str = Query(""),
               cursor: int = Query(0, ge=0), case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    from services.pattern_of_life import places
    r = resolve(db, case_id, subject)
    a, b = parse_range(start, end)
    ks = [k for k in kinds.split(",") if k]
    conn = db.connection()
    total, rows = places.observations(conn, r["extraction_ids"], a, b, ks, cursor, PLACE_PAGE)
    nxt = cursor + len(rows) if cursor + len(rows) < total else None
    return _jsonable({"subject": r["subject"], "total": total, "returned": len(rows), "next_cursor": nxt,
                      "page_size": PLACE_PAGE, "observations": rows,
                      "towers_not_placed": [dict(t, words=places.TOWER_WORDS[t["reason"]])
                                            for t in places.unplaced_towers(conn, r["extraction_ids"])],
                      "reverse_geocoding": places._GEO["status"] or places.reverse_geocoding_status()})


class CellImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_path_on_server: str = Field(min_length=1, max_length=4000)
    name: str = Field(min_length=1, max_length=400)
    licence: str = Field(min_length=1, max_length=400)
    attribution: str = Field(min_length=1, max_length=2000)
    retrieved_on: date_type
    source_note: str | None = Field(default=None, max_length=4000)


@router.post("/{case_id}/reference/cell")
def import_cell_reference(body: CellImport, case_id: UUID, db: Session = Depends(get_db),
                          user=Depends(require_admin)):
    """Admin: import an offline cell-tower file an operator placed on the server (04 section 6.4). The dataset is
    global and kept as a dated version; no case uses it until a person chooses it for that case."""
    from services.pattern_of_life import places
    conn = db.connection()
    try:
        out = places.import_cell_file(conn, body.file_path_on_server, name=body.name, licence=body.licence,
                                      attribution=body.attribution, retrieved_on=body.retrieved_on,
                                      source_note=body.source_note, by_name=user.name or user.email,
                                      by_email=user.email)
    except places.ImportRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return out


def _zone_for(conn, extraction_ids, zone):
    from sqlalchemy import text as _t
    dz = conn.execute(_t("SELECT device_zone FROM phone_extractions WHERE id = :e"),
                      {"e": extraction_ids[0]}).scalar() if extraction_ids else None
    try:
        return grid.zone_of(zone, dz)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{case_id}/routine")
def get_routine(subject: str = Query(...), zone: str = Query("device"), case_id: UUID = Depends(require_case_view),
                db: Session = Depends(get_db)):
    from services.pattern_of_life import routine
    r = resolve(db, case_id, subject)
    conn = db.connection()
    z, zname = _zone_for(conn, r["extraction_ids"], zone)
    out = routine.compute(conn, r["extraction_ids"], z)
    out["zone"] = zname
    return _jsonable(dict(out, subject=r["subject"], stays_total=len(out["stays"])))


@router.get("/{case_id}/routine/deviations")
def get_deviations(subject: str = Query(...), start_date: str = Query(None), end_date: str = Query(None),
                   zone: str = Query("device"), case_id: UUID = Depends(require_case_view),
                   db: Session = Depends(get_db)):
    from services.pattern_of_life import routine
    r = resolve(db, case_id, subject)
    a = parse_date(start_date, "start_date") if start_date else None
    b = parse_date(end_date, "end_date") if end_date else None
    conn = db.connection()
    z, zname = _zone_for(conn, r["extraction_ids"], zone)
    res = routine.compute(conn, r["extraction_ids"], z)
    out = routine.deviations(res, z, a, b)
    return _jsonable(dict(out, subject=r["subject"], zone=zname, routine_places=res["routine_places"]))


class TogetherParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_s: float = Field(default=300, gt=0, le=86400)
    assumed_radius_m: float = Field(default=1000.0, gt=0, le=100000)
    max_speed_mps: float = Field(default=40.0, gt=0, le=400)
    include_synced: bool = False


class TogetherRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subjects: list[dict] = Field(min_length=2, max_length=2)
    start: str
    end: str
    params: TogetherParams = TogetherParams()


@router.post("/{case_id}/together")
def post_together(body: TogetherRequest, case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db),
                  user=Depends(get_current_db_user)):
    """Together and apart for two subjects (04 section 8.4). Every pair is kept; a large run answers 202 with its id
    and runs in the background. Reading a case's phones needs only case view; the run is the reader's own."""
    from fastapi.responses import JSONResponse

    from services.pattern_of_life import colocation
    conn = db.connection()
    try:
        ra = subjects.resolve(conn, case_id, body.subjects[0])
        rb = subjects.resolve(conn, case_id, body.subjects[1])
    except subjects.SubjectError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    a, b = parse_range(body.start, body.end)
    params = body.params.model_dump()
    rid = colocation.create_run(conn, case_id, ra["subject"], rb["subject"], ra["extraction_ids"], rb["extraction_ids"],
                                a, b, params, user.email)
    est = colocation.estimate_pairs(conn, ra["extraction_ids"], rb["extraction_ids"], a, b)
    if est > colocation.BACKGROUND_PAIRS:
        db.commit()
        from postgres.session import _get_background_engine
        colocation.run_in_background(_get_background_engine, rid)
        return JSONResponse(status_code=202, content={"run_id": str(rid), "estimated_pairs": est,
                                                      "status": "queued"})
    colocation.execute_run(conn, rid)
    db.commit()
    return _jsonable(colocation.read_run(db.connection(), rid, case_id))


@router.get("/{case_id}/together/{run_id}")
def get_together(run_id: UUID, cursor: int = Query(0, ge=0), case_id: UUID = Depends(require_case_view),
                 db: Session = Depends(get_db)):
    from services.pattern_of_life import colocation
    out = colocation.read_run(db.connection(), run_id, case_id, cursor)
    if out is None:
        raise HTTPException(status_code=404, detail="That run is not in this case.")
    return _jsonable(out)


@router.get("/{case_id}/money")
def get_money(start_date: str | None = Query(None), end_date: str | None = Query(None),
              account_ids: list[UUID] = Query(default=[]), subject: str | None = Query(None),
              zone: str = Query("device"), cursor: int = Query(0, ge=0),
              case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    """The money lane (04 section 8.5): admitted payments as all-day items, never at a time of day. ``subject`` only
    sets the zone an attached place's day is drawn in; the ledger does not link accounts to phones or people."""
    from services.pattern_of_life import money
    a = parse_date(start_date, "start_date") if start_date else None
    b = parse_date(end_date, "end_date") if end_date else None
    ext = resolve(db, case_id, subject)["extraction_ids"] if subject else []
    z, zname = _zone_for(db.connection(), ext, zone)
    try:
        out = money.lane(db, case_id, start_date=a, end_date=b, account_ids=account_ids, zone=z, cursor=cursor)
    except money.MoneyError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    out["zone"] = zname
    return _jsonable(out)


class ManualPlaceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^transaction$")
    transaction_id: UUID


class ManualPlaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: ManualPlaceTarget
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_m: int = Field(ge=1, le=50000)
    reason: str = Field(min_length=1, max_length=4000)


class ManualPlaceRemoval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: ManualPlaceTarget
    reason: str = Field(min_length=1, max_length=4000)


def _place_actor(user):
    from services.financial.quarantine_row import ActorError, actor_from_user
    try:
        return actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{case_id}/places/manual")
def post_manual_place(body: ManualPlaceRequest, case_id: UUID = Depends(require_case_edit),
                      db: Session = Depends(get_db), user=Depends(get_current_db_user)):
    """A person attaches a place to a payment, recorded as a decision with them as Actor (04 section 8.5)."""
    from services.pattern_of_life import money
    try:
        out = money.attach(db, case_id, body.target.transaction_id, lat=body.lat, lon=body.lon,
                           radius_m=body.radius_m, reason=body.reason, actor=_place_actor(user))
    except money.MoneyError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return out


@router.post("/{case_id}/places/manual/remove")
def post_manual_place_removal(body: ManualPlaceRemoval, case_id: UUID = Depends(require_case_edit),
                              db: Session = Depends(get_db), user=Depends(get_current_db_user)):
    from services.pattern_of_life import money
    try:
        out = money.remove(db, case_id, body.target.transaction_id, reason=body.reason, actor=_place_actor(user))
    except money.MoneyError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return out


@router.get("/{case_id}/places/manual/{transaction_id}")
def get_manual_place_history(transaction_id: UUID, case_id: UUID = Depends(require_case_view),
                             db: Session = Depends(get_db)):
    from services.pattern_of_life import money
    rows = money.history(db.connection(), case_id, transaction_id)
    return _jsonable({"total": len(rows), "items": rows})


# ---- statement check (04 section 9) ------------------------------------------------------------------------------

class ClaimFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str | None = None
    subject: dict | None = None
    window_start: str | None = None
    window_end: str | None = None
    window_zone: str | None = Field(default=None, max_length=64)
    window_text: str | None = Field(default=None, max_length=4000)
    place: dict | None = None
    activity: dict | None = None
    counterpart: dict | None = None
    source_anchor: dict | None = None


class ClaimEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: ClaimFields
    expected_version: int


class ClaimVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int


class ClaimReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=4000)


class AttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entry_id: UUID
    expected_version: int
    item_ordinals: list[int] = Field(default_factory=list, max_length=5000)
    include_check_link: bool = True


def _claim_error(exc):
    detail = {"message": str(exc), "fields": exc.fields} if exc.fields else str(exc)
    return HTTPException(status_code=exc.status, detail=detail)


@router.get("/{case_id}/claims")
def get_claims(status: str | None = Query(None), case_id: UUID = Depends(require_case_view),
               db: Session = Depends(get_db)):
    from services.pattern_of_life import claims
    return _jsonable(claims.list_claims(db.connection(), case_id, status))


@router.post("/{case_id}/claims")
def post_claim(body: ClaimFields, case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
               user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims
    try:
        out = claims.create(db.connection(), case_id, body.model_dump(exclude_unset=True), _place_actor(user))
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return _jsonable(out)


@router.get("/{case_id}/claims/{claim_id}")
def get_claim(claim_id: UUID, case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    from services.pattern_of_life import claims
    try:
        out = claims.get(db.connection(), case_id, claim_id)
        out["revisions"] = claims.revisions(db.connection(), case_id, claim_id)
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    return _jsonable(out)


@router.patch("/{case_id}/claims/{claim_id}")
def patch_claim(claim_id: UUID, body: ClaimEdit, case_id: UUID = Depends(require_case_edit),
                db: Session = Depends(get_db), user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims
    try:
        out = claims.edit(db.connection(), case_id, claim_id, body.fields.model_dump(exclude_unset=True),
                          body.expected_version, _place_actor(user))
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return _jsonable(out)


@router.post("/{case_id}/claims/{claim_id}/confirm")
def post_claim_confirm(claim_id: UUID, body: ClaimVersion, case_id: UUID = Depends(require_case_edit),
                       db: Session = Depends(get_db), user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims
    try:
        out = claims.confirm(db.connection(), case_id, claim_id, body.expected_version, _place_actor(user))
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return _jsonable(out)


@router.post("/{case_id}/claims/{claim_id}/withdraw")
def post_claim_withdraw(claim_id: UUID, body: ClaimReason, case_id: UUID = Depends(require_case_edit),
                        db: Session = Depends(get_db), user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims
    try:
        out = claims.withdraw(db.connection(), case_id, claim_id, body.reason, _place_actor(user))
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return _jsonable(out)


@router.post("/{case_id}/claims/{claim_id}/evaluate")
def post_claim_evaluate(claim_id: UUID, case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                        user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims, evaluation
    try:
        out = evaluation.evaluate(db.connection(), case_id, claim_id, _place_actor(user).name)
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return _jsonable(out)


@router.get("/{case_id}/claims/{claim_id}/evaluations")
def get_claim_evaluations(claim_id: UUID, case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    from services.pattern_of_life import claims, evaluation
    try:
        return _jsonable(evaluation.list_evaluations(db.connection(), case_id, claim_id))
    except claims.ClaimError as exc:
        raise _claim_error(exc)


@router.get("/{case_id}/claims/{claim_id}/evaluations/{evaluation_id}")
def get_claim_evaluation(claim_id: UUID, evaluation_id: UUID, case_id: UUID = Depends(require_case_view),
                         db: Session = Depends(get_db)):
    from services.pattern_of_life import claims, evaluation
    try:
        out = evaluation.read(db.connection(), case_id, evaluation_id)
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    if str(out["claim_id"]) != str(claim_id):
        raise HTTPException(status_code=404, detail="That check is not of this statement.")
    return _jsonable(out)


@router.post("/{case_id}/claims/{claim_id}/evaluations/{evaluation_id}/items/{ordinal}/dispute")
def post_item_dispute(claim_id: UUID, evaluation_id: UUID, ordinal: int, body: ClaimReason,
                      case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                      user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims, evaluation
    try:
        out = evaluation.dispute(db, case_id, evaluation_id, ordinal, body.reason, _place_actor(user))
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return out


@router.post("/{case_id}/claims/{claim_id}/evaluations/{evaluation_id}/items/{ordinal}/dispute/withdraw")
def post_item_dispute_withdraw(claim_id: UUID, evaluation_id: UUID, ordinal: int, body: ClaimReason,
                               case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                               user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims, evaluation
    try:
        out = evaluation.withdraw_dispute(db, case_id, evaluation_id, ordinal, body.reason, _place_actor(user))
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    db.commit()
    return out


@router.post("/{case_id}/claims/{claim_id}/evaluations/{evaluation_id}/attach")
def post_evaluation_attach(claim_id: UUID, evaluation_id: UUID, body: AttachRequest,
                           case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                           user=Depends(get_current_db_user)):
    from services.pattern_of_life import claims, evaluation
    from services.workspace_entry_service import (WorkspaceEntryConflict, WorkspaceEntryNotFound,
                                                  WorkspaceEntryValidationError)
    try:
        out = evaluation.attach(db, case_id, evaluation_id, entry_id=body.entry_id,
                                expected_version=body.expected_version, item_ordinals=body.item_ordinals,
                                include_check_link=body.include_check_link, user=user)
    except claims.ClaimError as exc:
        raise _claim_error(exc)
    except WorkspaceEntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc) or "That entry is not in this case.")
    except WorkspaceEntryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceEntryValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return _jsonable(out)


class ClaimDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dossier_id: UUID
    interview_ids: list[UUID] = Field(default_factory=list, max_length=20)
    conversation_locator: str | None = Field(default=None, max_length=512)
    subject: dict


@router.post("/{case_id}/claim-drafts")
def post_claim_drafts(body: ClaimDraftRequest, background_tasks: BackgroundTasks,
                      case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                      user=Depends(get_current_db_user)):
    """Model drafting of claims from interviews or a conversation (04 section 9.2): a Workspace AI output of type
    ``statement_claims`` under the ``statement_claim_drafting`` workload. Reviewed and accepted like any Workspace AI
    output; accepting makes draft claims for a person to confirm."""
    from services.workspace_ai_service import (WorkspaceAIError, WorkspaceAINotFound, create_output,
                                               run_output_in_background)
    resolve(db, case_id, json.dumps(body.subject))  # 404 when the phone or person is not in this case
    if not body.interview_ids and not body.conversation_locator:
        raise HTTPException(status_code=400, detail="Choose an interview or a conversation to draft from.")
    try:
        out = create_output(db, case_id=case_id, target_type="dossier", target_id=body.dossier_id,
                            output_type="statement_claims", requested_by=user, interview_ids=body.interview_ids,
                            subject=body.subject, conversation=body.conversation_locator)
    except WorkspaceAINotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except WorkspaceAIError as exc:
        status = 404 if "not in this case" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))
    background_tasks.add_task(run_output_in_background, UUID(out["id"]))
    return out
