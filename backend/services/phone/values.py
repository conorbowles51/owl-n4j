"""Value parsers for interpretation (02 section 4). Pure functions, no I/O.

Times are not parsed again here: 01 parsed every TimeStamp into ``phone_timestamps`` (02 decision 32). This module
adds what interpretation needs on top: the producer's ``format`` attribute and its agreement with the parsed
offset (4.1), TimeSpan durations (4.4), coordinates (4.5), and numbers and booleans (4.6). Doubles are
``Decimal`` from the text so no binary rounding enters a stored value; coordinates alone are floats (decision 6).
"""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

BOOLEAN_TEXT = {"True": True, "False": False}


# ---- 4.1 TimeStamp format agreement -------------------------------------------------------------------------

def producer_format(value_attrs: dict | None) -> str | None:
    return (value_attrs or {}).get("format")


def format_mismatch(producer_fmt: str | None, offset_state: str) -> bool:
    """The producer's ``format`` disagrees with what the text holds; the text wins and the row is flagged."""
    if producer_fmt == "TimeStampKnown" and offset_state != "explicit":
        return True
    if producer_fmt in ("DateTimeOnly", "DateOnly") and offset_state == "explicit":
        return True
    return False


def offset_present(offset_state: str) -> bool:
    return offset_state == "explicit"


# ---- 4.4 TimeSpan -------------------------------------------------------------------------------------------

_SPAN = re.compile(r"^(?:(?P<d>\d+)\.)?(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})(?:\.(?P<f>\d{1,7}))?$")


def parse_timespan(text: str | None):
    """``HH:MM:SS``, ``HH:MM:SS.fffffff`` and .NET ``d.HH:MM:SS[.f]``. Returns ``(Decimal seconds, problem)``."""
    if text is None:
        return None, "unparseable"
    m = _SPAN.match(text.strip())
    if not m:
        return None, "unparseable"
    h, mi, s = int(m["h"]), int(m["m"]), int(m["s"])
    if mi > 59 or s > 59 or (m["d"] is not None and h > 23):
        return None, "unparseable"
    total = Decimal(int(m["d"] or 0) * 86400 + h * 3600 + mi * 60 + s)
    if m["f"]:
        total += Decimal("0." + m["f"])
    return total, None


# ---- 4.6 numbers and booleans ---------------------------------------------------------------------------------

def parse_int(text: str | None):
    if text is None:
        return None
    t = text.strip()
    if not re.fullmatch(r"[+-]?\d+", t):
        return None
    return int(t)


def parse_decimal(text: str | None):
    if text is None:
        return None
    try:
        d = Decimal(text.strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def parse_boolean(text: str | None):
    return BOOLEAN_TEXT.get(text) if text is not None else None


def parse_by_type(value_type: str | None, text: str | None):
    """Typed value for the basic types (Strings and named sets are returned as written)."""
    if value_type in ("Int32", "Int64", "UInt32"):
        return parse_int(text)
    if value_type == "Double":
        return parse_decimal(text)
    if value_type == "Boolean":
        return parse_boolean(text)
    if value_type == "TimeSpan":
        return parse_timespan(text)[0]
    return text


# ---- 4.5 coordinates ------------------------------------------------------------------------------------------

def _finite_float(text):
    if text is None:
        return None, "missing_axis"
    try:
        v = float(text.strip())
    except (ValueError, AttributeError):
        return None, "unparseable"
    if not math.isfinite(v):
        return None, "unparseable"
    return v, None


def parse_coordinate(lat_text, lon_text, elevation_text=None, coordinate_accuracy=None, parent_accuracy=None,
                     parent_precision=None) -> dict:
    """A point when both axes parse within range; otherwise the problem flag. Accuracy per 4.5's order."""
    lat, p1 = _finite_float(lat_text)
    lon, p2 = _finite_float(lon_text)
    flags = []
    problem = None
    for p in (p1, p2):
        if p and problem is None:
            problem = p
    if problem is None:
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            problem = "out_of_range"
        elif lat == 0.0 and lon == 0.0:
            flags.append("zero_zero")
    if problem:
        flags.append(problem)
    acc = parse_decimal(coordinate_accuracy) if coordinate_accuracy is not None else None
    if acc is not None:
        basis, precision = "gps_horizontal", None
    else:
        acc = parse_decimal(parent_accuracy) if parent_accuracy is not None else None
        if acc is not None:
            basis, precision = "gps_horizontal", None
        elif parent_precision is not None:
            basis, precision = "precision_field", parent_precision
        else:
            basis, precision = "none", None
    return {
        "is_point": problem is None,
        "lat": lat if problem is None else None,
        "lon": lon if problem is None else None,
        "elevation_m": parse_decimal(elevation_text) if elevation_text is not None else None,
        "accuracy_m": acc,
        "accuracy_basis": basis,
        "precision_text": precision,
        "flags": flags,
    }
