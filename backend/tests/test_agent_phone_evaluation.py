"""The agent evaluation set (07 section 7.1): 30 or more questions with known answers on synthetic phones, measured
through the agent's own tools (the StructuredTool layer the model calls, with the run's case) under both case layers.

All data: every question's stated total equals its known answer and the records it cites (rec:// links) are exactly
the known records. Significant: every phone question is refused with the Significant boundary sentence and returns no
records (the phones are not on the Significant layer; never a partial answer). A question about a phone, person or
record that exists only in another case answers "Not in this case".

The known answers are written by hand from the events below, not computed by the code under test. Set
LOUPE_AGENT_EVAL_OUT to a file path to write the measured table (one line per question and setting) as JSON.
Synthetic data only; needs the PostgreSQL template.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager

import pytest
from sqlalchemy.orm import Session

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, OWNER2 = "phone:+12025550100", "phone:+12025550177"
ANA, BEN, CAL, ZED = "phone:+12025550143", "phone:+12025550188", "phone:+12025550166", "phone:+12025550199"


def _msg(instant, sender, recips, body, thread, owner=OWNER, **kw):
    parties = [(sender, "sender", sender == owner, None, None)] + [(r, "recipient", r == owner, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties, thread=thread,
                direction="outgoing" if sender == owner else "incoming", **kw)


def _call(instant, caller, callee, owner=OWNER):
    return dict(kind="call", instant=instant, body=None, thread=None, call_duration_s=65,
                direction="outgoing" if caller == owner else "incoming",
                parties=[(caller, "caller", caller == owner, None, None), (callee, "callee", callee == owner, None, None)])


# Phone C3 (owner OWNER). Index -> event; e6 is a second copy of e5 (counted once, both records cited as one row).
C3 = [
    _msg(at(2023, 3, 1, 9), ANA, [OWNER], "meet at the dock", "t1"),                     # e0
    _msg(at(2023, 3, 1, 10), OWNER, [ANA], "on my way", "t1"),                           # e1
    _call(at(2023, 3, 2, 9), OWNER, ANA),                                                 # e2
    _msg(at(2023, 3, 3, 9), BEN, [OWNER], "invoice attached", "t2"),                     # e3
    _msg(at(2023, 3, 3, 10), OWNER, [BEN], "paid the invoice", "t2", level="applied_unconfirmed"),  # e4
    _msg(at(2023, 3, 4, 9), ANA, [OWNER], "dock again tomorrow", "t1", dup="g1", app="Native Messages"),  # e5
    _msg(at(2023, 3, 4, 9), ANA, [OWNER], "dock again tomorrow", "t1", dup="g1", app="IMS Service"),  # e6 copy
    _call(at(2023, 3, 5, 9), BEN, OWNER),                                                 # e7
    _msg(at(2023, 3, 6, 9), CAL, [OWNER, ANA], "group hello", "grp"),                    # e8 group
    _msg(at(2023, 3, 7, 9), ANA, [OWNER], "last word", "t1"),                            # e9
]
# Phone C4 (owner OWNER2), same case
C4 = [
    _msg(at(2023, 3, 2, 12), ANA, [OWNER2], "hi from the second phone", "u1", owner=OWNER2),  # f0
    _msg(at(2023, 3, 8, 12), OWNER2, [ANA], "bye for now", "u1", owner=OWNER2),               # f1
]


@pytest.fixture(scope="module")
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            _, e = phone(c, case, label="C3", contacts={ANA: "Maria Lopez", BEN: "Ben Synthetic", CAL: "Cal Group"},
                         events=C3, threads={"grp": {"chat_type": "Group", "title": "Synthetic group",
                                                     "members": [OWNER, ANA, CAL]}})
            _, f = phone(c, case, label="C4", owner=OWNER2, contacts={ANA: "Maria L"}, events=C4)
            _, z = phone(c, other, label="C9", owner="phone:+12025550111", contacts={ZED: "Zed Elsewhere"},
                         events=[_msg(at(2023, 3, 14, 9), ZED, ["phone:+12025550111"], "other case only", "z1",
                                      owner="phone:+12025550111")])
        ids = {"e%d" % i: x["record_uid"] for i, x in enumerate(e)}
        ids.update({"f%d" % i: x["record_uid"] for i, x in enumerate(f)})
        ids["z0"] = z[0]["record_uid"]
        yield {"engine": engine, "case": case, "ids": ids}


def _tools(w, significant):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=w["engine"]) as s:
            yield s
    ctx = AgentToolContext(case_id=str(w["case"]), ledger_session_factory=session,
                           allowed_entity_keys=set() if significant else None)
    return {t.name: t for t in make_agent_tools(ctx)}


# (id, question, tool, args, known total, known cited events or None when the tool cites no rows, extra check)
M = "phone_messages"
QUESTIONS = [
    ("Q01", "How many messages and calls involve Maria Lopez?", M, {"people": ["Maria Lopez"], "mode": "any"},
     8, ["e0", "e1", "e2", "e5", "e8", "e9", "f0", "f1"]),   # involving: the group message she is in counts
    ("Q02", "Messages and calls with Maria Lopez on C3 only?", M, {"people": ["Maria Lopez"], "mode": "any",
                                                                  "phones": ["C3"]}, 6, ["e0", "e1", "e2", "e5", "e8", "e9"]),
    ("Q03", "Messages and calls with Maria Lopez on C4 only?", M, {"people": ["Maria Lopez"], "mode": "any",
                                                                  "phones": ["C4"]}, 2, ["f0", "f1"]),
    ("Q04", "Calls with Maria Lopez?", M, {"people": ["Maria Lopez"], "mode": "any", "kinds": ["call"]}, 1, ["e2"]),
    ("Q05", "Messages (not calls) with Maria Lopez?", M, {"people": ["Maria Lopez"], "mode": "any",
                                                          "kinds": ["message"]}, 7, ["e0", "e1", "e5", "e8", "e9", "f0", "f1"]),
    ("Q06", "Messages involving Maria Lopez with include_groups (no change for involving)?", M, {"people": ["Maria Lopez"], "mode": "any",
                                                                    "include_groups": True},
     8, ["e0", "e1", "e2", "e5", "e8", "e9", "f0", "f1"]),
    ("Q07", "What did Maria Lopez and the phone say on 1 March 2023?", M, {
        "people": ["Maria Lopez"], "mode": "any", "start": "2023-03-01", "end": "2023-03-01"}, 2, ["e0", "e1"]),
    ("Q08", "Activity with Maria Lopez from 2 to 4 March 2023?", M, {
        "people": ["Maria Lopez"], "mode": "any", "start": "2023-03-02", "end": "2023-03-04"}, 3, ["e2", "e5", "f0"]),
    ("Q09", "Anything with Maria Lopez after 7 March 2023?", M, {
        "people": ["Maria Lopez"], "mode": "any", "start": "2023-03-08"}, 1, ["f1"]),
    ("Q10", "Anything with Maria Lopez before 2 March 2023?", M, {
        "people": ["Maria Lopez"], "mode": "any", "end": "2023-03-01"}, 2, ["e0", "e1"]),
    ("Q11", "How many messages and calls involve Ben Synthetic?", M, {"people": ["Ben Synthetic"], "mode": "any"},
     3, ["e3", "e4", "e7"]),
    ("Q12", "Messages with Ben Synthetic mentioning the invoice?", M, {"people": ["Ben Synthetic"], "mode": "any",
                                                                       "search": "invoice"}, 2, ["e3", "e4"]),
    ("Q13", "Which messages mention the dock?", M, {"search": "dock"}, 2, ["e0", "e5"]),
    ("Q14", "Which messages say 'last word'?", M, {"search": "last word"}, 1, ["e9"]),
    ("Q15", "Which messages mention a submarine?", M, {"search": "submarine"}, 0, []),
    ("Q16", "Everything on C4?", M, {"phones": ["C4"]}, 2, ["f0", "f1"]),
    ("Q17", "Everything on C3?", M, {"phones": ["C3"]}, 9, ["e0", "e1", "e2", "e3", "e4", "e5", "e7", "e8", "e9"]),
    ("Q18", "Everything on every phone?", M, {}, 11,
     ["e0", "e1", "e2", "e3", "e4", "e5", "e7", "e8", "e9", "f0", "f1"]),
    ("Q19", "Every call on the phones?", M, {"kinds": ["call"]}, 2, ["e2", "e7"]),
    ("Q20", "Everything on 3 March 2023?", M, {"start": "2023-03-03", "end": "2023-03-03"}, 2, ["e3", "e4"]),
    ("Q21", "Messages between Maria Lopez and Ben Synthetic?", M, {"people": ["Maria Lopez", "Ben Synthetic"],
                                                                   "mode": "between"}, 0, []),
    ("Q22", "First 3 of everything, oldest first?", M, {"limit": 3}, 11, ["e0", "e1", "e2"]),
    ("Q23", "Everything from the fourth onwards (offset 3, 3 rows)?", M, {"offset": 3, "limit": 3}, 11,
     ["f0", "e3", "e4"]),
    ("Q24", "Messages involving Cal Group?", M, {"people": ["Cal Group"], "mode": "any"}, 1, ["e8"]),
    ("Q25", "Messages between Cal Group and Maria Lopez, direct only?", M, {
        "people": ["Cal Group", "Maria Lopez"], "mode": "between"}, 0, []),
    ("Q25b", "Messages between Cal Group and Maria Lopez, group chats included?", M, {
        "people": ["Cal Group", "Maria Lopez"], "mode": "between", "include_groups": True}, 1, ["e8"]),
    ("Q26", "Messages with +1 202 555 0143 (by number)?", M, {"people": ["+1 202 555 0143"], "mode": "any"},
     8, ["e0", "e1", "e2", "e5", "e8", "e9", "f0", "f1"]),
    ("Q27", "Contact summary for Maria Lopez: how many in total (groups included)?", "phone_contact_summary",
     {"person": "Maria Lopez"}, 8, None),
    ("Q28", "Contact summary for Ben Synthetic?", "phone_contact_summary", {"person": "Ben Synthetic"}, 3, None),
    ("Q29", "Who is +1 202 555 0188?", "phone_find_people", {"query": "+1 202 555 0188"}, 1, None),
    ("Q30", "Read record e9 in full", "phone_record", {"record": "@e9"}, 1, ["e9"]),
    ("Q31", "Which phones are in this case?", "phone_coverage", {}, 2, None),
    # not in this case: a phone, a person and a record that exist only in another case
    ("Q32", "Everything on C9?", M, {"phones": ["C9"]}, "not_in_case", []),
    ("Q33", "Messages with Zed Elsewhere?", M, {"people": ["Zed Elsewhere"], "mode": "any"}, "not_in_case", []),
    ("Q34", "Read record z0 (another case's)", "phone_record", {"record": "@z0"}, "not_in_case", []),
    ("Q35", "Who is +1 202 555 0199 (only in another case)?", "phone_find_people", {"query": "+1 202 555 0199"},
     "not_in_case", []),
]


def _args(w, args):
    return {k: (w["ids"][v[1:]] if isinstance(v, str) and v.startswith("@") else v) for k, v in args.items()}


def _cited(w, data) -> list[str]:
    """Cited records as event names (a copy cites its first record; e6 reads as e5)."""
    names = {v: k for k, v in w["ids"].items()}
    names[w["ids"]["e6"]] = "e5"
    out = []
    for item in data.get("items") or ([data["record"]] if isinstance(data.get("record"), dict) else []):
        rec = str(item.get("rec") or item.get("record_uid") or "")
        uid = rec[len("rec://"):] if rec.startswith("rec://") else rec
        out.append(names.get(uid, uid))
    return out


def _measure(w, tools, q):
    qid, _, tool, args, total, cited = q
    out = tools[tool].invoke(_args(w, args))
    data = out.get("data") or {}
    if total == "not_in_case":
        got_total = "not_in_case" if data.get("not_in_case") or str(out.get("summary", "")).startswith(
            "Not in this case") else data.get("total_matching")
    else:
        got_total = data.get("total_matching")
    got_cited = _cited(w, data)
    return out, got_total, got_cited


def test_the_set_has_30_or_more_questions_each_with_a_known_answer():
    assert len(QUESTIONS) >= 30 and len({q[0] for q in QUESTIONS}) == len(QUESTIONS)


def test_all_data_every_question_states_the_known_total_and_cites_exactly_the_known_records(world):
    tools = _tools(world, significant=False)
    table, wrong = [], []
    for q in QUESTIONS:
        out, got_total, got_cited = _measure(world, tools, q)
        ok_total = got_total == q[4]
        ok_cited = q[5] is None or sorted(got_cited) == sorted(q[5])
        if q[0] in ("Q22", "Q23"):  # paging: the order is part of the answer (oldest first)
            ok_cited = got_cited == q[5]
        table.append({"id": q[0], "setting": "all data", "question": q[1], "total_ok": ok_total,
                      "cited_ok": ok_cited, "known_total": q[4], "stated_total": got_total})
        if not (ok_total and ok_cited):
            wrong.append((q[0], q[4], got_total, q[5], got_cited, out.get("summary")))
    _record(table)
    assert not wrong, wrong


def test_significant_every_phone_question_is_refused_with_the_boundary_and_no_records(world):
    tools = _tools(world, significant=True)
    table, wrong = [], []
    for q in QUESTIONS:
        out = tools[q[2]].invoke(_args(world, q[3]))
        data = out.get("data") or {}
        refused = out.get("status") == "error" and "Significant layer" in str(out.get("summary"))
        no_records = not data.get("items") and not data.get("record")
        table.append({"id": q[0], "setting": "significant", "question": q[1], "refused": refused,
                      "no_records": no_records})
        if not (refused and no_records):
            wrong.append((q[0], out.get("status"), out.get("summary")))
    _record(table)
    assert not wrong, wrong


def _record(rows):
    path = os.environ.get("LOUPE_AGENT_EVAL_OUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
