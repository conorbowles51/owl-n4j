"""lx-agentfit round 2: the answer-quality rule check (R2a), the switches that change what DeepSeek is given (R2b:
S, Q, A, V) and the prompt loop (R12)."""
from __future__ import annotations

import os
from unittest import mock

from services.agent import answer_quality as AQ
from services.agent import prompt_loop as PL

TXN = "txn://0ca38b99-7f7e-43e2-8bc5-6e9d4317bc11"
REC = "rec://7dee2434-b5ca-50a9-a328-bfcf969293f1"
OUTPUTS = [{"data": {"items": [
    {"cite": TXN, "amount_minor": 120000000, "currency": "MXN", "transaction_date": "2025-05-12"},
    {"ref": REC, "text": "Seized on June 14, 2024 from the glovebox"}]}}]


def test_figures_read_dates_and_amounts_as_records_write_them():
    assert AQ.figures("On 12 May 2025 it received 1,200,000.00 MXN") == {"2025-05-12", "1200000"}
    assert AQ.figures("May 12, 2025 and 2025-05-12") == {"2025-05-12"}
    assert AQ.figures("2 calls") == set()


def test_a_cited_figure_its_record_carries_is_in_record_and_one_it_does_not_is_listed():
    answer = (f"On 12 May 2025 the account received 1,200,000.00 MXN ([payment]({TXN})). "
              f"It also received 3,800,000.00 MXN ([payment]({TXN})). "
              f"The phone was seized on 14 June 2024 ([record]({REC})). "
              "The total was 9,999.00 USD.")
    s = AQ.score(answer, OUTPUTS)
    assert (s["claims"], s["cited"], s["uncited"], s["citations"], s["not_read"]) == (4, 3, 1, 2, 0)
    assert s["in_record"] == 3 and s["not_in_record"] == 1
    assert s["unsupported"][0]["figures"] == ["3800000"]


def test_a_link_to_a_record_no_result_returned_is_not_read():
    s = AQ.score("Paid 5,000.00 ([p](txn://11111111-2222-3333-4444-555555555555)).", OUTPUTS)
    assert s["not_read"] == 1 and s["in_record"] == 0 and s["not_in_record"] == 0


def test_unfinished_and_other_side_and_certainty_are_counted():
    s = AQ.score("Phone 3 was with Phone 2 [r](%s). This proves it." % REC, OUTPUTS,
                 question="Whose phone was it with?", stopped_at_limit=True)
    assert s["unfinished_unstated"] == 1 and s["other_side_missing"] == 1 and s["certainty"] == 1
    s = AQ.score("I could not yet read every message. The records do not support the other version.", [],
                 question="Whose phone was it with?", stopped_at_limit=True)
    assert s["unfinished_unstated"] == 0 and s["other_side_missing"] == 0


def test_losses_name_every_count_that_got_worse_whatever_else_gained():
    before = {"cited": 5, "citations": 5, "in_record": 8, "not_in_record": 0, "uncited": 2}
    after = {"cited": 9, "citations": 4, "in_record": 12, "not_in_record": 1, "uncited": 0}
    assert AQ.losses(before, after) == ["not_in_record 0 → 1", "citations 5 → 4"]


def test_mark_unsupported_keeps_the_answer_and_lists_the_figure_to_check():
    answer = f"It received 3,800,000.00 MXN ([payment]({TXN}))."
    marked = AQ.mark_unsupported(answer, OUTPUTS)
    assert marked.startswith(answer) and AQ.UNSUPPORTED_HEADING in marked and "3800000" in marked
    supported = f"It received 1,200,000.00 MXN ([payment]({TXN}))."
    assert AQ.mark_unsupported(supported, OUTPUTS) == supported


def _s(**kw):
    base = {"cited": 3, "citations": 3, "in_record": 3, "not_in_record": 0, "uncited": 1, "not_read": 0,
            "unfinished_unstated": 0, "other_side_missing": 0, "certainty": 0, "key": None}
    return base | kw


def test_decide_refuses_a_candidate_that_loses_on_any_question_even_with_net_gains():
    ids = [f"q{i}" for i in range(20)]
    held = PL.held_out(ids)
    current = {q: _s() for q in ids}
    candidate = {q: _s(cited=6, citations=6) for q in ids}
    candidate["q3"] = _s(citations=2)
    d = PL.decide(current, candidate, held=held)
    assert not d["accepted"] and "q3" in d["losses"]
    candidate["q3"] = _s()
    assert PL.decide(current, candidate, held=held)["accepted"]


def test_decide_needs_a_held_out_question_the_candidate_was_not_written_from():
    ids = [f"q{i}" for i in range(20)]
    held = PL.held_out(ids)
    assert held and len(held) < len(ids)
    current = {q: _s() for q in ids}
    candidate = {q: _s(cited=4) for q in ids}
    d = PL.decide(current, candidate, held=held, written_from=held)
    assert not d["accepted"] and "no held-out question was checked" in d["reasons"]


def test_decide_counts_a_worse_demo_key_as_a_loss():
    d = PL.decide({"demo-Q1": _s(key="found")}, {"demo-Q1": _s(key="missed", cited=9)}, held={"demo-Q1"})
    assert not d["accepted"] and d["losses"]["demo-Q1"] == ["key found → missed"]


def test_held_out_is_stable_as_the_question_set_grows():
    first = PL.held_out([f"q{i}" for i in range(50)])
    grown = PL.held_out([f"q{i}" for i in range(80)])
    assert first == {q for q in grown if int(q[1:]) < 50}


def test_part_versions_name_the_part_that_changed(tmp_path):
    a = PL.part_versions({"system": "x", "answer_requirements": ""}, [{"function": {"name": "t1", "d": 1}}])
    b = PL.part_versions({"system": "x", "answer_requirements": "check"}, [{"function": {"name": "t1", "d": 2}}])
    assert PL.changed_parts(a, b) == ["prompt:answer_requirements", "tool:t1"]
    path = tmp_path / "h.jsonl"
    PL.record(PL.decide({"q": _s()}, {"q": _s(cited=4)}, held={"q"}), part="prompt:answer_requirements",
              current="v1", candidate="v2", path=str(path))
    assert PL.history(str(path))[0]["accepted"] is True


class _Conn:
    def __init__(self, runs, together):
        self.runs, self.together = runs, together

    def begin_nested(self):
        return mock.MagicMock()

    def execute(self, sql, params):
        if "phone_analysis_runs" in str(sql):
            return iter(self.runs)
        return mock.Mock(scalar=lambda: self.together)


def test_case_briefing_says_what_the_case_holds_and_lacks():
    from services.agent import case_briefing
    text = case_briefing.briefing(_Conn([("device_users", 1)], 0), "c", {
        "ledger": 0, "financial_sources": 0, "trades": 0, "phones": 6, "documents": 12, "dossiers": None,
        "timeline": 3})
    assert "6 phone extractions" in text and "Holds none: payments in the ledger" in text
    assert "Could not be counted: dossiers" in text and "device_users 1" in text
    assert "Together-and-apart runs made: 0." in text and case_briefing.LACKS in text


def test_answer_requirements_and_plan_reach_the_model_only_with_their_switch():
    from services.agent import graph
    with mock.patch.dict(os.environ, {"LOUPE_AGENT_FIT": "W"}):
        assert "restate the question as a plan" not in graph._fit_prompt_lines()
    with mock.patch.dict(os.environ, {"LOUPE_AGENT_FIT": "W,Q"}):
        assert "restate the question as a plan" in graph._fit_prompt_lines()
    assert "never 'proves' or 'confirms'" in graph.ANSWER_REQUIREMENTS
    src = open(graph.__file__).read()
    assert 'if fit.on("A"):\n        request += ANSWER_REQUIREMENTS' in src


def test_check_before_answer_lists_unsupported_figures_only_with_v():
    from services.agent import graph
    from services.agent.tools import AgentToolContext
    ctx = AgentToolContext(case_id="c")
    ctx.model_views["res_1"] = OUTPUTS[0]
    answer = f"It received 3,800,000.00 MXN ([payment]({TXN}))."
    with mock.patch.dict(os.environ, {"LOUPE_AGENT_FIT": "W"}):
        assert AQ.UNSUPPORTED_HEADING not in graph._with_kept_sources(answer, ctx, False)
    with mock.patch.dict(os.environ, {"LOUPE_AGENT_FIT": "W,V"}):
        assert AQ.UNSUPPORTED_HEADING in graph._with_kept_sources(answer, ctx, False)


def test_the_prompt_version_changes_with_a_round_two_part():
    from services.agent import run_record
    with mock.patch.dict(os.environ, {"LOUPE_AGENT_FIT": "W"}):
        off = run_record.prompt_version_source()["prompts"]
    with mock.patch.dict(os.environ, {"LOUPE_AGENT_FIT": "W,A,S"}):
        on = run_record.prompt_version_source()["prompts"]
    assert off["answer_requirements"] == "" and on["answer_requirements"]
    assert on["case_briefing"] and on["agent_fit"] == ["W", "S", "A"]
