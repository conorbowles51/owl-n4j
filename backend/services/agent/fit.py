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
# S, QP, BN and DC against a base is in progress: results with their numbers are recorded here as each lands.
# MEASURED holds the result of a finished measurement: item -> (date, verdict, numbers); an item with a result
# that passed is in ON_BY_DEFAULT, one that did not stays off with the numbers kept here.
_UNMEASURED = "off since 11 Nov: the release gate failed on what could be measured before the DeepSeek balance ran out"
# Measured 17-19 Nov 2026 (demo Q1-Q8, DeepSeek; the driver stopped at its 100 USD balance floor, so Q1-Q4 have 2 repeats
# per config and Q5-Q8 one; decide needs 3 per question, so no item could be accepted or rejected on the gate).
# Answers scored with services.agent.answer_quality (no tool outputs kept): cited claims / claims, key found / answers.
MEASURED: dict[str, tuple[str, str, str]] = {
    "base": ("2026-11-19", "reference", "13 answers: cited 106/175, key found 10/13 (missed Q1 x2, Q4-2: run spread)"),
    "S": ("2026-11-19", "not accepted: fewer than 3 runs", "12 answers: cited 87/175 (base 106), key found 10/12, 2 certainty flags (base 0)"),
    "QP": ("2026-11-19", "not accepted: fewer than 3 runs", "12 answers: cited 88/153, key found 8/12 (lost Q6-1, Q8-1 that base found)"),
    "BN": ("2026-11-19", "not accepted: fewer than 3 runs", "12 answers: cited 81/147, key found 10/12, none lost beyond the base spread"),
    "DC": ("2026-11-19", "not accepted: fewer than 3 runs", "11 answers (no Q7): cited 71/127, key found 7/11 (lost Q2-2)"),
}
OFF_ITEMS: dict[str, tuple[str, str, str]] = {
    # item: (owner, reason, next measurement date)
    "S": ("lx-agentquick", _UNMEASURED + "; case briefing, measured alone from 17 Nov", "2026-11-26"),
    "Q": ("lx-agentquick", _UNMEASURED + "; planning, measured with P from 17 Nov", "2026-11-26"),
    "P": ("lx-agentquick", _UNMEASURED + "; planning, measured with Q from 17 Nov", "2026-11-26"),
    "B": ("lx-agentquick", _UNMEASURED + "; working notes, measured with N from 17 Nov", "2026-11-26"),
    "N": ("lx-agentquick", _UNMEASURED + "; free re-reads, measured with B from 17 Nov", "2026-11-26"),
    "D": ("lx-agentquick", _UNMEASURED + "; hidden tools check_statements, get_period_activity, measured with C", "2026-11-26"),
    "C": ("lx-agentquick", _UNMEASURED + "; hidden tool get_phone_company, measured with D", "2026-11-26"),
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
