"""What the case holds and lacks, told to the agent before its first tool (lx-agentfit round 2, R2b item S).

The demo's Q1 run asked for a together-and-apart run that had never been made, and runs in cases with no phones
searched phones. One short block of counts, read-only and exact, saves those dead ends: what the case holds of each
kind, which phone analyses have been run, and that a kind or analysis the case lacks is said, not searched for.
Counts only (no case content), so the block is the same for every question in a case until its material changes.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_KINDS = (("ledger", "payments in the ledger"), ("financial_sources", "bank or brokerage statements"),
          ("trades", "brokerage trades"), ("phones", "phone extractions"), ("documents", "other documents"),
          ("dossiers", "dossiers"), ("timeline", "timeline entries"))
LACKS = ("Where the case holds none of a kind, or an analysis has not been run, say so in the answer instead of "
         "searching for it; a tool that computes an analysis on request may still be used.")


def _analyses(conn, case_id) -> tuple[dict[str, int], int | None]:
    from sqlalchemy import text
    runs: dict[str, int] = {}
    together = None
    try:
        with conn.begin_nested():
            for approach, n in conn.execute(text(
                    "SELECT approach, count(*) FROM phone_analysis_runs WHERE case_id = :c AND status = 'completed' "
                    "GROUP BY approach ORDER BY approach"), {"c": str(case_id)}):
                runs[str(approach)] = int(n)
    except Exception:  # noqa: BLE001 - a test schema: the line is left out, never shown as "none"
        runs = {}
    try:
        with conn.begin_nested():
            together = int(conn.execute(text("SELECT count(*) FROM pol_colocation_run WHERE case_id = :c"),
                                        {"c": str(case_id)}).scalar() or 0)
    except Exception:  # noqa: BLE001
        together = None
    return runs, together


def briefing(conn, case_id, counts: dict[str, Any]) -> str:
    """The block, or "" when nothing could be counted. A count that failed is said to be unknown."""
    held, none, unknown = [], [], []
    for kind, words in _KINDS:
        value = counts.get(kind)
        if value is None:
            unknown.append(words)
        elif value:
            held.append(f"{value:,} {words}")
        else:
            none.append(words)
    if not held and not none:
        return ""
    lines = ["What this case holds (counted for this question):"]
    if held:
        lines.append("- Holds: " + "; ".join(held) + ".")
    if none:
        lines.append("- Holds none: " + "; ".join(none) + ".")
    if unknown:
        lines.append("- Could not be counted: " + "; ".join(unknown) + ".")
    if counts.get("phones"):
        runs, together = _analyses(conn, case_id)
        if runs:
            lines.append("- Phone analyses run: " + "; ".join(f"{a} {n}" for a, n in runs.items()) + ".")
        elif runs == {}:
            lines.append("- Phone analyses run: none stored.")
        if together is not None:
            lines.append(f"- Together-and-apart runs made: {together}.")
    lines.append(LACKS)
    return "\n".join(lines)
