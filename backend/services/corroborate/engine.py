"""Corroborate: weigh how the records of a selection link, against ordinary instances (lx-corroengine B-F).

``run(store, members, question)`` returns the ``corroboration`` block of a run's result (schema loupe.corroborate/1):
the question, the level with its rule and sentence, the comparison and its instances, the grid, every explained-away
check, what is not in the pattern (people searched, with what was searched), the gaps (records missing), and where
to look further. The level comes from ``levels`` only. Nothing here calls a model.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from itertools import combinations
from typing import Any, Callable

from services.corroborate import checks as C
from services.corroborate import levels as L
from services.corroborate import model as M
from services.corroborate import questions as Q
from services.corroborate import signals as S

SCHEMA = "loupe.corroborate/1"
PICK_SHARE = 0.5
PICK_MINUTES = 45    # a contact "recurs" on another instance when it is within this many minutes of the seed's hour     # a contact on more than half the ordinary instances is routine and never picks incidents
MAX_ORDINARY = 400   # ordinary instances compared, nearest the incidents first; more are counted, never dropped silently


def _people_of(points: list[dict]) -> list[str]:
    """The people a selection names: the owners of its phone records when there are two or more of them (the people
    they wrote to are then "who else"), else everyone its items name."""
    owners = list(dict.fromkeys(p["people"][0] for p in points if p.get("type") == "phone_record" and p.get("people")))
    named = list(dict.fromkeys(k for p in points if p.get("type") != "phone_record" for k in p.get("people") or []))
    if len(owners) >= 2:
        return list(dict.fromkeys(owners + named))
    return list(dict.fromkeys(k for p in points for k in p.get("people") or []))


def _expand_places(store, points: list[dict], people_keys: list[str], everyone: dict) -> tuple[list[dict], list[dict], list[str]]:
    """A place with no time (a Map lasso) says where, not when: with other dated items in the selection it is kept
    as the place asked about (a signal: who was there on each instance). Alone, it becomes the presence positions
    inside it (of the selection's people when it names any, else of every phone). Stated in ``notes``."""
    out, places, notes = [], [], []
    has_times = any(p.get("at") for p in points if p.get("kind") != "place")
    phones = [e for k in people_keys for e in everyone[k]["phones"]] or None
    by_phone = {e: p["key"] for p in everyone.values() for e in p["phones"]}
    for p in points:
        if p.get("kind") != "place":
            out.append(p)
            continue
        if has_times:
            places.append(p["place"])
            notes.append("The area chosen is read as the place asked about: who was inside it on each instance.")
            continue
        inside = store.place_points(p["place"], phones)
        for x in inside:
            x["people"] = [by_phone[x["phone"]]] if x["phone"] in by_phone else []
        notes.append(f"The area chosen holds {len(inside):,} positions of "
                     f"{'the people chosen' if phones else 'any phone'}; each is part of the selection.")
        out += inside
    return out, places, notes


def run(store, members: list[dict], question: dict | None = None,
        progress: Callable[[str, int, int], None] | None = None) -> dict[str, Any]:
    started = time.time()
    step = progress or (lambda *_: None)
    question = dict(question or {})
    chips = dict(question.get("chips") or {})
    zone = store.zone()
    everyone = {p["key"]: p for p in store.people()}
    points, unread = store.selection_points(members)
    keys = [k for k in chips.get("who") or [] if k in everyone] or _people_of(points)
    points, places, notes = _expand_places(store, points, keys, everyone)
    if not chips.get("who"):
        keys = _people_of(points) or keys
    kind = question.get("kind") or Q.default_kind(points, keys)
    step("Reading the selection", len(points), len(members))

    if kind == "who_used":
        return _who_used(store, points, everyone, zone, unread, notes, started, question)
    # the people asked about; "connected at all" and "who used this phone" ask about one against the others
    focus = chips.get("person") if chips.get("person") in everyone else None
    if kind == "connected" and not focus:
        focus = next((k for k in keys if any(p.get("type") == "person" and k in p["people"] for p in points)), None)
    people = {k: everyone[k] for k in keys}
    timed = [p for p in points if p.get("at")]
    if kind == "connected" and focus:
        timed = [p for p in timed if focus not in p.get("people", []) or len(p["people"]) > 1]

    # instances asked about, and the comparison set
    hours_override = chips.get("hours")
    if kind == "behaviour_change":
        after = date.fromisoformat(chips["after"]) if chips.get("after") else None
        period = store.period(list(people.values()))
        if not after or not period:
            return _cant(question, kind, zone, people, unread, notes, started,
                         "a date to compare before and after" if not after else "records for these people")
        hours = {"start": "00:00", "length_h": 24}
        days = [period[0] + timedelta(days=n) for n in range((period[1] - period[0]).days + 1)]
        tzz = M.tz(zone)
        instances = [M.make_instance(d, datetime.strptime("00:00", "%H:%M").time(), timedelta(hours=24), tzz,
                                     "incident" if d >= after else "ordinary", zone) for d in days]
        comparison = {"kind": "before_after", "words": f"The days on and after {after:%d %b %Y} compared with the days "
                      f"before it, {period[0]:%d %b %Y} to {period[1]:%d %b %Y}.", "incident_noun": "days after",
                      "ordinary_noun": "days before"}
    else:
        incidents, hours = M.incidents_from_selection(timed, zone)
        if hours_override:
            hours = {"start": hours_override["start"], "length_h": float(hours_override["length_h"])}
            tzz = M.tz(zone)
            h, m = (int(x) for x in hours["start"].split(":"))
            incidents = [M.make_instance(date.fromisoformat(i["day"]), datetime.min.time().replace(hour=h, minute=m),
                                         timedelta(hours=hours["length_h"]), tzz, "incident", zone) for i in incidents]
        if not incidents:
            return _cant(question, kind, zone, people, unread, notes, started, "a date or time in the selection")
        period = store.period(list(people.values()))
        comp_kind = chips.get("compare_with") or Q.default_comparison(kind)
        ordinary, comparison = M.comparison_set(comp_kind, incidents, period, zone, hours)
        if len(ordinary) > MAX_ORDINARY:
            mid = min(date.fromisoformat(i["day"]) for i in incidents)
            ordinary.sort(key=lambda o: abs((date.fromisoformat(o["day"]) - mid).days))
            comparison["words"] += f" The {MAX_ORDINARY} nearest of {len(ordinary):,} are compared."
            ordinary = sorted(ordinary[:MAX_ORDINARY], key=lambda o: o["day"])
        instances = incidents + ordinary
    step("Building the comparison", len(instances), len(instances))

    # records
    windows = [(i["start"], i["money_end"]) for i in instances]
    raw = store.records(list(people.values()), windows, list(everyone.values()))
    recs, folded = M.dedupe(raw)
    activity = store.activity(list(people.values()), [(i["start"], i["end"]) for i in instances])
    doc_ids = sorted({r["source"] for r in recs if r["kind"] == "doc_row"})
    cov = store.coverage(list(people.values()), doc_ids)
    step("Reading the records", len(raw), len(raw))

    rows = _rows(people, recs, instances, cov, activity, store, kind)
    if kind in ("statement", "document"):
        docs = [p for p in points if p.get("kind") == "doc_row"]
        rows += [r for r in S.statement_rows(people, recs, activity, instances, docs, zone)
                 if any(v == "present" for v in r["cells"].values())]
    for pl in places:
        rows += [r for r in S.place_rows(people, recs, instances, pl) if any(v == "present" for v in r["cells"].values())]
    if focus:
        rows = [r for r in rows if focus in r["people"] or r["link_kind"] == "sequence"]
    _counts(rows, instances)

    # "does this happen every time": with one night asked about, find the others by the night's rarest link
    picked = None
    incidents_now = [i for i in instances if i["side"] == "incident"]
    if kind == "every_time" and len(incidents_now) == 1:
        rare = _pick(rows, incidents_now[0])
        if rare:
            need = max(min(2, len(rare)), (len(rare) + 1) // 2)
            by_ref = {x["ref"]: x for x in recs}
            for i in instances:
                if i["side"] == "ordinary" and sum(1 for r in rare if r["cells"].get(i["id"]) == "present" and
                                                   _same_hours(r, i, incidents_now[0], by_ref, zone)) >= need:
                    i["side"] = "incident"
            for r in rare:
                r["picked_by"] = True
            picked = rare
            n_more = sum(1 for i in instances if i["side"] == "incident") - 1
            day_name = date.fromisoformat(incidents_now[0]["day"]).strftime("%A")
            comparison["words"] += (f" The other {n_more} incident {day_name}{'' if n_more == 1 else 's'} "
                                    f"{'is' if n_more == 1 else 'are'} the ones on which at least {need} of the "
                                    f"{len(rare)} uncommon contacts of the {day_name} asked about recur within {PICK_MINUTES} minutes of the "
                                    "same time of day ("
                                    + "; ".join(r["label"] for r in rare) + "). Those rows picked them, so they are not "
                                    "counted as evidence.")
            comparison["incident_noun"] = f"incident {day_name}s"
            _counts(rows, instances)
    # with one instance, what one person did alone links no one to anyone: listed, never weighed
    if len(people) >= 2 and sum(1 for i in instances if i["side"] == "incident") == 1:
        for r in rows:
            if len(r["people"]) == 1:
                r["context"] = True
                r["why_context"] = "one person's record on one instance links no one to anyone"
    seq = S.sequence_row(rows, instances)
    if seq:
        rows.append(seq)
        _counts([seq], instances)
    step("Weighing the signals", len(rows), len(rows))

    # explained-away checks, then the level
    phones = [e for p in people.values() for e in p["phones"]]
    saved = {k: [(f"“{x['name']}” saved on a phone for {x['value']} shares a name with {people[k]['label']} but is "
                  "another number, so it is not joined to them") if x["where"] == "saved on a phone" else
                 (f"“{x['name']}” in the ledger shares a name with {people[k]['label']}; it is not joined to them by "
                  "the name alone") for x in store.lookalike_names(people[k])] for k in people}
    period_start = min((s[0] for c in cov.values() for s in c.get("phone", [])), default=None)
    ctx = {"comparison": comparison, "folded": folded, "facts": store.facts(), "phones": phones, "zone": zone,
           "windows": [(i["start"], i["end"]) for i in instances], "period_start": period_start,
           "phone_zones": store.phone_zones(), "phone_starts": store.phone_starts(list(people.values())), "everyone": list(everyone.values()), "saved_names": saved,
           "statements_outside": store.statement_files_outside_ledger()}
    checks = C.run(rows, instances, people, recs, ctx, store)
    for r in rows:
        if r["link_kind"] in ("contact", "money", "access", "shared_content"):
            r["ever_checked"] = True
            r["ever_present"] = any(v == "present" for v in r["cells"].values()) or (
                r["link_kind"] == "contact" and len(r["people"]) == 2 and
                store.contact_ever(people[r["people"][0]], people[r["people"][1]]) > 0)
    if not any(r["link_kind"] == "contact" for r in rows) and len(people) >= 2:
        rows.append(_never_row("contact", "contact between any of them", instances, people, store))
    missing = _gaps(rows, instances, people, cov, store)
    level = L.decide(rows, instances, comparison, checks, question_kind=kind, missing=missing)

    out_rows = _grid(rows, instances)
    not_in, others_media, others_alike = _not_in_pattern(store, everyone, people, instances, focus)
    _add_others_to_checks(checks, others_media, others_alike)
    result = {
        "schema": SCHEMA,
        "question": {"kind": kind, "text": Q.words(kind, people, instances, comparison, focus and everyone[focus]),
                     "chips": {**chips, "who": list(people), "compare_with": comparison["kind"],
                               "when": [i["label"] for i in instances if i["side"] == "incident"][:12]}},
        "level": level,
        "comparison": {"kind": comparison["kind"], "words": comparison["words"], "zone": zone,
                       "hours": hours, "incident": [_inst(i) for i in instances if i["side"] == "incident"],
                       "ordinary": [_inst(i) for i in instances if i["side"] == "ordinary"]},
        "grid": out_rows,
        "checks": checks,
        "people": [_person(p) for p in people.values()],
        "not_in_pattern": not_in,
        "searched": _searched(rows, recs, raw, instances, people),
        "gaps": missing,
        "look_further": _further(store, people, everyone, rows, instances),
        "unread": unread,
        "notes": notes,
        "case_facts_used": [f for f in ctx["facts"] if any(f["text"] in (r.get("why_low") or "") for r in rows)],
        "seconds": round(time.time() - started, 2),
    }
    return result


# ---- rows --------------------------------------------------------------------------------------------------------

def _rows(people, recs, instances, cov, activity, store, kind) -> list[dict]:
    rows = []
    rows += S.contact_rows(people, recs, instances, cov)
    rows += S.together_rows(people, recs, instances, cov)
    rows += S.money_rows(people, recs, instances, cov)
    rows += S.access_rows(people, recs, instances, cov)
    rows += S.absence_rows(people, activity, instances, cov)
    # shared words: count each candidate phrase across the case once
    cands = set()
    for inst in instances:
        if inst["side"] != "incident":
            continue
        by_ph = defaultdict(set)
        for r in S.bucket(recs, [inst], M.CONTACT_KINDS)[inst["id"]]:
            if r.get("body") and r.get("sender") in people:
                for ph in M.phrases(r["body"]):
                    by_ph[ph].add(r["sender"])
        cands |= {ph for ph, s in by_ph.items() if len(s) >= 2}
    counts = store.phrase_counts(sorted(cands)) if cands else {}
    rows += S.content_rows(people, recs, instances, counts)
    if kind in ("burst", "every_time", "together") or len(people) >= 3:
        act = S.activity_row(people, activity, instances)
        if act:
            pass
            rows.append(act)
    # rows that are never present anywhere are summarised in "searched", not drawn
    return [r for r in rows if any(v == "present" for v in r["cells"].values())]


def _counts(rows, instances):
    for r in rows:
        c = L.row_counts(r, instances)
        r["incident"], r["ordinary"] = c["incident"], c["ordinary"]


def _pick(rows, seed) -> list[dict]:
    """The seed's uncommon contacts: contact rows present on the seed instance and on no more than PICK_SHARE of the
    other instances (the other incidents are still among those, so the share is read loosely)."""
    out = []
    for r in rows:
        if r["link_kind"] != "contact" or r["cells"].get(seed["id"]) != "present" or not r["ordinary"]["of"]:
            continue
        s = L.share(r["ordinary"])
        if s is not None and s <= PICK_SHARE:
            out.append(r)
    return out


def _same_hours(row, inst, seed, by_ref, zone) -> bool:
    """The row's contact recurs on ``inst`` at the seed's hours: one of its records within PICK_MINUTES of the local
    time of day of one of the seed's records for that row."""
    tz = M.tz(zone)

    def minutes(ref):
        r = by_ref.get(ref)
        if not r:
            return None
        t = r["at"].astimezone(tz)
        return t.hour * 60 + t.minute
    seed_m = [m for m in (minutes(x) for x in row["records"].get(seed["id"], [])) if m is not None]
    for m in (minutes(x) for x in row["records"].get(inst["id"], [])):
        if m is not None and any(min(abs(m - s), 1440 - abs(m - s)) <= PICK_MINUTES for s in seed_m):
            return True
    return False


def _never_row(kind, label, instances, people, store) -> dict:
    row = {"id": f"{kind}:none", "link_kind": kind, "label": label, "people": list(people), "cells": {},
           "records": {}, "times": {}, "weight": "full", "ever_checked": True, "ever_present": False}
    for i in instances:
        row["cells"][i["id"]] = "absent"
    for a, b in combinations(sorted(people), 2):
        if store.contact_ever(people[a], people[b]):
            row["ever_present"] = True
    _counts([row], instances)
    return row


def _grid(rows, instances) -> list[dict]:
    out = []
    for r in rows:
        out.append({"signal": r["id"], "link_kind": r["link_kind"], "label": r["label"], "people": r["people"],
                    "cells": {i["id"]: r["cells"].get(i["id"], "no_data") for i in instances},
                    "incident": r["incident"], "ordinary": r["ordinary"], "weight": r.get("weight", "full"),
                    **({"why_low": r["why_low"]} if r.get("why_low") else {}),
                    **({"picked_by": True} if r.get("picked_by") else {}),
                    **({"context": True} if r.get("context") else {}),
                    "separates": L.separates(r), "records": r["records"],
                    "record_counts": r.get("record_counts", {}),
                    **({"precision_m": r["precision_m"]} if r.get("precision_m") is not None else {}),
                    **({"gaps": r["gaps"]} if r.get("gaps") else {}),
                    **({"phrase": r["phrase"], "case_count": r["case_count"]} if r.get("phrase") else {})})
    rank = {"incident": 0}
    out.sort(key=lambda r: (r.get("picked_by", False), not r["separates"], r["weight"] != "full",
                            -r["incident"]["present"], rank.get("x", 0), r["label"]))
    return out


def _inst(i) -> dict:
    return {"id": i["id"], "label": i["label"], "start": M.iso(i["start"]), "end": M.iso(i["end"]),
            "money_until": M.iso(i["money_end"]), "weekday": i["weekday"]}


def _person(p) -> dict:
    return {"key": p["key"], "label": p["label"], "dossier_id": p.get("dossier_id"),
            "phones": [{"id": e, "label": (p.get("phone_labels") or {}).get(e, e[:8])} for e in p["phones"]],
            "accounts": p["accounts"], "identifiers": p["links"],
            "suggested": any(x["how"] == "suggested" for x in p["links"])}


# ---- what was searched, what is missing, who is not in the pattern ------------------------------------------------

def _searched(rows, recs, raw, instances, people) -> dict:
    kinds = defaultdict(int)
    for r in raw:
        kinds[r["kind"]] += 1
    drawn = {r["link_kind"] for r in rows}
    return {"records_read": dict(kinds), "instances": len(instances), "people": len(people),
            "kinds_checked": sorted(L.LINK_KINDS), "kinds_with_nothing": sorted(set(L.LINK_KINDS) - drawn -
                                                                                {"same_person", "statement"})}


def _gaps(rows, instances, people, cov, store) -> list[dict]:
    """Records missing for the instances asked about: a person with no phone, a phone that does not cover a night,
    an account with no ledger rows for the month (a statement missing or waiting for a person)."""
    out = []
    incidents = [i for i in instances if i["side"] == "incident"]
    for k, p in people.items():
        c = cov.get(k, {})
        if not p["phones"]:
            out.append({"missing": f"a phone for {p['label']}", "words": f"No phone of {p['label']} is in the case; "
                        "their contact shows only on the others' phones, and their positions not at all."})
        else:
            uncovered = [i for i in incidents if not any(lo <= i["end"] and hi >= i["start"] for lo, hi in c.get("phone", []))]
            if uncovered:
                out.append({"missing": f"{p['label']}'s phone records for {len(uncovered)} instance(s)",
                            "words": f"{p['label']}'s phone holds no records for " +
                            ", ".join(i["label"] for i in uncovered[:5]) + "."})
        if p["accounts"]:
            months = {i["start"].strftime("%Y-%m") for i in incidents} | {i["money_end"].strftime("%Y-%m") for i in incidents}
            have = {m for a, ms in store.ledger_months([p]).items() for m in ms}
            lost = sorted(months - have)
            if lost:
                out.append({"missing": f"ledger rows for {p['label']} in {', '.join(lost)}",
                            "words": f"No ledger rows for {p['label']}'s account in {', '.join(lost)}: the statement is "
                            "missing or waits for a person. Payments then are read from phone alerts only."})
        elif any(r["link_kind"] == "money" and k in r["people"] for r in rows):
            out.append({"missing": f"a bank account for {p['label']}",
                        "words": f"No account of {p['label']} is in the case; money to them is read from the payer's "
                        "records and phone alerts."})
    return out


def _not_in_pattern(store, everyone, people, instances, focus) -> list[dict]:
    """Everyone else the case knows, searched against the people on the instances asked about: contact, the same
    place, money. Each says what was searched; "no link found" is never said without it."""
    incidents = [i for i in instances if i["side"] == "incident"]
    others = [p for k, p in everyone.items() if k not in people and (p["phones"] or p["accounts"] or p["numbers"])]
    if not others or not incidents:
        return [], [], []
    windows = [(i["start"], i["money_end"]) for i in incidents]
    group = {**{k: v for k, v in people.items()}, **{p["key"]: p for p in others}}
    raw = store.records(list(group.values()), windows, list(everyone.values()))
    recs, _ = M.dedupe(raw)
    cov = store.coverage(others, [])
    out = []
    media = [r for r in raw if r["kind"] == "media_position" and r.get("owner") not in people]
    alike = []
    for o in others:
        for x in store.lookalike_names(o):
            if x["where"] == "saved on a phone":
                alike.append(f"“{x['name']}” saved on a phone for {x['value']} shares a name with {o['label']} but is "
                             "another number, so it is not joined to them")
    for o in others:
        sub = {**people, o["key"]: o}
        hits = []
        rows = S.contact_rows(sub, recs, incidents, {**cov, **{k: {} for k in people}}) + \
            S.together_rows(sub, recs, incidents, {}) + S.money_rows(sub, recs, incidents, cov)
        rows = [r for r in rows if o["key"] in r["people"]]
        for r in rows:
            n = sum(1 for v in r["cells"].values() if v == "present")
            if n:
                hits.append({"signal": r["label"], "instances": n})
        read = sum(1 for r in raw if r.get("owner") == o["key"] or o["key"] in (r.get("parties") or ()))
        searched = [f"contact with {', '.join(p['label'] for p in people.values())} on {len(incidents)} instance(s)",
                    "the same place within 15 minutes" + ("" if o["phones"] else " (no phone of theirs in the case)"),
                    "money to or from them up to 3 days after"]
        out.append({"who": o["label"], "key": o["key"], "found": hits,
                    "says": ("In the pattern's instances: " + "; ".join(f"{h['signal']} on {h['instances']}" for h in hits))
                    if hits else "No link found in the instances asked about. This is what was searched, not proof "
                                 "that no link exists.",
                    "searched": searched, "counts": {"records_read": read, "instances": len(incidents)},
                    "out_of_reach": [] if o["phones"] else ["their own phone"]})
    out.sort(key=lambda x: (not x["found"], x["who"]))
    for o in out:
        o["received_photos"] = sum(1 for m in media if m.get("owner") == o["key"])
    return out, [(everyone[m["owner"]]["label"] if m.get("owner") in everyone else "a phone", m["ref"]) for m in media], alike


def _add_others_to_checks(checks, media, alike):
    """Received photos and look-alike names among the people outside the pattern are checks too: shown, never links."""
    for c in checks:
        if c["check"] == "received_media" and media:
            who = sorted({w for w, _ in media})
            c["outcome"] = "ruled_out"
            c["words"] = (c["words"] if c["records"] else "") + (" " if c["records"] else "") + \
                f"{len(media)} position{'s' if len(media) != 1 else ''} on the phone of {', '.join(who)} come from photos " \
                "received from someone else on these instances; they show where the photo was taken and do not place " \
                f"{'them' if len(who) > 1 else who[0]} there."
            c["records"] = (c["records"] + [r for _, r in media])[:25]
        if c["check"] == "same_name" and alike:
            c["outcome"] = "ruled_out"
            c["words"] = (c["words"].rstrip(".") + "; " if c["words"].startswith("“") else "") + "; ".join(
                dict.fromkeys(alike)) + "."


def _further(store, people, everyone, rows, instances) -> list[dict]:
    out = []
    pairs = [(a, b) for a, b in combinations(sorted(people), 2)]
    for a, b in pairs[:12]:
        n = store.contact_ever(people[a], people[b])
        if n:
            out.append({"text": f"All contact between {people[a]['label']} and {people[b]['label']} in the case",
                        "count": n, "question": {"kind": "in_contact", "chips": {"who": [a, b]}}})
    if len([i for i in instances if i["side"] == "incident"]) > 1:
        out.append({"text": "Who else was there on these instances", "count": len(everyone) - len(people),
                    "question": {"kind": "who_else", "chips": {"who": list(people)}}})
    return out


def _who_used(store, points, everyone, zone, unread, notes, started, question) -> dict:
    """Who used this phone: every other person's phone compared with it, day by day. A phone that is with one
    person's phone on most days with positions, and never in contact with it, is likely that person's second phone.
    The rule is ``levels.who_used``."""
    phone_key = next((k for p in points if p.get("kind") == "phone" for k in p["people"]), None)
    if not phone_key:
        return _cant(question, "who_used", zone, {}, unread, notes, started, "a phone")
    subject = everyone[phone_key]
    period = store.period([subject])
    if not period:
        return _cant(question, "who_used", zone, {phone_key: subject}, unread, notes, started, "records on the phone")
    tzz = M.tz(zone)
    days = [period[0] + timedelta(days=n) for n in range((period[1] - period[0]).days + 1)]
    instances = [M.make_instance(d, datetime.min.time(), timedelta(hours=24), tzz, "incident", zone) for d in days]
    others = [p for k, p in everyone.items() if k != phone_key and p["phones"]]
    group = {phone_key: subject, **{p["key"]: p for p in others}}
    recs, folded = M.dedupe(store.records(list(group.values()), [(i["start"], i["end"]) for i in instances],
                                          list(everyone.values())))
    rows = [r for r in S.together_rows(group, recs, instances, {}) if phone_key in r["people"]]
    _counts(rows, instances)
    candidates = []
    for r in rows:
        other = next(x for x in r["people"] if x != phone_key)
        contact = store.contact_ever(subject, everyone[other])
        lvl = L.who_used(r["incident"], contact)
        candidates.append({"person": everyone[other]["label"], "key": other, "days_together": r["incident"]["present"],
                           "days_with_positions": r["incident"]["of"], "contact_between": contact, "level": lvl,
                           "records": [x for v in r["records"].values() for x in v][:25]})
    rank = list(L.LEVELS)
    candidates.sort(key=lambda c: (rank.index(c["level"]["key"]), -c["days_together"]))
    best = candidates[0]["level"] if candidates else {"key": "cant_tell", "name": L.LEVELS["cant_tell"],
                                                      "sentence": "Can't tell: no other phone with positions to compare."}
    lead = dict(best)
    if candidates:
        lead["sentence"] = f"{candidates[0]['person']}: {best['sentence']}"
    comparison = {"kind": "same_people_ordinary", "words": f"Every day from {period[0]:%d %b %Y} to {period[1]:%d %b %Y}: "
                  f"each other phone's positions against {subject['label']}'s.", "zone": zone, "incident": [],
                  "ordinary": []}
    return {"schema": SCHEMA, "question": {"kind": "who_used", "text": questions_text_who_used(subject),
                                           "chips": {"phone": phone_key}},
            "level": lead, "comparison": comparison, "grid": _grid(rows, instances)[:10], "candidates": candidates,
            "checks": [], "people": [_person(subject)] + [_person(p) for p in others], "not_in_pattern": [],
            "searched": {"records_read": len(recs), "days": len(days)}, "gaps": [], "look_further": [],
            "unread": unread, "notes": notes, "case_facts_used": [], "seconds": round(time.time() - started, 2)}


def questions_text_who_used(subject) -> str:
    return f"Who used {subject['label']}?"


def _cant(question, kind, zone, people, unread, notes, started, missing_words) -> dict:
    level = {"key": "cant_tell", "name": L.LEVELS["cant_tell"], "rule": "no_data",
             "reasons": [f"The selection holds no {missing_words}."], "comparison": "", "separating_kinds": [],
             "repeated": False, "sentence": f"Can't tell: too little data. Missing: {missing_words}."}
    return {"schema": SCHEMA, "question": {"kind": kind, "text": "", "chips": question.get("chips") or {}},
            "level": level, "comparison": {"kind": None, "words": "", "zone": zone, "incident": [], "ordinary": []},
            "grid": [], "checks": [], "people": [_person(p) for p in people.values()], "not_in_pattern": [],
            "searched": {}, "gaps": [{"missing": missing_words, "words": f"The selection holds no {missing_words}."}],
            "look_further": [], "unread": unread, "notes": notes, "case_facts_used": [],
            "seconds": round(time.time() - started, 2)}
