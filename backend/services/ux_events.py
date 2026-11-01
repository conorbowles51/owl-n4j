"""In-app instrumentation for phone screens (07 section 10.2).

The browser posts events; each is checked against ``ux_event_fields.json`` (the one list of allowed fields,
shared with the frontend's ``lib/ux-events.ts``). Only ids, kinds, counts, milliseconds and booleans are
accepted: any other field, a value of the wrong type, or a string outside its fixed vocabulary refuses the whole
event, so names, numbers, message text, addresses, coordinates and query strings cannot be stored. Accepted
events go into Loupe's own activity records (action ``ux_event``) with the session and browser the activity
trail already records, and are shown as funnels on the admin Speed page. Nothing goes to a third party.
"""
from __future__ import annotations

import json
import math
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = json.loads((Path(__file__).with_name("ux_event_fields.json")).read_text())
ACTION = "ux_event"
MAX_EVENTS = 50


class Refused(ValueError):
    pass


def _check(name: str, value):
    spec = FIELDS["field_types"].get(name)
    if spec is None:
        raise Refused(f"field {name} is not allowed")
    if "ref" in spec:
        spec = FIELDS["field_types"][spec["ref"]]
    if "enum" in spec:
        if not isinstance(value, str) or value not in spec["enum"]:
            raise Refused(f"{name} is not one of its fixed values")
        return value
    if "bool" in spec:
        if not isinstance(value, bool):
            raise Refused(f"{name} must be true or false")
        return value
    if "int" in spec:
        low, high = spec["int"]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise Refused(f"{name} must be a whole number from {low} to {high}")
        return value
    if "number" in spec:
        low, high = spec["number"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise Refused(f"{name} must be a number from {low} to {high}")
        return round(float(value), 1)
    if "uuid" in spec:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError):
            raise Refused(f"{name} must be an id") from None
    raise Refused(f"field {name} has no type")  # pragma: no cover


def clean(event: dict) -> dict:
    """The event as stored, or Refused. Unknown events and fields are refused, never trimmed."""
    if not isinstance(event, dict):
        raise Refused("an event must be an object")
    kind = event.get("event")
    allowed = FIELDS["events"].get(kind)
    if allowed is None:
        raise Refused("unknown event")
    out = {"event": kind}
    for name, value in event.items():
        if name == "event":
            continue
        if name not in allowed:
            raise Refused(f"field {name} is not allowed on {kind}")
        out[name] = _check(name, value)
    missing = [name for name in FIELDS["required"].get(kind, []) if name not in out]
    if missing:
        raise Refused(f"{kind} needs {', '.join(missing)}")
    return out


def record(events: list, *, user, case_id, db=None) -> dict:
    from services import activity_trail
    accepted, refused = 0, 0
    for event in events[:MAX_EVENTS]:
        try:
            details = clean(event)
        except Refused:
            refused += 1
            continue
        if activity_trail.record(ACTION, db=db, user=user, case_id=case_id, details=details):
            accepted += 1
    refused += max(0, len(events) - MAX_EVENTS)
    if db is not None and accepted:
        db.commit()
    return {"accepted": accepted, "refused": refused}


def funnels(db, days: int = 14) -> dict:
    """Per journey: started, completed, abandoned, median time to complete, and how many reached each step.
    Also wait and collect counts. Counts and milliseconds only."""
    from sqlalchemy import select
    from postgres.models.activity_event import ActivityEvent as E

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(E.details).where(E.action == ACTION, E.at >= since))
    journeys: dict[str, dict] = {}
    waits = {"over_2s": 0, "over_2s_without_panel": 0, "left_before_data": 0}
    collect = {"actions": 0, "records": 0}
    reviews: dict[str, list[float]] = {}
    for d in rows:
        kind = d.get("event")
        j = d.get("journey")
        if j:
            item = journeys.setdefault(j, {"journey": j, "started": 0, "completed": 0, "abandoned": 0, "steps": {}, "_ms": []})
            if kind == "journey_start":
                item["started"] += 1
            elif kind == "journey_complete":
                item["completed"] += 1
                if d.get("ms") is not None:
                    item["_ms"].append(d["ms"])
            elif kind == "journey_abandon":
                item["abandoned"] += 1
            elif kind == "journey_step":
                step = str(d.get("step"))
                item["steps"][step] = item["steps"].get(step, 0) + 1
        if kind == "wait" and d.get("ms", 0) > 2000:
            waits["over_2s"] += 1
            if not d.get("panel"):
                waits["over_2s_without_panel"] += 1
        if kind == "left_before_data":
            waits["left_before_data"] += 1
        if kind == "collect":
            collect["actions"] += 1
            collect["records"] += d.get("count", 0)
        if kind == "review_item" and d.get("ms") is not None:
            reviews.setdefault(d.get("queue"), []).append(d["ms"])
    out = []
    for item in sorted(journeys.values(), key=lambda x: int(x["journey"].split("-")[1])):
        ms = item.pop("_ms")
        item["median_ms"] = statistics.median(ms) if ms else None
        item["steps"] = [{"step": int(k), "reached": v} for k, v in sorted(item["steps"].items(), key=lambda kv: int(kv[0]))]
        out.append(item)
    return {
        "days": days,
        "journeys": out,
        "waits": waits,
        "collect": collect,
        "review_median_ms": {q: statistics.median(v) for q, v in reviews.items()},
    }
