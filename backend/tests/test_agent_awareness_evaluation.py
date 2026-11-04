"""Agent evaluation questions for approach 4 steps 1 to 4 and approach 5 steps 2 and 4 (cb-gated-aware E; AGENT-INDEX
rule 6), measured through the agent's own tool (get_analysis_results, the StructuredTool layer the model calls) under
both case layers, in the format of the phone and cross sets.

All data: every question's stated total equals its known answer and its check holds (strength, counts per strength,
the counts the results rest on). Significant: every question is refused with the boundary and returns no records.
Known answers are written by hand from the events below. LOUPE_AGENT_EVAL_OUT writes the measured table as JSON.
Synthetic data only; needs the PostgreSQL template.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_analysis_device_users import _event, _place

pytestmark = needs_template
OWNER, OTHER = "phone:+12025550100", "phone:+12025550143"


def _inc(t, read=None, status=None, thread="one"):
    return {"instant": t, "direction": "incoming", "thread": thread, "status": status,
            "parties": [(OTHER, "sender", False, "Synthetic Sender", "+12025550143"),
                        (OWNER, "recipient", True, None, "+12025550100", None, read)]}


def _out(t, thread="one"):
    return {"instant": t, "direction": "outgoing", "thread": thread,
            "parties": [(OWNER, "sender", True, None, "+12025550100"),
                        (OTHER, "recipient", False, "Synthetic Sender", "+12025550143")]}


@pytest.fixture(scope="module")
def world():
    from services.phone_analysis import approaches, framework as F
    approaches.install()
    t = at(2023, 5, 1, 10)
    lat, lon = 38.9, -77.03
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            # C1: one reply in 20 minutes after a read at 10:05 (thread one); a message read and never answered
            # (thread two, nothing after it within 48 hours); one message still unread (thread three)
            x, _ = phone(c, case, label="C1", events=[
                _inc(t, read=t + timedelta(minutes=5)), _out(t + timedelta(minutes=20)),
                _inc(t + timedelta(days=1), read=t + timedelta(days=1, minutes=1), thread="two"),
                _inc(t + timedelta(days=5), status="Unread", thread="three")])
            y, _ = phone(c, case, label="C2", owner="phone:+12025550111", events=[])
            # 10 quarter hours together (30 m apart, 20 m radii), then one apart (2 km) in which C1 was used
            for i in range(10):
                _place(c, case, x, 100 + i, t + timedelta(hours=i), lat, lon)
                _place(c, case, y, 100 + i, t + timedelta(hours=i, minutes=2), lat + 30 / 111_320, lon)
            _place(c, case, x, 200, t + timedelta(days=2), lat, lon)
            _place(c, case, y, 200, t + timedelta(days=2), lat + 2000 / 111_320, lon)
            _event(c, case, x, 300, t + timedelta(days=2, minutes=5))
            runs = [F.request_run(c, case, a, None, "synthetic@example.org")[0] for a in ("awareness", "device_users")]
        for r in runs:
            assert F.execute(engine, uuid.UUID(r["id"]))["status"] == "completed"
        yield {"engine": engine, "case": case}


def _tools(w, significant):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=w["engine"]) as s:
            yield s
    ctx = AgentToolContext(case_id=str(w["case"]), ledger_session_factory=session,
                           allowed_entity_keys=set() if significant else None)
    return {t.name: t for t in make_agent_tools(ctx)}


R = "get_analysis_results"
AW, DU = {"approach": "awareness"}, {"approach": "device_users"}


def _m(d, i=0):
    return d["items"][i]["measures"]


# (id, question, tool, args, known total, extra check)
QUESTIONS = [
    ("G01", "How quickly did the owner of C1 reply to Synthetic Sender?", R, dict(AW, kind="reply_latency"), 1,
     lambda d: _m(d)["latency"]["median_s"] == 1200.0 and _m(d)["read_to_reply"]["median_s"] == 900.0
     and d["items"][0]["strength"] == "weak" and d["by_strength"] == {"weak": 1}),
    ("G02", "Which messages did the owner read and not answer?", R, dict(AW, kind="read_without_reply"), 1,
     lambda d: _m(d)["without_reply"] == 1 and _m(d)["window_hours"] == 48),
    ("G03", "Which messages are still unread on the phones?", R, dict(AW, kind="unread"), 1,
     lambda d: _m(d)["unread"] == 1),
    ("G04", "When did the owner read messages?", R, dict(AW, kind="read_events"), 2,
     lambda d: sum(_m(d, i)["incoming_owner_read"] for i in range(2)) == 2),
    ("G05", "List every weak read or reply result", R, dict(AW, strength="weak"), 5,
     lambda d: d["by_strength"] == {"weak": 5}),
    ("G06", "How many phones have read times, and what do the results rest on?", R, dict(AW, kind="reply_latency"), 1,
     lambda d: any("Owner read or play times on 1 of 2 phones" in n for n in d["coverage_notes"])
     and any("Rule of thumb" in n for n in d["coverage_notes"])),
    ("G07", "Were C1 and C2 together?", R, dict(DU, kind="co_location"), 1,
     lambda d: _m(d)["together"] == 10 and _m(d)["apart"] == 1 and _m(d)["C"] == round(10 / 11, 4)
     and d["items"][0]["strength"] == "weak"),
    ("G08", "Was either phone used while they were apart?", R, dict(DU, kind="use_while_apart"), 1,
     lambda d: _m(d)["used_phone"] == "C1" and len(_m(d)["bins"]) == 1),
    ("G09", "How many quarter hours were both phones placed, against the plan's figure?", R,
     dict(DU, kind="co_location"), 1,
     lambda d: any("the most here is 11" in n for n in d["coverage_notes"])),
]


def _measure(w, tools, q):
    qid, _, tool, args, total, check = q
    out = tools[tool].invoke(dict(args))
    data = out.get("data") or {}
    got = data.get("total_matching")
    try:
        ok_check = check is None or (got == total and bool(check(data)))
    except Exception:  # noqa: BLE001 - a missing key on old code is a failed check, measured
        ok_check = False
    return out, got, ok_check


def test_the_awareness_set_has_9_questions():
    assert len(QUESTIONS) == 9 and len({q[0] for q in QUESTIONS}) == 9


def test_all_data_every_question_states_the_known_answer(world):
    tools = _tools(world, significant=False)
    table, wrong = [], []
    for q in QUESTIONS:
        out, got, ok_check = _measure(world, tools, q)
        ok = got == q[4] and ok_check
        table.append({"id": q[0], "setting": "all data", "question": q[1], "total_ok": got == q[4],
                      "check_ok": ok_check, "known_total": q[4], "stated_total": got, "ok": ok})
        if not ok:
            wrong.append((q[0], q[4], got, ok_check, str(out.get("summary"))[:300]))
    _record(table)
    assert not wrong, wrong


def test_significant_every_question_is_refused_with_the_boundary_and_no_records(world):
    tools = _tools(world, significant=True)
    table, wrong = [], []
    for q in QUESTIONS:
        out = tools[q[2]].invoke(dict(q[3]))
        data = out.get("data") or {}
        refused = out.get("status") == "error" and "Significant layer" in str(out.get("summary"))
        table.append({"id": q[0], "setting": "significant", "question": q[1], "refused": refused,
                      "no_records": not data.get("items"), "ok": refused and not data.get("items")})
        if not (refused and not data.get("items")):
            wrong.append((q[0], out.get("status"), out.get("summary")))
    _record(table)
    assert not wrong, wrong


def _record(rows):
    path = os.environ.get("LOUPE_AGENT_EVAL_OUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
