"""Pattern of life API, prefix ``/api/pattern`` (docs/cellebrite/04-pattern-of-life.md section 10).

Reads need case view, writes case edit. Times in and out are ISO 8601 with offset. ``subject`` is a JSON object in
the query string: ``{"kind": "extraction", "extraction_id": ...}`` or ``{"kind": "dossier", "dossier_id": ...}``.
Errors: 400 invalid range or subject, 404 unknown subject, 409 projection building (the body states progress).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from postgres.session import get_db
from routers.case_access import require_case_view
from services.pattern_of_life import availability, subjects

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
