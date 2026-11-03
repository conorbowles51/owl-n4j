"""Day view and the lanes window (04 sections 8.1 and 8.6, unit U6).

One local day (or any window) for a subject, as lanes: availability per phone, interaction, device state,
communications, places, money, passive, and others' actions (counterpart events). Every item is returned; when a
window holds more than ``PASSIVE_LIMIT`` items the passive lane is returned as hourly counts, said so, and
``GET .../events`` pages through every item.

The same function serves the Day view, the Timeline's window around a moment and the incident window, drawn by the
one shared Lanes component.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import text

from services.pattern_of_life import availability
from services.phone.labels import RECIPIENT_ROLES, SENDER_ROLES

PASSIVE_LIMIT = 5000
LANES = ("interaction", "device_state", "communications", "places", "money", "passive", "others")
LANE_WORDS = {"interaction": "Use of the phone", "device_state": "Device state", "communications": "Messages and calls",
              "places": "Places", "money": "Payments", "passive": "Recorded without use",
              "others": "Others' actions"}
EVENT_COLUMNS = ("id, extraction_id, record_uid, record_type, time_field, field_path, instant_utc, end_utc, "
                 "time_semantics, activity_class, actor, physical, attribution_flags, strength, source_app, "
                 "offset_status, class_basis")


def day_bounds(day, zone):
    a = datetime.combine(day, time(0), tzinfo=zone)
    return a, datetime.combine(day + timedelta(days=1), time(0), tzinfo=zone)


def _lane_of(ev) -> str:
    if ev["actor"] == "counterpart":
        return "others"
    if ev["activity_class"] == "interaction":
        return "interaction"
    if ev["activity_class"] == "device_state":
        return "device_state"
    return "passive"


def _event_item(ev, labels):
    return {"ref_kind": "activity_event", "id": ev["id"], "at": ev["instant_utc"], "end": ev["end_utc"],
            "field": ev["time_field"], "meaning": ev["time_semantics"], "class": ev["activity_class"],
            "strength": ev["strength"], "actor": ev["actor"], "physical": ev["physical"],
            "flags": list(ev["attribution_flags"] or []), "source_app": ev["source_app"],
            "extraction_id": str(ev["extraction_id"]), "phone": labels.get(str(ev["extraction_id"])),
            "record_uid": str(ev["record_uid"]), "record_type": ev["record_type"], "field_path": ev["field_path"]}


def window(conn, extraction_ids, labels, a, b, *, include_passive=True, case_id=None, money_rows=None) -> dict:
    exts = [str(e) for e in extraction_ids]
    lanes = {k: [] for k in LANES}
    n_events = conn.execute(text("SELECT count(*) FROM pol_activity_event WHERE extraction_id = ANY(CAST(:e AS uuid[])) "
                                 "AND instant_utc >= :a AND instant_utc < :b"), {"e": exts, "a": a, "b": b}).scalar()
    passive_as_counts = n_events > PASSIVE_LIMIT
    q = ("SELECT " + EVENT_COLUMNS + " FROM pol_activity_event_v WHERE extraction_id = ANY(CAST(:e AS uuid[])) AND "
         "instant_utc >= :a AND instant_utc < :b")
    if passive_as_counts:
        q += " AND NOT (activity_class IN ('passive','unknown') AND actor <> 'counterpart')"
    for ev in conn.execute(text(q + " ORDER BY instant_utc, id"), {"e": exts, "a": a, "b": b}).mappings():
        lanes[_lane_of(ev)].append(_event_item(ev, labels))
    passive_hours = None
    if passive_as_counts:
        passive_hours = [{"hour_utc": r[0], "count": r[1]} for r in conn.execute(text(
            "SELECT date_trunc('hour', instant_utc), count(*) FROM pol_activity_event WHERE extraction_id = "
            "ANY(CAST(:e AS uuid[])) AND instant_utc >= :a AND instant_utc < :b AND activity_class IN "
            "('passive','unknown') AND actor <> 'counterpart' GROUP BY 1 ORDER BY 1"), {"e": exts, "a": a, "b": b})]
    elif not include_passive:
        lanes["passive_count"] = len(lanes["passive"])
    comm = conn.execute(text(
        "SELECT ev.event_uid, ev.record_uid, ev.extraction_id, ev.kind, ev.direction, ev.sort_instant, ev.end_instant, "
        "ev.time_field, ev.app, ev.model_type, ev.status, ev.call_status, ev.deleted_state, "
        "(SELECT json_agg(json_build_object('name', p.name_in_record, 'identifier', p.identifier_raw, 'role', p.role, "
        "'identity_key', p.identity_key) ORDER BY CASE WHEN p.role = ANY(:sr) THEN 0 WHEN p.role = ANY(:rr) THEN 1 "
        "ELSE 2 END, p.participation_uid) FROM pv_comm_party p WHERE p.event_uid = "
        "ev.event_uid AND p.extraction_id = ev.extraction_id AND NOT coalesce(p.is_phone_owner, false) AND "
        "p.role <> 'owner_implicit') AS parties "
        "FROM pv_comm_event ev WHERE ev.extraction_id = ANY(CAST(:e AS uuid[])) AND ev.sort_instant >= :a AND "
        "ev.sort_instant < :b ORDER BY ev.sort_instant, ev.event_uid"),
        {"e": exts, "a": a, "b": b, "sr": list(SENDER_ROLES), "rr": list(RECIPIENT_ROLES)}).mappings()
    for r in comm:
        lanes["communications"].append({
            "ref_kind": "comm_event", "id": str(r["event_uid"]), "at": r["sort_instant"], "end": r["end_instant"],
            "field": r["time_field"], "kind": r["kind"], "direction": r["direction"], "source_app": r["app"],
            "status": r["status"] or r["call_status"], "deleted_state": r["deleted_state"],
            "parties": r["parties"] or [], "extraction_id": str(r["extraction_id"]),
            "phone": labels.get(str(r["extraction_id"])), "record_uid": str(r["record_uid"]),
            "record_type": r["model_type"]})
    for o in conn.execute(text(
            "SELECT id, extraction_id, record_uid, record_type, kind, source_kind, lat, lon, radius_m, radius_basis, "
            "start_utc, end_utc, attribution_flags, source_app FROM pol_place_observation WHERE extraction_id = "
            "ANY(CAST(:e AS uuid[])) AND start_utc < :b AND end_utc >= :a ORDER BY start_utc, id"),
            {"e": exts, "a": a, "b": b}).mappings():
        lanes["places"].append({
            "ref_kind": "place_observation", "id": o["id"], "at": o["start_utc"], "end": o["end_utc"],
            "kind": o["kind"], "source_kind": o["source_kind"], "lat": o["lat"], "lon": o["lon"],
            "radius_m": o["radius_m"], "radius_basis": o["radius_basis"], "flags": list(o["attribution_flags"] or []),
            "source_app": o["source_app"], "extraction_id": str(o["extraction_id"]),
            "phone": labels.get(str(o["extraction_id"])), "record_uid": str(o["record_uid"]) if o["record_uid"] else None,
            "record_type": o["record_type"]})
    if money_rows:
        lanes["money"] = money_rows
    avail = []
    for e in exts:
        hours = availability.hour_states(conn, e, a, b)
        avail.append({"extraction_id": e, "phone": labels.get(e),
                      "hours": [{"hour_utc": h["hour_utc"], "state": h["state"],
                                 "words": availability.UI_COPY.get(h["state"], h["state"])} for h in hours]})
    totals = {k: len(lanes[k]) for k in LANES}
    if passive_hours is not None:
        totals["passive"] = sum(h["count"] for h in passive_hours)
    out = {"lanes": {k: lanes[k] for k in LANES}, "availability": avail, "totals": totals,
           "lane_words": LANE_WORDS, "truncated": False, "passive_as_hourly_counts": passive_as_counts,
           "passive_hours": passive_hours, "limit_words": None}
    if passive_as_counts:
        out["limit_words"] = ("More than %s items in this window: recorded-without-use items are shown as counts per "
                              "hour. Show all pages through every item." % format(PASSIVE_LIMIT, ","))
    return out


def events(conn, extraction_ids, labels, a, b, cursor=0, limit=1000, classes=None) -> dict:
    """Every activity event in the window, cursor-paged, with the total."""
    exts = [str(e) for e in extraction_ids]
    where = "extraction_id = ANY(CAST(:e AS uuid[])) AND instant_utc >= :a AND instant_utc < :b"
    params = {"e": exts, "a": a, "b": b}
    if classes:
        where += " AND activity_class = ANY(:k)"
        params["k"] = list(classes)
    total = conn.execute(text("SELECT count(*) FROM pol_activity_event WHERE " + where), params).scalar()
    rows = conn.execute(text("SELECT " + EVENT_COLUMNS + " FROM pol_activity_event_v WHERE " + where +
                             " ORDER BY instant_utc, id OFFSET :o LIMIT :l"), dict(params, o=cursor, l=limit)).mappings()
    items = [_event_item(r, labels) for r in rows]
    nxt = cursor + len(items)
    return {"total": total, "returned": len(items), "cursor": cursor, "limit": limit,
            "next_cursor": nxt if nxt < total else None, "items": items}
