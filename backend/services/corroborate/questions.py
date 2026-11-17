"""Question kinds of Corroborate (lx-corroengine F) and the preview: what each kind would check, with counts.

The preview answers within two seconds: it reads the selection, derives its people, times, places and items, and
counts what each question would read, without weighing anything.
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import date

KINDS = {
    "in_contact": "Were they in contact?",
    "together": "Were they together?",
    "payment": "Is this payment connected?",
    "every_time": "Does this happen every time?",
    "who_else": "Who else is part of this?",
    "statement": "Does this fit what someone said?",
    "who_used": "Who used this phone?",
    "connected": "Is this person connected at all?",
    "behaviour_change": "Did this person's behaviour change after a date?",
    "document": "Does this document agree with the phones?",
}
# What each kind reads (link kinds of ``levels.LINK_KINDS``) and how it compares.
CHECKS = {
    "in_contact": ["contact", "shared_content", "absence"],
    "together": ["together", "contact", "money", "access"],
    "payment": ["money", "contact", "together", "sequence"],
    "every_time": ["contact", "together", "money", "access", "absence", "shared_content", "sequence"],
    "who_else": ["contact", "together", "money"],
    "statement": ["statement", "together", "contact", "access"],
    "who_used": ["together", "same_person", "contact"],
    "connected": ["contact", "together", "money", "access", "shared_content"],
    "behaviour_change": ["contact", "absence", "activity"],
    "document": ["access", "together", "contact", "money"],
}
COMPARISON = {"every_time": "same_weekday_hours", "behaviour_change": "before_after"}
CHECK_WORDS = {
    "contact": "calls, messages and e-mails between them, and through a third number within 10 minutes",
    "together": "their phones in the same place within 15 minutes",
    "money": "payments and payment alerts between them, up to 3 days after",
    "access": "badge logs and dated documents naming them",
    "absence": "their phones going silent for 4 hours or more",
    "shared_content": "the same rare words in their messages",
    "sequence": "the same order of events each time",
    "statement": "what the statement says against the records at that time",
    "same_person": "phones that travel together and never contact each other",
    "activity": "how busy their phones are by hour",
}


def default_comparison(kind: str) -> str:
    return COMPARISON.get(kind, "same_people_ordinary")


def default_kind(points: list[dict], people: list[str]) -> str:
    kinds = Counter(p.get("kind") for p in points)
    if kinds.get("phone") and len(people) == 1:
        return "who_used"
    if kinds.get("person") and len(points) == kinds["person"] and len(people) == 1:
        return "connected"
    if kinds.get("payment") or kinds.get("payment_alert"):
        return "every_time" if len(points) > 2 else "payment"
    if kinds.get("doc_row") and len(points) == kinds["doc_row"]:
        return "document"
    days = {p["at"].date() for p in points if p.get("at")}
    if len(days) > 2:
        return "every_time"
    if kinds.get("position") and not (kinds.get("message") or kinds.get("call")):
        return "together"
    return "in_contact"


def suggested(points: list[dict], people: list[str]) -> list[str]:
    """Three to five kinds that fit the selection, the drafted one first."""
    first = default_kind(points, people)
    kinds = Counter(p.get("kind") for p in points)
    fit = [first]
    if len(people) >= 2:
        fit += ["in_contact", "together", "every_time", "who_else"]
    if kinds.get("payment") or kinds.get("payment_alert"):
        fit.insert(1, "payment")
    if kinds.get("doc_row"):
        fit.append("document")
    if len(people) == 1:
        fit += ["connected", "behaviour_change"]
    if kinds.get("phone"):
        fit.append("who_used")
    out = list(dict.fromkeys(fit))
    return out[:5] if len(out) >= 3 else (out + [k for k in ("connected", "who_else", "every_time") if k not in out])[:3]


def words(kind, people: dict, instances: list[dict], comparison: dict, focus=None) -> str:
    names = [p["label"] for p in people.values()]
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1] if names else "these records"
    inc = [i for i in instances if i["side"] == "incident"]
    when = inc[0]["label"] if len(inc) == 1 else f"{len(inc)} {comparison.get('incident_noun', 'instances')}"
    base = {
        "in_contact": f"Were {who} in contact on {when}?",
        "together": f"Were {who} together on {when}?",
        "payment": f"Is the money between {who} connected to {when}?",
        "every_time": f"Do {who} follow the same pattern every time ({when})?",
        "who_else": f"Who else is part of what {who} did on {when}?",
        "statement": f"Does the statement fit the records of {who} on {when}?",
        "who_used": f"Who used {who}'s phone?",
        "connected": f"Is {focus['label'] if focus else who} connected to the others on {when}?",
        "behaviour_change": f"Did {who}'s behaviour change after the date?",
        "document": f"Does the document agree with the phones of {who}?",
    }[kind]
    return base + f" {comparison.get('words', '')}".rstrip()


def preview(store, members: list[dict]) -> dict:
    """What Loupe takes from the selection and the questions that fit it, each with what it would check and counts."""
    from services.corroborate import model as M
    started = time.time()
    zone = store.zone()
    everyone = {p["key"]: p for p in store.people()}
    points, unread = store.selection_points(members)
    keys = list(dict.fromkeys(k for p in points for k in p.get("people") or []))
    places = [p for p in points if p.get("kind") == "place"]
    timed = [p for p in points if p.get("at")]
    incidents, hours = M.incidents_from_selection(timed, zone)
    period = store.period([everyone[k] for k in keys]) if keys else None
    comp_counts = {}
    for kind in ("same_weekday_hours", "same_people_ordinary"):
        ordinary, comp = M.comparison_set(kind, incidents, period, zone, hours) if incidents else ([], {})
        comp_counts[kind] = {"count": len(ordinary), "words": comp.get("words", "")}
    kinds = suggested(points, keys)
    questions = []
    for k in kinds:
        comp = comp_counts.get(default_comparison(k)) or {"count": 0, "words": ""}
        questions.append({
            "kind": k, "text": KINDS[k],
            "count": comp["count"],
            "count_words": (f"{len(incidents)} instance(s) asked about, compared with {comp['count']} ordinary ones"
                            if incidents else "no dated records in the selection"),
            "checks": [{"signal": s, "words": CHECK_WORDS[s], "count": None} for s in CHECKS[k]],
            "chips": {"who": keys, "when": [i["label"] for i in incidents][:12], "compare_with": default_comparison(k),
                      "hours": hours}})
    by_type = Counter(p.get("type") for p in points)
    return {
        "taken": {
            "people": [{"key": k, "label": everyone[k]["label"],
                        "count": sum(1 for p in points if k in (p.get("people") or [])),
                        "identifiers": [{"kind": "number", "value": "+" + n} for n in sorted(everyone[k]["numbers"])] +
                                       [{"kind": "handle", "value": h} for h in sorted(everyone[k]["handles"])],
                        "suggested": any(x["how"] == "suggested" for x in everyone[k]["links"])} for k in keys],
            "times": {"from": M.iso(min((p["at"] for p in timed), default=None)),
                      "to": M.iso(max((p["at"] for p in timed), default=None)), "count": len(timed), "zone": zone,
                      "instances": [i["label"] for i in incidents]},
            "places": [{"label": f"{p['place']['lat']:.5f}, {p['place']['lon']:.5f} within {p['place']['radius_m']:.0f} m",
                        "count": 1} for p in places],
            "items": [{"type": t, "count": n} for t, n in sorted(by_type.items())],
        },
        "left_out": dict(Counter(u["ref"].split(":")[0] for u in unread)),
        "unread": unread,
        "questions": questions,
        "seconds": round(time.time() - started, 2),
    }


def parse_day(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
