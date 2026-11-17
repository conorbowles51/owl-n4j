"""What Loupe takes from a selection and which questions fit it (lx-corroselect E).

``preview`` reads the whole selection (every member, never a page): the people, times, places and items in it, with
counts, what was not in the case, and three to five questions that fit the mix. Each question carries a count Loupe
measured in the selection itself (payments, days, people), its words, and the chips the person can edit (when,
nights, who, what, compare with). Nothing here weighs a link: that is the run's work. Read-only.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from services import case_selections
from services.relations import rules

MAX_QUESTIONS = 5

ITEM_WORDS = {
    "graph_entity": ("graph item", "graph items"), "financial_transaction": ("payment", "payments"),
    "financial_account": ("account", "accounts"), "financial_party": ("party", "parties"),
    "evidence": ("document", "documents"), "timeline_event": ("timeline event", "timeline events"),
    "phone_record": ("phone record", "phone records"), "entry": ("note", "notes"), "place": ("area", "areas"),
}
PERSON_LABELS = {"Person", "Suspect", "Witness", "Victim"}
PLACE_LABELS = {"Location", "Place", "Address"}


def graph_facts(case_id: str, keys: list[str]) -> dict[str, dict[str, Any]]:
    """Each graph node's kind, name and position, matched by key and case together."""
    from services.neo4j.driver import active_node_predicate, driver
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(keys), 1000):
        with driver.session() as session:
            rows = session.run(
                f"MATCH (n) WHERE {active_node_predicate('n')} AND n.key IN $keys "
                "RETURN n.key AS key, labels(n) AS labels, n.name AS name, n.latitude AS lat, n.longitude AS lon",
                case_id=str(case_id), keys=keys[start:start + 1000])
            for row in rows:
                out[row["key"]] = {"labels": list(row["labels"] or []), "name": row["name"],
                                   "lat": row["lat"], "lon": row["lon"]}
    return out


def _words(kind: str, n: int) -> str:
    one, many = ITEM_WORDS.get(kind, (kind.replace("_", " "), kind.replace("_", " ") + "s"))
    return f"{n:,} {one if n == 1 else many}"


def _day(value: str | None) -> str | None:
    when = rules.parse_when(value)
    return when.date().isoformat() if when else None


def _span(days: list[str]) -> str:
    if not days:
        return "no dates in the selection"
    return days[0] if days[0] == days[-1] else f"{days[0]} to {days[-1]}"


def _list(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def read(db, case_id, members: list[dict[str, Any]], *, sources=None, scope: dict[str, Any] | None = None,
         graph: Callable[[str, list[str]], dict[str, dict[str, Any]]] = graph_facts) -> dict[str, Any]:
    """The selection as Loupe reads it: counts of people, times, places and items, and what was not in the case."""
    from services.relations import runs
    from services.relations.sources import DbSources
    named = case_selections.clean_members("relation_query", runs.normalise(db, case_id, list(members)))
    kept, left = case_selections.split_by_case(db, case_id, named)
    items = (sources or DbSources(db, case_id)).load_items(kept) if kept else []
    from services.corroborate import scope as scope_rules
    scoped = scope_rules.apply(items, scope)
    items = scoped["kept"]
    keys = [i["id"] for i in items if i["type"] in ("graph_entity", "timeline_event")]
    try:
        nodes = graph(str(case_id), keys) if keys else {}
    except Exception:  # noqa: BLE001 - without the graph its items still count, as items
        nodes = {}
    people: Counter = Counter()
    shown: dict[str, str] = {}
    places: Counter = Counter()
    days: list[str] = []
    undated = 0
    for item in items:
        node = nodes.get(item["id"], {}) if item["type"] in ("graph_entity", "timeline_event") else {}
        labels = set(node.get("labels") or [])
        if labels & PERSON_LABELS:
            names = [node.get("name") or item["label"]]
        elif item["type"] == "financial_party":
            names = [item["label"]]
        elif item["type"] in ("phone_record", "financial_transaction"):
            names = list(item.get("names") or [])
        else:
            names = []
        for name in names:
            key = rules.name_key(name)
            if key:
                people[key] += 1
                shown.setdefault(key, name)
        place_name = None
        if labels & PLACE_LABELS:
            place_name = node.get("name") or item["label"]
        elif item.get("place"):
            p = item["place"]
            place_name = f"{p['lat']:.3f}, {p['lon']:.3f}"
        if place_name:
            places[place_name] += 1
        day = _day(item.get("at"))
        if day:
            days.append(day)
        elif item["type"] in ("financial_transaction", "phone_record", "timeline_event", "graph_entity") and not item.get("at"):
            undated += 1
    days.sort()
    kinds = Counter(i["type"] for i in items)
    return {
        "members": len(items),
        "selected": len(kept),
        "scope": {"active": scoped["active"], "words": scoped["words"], "outside": scoped["outside"],
                  "outside_total": scoped["outside_total"], "no_time": scoped["no_time"],
                  "anchors": scoped.get("anchors"), "anchors_date_only": scoped.get("anchors_date_only", 0),
                  "kept": [{"type": i["type"], "id": i["id"]} for i in items] if scoped["active"] else None},
        "left_out": {"count": len(left), "examples": [m["id"] for m in left[:20]]},
        "taken": {
            "people": [{"key": k, "label": shown[k], "count": n} for k, n in people.most_common()],
            "times": {"from": days[0] if days else None, "to": days[-1] if days else None, "dated": len(days),
                      "days": len(set(days)), "undated": undated},
            "places": [{"label": k, "count": n} for k, n in places.most_common()],
            "items": [{"type": k, "count": n, "words": _words(k, n)} for k, n in kinds.most_common()],
        },
        "_days": sorted(set(days)),
    }


def questions(taken: dict[str, Any], members: int) -> list[dict[str, Any]]:
    """Three to five questions that fit what the selection holds. Each count is measured in the selection itself."""
    people = taken["people"]
    times = taken["times"]
    kinds = {i["type"]: i["count"] for i in taken["items"]}
    names = [p["label"] for p in people[:4]]
    days = times["days"]
    when = _span([d for d in (times["from"], times["to"]) if d])
    phones = kinds.get("phone_record", 0)
    pays = kinds.get("financial_transaction", 0)
    docs = kinds.get("evidence", 0)
    who = _list(names) or "the people in the selection"
    out: list[dict[str, Any]] = []

    def add(kind, text, count, count_words, what, compare):
        out.append({"kind": kind, "text": text, "count": count, "count_words": count_words,
                    "chips": {"when": when, "nights": f"{days} {'day' if days == 1 else 'days'}" if days else "no dates",
                              "who": who, "what": what, "compare_with": compare}})

    ordinary = "the same hours on other days of the period"
    if len(people) >= 2:
        add("in_contact", f"Were {_list(names[:3])} in contact around {when}?", len(people),
            f"{len(people)} people", "calls, messages, payments", ordinary)
    if phones and (len(people) >= 2 or phones >= 2):
        add("together", "Were these phones in the same place at the same time?", phones, _words("phone_record", phones),
            "positions, calls, messages", ordinary)
    if pays:
        add("payment_connected", f"Is {'this payment' if pays == 1 else 'each of these payments'} connected to the rest of the selection?",
            pays, _words("financial_transaction", pays), "everything within a day of each payment", ordinary)
    if days >= 3:
        add("repeats", "Does this happen every time?", days, f"{days} days", "the same kinds of record on each day",
            "ordinary days of the period")
    if len(people) == 1:
        add("connected_at_all", f"Is {people[0]['label']} connected to anyone else in the case at all?", 1, "1 person",
            "every number, account and name", "everyone else in the case")
    if people and times["dated"] >= 6 and days >= 2:
        add("changed_after", f"Did {people[0]['label']}'s behaviour change after a date?", times["dated"],
            f"{times['dated']} dated records", "timing, contacts, amounts", "the same measures before the date")
    if docs:
        add("document_agrees", "Does this document agree with the phones?" if docs == 1 else "Do these documents agree with the phones?",
            docs, _words("evidence", docs), "times, places, people and amounts in the document", "phone and ledger records")
    add("who_else", "Who else is connected to these?", members, f"{members:,} items", "numbers, accounts, names, places",
        "everyone else in the case")
    # The first questions are the ones the mix points to; "who else" always closes the list when there is room.
    ranked = out[:MAX_QUESTIONS - 1] + [q for q in out if q["kind"] == "who_else"]
    seen: set[str] = set()
    return [q for q in ranked if not (q["kind"] in seen or seen.add(q["kind"]))][:MAX_QUESTIONS]


def preview(db, case_id, members: list[dict[str, Any]], **kw) -> dict[str, Any]:
    data = read(db, case_id, members, **kw)
    data["questions"] = questions(data["taken"], data["members"]) if data["members"] else []
    data.pop("_days", None)
    return data
