"""The one result shape every search tool returns (plan R4, D19 search-tools part).

Every search result carries:
- ``total``: how many results the search found (all grades), ``shown``: how many are in this page,
  ``next_offset``: the offset of the next page, or ``None`` when this page is the last;
- ``searched``: what was searched and how; ``not_searched``: what was not, and why;
- ``why_empty``: for a search that found nothing, why and what to try; ``None`` otherwise.

``conform`` adds the shape to an older tool result from its own keys, so every search tool says the same things in
the same words. ``check`` is what the contract test runs over every search tool's output.
"""
from __future__ import annotations

from typing import Any

RESULT_KEYS = ("total", "shown", "next_offset", "searched", "not_searched", "why_empty")


def why_empty(res: dict[str, Any], *, below: int = 0) -> str:
    u = res.get("understood") or {}
    parts = ["Nothing found."]
    if below:
        parts = ["No result reached the grade asked for; %d weaker ones were found." % below]
    terms = u.get("terms") or []
    parts.append("Searched %s%s." % ("; ".join(res.get("searched") or []) or "nothing",
                                     (" for the words %s" % ", ".join(terms)) if terms else ""))
    if res.get("not_searched"):
        parts.append("Not searched: %s." % "; ".join(res["not_searched"]))
    if res.get("meaning_search") is False:
        parts.append("Meaning search was unavailable, so only exact words could match.")
    parts.append("Try other words for the same thing, a name or number as the record would print it, or read the "
                 "records directly (messages by person and window, the ledger by account and month). A zero here is "
                 "not proof of absence.")
    return " ".join(parts)


def conform(data: dict[str, Any], *, searched: list[str] | str, not_searched: list[str] | None = None,
            total_key: str = "total_matching", shown_key: str = "returned", items_key: str = "items",
            empty_reason: str | None = None) -> dict[str, Any]:
    """``data`` with the shared keys added from its own (it is changed in place and returned). A result that
    already has a key keeps its value."""
    if not isinstance(data, dict):
        return data
    items = data.get(items_key)
    total = data.get(total_key)
    if total is None and isinstance(items, list):
        total = len(items)
    shown = data.get(shown_key)
    if shown is None and isinstance(items, list):
        shown = len(items)
    data.setdefault("total", int(total or 0))
    data.setdefault("shown", int(shown or 0))
    data.setdefault("next_offset", None)
    data.setdefault("searched", [searched] if isinstance(searched, str) else list(searched))
    data.setdefault("not_searched", list(not_searched or []))
    if data.get("why_empty") is None:
        data["why_empty"] = (empty_reason or data.get("limitation") or data.get("reason") or
                             "Nothing found. Try other words, a name or number as the record prints it, or read the "
                             "records directly. A zero here is not proof of absence.") if not data["total"] else None
    return data


def check(data: dict[str, Any]) -> list[str]:
    """The ways ``data`` breaks the shape (empty when it conforms)."""
    bad = [k for k in RESULT_KEYS if k not in data]
    if bad:
        return ["missing %s" % ", ".join(bad)]
    out = []
    if not isinstance(data["total"], int) or not isinstance(data["shown"], int):
        out.append("total and shown must be whole numbers")
    elif data["shown"] > data["total"]:
        out.append("shown is more than total")
    if not isinstance(data["searched"], list) or not data["searched"]:
        out.append("searched must list what was searched")
    if not isinstance(data["not_searched"], list):
        out.append("not_searched must be a list")
    if isinstance(data.get("total"), int) and data["total"] == 0 and not data.get("why_empty"):
        out.append("an empty result must say why")
    if isinstance(data.get("total"), int) and data["total"] > 0 and data.get("why_empty"):
        out.append("a result with hits must not say why it is empty")
    nxt = data.get("next_offset")
    if nxt is not None and (not isinstance(nxt, int) or nxt <= 0):
        out.append("next_offset must be a positive whole number or None")
    return out


# Every agent tool that searches case content: what it searches, and its own names for total, shown and items.
SEARCH_TOOLS: dict[str, dict[str, str]] = {
    "search_case": {"searched": "every kind of case material (ranked case search) and the word groups"},
    "search_by_meaning": {"searched": "every kind of case material by meaning and words (ranked case search)"},
    "search_documents": {"searched": "document passages by meaning, or by their words when meaning search is down",
                         "items": "chunks"},
    "search_exact_words": {"searched": "every document's stored text for the exact words",
                           "total": "total_documents", "shown": "returned_documents", "items": "results"},
    "search_graph_entities": {"searched": "graph entities by name, key, summary, notes and aliases",
                              "total": "count", "items": "entities"},
    "phone_find_people": {"searched": "phone identities and the names phones give them"},
    "phone_messages": {"searched": "phone messages and calls"},
    "get_financial_transactions": {"searched": "the ledger's statement rows"},
    "find_connected_payments": {"searched": "the ledger's payments"},
    "get_casework": {"searched": "notes, findings and other casework"},
    "list_dossiers": {"searched": "people's dossiers"},
    "get_evidence_files": {"searched": "evidence file names"},
    "get_significant_layer": {"searched": "the items marked significant"},
    "get_map_locations": {"searched": "places on the map", "total": "total"},
    "get_account_mentions": {"searched": "account numbers named in payment descriptions", "total": "total"},
}


def _many(data: dict[str, Any], spec: dict[str, str]) -> None:
    """A result of several searches in one call (``searches``): totals summed over them."""
    subs = [s for s in data.get("searches") or [] if isinstance(s, dict)]
    total = shown = 0
    for s in subs:
        items = s.get(spec.get("items", "items")) or s.get("items") or []
        t = s.get(spec.get("total", "total_matching"), s.get("count"))
        total += int(t if isinstance(t, int) else len(items))
        shown += int(s.get(spec.get("shown", "returned")) or len(items))
    data.setdefault("total", total)
    data.setdefault("shown", min(shown, total) if total else shown)


def apply(tool_name: str, data: Any) -> Any:
    """The shared shape added to a search tool's result (in place), from the tool's own keys."""
    spec = SEARCH_TOOLS.get(tool_name)
    if spec is None or not isinstance(data, dict) or data.get("error"):
        return data
    if isinstance(data.get("searches"), list) and "total" not in data:
        _many(data, spec)
    empty = data.get("limitation") or data.get("reason") or data.get("note") or (
        (data.get("search_coverage") or {}).get("note") if isinstance(data.get("search_coverage"), dict) else None)
    if isinstance(empty, dict):
        empty = None
    conform(data, searched=spec["searched"], total_key=spec.get("total", "total_matching"),
            shown_key=spec.get("shown", "returned"), items_key=spec.get("items", "items"), empty_reason=empty)
    if not data.get("searched"):
        data["searched"] = [spec["searched"]]
    if isinstance(data.get("shown"), int) and isinstance(data.get("total"), int) and data["shown"] > data["total"]:
        data["total"] = data["shown"]
    return data
