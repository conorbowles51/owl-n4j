"""Which analysis can link which two kinds of item, and on what key (lx-overlaps A).

One table, read by the engine to choose analyses and by the report to say, for a pair of types no analysis reaches,
"no analysis links these types". Nothing is skipped silently: an empty cell is a stated result.
``existing`` names the module an analysis calls; the engine never copies it.
"""
from __future__ import annotations

from itertools import combinations_with_replacement

TYPES = {
    "phone_record": "phone record", "financial_transaction": "payment", "financial_account": "account",
    "financial_party": "party", "evidence": "document or passage", "graph_entity": "graph entity",
    "timeline_event": "timeline event", "place": "place", "entry": "dossier or note",
}
DATED = ("phone_record", "financial_transaction", "graph_entity", "timeline_event")
EVERYTHING = tuple(TYPES)
PLACED = ("phone_record", "place", "financial_transaction")

ANALYSES: dict[str, dict] = {
    "time_proximity": {"title": "Close in time", "key": "time", "types": [(a, b) for a in DATED for b in DATED],
                       "existing": None, "base": "days with a record of each kind in the period"},
    "sequence": {"title": "Order of events", "key": "time", "types": [(a, b) for a in DATED for b in DATED],
                 "existing": None, "base": "days with a record of each kind in the period"},
    "shared_identifier": {"title": "Same number, email, account or name", "key": "identifier",
                          "types": [(a, b) for a in EVERYTHING for b in EVERYTHING if a != "place" and b != "place"],
                          "existing": None, "base": "ledger rows carrying the same identifier"},
    "same_amount": {"title": "Same amount", "key": "amount", "types": [("financial_transaction", "financial_transaction")],
                    "existing": "services.phone_analysis.money_pairings", "base": "none"},
    "place_overlap": {"title": "Same place, same time", "key": "place",
                      "types": [(a, b) for a in PLACED for b in PLACED],
                      "existing": "services.pattern_of_life.places", "base": "other phones near the place; routine place; clock offset"},
    "relay_chain": {"title": "Relay: one contacts someone, who then contacts the other", "key": "contact",
                    "types": [("phone_record", "phone_record")], "existing": None, "base": "none"},
    "shared_silence": {"title": "Both quiet at once", "key": "time", "types": [("phone_record", "phone_record")],
                       "existing": None, "base": "each phone's silences of that length"},
    "together_apart": {"title": "Used by the same person (alternating use)", "key": "time",
                       "types": [("phone_record", "phone_record")],
                       "existing": "services.phone_analysis.device_users", "base": "days both phones hold owner use"},
}


def _pair(a: str, b: str) -> frozenset:
    return frozenset((a, b))


def applicable(type_a: str, type_b: str) -> list[str]:
    key = _pair(type_a, type_b)
    return [aid for aid, spec in ANALYSES.items() if any(_pair(x, y) == key for x, y in spec["types"])]


def table() -> list[dict]:
    rows = []
    for a, b in combinations_with_replacement(TYPES, 2):
        ids = applicable(a, b)
        rows.append({"a": a, "b": b, "analyses": ids,
                     "keys": sorted({ANALYSES[i]["key"] for i in ids}),
                     "says": None if ids else "no analysis links these types"})
    return rows


def empty_cells() -> list[tuple[str, str]]:
    return [(r["a"], r["b"]) for r in table() if not r["analyses"]]


def markdown() -> str:
    out = ["| | " + " | ".join(TYPES[t] for t in TYPES) + " |", "|---|" + "---|" * len(TYPES)]
    for a in TYPES:
        cells = []
        for b in TYPES:
            ids = applicable(a, b)
            cells.append(", ".join(sorted({ANALYSES[i]["key"] for i in ids})) or "none")
        out.append(f"| {TYPES[a]} | " + " | ".join(cells) + " |")
    return "\n".join(out)
