"""The scope bar's rules (lx-corroselect D, P): which of the selected items fall inside a time window, a recurring
window, a set of record kinds and a set of people, and what is outside, counted per kind.

Times are read in the zone the person chose, and the zone is named in the words. An item with no time is never
silently kept or dropped by a time rule: it is counted as "no time" and stays in scope, so the person can see it.
Nothing is deleted from the selection; the scope only chooses what the question is asked of.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from services.relations import rules


class ScopeError(ValueError):
    pass


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScopeError(f"{name!r} is not a time zone Loupe knows.") from exc


def _hours(start: int, end: int, hour: int) -> bool:
    """Hours of a window that may cross midnight (22 to 4)."""
    return start <= hour < end if start < end else (hour >= start or hour < end)


def in_scope(item: dict[str, Any], scope: dict[str, Any], zone: ZoneInfo) -> tuple[bool, bool]:
    """(kept, had_no_time_for_a_time_rule)."""
    kinds = scope.get("kinds") or []
    if kinds and item["type"] not in kinds:
        return False, False
    people = [rules.name_key(p) for p in (scope.get("people") or [])]
    if people:
        names = {rules.name_key(n) for n in (item.get("names") or []) + [item.get("label") or ""]}
        if not any(p and any(p in n for n in names) for p in people):
            return False, False
    needs_time = any(scope.get(k) for k in ("from", "to", "recurring", "window"))  # a relative window is applied in apply()
    if not needs_time:
        return True, False
    when = rules.parse_when(item.get("at"))
    if when is None:
        return True, True
    win = scope.get("window")
    if win:
        # An exact window of instants (an incident time plus or minus hours). A day-only item cannot be placed in it.
        lo, hi = rules.parse_when(win.get("from_at")), rules.parse_when(win.get("to_at"))
        if item.get("precision") == "day":
            return True, True
        if (lo and when < lo) or (hi and when > hi):
            return False, False
    local = when.astimezone(zone)
    if scope.get("from") and local.date() < datetime.fromisoformat(scope["from"]).date():
        return False, False
    if scope.get("to") and local.date() > datetime.fromisoformat(scope["to"]).date():
        return False, False
    rec = scope.get("recurring")
    if rec:
        # A window that crosses midnight belongs to the day it started on: Friday 22:00-04:00 holds Saturday 02:00.
        start_h, end_h = int(rec.get("from_hour", 0)), int(rec.get("to_hour", 24))
        weekday = int(rec["weekday"]) if rec.get("weekday") is not None else None
        hour_ok = _hours(start_h, end_h, local.hour)
        day = local.weekday()
        if weekday is not None and start_h >= end_h and local.hour < end_h:
            day = (day - 1) % 7
        if not hour_ok or (weekday is not None and day != weekday):
            return False, False
    return True, False


def _relative_anchors(items: list[dict[str, Any]], rel: dict[str, Any]) -> tuple[list[datetime], int]:
    """The moments a relative window hangs on: items of the anchor kind (to a person, if named). An anchor that has only
    a date cannot place a window of minutes; those are counted and said, never used as midnight."""
    kind = rel.get("anchor_kind") or "financial_transaction"
    person = rules.name_key(rel.get("person") or "")
    anchors, dateonly = [], 0
    for item in items:
        if item["type"] != kind:
            continue
        if person and not any(person in rules.name_key(n) for n in (item.get("names") or []) + [item.get("label") or ""]):
            continue
        when = rules.parse_when(item.get("at"))
        if when is None or item.get("precision") == "day":
            dateonly += 1
        else:
            anchors.append(when)
    return anchors, dateonly


def words(scope: dict[str, Any]) -> list[str]:
    zone = scope.get("zone") or "UTC"
    out = []
    if scope.get("from") or scope.get("to"):
        out.append(f"{scope.get('from') or 'start'} to {scope.get('to') or 'end'} ({zone})")
    if scope.get("window"):
        w = scope["window"]
        out.append(f"{w.get('from_at') or 'start'} to {w.get('to_at') or 'end'}" + (f" ({w['label']})" if w.get("label") else ""))
    rec = scope.get("recurring")
    if rec:
        day = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][int(rec["weekday"])] if rec.get("weekday") is not None else "every day"
        out.append(f"{'every ' + day if rec.get('weekday') is not None else day}, {int(rec.get('from_hour', 0)):02d}:00 to {int(rec.get('to_hour', 24)) % 24:02d}:00 ({zone})")
    rel = scope.get("relative")
    if rel:
        out.append(f"{int(rel.get('before_min', 0))} min before to {int(rel.get('after_min', 0))} min after each "
                   f"{str(rel.get('anchor_kind') or 'financial_transaction').replace('_', ' ')}"
                   + (f" involving {rel['person']}" if rel.get("person") else ""))
    if scope.get("kinds"):
        out.append("only " + ", ".join(str(k).replace("_", " ") for k in scope["kinds"]))
    if scope.get("people"):
        out.append("involving " + ", ".join(scope["people"]))
    return out


def apply(items: list[dict[str, Any]], scope: dict[str, Any] | None) -> dict[str, Any]:
    """What is in scope, and what is outside it by kind, so nothing is hidden silently."""
    scope = dict(scope or {})
    if not any(scope.get(k) for k in ("from", "to", "recurring", "window", "relative", "kinds", "people")):
        return {"active": False, "kept": items, "outside": {}, "outside_total": 0, "no_time": 0, "words": []}
    zone = _zone(scope.get("zone"))
    rel = scope.get("relative")
    anchors, dateonly = _relative_anchors(items, rel) if rel else ([], 0)
    before, after = (timedelta(minutes=int(rel.get("before_min", 0))), timedelta(minutes=int(rel.get("after_min", 0)))) if rel else (None, None)
    kept, outside, no_time = [], Counter(), 0
    for item in items:
        keep, untimed = in_scope(item, scope, zone)
        if keep and rel:
            when = rules.parse_when(item.get("at"))
            if when is None or item.get("precision") == "day":
                untimed = True
            elif not any(a - before <= when <= a + after for a in anchors):
                keep = False
        no_time += 1 if untimed else 0
        if keep:
            kept.append(item)
        else:
            outside[item["type"]] += 1
    return {"active": True, "kept": kept, "outside": dict(outside), "outside_total": sum(outside.values()),
            "no_time": no_time, "words": words(scope),
            "anchors": len(anchors) if rel else None, "anchors_date_only": dateonly}
