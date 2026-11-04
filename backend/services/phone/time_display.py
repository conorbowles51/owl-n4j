"""How a phone time is written, everywhere (docs/cellebrite/03 section 3.2).

The same rules are in ``frontend_v2/src/lib/evidence-time.ts``; both are tested against
``backend/tests/fixtures/time_cases.json`` so the screen, copied text and the PDF agree byte for byte.

- Row: ``3:07 PM``. Day header: ``Tuesday, March 14, 2023``. Zone label for that day: ``Eastern Time (UTC-4)``,
  or ``Eastern Time (UTC-5 until 2:00 AM, then UTC-4)`` on a day the offset changes. Full form (detail, copy,
  export): ``Tue, Mar 14, 2023, 3:07:12 PM EDT``.
- en-US words are written here, never taken from the machine's locale (D-6).
- Zone names and abbreviations come from ``data/zone_names.json``; a zone not listed is ``<City> time`` and its
  abbreviation is its offset (``UTC+5:30``). UTC is ``UTC``.
- Day grouping uses ``zoneinfo`` in the chosen zone, never a slice of an ISO string.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

NO_TIME = "No time recorded"
NO_OFFSET_FLAG = "No offset in report"
UTC_NAMES = ("UTC", "Etc/UTC", "Etc/GMT", "GMT", "Z")

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


@lru_cache(maxsize=1)
def _table() -> dict:
    with open(os.path.join(os.path.dirname(__file__), "data", "zone_names.json"), encoding="utf-8") as fh:
        return json.load(fh)["zones"]


def is_utc(zone: str) -> bool:
    return zone in UTC_NAMES


@lru_cache(maxsize=256)
def tz(zone: str):
    if is_utc(zone):
        return timezone.utc
    return ZoneInfo(zone)


def valid_zone(zone) -> bool:
    if not isinstance(zone, str) or not zone or len(zone) > 64:
        return False
    try:
        tz(zone)
        return True
    except Exception:
        return False


def zone_name(zone: str) -> str:
    """``Eastern Time``; ``Kolkata time`` for a zone not in the table; ``UTC``."""
    if is_utc(zone):
        return "UTC"
    entry = _table().get(zone)
    if entry:
        return entry["name"]
    return "%s time" % zone.rsplit("/", 1)[-1].replace("_", " ")


def offset_text(minutes: int) -> str:
    """``UTC-4``, ``UTC+5:30``, ``UTC+0``."""
    sign = "+" if minutes >= 0 else "-"
    m = abs(int(minutes))
    h, r = divmod(m, 60)
    return "UTC%s%d%s" % (sign, h, (":%02d" % r) if r else "")


def _offset_minutes(instant: datetime, zone: str) -> int:
    off = instant.astimezone(tz(zone)).utcoffset() or timedelta(0)
    return int(off.total_seconds() // 60)


def abbreviation(instant: datetime, zone: str) -> str:
    """``EDT`` / ``EST`` for a listed zone; ``UTC+5:30`` otherwise; ``UTC`` for UTC."""
    if is_utc(zone):
        return "UTC"
    off = _offset_minutes(instant, zone)
    entry = _table().get(zone)
    if entry:
        return entry["std"] if off == entry["std_offset"] else entry["dst"]
    return "UTC" if off == 0 else offset_text(off)


def _aware(instant) -> datetime | None:
    if instant is None:
        return None
    if isinstance(instant, str):
        instant = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError("an instant must carry an offset")
    return instant


def _clock(dt: datetime, seconds: bool) -> str:
    h = dt.hour % 12 or 12
    s = "%d:%02d" % (h, dt.minute)
    if seconds:
        s += ":%02d" % dt.second
    return s + (" AM" if dt.hour < 12 else " PM")


def local(instant, zone: str) -> datetime | None:
    i = _aware(instant)
    return i.astimezone(tz(zone)) if i is not None else None


def format_row(instant, zone: str, seconds: bool = False) -> str:
    """``3:07 PM`` (``3:07:12 PM`` on hover); ``No time recorded`` when there is no instant."""
    lt = local(instant, zone)
    return NO_TIME if lt is None else _clock(lt, seconds)


def format_full(instant, zone: str) -> str:
    """``Tue, Mar 14, 2023, 3:07:12 PM EDT``."""
    lt = local(instant, zone)
    if lt is None:
        return NO_TIME
    return "%s, %s %d, %d, %s %s" % (WEEKDAYS[lt.weekday()][:3], MONTHS[lt.month - 1][:3], lt.day, lt.year,
                                     _clock(lt, True), abbreviation(_aware(instant), zone))


def format_wall(wall: datetime | None) -> str:
    """A time written without an offset, as the report wrote it: ``Tue, Mar 14, 2023, 3:07:12 PM, no offset in
    report``. Loupe assumes no zone for it."""
    if wall is None:
        return NO_TIME
    return "%s, %s %d, %d, %s, no offset in report" % (WEEKDAYS[wall.weekday()][:3], MONTHS[wall.month - 1][:3],
                                                      wall.day, wall.year, _clock(wall, True))


def day_of(instant, zone: str) -> date | None:
    lt = local(instant, zone)
    return lt.date() if lt is not None else None


def format_day_header(day: date | str) -> str:
    """``Tuesday, March 14, 2023``."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    return "%s, %s %d, %d" % (WEEKDAYS[day.weekday()], MONTHS[day.month - 1], day.day, day.year)


def day_bounds(day: date | str, zone: str) -> tuple[datetime, datetime]:
    """The instants where ``day`` starts and the next day starts, in ``zone``, as UTC."""
    if isinstance(day, str):
        day = date.fromisoformat(day)
    z = tz(zone)
    start = datetime.combine(day, time(0), tzinfo=z).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=z).astimezone(timezone.utc)
    return start, end


def _transition(a: datetime, b: datetime, zone: str) -> datetime:
    """The first instant in (a, b] whose offset differs from a's, to the second."""
    base = _offset_minutes(a, zone)
    lo, hi = a, b
    while (hi - lo) > timedelta(seconds=1):
        mid = lo + (hi - lo) / 2
        if _offset_minutes(mid, zone) == base:
            lo = mid
        else:
            hi = mid
    return hi.replace(microsecond=0)


def day_offsets(day: date | str, zone: str) -> str:
    """``UTC-4``, or ``UTC-5 until 2:00 AM, then UTC-4`` on a day the offset changes. The change time is the wall
    clock before it."""
    start, end = day_bounds(day, zone)
    last = end - timedelta(seconds=1)
    a, b = _offset_minutes(start, zone), _offset_minutes(last, zone)
    if a == b:
        return offset_text(a)
    t = _transition(start, last, zone)
    before = (t.astimezone(timezone.utc) + timedelta(minutes=a)).replace(tzinfo=None)
    return "%s until %s, then %s" % (offset_text(a), _clock(before, False), offset_text(b))


def zone_label(day: date | str, zone: str) -> str:
    """``Eastern Time (UTC-4)``; ``UTC`` for UTC."""
    if is_utc(zone):
        return "UTC"
    return "%s (%s)" % (zone_name(zone), day_offsets(day, zone))


def iso(instant) -> str | None:
    i = _aware(instant)
    return i.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if i is not None else None


ZONE_DECIDED = "zone from a decision, no offset in report"
ZONE_BASES = ("zone_decision", "zone_and_clock")


def format_decided(instant, zone: str, basis) -> str:
    """``format_full`` of an effective time, which says so when a zone decision placed it (02 section 4.1 rule 2)."""
    full = format_full(instant, zone)
    return "%s (%s)" % (full, ZONE_DECIDED) if basis in ZONE_BASES else full


def time_block(instant, zone: str, *, offset_present=True, time_field=None, wall=None, zone_decided=False) -> dict:
    """The ``time`` object of a StreamRow (03 section 4.5). ``zone_decided``: the report wrote no offset and a person's
    decision placed this time (02 section 4.1 rule 2); it says so wherever the time is shown."""
    if zone_decided and instant is not None:
        return {"instant": iso(instant), "row": format_row(instant, zone), "time_field": time_field,
                "full": "%s (%s)" % (format_full(instant, zone), ZONE_DECIDED), "offset_present": False,
                "zone_decided": True}
    if instant is None and wall is not None:
        return {"instant": None, "row": _clock(wall, False), "full": format_wall(wall), "offset_present": False,
                "time_field": time_field}
    return {"instant": iso(instant), "row": format_row(instant, zone), "full": format_full(instant, zone),
            "offset_present": bool(offset_present) if instant is not None else False, "time_field": time_field}
