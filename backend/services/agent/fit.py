"""Switches for the agent-fit changes (lx-agentfit), one per item, so a change that fails its release gate stays in
the code, off.

LOUPE_AGENT_FIT lists the items that are on, comma separated (e.g. "B,C,D,F"); unset means ON_BY_DEFAULT; empty
means none. B: re-reads and notes outside the investigative budget. C: phone comparisons and analyses computed on
request, a suggested phone or identity instead of a refusal. D: the question-shaped tools. F: test the other side of
a factual question. The default is set from the before-and-after measurement recorded in headless/LX-AGENTFIT-STATUS.md.
"""
from __future__ import annotations

import os

SETTING = "LOUPE_AGENT_FIT"
ITEMS = ("B", "C", "D", "F")
ON_BY_DEFAULT = ("B", "C", "D", "F")
# The tools each item adds; not offered to the model while the item is off.
TOOLS = {"B": ("record_working_notes",), "C": ("get_phone_company",), "D": ("check_statements", "get_period_activity")}


def on(item: str) -> bool:
    value = os.environ.get(SETTING)
    items = ON_BY_DEFAULT if value is None else tuple(x.strip().upper() for x in value.split(",") if x.strip())
    return item in items


def hidden_tools() -> frozenset[str]:
    return frozenset(name for item, names in TOOLS.items() if not on(item) for name in names)
