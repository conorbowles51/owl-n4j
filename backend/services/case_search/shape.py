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
