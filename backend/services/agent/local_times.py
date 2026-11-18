"""Local time beside every UTC time a tool result gives (followups m11180017126956 item 4).

Deep runs on the demo case wrote night events under their UTC date ("4 May 03:10") while the documents and the
people lived them on the evening before ("3 May 23:10"). Message rows already carry local_day, time and time_zone;
positions, day and period reads, the ledger and the analyses give UTC instants only. When the case has a time zone
(its setting, or one device zone all its phones share; services.phone.streams.case_zone), each such value gets a
sibling ``<key>_local``: "Fri 2024-05-03 23:10 EDT". A UTC case adds nothing. *Reverse if* a measured run reads
worse with the extra field.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|\+00:00|\+00)$")
MAX_ANNOTATIONS = 3_000


def local_text(value: str, zone: str) -> str | None:
    from services.phone import time_display as T
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T", 1))
    except ValueError:
        return None
    local = when.astimezone(T.tz(zone))
    return "%s %s" % (local.strftime("%a %Y-%m-%d %H:%M"), local.tzname() or zone)


def annotate(data: Any, zone: str | None) -> Any:
    """``data`` with ``<key>_local`` beside each UTC instant string; unchanged when ``zone`` is None or UTC."""
    from services.phone import time_display as T
    if not zone or T.is_utc(zone):
        return data
    budget = [MAX_ANNOTATIONS]

    def walk(v, depth):
        if depth > 12 or budget[0] <= 0:
            return v
        if isinstance(v, list):
            return [walk(x, depth + 1) for x in v]
        if not isinstance(v, dict):
            return v
        out = {}
        has_local = "local_day" in v or "time_zone" in v
        for k, x in v.items():
            out[k] = walk(x, depth + 1)
            if (not has_local and isinstance(k, str) and isinstance(x, str) and not k.endswith("_local")
                    and (k + "_local") not in v and _ISO_UTC.match(x) and budget[0] > 0):
                text = local_text(x, zone)
                if text:
                    out[k + "_local"] = text
                    budget[0] -= 1
        return out

    return walk(data, 0)


def case_zone_name(case_id: str) -> str | None:
    """The case's zone name, or None when it is UTC or cannot be read."""
    try:
        from services.agent.tools import _financial_session
        from services.phone import streams
        from services.phone import time_display as T
        with _financial_session() as s:
            name = streams.case_zone(s.connection(), str(case_id))["name"]
        return None if T.is_utc(name) else name
    except Exception:  # a read failure leaves the result as it was, never fails the tool
        return None
