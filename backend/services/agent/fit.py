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
# lx-agentquick G (16 Nov 2026): every item that is off has an owner, a reason and the date of its next measurement
# (tests/test_agent_fit_off_items.py fails on an item that has none, or whose date has passed). The measurement of
# S, QP, BN and DC against a base finished 23 Nov: none passed; numbers in MEASURED.
# MEASURED holds the result of a finished measurement: item -> (date, verdict, numbers); an item with a result
# that passed is in ON_BY_DEFAULT, one that did not stays off with the numbers kept here.
_UNMEASURED = "off since 11 Nov: the release gate failed on what could be measured before the DeepSeek balance ran out"
# Measured 17-23 Nov 2026 (demo Q1-Q8, DeepSeek, 3 repeats per question and config, 24 runs each; the driver ran to its
# end). Answers scored with services.agent.answer_quality (no tool outputs kept): cited claims / claims, key found / answers.
# Gate: scripts.financial_agent_prompt_loop decide base.json <item>.json (an item loses nothing beyond the base's own
# range per question). No item passed, so none is on. Each verdict lists the questions that fell outside the base range.
MEASURED: dict[str, tuple[str, str, str]] = {
    "base": ("2026-11-23", "reference", "24 answers: cited 213/342, key found 20/24 (missed Q1 x3, Q4-2)"),
    "S": ("2026-11-23", "not accepted: 7 of 8 questions outside the base range",
          "23 answers: cited 174/321 (base 213/342), key found 18/23, 3 certainty flags (base 0)"),
    "QP": ("2026-11-23", "not accepted: 7 of 8 questions outside the base range",
           "24 answers: cited 208/334, key found 18/24 (lost Q6-1, Q8 x2 that base found)"),
    "BN": ("2026-11-23", "not accepted: 7 of 8 questions outside the base range",
           "24 answers: cited 164/283, key found 21/24 (base 20/24; Q2-2 missed, Q1-1 found), 1 certainty flag"),
    "DC": ("2026-11-23", "not accepted: 8 of 8 questions outside the base range",
           "23 answers: cited 171/288, key found 18/23 (lost Q2-2, Q4-2, Q1 x3 as base), 15 other-side gaps (base 12)"),
}
OFF_ITEMS: dict[str, tuple[str, str, str]] = {
    # item: (owner, reason, next measurement date)
    "S": ("lx-agentquick", _UNMEASURED + "; case briefing: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "Q": ("lx-agentquick", _UNMEASURED + "; planning: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "P": ("lx-agentquick", _UNMEASURED + "; planning: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "B": ("lx-agentquick", _UNMEASURED + "; working notes: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "N": ("lx-agentquick", _UNMEASURED + "; free re-reads: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "D": ("lx-agentquick", _UNMEASURED + "; hidden tools check_statements, get_period_activity: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "C": ("lx-agentquick", _UNMEASURED + "; hidden tool get_phone_company: failed the 3-run gate 23 Nov (see MEASURED)", "2026-12-14"),
    "F": ("lx-deepinvest", _UNMEASURED + "; other-side test of fact questions", "2026-12-01"),
    "R": ("lx-deepinvest", _UNMEASURED + "; compact tool results for the model", "2026-12-01"),
    "T": ("lx-deepinvest", "its Cypher parts are on for everyone since 17 Nov (lx-agentquick D); the tool error and page-path "
                           "parts stay off, never measured alone", "2026-12-01"),
    "M": ("lx-deepinvest", _UNMEASURED + "; several names or searches in one call", "2026-12-01"),
    "G": ("lx-deepinvest", _UNMEASURED + "; graph tools for several entities", "2026-12-01"),
    "X": ("lx-deepinvest", _UNMEASURED + "; a step's tool calls side by side", "2026-12-01"),
    "K": ("lx-deepinvest", _UNMEASURED + "; cache-stable history", "2026-12-01"),
    "A": ("lx-deepinvest", _UNMEASURED + "; answer requirements in the final request", "2026-12-01"),
    "V": ("lx-deepinvest", _UNMEASURED + "; figure check before the answer is stored", "2026-12-01"),
}
# The tools each item adds; not offered to the model while the item is off.
TOOLS = {"B": ("record_working_notes",), "C": ("get_phone_company",), "D": ("check_statements", "get_period_activity")}


def on(item: str) -> bool:
    value = os.environ.get(SETTING)
    items = ON_BY_DEFAULT if value is None else tuple(x.strip().upper() for x in value.split(",") if x.strip())
    return item in items


def hidden_tools() -> frozenset[str]:
    return frozenset(name for item, names in TOOLS.items() if not on(item) for name in names)
