"""Switches for the agent-fit changes (lx-agentfit), one per item, so a change that fails its release gate stays in
the code, off.

LOUPE_AGENT_FIT lists every item that is on, comma separated (e.g. "W,B,C"); it replaces ON_BY_DEFAULT, so an item on
by default is off unless listed. Unset means ON_BY_DEFAULT; empty means none. B: re-reads and notes outside the investigative budget. C: phone comparisons and analyses computed on
request, a suggested phone or identity instead of a refusal. D: the question-shaped tools. F: test the other side of
a factual question. W: the answer at the tool limit keeps its sources (services.agent.wrap_up).
Round 2 (each measured alone): R compact tool results (model_payloads.compact_for_model); T tool descriptions and
errors written for the model (tool_errors, the Cypher checker's literal lists, page paths mended); P plan, batch
and stop lines in the system prompt; M several names or searches in one call; G graph tools for several entities;
X a step's tool calls run side by side; N working notes capped and the free re-read allowance from measurement;
K the cache-stable history and the finalizer on the agent's prefix together (lean_history).
Round 2, what DeepSeek is given (R2b, each measured by services.agent.answer_quality): S what the case holds and lacks
before the first tool (case_briefing); Q the question restated as a plan in the model's thinking; A the answer
requirements in the final request; V each figure of a cited claim checked against its records before the answer is
stored, unsupported ones listed under it. The default is set from the before-and-after measurement recorded in headless/LX-AGENTFIT-STATUS.md.
"""
from __future__ import annotations

import os

SETTING = "LOUPE_AGENT_FIT"
ITEMS = ("B", "C", "D", "F", "W", "R", "T", "P", "M", "G", "X", "N", "K", "S", "Q", "A", "V")
# Off (11 Nov 2026): the release gate failed on what could be measured before the DeepSeek balance ran out (demo 21 of
# 24 answered as the key says, not 24; simple real requests took longer in 9 of 12 single-sample replays; 2 of 3
# measured defence questions still stopped at the budget). Reverse per item when its measured runs pass the gate.
# W (round 2, R3): the answer at the tool limit keeps its sources. A fix, not an experiment: on once its tests pass
# (lx-agentfit round 2). Reverse: a measured limit answer that is worse with it.
ON_BY_DEFAULT: tuple[str, ...] = ("W",)
# The tools each item adds; not offered to the model while the item is off.
TOOLS = {"B": ("record_working_notes",), "C": ("get_phone_company",), "D": ("check_statements", "get_period_activity")}


def on(item: str) -> bool:
    value = os.environ.get(SETTING)
    items = ON_BY_DEFAULT if value is None else tuple(x.strip().upper() for x in value.split(",") if x.strip())
    return item in items


def hidden_tools() -> frozenset[str]:
    return frozenset(name for item, names in TOOLS.items() if not on(item) for name in names)
