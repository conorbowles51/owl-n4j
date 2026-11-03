"""Approach 14: common contacts (docs/cellebrite/05 section 16a; unit 05-S16a).

For each pair of owners of the case's phones (A and B), every person X other than A and B that both are in contact
with, from both sides of every phone in the case: calls, messages and emails between A and X on A's phones, and on
X's own phones when X owns a phone in the case (counted apart, "seen on the other phone"), and the same for B; by
channel and direction, with the first and last on each side. A person saved as a contact on one side's phone with no
communication on that side is listed apart as "saved, no contact seen" (16a.3 step 3). Nothing is merged: a person is
a reviewed person (02) when one exists, else one identity.

Gate (16a.6) passed: on the 10-report corpus case 21 of 28 owner pairs have 3 or more common contacts.

Decisions (05 section 19):

- 19.S16a-a Owners are each phone's owner identities as 02 computes them (with account candidates), read through
  reviewed persons; phones whose owners share a person or identity are one owner. Reverse if 02 records owners per
  phone in another way.
- 19.S16a-b The window is the whole span of the data (16a.3 step 3 default); a narrower window is the Conversations
  filter the counts open, so key dates never need a rerun.
- 19.S16a-c A result rests on the first and last communication of each side and on the saved contact entries, with a
  pair anchor of its own (one record can be the first contact of two pairs); the counts open the full lists.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone_analysis import fields as FV
from services.phone_analysis.message_reconciliation import _owners, _people

CODE = "common_contacts"
VERSION = "14.1"
PARAMETERS: dict = {}
KINDS = ("common_contact", "saved_no_contact")
SUPPORTS = ("both_sides", "seen_on_other_phone", "saved_contact", "reviewed_person")
UNDERCUTS = ("identity_unreviewed", "apps_not_extracted", "number_shared", "deleted_or_carved", "saved_only")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "owners", "label": "Known owner identities"},
    {"code": "comms", "label": "Calls, messages and emails"},
]
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def coverage(conn, case_id) -> dict:
    people = _people(conn, case_id)
    counts = {str(r[0]): int(r[1]) for r in conn.execute(text(
        "SELECT extraction_id, count(*) FROM pv_comm_event WHERE case_id = :c AND kind IN ('message', 'call', 'email') "
        "GROUP BY 1"), {"c": str(case_id)})}
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        o = len(_owners(conn, ext, people))
        phones[ext] = {"label": label, "signals": {"owners": {"carries_signal": o > 0, "records": o},
                                                   "comms": {"carries_signal": counts.get(ext, 0) > 0,
                                                             "records": counts.get(ext, 0)}}}
    return {"phones": phones, "signals": SIGNALS}


def owner_sets(conn, case_id, phones, people) -> list:
    """[{"groups": set, "phones": [ext...]}]: phones whose owner groups overlap are one owner (19.S16a-a)."""
    owners = []
    for ext in phones:
        g = set(_owners(conn, ext, people))
        if not g:
            continue
        hit = [o for o in owners if o["groups"] & g]
        merged = {"groups": set(g), "phones": [ext]}
        for o in hit:
            merged["groups"] |= o["groups"]
            merged["phones"] += o["phones"]
            owners.remove(o)
        owners.append(merged)
    for o in owners:
        o["phones"] = sorted(o["phones"])
    return sorted(owners, key=lambda o: o["phones"])


def _comms(conn, ext, people):
    """{counterpart group: [(instant, kind, direction, record_uid, deleted)]} of one phone, owner parties left out."""
    out = defaultdict(list)
    for r in conn.execute(text(
            "SELECT DISTINCT e.record_uid::text AS uid, e.kind, e.direction, e.sort_instant, e.deleted_state, "
            "p.identity_key FROM pv_comm_event e JOIN pv_comm_party p ON p.event_uid = e.event_uid WHERE "
            "e.extraction_id = :e AND e.kind IN ('message', 'call', 'email') AND p.identity_key IS NOT NULL AND NOT "
            "coalesce(p.is_phone_owner, false)"), {"e": ext}).mappings():
        out[people.get(r["identity_key"], r["identity_key"])].append(
            (r["sort_instant"], r["kind"], r["direction"] or "unknown", r["uid"], r["deleted_state"], ext))
    return out


def _cards(conn, ext, people):
    out = defaultdict(set)
    for r in conn.execute(text(
            "SELECT DISTINCT identity_key, card_record_uid::text FROM pv_identity_sighting WHERE extraction_id = :e AND "
            "card_type = 'Contact' AND card_record_uid IS NOT NULL"), {"e": ext}):
        out[people.get(r[0], r[0])].add((r[1], ext))
    return out


def _side(own_comms, other_comms):
    """Counts of one side: on the owner's phones, and on the contact's own phones (seen on the other phone)."""
    evs = sorted(own_comms + other_comms, key=lambda e: (e[0] is None, e[0] or 0, e[3]))
    timed = [e for e in evs if e[0] is not None]
    by = defaultdict(int)
    for e in evs:
        by["%s_%s" % (e[1], e[2])] += 1
    return {"total": len(evs), "on_own_phones": len(own_comms), "seen_on_other_phone": len(other_comms),
            "by_channel": dict(sorted(by.items())), "first": timed[0] if timed else None,
            "last": timed[-1] if timed else None, "deleted": sum(1 for e in evs if e[4] in ("Deleted", "Trash"))}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    people = _people(conn, case_id)
    phones = FV.active_phones(conn, case_id)
    owners = owner_sets(conn, case_id, phones, people)
    counts["owners"] = len(owners)
    comms, cards = {}, {}
    for i, ext in enumerate(phones):
        if ctx is not None:
            ctx.progress(i, len(phones), phones[ext])
            if ctx.cancelled():
                return [], dict(counts)
        comms[ext] = _comms(conn, ext, people)
        cards[ext] = _cards(conn, ext, people)
    display = {}
    for r in conn.execute(text("SELECT identity_key, value_display, person_id FROM pv_identity WHERE case_id = :c"),
                          {"c": str(case_id)}):
        display.setdefault(people.get(r.identity_key, r.identity_key), r.value_display)
    owner_of_group = {g: n for n, o in enumerate(owners) for g in o["groups"]}

    def side_lists(n, x):
        """(on owner n's phones with x, on x's own phones with owner n)."""
        own = [e for ext in owners[n]["phones"] for e in comms[ext].get(x, [])]
        other = []
        if x in owner_of_group:
            for ext in owners[owner_of_group[x]]["phones"]:
                for g in owners[n]["groups"]:
                    other += comms[ext].get(g, [])
        return own, other

    def label(n):
        return " and ".join(phones[e] for e in owners[n]["phones"])
    out = []
    for a in range(len(owners)):
        for b in range(a + 1, len(owners)):
            ga, gb = owners[a]["groups"], owners[b]["groups"]
            xs = set()
            for n in (a, b):
                for ext in owners[n]["phones"]:
                    xs |= set(comms[ext]) | set(cards[ext])
                for m, o in enumerate(owners):
                    if m != n:
                        for ext in o["phones"]:
                            if any(g in comms[ext] for g in owners[n]["groups"]):
                                xs |= o["groups"]
            xs -= ga | gb
            counts["pairs"] += 1
            pair_hits = 0
            for x in sorted(xs, key=str):
                sa, sb = _side(*side_lists(a, x)), _side(*side_lists(b, x))
                card_a = sorted(c for ext in owners[a]["phones"] for c in cards[ext].get(x, ()))
                card_b = sorted(c for ext in owners[b]["phones"] for c in cards[ext].get(x, ()))
                if sa["total"] and sb["total"]:
                    kind = "common_contact"
                elif (sa["total"] or card_a) and (sb["total"] or card_b) and (card_a or card_b):
                    kind = "saved_no_contact"
                else:
                    continue
                counts[kind] += 1
                pair_hits += kind == "common_contact"
                reviewed = str(x).startswith("person:")
                supports, undercuts = [], []
                if kind == "common_contact":
                    supports.append(_d("both_sides", "In contact with %s %d times and with %s %d times." % (
                        label(a), sa["total"], label(b), sb["total"])))
                else:
                    undercuts.append(_d("saved_only", "Saved as a contact with no call, message or email seen on "
                                        "one side."))
                seen_other = sa["seen_on_other_phone"] + sb["seen_on_other_phone"]
                if seen_other:
                    supports.append(_d("seen_on_other_phone", "%d of these are on the contact's own phone; a message "
                                       "held on both phones is counted on each." % seen_other))
                if card_a or card_b:
                    supports.append(_d("saved_contact", "Saved as a contact on %s." % " and ".join(
                        label(n) for n, c in ((a, card_a), (b, card_b)) if c), [c for c, _ in (card_a + card_b)[:1]]))
                if reviewed:
                    supports.append(_d("reviewed_person", "Several numbers or accounts are joined under one person by "
                                       "a reviewed decision."))
                else:
                    undercuts.append(_d("identity_unreviewed", "The person is matched across phones only because "
                                        "the number or account is equal."))
                undercuts.append(_d("apps_not_extracted", "Contact through apps the extractions do not hold is not "
                                    "counted."))
                undercuts.append(_d("number_shared", "A number can be used by more than one person."))
                if sa["deleted"] or sb["deleted"]:
                    undercuts.append(_d("deleted_or_carved", "Some of these records are deleted ones the phones "
                                        "still held."))
                anchor = "common:%s|%s|%s" % (min(str(sorted(ga)[0]), str(sorted(gb)[0])),
                                              max(str(sorted(ga)[0]), str(sorted(gb)[0])), x)
                recs, seen = [], set()
                for role, ev in (("first_a", sa["first"]), ("last_a", sa["last"]), ("first_b", sb["first"]),
                                 ("last_b", sb["last"])):
                    if ev and ev[3] not in seen:
                        seen.add(ev[3])
                        recs.append({"extraction_id": ev[5], "record_uid": ev[3], "field_path": None, "role": role})
                for c, ext in card_a + card_b:
                    if c not in seen:
                        seen.add(c)
                        recs.append({"extraction_id": ext, "record_uid": c, "field_path": None, "role": "contact_card"})
                recs[0] = dict(recs[0], field_path=anchor)
                firsts = [s["first"][0] for s in (sa, sb) if s["first"]]
                lasts = [s["last"][0] for s in (sa, sb) if s["last"]]

                def side_measures(s, cards_):
                    return {"total": s["total"], "on_own_phones": s["on_own_phones"],
                            "seen_on_other_phone": s["seen_on_other_phone"], "by_channel": s["by_channel"],
                            "first": s["first"][0] if s["first"] else None,
                            "last": s["last"][0] if s["last"] else None, "saved": len(cards_)}
                out.append({
                    "kind": kind, "strength": "both_sides" if kind == "common_contact" else "saved_only",
                    "measures": {"phones": [label(a), label(b)], "owner_a": label(a), "owner_b": label(b),
                                 "contact": x, "contact_display": display.get(x) or str(x),
                                 "contact_owns_phone": x in owner_of_group,
                                 "a": side_measures(sa, card_a), "b": side_measures(sb, card_b),
                                 "smaller_side": min(sa["total"], sb["total"]),
                                 "extraction_ids": sorted(set(owners[a]["phones"] + owners[b]["phones"]))},
                    "directions": {"supports": supports, "undercuts": undercuts},
                    "period_start": min(firsts) if firsts else None, "period_end": max(lasts) if lasts else None,
                    "records": recs})
            counts["pairs_with_3_or_more"] += pair_hits >= 3
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    out.sort(key=lambda r: (-r["measures"]["smaller_side"], str(r["period_end"] or "")), reverse=False)
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
