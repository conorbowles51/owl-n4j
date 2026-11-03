"""Statement check: evaluating a confirmed claim (04 sections 9.3 to 9.5, unit U11).

The outcome is computed from the items and never set by hand. An evaluation stores the inputs it read (extractions
with their interpretation generation and projection state, mapping versions, the case's cell dataset, parameters,
the claim version) and their sha256; an evaluation whose inputs no longer match the current ones is ``stale`` (shown,
never deleted), and **Check again** writes a new one beside it.

Every item is stored and returned; there is no limit. Context events inside the window (recorded without use, a state
change, not the user's own action, a time whose meaning is unknown) are one item per phone, hour and reason with the
count, each event listed by ``group_events`` (04 decision 37). Items within 30 minutes outside the window are
``context`` so an approximate time in the statement never hides a near miss. Items are ordered by time, then kind and id, so a
re-run on unchanged inputs is identical.

Bank payments are never items of a person's check: the ledger does not link accounts to phones or people (04
decision 28), so a payment with an attached place is listed as context only.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life import availability, claims, colocation, subjects
from services.pattern_of_life.attribution import GROUP_A
from services.pattern_of_life.places import ROUTINE_KINDS

MARGIN = timedelta(minutes=30)
COVER_SHARE = 0.80
PARAMS = {"margin_minutes": 30, "cover_share": COVER_SHARE, "tight_radius_m": colocation.DEFAULT_PARAMS["tight_radius_m"],
          "max_speed_mps": colocation.DEFAULT_PARAMS["max_speed_mps"],
          "assumed_radius_m": colocation.DEFAULT_PARAMS["assumed_radius_m"]}
GAP_STATES = ("no_data", "powered_off", "powered_off_inferred", "after_extraction", "outside_selection", "not_selected")
OUTCOME_WORDS = {
    "consistent": {"inactive": "Nothing on the phone needed a person during this time, and the phone was recording "
                               "for most of it.",
                   "no_contact": "No contact with the other side was found on any phone in the case, and the phones' "
                                 "messages and calls cover this time."},
    "contradicted": "Records on the phone undercut this statement.",
    "contradicted_weakly": "Some records may undercut this statement, but none of them is strong.",
    "supported": "Records on the phone support this statement.",
    "mixed": "Records on the phone both support and undercut this statement.",
    "insufficient_data": "The phone does not hold enough for this time to test the statement.",
    "no_record": "The phone holds no record of this kind for this time, for the reason stated: that is a finding "
                 "about what was extracted, not about what happened.",
}
# no_record (agent-phones; report "Statement check with the money lane"): "insufficient data" (the phone holds some
# of this time, too little to test) and "no record of something that should be there" are different findings. The
# reasons are fixed codes; each says why the phone cannot hold the record.
NO_RECORD_REASONS = {
    "not_extracted": "The extraction holds no %s at all.",
    "outside_coverage": "The time is outside what the phone's extraction covers (records run %s to %s).",
    "after_extraction": "The time is after the phone was extracted.",
    "not_selected": "The production did not select this time.",
}
GAP_WORDS = {"no_data": "Nothing recorded on this phone for this time.", "powered_off": "The phone was switched off.",
             "powered_off_inferred": "The phone appears to have been switched off.",
             "after_extraction": "After the phone was extracted.",
             "outside_selection": "Outside what the production selected.", "not_selected": "Not selected for the report.",
             "no_location": "No location recorded.", "messages_may_be_deleted": "Messages may have been deleted.",
             "no_comm_coverage": "No messages or calls recorded on this phone for this time."}


class EvaluationError(claims.ClaimError):
    pass


# ---------------------------------------------------------------------------------------------------------------
# inputs and the fingerprint

def _subject_exts(conn, case_id, subject, role="subject"):
    try:
        r = subjects.resolve(conn, case_id, subject)
    except subjects.SubjectError as exc:
        raise EvaluationError(str(exc), exc.status)
    if not r["extraction_ids"]:
        name = r.get("name") or "this person"
        raise EvaluationError("This check needs a phone linked to %s. Link a phone's owner to the person first."
                              % name, 422, fields=[role])
    return sorted(r["extraction_ids"])


def inputs(conn, claim) -> dict:
    case_id = claim["case_id"]
    exts = _subject_exts(conn, case_id, claim["subject"])
    other = []
    cp = claim.get("counterpart")
    if claim["kind"] in claims.SUBJECT_KINDS or (claim["kind"] in claims.CONTACT_KINDS and isinstance(cp, dict)
                                                 and cp.get("kind") == "dossier"):
        other = _subject_exts(conn, case_id, cp, "counterpart")
    every = sorted(set(exts) | set(other))
    if claim["kind"] in claims.CONTACT_KINDS:
        # both sides of every phone in the case (9.4 no_contact step 1)
        every = sorted({r[0] for r in conn.execute(text(
            "SELECT id::text FROM phone_extractions WHERE case_id = :c AND standing = 'active'"), {"c": case_id})})
    states = {}
    for e in every:
        gen = conn.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                           {"e": e}).scalar()
        p = conn.execute(text(
            "SELECT interpretation_generation, activity_mapping_version, meaning_mapping_version, "
            "attribution_mapping_version, signature, built_at, status FROM pol_projection_state WHERE extraction_id = :e"),
            {"e": e}).mappings().first()
        states[e] = {"generation": gen, "projection": json.loads(json.dumps(dict(p), default=str)) if p else None}
    ds = conn.execute(text("SELECT dataset_id FROM pol_case_cell_dataset WHERE case_id = :c"), {"c": case_id}).scalar()
    return {"claim_id": str(claim["id"]), "claim_version": claim["version"], "kind": claim["kind"],
            "subject_extractions": exts, "counterpart_extractions": other, "extractions": states,
            "cell_dataset_id": str(ds) if ds else None, "params": PARAMS}


def fingerprint(inp) -> str:
    return hashlib.sha256(json.dumps(inp, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# ---------------------------------------------------------------------------------------------------------------
# items

def _item(role, ref_kind, ref_id, reason, explanation, *, strength=None, at=None, end=None, record_uid=None,
          field_path=None, extraction_id=None, display=None):
    return {"role": role, "ref_kind": ref_kind, "ref_id": str(ref_id), "strength": strength, "reason_code": reason,
            "explanation": explanation, "record_uid": str(record_uid) if record_uid else None, "field_path": field_path,
            "extraction_id": str(extraction_id) if extraction_id else None, "at_utc": at, "end_utc": end,
            "display": display or {}}


_EVENT_COLUMNS = ("SELECT id, extraction_id, record_uid, record_type, time_field, field_path, instant_utc, end_utc, "
                  "time_semantics, activity_class, actor, physical, attribution_flags, strength, source_app, "
                  "offset_status")
_CONTEXT_COLUMNS = ("SELECT extraction_id, instant_utc, end_utc, time_semantics, activity_class, actor, physical, "
                    "strength, record_type")


def _overlap(cols):
    """Events overlapping [a - margin, b + margin): those starting inside it, and those starting earlier whose end
    falls inside it (two index ranges; one overlap test read every earlier event of the phone, 04 section 11)."""
    sel = cols + " FROM pol_activity_event_v WHERE extraction_id = ANY(CAST(:e AS uuid[])) AND "
    return "(" + sel + "instant_utc >= :lo AND instant_utc < :hi AND coalesce(end_utc, instant_utc) >= :lo UNION ALL " + \
        sel + "instant_utc < :lo AND end_utc >= :lo) x"


# An event inside the window that is neither the owner's use nor (for "inactive") the phone moving: context, kept
# by count only (04 decision 37). Mirrors the tests in ``_activity``; the columns it reads are NOT NULL.
_INSIDE = "x.instant_utc < :b AND coalesce(x.end_utc, x.instant_utc) >= :a"
_CONTEXT = (_INSIDE + " AND NOT (x.actor = 'owner' AND x.activity_class = 'interaction' AND x.strength <> 'none') "
            "AND NOT (CAST(:inactive AS boolean) AND x.physical)")


_HOUR = "date_trunc('hour', x.instant_utc AT TIME ZONE 'UTC')"
# why a context event neither undercuts nor supports: what its time means is unknown, or its class
_REASON = ("CASE WHEN x.time_semantics = 'unknown' THEN 'time_meaning_unknown' WHEN x.activity_class IN "
           "('device_state', 'passive') THEN x.activity_class ELSE 'not_owner_use' END")


def _events(conn, exts, a, b, inactive):
    """The events listed one by one: every overlapping event except the context ones."""
    p = {"e": list(exts), "lo": a - MARGIN, "hi": b + MARGIN, "a": a, "b": b, "inactive": bool(inactive)}
    return [dict(r) for r in conn.execute(text(
        "SELECT * FROM " + _overlap(_EVENT_COLUMNS) + " WHERE NOT (" + _CONTEXT + ") ORDER BY instant_utc, id"),
        p).mappings()]


def _context_groups(conn, exts, a, b, inactive):
    """The context events counted per phone, UTC hour, reason and record type."""
    p = {"e": list(exts), "lo": a - MARGIN, "hi": b + MARGIN, "a": a, "b": b, "inactive": bool(inactive)}
    groups = {}
    for ext, hour, reason, rtype, n, first, last in conn.execute(text(
            "SELECT x.extraction_id, " + _HOUR + ", " + _REASON + ", x.record_type, count(*), min(x.instant_utc), "
            "max(x.instant_utc) FROM " + _overlap(_CONTEXT_COLUMNS) + " WHERE " + _CONTEXT +
            " GROUP BY 1, 2, 3, 4"), p):
        g = groups.setdefault((str(ext), hour.replace(tzinfo=timezone.utc), reason),
                              {"count": 0, "first": first, "last": last, "types": {}})
        g["count"] += n
        g["first"], g["last"] = min(g["first"], first), max(g["last"], last)
        g["types"][rtype] = g["types"].get(rtype, 0) + n
    return groups


def _in_window(start, end, a, b):
    end = end or start
    return start < b and end >= a


def _event_display(ev):
    return {"type": ev["record_type"], "field": ev["time_field"], "meaning": ev["time_semantics"],
            "source_app": ev["source_app"], "flags": list(ev["attribution_flags"] or []),
            "activity_class": ev["activity_class"], "actor": ev["actor"]}


def _gap_items(conn, exts, a, b):
    out, pieces = [], {}
    for e in exts:
        ps = availability.window_pieces(conn, e, a, b)
        pieces[e] = ps
        for p in ps:
            if p["state"] in GAP_STATES:
                out.append(_item("gap", "window_piece", "%s:%s" % (e, p["start"].isoformat()), p["state"],
                                 GAP_WORDS[p["state"]], at=p["start"], end=p["end"], extraction_id=e))
    return out, pieces


def _interaction_free_pieces(pieces, owner_int):
    """Observed pieces with the owner-interaction instants cut out (data_no_interaction)."""
    out = []
    for e, ps in pieces.items():
        cuts = sorted(t for x, t in owner_int if x == e)
        for p in ps:
            if p["state"] != "observed":
                continue
            s = p["start"]
            for t in [t for t in cuts if p["start"] <= t < p["end"]] + [p["end"]]:
                if t > s:
                    out.append((e, s, t, p))
                s = max(s, t)
    return out


CONTEXT_WORDS = {"device_state": "The screen or the phone's state changed; a notification can do this.",
                 "passive": "Recorded by the phone without anyone using it.",
                 "time_meaning_unknown": "What this time means is not established.",
                 "not_owner_use": "Not shown to be the user's own action."}


def _activity(conn, claim, a, b, exts, inactive):
    items = []
    tol = timedelta(minutes=int((claim.get("activity") or {}).get("tolerance_minutes", 0) or 0))
    owner_int = []
    for ev in _events(conn, exts, a, b, inactive):
        disp, kw = _event_display(ev), {}
        kw = dict(at=ev["instant_utc"], end=ev["end_utc"], record_uid=ev["record_uid"], field_path=ev["field_path"],
                  extraction_id=ev["extraction_id"], display=disp)
        inside = _in_window(ev["instant_utc"], ev["end_utc"], a, b)
        if not inside:
            items.append(_item("context", "activity_event", ev["id"], "near_window",
                               "Within 30 minutes of the time in the statement.", strength=ev["strength"], **kw))
            continue
        owner = ev["actor"] == "owner" and ev["activity_class"] == "interaction" and ev["strength"] != "none"
        if owner:
            owner_int.append((str(ev["extraction_id"]), ev["instant_utc"]))
            if inactive and tol and (ev["instant_utc"] < a + tol or ev["instant_utc"] >= b - tol):
                items.append(_item("context", "activity_event", ev["id"], "within_stated_tolerance",
                                   "Use within the tolerance the statement allows.", strength=ev["strength"], **kw))
            else:
                items.append(_item("contradicting" if inactive else "supporting", "activity_event", ev["id"],
                                   "owner_interaction", "The phone's user did something on it.",
                                   strength=ev["strength"], **kw))
        elif inactive and ev["physical"]:
            items.append(_item("contradicting", "activity_event", ev["id"], "phone_moved", "The phone moved.",
                               strength="weak", **kw))
        else:
            raise AssertionError("a context event was listed one by one")  # _CONTEXT and these tests disagree
    groups = _context_groups(conn, exts, a, b, inactive)
    for (ext, hour, reason), g in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
        items.append(_item("context", "event_group", "%s:%s:%s" % (ext, hour.isoformat(), reason), reason,
                           "%s event%s in this hour. %s" % (format(g["count"], ","), "" if g["count"] == 1 else "s",
                                                            CONTEXT_WORDS[reason]),
                           at=g["first"], end=g["last"], extraction_id=ext,
                           display={"count": g["count"], "hour_utc": hour.isoformat(),
                                    "types": dict(sorted(g["types"].items()))}))
    gaps, pieces = _gap_items(conn, exts, a, b)
    items += gaps
    free = _interaction_free_pieces(pieces, owner_int)
    window_s = (b - a).total_seconds() * len(exts)
    free_s = sum((t - s).total_seconds() for _, s, t, _ in free)
    for e, s, t, p in free:
        items.append(_item("supporting" if inactive else "contradicting", "window_piece", "%s:%s" % (e, s.isoformat()),
                           "data_no_interaction", "The phone was recording and shows no use.",
                           strength="moderate" if p["interaction_capable"] else "weak", at=s, end=t, extraction_id=e,
                           display={"streams": p["streams"]}))
    share = free_s / window_s if window_s else 0.0
    return items, {"recording_share_without_use": round(share, 4)}


def _place_strength(v, flags):
    if v.get("assumed") or "cell_reference" in flags or "cell" in flags:
        return "weak"
    a_flags = [f for f in flags if f in GROUP_A]
    # 9.4 at_place step 2: tight is a radii sum of 150 m or less, whichever way the pair falls
    if v["radii_sum_m"] <= PARAMS["tight_radius_m"] and not a_flags:
        return "strong"
    return "moderate" if len(a_flags) <= 1 else "weak"


def _place(conn, claim, a, b, exts, at_place):
    place = claim["place"]
    target = {"lat": float(place["lat"]), "lon": float(place["lon"]), "radius_m": float(place["radius_m"])}
    rows = [dict(r) for r in conn.execute(text(
        "SELECT id, extraction_id, record_uid, coordinate_record_uid, field_path, record_type, source_kind, lat, lon, "
        "radius_m, start_utc, end_utc, offset_status, attribution_flags FROM pol_place_observation WHERE "
        "extraction_id = ANY(CAST(:e AS uuid[])) AND kind = ANY(:k) AND start_utc < :b AND end_utc >= :a "
        "ORDER BY start_utc, id"), {"e": list(exts), "k": list(ROUTINE_KINDS), "a": a - MARGIN, "b": b + MARGIN}).mappings()]
    items = []
    covered = {}
    for o in rows:
        kw = dict(at=o["start_utc"], end=o["end_utc"], record_uid=o["record_uid"], field_path=o["field_path"],
                  extraction_id=o["extraction_id"],
                  display={"type": o["record_type"], "source_kind": o["source_kind"], "radius_m": o["radius_m"],
                           "flags": list(o["attribution_flags"] or [])})
        if not _in_window(o["start_utc"], o["end_utc"], a, b):
            items.append(_item("context", "place_observation", o["id"], "near_window",
                               "Within 30 minutes of the time in the statement.", **kw))
            continue
        covered.setdefault(str(o["extraction_id"]), []).append(o["start_utc"])
        obs = {"lat": o["lat"], "lon": o["lon"], "radius_m": o["radius_m"], "start": o["start_utc"],
               "end": o["start_utc"], "offset_status": o["offset_status"]}
        v = colocation.verdict(obs, dict(target, start=o["start_utc"], end=o["start_utc"], offset_status="explicit"),
                               {"window_s": 0})
        flags = list(o["attribution_flags"] or []) + ([o["source_kind"]] if o["source_kind"] == "cell_reference" else [])
        strength = _place_strength(v, flags)
        kw["display"].update(distance_m=round(v["distance_m"], 1), radii_sum_m=round(v["radii_sum_m"], 1))
        if v["verdict"] == "compatible":
            role = "supporting" if at_place else "contradicting"
            items.append(_item(role, "place_observation", o["id"], "inside_place",
                               "The phone's position overlaps the place.", strength=strength, **kw))
        elif v["verdict"] == "separated":
            role = "contradicting" if at_place else "supporting"
            items.append(_item(role, "place_observation", o["id"], "away_from_place",
                               "The phone's position could not overlap the place.", strength=strength, **kw))
        else:
            items.append(_item("context", "place_observation", o["id"], "undetermined",
                               "Neither inside nor clearly away from the place.", strength=strength, **kw))
    gaps, pieces = _gap_items(conn, exts, a, b)
    items += gaps
    for e in exts:
        if not covered.get(e):
            items.append(_item("gap", "window_piece", "%s:no_location" % e, "no_location", GAP_WORDS["no_location"],
                               at=a, end=b, extraction_id=e))
    items += _payment_context(conn, claim["case_id"], a, b)
    return items, {"presence_observations": sum(len(v) for v in covered.values())}


def _payment_context(conn, case_id, a, b):
    out = []
    for r in conn.execute(text(
            "SELECT m.id, m.transaction_id, m.lat, m.lon, m.radius_m, coalesce(t.transaction_date, t.posted_date, "
            "t.ordering_date) AS day FROM pol_manual_place m JOIN financial_transactions t ON t.id = m.transaction_id "
            "WHERE m.case_id = :c AND m.removed_decision_id IS NULL AND t.ledger_status = 'admitted' AND "
            "coalesce(t.transaction_date, t.posted_date, t.ordering_date) BETWEEN CAST(:a AS date) - 1 AND "
            "CAST(:b AS date) + 1 ORDER BY day, m.id"), {"c": case_id, "a": a.date(), "b": b.date()}).mappings():
        out.append(_item("context", "transaction", r["transaction_id"], "payment_not_linked_to_person",
                         "A payment with a place a person attached. Bank accounts are not linked to phones or people, "
                         "so it is shown for context only.", display={"day": str(r["day"]), "radius_m": r["radius_m"]}))
    return out


def _together(conn, claim, a, b, exts, with_subject):
    other = _subject_exts(conn, claim["case_id"], claim["counterpart"], "counterpart")
    p = dict(colocation.DEFAULT_PARAMS)
    A = colocation._observations(conn, exts, a, b, False)
    B = colocation._observations(conn, other, a, b, False)
    pairs = colocation.sweep_pairs(A, B, p)
    rows = [{"at_utc": max(x["start"], y["start"]), "verdict": v["verdict"], "tight": v["tight"], "a": x, "b": y,
             "v": v} for x, y, v in pairs]
    items = []
    for ep in colocation.episodes(rows, p["episode_gap_s"]):
        together = ep["kind"] == "together"
        role = ("supporting" if together else "contradicting") if with_subject else \
            ("contradicting" if together else "supporting")
        strength = ("strong" if ep["breadth"] == "tight" else "moderate") if together else "strong"
        items.append(_item(role, "colocation", "%s:%s" % (ep["kind"], ep["start"].isoformat()),
                           "together_episode" if together else "apart_episode",
                           ("Both phones' positions overlap (%s)." % ep["breadth"]) if together else
                           "The two phones could not have been in one place.", strength=strength, at=ep["start"],
                           end=ep["end"], display={"pairs": ep["items"], "breadth": ep["breadth"]}))
    if not A or not B:
        items.append(_item("gap", "window_piece", "no_location_pair", "no_location",
                           "One of the two has no location recorded for this time.", at=a, end=b))
    return items, {"pairs_compared": len(pairs), "observations_subject": len(A), "observations_other": len(B)}


def _counterpart_keys(conn, claim):
    cp = claim["counterpart"]
    if isinstance(cp, dict) and cp.get("identity_ids"):
        return sorted(r[0] for r in conn.execute(text(
            "SELECT identity_key FROM phone_identities WHERE case_id = :c AND id = ANY(CAST(:i AS uuid[]))"),
            {"c": claim["case_id"], "i": [str(x) for x in cp["identity_ids"]]}))
    return sorted(r[0] for r in conn.execute(text(
        "SELECT i.identity_key FROM phone_identity_links l JOIN phone_identities i ON i.id = l.identity_id "
        "WHERE l.case_id = :c AND l.dossier_id = :d"), {"c": claim["case_id"], "d": cp.get("dossier_id")}))


def _contact(conn, claim, a, b, exts, no_contact):
    keys = _counterpart_keys(conn, claim)
    subject_keys = sorted(r[0] for r in conn.execute(text(
        "SELECT DISTINCT p.identity_key FROM pv_comm_party p WHERE p.extraction_id = ANY(CAST(:e AS uuid[])) AND "
        "p.is_phone_owner AND p.identity_key IS NOT NULL"), {"e": list(exts)}))  # an unnamed owner names no one
    if not keys:
        raise EvaluationError("The other side has no identity in the case to look for.", 422, fields=["counterpart"])
    case_exts = sorted({r[0] for r in conn.execute(text(
        "SELECT id::text FROM phone_extractions WHERE case_id = :c AND standing = 'active'"), {"c": claim["case_id"]})})
    rows = [dict(r) for r in conn.execute(text(
        "SELECT DISTINCT ON (ev.event_uid) ev.event_uid, ev.record_uid, ev.extraction_id::text AS extraction_id, ev.kind, "
        "ev.direction, ev.sort_instant, ev.time_field, ev.status, ev.call_status, ev.deleted_state, ev.app, "
        "ev.model_type FROM pv_comm_event ev JOIN pv_comm_party p ON p.event_uid = ev.event_uid AND p.extraction_id = "
        "ev.extraction_id WHERE ev.case_id = :c AND ev.sort_instant < :b AND ev.sort_instant >= :a AND "
        "p.identity_key = ANY(:k) AND (ev.extraction_id = ANY(CAST(:e AS uuid[])) OR EXISTS (SELECT 1 FROM "
        "pv_comm_party q WHERE q.event_uid = ev.event_uid AND q.extraction_id = ev.extraction_id AND q.identity_key = "
        "ANY(:sk))) ORDER BY ev.event_uid"),
        {"c": claim["case_id"], "a": a - MARGIN, "b": b + MARGIN, "k": keys, "e": list(exts),
         "sk": subject_keys or ["-"]}).mappings()]
    rows.sort(key=lambda r: (r["sort_instant"], str(r["event_uid"])))
    items = []
    for r in rows:
        on_subject = r["extraction_id"] in exts
        out_going = r["direction"] == "outgoing"
        status = (r["status"] or r["call_status"] or "").lower()
        if on_subject and out_going:
            strength, why = "strong", "Sent or placed by the phone's user."
        elif on_subject and r["kind"] == "call" and status in ("answered", "accepted", "connected", "incoming"):
            strength, why = "strong", "Answered by the phone's user."
        elif on_subject and status in ("read", "opened", "played"):
            strength, why = "moderate", "Received and read on the phone."
        elif on_subject:
            strength, why = "weak", "Received; not shown to have been read or answered."
        else:
            strength, why = ("strong" if r["direction"] == "incoming" else "moderate"), \
                "Seen on the other phone."
        kw = dict(at=r["sort_instant"], record_uid=r["record_uid"], field_path=r["time_field"],
                  extraction_id=r["extraction_id"],
                  display={"type": r["model_type"], "kind": r["kind"], "direction": r["direction"], "app": r["app"],
                           "seen_on_other_phone": not on_subject})
        if not _in_window(r["sort_instant"], None, a, b):
            items.append(_item("context", "comm_event", r["event_uid"], "near_window",
                               "Within 30 minutes of the time in the statement.", strength=strength, **kw))
            continue
        items.append(_item("contradicting" if no_contact else "supporting", "comm_event", r["event_uid"],
                           "contact" if on_subject else "contact_seen_on_other_phone", why, strength=strength, **kw))
        if r["deleted_state"] and r["deleted_state"] != "Intact":
            items.append(_item("gap", "comm_event", "%s:deleted" % r["event_uid"], "messages_may_be_deleted",
                               GAP_WORDS["messages_may_be_deleted"], at=r["sort_instant"],
                               extraction_id=r["extraction_id"]))
    spans = {}
    for e in exts:
        first, last = conn.execute(text(
            "SELECT min(sort_instant), max(sort_instant) FROM pv_comm_event WHERE extraction_id = :e AND kind IN "
            "('message','call','email')"), {"e": e}).one()
        spans[e] = bool(first and last and first <= a and last >= b)
        if not spans[e]:
            items.append(_item("gap", "window_piece", "%s:no_comm_coverage" % e, "no_comm_coverage",
                               GAP_WORDS["no_comm_coverage"], at=a, end=b, extraction_id=e))
    return items, {"phones_searched": len(case_exts), "identities": len(keys), "comm_span_covers_window": all(spans.values())}


# ---------------------------------------------------------------------------------------------------------------
# outcome

def counts_of(items) -> dict:
    c = {"contradicting": {"strong": 0, "moderate": 0, "weak": 0}, "supporting": {"strong": 0, "moderate": 0, "weak": 0},
         "gap": 0, "context": 0}
    for it in items:
        if it["role"] in ("gap", "context"):
            c[it["role"]] += 1
        else:
            c[it["role"]][it["strength"] if it["strength"] in ("strong", "moderate", "weak") else "weak"] += 1
    return c


def outcome(kind, items, summary):
    c = counts_of(items)
    con, sup = c["contradicting"], c["supporting"]
    n_con, n_sup = sum(con.values()), sum(sup.values())
    if kind in ("inactive", "no_contact"):
        if con["strong"]:
            return "contradicted", "%d strong undercutting item%s" % (con["strong"], "" if con["strong"] == 1 else "s")
        if n_con:
            return "contradicted_weakly", "%d undercutting item%s, none strong" % (n_con, "" if n_con == 1 else "s")
        if kind == "inactive":
            share = summary.get("recording_share_without_use", 0)
            if share >= COVER_SHARE:
                return "consistent", "no undercutting item; recording without use for %d%% of the time" % int(share * 100)
            return "insufficient_data", "recording without use for only %d%% of the time" % int(share * 100)
        if summary.get("comm_span_covers_window"):
            return "consistent", "no contact found; messages and calls cover the time"
        return "insufficient_data", "the phones' messages and calls do not cover the whole time"
    if kind == "active":
        if n_sup:
            return "supported", "%d item%s showing use" % (n_sup, "" if n_sup == 1 else "s")
        share = summary.get("recording_share_without_use", 0)
        if share >= COVER_SHARE:
            return "contradicted", "no use while recording for %d%% of the time" % int(share * 100)
        return "insufficient_data", "no use seen, and recording for only %d%% of the time" % int(share * 100)
    if kind == "contact":
        if n_sup:
            return "supported", "%d contact item%s" % (n_sup, "" if n_sup == 1 else "s")
        if summary.get("comm_span_covers_window"):
            return "contradicted", "no contact found; messages and calls cover the time"
        return "insufficient_data", "no contact found, and the phones' messages and calls do not cover the time"
    # at_place / not_at_place / with_subject / apart_from_subject, in 9.4's order: a strong undercutting item decides
    if not n_con and not n_sup:
        return "insufficient_data", "no positions to compare"
    if con["strong"]:
        return "contradicted", "%d strong undercutting item%s" % (con["strong"], "" if con["strong"] == 1 else "s")
    if n_sup and n_con:
        return "mixed", "%d supporting and %d undercutting items, none undercutting strongly" % (n_sup, n_con)
    if n_con:
        return "contradicted_weakly", "%d undercutting item%s, none strong" % (n_con, "" if n_con == 1 else "s")
    return "supported", "%d supporting item%s and none undercutting" % (n_sup, "" if n_sup == 1 else "s")


_NEEDS = {"inactive": ("activity records", "pol_activity_event"), "active": ("activity records", "pol_activity_event"),
          "at_place": ("location records", "pol_place_observation"),
          "not_at_place": ("location records", "pol_place_observation"),
          "with_subject": ("location records", "pol_place_observation"),
          "apart_from_subject": ("location records", "pol_place_observation"),
          "contact": ("messages or calls", "pv_comm_event"), "no_contact": ("messages or calls", "pv_comm_event")}


def no_record_reason(conn, claim, exts, items) -> tuple | None:
    """``(code, words)`` when the subject's phones cannot hold the record the statement needs for its window, else
    None. Only an ``insufficient_data`` outcome is turned into ``no_record``: a supporting or undercutting item means
    the phone holds records for the time. Checked in order: no record of the kind on any subject phone; the whole
    window before the first or after the last such record on every phone; every piece of the window after the
    extraction or outside the production's selection."""
    what, table = _NEEDS[claim["kind"]]
    a, b = claim["window_start"], claim["window_end"]
    has_kind = conn.execute(text("SELECT EXISTS (SELECT 1 FROM %s WHERE extraction_id = ANY(CAST(:e AS uuid[])))"
                                 % table), {"e": list(exts)}).scalar()
    if not has_kind:
        return "not_extracted", NO_RECORD_REASONS["not_extracted"] % what
    # the extraction's coverage: its first and last timed record of any kind, on every subject phone together
    first, last = conn.execute(text("SELECT min(instant_utc), max(coalesce(end_utc, instant_utc)) FROM "
                                    "pol_activity_event WHERE extraction_id = ANY(CAST(:e AS uuid[]))"),
                               {"e": list(exts)}).first()
    if first is not None and (b <= first or a > last):
        return "outside_coverage", NO_RECORD_REASONS["outside_coverage"] % (first.date().isoformat(),
                                                                             last.date().isoformat())
    gaps = [it for it in items if it["role"] == "gap" and it["ref_kind"] == "window_piece"
            and it["reason_code"] in GAP_STATES]
    for code, states in (("after_extraction", {"after_extraction"}),
                         ("not_selected", {"outside_selection", "not_selected"})):
        for e in exts:
            mine = sorted((g for g in gaps if g["extraction_id"] == str(e)), key=lambda g: g["at_utc"])
            covered, at = True, a
            for g in mine:
                if g["reason_code"] not in states or g["at_utc"] > at:
                    covered = False
                    break
                at = max(at, g["end_utc"])
            if not mine or not covered or at < b:
                break
        else:
            return code, NO_RECORD_REASONS[code]
    return None


def words_for(kind, out):
    w = OUTCOME_WORDS[out]
    if isinstance(w, dict):
        return w.get(kind) or "Nothing on the phones undercuts this statement."
    return w


def not_yet_checked(conn, claim, exts, a, b) -> list:
    """"What would contradict this?": what the check could not read, as counts."""
    out = []
    n = conn.execute(text("SELECT count(*) FROM pol_unplaced_tower WHERE extraction_id = ANY(CAST(:e AS uuid[]))"),
                     {"e": list(exts)}).scalar() or 0
    if n and claim["kind"] in claims.PLACE_KINDS + claims.SUBJECT_KINDS:
        out.append({"code": "towers_not_placed", "count": n,
                    "words": "%d cell tower sighting%s on the phone could not be placed." % (n, "" if n == 1 else "s")})
    if claim["kind"] in ("inactive", "active"):
        out.append({"code": "app_usage_not_read", "count": None,
                    "words": "App usage and log records are not read as use of the phone."})
    if claim["kind"] in claims.PLACE_KINDS:
        out.append({"code": "media_not_placed", "count": None,
                    "words": "Photo locations are not used until a photo is shown to be taken on this phone."})
    return out


# ---------------------------------------------------------------------------------------------------------------
# run, read, stale, dispute

KIND_FN = {"inactive": lambda c, cl, a, b, e: _activity(c, cl, a, b, e, True),
           "active": lambda c, cl, a, b, e: _activity(c, cl, a, b, e, False),
           "at_place": lambda c, cl, a, b, e: _place(c, cl, a, b, e, True),
           "not_at_place": lambda c, cl, a, b, e: _place(c, cl, a, b, e, False),
           "with_subject": lambda c, cl, a, b, e: _together(c, cl, a, b, e, True),
           "apart_from_subject": lambda c, cl, a, b, e: _together(c, cl, a, b, e, False),
           "no_contact": lambda c, cl, a, b, e: _contact(c, cl, a, b, e, True),
           "contact": lambda c, cl, a, b, e: _contact(c, cl, a, b, e, False)}


def compute(conn, claim) -> dict:
    if claim["status"] != "confirmed":
        raise EvaluationError("Only a confirmed statement is checked.", 422, fields=["status"])
    inp = inputs(conn, claim)
    a, b = claim["window_start"], claim["window_end"]
    items, summary = KIND_FN[claim["kind"]](conn, claim, a, b, inp["subject_extractions"])
    order = {"contradicting": 0, "supporting": 1, "gap": 2, "context": 3}
    items.sort(key=lambda it: (order[it["role"]], it["at_utc"] or a, it["ref_kind"], it["ref_id"]))
    out, basis = outcome(claim["kind"], items, summary)
    if out == "insufficient_data":
        why = no_record_reason(conn, claim, inp["subject_extractions"], items)
        if why:
            out, basis = "no_record", why[1]
            summary = dict(summary, no_record_reason=why[0])
    summary = dict(summary, not_yet_checked=not_yet_checked(conn, claim, inp["subject_extractions"], a, b),
                   words=words_for(claim["kind"], out))
    return {"inputs": inp, "fingerprint": fingerprint(inp), "items": items, "outcome": out, "outcome_basis": basis,
            "summary": summary, "counts": counts_of(items)}


def evaluate(conn, case_id, claim_id, requested_by) -> dict:
    claim = claims.get(conn, case_id, claim_id, raw=True)
    res = compute(conn, claim)
    eid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_claim_evaluation (id, case_id, claim_id, claim_version, requested_by, inputs, inputs_fingerprint, "
        "outcome, outcome_basis, summary, counts) VALUES (:i, :c, :cl, :v, :r, CAST(:inp AS jsonb), :f, :o, :ob, "
        "CAST(:s AS jsonb), CAST(:n AS jsonb))"),
        {"i": eid, "c": case_id, "cl": claim_id, "v": claim["version"], "r": requested_by,
         "inp": json.dumps(res["inputs"], default=str), "f": res["fingerprint"], "o": res["outcome"],
         "ob": res["outcome_basis"], "s": json.dumps(res["summary"], default=str), "n": json.dumps(res["counts"])})
    # every item is stored (a busy day gives tens of thousands of context items), so they go in by COPY
    from services.phone import generic
    w = generic.Writer(conn, {"pol_claim_evaluation_item": ITEM_COLUMNS})
    for n, it in enumerate(res["items"]):
        w.add("pol_claim_evaluation_item", dict(it, evaluation_id=eid, ordinal=n,
                                                display=json.dumps(it["display"], default=str)))
    w._flush()
    return read(conn, case_id, eid)


ITEM_COLUMNS = ("evaluation_id", "ordinal", "role", "ref_kind", "ref_id", "strength", "reason_code", "explanation",
                "record_uid", "field_path", "extraction_id", "at_utc", "end_utc", "display")


def is_stale(conn, ev) -> bool:
    claim = claims.get(conn, ev["case_id"], ev["claim_id"], raw=True)
    if claim["version"] != ev["claim_version"] or claim["status"] != "confirmed":
        return True
    try:
        return fingerprint(inputs(conn, claim)) != ev["inputs_fingerprint"]
    except claims.ClaimError:
        return True


def read(conn, case_id, evaluation_id) -> dict:
    ev = conn.execute(text("SELECT * FROM pol_claim_evaluation WHERE id = :i AND case_id = :c"),
                      {"i": evaluation_id, "c": case_id}).mappings().first()
    if ev is None:
        raise EvaluationError("That check is not in this case.", 404)
    ev = dict(ev)
    items = [dict(r) for r in conn.execute(text(
        "SELECT * FROM pol_claim_evaluation_item WHERE evaluation_id = :i ORDER BY ordinal"), {"i": evaluation_id}).mappings()]
    disputes = {r["ordinal"]: dict(r) for r in conn.execute(text(
        "SELECT ordinal, reason, actor_name, created_at FROM pol_claim_item_dispute WHERE evaluation_id = :i AND "
        "withdrawn_at IS NULL"), {"i": evaluation_id}).mappings()}
    for it in items:
        it.pop("evaluation_id", None)
        it["disputed"] = disputes.get(it["ordinal"])
    claim = claims.get(conn, case_id, ev["claim_id"], raw=True)
    return {"evaluation_id": ev["id"], "claim_id": ev["claim_id"], "claim_version": ev["claim_version"],
            "evaluated_at": ev["evaluated_at"], "requested_by": ev["requested_by"], "outcome": ev["outcome"],
            "outcome_basis": ev["outcome_basis"], "outcome_words": ev["summary"].get("words"),
            "stale": is_stale(conn, ev), "window": {"start": claim["window_start"], "end": claim["window_end"],
                                                    "zone": claim["window_zone"]},
            "summary": ev["summary"], "counts": ev["counts"], "inputs": ev["inputs"],
            "inputs_fingerprint": ev["inputs_fingerprint"], "total_items": len(items), "items": items,
            "disputed_items": len(disputes)}


GROUP_PAGE = 1000


def group_events(conn, case_id, evaluation_id, ordinal, cursor=0) -> dict:
    """The events of one context group (04 decision 37), from the current projection, paged; with the count the check
    stored, so a group whose events changed since the check says so."""
    ev = read_head(conn, case_id, evaluation_id)
    it = conn.execute(text("SELECT ref_kind, ref_id, display FROM pol_claim_evaluation_item WHERE evaluation_id = :i "
                           "AND ordinal = :o"), {"i": evaluation_id, "o": ordinal}).mappings().first()
    if it is None or it["ref_kind"] != "event_group":
        raise EvaluationError("That item is not a group of events in this check.", 404)
    ext, reason = it["ref_id"].split(":", 1)[0], it["ref_id"].rsplit(":", 1)[1]
    hour = datetime.fromisoformat(it["display"]["hour_utc"])
    a, b = ev["window"]["start"], ev["window"]["end"]
    # the same rule as _context_groups, narrowed to the group's phone, hour and reason
    p = {"e": [ext], "lo": a - MARGIN, "hi": b + MARGIN, "a": a, "b": b, "inactive": ev["kind"] == "inactive",
         "hour": hour.astimezone(timezone.utc).replace(tzinfo=None), "reason": reason}
    where = " WHERE " + _CONTEXT + " AND " + _HOUR + " = :hour AND " + _REASON + " = :reason"
    total = conn.execute(text("SELECT count(*) FROM " + _overlap(_CONTEXT_COLUMNS) + where), p).scalar_one()
    page = [dict(r) for r in conn.execute(text(
        "SELECT * FROM " + _overlap(_EVENT_COLUMNS) + where + " ORDER BY instant_utc, id "
        "LIMIT :lim OFFSET :off"), dict(p, lim=GROUP_PAGE, off=max(int(cursor), 0))).mappings()]
    nxt = cursor + len(page)
    return {"ordinal": ordinal, "stored_count": it["display"]["count"], "total": total, "cursor": cursor,
            "limit": GROUP_PAGE, "returned": len(page), "next_cursor": nxt if nxt < total else None,
            "changed_since_check": total != it["display"]["count"],
            "items": [{"activity_event_id": e["id"], "at_utc": e["instant_utc"], "end_utc": e["end_utc"],
                       "record_uid": str(e["record_uid"]) if e["record_uid"] else None, "field_path": e["field_path"],
                       "display": _event_display(e)} for e in page]}


def read_head(conn, case_id, evaluation_id) -> dict:
    """The evaluation's window and claim kind as the check ran them (the claim's revision at the checked version; a
    statement edited since keeps its old check), without its items."""
    ev = conn.execute(text(
        "SELECT e.claim_id, c.kind, c.window_start, c.window_end, r.snapshot FROM pol_claim_evaluation e JOIN "
        "pol_claim c ON c.id = e.claim_id LEFT JOIN pol_claim_revision r ON r.claim_id = e.claim_id AND "
        "r.version = e.claim_version WHERE e.id = :i AND e.case_id = :c"),
        {"i": evaluation_id, "c": case_id}).mappings().first()
    if ev is None:
        raise EvaluationError("That check is not in this case.", 404)
    snap = ev["snapshot"] or {}
    if snap.get("window_start") and snap.get("window_end") and snap.get("kind"):
        return {"claim_id": ev["claim_id"], "kind": snap["kind"],
                "window": {"start": datetime.fromisoformat(snap["window_start"]),
                           "end": datetime.fromisoformat(snap["window_end"])}}
    return {"claim_id": ev["claim_id"], "kind": ev["kind"],
            "window": {"start": ev["window_start"], "end": ev["window_end"]}}


def list_evaluations(conn, case_id, claim_id) -> dict:
    claims.get(conn, case_id, claim_id, raw=True)
    rows = [dict(r) for r in conn.execute(text(
        "SELECT * FROM pol_claim_evaluation WHERE claim_id = :c AND case_id = :k ORDER BY evaluated_at, id"),
        {"c": claim_id, "k": case_id}).mappings()]
    out = [{"evaluation_id": r["id"], "claim_version": r["claim_version"], "evaluated_at": r["evaluated_at"],
            "outcome": r["outcome"], "outcome_basis": r["outcome_basis"], "counts": r["counts"],
            "stale": is_stale(conn, r)} for r in rows]
    return {"total": len(out), "items": out}


def dispute(db, case_id, evaluation_id, ordinal, reason, actor) -> dict:
    """Mark an item wrong with a typed reason (9.5). Recorded as a decision on the record (or payment) it names; an
    item with no record of its own (a window piece, a together episode) is marked with the reason alone."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from services.financial import decisions
    if not isinstance(reason, str) or not reason.strip():
        raise EvaluationError("Say why the item is wrong.", fields=["reason"])
    conn = db.connection()
    ev = conn.execute(text("SELECT id, claim_id FROM pol_claim_evaluation WHERE id = :i AND case_id = :c"),
                      {"i": evaluation_id, "c": case_id}).first()
    if ev is None:
        raise EvaluationError("That check is not in this case.", 404)
    it = conn.execute(text("SELECT * FROM pol_claim_evaluation_item WHERE evaluation_id = :i AND ordinal = :o"),
                      {"i": evaluation_id, "o": ordinal}).mappings().first()
    if it is None:
        raise EvaluationError("That item is not in this check.", 404)
    if conn.execute(text("SELECT 1 FROM pol_claim_item_dispute WHERE evaluation_id = :i AND ordinal = :o AND "
                         "withdrawn_at IS NULL"), {"i": evaluation_id, "o": ordinal}).scalar():
        raise EvaluationError("That item is already marked wrong.", 409)
    payload = {"evaluation_id": str(evaluation_id), "ordinal": ordinal, "ref_kind": it["ref_kind"], "ref_id": it["ref_id"]}
    decision_id = None
    subject = _decision_subject(db, case_id, it)
    if subject is not None:
        st = AdjudicationSubject.transaction if it["ref_kind"] == "transaction" else AdjudicationSubject.phone_record
        row = decisions.record(db, case_id=case_id, subject=subject, subject_type=st,
                               decision=AdjudicationDecision.dispute_check_item, reason=reason.strip(), actor=actor,
                               before={"disputed": None}, after={"disputed": payload})
        decision_id = row.id
    did = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_claim_item_dispute (id, case_id, evaluation_id, ordinal, ref_kind, ref_id, reason, decision_id, "
        "actor_name, actor_email) VALUES (:i, :c, :e, :o, :rk, :ri, :r, :d, :an, :ae)"),
        {"i": did, "c": case_id, "e": evaluation_id, "o": ordinal, "rk": it["ref_kind"], "ri": it["ref_id"],
         "r": reason.strip(), "d": decision_id, "an": actor.name, "ae": actor.email})
    from services import manual_changes
    manual_changes.record_change(db, "statement_check_item", case_id, {"type": "statement_check", "id": str(evaluation_id)},
                                 {"disputed": None}, {"disputed": payload}, actor, reason.strip(),
                                 link="/cases/%s/phone-patterns" % case_id,
                                 pattern_key=manual_changes.make_pattern_key("statement_check_item"))
    return {"dispute_id": str(did), "decision_id": str(decision_id) if decision_id else None}


def _decision_subject(db, case_id, it):
    if it["ref_kind"] == "transaction":
        from postgres.models.financial import FinancialTransaction
        return db.get(FinancialTransaction, uuid.UUID(it["ref_id"]))
    if not it["record_uid"]:
        return None
    from postgres.models.phone_identity import PhoneRecordSubject
    s = db.get(PhoneRecordSubject, it["record_uid"])
    if s is None:
        row = db.connection().execute(text(
            "SELECT r.extraction_id, r.document_index, r.ordinal FROM phone_record_summaries r JOIN "
            "phone_interpretation_state s ON s.extraction_id = r.extraction_id AND s.generation = r.generation "
            "WHERE r.record_uid = :r"), {"r": it["record_uid"]}).first()
        if row is None:
            return None
        s = PhoneRecordSubject(id=it["record_uid"], case_id=case_id, extraction_id=row[0], document_index=row[1],
                               ordinal=row[2])
        db.add(s)
        db.flush()
    return s


def withdraw_dispute(db, case_id, evaluation_id, ordinal, reason, actor) -> dict:
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from services.financial import decisions
    if not isinstance(reason, str) or not reason.strip():
        raise EvaluationError("Say why the mark is withdrawn.", fields=["reason"])
    conn = db.connection()
    d = conn.execute(text("SELECT * FROM pol_claim_item_dispute WHERE case_id = :c AND evaluation_id = :e AND "
                          "ordinal = :o AND withdrawn_at IS NULL"),
                     {"c": case_id, "e": evaluation_id, "o": ordinal}).mappings().first()
    if d is None:
        raise EvaluationError("That item is not marked wrong.", 409)
    it = conn.execute(text("SELECT * FROM pol_claim_evaluation_item WHERE evaluation_id = :i AND ordinal = :o"),
                      {"i": evaluation_id, "o": ordinal}).mappings().first()
    wid = None
    subject = _decision_subject(db, case_id, it) if d["decision_id"] else None
    if subject is not None:
        st = AdjudicationSubject.transaction if it["ref_kind"] == "transaction" else AdjudicationSubject.phone_record
        payload = {"evaluation_id": str(evaluation_id), "ordinal": ordinal, "ref_kind": it["ref_kind"],
                   "ref_id": it["ref_id"]}
        wid = decisions.record(db, case_id=case_id, subject=subject, subject_type=st,
                               decision=AdjudicationDecision.withdraw_check_item_dispute, reason=reason.strip(),
                               actor=actor, before={"disputed": payload}, after={"disputed": None}).id
    conn.execute(text("UPDATE pol_claim_item_dispute SET withdrawn_at = clock_timestamp(), withdrawn_decision_id = :w "
                      "WHERE id = :i"), {"i": d["id"], "w": wid})
    return {"withdrawn": str(d["id"])}


# ---------------------------------------------------------------------------------------------------------------
# attaching to Workspace (9.6) and the statement_check link type

ROLE_RELATIONSHIP = {"contradicting": "contradicts", "supporting": "supports", "context": "context", "gap": "context"}
OUTCOME_RELATIONSHIP = {"contradicted": "contradicts", "contradicted_weakly": "contradicts", "supported": "supports",
                        "consistent": "supports"}


def _versions_of(inputs_json) -> dict:
    out = {}
    for e, st in sorted((inputs_json.get("extractions") or {}).items()):
        p = st.get("projection") or {}
        out[e] = {"generation": st.get("generation"), "activity_mapping_version": p.get("activity_mapping_version"),
                  "meaning_mapping_version": p.get("meaning_mapping_version"),
                  "attribution_mapping_version": p.get("attribution_mapping_version")}
    return out


def resolve_statement_check(db, case_id, target_id):
    from postgres import link_types
    try:
        eid = uuid.UUID(str(target_id))
    except (TypeError, ValueError):
        return None
    row = db.execute(text("SELECT e.id, e.outcome, e.inputs, e.evaluated_at, c.kind, c.window_text FROM "
                          "pol_claim_evaluation e JOIN pol_claim c ON c.id = e.claim_id WHERE e.id = :i AND "
                          "e.case_id = :c"), {"i": eid, "c": case_id}).mappings().first()
    if row is None:
        return None
    label = "Statement check: %s (%s)" % (row["window_text"] or row["kind"], row["outcome"].replace("_", " "))
    return link_types.PhoneTarget(label=label[:512], mapping_versions=_versions_of(row["inputs"]),
                                  metadata={"evaluation_id": str(row["id"]), "outcome": row["outcome"]})


def register():
    from postgres import link_types
    link_types.register_phone_resolver("statement_check", resolve_statement_check)


def attach(db, case_id, evaluation_id, *, entry_id, expected_version, item_ordinals, include_check_link, user,
           rationale=None) -> dict:
    """Links the chosen items to a finding or theory (never automatically). Each item links its record; the check
    itself links once with the outcome's relationship."""
    from services.workspace_entry_service import add_entry_links
    ev = read(db.connection(), case_id, evaluation_id)
    by_ord = {it["ordinal"]: it for it in ev["items"]}
    unknown = [o for o in item_ordinals if o not in by_ord]
    if unknown:
        raise EvaluationError("These items are not in the check: %s." % ", ".join(map(str, unknown)), 404)
    links, skipped = [], []
    for o in item_ordinals:
        it = by_ord[o]
        if not it["record_uid"]:
            skipped.append({"ordinal": o, "reason": "This item names no record (a period or an episode); it is "
                                                    "carried by the check's own link."})
            continue
        links.append({"target_type": "phone_record", "target_id": str(it["record_uid"]),
                      "relationship": ROLE_RELATIONSHIP[it["role"]],
                      "source_anchor": {"time_field": it["field_path"],
                                        "instant_utc": it["at_utc"].isoformat() if it["at_utc"] else None},
                      "metadata": {"field_path": it["field_path"], "evaluation_id": str(evaluation_id),
                                   "claim_id": str(ev["claim_id"]), "strength": it["strength"],
                                   "reason_code": it["reason_code"], "role": it["role"]}})
    if include_check_link:
        links.append({"target_type": "statement_check", "target_id": str(evaluation_id),
                      "relationship": OUTCOME_RELATIONSHIP.get(ev["outcome"], "context"),
                      "metadata": {"claim_id": str(ev["claim_id"]), "outcome": ev["outcome"],
                                   "inputs_fingerprint": ev["inputs_fingerprint"]}})
    if not links:
        raise EvaluationError("Nothing to attach: none of the chosen items names a record, and the check's own link "
                              "was not asked for.", 422)
    out = add_entry_links(db, case_id=case_id, entry_id=entry_id, current_user=user,
                          expected_version=expected_version, links=links,
                          rationale=rationale or "Attached from a statement check.", ignore_existing=True,
                          commit=False)
    return {"result": out, "requested": len(item_ordinals), "linked_items": len(links) - int(bool(include_check_link)),
            "skipped": skipped}
