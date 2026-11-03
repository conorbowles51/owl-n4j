"""Subjects of the pattern views (04 sections 1.4, 4.2 and 10): one extraction, or a person as a dossier.

A person counts an extraction only when the extraction's owner identity is linked to the dossier by a reviewed
identity-to-dossier link (``phone_identity_links``, 02 section 8). Every subject is checked against the case the
request is made in; an extraction or dossier of another case is "not found".
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import text

from services.pattern_of_life import activity


class SubjectError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _uuid(v):
    try:
        return UUID(str(v))
    except (TypeError, ValueError):
        raise SubjectError(400, "The subject's id is not a valid id.")


def _when(iso):
    return datetime.fromisoformat(iso) if iso else None


SET_APART_GAP_DAYS = 90
SET_APART_SHARE = 0.01
SET_APART_EVENTS = 20


def usual_span(conn, extraction_id) -> dict:
    """The days a phone's activity actually covers (04 decision 38). A run of days more than 90 days from the rest
    holding under 1% of the phone's activity or fewer than 20 events is set apart, from either end (the smaller end
    first), until none is left or one run remains: a stray date (a clock reset, a far-future reminder) must not decide
    which day the views open on. Nothing is hidden: the events set apart are counted, and any date can be chosen."""
    days = conn.execute(text(
        "SELECT (hour_utc AT TIME ZONE 'UTC')::date, sum(interaction_strong + interaction_moderate + interaction_weak + "
        "device_state + passive) FROM pol_hourly_rollup WHERE extraction_id = :e GROUP BY 1 HAVING "
        "sum(interaction_strong + interaction_moderate + interaction_weak + device_state + passive) > 0 ORDER BY 1"),
        {"e": extraction_id}).fetchall()
    if not days:
        return {"first": None, "last": None, "set_apart": 0, "set_apart_first": None, "set_apart_last": None}
    runs = [[days[0]]]
    for d in days[1:]:
        if (d[0] - runs[-1][-1][0]).days > SET_APART_GAP_DAYS:
            runs.append([])
        runs[-1].append(d)
    total = sum(int(n) for _, n in days)
    size = lambda run: sum(int(n) for _, n in run)  # noqa: E731
    small = lambda run: size(run) < SET_APART_EVENTS or size(run) < SET_APART_SHARE * total  # noqa: E731
    while len(runs) > 1 and (small(runs[0]) or small(runs[-1])):
        ends = [i for i in (0, -1) if small(runs[i])]
        runs.pop(min(ends, key=lambda i: size(runs[i])))
    first, last = runs[0][0][0], runs[-1][-1][0]
    before, after = (conn.execute(text(
        "SELECT count(*), min(instant_utc), max(instant_utc) FROM pol_activity_event WHERE extraction_id = :e AND " + w),
        {"e": extraction_id, "t": datetime.combine(t, time(0), tzinfo=timezone.utc)}).one()
        for w, t in (("instant_utc < :t", first), ("instant_utc >= :t", last + timedelta(days=1))))
    utc = lambda v: v.astimezone(timezone.utc) if v is not None else None  # noqa: E731 (the page shows UTC dates)
    return {"first": first, "last": last, "set_apart": int(before[0]) + int(after[0]),
            "set_apart_first": utc(before[1] or after[1]), "set_apart_last": utc(after[2] or before[2])}


def extractions(conn, case_id) -> list:
    """Active extractions of the case with their label, zone, owner identity, families and projection status."""
    from services.phone import identities as I
    from services.phone import readings
    labels = readings.phone_labels(conn, case_id)
    out = []
    for r in conn.execute(text(
            "SELECT e.id, e.device_zone, s.status AS interp_status, p.status AS pol_status, p.event_count, p.built_at, "
            "p.families "
            "FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id "
            "LEFT JOIN pol_projection_state p ON p.extraction_id = e.id "
            "WHERE e.case_id = :c AND e.standing = 'active' ORDER BY e.created_at"), {"c": case_id}).mappings():
        # kept on the projection state by the build; computed here for a projection built before it was kept
        stored = r["families"] if r["families"] is not None else activity.families(conn, r["id"])
        fams = [dict(f, first=_when(f["first"]), last=_when(f["last"])) for f in stored]
        owner = I.owner(conn, r["id"])
        keys = owner.get("owner_identity_keys") or []
        out.append({"kind": "extraction", "extraction_id": str(r["id"]), "label": labels.get(r["id"]) or
                    labels.get(str(r["id"])) or "Phone", "device_zone": r["device_zone"],
                    "owner_identity_key": keys[0] if keys else None,
                    "families": fams, "first": min((f["first"] for f in fams), default=None),
                    "last": max((f["last"] for f in fams), default=None),
                    "projection_status": r["pol_status"] or ("waiting" if r["interp_status"] == "done" else
                                                             "not_interpreted"),
                    "event_count": r["event_count"] or 0,
                    "usual_span": usual_span(conn, r["id"]) if r["pol_status"] == "ready" else None})
    return out


def _owners(conn, case_id) -> list:
    """Active extractions of the case with their owner identity only, in the order ``extractions`` gives them:
    what ``dossiers`` needs, without the per-family event counts (an aggregate over every event of every phone, 5.5 s
    of each request about a person on a 542,091-event phone)."""
    from services.phone import identities as I
    out = []
    for (e,) in conn.execute(text("SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' "
                                  "ORDER BY created_at"), {"c": case_id}):
        keys = I.owner(conn, e).get("owner_identity_keys") or []
        out.append({"extraction_id": str(e), "owner_identity_key": keys[0] if keys else None})
    return out


def dossiers(conn, case_id, exts=None) -> list:
    """Persons (dossiers) with the extractions whose owner identity is linked to them."""
    exts = _owners(conn, case_id) if exts is None else exts
    by_key = {}
    for e in exts:
        if e["owner_identity_key"]:
            by_key.setdefault(e["owner_identity_key"], []).append(e["extraction_id"])
    out = {}
    if by_key:
        for key, dossier, name in conn.execute(text(
                "SELECT i.identity_key, l.dossier_id, p.display_name FROM phone_identity_links l JOIN phone_identities i "
                "ON i.id = l.identity_id LEFT JOIN case_profiles p ON p.id = l.dossier_id WHERE l.case_id = :c AND "
                "i.identity_key = ANY(:k)"), {"c": case_id, "k": list(by_key)}):
            d = out.setdefault(str(dossier), {"kind": "dossier", "dossier_id": str(dossier), "name": name,
                                              "extraction_ids": []})
            d["extraction_ids"] += [x for x in by_key[key] if x not in d["extraction_ids"]]
    return sorted(out.values(), key=lambda d: (d["name"] or "", d["dossier_id"]))


def resolve(conn, case_id, subject) -> dict:
    """``{"subject": ..., "extraction_ids": [...]}``; raises ``SubjectError`` 400 or 404."""
    if not isinstance(subject, dict) or subject.get("kind") not in ("extraction", "dossier"):
        raise SubjectError(400, "A subject is a phone (extraction) or a person (dossier).")
    if subject["kind"] == "extraction":
        eid = _uuid(subject.get("extraction_id"))
        ok = conn.execute(text("SELECT 1 FROM phone_extractions WHERE id = :e AND case_id = :c AND standing = 'active'"),
                          {"e": eid, "c": case_id}).scalar()
        if not ok:
            raise SubjectError(404, "That phone is not in this case.")
        return {"subject": {"kind": "extraction", "extraction_id": str(eid)}, "extraction_ids": [str(eid)]}
    did = _uuid(subject.get("dossier_id"))
    exists = conn.execute(text("SELECT 1 FROM case_profiles WHERE id = :d AND case_id = :c"),
                          {"d": did, "c": case_id}).scalar()
    if not exists:
        raise SubjectError(404, "That person is not in this case.")
    for d in dossiers(conn, case_id):
        if d["dossier_id"] == str(did):
            return {"subject": {"kind": "dossier", "dossier_id": str(did)}, "extraction_ids": d["extraction_ids"],
                    "name": d["name"]}
    return {"subject": {"kind": "dossier", "dossier_id": str(did)}, "extraction_ids": [], "name": None}
