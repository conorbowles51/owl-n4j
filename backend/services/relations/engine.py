"""The link-analysis engine (lx-overlaps B).

``run`` takes a group of any mix of items, picks every analysis in ``matrix`` that applies to each pair or subset, runs
them by rule and returns:

- ``candidates``: every candidate link, weak ones as weak: kind, members, key, strength, plain reasons, the chance
  sentence (count and base);
- ``no_links``: for every pair with no candidate, what was searched, how much, and what was out of reach. A pair no
  analysis reaches says "no analysis links these types". Absence of a search is never shown as absence of a link;
- ``analyses``: each analysis that was run, with how many pairs it covered and found.

The result says what occurs together. It never says why.
"""
from __future__ import annotations

import time
from itertools import combinations
from typing import Any, Callable

from services.relations import matrix, rules
from services.relations.sources import OutOfReach

SCHEMA = "loupe.relations/1"
SAYS = "These are records that occur together. They do not show why."


def _pair_key(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def run(sources, members: list[dict], progress: Callable[[str, int, int], None] | None = None) -> dict[str, Any]:
    started = time.time()
    step = progress or (lambda *_: None)
    items = sources.load_items(members)
    by_ref = {i["ref"]: i for i in items}
    step("Reading the items", len(items), len(items))
    out_of_reach: list[dict] = []
    candidates: list[dict] = []
    searched: list[dict] = []
    ran: dict[str, dict] = {}

    def record(aid, covered, found, note=None):
        ran[aid] = {"id": aid, "title": matrix.ANALYSES[aid]["title"], "pairs": covered, "found": found,
                    "existing": matrix.ANALYSES[aid]["existing"], **({"note": note} if note else {})}

    def pairs_for(aid):
        return [(a, b) for a, b in combinations(items, 2) if aid in matrix.applicable(a["type"], b["type"])]

    try:
        base = sources.base(items)
    except Exception as exc:  # noqa: BLE001
        base = {"period_days": 0, "days_with": {}}
        out_of_reach.append({"analysis": "baseline", "reason": f"The case's day counts could not be read: {exc}"})
    step("Counting how often these kinds of record occur", 1, 1)

    # time
    tp = pairs_for("time_proximity")
    c, s = rules.time_proximity([i for i in items if i["type"] in matrix.DATED], base) if tp else ([], [])
    c = [x for x in c if aid_ok("time_proximity", x, by_ref)]
    s = [x for x in s if aid_ok("time_proximity", x, by_ref, pair_only=True)]
    candidates += c; searched += s
    record("time_proximity", len(tp), len(c))
    seq = rules.sequences([i for i in items if i["type"] in matrix.DATED], base)
    candidates += seq
    record("sequence", len(tp), len(seq))
    step("Time", 1, 1)

    # identifiers
    ip = pairs_for("shared_identifier")

    def counts(kind, value):
        try:
            return sources.identifier_counts(kind, value)
        except Exception:  # noqa: BLE001
            return None
    c, s = rules.shared_identifiers(items, counts) if ip else ([], [])
    candidates += c; searched += s
    record("shared_identifier", len(ip), len(c))
    step("Identifiers", 1, 1)

    am = rules.money_amounts([i for i in items if i["type"] == "financial_transaction"])
    candidates += am
    record("same_amount", len(pairs_for("same_amount")), len(am))

    # place
    pp = pairs_for("place_overlap")
    if pp:
        try:
            c, s = rules.place_overlap(items, sources.place_stats, pair_stats=getattr(sources, "pair_stats", None))
        except Exception as exc:  # noqa: BLE001
            c, s = [], []
            out_of_reach.append({"analysis": "place_overlap", "reason": f"Positions could not be read: {exc}"})
        candidates += c; searched += s
        record("place_overlap", len(pp), len(c))
    step("Place", 1, 1)

    # phone streams
    phones = sorted({i["phone"] for i in items if i.get("phone")})
    if len(phones) >= 2:
        try:
            events = sources.events(phones)
            labels = {p: next((i["label"] for i in items if i.get("phone") == p), p[:8]) for p in phones}
            for e in events:
                e["label"] = labels[e["phone"]]
            c, n = rules.relay_chains(events, phones)
            candidates += c
            record("relay_chain", len(phones) * (len(phones) - 1) // 2, len(c), f"{n['events_read']:,} contacts read")
            streams = sources.streams(phones)
            c, n = rules.shared_silence(streams)
            candidates += c
            record("shared_silence", len(phones) * (len(phones) - 1) // 2, len(c),
                   f"{sum(len(v) for v in streams.values()):,} activity times read")
        except Exception as exc:  # noqa: BLE001
            out_of_reach.append({"analysis": "relay_chain, shared_silence", "reason": f"Phone activity could not be read: {exc}"})
        found = 0
        for pa, pb in combinations(phones, 2):
            try:
                res = sources.together_apart(pa, pb)
            except Exception as exc:  # noqa: BLE001
                out_of_reach.append({"analysis": "together_apart", "reason": f"Alternating use could not be measured: {exc}"})
                break
            if res.get("days"):
                phi = res.get("phi")
                level = "moderate" if phi is not None and phi < -0.3 else "weak" if phi is not None and phi < 0 else "faint"
                candidates.append(rules.candidate(
                    "together_apart", [pa, pb], "time", level,
                    [f"On {res['days']} days both phones hold owner use, {res['both']} quarter-hours were shared, "
                     f"{res['only_x']} used only on one and {res['only_y']} only on the other. Correlation {phi}: "
                     "below zero means the phones are used one after the other."],
                    chance={"words": f"{res['both']:,} of {res['bins']:,} quarter-hours on those days had both phones in use.",
                            "reading": "none", "share_of_days": None}, extra=res))
                found += 1
        record("together_apart", len(phones) * (len(phones) - 1) // 2, found)
    elif phones:
        out_of_reach.append({"analysis": "relay_chain, shared_silence, together_apart",
                             "reason": "Only one phone is in the group; these compare two or more phones."})
    step("Phones", 1, 1)

    # map phone-level candidates back onto the items so every pair can be read
    phone_items: dict[str, list[str]] = {}
    for i in items:
        if i.get("phone"):
            phone_items.setdefault(i["phone"], []).append(i["ref"])
    linked: dict[frozenset, list[dict]] = {}
    for cand in candidates:
        refs = cand["members"]
        expanded = [r for m in refs for r in (phone_items.get(m, []) if m not in by_ref else [m])]
        for a, b in combinations(dict.fromkeys(expanded), 2):
            linked.setdefault(_pair_key(a, b), []).append(cand)
    no_links = []
    for a, b in combinations(items, 2):
        if linked.get(_pair_key(a["ref"], b["ref"])):
            continue
        ids = matrix.applicable(a["type"], b["type"])
        notes = [n for n in searched if {a["ref"], b["ref"]} <= set(n["members"])]
        if not ids:
            no_links.append({"members": [a["ref"], b["ref"]], "analyses": [], "searched": [],
                             "says": f"No analysis links a {matrix.TYPES[a['type']]} to a {matrix.TYPES[b['type']]}.",
                             "out_of_reach": []})
            continue
        reach = [n["searched"] for n in notes if n.get("out_of_reach")]
        no_links.append({"members": [a["ref"], b["ref"]], "analyses": ids,
                         "searched": [n["searched"] for n in notes if not n.get("out_of_reach")] or
                         [f"{matrix.ANALYSES[i]['title']}: {a['label']} against {b['label']}" for i in ids],
                         "says": "Nothing found by the analyses that apply. This is what was searched, not proof that no link exists.",
                         "out_of_reach": reach + [o["reason"] for o in out_of_reach if o["analysis"] in ids or
                                                  any(x.strip() in ids for x in o["analysis"].split(","))]})
    rank = {l: n for n, l in enumerate(rules.LEVELS)}
    candidates.sort(key=lambda c: (rank[c["strength"]], c["kind"]))
    return {"schema": SCHEMA, "says": SAYS, "items": items, "base": base, "candidates": candidates, "no_links": no_links,
            "analyses": list(ran.values()), "out_of_reach": out_of_reach,
            "counts": {"items": len(items), "pairs": len(items) * (len(items) - 1) // 2,
                       "candidates": len(candidates), "no_links": len(no_links),
                       "by_strength": {l: sum(1 for c in candidates if c["strength"] == l) for l in rules.LEVELS}},
            "seconds": round(time.time() - started, 2)}


def aid_ok(aid, cand_or_note, by_ref, pair_only=False) -> bool:
    """Keep a rule's output only for pairs of types the matrix says that analysis covers."""
    refs = [m for m in cand_or_note["members"] if m in by_ref]
    return all(aid in matrix.applicable(by_ref[a]["type"], by_ref[b]["type"]) for a, b in combinations(refs, 2)) if len(refs) > 1 else True
