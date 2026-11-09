"""lx-callagent (team call, 9 Nov 2026): retries are shown (AG-06), a person picks the model per message and the
answer says which wrote it (AG-08, AG-07), and the answer stays on the question (AG-02). Each test fails on the code
before these changes (no invoke_model / progress_retrying, model overrides refused, no question_scope)."""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402
import openai  # noqa: E402


def _timeout():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))


def _bad_request():
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    return openai.BadRequestError("bad", response=httpx.Response(400, request=request), body=None)


class FlakyModel:
    def __init__(self, failures, error=_timeout):
        self.failures, self.error, self.calls = failures, error, 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error()
        return SimpleNamespace(content="answer")


class RetryShownTests(unittest.TestCase):
    def test_each_retry_is_said_in_plain_words_before_the_wait(self):
        from services.agent.graph import invoke_model
        events = []
        model = FlakyModel(failures=2)
        out = invoke_model(model, [], note=lambda p: events.append(("note", p)), step=3,
                           sleep=lambda s: events.append(("sleep", s)))
        self.assertEqual(out.content, "answer")
        notes = [p for kind, p in events if kind == "note"]
        self.assertEqual([p["title"] for p in notes], [
            "The model service did not answer in time; trying again (2 of 3)",
            "The model service did not answer in time; trying again (3 of 3)"])
        self.assertEqual({p["phase"] for p in notes}, {"retrying"})
        self.assertEqual(notes[0]["step"], 3)
        # The line reaches the reader before the run waits, so it shows within the 2 s the reader polls at.
        self.assertEqual(events[0][0], "note")

    def test_a_final_failure_says_what_failed_and_offers_retry(self):
        from services.agent.graph import ModelServiceError, invoke_model
        with self.assertRaises(ModelServiceError) as caught:
            invoke_model(FlakyModel(failures=5), [], sleep=lambda s: None)
        self.assertIn("did not answer in time after 3 tries", str(caught.exception))
        self.assertIn("Retry", str(caught.exception))
        self.assertTrue(caught.exception.retryable)

    def test_a_refused_request_is_not_tried_again(self):
        from services.agent.graph import invoke_model
        model = FlakyModel(failures=1, error=_bad_request)
        with self.assertRaises(openai.BadRequestError):
            invoke_model(model, [], sleep=lambda s: None)
        self.assertEqual(model.calls, 1)

    def test_stop_during_the_wait_stops_the_run(self):
        from services.agent.graph import AgentRunCancelled, invoke_model
        with self.assertRaises(AgentRunCancelled):
            invoke_model(FlakyModel(failures=1), [], should_cancel=lambda: True, sleep=lambda s: None)

    def test_the_client_no_longer_retries_silently(self):
        from services.agent.graph import AgentGraphRunner
        runner = AgentGraphRunner(provider="deepseek", model_id="deepseek-v4-pro", api_key="k")
        self.assertEqual(runner.base_model.max_retries, 0)

    def test_a_retried_step_reaches_the_live_progress(self):
        """Through the production stream: a model turn that times out once shows the retry line, then answers."""
        from langchain_core.messages import AIMessage, HumanMessage
        from services.agent import graph

        class Model:
            calls = 0

            def bind_tools(self, tools, **_k):
                return self

            def invoke(self, messages):
                Model.calls += 1
                if Model.calls == 1:
                    raise _timeout()
                return AIMessage(content="No tools needed: the answer.")

        runner = graph.AgentGraphRunner.__new__(graph.AgentGraphRunner)
        runner.provider, runner.model_id, runner.base_model = "deepseek", "deepseek-v4-pro", Model()
        seen = []
        with patch.object(graph, "RETRY_WAITS_SECONDS", (0.0, 0.0)):
            events = list(runner.stream(case_id="00000000-0000-0000-0000-000000000001", thread_id="t",
                                        messages=[HumanMessage(content="Hello?")], on_progress=seen.append))
        titles = [p.get("title") for p in seen]
        self.assertIn("The model service did not answer in time; trying again (2 of 3)", titles)
        final = [e for e in events if e.get("type") == "final"][-1]["result"]
        self.assertEqual(final["answer"], "No tools needed: the answer.")


class OutOfStepsTests(unittest.TestCase):
    def test_running_out_of_steps_still_writes_the_answer_and_offers_continue(self):
        """Both team-call questions, replayed on 97f1779d9, used all 28 steps and ended with no answer at all."""
        from langchain_core.messages import AIMessage, HumanMessage
        from services.agent import graph

        class Planner:
            def invoke(self, messages):
                return AIMessage(content="", tool_calls=[{"name": "no_such_tool", "args": {}, "id": "c%d" % len(messages)}])

        class Writer:
            requests = []

            def bind_tools(self, tools, **_k):
                return Planner()

            def invoke(self, messages):
                Writer.requests.append(messages[-1].content)
                return AIMessage(content="Partial: two accounts found so far.")

        runner = graph.AgentGraphRunner.__new__(graph.AgentGraphRunner)
        runner.provider, runner.model_id, runner.base_model = "deepseek", "deepseek-v4-pro", Writer()
        events = list(runner.stream(case_id="00000000-0000-0000-0000-000000000001", thread_id="t", max_tool_calls=2,
                                    messages=[HumanMessage(content="Which accounts?")]))
        final = [e for e in events if e.get("type") == "final"][-1]["result"]
        self.assertEqual(final["answer"], "Partial: two accounts found so far.")
        self.assertEqual(final["clarification"]["context"]["reason"], "tool_budget_exhausted")
        self.assertIn("start with one line saying what it could not yet cover", Writer.requests[-1])


class FaultDrillTests(unittest.TestCase):
    def test_the_drill_fails_the_first_request_once_across_bound_copies(self):
        from services.agent.graph import FaultDrill, invoke_model
        notes = []
        drill = FaultDrill(SimpleNamespace(invoke=lambda m: "ok", bind_tools=lambda t: SimpleNamespace(invoke=lambda m: "tools")))
        bound = drill.bind_tools([])
        self.assertEqual(invoke_model(bound, [], note=notes.append, sleep=lambda s: None), "tools")
        self.assertEqual(drill.invoke([]), "ok")
        self.assertEqual(len(notes), 1)


class ReasoningClientTests(unittest.TestCase):
    def test_higher_reasoning_sends_thinking_and_effort_and_returns_the_reasoning(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from services.agent.graph import DeepSeekReasoningChat, deepseek_chat
        off = deepseek_chat(model_id="deepseek-v4-pro", api_key="k", reasoning="off")
        self.assertEqual(off.extra_body, {"thinking": {"type": "disabled"}})
        high = deepseek_chat(model_id="deepseek-v4-pro", api_key="k", reasoning="high")
        self.assertIsInstance(high, DeepSeekReasoningChat)
        self.assertEqual(high.extra_body, {"thinking": {"type": "enabled"}, "reasoning_effort": "high"})
        earlier = AIMessage(content="", additional_kwargs={"reasoning_content": "I should read the ledger."},
                            tool_calls=[{"name": "t", "args": {}, "id": "c1"}])
        payload = high._get_request_payload([HumanMessage(content="q"), earlier])
        self.assertEqual(payload["messages"][1]["reasoning_content"], "I should read the ledger.")
        result = high._create_chat_result({"choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": "a", "reasoning_content": "thought"}}]})
        self.assertEqual(result.generations[0].message.additional_kwargs["reasoning_content"], "thought")

    def test_an_unknown_level_is_refused(self):
        from services.agent.graph import deepseek_chat
        with self.assertRaises(ValueError):
            deepseek_chat(model_id="deepseek-v4-pro", api_key="k", reasoning="extreme")


def _policy(db, workload):
    return ("deepseek", "deepseek-v4-pro")


class ModelChoiceTests(unittest.TestCase):
    def _configured(self, providers):
        return patch("services.ai_model_policy.provider_is_configured",
                     side_effect=lambda provider, db=None: provider in providers)

    def test_choices_put_the_default_first_and_offer_no_openai(self):
        from services.agent import model_choice
        with self._configured({"deepseek", "openai"}):
            offered, default = model_choice.choices(None, workload_model=_policy)
        self.assertEqual(offered[0], default)
        self.assertEqual(default.key, "deepseek-v4-pro:high")
        self.assertNotIn("openai", {c.provider for c in offered})
        self.assertIn("deepseek-v4-pro:off", {c.key for c in offered})
        self.assertEqual([c.label for c in offered if c.model_id == "deepseek-v4-pro"],
                         ["DeepSeek V4 Pro · thinks longer", "DeepSeek V4 Pro · answers faster",
                          "DeepSeek V4 Pro · thinks longest"])

    def test_a_pick_is_resolved_and_marked_as_a_persons_choice(self):
        from services.agent import model_choice
        with self._configured({"deepseek"}):
            choice, chosen = model_choice.resolve(None, model="deepseek-v4-pro", provider=None, reasoning="max",
                                                  workload_model=_policy)
            default, by_person = model_choice.resolve(None, model=None, provider=None, reasoning=None,
                                                      workload_model=_policy)
            with self.assertRaisesRegex(ValueError, "OpenAI"):
                model_choice.resolve(None, model="gpt-5", provider="openai", reasoning=None, workload_model=_policy)
        self.assertEqual((choice.reasoning, chosen), ("max", True))
        self.assertEqual((default.key, by_person), ("deepseek-v4-pro:high", False))
        self.assertEqual(model_choice.written_by(choice.model_name, choice.reasoning),
                         "Written by DeepSeek V4 Pro · thinks longest")

    def test_the_answer_shows_the_model_recorded_on_its_run(self):
        from services.agent.storage import _written_by
        run = SimpleNamespace(extra_metadata={"model_choice": {"written_by": "Written by DeepSeek V4 Pro · thinks "
                                                                              "longest"}})
        message = SimpleNamespace(role="assistant", model_id="deepseek-v4-pro", run=run)
        self.assertEqual(_written_by(message), "Written by DeepSeek V4 Pro · thinks longest")
        older = SimpleNamespace(role="assistant", model_id="deepseek-v4-pro", run=SimpleNamespace(extra_metadata={}))
        self.assertEqual(_written_by(older), "Written by DeepSeek V4 Pro")
        self.assertIsNone(_written_by(SimpleNamespace(role="user", model_id=None, run=None)))


ACCOUNTS = [
    dict(id="a1", holder="ERICA HOPPER", institution="Truist", identifier="****1234"),
    dict(id="a2", holder="GEORGE N DORSEY JR", institution="Bank of America", identifier="000055667788"),
    dict(id="a3", holder="ERICA HOPPER / LASHIKA -HOPPER", institution="Truist", identifier="999999"),
    dict(id="a4", holder="NOVAC PATRIMONIAL SA DE CV", institution="BBVA", identifier="0110274593"),
]


class QuestionScopeTests(unittest.TestCase):
    def test_the_scope_drops_an_account_the_question_does_not_name(self):
        from services.agent import question_scope
        scope = question_scope.build("Did erica hopper move money out of her accounts in March 2021?", ACCOUNTS)
        self.assertEqual([a["id"] for a in scope.accounts], ["a1", "a3"])
        self.assertEqual(scope.names, ["ERICA HOPPER"])
        self.assertEqual(scope.dates, ["March 2021"])
        block = question_scope.block(scope)
        self.assertIn("ERICA HOPPER · Truist · ****1234", block)
        self.assertNotIn("NOVAC", block)
        self.assertNotIn("DORSEY", block)
        self.assertIn("Also found:", block)

    def test_an_account_named_by_number_ranks_first(self):
        from services.agent import question_scope
        scope = question_scope.build("What went from Erica Hopper to account 55667788 in 2020?", ACCOUNTS)
        self.assertEqual([a["id"] for a in scope.accounts], ["a2", "a1", "a3"])
        self.assertEqual(scope.identifiers, ["55667788"])

    def test_the_planning_prompt_asks_for_a_case_wide_search_of_each_named_person_and_the_answer_prompt_does_not(self):
        """Run 8df85211 found a person's second account number only in payment text, by searching the name; replays
        that did not search named one account of two (lx-callagent, 9 Nov)."""
        from services.agent import question_scope
        scope = question_scope.build("Which accounts does Erica Hopper hold that this case's financial records do "
                                     "not?", ACCOUNTS)
        planning = question_scope.block(scope, planning=True)
        self.assertIn("search the whole case for each person or company named here (search_case with the name)",
                      planning)
        self.assertNotIn("search_case", question_scope.block(scope))
        nobody = question_scope.build("What happened in March 2021?", ACCOUNTS)
        self.assertNotIn("search_case", question_scope.block(nobody, planning=True))

    def test_focus_for_gives_the_planning_and_the_answer_block(self):
        from unittest import mock
        from services.agent import question_scope
        session = mock.MagicMock()
        with mock.patch.object(question_scope, "case_accounts", return_value=ACCOUNTS):
            planning, answer = question_scope.focus_for(session, "c1", "Which accounts does Erica Hopper hold?")
        self.assertIn("search_case", planning)
        self.assertNotIn("search_case", answer)
        self.assertTrue(answer.startswith("Stay on the question."))

    def test_a_question_naming_nothing_still_gets_the_rule(self):
        from services.agent import question_scope
        block = question_scope.block(question_scope.build("What happened?", ACCOUNTS))
        self.assertTrue(block.startswith("Stay on the question."))
        self.assertNotIn("Case accounts", block)


try:
    from tests.test_agent_run_record import RunRecordFixture
except Exception:  # noqa: BLE001 - the service tests need the ledger fixture's packages
    RunRecordFixture = None


if RunRecordFixture is not None:
    class ServicePathTests(RunRecordFixture):
        """Through both service paths: the picked model runs, is recorded on the run and shown on the answer; the
        question's focus reaches the planning and final-answer prompts."""

        def run_service(self, path, _result=None, **request_fields):
            from services.agent import service as svc
            from services.agent.schemas import AgentMessageRequest
            from postgres.models.agent import AgentRun
            captured = {}
            result = {"answer": "Erica Hopper holds two accounts.", "tool_trace": [], "artifacts": [], "usage": None,
                      **(_result or {})}

            class Runner:
                def __init__(self, **kwargs):
                    captured["init"] = kwargs

                def spent_so_far(self):
                    return None

                def stream(self, **kwargs):
                    captured["call"] = kwargs
                    yield {"type": "final", "result": result}

                def invoke(self, **kwargs):
                    captured["call"] = kwargs
                    return result

            mandate = SimpleNamespace(override=None, block="")
            with patch.object(svc, "check_case_access"), \
                    patch.object(svc, "get_workload_model", return_value=("deepseek", "deepseek-v4-pro")), \
                    patch("services.ai_model_policy.provider_is_configured", return_value=True), \
                    patch.object(svc, "get_provider_api_key", return_value="k"), \
                    patch.object(svc, "AgentGraphRunner", Runner), \
                    patch.object(svc.mandate_context_service, "resolve", return_value=mandate), \
                    patch.object(svc.mandate_context_service, "active_version", return_value=None), \
                    patch.object(svc.mandate_context_service, "metadata", return_value={}), \
                    patch.object(svc.system_log_service, "log"), \
                    patch.object(svc.AgentService, "_proposal_feedback", return_value=None), \
                    patch.object(svc.storage, "check_case_access"):
                request = AgentMessageRequest(message="What does Erica Hopper hold?", case_id=self.fx.case.id,
                                              **request_fields)
                if path == "stream":
                    out = list(svc.agent_service.stream_message(db=self.fx.db, user=self.fx.user, request=request))
                    self.assertEqual(out[-1]["type"], "done", out[-1])
                    response = out[-1]["response"]
                else:
                    response = svc.agent_service.handle_message(db=self.fx.db, user=self.fx.user,
                                                                request=request).model_dump(mode="json")
            run = self.fx.db.get(AgentRun, __import__("uuid").UUID(str(response["run_id"])))
            return captured, response, run

        def test_the_picked_model_runs_and_the_answer_says_so(self):
            for path in ("stream", "handle"):
                with self.subTest(path=path):
                    captured, response, run = self.run_service(path, model="deepseek-v4-pro", reasoning="off")
                    self.assertEqual(captured["init"]["reasoning"], "off")
                    self.assertEqual(run.extra_metadata["model_choice"]["reasoning"], "off")
                    self.assertTrue(run.extra_metadata["model_choice"]["chosen_by_person"])
                    self.assertEqual(response["model_info"]["written_by"], "Written by DeepSeek V4 Pro")
                    from services.agent.storage import get_thread_detail
                    with patch("services.agent.storage.check_case_access"):
                        detail = get_thread_detail(self.fx.db, thread_id=run.thread_id, user=self.fx.user)
                    answers = [m for m in detail.messages if m.role == "assistant"]
                    self.assertEqual(answers[-1].written_by, "Written by DeepSeek V4 Pro")

        def test_an_out_of_steps_answer_keeps_the_answer_and_the_offer(self):
            from services.agent.graph import _budget_continuation_clarification
            captured, response, run = self.run_service("stream", _result={
                "answer": "Partial: two accounts found so far.",
                "clarification": _budget_continuation_clarification(28)})
            self.assertTrue(response["answer"].startswith("Partial: two accounts found so far.\n\nI reached the limit"))

        def test_the_default_needs_no_pick(self):
            captured, response, run = self.run_service("stream")
            self.assertEqual(captured["init"]["reasoning"], "high")
            self.assertEqual(response["model_info"]["written_by"], "Written by DeepSeek V4 Pro · thinks longer")
            self.assertFalse(run.extra_metadata["model_choice"]["chosen_by_person"])

        def test_the_focus_reaches_both_prompts(self):
            for path in ("stream", "handle"):
                with self.subTest(path=path):
                    captured, _, _ = self.run_service(path)
                    self.assertIn("Stay on the question.", captured["call"]["mandate_context_block"])
                    self.assertIn("Stay on the question.", captured["call"]["final_answer_rules"])


if __name__ == "__main__":
    unittest.main()
