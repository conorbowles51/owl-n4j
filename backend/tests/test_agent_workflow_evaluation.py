"""The agent evaluation set, workflow questions (agent-workflows C): 3 questions per scenario (30), each asked of a
tool its workflow lists, or of the workflow's readiness on the case, with known answers written by hand from the
synthetic world of the cross set (``tests.test_agent_cross_evaluation``: two handsets of Sam, three more people, a
ledger of five payments from Sam's account ending 1234, one of them p3).

The world, written down here so the known answers can be checked by eye: ledger rows paid USD 500.00 to Ana on 14
March (p2, CAR PURCHASE), USD 70.00 to Ana on 17 March (p2), USD 9.00 to Ana on 16 March (p3), USD 30.00 to Ana on 30
April (p2), USD 25.00 to Ben on 17 March (p2); one statement period, March 2023. Phone C1: e0 Sam to Ana 14 March
09:00 "sending the money for the car today", e1 Ana to Sam 10:00, e2 Ana to Sam 20 March, e3 Ben to Sam 14 March
11:00 "lunch", e4 call Sam to Ben 17 March. Phone C2: bank alerts (USD 500.00 on 14 March 10:30, USD 99.00 on 10
April), a one-time code, the Two Dollar app. No documents other than the statement, no timeline entries, no
phone owner linked to a dossier on People.

All data: every question's stated total equals its known answer, the records cited are exactly the known ones, and
the extra check holds. Significant: every tool question is refused with the boundary and returns no records. Set
LOUPE_AGENT_EVAL_OUT to append the measured table. Invented data only; needs the PostgreSQL template.
"""
from __future__ import annotations

import json
import uuid

from tests.phone_pg import needs_template
from tests.test_agent_cross_evaluation import _args, _cited, _record, _tools, world  # noqa: F401
from services.agent import workflows as W

pytestmark = needs_template

R = "readiness"
SA = {"person_a": "Sam Synthetic", "person_b": "Ana Synthetic"}
NO_DOCS = "the case holds no evidence documents other than statements and phone files"
APRIL = {"start_date": "2023-04-01", "end_date": "2023-04-30"}


def _has(name):
    return lambda d: d["_ids"][name] in json.dumps(d, default=str)


# (id, workflow, question, tool or R, args, known total ("refused" for a refusal; for R the known reasons), known
# cited names or None, extra check)
QUESTIONS = [
    # 1 Last proof of life
    ("WF01", "last-proof-of-life", "What is the last record on Sam's phone on 20 March, and was Sam acting?",
     "get_day_activity", {"person": "Sam Synthetic", "day": "2023-03-20", "zone": "UTC", "lanes": ["communications"]},
     1, ["e2"], lambda d: d["items"][0]["direction"] == "incoming"),
    ("WF02", "last-proof-of-life", "Which card payment has a phone alert that gives its time?",
     "get_money_signal_matches", {}, 1, None,
     lambda d: d["items"][0]["ledger_rows"][0]["txn"].endswith(d["_ids"]["t_paid"])),
    ("WF03", "last-proof-of-life", "Can the last-proof-of-life workflow run on this case?", R, {}, [], None, None),
    # 2 Hidden assets
    ("WF04", "hidden-assets", "Which accounts does the phone show that the financial records do not hold?",
     "get_money_signal_leads", {}, 2, None,
     lambda d: ("Two Dollar Exchange", "missing_account") in [(i["institution"], i["ledger"]) for i in d["items"]]),
    ("WF05", "hidden-assets", "Which accounts and periods do the financial records hold?",
     "get_financial_coverage", {}, 1, None,
     lambda d: d["items"][0]["account_number"].endswith("1234") and d["items"][0]["period"]["start"] == "2023-03-01"
     and d["items"][0]["period"]["end"] == "2023-03-31"),
    ("WF06", "hidden-assets", "Verified spending by month?", "analyze_financial_transactions",
     {"group_by": "month", "population": "verified"}, 2, None,
     lambda d: sorted(int(i["debits_minor"]) for i in d["items"]) == [30_00, 595_00]),
    # 3 Carer abuse
    ("WF07", "carer-abuse", "Money from Sam to Ana in April 2023?", "get_contact_and_money_between",
     dict(SA, start="2023-04-01", end="2023-04-30"), 1, ["t_late"], None),
    ("WF08", "carer-abuse", "Who had the means to operate the account ending 1234 in March 2023: Sam?",
     "draft_control_claim", {"person": "Sam Synthetic", "account": "1234", "start": "2023-03-01", "end": "2023-03-31"},
     4, None, lambda d: d["established"] is True),
    ("WF09", "carer-abuse", "What was said around the USD 500.00 transfer?", "get_payment_conversation",
     {"payment": "@t_paid"}, 2, ["e0", "e1"], None),
    # 4 Procurement kickbacks
    ("WF10", "procurement-kickbacks", "Can the procurement workflow run on this case?", R, {}, [NO_DOCS], None, None),
    ("WF11", "procurement-kickbacks", "Were Sam's and Ana's phones together in March 2023?", "get_together_apart",
     dict(SA, start="2023-03-01", end="2023-03-31"), "refused", [],
     lambda d: "No phone in this case is linked to this person" in d["_summary"]),
    ("WF12", "procurement-kickbacks", "Was the USD 70.00 leg to Ana discussed?", "get_payment_conversation",
     {"payment": "@t_quiet"}, 0, [], lambda d: d["outcome"] == "no_conversation_in_window"),
    # 5 Expense fraud
    ("WF13", "expense-fraud", "Which card line matches the car purchase claim?", "get_financial_transactions",
     {"search": "CAR"}, 1, None, _has("t_paid")),
    ("WF14", "expense-fraud", "What does Sam's day of 14 March show in money?", "get_day_activity",
     {"person": "Sam Synthetic", "day": "2023-03-14", "zone": "UTC", "lanes": ["money"]}, 1, ["t_paid"], None),
    ("WF15", "expense-fraud", "Can the expense workflow run on this case?", R, {}, [NO_DOCS], None, None),
    # 6 Insider trading
    ("WF16", "insider-trading", "Can the insider-trading workflow run on this case?", R, {},
     [W.get("insider-trading").not_modelled], None, None),
    ("WF17", "insider-trading", "Which calls did Sam make on 17 March?", "get_day_activity",
     {"person": "Sam Synthetic", "day": "2023-03-17", "zone": "UTC", "lanes": ["communications"]}, 1, ["e4"],
     lambda d: d["items"][0]["kind"] == "call"),
    ("WF18", "insider-trading", "The messages a week either side of the USD 500.00 payment?",
     "get_payment_conversation", {"payment": "@t_paid", "days": 7}, 3, ["e0", "e1", "e2"], None),
    # 7 Payment-scam victim
    ("WF19", "payment-scam-victim", "Every outgoing payment from Sam's account?", "get_financial_transactions",
     {"direction": "debit"}, 5, None, None),
    ("WF20", "payment-scam-victim", "Record what Sam was told before the USD 500.00 payment",
     "draft_payment_purpose", {"payment": "@t_paid", "outcome": "consistent", "quoted": ["@e0"], "purpose": "the car"},
     1, None, lambda d: d["status"] == "model drafted, not confirmed"),
    ("WF21", "payment-scam-victim", "Record a pairing quoting a message from outside the window",
     "draft_payment_purpose", {"payment": "@t_paid", "outcome": "consistent", "quoted": ["@e2"], "purpose": "x"},
     "refused", [], None),
    # 8 Drug proceeds
    ("WF22", "drug-proceeds", "Who used which phone over which periods?", "get_analysis_results",
     {"approach": "device_users"}, 0, [], lambda d: "has not been run in this case" in d["_summary"]),
    ("WF23", "drug-proceeds", "Verified money out in April 2023?", "analyze_financial_transactions",
     dict(APRIL, population="verified"), 1, None, lambda d: d["items"][0]["debits_minor"] == "3000"),
    ("WF24", "drug-proceeds", "Can the proceeds workflow run on this case?", R, {}, [], None, None),
    # 9 Staged accident
    ("WF25", "staged-accident", "Can the staged-accident workflow run on this case?", R, {}, [], None, None),
    ("WF26", "staged-accident", "Did Sam and Ben talk, and did money move?", "get_contact_and_money_between",
     {"person_a": "Sam Synthetic", "person_b": "Ben Synthetic"}, 1, ["t_ben"],
     lambda d: d["communication"]["calls_ab"] + d["communication"]["calls_ba"] == 1),
    ("WF27", "staged-accident", "Did money move between Ana and Ben?", "get_contact_and_money_between",
     {"person_a": "Ana Synthetic", "person_b": "Ben Synthetic"}, 0, [], None),
    # 10 Defence review
    ("WF28", "defence-review", "What notes, findings and theories does the case hold?", "get_casework", {}, 0, [],
     None),
    ("WF29", "defence-review", "Check a claim that is not in this case", "evaluate_statement",
     {"claim_id": "00000000-0000-0000-0000-000000000000"}, 0, [],
     lambda d: d["_summary"].startswith("Not in this case.")),
    ("WF30", "defence-review", "Does a statement cover April 2023, where a payment sits?", "get_financial_coverage",
     {"start_date": "2023-04-01", "end_date": "2023-04-30"}, 0, [],
     lambda d: d["coverage"]["matching_transactions"] == 1 and d["coverage"]["registered_statement_periods"] == 0),
]


def _measure(w, tools, counts, q):
    qid, wid, _, tool, args, total, cited, check = q
    wf = W.get(wid)
    if tool == R:
        got = W.assess(wf, counts, tools.keys())["reasons"]
        return {"summary": got}, got, True, True
    out = tools[tool].invoke(_args(w, args))
    data = dict(out.get("data") or {}, _ids=w["ids"], _summary=str(out.get("summary")))
    got = "refused" if out.get("status") == "error" else data.get("total_matching")
    ok_cited = cited is None or sorted(_cited(w, data)) == sorted(cited)
    ok_check = check is None or (got == total and bool(check(data)))
    return out, got, ok_cited, ok_check


def test_three_questions_per_scenario_each_on_a_tool_its_workflow_lists():
    assert len(QUESTIONS) == 30 and len({q[0] for q in QUESTIONS}) == 30
    per = {}
    for q in QUESTIONS:
        per[q[1]] = per.get(q[1], 0) + 1
        assert q[3] == R or q[3] in W.get(q[1]).tools, q[0]
    assert per == {w.id: 3 for w in W.WORKFLOWS if not w.extra}


def test_all_data_every_workflow_question_states_the_known_answer(world):
    from sqlalchemy.orm import Session
    with Session(bind=world["engine"]) as s:
        counts = W.case_counts(s.connection(), world["case"])
    assert counts == {"ledger": 5, "financial_sources": 1, "phones": 2, "documents": 0, "dossiers": 4, "timeline": 0}
    tools = _tools(world, significant=False)
    table, wrong = [], []
    for q in QUESTIONS:
        out, got, ok_cited, ok_check = _measure(world, tools, counts, q)
        ok = got == q[5] and ok_cited and ok_check
        table.append({"id": q[0], "workflow": q[1], "setting": "all data", "question": q[2], "tool": q[3],
                      "total_ok": got == q[5], "cited_ok": ok_cited, "check_ok": ok_check,
                      "known": q[5], "stated": got})
        if not ok:
            wrong.append((q[0], q[5], got, ok_cited, ok_check, str(out.get("summary"))[:300]))
    _record(table)
    assert not wrong, wrong


def test_significant_every_workflow_tool_question_is_refused_with_the_boundary(world):
    tools = _tools(world, significant=True)
    table, wrong = [], []
    for q in QUESTIONS:
        if q[3] == R:
            continue
        out = tools[q[3]].invoke(_args(world, q[4]))
        data = out.get("data") or {}
        refused = out.get("status") == "error" and "Significant layer" in str(out.get("summary"))
        table.append({"id": q[0], "workflow": q[1], "setting": "significant", "refused": refused,
                      "no_records": not data.get("items")})
        if not (refused and not data.get("items")):
            wrong.append((q[0], out.get("status"), out.get("summary")))
    _record(table)
    assert not wrong, wrong


def test_unknown_uuid_is_not_a_known_record():
    assert uuid.UUID(QUESTIONS[28][4]["claim_id"]).int == 0


def test_messages_across_phones_is_readable_by_the_agent(world):
    """Scenario 9 lists approach 2 (messages across phones). The agent tool names it (it refused it before)."""
    out = _tools(world, significant=False)["get_analysis_results"].invoke({"approach": "message_reconciliation"})
    assert out.get("status") != "error", out.get("summary")
    assert out["data"]["total_matching"] == 0 and "message_reconciliation has not been run" in str(out["summary"])
