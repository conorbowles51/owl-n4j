"""Guided investigative workflows (agent-workflows A): the registry, readiness on measured counts, the prompt block,
the run's record of the workflow, and the request's refusal of an unknown workflow."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from services.agent import workflows as W

# Tools the workflows name that sibling Phase 3 jobs register on their branches (agent-ledger: the money tools;
# agent-proposals: the proposal tools). Until those are merged a step on them is marked "not in this build". A name
# outside this set and outside the registered tools is a typo and fails.
PENDING_ON_SIBLING_BRANCHES = {
    "get_money_between", "get_judgement_calls", "get_decisions", "get_statement_continuity", "get_account_mentions",
    "propose_judgement_call", "propose_workspace_entry", "propose_lead_card", "propose_timeline_addition",
    "propose_link", "propose_assumption",
}
BY_PERSON = {"red_cell"}

ALL = {"ledger": 100, "financial_sources": 3, "phones": 3, "documents": 5, "dossiers": 4, "timeline": 2}


def test_ten_scenarios_and_seven_more():
    main = [w for w in W.WORKFLOWS if not w.extra]
    extra = [w for w in W.WORKFLOWS if w.extra]
    assert [w.number for w in main] == list(range(1, 11))
    assert len(extra) == 7 and all(w.adds_requirement and w.requirement_met_by for w in extra)
    assert len(W.BY_ID) == 17
    for w in W.WORKFLOWS:
        assert w.steps and w.proposals and w.person_confirms and w.starting_question


def test_every_tool_named_is_registered_or_pending_on_a_sibling_branch():
    have = W.registered_tool_names()
    named = {t for w in W.WORKFLOWS for t in w.tools} | {s.tool for w in W.WORKFLOWS for s in w.steps}
    unknown = named - have - PENDING_ON_SIBLING_BRANCHES - BY_PERSON
    assert not unknown, unknown


def test_requirements_met_by_exist_in_this_build():
    import importlib
    have = W.registered_tool_names()
    for w in W.WORKFLOWS:
        for ref in w.requirement_met_by:
            if ref.startswith("services."):
                mod, _, attr = ref.rpartition(".")
                try:
                    importlib.import_module(ref)
                except ModuleNotFoundError:
                    assert hasattr(importlib.import_module(mod), attr), ref
            else:
                assert ref in have or ref in PENDING_ON_SIBLING_BRANCHES, ref


def test_every_proposal_output_is_a_proposal_or_draft_tool():
    for w in W.WORKFLOWS:
        for tool, _ in w.proposals:
            assert tool.startswith(("propose_", "draft_")), (w.id, tool)


def test_block_marks_missing_tools_and_ends_with_not_examined():
    w = W.get("carer-abuse")
    block = W.render_block(w, tools={"get_money_signal_matches"})
    assert "get_money_between: money from the account holder" in block
    assert "not in this build: report it under Not examined" in block
    assert "'Not examined'" in block and "Never present the workflow's result as a conclusion" in block
    full = W.render_block(w, tools=set(w.tools))
    assert "not in this build" not in full


def test_red_cell_is_a_person_step_never_claimed():
    block = W.render_block(W.get("defence-review"), tools=set())
    assert "red_cell: " in block and "a person does this on screen; suggest it, do not claim it was done" in block


def test_readiness_counts_decide():
    tools = W.registered_tool_names() | PENDING_ON_SIBLING_BRANCHES
    assert W.assess(W.get("hidden-assets"), ALL, tools)["status"] == "ready"
    none_phones = dict(ALL, phones=0)
    r = W.assess(W.get("last-proof-of-life"), none_phones, tools)
    assert r["status"] == "not_possible" and r["reasons"] == ["the case holds no phone extractions"]
    r = W.assess(W.get("procurement-kickbacks"), dict(ALL, phones=1), tools)
    assert r["status"] == "not_possible" and r["reasons"] == ["needs 2 phones; the case holds 1"]
    # Hidden assets' ledger half runs without phones; the phone step is reported as not run.
    r = W.assess(W.get("hidden-assets"), none_phones, tools)
    assert r["status"] == "partial"
    assert [s["tool"] for s in r["steps"] if not s["runs"]] == ["get_money_signal_leads"]


def test_insider_trading_is_not_possible_while_brokerage_rows_are_not_modelled():
    r = W.assess(W.get("insider-trading"), ALL, W.registered_tool_names() | PENDING_ON_SIBLING_BRANCHES)
    assert r["status"] == "not_possible" and "instrument and quantity" in r["reasons"][0]


def test_missing_tool_makes_partial_and_is_named():
    r = W.assess(W.get("embezzlement"), ALL, tools={"get_money_signal_leads"})
    assert r["status"] == "partial"
    assert r["tools_missing"] == ["get_account_mentions", "get_statement_continuity", "propose_judgement_call",
                                  "propose_lead_card"]


def test_case_counts_read_only_and_missing_tables_count_zero(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "w.db"))
    case = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE financial_transactions (id integer, case_id text)"))
        conn.execute(text("INSERT INTO financial_transactions VALUES (1, :c), (2, :c), (3, 'other')"), {"c": str(case)})
    with engine.connect() as conn:
        counts = W.case_counts(conn, case)
    assert counts["ledger"] == 2 and counts["phones"] == 0 and counts["documents"] == 0


def test_catalogue_shape():
    cat = W.catalogue(ALL, W.registered_tool_names())
    assert cat["total"] == 17 and cat["schema"] == W.SCHEMA
    assert {"id", "title", "starting_question", "readiness", "steps", "proposals"} <= set(cat["workflows"][0])
    assert W.catalogue()["workflows"][0].get("readiness") is None


def test_request_refuses_an_unknown_workflow_and_keeps_a_known_one():
    from pydantic import ValidationError
    from services.agent.schemas import AgentMessageRequest
    ok = AgentMessageRequest(message="go", case_id=uuid.uuid4(), workflow_id="hidden-assets")
    assert ok.workflow_id == "hidden-assets"
    assert AgentMessageRequest(message="go", case_id=uuid.uuid4()).workflow_id is None
    with pytest.raises(ValidationError):
        AgentMessageRequest(message="go", case_id=uuid.uuid4(), workflow_id="nope")


def test_run_metadata_and_prompt_block():
    from services.agent.schemas import AgentMessageRequest
    from services.agent.service import AgentService
    req = AgentMessageRequest(message="go", case_id=uuid.uuid4(), workflow_id="drug-proceeds")
    meta = AgentService._workflow_metadata(req)
    assert meta["workflow"]["id"] == "drug-proceeds" and meta["workflow"]["number"] == 8
    assert "propose_assumption" in meta["workflow"]["proposals"]
    block = AgentService._prompt_block("MANDATE", req)
    assert block.startswith("MANDATE\n\nGuided workflow 8: Drug-supply turnover and proceeds.")
    plain = AgentMessageRequest(message="go", case_id=uuid.uuid4())
    assert AgentService._workflow_metadata(plain) == {} and AgentService._prompt_block("MANDATE", plain) == "MANDATE"


def test_prompt_version_fingerprints_every_workflow_plan():
    from services.agent.run_record import prompt_version_source
    src = prompt_version_source()
    assert set(src["prompts"]["workflows"]) == set(W.BY_ID)
