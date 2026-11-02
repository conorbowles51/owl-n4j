"""Measure spec 03 section 20.2, 20.3 and 20.9 on captured phones. Prints counts and sizes only, never content.

    python backend/scripts/phone_measure_section20.py [--case <uuid>] [--extraction <uuid>]

20.2: the most events in one day on one phone (communications and timeline entries, by UTC day and by the
phone's zone when known). 20.3: average and 99th-percentile JSON size of a ``StreamRow`` built in spec 03
section 9's documented shape from ``pv_comm_event`` and ``pv_comm_party`` (with ``ParticipantLabel``s).
20.9: communicating identities and pair edges per case, from the graph projection's plan (02 section 9.3).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402


def _label(p, names, displays, owner_key):
    key = p.identity_key
    return {"identity_key": key, "name": names.get(key) or p.name_in_record,
            "name_basis": "contact_on_this_phone" if names.get(key) else ("name_in_record" if p.name_in_record
                                                                          else "none"),
            "identifier": {"kind": (key or "other:").split(":", 1)[0], "display": displays.get(key),
                           "captured": p.identifier_raw},
            "is_owner": bool(p.is_phone_owner or (owner_key and key == owner_key)),
            "owner_basis": None, "case_names": []}


def stream_row_sizes(conn, ext):
    from services.phone import identities
    from services.phone.readings import phone_labels
    from services.phone.thread_text import _zone, when_words
    head = conn.execute(text("SELECT case_id, device_zone FROM phone_extractions WHERE id = :e"), {"e": ext}).one()
    label = phone_labels(conn, head.case_id).get(str(ext))
    zone = _zone(head.device_zone)
    owner_key = (identities.owner(conn, ext).get("owner_identity_keys") or [None])[0]
    displays = {r[0]: r[1] for r in conn.execute(text(
        "SELECT identity_key, value_display FROM phone_identities WHERE case_id = :c"), {"c": head.case_id})}
    names = {r[0]: r[1] for r in conn.execute(text(
        "SELECT identity_key, name FROM pv_identity_name WHERE extraction_id = :e AND is_phone_name"), {"e": ext})}
    titles = {r[0]: r[1] for r in conn.execute(text(
        "SELECT thread_key, title_in_record FROM pv_thread WHERE extraction_id = :e"), {"e": ext})}
    parties = defaultdict(list)
    for p in conn.execute(text("SELECT event_uid, identity_key, role, implied_role, is_phone_owner, name_in_record, "
                               "identifier_raw FROM pv_comm_party WHERE extraction_id = :e"), {"e": ext}):
        parties[p.event_uid].append(p)
    sizes = []
    for ev in conn.execute(text(
            "SELECT event_uid, record_uid, kind, app, thread_key, direction, sort_instant, time_field, body, subject, "
            "call_duration_s, call_status, video, flags, deleted_state, interpretation_level FROM pv_comm_event WHERE "
            "extraction_id = :e").execution_options(stream_results=True, yield_per=5000), {"e": ext}):
        ps = parties.get(ev.event_uid, [])
        frm = [p for p in ps if (p.implied_role if p.role == "owner_implicit" else p.role) in ("sender", "caller", "from")]
        to = [p for p in ps if p not in frm]
        row = {"event_uid": str(ev.event_uid), "record_uid": str(ev.record_uid), "kind": ev.kind,
               "phone": {"extraction_id": str(ext), "label": label}, "app": ev.app,
               "thread": {"thread_key": ev.thread_key, "title": titles.get(ev.thread_key)}, "direction": ev.direction,
               "time": {"instant": ev.sort_instant.isoformat() if ev.sort_instant else None,
                        "row": when_words(ev.sort_instant, zone, seconds=False).split(", ")[-1]
                        if ev.sort_instant else None,
                        "full": when_words(ev.sort_instant, zone), "offset_present": True, "time_field": ev.time_field},
               "from": _label(frm[0], names, displays, owner_key) if frm else None,
               "to": [_label(p, names, displays, owner_key) for p in to],
               "body": ev.body, "subject": ev.subject,
               "call": {"duration_s": ev.call_duration_s, "status": ev.call_status, "video": ev.video}
               if ev.kind == "call" else None,
               "attachments": [], "flags": list(ev.flags or []) + (["Deleted"] if ev.deleted_state not in
                                                                    (None, "Intact") else []),
               "copies": None, "owner_read": {"date_read": None, "date_played": None},
               "interpretation_level": ev.interpretation_level}
        sizes.append(len(json.dumps(row, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")))
    sizes.sort()
    return {"rows": len(sizes), "avg_bytes": round(statistics.mean(sizes), 1) if sizes else None,
            "p99_bytes": sizes[int(0.99 * (len(sizes) - 1))] if sizes else None,
            "max_bytes": sizes[-1] if sizes else None}


def most_in_a_day(conn, ext):
    zone = conn.execute(text("SELECT device_zone FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar() or "UTC"
    out = {}
    for name, view, col in (("comm_events", "pv_comm_event", "sort_instant"),
                            ("timeline_entries", "pv_timeline_entry", "instant")):
        for basis, tz in (("utc", "UTC"), ("phone_zone", zone)):
            r = conn.execute(text(
                "SELECT (%s AT TIME ZONE :z)::date, count(*) FROM %s WHERE extraction_id = :e AND %s IS NOT NULL "
                "GROUP BY 1 ORDER BY 2 DESC LIMIT 1" % (col, view, col)), {"e": ext, "z": tz}).first()
            out["%s_%s" % (name, basis)] = int(r[1]) if r else 0
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", default=[])
    ap.add_argument("--extraction", action="append", default=[])
    args = ap.parse_args(argv)
    from postgres.session import _get_engine
    from services.phone import graph_projection
    from services.phone.readings import phone_labels
    engine = _get_engine()
    with engine.connect() as conn:
        exts = args.extraction or [str(r[0]) for r in conn.execute(text(
            "SELECT e.id FROM phone_extractions e JOIN phone_interpretation_state s ON s.extraction_id = e.id "
            "WHERE e.standing = 'active' AND s.generation > 0 AND (cardinality(CAST(:c AS uuid[])) = 0 OR "
            "e.case_id = ANY(CAST(:c AS uuid[]))) ORDER BY e.record_count DESC"), {"c": args.case})]
        for ext in exts:
            case = conn.execute(text("SELECT case_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
            print(json.dumps({"extraction": ext[:8], "label": phone_labels(conn, case).get(ext),
                              "20.2": most_in_a_day(conn, ext), "20.3": stream_row_sizes(conn, ext)}), flush=True)
        cases = args.case or sorted({str(r[0]) for r in conn.execute(text(
            "SELECT case_id FROM phone_extractions WHERE id = ANY(CAST(:e AS uuid[]))"), {"e": exts})})
        for case in cases:
            p = graph_projection.plan(conn, case)
            print(json.dumps({"case": case[:8], "20.9": p["counts"]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
