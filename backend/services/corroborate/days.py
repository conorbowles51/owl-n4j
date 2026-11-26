"""The evidence day by day (lx-corroredo C): what the answer page draws under the level.

One link between the people is *the relation* the question asks about (for "Were they together?", their phones in
the same place). It is defined in one sentence naming the phones and their owners. Each instance asked about becomes
a tile: its date, the selected records that made it (a check number and amount, a message), the relation's outcome
that day and when it held. The ordinary instances are counted: present, absent, and no data, which counts neither
way and is drawn apart.

Everything here is read from the engine's own rows and records, by rule; nothing is weighed again and no model is
asked. *Reverse if* the engine starts returning its own definition per row: then ``relation`` reads that instead.
"""
from __future__ import annotations

import re
from datetime import datetime

from services.corroborate import model as M

# The link kind each question asks about first; the others are evidence around it.
PRIMARY = {"together": "together", "in_contact": "contact", "payment": "money", "statement": "statement",
           "document": "access", "who_else": "contact", "connected": "contact", "behaviour_change": "absence"}

# Per link kind: (the relation in one word, present, absent, no data, what records it reads).
WORDS = {
    "together": ("together", "Together", "Apart", "No location data", "location records"),
    "contact": ("in contact", "In contact", "No contact", "No phone records", "calls, messages and e-mails"),
    "money": ("paid each other", "Money moved", "No payment", "No bank records", "bank rows and payment alerts"),
    "access": ("named or logged together", "Named together", "Not named", "No records", "badge logs and documents"),
    "absence": ("silent", "Silent", "In use", "No phone records", "phone activity"),
    "shared_content": ("using the same rare words", "Same words", "Not found", "No messages", "messages"),
    "sequence": ("in the same order of events", "Same order", "Not found", "No records", "the records above"),
    "statement": ("as the statement says", "Fits", "Does not fit", "No records", "the records at that time"),
    "activity": ("busy at the same hours", "Busy", "Quiet", "No phone records", "phone activity"),
    "same_person": ("travelling together", "Together", "Apart", "No location data", "location records"),
}
_GENERIC = ("linked", "Found", "Not found", "No records", "the case's records")

_CHECK = re.compile(r"\b(?:check|cheque|chk|ck)\s*(?:no\.?|number|#)?\s*(\d{3,8})\b", re.I)


def _words(kind: str) -> tuple[str, str, str, str, str]:
    return WORDS.get(kind, _GENERIC)


def _names(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1] if labels else "them"


def pick_row(rows: list[dict], kind: str, people: list[str]) -> dict | None:
    """The relation: a row of the question's link kind between the people asked about, weighed and not context,
    the one present on most incidents; else the row that best tells incidents from ordinary instances."""
    usable = [r for r in rows if not r.get("context") and not r.get("picked_by") and r["link_kind"] != "sequence"]
    want = PRIMARY.get(kind)
    asked = set(people)

    def share(r, side):
        c = r[side]
        seen = c["present"] + c.get("absent", 0)
        return c["present"] / seen if seen else 0.0

    first = [r for r in usable if r["link_kind"] == want and (len(asked) < 2 or len(set(r["people"]) & asked) >= 2)]
    pool = first or [r for r in usable if r["link_kind"] == want] or usable
    if not pool:
        return None
    return max(pool, key=lambda r: (share(r, "incident") - share(r, "ordinary"), r["incident"]["present"],
                                    r.get("weight", "full") == "full", r["label"]))


def _local(at: datetime | None, zone) -> datetime | None:
    return at.astimezone(zone) if at else None


def _clock(t: datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def _span(times: list[datetime], zone) -> str:
    loc = sorted(_local(t, zone) for t in times if t)
    if not loc:
        return ""
    if loc[0] == loc[-1] or (loc[-1] - loc[0]).total_seconds() < 60:
        return f"at {_clock(loc[0])}"
    return f"{_clock(loc[0])} to {_clock(loc[-1])}"


def event_words(p: dict) -> str:
    """One selected record in a few words: "Check 2204 · $2,460.00", "Message at 9:14 PM"."""
    k = p.get("kind")
    if k == "payment":
        amount = M.fmt_money(p.get("amount_minor"))
        m = _CHECK.search(p.get("memo") or "")
        what = f"Check {m.group(1)}" if m else ("Money in" if p.get("direction") == "credit" else "Payment")
        return f"{what} · {amount}"
    if k == "payment_alert":
        return "Payment alert on a phone"
    if k == "doc_row":
        text = " ".join(str(p.get("label") or "").split())
        return f"Document: {text[:77]}…" if len(text) > 80 else f"Document: {text}" if text else "A document line"
    noun = {"message": "Message", "call": "Call", "email": "E-mail", "position": "Location", "media_position": "Photo place",
            "activity": "Phone in use"}.get(k or "", "Record")
    return noun


_PLURAL = {"Message": "messages", "Call": "calls", "E-mail": "e-mails", "Location": "locations",
           "Photo place": "photo places", "Phone in use": "records of a phone in use", "Record": "records",
           "Payment alert on a phone": "payment alerts on a phone", "A document line": "document lines"}


def collapse(words: list[str]) -> list[str]:
    """The same few words said once with their count ("8 messages"), in the order first seen; each different line
    (a check, a document) stays as it is."""
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return [w if n == 1 else f"{n} {_PLURAL.get(w, w)}" if w in _PLURAL else f"{w} ({n} times)" for w, n in counts.items()]


def _events_phrase(points: list[dict], n: int) -> tuple[str, str]:
    """("the 7 check deposits", "from the financial records") for the question sentence and the tiles' heading."""
    kinds = {p.get("kind") for p in points if p.get("at")}
    s = "" if n == 1 else "s"
    if kinds <= {"payment"} and kinds:
        checks = [p for p in points if _CHECK.search(p.get("memo") or "")]
        credit = all(p.get("direction") == "credit" for p in points if p.get("kind") == "payment")
        noun = ("check deposit" if credit else "check payment") if len(checks) == len(points) else \
            ("deposit" if credit else "payment")
        return f"the {n} {noun} day{s}" if n != 1 else f"the day of the {noun}", "from the financial records"
    if kinds <= {"message", "call", "email", "payment_alert", "position", "media_position", "activity"} and kinds:
        return f"the {n} day{s} of the phone records you chose", "from the phone records"
    if kinds <= {"doc_row"} and kinds:
        return f"the {n} day{s} the document names", "from the document"
    return f"the {n} day{s} you chose", "from the records you chose"


def _events_by_instance(points: list[dict], incidents: list[dict]) -> dict[str, list[dict]]:
    out = {i["id"]: [] for i in incidents}
    for p in points:
        at = p.get("at")
        if not at:
            continue
        for i in incidents:
            if (p.get("day_only") and at.date().isoformat() == i["day"]) or i["start"] <= at <= i["end"] or (
                    p.get("kind") in M.MONEY_KINDS and i["start"] <= at <= i["money_end"]):
                out[i["id"]].append(p)
                break
    return out


def _short_day(inst: dict) -> str:
    from datetime import date
    d = date.fromisoformat(inst["day"])
    return f"{d:%a} {d.day} {d:%b %Y}"


def _phone_words(people: dict, keys: list[str]) -> list[str]:
    out = []
    for k in keys:
        p = people.get(k)
        if not p:
            continue
        labels = [(p.get("phone_labels") or {}).get(e, "a phone") for e in p["phones"]]
        if not labels:
            out.append(f"{p['label']} (no phone of theirs is in the case)")
        elif len(labels) == 1:
            out.append(f"{p['label']}'s phone ({labels[0]})" if p.get("dossier_id") else labels[0])
        else:
            out.append(f"{p['label']}'s phones ({_names(labels)})" if p.get("dossier_id") else _names(labels))
    return out


def _definition(row: dict, people: dict) -> str:
    word = _words(row["link_kind"])[0]
    phones = _names(_phone_words(people, row["people"]))
    if row["link_kind"] == "together":
        prec = row.get("precision_m")
        reach = f" (the roughest location used is accurate to about {prec:,.0f} m)" if prec else ""
        return (f"“{word.capitalize()}” means {phones} were placed within each other's accuracy plus "
                f"{M.TOGETHER_SLACK_M:.0f} m, within {int(M.TOGETHER_GAP.total_seconds() // 60)} minutes of each other, "
                f"from their location records{reach}.")
    if row["link_kind"] == "contact":
        return (f"“{word.capitalize()}” means a call, message or e-mail between them, or through a third number within "
                f"10 minutes, on {phones}.")
    if row["link_kind"] == "money":
        return f"“{word.capitalize()}” means a payment or payment alert between them, up to 3 days after, for {_names([people[k]['label'] for k in row['people'] if k in people])}."
    return f"“{word.capitalize()}” here is the row “{row['label']}”, read from {_words(row['link_kind'])[4]} of {phones}."


def _missing_who(row, inst, recs_by_inst, people) -> str:
    kinds = {"together": ("position",), "contact": tuple(M.CONTACT_KINDS)}.get(row["link_kind"])
    if not kinds:
        return "The records that would show it do not cover this day, so it counts neither way."
    have = {r.get("owner") for r in recs_by_inst.get(inst["id"], []) if r["kind"] in kinds}
    lacking = [people[k]["label"] for k in row["people"] if k in people and k not in have]
    what = "locations" if row["link_kind"] == "together" else "phone records"
    if not lacking:
        return "The records that would show it do not cover this day, so it counts neither way."
    return f"{_names(lacking)}'s phone has no {what} that day, so it counts neither way."


def build(rows: list[dict], instances: list[dict], recs: list[dict], points: list[dict], people: dict, kind: str,
          comparison: dict, zone_name: str) -> dict:
    zone = M.tz(zone_name)
    incidents = [i for i in instances if i["side"] == "incident"]
    ordinary = [i for i in instances if i["side"] == "ordinary"]
    events_phrase, source = _events_phrase(points, len(incidents))
    row = pick_row(rows, kind, list(people))
    by_ref = {r["ref"]: r for r in recs}
    events = _events_by_instance(points, incidents)
    out = {"events_phrase": events_phrase, "events_source": source, "people": [people[k]["label"] for k in people]}
    if row is None:
        out.update(row=None, relation=None, tiles=[], ordinary=None)
        return out
    word, yes, no, none, _reads = _words(row["link_kind"])
    from services.corroborate.signals import bucket
    recs_by_inst = bucket(recs, instances)
    tiles = []
    for i in incidents:
        state = row["cells"].get(i["id"], "no_data")
        refs = row["records"].get(i["id"], [])
        if state == "present":
            detail = _span([by_ref[x]["at"] for x in refs if x in by_ref and by_ref[x].get("at") and
                            not by_ref[x].get("day_only")], zone) or "that day"
        elif state == "absent":
            detail = f"Checked; not {word} in these hours"
        else:
            detail = _missing_who(row, i, recs_by_inst, people)
        ev = events.get(i["id"], [])
        tiles.append({"instance": i["id"], "date": _short_day(i), "hours": i["label"],
                      "events": collapse([event_words(p) for p in ev]), "event_refs": [p["ref"] for p in ev],
                      "outcome": state, "outcome_words": {"present": yes, "absent": no, "no_data": none}[state],
                      "detail": detail, "records": refs})
    counts = {"present": 0, "absent": 0, "no_data": 0}
    cells = []
    for i in ordinary:
        st = row["cells"].get(i["id"], "no_data")
        counts[st] += 1
        cells.append({"instance": i["id"], "date": _short_day(i), "state": st})
    first, last = (ordinary[0], ordinary[-1]) if ordinary else (None, None)
    span = f"{_short_day(first)} to {_short_day(last)}" if first else ""
    out.update(
        row=row["id"],
        relation={"link_kind": row["link_kind"], "word": word, "label": row["label"], "people": row["people"],
                  "definition": _definition(row, people), "present": yes, "absent": no, "no_data": none},
        tiles=tiles,
        ordinary={"of": len(ordinary), **counts, "noun": comparison.get("ordinary_noun", "ordinary days"),
                  "span": span, "cells": cells,
                  "words": (f"{yes} on {counts['present']:,}, {no.lower()} on {counts['absent']:,}, "
                            f"{none.lower()} on {counts['no_data']:,}") if ordinary else
                  "No ordinary days to compare with."},
    )
    return out
