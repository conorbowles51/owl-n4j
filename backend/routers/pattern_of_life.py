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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import require_case_view
from routers.users import require_admin
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
