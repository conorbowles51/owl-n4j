"""Approach 16: number switching (docs/cellebrite/05 section 16c; unit 05-S16c).

A person whose contact stops (X) while another person (Y) with a similar set of counterparts starts within the gap
after: for each such pair, the gap, the Jaccard similarity of X's counterparts over the window before its last
communication and Y's over the window after its first, the shared counterparts, and the markers beside it (a saved
contact entry holding both, the same name for both on one phone, never active on the same day). Nothing is merged:
a pair is a lead, and joining the two is a person's identity decision (02).

Counterparts are read as approach 15 reads senders and recipients (``contact_matrix._events``). Owners are not paired
(their numbers are the phones'), but are counterparts. A person whose last communication falls within the gap of the
end of the data of a phone it appears on has not stopped: the phone's data stopped (16c.8 test 2); likewise a start
within the gap of the start of a phone's data is not a start.

Gate (16c.6) passed: on the 10-report corpus case 3 pairs reach the defaults against 0 in 20 shuffled runs.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from services.phone_analysis import fields as FV
from services.phone_analysis.common_contacts import owner_sets
from services.phone_analysis.contact_matrix import _events
from services.phone_analysis.message_reconciliation import _people

CODE = "number_switching"
VERSION = "16.1"
PARAMETERS = {
    "gap_days": {"default": 14, "min": 1, "max": 120},
    "window_days": {"default": 90, "min": 7, "max": 730},
    "threshold": {"default": 0.5, "min": 0.1, "max": 1.0},
    "min_shared": {"default": 5, "min": 1, "max": 100},
}
KINDS = ("switch_candidate",)
SUPPORTS = ("similar_counterparts", "saved_together", "same_name", "never_same_day")
UNDERCUTS = ("changed_together", "group_chat_counterparts", "short_span", "identity_unreviewed", "not_merged")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [{"code": "comms", "label": "Calls, messages and emails"}]
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def coverage(conn, case_id) -> dict:
    from services.phone_analysis import contact_matrix
    return contact_matrix.coverage(conn, case_id)


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    gap, window = timedelta(days=params["gap_days"]), timedelta(days=params["window_days"])
    people = _people(conn, case_id)
    phones = FV.active_phones(conn, case_id)
    owners = owner_sets(conn, case_id, phones, people)
    owner_of_group = {g: n for n, o in enumerate(owners) for g in o["groups"]}
    owner_of_phone = {ext: n for n, o in enumerate(owners) for ext in o["phones"]}

    def node_of(g):
        return ("owner", owner_of_group[g]) if g in owner_of_group else g
    nbr = defaultdict(list)          # person -> [(instant, counterpart, record_uid, ext)]
    span = {}
    phones_of = defaultdict(set)
    group_events = defaultdict(int)
    for i, ext in enumerate(phones):
        if ctx is not None:
            ctx.progress(i, len(phones), phones[ext])
            if ctx.cancelled():
                return [], dict(counts)
        if ext not in owner_of_phone:
            continue
        me = ("owner", owner_of_phone[ext])
        for sender, others, _k, _s, _d2, at, uid, _del in _events(conn, ext, people, me, node_of):
            if at is None or sender is None:
                continue
            lo, hi = span.get(ext, (at, at))
            span[ext] = (min(lo, at), max(hi, at))
            for y in others:
                for a, b in ((sender, y), (y, sender)):
                    if not isinstance(a, tuple):
                        nbr[a].append((at, b, uid, ext))
                        phones_of[a].add(ext)
                        if len(others) > 1:
                            group_events[a] += 1
    first, last = {}, {}
    for x, evs in nbr.items():
        evs.sort(key=lambda e: (e[0], str(e[1]), e[2]))
        first[x], last[x] = evs[0][0], evs[-1][0]
    times = {x: [e[0] for e in evs] for x, evs in nbr.items()}

    def window_set(x, a, b):
        lo, hi = bisect.bisect_left(times[x], a), bisect.bisect_right(times[x], b)
        return {e[1] for e in nbr[x][lo:hi]}
    stopped = [x for x in nbr if all(last[x] < span[e][1] - gap for e in phones_of[x])]
    started = [y for y in nbr if all(first[y] > span[e][0] + gap for e in phones_of[y])]
    counts["stopped"], counts["started"] = len(stopped), len(started)
    by_start = sorted((first[y], str(y), y) for y in started)
    keys = [s for s, _, _ in by_start]
    names = defaultdict(lambda: defaultdict(set))   # ext -> name -> persons
    for r in conn.execute(text("SELECT i.identity_key, n.extraction_id::text, n.name FROM phone_identity_names n JOIN "
                               "phone_identities i ON i.id = n.identity_id WHERE n.case_id = :c"), {"c": str(case_id)}):
        names[r[1]][(r[2] or "").strip().casefold()].add(people.get(r[0], r[0]))
    cards = defaultdict(set)                         # card -> persons
    for r in conn.execute(text("SELECT identity_key, card_record_uid::text FROM pv_identity_sighting WHERE case_id = :c "
                               "AND card_type = 'Contact' AND card_record_uid IS NOT NULL"), {"c": str(case_id)}):
        cards[r[1]].add(people.get(r[0], r[0]))
    display = {}
    for r in conn.execute(text("SELECT identity_key, value_display FROM pv_identity WHERE case_id = :c"),
                          {"c": str(case_id)}):
        display.setdefault(people.get(r.identity_key, r.identity_key), r.value_display)
    out = []
    for x in sorted(stopped, key=str):
        bx = window_set(x, last[x] - window, last[x])
        if len(bx) < params["min_shared"]:
            continue
        i, j = bisect.bisect_right(keys, last[x]), bisect.bisect_right(keys, last[x] + gap)
        for _s, _k, y in by_start[i:j]:
            if y == x:
                continue
            counts["candidate_pairs"] += 1
            ay = window_set(y, first[y], first[y] + window)
            shared = bx & ay
            jac = len(shared) / len(bx | ay) if bx | ay else 0.0
            if jac < params["threshold"] or len(shared) < params["min_shared"]:
                continue
            counts["switch_candidate"] += 1
            supports = [_d("similar_counterparts", "%d of their counterparts are shared (similarity %.2f)." % (
                len(shared), jac))]
            card = sorted(c for c, ps in cards.items() if x in ps and y in ps)
            if card:
                supports.append(_d("saved_together", "One saved contact entry holds both.", card[:1]))
            same = sorted(phones[e] for e, ns in names.items() if any(x in ps and y in ps for ps in ns.values()))
            if same:
                supports.append(_d("same_name", "Named the same on %s." % ", ".join(same)))
            days_x = {e[0].date() for e in nbr[x]}
            if not days_x & {e[0].date() for e in nbr[y]}:
                supports.append(_d("never_same_day", "Never active on the same day."))
            undercuts = [_d("not_merged", "Nothing is joined: joining the two is a person's identity decision."),
                         _d("changed_together", "Counterparts who changed phone together also give this pattern.")]
            if group_events[x] or group_events[y]:
                undercuts.append(_d("group_chat_counterparts", "Group chats make many counterparts shared."))
            for p in (x, y):
                if not str(p).startswith("person:"):
                    undercuts.append(_d("identity_unreviewed", "Each side is one number or account, not a reviewed "
                                        "person."))
                    break
            lx, fy = nbr[x][-1], nbr[y][0]
            recs = [{"extraction_id": lx[3], "record_uid": lx[2], "field_path": "switch:%s|%s" % (x, y),
                     "role": "last_of_first"},
                    {"extraction_id": fy[3], "record_uid": fy[2], "field_path": None, "role": "first_of_second"}]
            recs += [{"extraction_id": None, "record_uid": c, "field_path": None, "role": "contact_card"}
                     for c in card[:1] if c not in (lx[2], fy[2])]
            if recs[1]["record_uid"] == recs[0]["record_uid"]:
                recs.pop(1)
            out.append({
                "kind": "switch_candidate", "strength": "with_markers" if len(supports) > 1 else "overlap_only",
                "measures": {"from": str(x), "to": str(y), "from_display": display.get(x) or str(x),
                             "to_display": display.get(y) or str(y), "last_of_first": last[x],
                             "first_of_second": first[y], "gap_days": round((first[y] - last[x]).total_seconds() /
                                                                            86400, 1),
                             "similarity": round(jac, 3), "shared": len(shared), "first_counterparts": len(bx),
                             "second_counterparts": len(ay), "markers": [s["code"] for s in supports[1:]],
                             "extraction_ids": sorted(phones_of[x] | phones_of[y])},
                "directions": {"supports": supports, "undercuts": undercuts},
                "period_start": last[x], "period_end": first[y], "records": recs})
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
