"""Compare two phones (07 J-16): how many messages and calls are on both, only on one, only on the other.

A message or call is matched across the two phones by a key read from its own record: kind, app, instant to the
second, and the body's hash (calls: the duration instead of a body). Participants are left out of the key because
each phone records its own owner implicitly, so the same message names its sender differently on the two sides.
Copies of one message on the same phone count once. Records with no time are not compared and are counted.

Decision: this key stands until approach 12 (05 section 15.3 step 3) ships its natural keys; J-16's counts then
read approach 12's ``present_in_both`` / ``only_in_*`` for the same pair and scope (07 J-16 targets). Reverse
when that result exists.
"""
from __future__ import annotations

from sqlalchemy import text

KINDS = ("message", "call")
KEY_WORDS = ("Matched by app, time to the second and the message text (calls: the duration). Copies on one phone "
             "count once.")


class NotFound(LookupError):
    pass


def compare(conn, case_id, a, b, person=None) -> dict:
    from services.phone import readings
    a, b, case_id = str(a), str(b), str(case_id)
    if a == b:
        raise ValueError("Choose two different phones.")
    found = {str(r[0]) for r in conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' AND id IN "
        "(CAST(:a AS uuid), CAST(:b AS uuid))"), {"c": case_id, "a": a, "b": b})}
    if found != {a, b}:
        raise NotFound("Both phones must be in this case.")
    labels = readings.phone_labels(conn, case_id)
    scope = ("AND EXISTS (SELECT 1 FROM pv_comm_party p WHERE p.event_uid = ev.event_uid AND p.identity_key = :who)"
             if person else "")
    p = {"c": case_id, "a": a, "b": b, "who": person}
    # a phone's period is all its messages and calls (what it covers), whoever is chosen; the undated count is
    # within the chosen scope
    periods = {str(r.extraction_id): r for r in conn.execute(text(
        "SELECT ev.extraction_id, min(ev.sort_instant) AS first, max(ev.sort_instant) AS last, "
        "count(*) FILTER (WHERE ev.sort_instant IS NULL " + scope + ") AS no_time FROM pv_comm_event ev WHERE "
        "ev.case_id = :c AND ev.extraction_id IN (CAST(:a AS uuid), CAST(:b AS uuid)) AND ev.kind IN ('message', "
        "'call') GROUP BY ev.extraction_id"), p)}
    p.update({"af": getattr(periods.get(a), "first", None), "al": getattr(periods.get(a), "last", None),
              "bf": getattr(periods.get(b), "first", None), "bl": getattr(periods.get(b), "last", None)})
    rows = conn.execute(text(
        "WITH k AS (SELECT DISTINCT ev.extraction_id, ev.kind, coalesce(ev.app, '') AS app, "
        "date_trunc('second', ev.sort_instant) AS t, CASE WHEN ev.kind = 'call' THEN "
        "coalesce(CAST(ev.call_duration_s AS text), '') ELSE md5(coalesce(ev.body, '')) END AS h "
        "FROM pv_comm_event ev WHERE ev.case_id = :c AND ev.extraction_id IN (CAST(:a AS uuid), CAST(:b AS uuid)) "
        "AND ev.kind IN ('message', 'call') AND ev.sort_instant IS NOT NULL " + scope + "), "
        "s AS (SELECT kind, t, bool_or(extraction_id = CAST(:a AS uuid)) AS ina, "
        "bool_or(extraction_id = CAST(:b AS uuid)) AS inb FROM k GROUP BY kind, app, t, h) "
        "SELECT kind, count(*) FILTER (WHERE ina AND inb) AS both, "
        "count(*) FILTER (WHERE ina AND NOT inb) AS only_a, "
        "count(*) FILTER (WHERE ina AND NOT inb AND (CAST(:bf AS timestamptz) IS NULL OR t < date_trunc('second', "
        "CAST(:bf AS timestamptz)) OR t > CAST(:bl AS timestamptz))) AS only_a_outside, "
        "count(*) FILTER (WHERE inb AND NOT ina) AS only_b, "
        "count(*) FILTER (WHERE inb AND NOT ina AND (CAST(:af AS timestamptz) IS NULL OR t < date_trunc('second', "
        "CAST(:af AS timestamptz)) OR t > CAST(:al AS timestamptz))) AS only_b_outside FROM s GROUP BY kind"), p)
    kinds = {k: {"both": 0, "only_a": 0, "only_a_outside": 0, "only_b": 0, "only_b_outside": 0} for k in KINDS}
    for r in rows:
        kinds[r.kind] = {"both": r.both, "only_a": r.only_a, "only_a_outside": r.only_a_outside,
                         "only_b": r.only_b, "only_b_outside": r.only_b_outside}

    def side(ext):
        r = periods.get(ext)
        iso = (lambda v: v.isoformat() if v is not None else None)
        return {"extraction_id": ext, "label": labels.get(ext, "A phone"), "first": iso(getattr(r, "first", None)),
                "last": iso(getattr(r, "last", None)), "no_time": int(getattr(r, "no_time", 0) or 0)}
    return {"case_id": case_id, "person": person, "a": side(a), "b": side(b), "kinds": kinds, "key": KEY_WORDS}
