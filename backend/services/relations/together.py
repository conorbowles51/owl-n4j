"""Where two or more phones were together, and who they both dealt with (lx-phonetogether B, D).

One read for the Map, the Timeline and Conversations: *together* places (same 15-minute slot and same 550 m square on
two phones, merged into meetings), *shared contacts* and *relay chains*. Read-only SQL scoped to the case. Each item
carries the record ids it rests on. The answer says what was searched and what was out of reach; no result is never
blank, it reads "no meeting found in <what was searched>".

Decisions (reverse by editing the named constant):
- A cell is one phone pair, one 15-minute slot and one 550 m square, the definition lx-overlaps measured (10 cells on
  Phone reference 1). Positions of the same phone in a cell count once (``readings`` keeps the raw number).
  Two positions either side of a slot or square edge are not paired; the answer says so. ``SLOT_S``, ``SQUARE_DEG``.
- Cells of one pair in one square merge into one meeting while the gap between them is at most ``MERGE_GAP_S``.
- A place is busy when ``BUSY_OTHER_PHONES`` or more other phones of the case also have a position in the square.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

SLOT_S = 900
SQUARE_DEG = 0.005          # about 550 m
MERGE_GAP_S = 2 * 3600
BUSY_OTHER_PHONES = 2
MAX_PHONES = 8
RECORD_CAP = 25             # record ids listed per side of a meeting; the total is stated beside them
FINE_ACCURACY_M = 100.0
PLACE_WORDS = "same 15-minute slot and same 550 m square"


class TogetherError(ValueError):
    pass


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None, name: str) -> datetime | None:
    """A date alone is the whole day: 'from' its start, 'to' its end (so a last day is not cut at midnight)."""
    if not value:
        return None
    try:
        out = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TogetherError(f"'{name}' is not a date and time.")
    if len(value.strip()) == 10 and name == "to":
        out = out + timedelta(days=1) - timedelta(microseconds=1)
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


def _span(start, end) -> str:
    if start and end:
        return f"{start:%Y-%m-%d} to {end:%Y-%m-%d}"
    if start:
        return f"from {start:%Y-%m-%d}"
    if end:
        return f"up to {end:%Y-%m-%d}"
    return "the whole period of the case"


def cells(conn, case_id: str, phones: list[str], start, end) -> tuple[list[dict], dict]:
    rows = conn.execute(text(f"""
        WITH p AS (SELECT extraction_id e, floor(extract(epoch FROM instant) / {SLOT_S}) AS bin,
                          round(lat / {SQUARE_DEG}) AS la, round(lon / {SQUARE_DEG}) AS lo,
                          count(*) AS n, avg(lat) AS lat, avg(lon) AS lon, min(accuracy_m) AS acc,
                          array_agg(DISTINCT source_kind) AS src, array_agg(DISTINCT record_uid::text) AS uids
                   FROM phone_location_points
                   WHERE case_id = CAST(:c AS uuid) AND extraction_id = ANY(CAST(:e AS uuid[]))
                     AND instant IS NOT NULL AND lat IS NOT NULL
                     AND (CAST(:s AS timestamptz) IS NULL OR instant >= CAST(:s AS timestamptz))
                     AND (CAST(:t AS timestamptz) IS NULL OR instant <= CAST(:t AS timestamptz))
                   GROUP BY 1, 2, 3, 4)
        SELECT a.e, b.e, a.bin, a.la, a.lo, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2,
               a.n, b.n, a.acc, b.acc, a.src, b.src, a.uids, b.uids
        FROM p a JOIN p b ON a.bin = b.bin AND a.la = b.la AND a.lo = b.lo AND a.e < b.e
        ORDER BY a.e, b.e, a.la, a.lo, a.bin"""), {"c": case_id, "e": phones, "s": start, "t": end}).fetchall()
    read = conn.execute(text(
        "SELECT count(*), count(instant) FROM phone_location_points WHERE case_id = CAST(:c AS uuid) "
        "AND extraction_id = ANY(CAST(:e AS uuid[])) AND lat IS NOT NULL"), {"c": case_id, "e": phones}).first()
    out = []
    for r in rows:
        out.append({"a": str(r[0]), "b": str(r[1]), "bin": int(r[2]), "sq": (int(r[3]), int(r[4])),
                    "lat": float(r[5]), "lon": float(r[6]), "readings": int(r[7]) + int(r[8]),
                    "acc": [float(x) for x in (r[9], r[10]) if x is not None], "src": sorted(set(r[11]) | set(r[12])),
                    "uids_a": list(r[13]), "uids_b": list(r[14])})
    return out, {"positions": int(read[0] or 0), "with_time": int(read[1] or 0)}


def _merge(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in rows:
        groups[(c["a"], c["b"], c["sq"])].append(c)
    meetings = []
    for (a, b, sq), cs in groups.items():
        cs.sort(key=lambda c: c["bin"])
        run = [cs[0]]
        for c in cs[1:]:
            if (c["bin"] - run[-1]["bin"]) * SLOT_S <= MERGE_GAP_S:
                run.append(c)
            else:
                meetings.append((a, b, sq, run))
                run = [c]
        meetings.append((a, b, sq, run))
    out = []
    for a, b, sq, run in meetings:
        first, last = run[0]["bin"] * SLOT_S, run[-1]["bin"] * SLOT_S + SLOT_S
        uids_a = sorted({u for c in run for u in c["uids_a"]})
        uids_b = sorted({u for c in run for u in c["uids_b"]})
        accs = [x for c in run for x in c["acc"]]
        sources = sorted({s for c in run for s in c["src"]})
        days = sorted({datetime.fromtimestamp(c["bin"] * SLOT_S, timezone.utc).date().isoformat() for c in run})
        key = f"{a}:{b}:{sq[0]}:{sq[1]}:{run[0]['bin']}"
        out.append({
            "id": hashlib.sha1(key.encode()).hexdigest()[:16], "phones": [a, b], "square": sq,
            "start": datetime.fromtimestamp(first, timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(last, timezone.utc).isoformat(),
            "cells": len(run), "readings": sum(c["readings"] for c in run), "days": days,
            "place": {"lat": sum(c["lat"] for c in run) / len(run), "lon": sum(c["lon"] for c in run) / len(run),
                      "square_m": 550},
            "precision": {"best_accuracy_m": min(accs) if accs else None, "accuracy_stated": bool(accs),
                          "sources": sources,
                          "level": "fine" if accs and min(accs) <= FINE_ACCURACY_M else "coarse"},
            "records": {a: uids_a[:RECORD_CAP], b: uids_b[:RECORD_CAP]},
            "records_total": {a: len(uids_a), b: len(uids_b)},
        })
    return sorted(out, key=lambda m: (m["start"], m["id"]))


def _busy(conn, case_id: str, meetings: list[dict], start, end) -> int:
    """Per meeting: the other phones of the case with a position in the same square in the period, and how many of
    the case's phones have positions at all. Returns the number of phones in the case with a position."""
    total = conn.execute(text(
        "SELECT count(DISTINCT extraction_id) FROM phone_location_points WHERE case_id = CAST(:c AS uuid) "
        "AND lat IS NOT NULL"), {"c": case_id}).scalar() or 0
    for sq in {m["square"] for m in meetings}:
        got = {str(r[0]): int(r[1]) for r in conn.execute(text(
            "SELECT extraction_id, count(DISTINCT instant::date) FROM phone_location_points "
            "WHERE case_id = CAST(:c AS uuid) AND lat IS NOT NULL AND instant IS NOT NULL "
            "AND round(lat / :q) = :la AND round(lon / :q) = :lo "
            "AND (CAST(:s AS timestamptz) IS NULL OR instant >= CAST(:s AS timestamptz)) "
            "AND (CAST(:t AS timestamptz) IS NULL OR instant <= CAST(:t AS timestamptz)) GROUP BY 1"),
            {"c": case_id, "q": SQUARE_DEG, "la": sq[0], "lo": sq[1], "s": start, "t": end})}
        for m in meetings:
            if m["square"] != sq:
                continue
            others = {k: v for k, v in got.items() if k not in m["phones"]}
            busy = len(others) >= BUSY_OTHER_PHONES
            m["busy"] = {"other_phones": len(others), "phones_total": int(total), "is_busy": busy,
                         "words": (f"{len(others)} other phones of the {total} in the case also have positions in this "
                                   f"550 m square in the period, so being here at one time is weak evidence of meeting."
                                   if busy else
                                   f"{len(others)} other of the {total} phones in the case have positions in this "
                                   f"550 m square in the period.")}
    return int(total)


def shared_contacts(conn, case_id: str, phones: list[str], start, end) -> tuple[list[dict], dict]:
    """People (a confirmed person, else one identity) with records on at least two of the chosen phones. A copy of a
    record on one phone (same duplicate group) counts once."""
    rows = conn.execute(text("""
        WITH x AS (SELECT e.extraction_id AS ext, coalesce('person:' || l.dossier_id::text, p.identity_key) AS g,
                          min(e.record_uid::text) AS uid, min(e.sort_instant) AS t, min(i.value_display) AS shown
                   FROM phone_comm_events e
                   JOIN phone_participations p ON p.record_uid = e.record_uid AND p.generation = e.generation
                   JOIN phone_interpretation_state st ON st.extraction_id = e.extraction_id AND st.generation = e.generation
                   JOIN phone_extractions x_ ON x_.id = e.extraction_id AND x_.standing = 'active'
                   LEFT JOIN phone_identities i ON i.case_id = e.case_id AND i.identity_key = p.identity_key
                   LEFT JOIN phone_identity_links l ON l.identity_id = i.id
                   WHERE e.case_id = CAST(:c AS uuid) AND e.extraction_id = ANY(CAST(:e AS uuid[]))
                     AND e.kind IN ('message', 'call', 'email') AND p.identity_key IS NOT NULL
                     AND NOT coalesce(p.is_phone_owner, false)
                     AND (CAST(:s AS timestamptz) IS NULL OR e.sort_instant >= CAST(:s AS timestamptz))
                     AND (CAST(:t AS timestamptz) IS NULL OR e.sort_instant <= CAST(:t AS timestamptz))
                   GROUP BY e.extraction_id, 2, coalesce(e.dup_group_uid, e.record_uid::text)),
             shared AS (SELECT g FROM x GROUP BY g HAVING count(DISTINCT ext) >= 2)
        SELECT ext, uid, t, g, shown FROM x WHERE g IN (SELECT g FROM shared)"""),
        {"c": case_id, "e": phones, "s": start, "t": end}).fetchall()
    read = conn.execute(text(
        "SELECT count(*) FROM pv_comm_event WHERE case_id = CAST(:c AS uuid) AND extraction_id = ANY(CAST(:e AS uuid[])) "
        "AND kind IN ('message', 'call', 'email')"), {"c": case_id, "e": phones}).scalar() or 0
    by: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    names: dict[str, str] = {}
    for ext, uid, when, g, shown in rows:
        by[g][str(ext)].append((when, "", uid))
        if shown and (g not in names or shown < names[g]):
            names[g] = shown
    out = []
    for g, per in by.items():
        if len(per) < 2:
            continue
        timed = sorted(w for v in per.values() for w, _, _ in v if w)
        label = names.get(g, g)
        out.append({
            "id": hashlib.sha1(g.encode()).hexdigest()[:16], "label": label,
            "basis": "confirmed person" if g.startswith("person:") else "one identity (same number, address or account)",
            "phones": {ext: {"records": len(v), "first": _iso(min((w for w, _, _ in v if w), default=None)),
                             "last": _iso(max((w for w, _, _ in v if w), default=None)),
                             "record_ids": [u for _, _, u in sorted(v, key=lambda x: (x[0] is None, x[0]))][:RECORD_CAP]}
                       for ext, v in sorted(per.items())},
            "records": sum(len(v) for v in per.values()),
            "first": _iso(timed[0]) if timed else None, "last": _iso(timed[-1]) if timed else None})
    out.sort(key=lambda x: (-len(x["phones"]), -x["records"], x["label"]))
    return out, {"records": int(read)}


def relay_chains(conn, case_id: str, phones: list[str], start, end) -> tuple[list[dict], dict]:
    """A phone's contact with a counterpart, then another chosen phone's contact with the same counterpart within ten
    minutes. One chain per pair of phones, counterpart and day, the shortest gap."""
    read = conn.execute(text(
        "SELECT count(*) FROM pol_activity_event WHERE case_id = CAST(:c AS uuid) AND extraction_id = ANY(CAST(:e AS uuid[])) "
        "AND instant_utc IS NOT NULL AND activity_class = 'interaction' AND counterpart_identity_id IS NOT NULL "
        "AND (CAST(:s AS timestamptz) IS NULL OR instant_utc >= CAST(:s AS timestamptz)) "
        "AND (CAST(:t AS timestamptz) IS NULL OR instant_utc <= CAST(:t AS timestamptz))"),
        {"c": case_id, "e": phones, "s": start, "t": end}).scalar() or 0
    rows = []
    for i, x in enumerate(phones):
        for y in phones[i + 1:]:
            for first, second in ((x, y), (y, x)):
                # ties sort the second phone first, so a contact at the same instant is not taken for the next one
                rows += conn.execute(text("""
                    WITH ev AS (SELECT extraction_id, counterpart_identity_id AS who, instant_utc AS t, record_uid
                                FROM pol_activity_event
                                WHERE case_id = CAST(:c AS uuid) AND extraction_id IN (CAST(:x AS uuid), CAST(:y AS uuid))
                                  AND activity_class = 'interaction' AND counterpart_identity_id IS NOT NULL
                                  AND instant_utc IS NOT NULL
                                  AND (CAST(:s AS timestamptz) IS NULL OR instant_utc >= CAST(:s AS timestamptz))
                                  AND (CAST(:t AS timestamptz) IS NULL OR instant_utc <= CAST(:t AS timestamptz))),
                         nx AS (SELECT extraction_id, who, t, record_uid,
                                       lead(extraction_id) OVER w AS n_ext, lead(t) OVER w AS n_t, lead(record_uid) OVER w AS n_uid
                                FROM ev WINDOW w AS (PARTITION BY who ORDER BY t, (extraction_id = CAST(:y AS uuid)) DESC, record_uid))
                    SELECT DISTINCT ON (nx.who, nx.t::date)
                           nx.extraction_id, nx.n_ext, nx.who, nx.t, nx.n_t, nx.record_uid::text, nx.n_uid::text, i.value_display
                    FROM nx LEFT JOIN pv_identity i ON i.identity_id = nx.who
                    WHERE nx.extraction_id = CAST(:x AS uuid) AND nx.n_ext = CAST(:y AS uuid)
                      AND nx.n_t > nx.t AND nx.n_t <= nx.t + interval '10 minutes'
                    ORDER BY nx.who, nx.t::date, (nx.n_t - nx.t)"""),
                    {"c": case_id, "x": first, "y": second, "s": start, "t": end}).fetchall()
    out = [{"id": hashlib.sha1(f"{r[0]}:{r[1]}:{r[2]}:{r[3]}".encode()).hexdigest()[:16],
            "first": str(r[0]), "second": str(r[1]), "via": str(r[2]), "via_label": r[7] or "an unnamed counterpart",
            "first_at": _iso(r[3]), "second_at": _iso(r[4]), "gap_s": int((r[4] - r[3]).total_seconds()),
            "records": [r[5], r[6]]} for r in rows]
    out.sort(key=lambda x: (x["first_at"], x["id"]))
    return out, {"events": int(read)}


def pair_days(conn, case_id: str, a: str, b: str) -> dict:
    from services.relations.sources import DbSources
    return DbSources(_Shim(conn), case_id).pair_stats(a, b)


class _Shim:
    """DbSources reads through ``db.execute``; a connection has the same method."""
    def __init__(self, conn):
        self.execute = conn.execute


def _side_by_side(db, conn, jobs):
    """Run each job on its own connection in a thread; fall back to the caller's connection if the session has no engine."""
    from concurrent.futures import ThreadPoolExecutor
    try:
        engine = db.get_bind()
        engine.connect().close()
    except Exception:
        return [j(conn) for j in jobs]

    def run(job):
        with engine.connect() as c:
            return job(c)
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(run, jobs))


PARTS = ("places", "contacts", "relay")


def read(db, case_id, phones: list[str], start: str | None = None, end: str | None = None,
         parts: list[str] | None = None) -> dict[str, Any]:
    """``parts`` limits the read to what a screen shows (places, contacts, relay); a part not asked for is absent from
    the answer, never an empty list read as "none found"."""
    from services.phone_analysis import fields as FV
    conn = db.connection()
    case = str(case_id)
    phones = list(dict.fromkeys(p for p in phones if p))
    if len(phones) < 2:
        raise TogetherError("Choose at least two phones.")
    if len(phones) > MAX_PHONES:
        raise TogetherError(f"Choose at most {MAX_PHONES} phones ({len(phones)} chosen).")
    labels = FV.active_phones(conn, case)
    unknown = [p for p in phones if p not in labels]
    if unknown:
        raise TogetherError("These phones are not in this case: " + ", ".join(u[:8] for u in unknown))
    want = list(dict.fromkeys(parts or PARTS))
    if [x for x in want if x not in PARTS]:
        raise TogetherError("'parts' can be: " + ", ".join(PARTS) + ".")
    a, b = _parse(start, "from"), _parse(end, "to")
    if a and b and a > b:
        raise TogetherError("'from' is after 'to'.")

    pair_list = [(x, y) for i, x in enumerate(phones) for y in phones[i + 1:]]

    def place_part(c):
        raw, positions = cells(c, case, phones, a, b)
        meetings = _merge(raw)
        if meetings:
            _busy(c, case, meetings, a, b)
        return raw, positions, meetings

    def days_part(c):
        return {pr: (pair_days(c, case, *pr) if not (a or b) else None) for pr in pair_list}

    # the reads are independent and read-only: each on its own connection, side by side; a screen asks only for its parts
    jobs = {"places": place_part, "days": days_part,
            "contacts": lambda c: shared_contacts(c, case, phones, a, b),
            "relay": lambda c: relay_chains(c, case, phones, a, b)}
    names = [k for k in ("places", "days", "contacts", "relay") if k in want or (k == "days" and "places" in want)]
    got = dict(zip(names, _side_by_side(db, conn, [jobs[k] for k in names])))
    raw, positions, meetings = got.get("places", ([], {"positions": 0, "with_time": 0}, []))
    contacts, c_read = got.get("contacts", ([], {"records": 0}))
    relays, r_read = got.get("relay", ([], {"events": 0}))
    days_by = got.get("days", {pr: None for pr in pair_list})
    pairs = []
    for x, y in pair_list:
        days = days_by[(x, y)]
        pairs.append({"phones": [x, y], "meetings": sum(1 for m in meetings if set(m["phones"]) == {x, y}),
                      "days_together": days["days_together"] if days else None,
                      "days_both_active": days["days_both_active"] if days else None})
    span = _span(a, b)
    searched, out_of_reach = [], []
    if "places" in want:
        searched.append(f"Positions of {len(phones)} phones with a time: {positions['with_time']:,} of {positions['positions']:,} "
                        f"positions in {span}; paired by {PLACE_WORDS}. Two positions either side of a slot or square edge are not paired.")
        if positions["positions"] > positions["with_time"]:
            out_of_reach.append(f"{positions['positions'] - positions['with_time']:,} positions have no time and cannot be placed with the other phone.")
        if positions["positions"] == 0:
            out_of_reach.append("None of the chosen phones holds a position, so no place could be compared.")
    if "contacts" in want:
        searched.append(f"Messages, calls and emails of the chosen phones: {c_read['records']:,}, grouped by person (a confirmed person, else one identity); copies count once.")
        if c_read["records"] == 0:
            out_of_reach.append("None of the chosen phones holds a message, call or email, so no shared contact could be read.")
    if "relay" in want:
        searched.append(f"Contacts by the chosen phones: {r_read['events']:,}, a second phone reaching the same counterpart within 10 minutes.")
    out: dict[str, Any] = {
        "case_id": case, "phones": [{"id": p, "label": labels[p]} for p in phones], "from": _iso(a), "to": _iso(b),
        "parts": want, "pairs": pairs, "searched": searched, "out_of_reach": out_of_reach,
        "together": [], "cells": 0, "shared_contacts": [], "relay_chains": [],
        "message": None, "contacts_message": None, "relay_message": None,
    }
    if "places" in want:
        out["together"], out["cells"] = meetings, len(raw)
        out["message"] = (f"No meeting found in {positions['with_time']:,} timed positions of these phones ({PLACE_WORDS}, {span})."
                          if not meetings else f"{len(meetings)} meetings found, {sum(m['cells'] for m in meetings)} cells ({PLACE_WORDS}).")
    if "contacts" in want:
        out["shared_contacts"] = contacts
        out["contacts_message"] = None if contacts else f"No person has records on two or more of these phones in {span}."
    if "relay" in want:
        out["relay_chains"] = relays
        out["relay_message"] = None if relays else f"No relay chain found in {r_read['events']:,} contacts of these phones in {span}."
    return out
