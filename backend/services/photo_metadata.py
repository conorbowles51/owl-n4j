"""What a photo's own data says: when and where it was taken, and with what camera.

One reader for the evidence engine (at processing) and the backend (backfill). It reads only the file's EXIF.
Nothing is guessed: a value the file does not hold is absent from the result. The time is kept as the camera wrote
it (no time zone unless the file records an offset), so a screen can say "time zone not recorded".
"""
from __future__ import annotations

import re
from typing import Any, Optional

from services.triage_processors.exif_processor import _dms_to_dd

EXIF_IFD = 0x8769
GPS_IFD = 0x8825
_TAG_DATE_ORIGINAL = 0x9003
_TAG_DATE_DIGITIZED = 0x9004
_TAG_DATE = 0x0132
_OFFSET_FOR = {0x9003: 0x9011, 0x9004: 0x9012, 0x0132: 0x9010}
_TAG_MAKE, _TAG_MODEL = 0x010F, 0x0110
_DATE_RE = re.compile(r"^\s*(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
_OFFSET_RE = re.compile(r"^\s*([+-])(\d{2}):?(\d{2})\s*$")

PHOTO_KEY = "photo_data"


def _text(value: Any) -> Optional[str]:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    value = str(value).replace("\x00", "").strip() if value is not None else ""
    return value or None


def parse_exif_datetime(raw: Any, offset_raw: Any = None) -> Optional[dict]:
    """``{"local": "2024-05-01T12:30:00", "offset": "+01:00" | None}`` or None when the value is not a real time."""
    match = _DATE_RE.match(_text(raw) or "")
    if not match:
        return None
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    if year < 1900 or not (1 <= month <= 12 and 1 <= day <= 31 and hour < 24 and minute < 60 and second < 61):
        return None  # "0000:00:00 00:00:00" is a camera with no clock set, not a date
    try:
        from datetime import datetime

        datetime(year, month, day, hour, minute, min(second, 59))
    except ValueError:
        return None
    offset = None
    off = _OFFSET_RE.match(_text(offset_raw) or "")
    if off and int(off.group(2)) <= 14 and int(off.group(3)) < 60:
        offset = f"{off.group(1)}{off.group(2)}:{off.group(3)}"
    return {"local": f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{min(second, 59):02d}", "offset": offset}


def _float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def read_photo_metadata(file_path: str) -> dict:
    """Everything the photo's data holds, keyed ``date_taken``, ``gps``, ``camera``, ``width``, ``height``.

    Absent values are absent keys. Returns ``{}`` when the file cannot be opened as a picture.
    """
    try:
        from PIL import Image

        with Image.open(file_path) as img:
            out: dict = {"width": img.width, "height": img.height}
            exif = img.getexif()
            if not exif:
                return out
            main = dict(exif)
            try:
                sub = dict(exif.get_ifd(EXIF_IFD))
            except Exception:
                sub = {}
            try:
                gps = dict(exif.get_ifd(GPS_IFD))
            except Exception:
                gps = {}
    except Exception:
        return {}

    merged = {**main, **sub}
    for tag in (_TAG_DATE_ORIGINAL, _TAG_DATE_DIGITIZED, _TAG_DATE):
        taken = parse_exif_datetime(merged.get(tag), merged.get(_OFFSET_FOR[tag]))
        if taken:
            taken["field"] = {_TAG_DATE_ORIGINAL: "DateTimeOriginal", _TAG_DATE_DIGITIZED: "DateTimeDigitized",
                              _TAG_DATE: "DateTime"}[tag]
            out["date_taken"] = taken
            break

    lat = _dms_to_dd(gps.get(2), _text(gps.get(1))) if gps.get(2) is not None else None
    lon = _dms_to_dd(gps.get(4), _text(gps.get(3))) if gps.get(4) is not None else None
    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
        place = {"latitude": lat, "longitude": lon}
        altitude = _float(gps.get(6))
        if altitude is not None:
            ref = gps.get(5)
            below = ref in (1, b"\x01")
            place["altitude_m"] = round(-altitude if below else altitude, 2)
        out["gps"] = place

    make, model = _text(merged.get(_TAG_MAKE)), _text(merged.get(_TAG_MODEL))
    if make or model:
        out["camera"] = {k: v for k, v in (("make", make), ("model", model)) if v}
    return out


def photo_data_record(file_path: str, read_by: str = "processing") -> dict:
    """The record kept on the evidence file under ``metadata["photo_data"]``: what was read, and by what.

    It is the file's own data, read by the system and not checked by a person: ``confirmed_by`` stays empty.
    Only the keys the file holds are present; ``read_by`` says whether processing or the backfill read it.
    """
    from datetime import datetime, timezone

    read = read_photo_metadata(file_path)
    if not read:
        return {}
    return {**read, "source": "photo_data", "confirmed_by": None, "read_by": read_by,
            "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


# One statement for processing (async) and the backfill (sync). The record replaces any earlier reading of the same
# file; a person's changes live elsewhere (a Timeline entry, a caption) and never in this record.
STORE_SQL = (
    "UPDATE evidence_files SET metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{photo_data}', "
    "CAST(:record AS jsonb), true) WHERE id = :id"
)


def store_params(file_id, record: dict) -> dict:
    import json

    return {"id": str(file_id), "record": json.dumps(record)}
