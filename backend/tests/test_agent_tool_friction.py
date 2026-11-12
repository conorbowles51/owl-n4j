"""Tool friction the Claude stand-ins met on the demo case (coordinator m111200450211521, 12 Nov): each test fails
on the code before the fix."""
from __future__ import annotations

from datetime import date

import pytest

from services.agent.tools import AgentToolContext, make_agent_tools


def _tools():
    return {t.name: t for t in make_agent_tools(AgentToolContext(case_id="00000000-0000-0000-0000-0000000000aa"))}


def test_phone_messages_description_names_only_the_modes_the_schema_takes():
    # (a) "in a window" read as a mode; the schema refused mode "window" with a literal_error.
    tool = _tools()["phone_messages"]
    words = tool.description
    assert "in a window" not in words
    assert "no other mode" in words and "start and end" in words
    modes = tool.args_schema.model_json_schema()["properties"]["mode"]
    assert set(modes.get("enum") or [x["const"] for x in modes.get("anyOf", []) if "const" in x]) == {"between", "any"}


def test_ledger_amount_range_says_it_needs_a_currency():
    # (b) "Select a currency for an amount range" came back only as an error.
    props = _tools()["get_financial_transactions"].args_schema.model_json_schema()["properties"]
    for field in ("minimum_minor", "maximum_minor", "currency"):
        text = str(props[field])
        assert "currency" in text.lower() and ("USD" in text or "Required" in text)


def test_phone_section_names_identity_suggestions():
    # (c) get_identity_suggestions was named only in the financial section.
    from services.agent.graph import _phone_prompt
    prompt = _phone_prompt()
    assert "get_identity_suggestions" in prompt
    assert "is a named person" in prompt


def test_owner_record_naming_a_person_is_found_and_labelled_not_a_link(monkeypatch):
    # (d) get_person_phones said "no phone identity is linked" while phone_coverage named the owner.
    from services.agent import phone_cross_tools as X
    from services.phone import records
    phones = [
        {"label": "Phone 2", "standing": "active", "owner": {
            "identity_key": "phone:+14105550121", "name": "Travis  Kell", "is_owner": True, "phone_label": "Phone 2",
            "identifier": {"kind": "phone", "display": "+1 410-555-0121"}}},
        {"label": "Phone 9", "standing": "superseded", "owner": {
            "identity_key": "phone:+1999", "name": "Travis Kell", "is_owner": True, "phone_label": "Phone 9",
            "identifier": {"kind": "phone", "display": "+1 999"}}},
        {"label": "Phone 3", "standing": "active", "owner": {"identity_key": "phone:+1443", "name": None}},
    ]
    monkeypatch.setattr(records, "phones", lambda conn, case_id: phones)
    found = X.owner_records_naming(None, "case", "travis kell")
    assert [x["phone"] for x in found] == ["Phone 2"]
    assert found[0]["identity_key"] == "phone:+14105550121"
    assert "no person has linked it" in found[0]["basis"]
    words = X._owner_words(found)
    assert "not a person's link" in words and "phone:+14105550121" in words
    assert X.owner_records_naming(None, "case", "Lena Marsh") == []


def test_money_matches_take_filters_and_a_bounded_page():
    # (e) no filter at all; one call returned 254,355 characters.
    from services.agent.phone_cross_tools import MatchesArgs
    a = MatchesArgs(person="Lena Marsh", direction="credit", minimum_minor=50000, maximum_minor=50000,
                    start="2024-03-01", end="2024-06-30", phones=["Phone 6"], limit=40)
    assert a.limit == 25 and a.max_pairings == 5
    assert MatchesArgs().limit == 10


def test_a_received_alert_is_set_beside_the_payers_debit_as_a_suggestion():
    # (e) the pairing rule keeps the phone's direction, so a received alert never met the payer's debit.
    from services.agent.phone_cross_tools import _other_side
    entries = {"kell": [
        {"id": "d1", "amount_minor": 50000, "currency": "USD", "direction": "debit", "date": date(2024, 3, 16),
         "description": "POCKETWIRE TO LENA MARSH", "counterparty": None},
        {"id": "d2", "amount_minor": 50000, "currency": "USD", "direction": "debit", "date": date(2024, 3, 20),
         "description": "too far", "counterparty": None},
        {"id": "c1", "amount_minor": 50000, "currency": "USD", "direction": "credit", "date": date(2024, 3, 16),
         "description": "same way", "counterparty": None}]}
    accounts = {"kell": {"holder": "TRAVIS KELL", "institution": "Kestrel Point Bank"}}
    reading = {"instant": "2024-03-16T14:02:00+00:00", "amount_minor": 50000, "currency": None, "direction": "credit"}
    out = _other_side(entries, accounts, reading)
    assert [x["payment"] for x in out] == ["d1"]
    assert out[0]["account_holder"] == "TRAVIS KELL" and "not a pairing" in out[0]["words"]


@pytest.mark.parametrize("question,dates", [
    ("Whose phone was the glovebox phone with between 23 May and 7 June 2024?", ["23 May to 7 June 2024"]),
    ("from 2024-01-01 to 2024-03-31 totals", ["2024-01-01 to 2024-03-31"]),
    ("What happened on 7 June 2024?", ["7 June 2024"]),
    ("Did he call on May 23?", ["May 23"]),
    ("he may go", []),
])
def test_question_focus_keeps_both_ends_of_a_range(question, dates):
    # (f) "between 23 May and 7 June 2024" kept only 7 June 2024.
    from services.agent import question_scope
    assert question_scope.build(question).dates == dates


def test_connected_payment_description_is_not_shown_as_a_name():
    # (g) from_name "KELL T BAY 4 RENT" was the description, and the name fit read 0 as a disagreement.
    from services.agent.ledger_reading_tools import _printed_not_named
    anchor = {"direction": "credit", "counterparty": None, "description": "KELL T BAY 4 RENT",
              "from_name": "KELL T BAY 4 RENT", "to_name": "RUIZ AUTO & TIRE LLC"}
    out = _printed_not_named(anchor)
    assert out["from_name"] is None and out["printed_text"] == "KELL T BAY 4 RENT"
    assert out["to_name"] == "RUIZ AUTO & TIRE LLC"
    cand = {"direction": "debit", "counterparty": None, "description": "ACH RUIZ AUTO & TIRE BAY 4 RENT",
            "from_name": "TRAVIS KELL", "to_name": "ACH RUIZ AUTO & TIRE BAY 4 RENT", "fits": {"name": 0},
            "name_similarity": []}
    out = _printed_not_named(cand)
    assert out["to_name"] is None and "not a disagreement" in out["name_fit_words"]
    named = {"direction": "debit", "counterparty": "RUIZ AUTO", "to_name": "RUIZ AUTO", "from_name": "X"}
    assert _printed_not_named(named) == named


def test_replays_give_the_tools_a_case_reader():
    # (h) get_document_text refused every replay ("An active case reader is required"): no user was passed.
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "scripts"
    for name in ("financial_agent_fit_replay.py", "financial_agent_trace_replay.py"):
        src = (root / name).read_text()
        assert "user_id=REPLAY_USER_ID" in src and "--user-id" in src


def _q(**k):
    base = {"uncited": 2, "not_read": 0, "not_in_record": 0, "unfinished_unstated": 0, "other_side_missing": 0,
            "certainty": 0, "cited": 5, "citations": 6, "in_record": 6, "key": "missed"}
    return dict(base, **k)


def test_range_gate_does_not_reject_a_run_inside_the_same_settings_spread():
    # Coordinator 12 Nov: decide's any-count rule rejected identical settings on most pairs of repeats.
    from services.agent import prompt_loop as PL
    current = {"Q1": [_q(cited=4), _q(cited=6), _q(cited=5, certainty=1)]}
    same = {"Q1": [_q(cited=4, certainty=1)]}
    assert PL.decide({"Q1": current["Q1"][1]}, {"Q1": same["Q1"][0]}, held={"Q1"})["losses"]  # the single-run rule rejects it
    out = PL.decide_range(current, same, held={"Q1"})
    assert out["losses"] == {} and "no count gains beyond the same-settings range" in out["reasons"]
    better = PL.decide_range(current, {"Q1": [_q(cited=7, key="found")]}, held={"Q1"})
    assert better["accepted"] and better["gains"]["Q1"]


def test_range_gate_still_blocks_a_loss_outside_the_range_and_too_few_runs():
    from services.agent import prompt_loop as PL
    current = {"Q1": [_q(cited=4), _q(cited=6), _q(cited=5)], "Q2": [_q(), _q()]}
    out = PL.decide_range(current, {"Q1": [_q(cited=7), _q(cited=3)], "Q2": [_q(cited=9)]}, held={"Q1", "Q2"})
    assert not out["accepted"]
    assert out["losses"]["Q1"] == ["cited 3 outside 4..6"]
    assert out["too_few_runs"] == ["Q2"]
