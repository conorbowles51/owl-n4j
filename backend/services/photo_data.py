"""A photo's own data on the case: Timeline events, map pins, the file's detail, and the one-line caption.

Everything here reads ``evidence_files.metadata["photo_data"]`` (written by processing and the backfill, see
services.photo_metadata). Nothing is invented: a photo with no date has no Timeline entry, a photo with no place has
no pin. Every value is worded as the photo's own data that no person has checked.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.timeline_entry import TimelineEntry

PHOTO_KEY = "photo_data"
CAPTION_KEY = "caption"
CAPTION_MAX = 200
TIMELINE_KIND = "evidence_file"
PHOTO_EVENT_PREFIX = "photo:"

FROM_PHOTO = "From the photo's data, not checked by a person."
ZONE_ABSENT = "Time zone not recorded."
CLOCK_NOTE = "A camera's clock can be wrong."


def _live_photos(db, case_id: UUID):
    return db.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.deleted_at.is_(None),
        EvidenceFile.metadata_[PHOTO_KEY].isnot(None)))


def photo_record(file: EvidenceFile) -> dict:
    record = (file.metadata_ or {}).get(PHOTO_KEY)
    return record if isinstance(record, dict) else {}


def time_words(taken: dict) -> str:
    """"12:30 (UTC offset +01:00)" or "12:30 (time zone not recorded)"."""
    hhmm = taken["local"][11:16]
    offset = taken.get("offset")
    return f"{hhmm} (UTC offset {offset})" if offset else f"{hhmm} ({ZONE_ABSENT[:-1].lower()})"


def absent_values(record: dict) -> list[str]:
    """Which of date taken, place and camera the file did not hold. Empty for a file not yet read."""
    if not record:
        return []
    return [label for key, label in (("date_taken", "date taken"), ("gps", "place"), ("camera", "camera")) if key not in record]


def photo_detail(file: EvidenceFile) -> dict:
    """What the file's detail shows: the record, how to word it, and what was absent."""
    record = photo_record(file)
    caption = (file.metadata_ or {}).get(CAPTION_KEY)
    return dict(
        read=bool(record), data=record, absent=absent_values(record), caption=caption or None,
        label=FROM_PHOTO if record else None,
        time_words=time_words(record["date_taken"]) if record.get("date_taken") else None,
    )


def thumbnail_url(case_id, file_id) -> str:
    return f"/api/photos/{file_id}/thumbnail?case_id={case_id}"


def photo_event(file: EvidenceFile, *, event_date: Optional[str] = None, event_time: Optional[str] = None,
                place: Optional[str] = None, key: Optional[str] = None) -> Optional[dict]:
    """The Timeline event for one photo, or None when it has no date. ``event_date``/``event_time``/``place`` are a
    person's choices; the photo's own value stays in the event (``photo_original``) and in its words."""
    record = photo_record(file)
    taken = record.get("date_taken")
    chosen = bool(event_date)
    if not chosen and not taken:
        return None
    original = (f"Date taken in the photo's data: {taken['local'][:10]} {time_words(taken)}." if taken
                else "The photo's data holds no date taken.")
    if chosen:
        date = event_date
        time = event_time or None
        basis = f"Date chosen by a person. {original}"
    else:
        date = taken["local"][:10]
        time = taken["local"][11:16]
        basis = f"{FROM_PHOTO} {ZONE_ABSENT if not taken.get('offset') else 'UTC offset ' + taken['offset'] + '.'} {CLOCK_NOTE}"
    gps = record.get("gps")
    camera = record.get("camera") or {}
    parts = [file.original_filename]
    if (file.metadata_ or {}).get(CAPTION_KEY):
        parts.insert(0, file.metadata_[CAPTION_KEY])
    if place:
        parts.append(f"Place: {place}")
    elif gps:
        parts.append(f"Place in the photo's data: {gps['latitude']:.5f}, {gps['longitude']:.5f}")
    if camera:
        parts.append("Camera: " + " ".join(v for v in (camera.get("make"), camera.get("model")) if v))
    event = dict(
        key=key or f"{PHOTO_EVENT_PREFIX}{file.id}", name="Photo taken" if not chosen else "Photo", type="Photo",
        date=date, time=time, amount=None, summary=". ".join(parts), notes=None, connections=[],
        source_references=[file.original_filename],
        evidence_file_id=str(file.id), thumbnail_url=thumbnail_url(file.case_id, file.id),
        source=dict(kind=TIMELINE_KIND, id=str(file.id), date_basis=basis, label=file.original_filename,
                    state="current"),
        photo_original=dict(date_taken=taken, gps=gps) if (taken or gps) else None)
    if taken and taken.get("offset") and not chosen:
        event["zone"] = taken["offset"]
    return event


def photo_events(db, case_id: UUID) -> list[dict]:
    """Every dated photo not already on the Timeline by a person's own entry. Undated photos are left out."""
    added = {row for row in db.scalars(select(TimelineEntry.source_id).where(
        TimelineEntry.case_id == case_id, TimelineEntry.source_kind == TIMELINE_KIND))}
    events = []
    for file in _live_photos(db, case_id):
        if file.id in added or not photo_record(file).get("date_taken"):
            continue
        events.append(photo_event(file))
    return events


def photo_places(db, case_id: UUID) -> list[dict]:
    """Every photo with a place, as a map pin linked to the file."""
    pins = []
    for file in _live_photos(db, case_id):
        record = photo_record(file)
        gps = record.get("gps")
        if not gps:
            continue
        taken = record.get("date_taken")
        pins.append(dict(
            key=f"{PHOTO_EVENT_PREFIX}{file.id}", name=(file.metadata_ or {}).get(CAPTION_KEY) or file.original_filename,
            type="document", latitude=gps["latitude"], longitude=gps["longitude"],
            location_formatted=f"Photo place. {FROM_PHOTO}", geocoding_status="photo_data",
            summary=f"{file.original_filename}. " + (f"Taken {taken['local'][:10]} {time_words(taken)}." if taken else
                                                      "No date taken in the photo's data."),
            date=taken["local"][:10] if taken else None, connections=[], manual_correction_history=[],
            evidence_file_id=str(file.id), thumbnail_url=thumbnail_url(case_id, file.id),
            altitude_m=gps.get("altitude_m")))
    return pins


def set_caption(file: EvidenceFile, caption: Optional[str]) -> Optional[str]:
    """One line, optional, never needed by any flow. Blank removes it. Returns what was kept."""
    text = " ".join((caption or "").split())
    if len(text) > CAPTION_MAX:
        raise ValueError(f"A caption is at most {CAPTION_MAX} characters. This one is {len(text)}.")
    meta = dict(file.metadata_ or {})
    if text:
        meta[CAPTION_KEY] = text
    else:
        meta.pop(CAPTION_KEY, None)
    file.metadata_ = meta
    return text or None
