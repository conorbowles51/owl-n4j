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


def _case_zone(conn, case_id):
    """The case time zone of 03 section 4.6 (the setting, else the phones' shared device zone, else UTC with a
    note), with its basis, for views that cover several phones."""
    from services.phone import streams
    return streams.case_zone(conn, case_id)


def _zone_for(conn, extraction_ids, zone, case_id=None):
    from sqlalchemy import text as _t
    if zone == "case":
        if case_id is None:
            raise HTTPException(status_code=400, detail="The case zone needs the case.")
        zone = _case_zone(conn, case_id)["name"]
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


# ---- Day view, the lanes window and every event (04 sections 8.1, 8.6, 10) ---------------------------------------

def _labels(conn, case_id):
    return {e["extraction_id"]: e["label"] for e in subjects.extractions(conn, case_id)}


def _money_days(db, case_id, first_day, last_day, zone):
    from services.pattern_of_life import money
    out = money.lane(db, case_id, start_date=first_day, end_date=last_day, zone=zone, limit=5000)
    return out["items"], out["total"]


@router.get("/{case_id}/day")
def get_day(subject: str = Query(...), date: str = Query(...), zone: str = Query("device"),
            include_passive: bool = Query(True), case_id: UUID = Depends(require_case_view),
            db: Session = Depends(get_db)):
    """One local day for a subject, as lanes (04 section 8.1). Every item is returned."""
    from services.pattern_of_life import day as day_view
    r = resolve(db, case_id, subject)
    d = parse_date(date, "date")
    conn = db.connection()
    z, zname = _zone_for(conn, r["extraction_ids"], zone)
    a, b = day_view.day_bounds(d, z)
    money_rows, money_total = _money_days(db, case_id, d, d, z)
    out = day_view.window(conn, r["extraction_ids"], _labels(conn, case_id), a, b, include_passive=include_passive,
                          money_rows=money_rows)
    out["totals"]["money"] = money_total
    return _jsonable(dict(out, subject=r["subject"], date=d, zone=zname, start=a, end=b))


WINDOW_SPANS = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(hours=24)}


@router.get("/{case_id}/window")
def get_window(at: str | None = Query(None), span: str = Query("1h"), start: str | None = Query(None),
               end: str | None = Query(None), subject: str | None = Query(None), zone: str = Query("case"),
               case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    """The window around a moment (07 J-5): one lane per phone (every active phone of the case, or the subject's),
    each with its availability, plus the money lane for the days it touches. ``span`` is 1h, 6h or 24h either side of
    ``at``, or ``custom`` with ``start`` and ``end``."""
    from services.pattern_of_life import day as day_view
    conn = db.connection()
    labels = _labels(conn, case_id)
    exts = resolve(db, case_id, subject)["extraction_ids"] if subject else list(labels)
    if span == "custom":
        if not (start and end):
            raise HTTPException(status_code=400, detail="A custom window needs a start and an end.")
        a, b = parse_range(start, end)
    elif span in WINDOW_SPANS:
        if not at:
            raise HTTPException(status_code=400, detail="Say which moment the window is around.")
        t = parse_instant(at, "at")
        a, b = t - WINDOW_SPANS[span], t + WINDOW_SPANS[span]
    else:
        raise HTTPException(status_code=400, detail="The window is 1h, 6h, 24h or custom.")
    if b - a > timedelta(days=31):
        raise HTTPException(status_code=400, detail="A window is at most 31 days.")
    z, zname = _zone_for(conn, exts, zone, case_id)
    cz = _case_zone(conn, case_id) if zone == "case" else None
    phones = []
    for e in exts:
        w = day_view.window(conn, [e], labels, a, b)
        phones.append(dict(w, extraction_id=e, label=labels.get(e)))
    money_rows, money_total = _money_days(db, case_id, a.astimezone(z).date(), b.astimezone(z).date(), z)
    return _jsonable({"start": a, "end": b, "span": span, "zone": zname,
                      "zone_basis": cz["basis"] if cz else ("device_zone" if zone == "device" else "chosen"),
                      "zone_note": cz["note"] if cz else None, "phones": phones,
                      "phones_total": len(phones), "money": money_rows, "money_total": money_total})


@router.get("/{case_id}/events")
def get_events(subject: str = Query(...), start: str = Query(...), end: str = Query(...),
               classes: str | None = Query(None), cursor: int = Query(0, ge=0),
               case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    from services.pattern_of_life import day as day_view
    r = resolve(db, case_id, subject)
    a, b = parse_range(start, end)
    conn = db.connection()
    ks = [k for k in (classes or "").split(",") if k] or None
    return _jsonable(day_view.events(conn, r["extraction_ids"], _labels(conn, case_id), a, b, cursor=cursor,
                                     classes=ks))


# ---- Frozen pattern results, collected as phone_analysis links (07 section 6.4 item 13) ---------------------------

class SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(day|window|grid|places)$")
    subject: str | None = None
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    start: str | None = None
    end: str | None = None
    zone: str = Field(default="device", max_length=64)
    parameters: dict = Field(default_factory=dict)


@router.post("/{case_id}/snapshots")
def post_snapshot(body: SnapshotRequest, case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                  user=Depends(get_current_db_user)):
    """Freeze what a pattern view shows so it can be added to a finding, dossier, note or interview. The server
    recomputes the result; nothing the browser counted is stored. A day takes ``date``; a window, grid or places
    take ``start`` and ``end``; a window without a subject covers every active phone of the case."""
    from services.pattern_of_life import day as day_view
    from services.pattern_of_life import snapshots
    conn = db.connection()
    labels = _labels(conn, case_id)
    if body.subject:
        r = resolve(db, case_id, body.subject)
        exts, subj = r["extraction_ids"], r["subject"]
    elif body.kind == "window":
        exts, subj = list(labels), {"kind": "case"}
    else:
        raise HTTPException(status_code=400, detail="Say which phone or person the result is for.")
    z, zname = _zone_for(conn, exts, body.zone, case_id)
    if body.kind == "day":
        if not body.date:
            raise HTTPException(status_code=400, detail="A day result needs its date.")
        a, b = day_view.day_bounds(parse_date(body.date, "date"), z)
    elif body.kind == "grid":
        # the grid shows local days, so it is frozen from local midnight to local midnight in its zone
        if not (body.start_date and body.end_date):
            raise HTTPException(status_code=400, detail="A grid result needs its first and last date.")
        d0, d1 = parse_date(body.start_date, "start_date"), parse_date(body.end_date, "end_date")
        if d1 < d0:
            raise HTTPException(status_code=400, detail="The end date must not be before the start date.")
        a, b = day_view.day_bounds(d0, z)[0], day_view.day_bounds(d1, z)[1]
    else:
        if not (body.start and body.end):
            raise HTTPException(status_code=400, detail="This result needs a start and an end.")
        a, b = parse_range(body.start, body.end)
    try:
        out = snapshots.freeze(db, case_id, kind=body.kind, subject=json.loads(json.dumps(subj, default=str)),
                               extraction_ids=exts, labels=labels, start=a, end=b, zone=z, zname=zname,
                               parameters=body.parameters, user=user)
    except snapshots.SnapshotError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return _jsonable(out)


@router.get("/{case_id}/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: str, case_id: UUID = Depends(require_case_view), db: Session = Depends(get_db)):
    from services.pattern_of_life import snapshots
    out = snapshots.read(db.connection(), case_id, snapshot_id)
    if out is None:
        raise HTTPException(status_code=404, detail="That result is not in this case.")
    return _jsonable(out)


# ---- Key dates and case terms (04 section 8.6) -------------------------------------------------------------------

class KeyDateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(date|term)$")
    label: str = Field(min_length=1, max_length=240)
    instant: str | None = None
    zone: str | None = Field(default=None, max_length=64)
    term: str | None = Field(default=None, max_length=240)
    note: str | None = Field(default=None, max_length=4000)


@router.get("/{case_id}/key-dates")
def get_key_dates(kind: str | None = Query(None, pattern="^(date|term)$"), case_id: UUID = Depends(require_case_view),
                  db: Session = Depends(get_db)):
    from services.pattern_of_life import key_dates
    return _jsonable(key_dates.list_for_case(db.connection(), case_id, kind))


@router.post("/{case_id}/key-dates")
def post_key_date(body: KeyDateRequest, case_id: UUID = Depends(require_case_edit), db: Session = Depends(get_db),
                  user=Depends(get_current_db_user)):
    """Enter a key date or case term once for the case: a Workspace note with the marker the analyses read."""
    from services.pattern_of_life import key_dates
    from services.workspace_entry_service import WorkspaceEntryValidationError
    instant = parse_instant(body.instant, "instant") if body.instant else None
    try:
        out = key_dates.create(db, case_id, user, kind=body.kind, label=body.label, instant=instant, zone=body.zone,
                               term=body.term, note=body.note)
    except key_dates.KeyDateError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    except WorkspaceEntryValidationError as exc:  # the Workspace's own rules for a note's words
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return _jsonable(out)
