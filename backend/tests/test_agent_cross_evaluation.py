"""The agent evaluation set, cross questions (agent-phones E): 20 questions joining phones and money, with known
answers written by hand from the events and rows below, measured through the agent's own tools (the StructuredTool
layer the model calls, with the run's case) under both case layers.

All data: every question's stated total equals its known answer and the records it cites (rec:// for phone records,
txn:// for ledger rows) are exactly the known ones. Significant: every question is refused with the Significant
boundary sentence and returns no records. Set LOUPE_AGENT_EVAL_OUT to append the measured table as JSON lines.
Invented data only; needs the PostgreSQL template.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, ensure_identity, phone
from tests.test_phone_analysis_money_signals import Ledger, Phone, _run

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
LINK = '{"investigation_labels": {"counterparty_link": {"kind": "party", "id": "%s", "label": "%s"}}}'


def _msg(instant, sender, recips, body, thread):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties, thread=thread,
                direction="outgoing" if sender == OWNER else "incoming")


# Phone C1 (owner Sam): index -> event
C1 = [
    _msg(at(2023, 3, 14, 9), OWNER, [ANA], "sending the money for the car today", "t1"),   # e0
    _msg(at(2023, 3, 14, 10), ANA, [OWNER], "got it, thanks for the car", "t1"),           # e1
    _msg(at(2023, 3, 20, 10), ANA, [OWNER], "see you next week", "t1"),                    # e2
    _msg(at(2023, 3, 14, 11), BEN, [OWNER], "unrelated chat about lunch", "t2"),          # e3
    dict(kind="call", instant=at(2023, 3, 17, 9), body=None, thread=None, call_duration_s=40,  # e4
         direction="outgoing", parties=[(OWNER, "caller", True, None, None), (BEN, "callee", False, None, None)]),
]
# Phone C2 (a second handset of Sam's, read by the real interpretation): bank notifications and an app
ALERT_AT = datetime(2023, 3, 14, 10, 30, tzinfo=timezone.utc)
APRIL_AT = datetime(2023, 4, 10, 12, 0, tzinfo=timezone.utc)
CODE_AT = datetime(2023, 3, 14, 10, 28, tzinfo=timezone.utc)
# Ledger, Sam's Synthetic Bank account ending 1234 (statement period March 2023):
#   paid  USD 500.00 to Ana 2023-03-14 p2 | quiet USD 70.00 to Ana 2023-03-17 p2 | p3 USD 9.00 to Ana 2023-03-16 p3
#   late  USD 30.00 to Ana 2023-04-30 p2  | ben   USD 25.00 to Ben 2023-03-17 p2


def _dossier(c, case, name, key, idents):
    did = uuid.uuid4()
    c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, "
                   "status, needs_link_review, graph_entity_deleted, canonical_entity_key, created_at, updated_at) "
                   "VALUES (:d, :c, 'person', :n, '[]', 'unlinked', 'active', false, false, :k, now(), now())"),
              {"d": did, "c": case, "n": name, "k": key})
    for i in idents:
        c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) VALUES "
                       "(:c, :i, :d, :x)"), {"c": case, "i": ensure_identity(c, case, i), "d": did, "x": uuid.uuid4()})
    return str(did)


@pytest.fixture(scope="module")
def world():
    from services.phone import identities as I
    from services.phone import link_edges as LE
    from services.phone_analysis import approaches, framework as F, institutions as INST, money_signals as MS
    from tests.test_phone_analysis_money_signals import BANK, TWO_DOLLARS
    mp = pytest.MonkeyPatch()
    INST.use_entries([BANK, TWO_DOLLARS])
    approaches.install()
    F.register(MS)
    try:
        with fresh_engine() as engine:
            with engine.begin() as c:
                case, other = make_case(c), make_case(c)
                _, ev = phone(c, case, label="C1", contacts={ANA: "Ana Synthetic", BEN: "Ben Synthetic"}, events=C1)
                _dossier(c, case, "Sam Synthetic", "ent-sam", [OWNER])
                _dossier(c, case, "Ana Synthetic", "ent-ana", [ANA])
                _dossier(c, case, "Ben Synthetic", "ent-ben", [BEN])
                _dossier(c, case, "Dee Nophone", "ent-dee", [])
                L = Ledger(c, case)
                acct = L.account("Synthetic Bank", "XXXX-XXXX-1234", statement=False)
                L.period(acct, date(2023, 3, 1), date(2023, 3, 31), 0, 0)
                pa, pb = str(uuid.uuid4()), str(uuid.uuid4())
                rows = {"paid": (500_00, date(2023, 3, 14), pa, "Ana Synthetic", "p2"),
                        "quiet": (70_00, date(2023, 3, 17), pa, "Ana Synthetic", "p2"),
                        "p3": (9_00, date(2023, 3, 16), pa, "Ana Synthetic", "p3"),
                        "late": (30_00, date(2023, 4, 30), pa, "Ana Synthetic", "p2"),
                        "ben": (25_00, date(2023, 3, 17), pb, "Ben Synthetic", "p2")}
                ids = {}
                for k, (amt, day, party, label, klass) in rows.items():
                    t = L.txn(acct, amt, day)
                    c.execute(text("UPDATE financial_transactions SET description = :d, proof_class = :p, metadata = "
                                   "CAST(:m AS jsonb) WHERE id = :i"),
                              {"i": t, "d": "CAR PURCHASE" if k == "paid" else "TRANSFER", "p": klass,
                               "m": LINK % (party, label)})
                    ids[k] = str(t)
                _, z = phone(c, other, label="C9", owner="phone:+12025550111", events=[
                    _msg(at(2023, 3, 14, 9), "phone:+12025550199", ["phone:+12025550111"], "other case only", "z")])
                _dossier(c, other, "Zed Elsewhere", "ent-zed", [])
            p = Phone()
            p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $500.00 on card ending 1234",
                           when=ALERT_AT)
            p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $99.00 on card ending 1234",
                           when=APRIL_AT)
            p.notification("test.synthbank.mobile", "Synthetic Bank: your one-time code is 482913.", when=CODE_AT)
            p.simple("InstalledApplication", Identifier="test.twodollar.app", Name="Two Dollar")
            c2 = str(p.make(engine, case))
            real_owner = I.owner
            mp.setattr(I, "owner", lambda conn, e: {"owner_identity_keys": [OWNER], "owner_basis": "extracted"}
                       if str(e) == c2 else real_owner(conn, e))
            sides = {"ent-sam": {"parties": set(), "accounts": {str(acct)}},
                     "ent-ana": {"parties": {pa}, "accounts": set()}, "ent-ben": {"parties": {pb}, "accounts": set()}}
            mp.setattr(LE, "financial_sides", lambda s, c_, keys: {k: sides.get(k, {"parties": set(),
                                                                                     "accounts": set()})
                                                                   for k in keys if k})
            _run(engine, case, {"phase": "1a"})
            names = {"e%d" % i: x["record_uid"] for i, x in enumerate(ev)}
            names.update({"t_%s" % k: v for k, v in ids.items()})
            yield {"engine": engine, "case": case, "ids": names, "z": z[0]["record_uid"]}
    finally:
        mp.undo()
        INST.use_entries(None)


def _tools(w, significant):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=w["engine"]) as s:
            yield s
    ctx = AgentToolContext(case_id=str(w["case"]), ledger_session_factory=session,
                           allowed_entity_keys=set() if significant else None)
    return {t.name: t for t in make_agent_tools(ctx)}


B, C, D = "get_contact_and_money_between", "get_payment_conversation", "draft_control_claim"
SA = {"person_a": "Sam Synthetic", "person_b": "Ana Synthetic"}
# (id, question, tool, args, known total or "not_in_case"/"refused", known cited (names) or None, extra check)
QUESTIONS = [
    ("X01", "Did Sam and Ana talk, and how much money moved between them?", B, SA, 4,
     ["t_paid", "t_quiet", "t_p3", "t_late"], lambda d: d["money"][0]["paid_ab_minor"] == 600_00
     and d["money"][0]["p3"]["paid_ab_minor"] == 9_00 and d["communication"]["messages_ab"]
     + d["communication"]["messages_ba"] == 3),
    ("X02", "Money between Sam and Ana in March 2023?", B, dict(SA, start="2023-03-01", end="2023-03-31"), 3,
     ["t_paid", "t_quiet", "t_p3"], lambda d: d["money"][0]["paid_ab_minor"] == 570_00),
    ("X03", "Did Sam and Ben talk, and did money move?", B, {"person_a": "Sam Synthetic", "person_b": "Ben Synthetic"},
     1, ["t_ben"], lambda d: d["communication"]["calls_ab"] + d["communication"]["calls_ba"] == 1),
    ("X04", "Money between Ana and Ben?", B, {"person_a": "Ana Synthetic", "person_b": "Ben Synthetic"}, 0, [], None),
    ("X05", "What did Sam and Ana say around the USD 500.00 payment?", C, {"payment": "@t_paid"}, 2, ["e0", "e1"],
     lambda d: d["anchor"]["basis"] == "phone_alert" and d["payment"]["description"] == "CAR PURCHASE"),
    ("X06", "Was the USD 70.00 payment to Ana discussed?", C, {"payment": "@t_quiet"}, 0, [],
     lambda d: d["outcome"] == "no_conversation_in_window" and d["reason_code"] == "no_messages_in_window"),
    ("X07", "Was the April payment to Ana discussed?", C, {"payment": "@t_late"}, 0, [],
     lambda d: d["reason_code"] == "outside_extraction_coverage"),
    ("X08", "The conversation around the USD 500.00 payment, a week either side?", C,
     {"payment": "@t_paid", "days": 7}, 3, ["e0", "e1", "e2"], None),
    ("X09", "Record the reading that the USD 500.00 was for the car", "draft_payment_purpose",
     {"payment": "@t_paid", "outcome": "consistent", "quoted": ["@e0"], "purpose": "the car"}, 1, None,
     lambda d: d["status"] == "model drafted, not confirmed" and d["items"][0]["outcome"] == "consistent"
     and d["items"][0]["quoted"] == ["rec://%s" % d["_ids"]["e0"]]),
    ("X10", "Record a reading quoting a message from outside the window", "draft_payment_purpose",
     {"payment": "@t_paid", "outcome": "consistent", "quoted": ["@e2"], "purpose": "the car"}, "refused", [], None),
    ("X11", "Which phone alerts match ledger rows?", "get_money_signal_matches", {}, 1, None,
     lambda d: d["items"][0]["ledger_rows"][0]["txn"].endswith(d["_ids"]["t_paid"])),
    ("X12", "Which accounts or periods do the phones point to that the ledger lacks?", "get_money_signal_leads", {},
     2, None, lambda d: sorted((i["institution"], i["ledger"]) for i in d["items"]) == [
         ("Synthetic Bank", "missing_period"), ("Two Dollar Exchange", "missing_account")]),
    ("X13", "Which months do the Synthetic Bank alerts fall in that no statement covers?", "get_money_signal_leads",
     {}, 2, None, lambda d: [i["uncovered_months"] for i in d["items"] if i["institution"] == "Synthetic Bank"]
     == [["2023-04"]]),
    ("X14", "Did Sam have the means to operate the account ending 1234 in March 2023?", D,
     {"person": "Sam Synthetic", "account": "1234", "start": "2023-03-01", "end": "2023-03-31"}, 4, None,
     lambda d: d["established"] is True and sorted(s["kind"] for s in d["items"]) == [
         "alert", "code", "owner_identity", "owner_identity"] and "482913" not in json.dumps(d)),
    ("X15", "Did Ana have the means to operate the account ending 1234 in March 2023?", D,
     {"person": "Ana Synthetic", "account": "1234", "start": "2023-03-01", "end": "2023-03-31"}, 0, None,
     lambda d: d["established"] is False),
    ("X16", "Did Sam have the means to operate the account ending 1234 in May 2023?", D,
     {"person": "Sam Synthetic", "account": "1234", "start": "2023-05-01", "end": "2023-05-31"}, 2, None,
     lambda d: d["established"] is False and "nothing ties the account" in d["limitation"]),
    ("X17", "Which messages mention the car?", "search_case", {"query": "car", "group": "messages"}, 2,
     ["e0", "e1"], None),
    ("X18", "Which numbers are Ana's?", "get_person_phones", {"person": "Ana Synthetic"}, 1, None,
     lambda d: d["items"][0]["identity_key"] == ANA and d["items"][0]["messages_and_calls"] == 3),
    ("X19", "What happened on Sam's phones and account on 14 March 2023?", "get_day_activity",
     {"person": "Sam Synthetic", "day": "2023-03-14", "lanes": ["communications", "money"], "zone": "UTC"}, 4,
     ["e0", "e1", "e3", "t_paid"], None),
    ("X20", "Money between Sam and Zed Elsewhere (a person only in another case)?", B,
     {"person_a": "Sam Synthetic", "person_b": "Zed Elsewhere"}, "not_in_case", [], None),
]


def _args(w, args):
    def one(v):
        if isinstance(v, str) and v.startswith("@"):
            return w["ids"][v[1:]]
        if isinstance(v, list):
            return [one(x) for x in v]
        return v
    return {k: one(v) for k, v in args.items()}


def _cited(w, data) -> list[str]:
    names = {v: k for k, v in w["ids"].items()}
    out = []
    for item in data.get("items") or []:
        link = str(item.get("rec") or item.get("txn") or "")
        uid = link.split("://", 1)[-1].split("#")[0] if link else ""
        if uid:
            out.append(names.get(uid, uid))
    return out


def _measure(w, tools, q):
    qid, _, tool, args, total, cited, check = q
    out = tools[tool].invoke(_args(w, args))
    data = dict(out.get("data") or {}, _ids=w["ids"])
    if total == "not_in_case":
        got = "not_in_case" if data.get("not_in_case") else data.get("total_matching")
    elif total == "refused":
        got = "refused" if out.get("status") == "error" else data.get("total_matching")
    else:
        got = data.get("total_matching")
    ok_cited = cited is None or sorted(_cited(w, data)) == sorted(cited)
    ok_check = check is None or (got == total and bool(check(data)))
    return out, got, ok_cited, ok_check


def test_the_cross_set_has_20_questions_each_with_a_known_answer():
    assert len(QUESTIONS) == 20 and len({q[0] for q in QUESTIONS}) == 20


def test_all_data_every_cross_question_states_the_known_answer_and_cites_exactly_the_known_records(world):
    tools = _tools(world, significant=False)
    table, wrong = [], []
    for q in QUESTIONS:
        out, got, ok_cited, ok_check = _measure(world, tools, q)
        ok = got == q[4] and ok_cited and ok_check
        table.append({"id": q[0], "setting": "all data", "question": q[1], "total_ok": got == q[4],
                      "cited_ok": ok_cited, "check_ok": ok_check, "known_total": q[4], "stated_total": got})
        if not ok:
            wrong.append((q[0], q[4], got, ok_cited, ok_check, str(out.get("summary"))[:300]))
    _record(table)
    assert not wrong, wrong


def test_significant_every_cross_question_is_refused_with_the_boundary_and_no_records(world):
    tools = _tools(world, significant=True)
    table, wrong = [], []
    for q in QUESTIONS:
        out = tools[q[2]].invoke(_args(world, q[3]))
        data = out.get("data") or {}
        refused = out.get("status") == "error" and "Significant layer" in str(out.get("summary"))
        table.append({"id": q[0], "setting": "significant", "question": q[1], "refused": refused,
                      "no_records": not data.get("items")})
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
