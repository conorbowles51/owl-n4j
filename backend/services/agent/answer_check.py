"""Completeness check for a normal (not deep) agent run (D18, C2e).

A live sample of 523 stored runs: median 6 tool calls, ``search_case`` found nothing on 109 of 312 calls, and the
answer then said "none found" without saying what was searched. Before a normal run writes its answer, this check
looks at the run's own tool calls. If searches found nothing and no later call found anything, the run goes back once
with the list of what was tried, and is told that a "none found" answer states what was searched.

Decision: one return per run (state["returned"]); a deep run has its own gate and never uses this one. Reverse if a
measured run is made worse by the extra step.
"""
from __future__ import annotations

from typing import Any

SEARCH_NAMES = ("search_", "get_contact_and_money_between", "get_person_phones", "get_account_mentions")
_COUNT_KEYS = ("total_matching", "total", "records_read", "count")


def _is_search(name: str) -> bool:
    return any(name.startswith(p) for p in SEARCH_NAMES)


def _found(preview: Any) -> bool:
    if not isinstance(preview, dict):
        return preview not in (None, "", [], {})
    for k in ("total_matching", "total"):
        if k in preview:
            return bool(preview[k])
    if preview.get("relevant"):
        return True
    if "records_read" in preview:
        return bool(preview["records_read"]) and bool(preview.get("relevant"))
    return any(bool(v) for v in preview.values())


def _empty_search(item: dict) -> bool:
    return (item.get("status") == "success" and _is_search(item.get("name") or "")
            and not _found(item.get("result_preview")))


def check_message(trace: list[dict], state: dict) -> str | None:
    if state.get("returned"):
        return None
    empties = [t for t in trace if _empty_search(t)]
    if not empties:
        return None
    last_empty = max(i for i, t in enumerate(trace) if _empty_search(t))
    # Something found after the last empty search counts as the retry that worked.
    for t in trace[last_empty + 1:]:
        if t.get("status") == "success" and _found(t.get("result_preview")) and t.get("name") not in ("",):
            return None
    state["returned"] = True
    rows = []
    for t in empties[:8]:
        q = (t.get("arguments") or {})
        rows.append("- %s %s" % (t["name"], ", ".join("%s=%s" % (k, str(v)[:60]) for k, v in list(q.items())[:3])))
    return ("Completeness check, not a new instruction from the person. These searches found nothing:\n%s\n"
            "Before you answer, try another route for each: a different tool, other words from the records you "
            "have seen, or read_scope_with_model on the conversation, document or window itself. If you still find "
            "nothing, say what was searched and what was not, never only that none was found." % "\n".join(rows))
