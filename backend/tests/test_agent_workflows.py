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


def test_scenario_9_reads_messages_across_phones():
    from services.agent.phone_cross_tools import AnalysisArgs
    assert AnalysisArgs(approach="message_reconciliation").approach == "message_reconciliation"
    assert ("get_analysis_results" in [s.tool for s in W.get("staged-accident").steps])


def test_phone_evidence_rows_are_not_documents_and_a_failed_count_is_unknown(tmp_path):
    engine = create_engine("sqlite:///%s" % (tmp_path / "d.db"))
    case = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE evidence_files (id text, case_id text, cellebrite_file_id text, "
                          "cellebrite_report_key text, source_type text)"))
        conn.execute(text("CREATE TABLE financial_source_documents (case_id text, evidence_file_id text)"))
        rows = [("a", "phone_extraction"), ("b", "phone_file"), ("c", "phone_text"), ("d", "cellebrite"),
                ("e", None), ("f", "upload"), ("s", None)]
        for i, st in rows:
            conn.execute(text("INSERT INTO evidence_files VALUES (:i, :c, NULL, NULL, :s)"), {"i": i, "c": str(case),
                                                                                             "s": st})
        conn.execute(text("INSERT INTO financial_source_documents VALUES (:c, 's')"), {"c": str(case)})
    with engine.connect() as conn:
        assert W.case_counts(conn, case)["documents"] == 2  # e and f; the statement s and four phone rows left out
    r = W.assess(W.get("expense-fraud"), dict(ALL, documents=None), W.registered_tool_names())
    assert r["status"] == "unknown" and "could not be counted" in r["reasons"][0]


def test_person_only_tools_need_a_dossier():
    """get_person_phones and draft_control_claim take a person (dossier) and nothing else; a case with no dossier
    cannot run them, so the workflow is partial, not ready (live: the synthetic training case holds 0 dossiers)."""
    for w in W.WORKFLOWS:
        for s in w.steps:
            if s.tool in ("get_person_phones", "draft_control_claim"):
                assert "dossiers" in s.needs, (w.id, s.tool)
    tools = W.registered_tool_names() | PENDING_ON_SIBLING_BRANCHES
    r = W.assess(W.get("carer-abuse"), dict(ALL, dossiers=0), tools)
    assert r["status"] == "partial" and "draft_control_claim" in [s["tool"] for s in r["steps"] if not s["runs"]]


def test_block_states_the_budget_and_when_to_stop():
    block = W.render_block(W.get("hidden-assets"), tools=set(), budget=28)
    assert "allows 28 tool calls" in block and "Once 24 calls are made, stop calling tools" in block
    assert "'not run: tool budget'" in block and "run_readonly_cypher" in block
    from services.agent.schemas import AgentMessageRequest
    from services.agent.service import AgentService, DEFAULT_AGENT_MAX_TOOL_CALLS
    req = AgentMessageRequest(message="go", case_id=uuid.uuid4(), workflow_id="hidden-assets")
    assert "allows %d tool calls" % DEFAULT_AGENT_MAX_TOOL_CALLS in AgentService._prompt_block("", req)
