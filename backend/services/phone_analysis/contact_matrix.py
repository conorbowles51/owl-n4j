"""Approach 15: directional from/to frequency matrix (docs/cellebrite/05 section 16b; unit 05-S16b).

Who contacts whom, and how often in each direction, over the case's owners and every person with at least
``min_communications`` calls, messages or emails (16b.3 step 1). A cell (X, Y) counts what X sent or placed to Y, by
channel; calls are counted by their recorded status and never summed into "contact" (step 3), with the total
duration of the connected ones. A message both phones hold and approach 2 matched counts once (step 2); a message
between two owners' phones that approach 2 did not match counts once per phone, and the result says how many such
copies there are (16b.5). The counts in the other direction are stated beside each cell as a count, never as a ratio.

Gate (16b.6) passed: on the 10-report corpus case 8 owners are in contact with another owner (3 needed).

Decisions (05 section 19):

- 19.S16b-a ``min_communications`` defaults to 1 (16b.3); M-15a gave 8,502 people at N = 1 and 5,519 at N = 5 on
  the corpus case, and every cell opens to its records, so the smaller population would only hide people. Reverse
  if the screen cannot list a case's cells.
- 19.S16b-b The sender of a record is its sender or caller party (or the phone's owner for an outgoing record that
  names none); every other party is a recipient. A record with neither sender nor direction is counted as
  "direction not recorded" and in no cell. Duplicate copies on one phone count once (02 duplicate groups).
- 19.S16b-c A result is one non-empty cell; it rests on the cell's first and last record with an anchor of its own
  (a message to a group is the first record of several cells).
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone_analysis import fields as FV
from services.phone_analysis.common_contacts import owner_sets
from services.phone_analysis.message_reconciliation import _people

CODE = "contact_matrix"
VERSION = "15.1"
PARAMETERS = {"min_communications": {"default": 1, "min": 1, "max": 1000}}
KINDS = ("between_owners", "cell")
SUPPORTS = ("sent", "matched_once", "reviewed_person")
UNDERCUTS = ("unmatched_copies", "identity_unreviewed", "apps_not_extracted", "selective_extraction",
             "deleted_or_carved", "calls_not_matched")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [{"code": "comms", "label": "Calls, messages and emails"}]
SENDER_ROLES = ("sender", "caller", "from")
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def coverage(conn, case_id) -> dict:
    counts = {str(r[0]): int(r[1]) for r in conn.execute(text(
        "SELECT extraction_id, count(*) FROM pv_comm_event WHERE case_id = :c AND kind IN ('message', 'call', 'email') "
        "GROUP BY 1"), {"c": str(case_id)})}
    return {"phones": {ext: {"label": label, "signals": {"comms": {"carries_signal": counts.get(ext, 0) > 0,
                                                                  "records": counts.get(ext, 0)}}}
                       for ext, label in FV.active_phones(conn, case_id).items()}, "signals": SIGNALS}


def matched_second_copies(conn, case_id) -> set:
    """Record uids of the second copy of every message approach 2's latest completed run matched on both phones."""
    run = conn.execute(text(
        "SELECT id FROM phone_analysis_runs WHERE case_id = :c AND approach = 'message_reconciliation' AND status = "
        "'completed' ORDER BY finished_at DESC NULLS LAST, created_at DESC LIMIT 1"), {"c": str(case_id)}).first()
    if run is None:
        return set()
    pairs = defaultdict(list)
    for r in conn.execute(text(
            "SELECT x.result_id, x.extraction_id::text, x.record_uid::text FROM phone_analysis_result_records x JOIN "
            "phone_analysis_results r ON r.id = x.result_id WHERE r.run_id = :r AND r.kind = 'both_sides' AND "
            "x.record_uid IS NOT NULL"), {"r": run.id}):
        pairs[r[0]].append((r[1], r[2]))
    return {max(v)[1] for v in pairs.values() if len({e for e, _ in v}) == 2}


def _events(conn, ext, people, owner_node, node_of):
    """[(sender node, [recipient nodes], kind, call_status, duration, instant, record_uid, deleted)] of one phone."""
    rows = defaultdict(lambda: {"parties": []})
    for r in conn.execute(text(
            "WITH one AS (SELECT DISTINCT ON (coalesce(dup_group_uid, event_uid::text)) * FROM pv_comm_event WHERE "
            "extraction_id = :e AND kind IN ('message', 'call', 'email') ORDER BY coalesce(dup_group_uid, "
            "event_uid::text), event_uid) SELECT e.event_uid::text AS ev, e.record_uid::text AS uid, e.kind, "
            "e.direction, e.call_status, e.call_duration_s, e.sort_instant, e.deleted_state, p.identity_key, p.role, "
            "p.implied_role, p.is_phone_owner FROM one e JOIN pv_comm_party p ON p.event_uid = e.event_uid ORDER BY "
            "e.event_uid, p.participation_uid"),
            {"e": ext}).mappings():
        x = rows[r["ev"]]
        x.update({k: r[k] for k in ("uid", "kind", "direction", "call_status", "call_duration_s", "sort_instant",
                                    "deleted_state")})
        if r["identity_key"] or r["is_phone_owner"]:
            node = owner_node if r["is_phone_owner"] else node_of(people.get(r["identity_key"], r["identity_key"]))
            x["parties"].append((node, (r["role"] or "").casefold(), (r["implied_role"] or "").casefold()))
    out = []
    for x in rows.values():
        senders = [n for n, role, implied in x["parties"] if role in SENDER_ROLES or implied == "sender"]
        sender = senders[0] if senders else (owner_node if x["direction"] == "outgoing" else None)
        others = sorted({n for n, _, _ in x["parties"] if n != sender}, key=str)
        if sender is not None and sender != owner_node and owner_node not in others and x["direction"] == "incoming":
            others.append(owner_node)
        if sender is None and x["direction"] == "incoming" and len(others) == 1:
            sender, others = others[0], [owner_node]
        out.append((sender, others, x["kind"], x["call_status"], float(x["call_duration_s"] or 0), x["sort_instant"],
                    x["uid"], x["deleted_state"]))
    return out


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    people = _people(conn, case_id)
    phones = FV.active_phones(conn, case_id)
    owners = owner_sets(conn, case_id, phones, people)
    owner_of_group = {g: n for n, o in enumerate(owners) for g in o["groups"]}
    owner_of_phone = {ext: n for n, o in enumerate(owners) for ext in o["phones"]}
    labels = {("owner", n): " and ".join(phones[e] for e in o["phones"]) for n, o in enumerate(owners)}

    def node_of(g):
        return ("owner", owner_of_group[g]) if g in owner_of_group else g
    skip = matched_second_copies(conn, case_id)
    counts["matched_copies_counted_once"] = 0
    cells = defaultdict(lambda: {"by_channel": defaultdict(int), "calls_by_status": defaultdict(int),
                                 "connected_call_seconds": 0.0, "events": [], "deleted": 0, "owner_copies": 0})
    totals = defaultdict(int)
    for i, ext in enumerate(phones):
        if ctx is not None:
            ctx.progress(i, len(phones), phones[ext])
            if ctx.cancelled():
                return [], dict(counts)
        if ext not in owner_of_phone:
            counts["phones_without_owner"] += 1
            continue
        me = ("owner", owner_of_phone[ext])
        for sender, others, kind, status, dur, at, uid, deleted in _events(conn, ext, people, me, node_of):
            if uid in skip:
                counts["matched_copies_counted_once"] += 1
                continue
            if sender is None or not others:
                counts["direction_not_recorded"] += 1
                continue
            for y in others:
                c = cells[(sender, y)]
                c["by_channel"][kind] += 1
                if kind == "call":
                    c["calls_by_status"][status or "Not recorded"] += 1
                    if status == "Established":
                        c["connected_call_seconds"] += dur
                c["events"].append((at, uid, ext))
                c["deleted"] += deleted in ("Deleted", "Trash")
                if kind == "message" and isinstance(sender, tuple) and isinstance(y, tuple):
                    c["owner_copies"] += 1
                totals[sender] += 1
                totals[y] += 1
    population = {n for n, t in totals.items() if isinstance(n, tuple) or t >= params["min_communications"]}
    counts["population"] = len(population)
    display = {}
    for r in conn.execute(text("SELECT identity_key, value_display FROM pv_identity WHERE case_id = :c"),
                          {"c": str(case_id)}):
        display.setdefault(people.get(r.identity_key, r.identity_key), r.value_display)

    def name(n):
        return ("Owner of " + labels[n]) if isinstance(n, tuple) else (display.get(n) or str(n))
    sent = defaultdict(int)
    received = defaultdict(int)
    for (x, y), c in cells.items():
        n = sum(c["by_channel"].values())
        sent[x] += n
        received[y] += n
    out = []
    for (x, y), c in sorted(cells.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        if x not in population or y not in population:
            counts["cells_outside_population"] += 1
            continue
        ev = sorted(c["events"], key=lambda e: (e[0] is None, e[0] or 0, e[1]))
        timed = [e for e in ev if e[0] is not None]
        back = cells.get((y, x))
        both_owners = isinstance(x, tuple) and isinstance(y, tuple)
        kind = "between_owners" if both_owners else "cell"
        counts[kind] += 1
        total = sum(c["by_channel"].values())
        supports = [_d("sent", "%d sent or placed by %s to %s." % (total, name(x), name(y)))]
        undercuts = [_d("apps_not_extracted", "Contact through apps the extractions do not hold is not counted."),
                     _d("selective_extraction", "A selective extraction can leave records out.")]
        if both_owners and skip:
            supports.append(_d("matched_once", "Messages held on both phones and matched are counted once."))
        if c["owner_copies"]:
            undercuts.append(_d("unmatched_copies", "%d messages between the two owners were not matched across "
                                "their phones and may be counted on each phone." % c["owner_copies"]))
        if both_owners and c["by_channel"].get("call"):
            undercuts.append(_d("calls_not_matched", "A call held on both phones is counted on each."))
        for n in (x, y):
            if not isinstance(n, tuple) and not str(n).startswith("person:"):
                undercuts.append(_d("identity_unreviewed", "%s is matched across phones only because the number or "
                                    "account is equal." % name(n)))
                break
        if c["deleted"]:
            undercuts.append(_d("deleted_or_carved", "%d of these are deleted records the phones still held." %
                                c["deleted"]))
        anchor = "cell:%s|%s" % (x if not isinstance(x, tuple) else "owner%d" % x[1],
                                 y if not isinstance(y, tuple) else "owner%d" % y[1])
        recs = [{"extraction_id": ev[0][2], "record_uid": ev[0][1], "field_path": anchor, "role": "first"}]
        if ev[-1][1] != ev[0][1]:
            recs.append({"extraction_id": ev[-1][2], "record_uid": ev[-1][1], "field_path": None, "role": "last"})
        out.append({
            "kind": kind, "strength": "counted",
            "measures": {"from": str(x) if not isinstance(x, tuple) else "owner%d" % x[1],
                         "to": str(y) if not isinstance(y, tuple) else "owner%d" % y[1],
                         "from_display": name(x), "to_display": name(y), "total": total,
                         "by_channel": dict(c["by_channel"]), "calls_by_status": dict(c["calls_by_status"]),
                         "connected_call_seconds": round(c["connected_call_seconds"]),
                         "reverse_total": sum(back["by_channel"].values()) if back else 0,
                         "from_sent_total": sent[x], "to_received_total": received[y],
                         "unmatched_owner_copies": c["owner_copies"],
                         "extraction_ids": sorted({e[2] for e in ev}),
                         "first": timed[0][0] if timed else None, "last": timed[-1][0] if timed else None},
            "directions": {"supports": supports, "undercuts": undercuts},
            "period_start": timed[0][0] if timed else None, "period_end": timed[-1][0] if timed else None,
            "records": recs})
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
