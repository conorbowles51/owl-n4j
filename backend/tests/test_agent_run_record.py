"""The agent run record is the disclosure record (agent-record A-D).

Runs the real agent runner with a scripted model over the real ledger tools (synthetic SQLite case), stores the run
through the real storage path, and checks what the record and its two exports state. Every check here fails on the
code before the run record: the trace carried no per-call totals, revisions or items, runs had no prompt version or
person, nothing said which returned items were opened, and no export existed.
"""
from contextlib import contextmanager
import csv
import io
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from postgres.base import Base
from postgres.models.agent import (AgentArtifactRecord, AgentMessage, AgentPromptVersion, AgentRun, AgentRunItem,
                                   AgentThread, AgentToolCall)
from services.agent import run_record
from services.agent.graph import AgentGraphRunner
from services.agent.model_payloads import tool_message_payload
import services.agent.storage as storage
from tests import test_agent_financial_ledger_tools as ledger_fixture


class ScriptedModel:
    """Asks for the given calls in order (each step sees earlier tool outputs), then answers with ``answer``."""

    def __init__(self, steps, answer):
        self.steps, self.answer, self.outputs, self.index = steps, answer, {}, 0

    def _record(self, messages):
        for message in messages:
            if isinstance(message, ToolMessage):
                # The message as first sent (later turns carry its digest: services.agent.lean_history).
                self.outputs.setdefault(message.tool_call_id, json.loads(message.content))

    def bind_tools(self, tools):
        owner = self

        class Bound:
            def invoke(self, messages):
                owner._record(messages)
                if owner.index == len(owner.steps):
                    return AIMessage(content=owner.answer(owner.outputs))
                step = owner.steps[owner.index]
                owner.index += 1
                calls = step(owner.outputs)
                calls = calls if isinstance(calls, list) else [calls]
                return AIMessage(content="", tool_calls=[
                    {"id": "step-%d-%d" % (owner.index, n), "name": name, "args": args}
                    for n, (name, args) in enumerate(calls)])

        return Bound()

    def invoke(self, messages):
        self._record(messages)
        return AIMessage(content=self.answer(self.outputs))


def _first(outputs):
    return outputs["step-1-0"]["data"]


class RunRecordFixture(unittest.TestCase):
    def setUp(self):
        fixture = ledger_fixture.FinancialAgentLedgerTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.fx = fixture
        Base.metadata.create_all(fixture.engine, tables=[m.__table__ for m in (
            AgentThread, AgentRun, AgentMessage, AgentToolCall, AgentArtifactRecord, AgentPromptVersion,
            AgentRunItem)])
        from postgres.models.case_context import CaseMandateVersion
        from postgres.models.financial_judgements import FinancialJudgement
        Base.metadata.create_all(fixture.engine, tables=[FinancialJudgement.__table__, CaseMandateVersion.__table__])
        self.rows = fixture.source(rows=5)

    def run_agent(self, steps, answer, *, max_tool_calls=28, path="stream"):
        runner = object.__new__(AgentGraphRunner)
        runner.base_model = ScriptedModel(steps, answer)
        runner.model_id = "deepseek-v4-pro"

        @contextmanager
        def read_session(*_a, **_k):
            with self.fx.SessionLocal() as session:
                yield session

        kwargs = dict(case_id=str(self.fx.case.id), max_tool_calls=max_tool_calls,
                      messages=[HumanMessage(content="Which payments went to the exact source company?")])
        with patch("services.agent.tools._financial_session", read_session):
            if path == "invoke":
                return runner.invoke(**kwargs)
            return list(runner.stream(**kwargs))[-1]["result"]

    def store(self, result, *, status="completed"):
        db = self.fx.db
        user = self.fx.user
        thread = storage.create_thread(db, user=user, case_id=self.fx.case.id, title="t")
        run = storage.create_run(db, thread=thread, user=user, provider="deepseek", model_id="deepseek-v4-pro",
                                 input_message="Which payments?", tool_budget=28, prompt_version="a" * 64,
                                 prompt_version_label="v1 · 2026-11-03 · aaaaaaaa")
        storage.persist_tool_trace(db, run=run, trace=result["tool_trace"], skip_existing=True)
        run_record.persist_call_facts(db, run=run, trace=result["tool_trace"], answer=result["answer"],
                                      artifacts=result.get("artifacts"), messages=result.get("messages"))
        storage.finish_run(db, run=run, status=status, final_answer=result["answer"])
        db.commit()
        return run

class RunRecordTests(RunRecordFixture):
    # -- A: per-call columns -------------------------------------------------------------------------------

    def test_ledger_call_records_total_returned_next_page_and_ledger_revision(self):
        for path in ("stream", "invoke"):
            result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2})],
                                    lambda o: "Two of five shown.", path=path)
            facts = result["tool_trace"][0]["record"]
            data = None
            self.assertEqual((facts["total"], facts["returned"]), (5, 2), path)
            self.assertEqual(facts["next_page"]["tool"]["offset"], 2)
            self.assertEqual(len(facts["ledger_revision"]), 64)
            self.assertEqual(facts["category"], "ledger")
            self.assertEqual([i["kind"] for i in facts["items"]], ["payment", "payment"])
            self.assertIsNone(data)

    def test_stored_call_has_columns_and_run_has_person_budget_and_prompt_version(self):
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2})], lambda o: "Done.")
        run = self.store(result)
        call = self.fx.db.query(AgentToolCall).filter_by(run_id=run.id).one()
        self.assertEqual((call.total, call.returned, call.next_page["tool"]["offset"]), (5, 2, 2))
        self.assertEqual(len(call.ledger_revision), 64)
        self.assertEqual(call.tool_not_returned, 3)
        self.assertEqual(run.for_user_email, self.fx.user.email)
        self.assertEqual((run.tool_budget, run.tool_calls_used), (28, 1))
        self.assertTrue(run.prompt_version_label.startswith("v1"))

    def test_prompt_version_is_stable_and_changes_with_prompt_or_tools(self):
        source = run_record.prompt_version_source()
        self.assertGreaterEqual(len(source["tools"]), 30)
        self.assertNotIn(str(self.fx.case.id), json.dumps(source))
        first = run_record.prompt_version_hash(source)
        self.assertEqual(first, run_record.prompt_version_hash(run_record.prompt_version_source()))
        changed = json.loads(json.dumps(source))
        changed["tools"][0]["function"]["description"] += " changed"
        self.assertNotEqual(first, run_record.prompt_version_hash(changed))
        label = run_record.register_prompt_version(self.fx.db, first, source)
        self.assertRegex(label, r"^v1 · \d{4}-\d\d-\d\d · " + first[:8] + "$")
        self.assertEqual(run_record.register_prompt_version(self.fx.db, first, source), label)
        stored = self.fx.db.get(AgentPromptVersion, first)
        self.assertIn("{case_id}", stored.prompt_text["all"])

    def test_phone_generation_names_each_extraction(self):
        class Conn:
            def execute(self, *_a, **_k):
                class R:
                    def scalar(self):
                        return "e1:3,e2:none"
                return R()
        self.assertEqual(run_record.phone_generation(Conn(), "c"), "e1:3,e2:none")

    # -- B: opened vs not opened -----------------------------------------------------------------------------

    def test_opened_cited_and_not_examined_items_are_computed_by_code(self):
        def open_one(outputs):
            # A later call that names the row's key reads it further (the graph read fails here: no Neo4j).
            return "get_entity_details", {"entity_key": _first(outputs)["items"][0]["key"]}

        def answer(outputs):
            return "The payment %s is the one." % _first(outputs)["items"][1]["key"]

        with patch("services.agent.tools.graph_service.get_entity_details", side_effect=RuntimeError("no graph"),
                   create=True):
            result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 4}), open_one], answer)
        examined = run_record.examine(result["tool_trace"], answer=result["answer"], artifacts=[])
        first = [r for r in examined["items"] if r["tool_call_sequence"] == 1]
        self.assertEqual(len(first), 4)
        self.assertEqual((first[0]["opened"], first[0]["opened_by_sequence"]), (True, 2))
        self.assertEqual((first[1]["opened"], first[1]["cited"]), (False, True))
        self.assertEqual([r["opened"] or r["cited"] for r in first[2:]], [False, False])
        run = self.store(result)
        stored = self.fx.db.query(AgentRunItem).filter_by(run_id=run.id, tool_call_sequence=1).count()
        self.assertEqual(stored, 4)
        self.assertEqual(run.record_summary["items_not_examined"], 2)

    def test_model_paging_marks_items_not_shown_until_their_page_is_read(self):
        data = {"items": [{"key": "entity-%04d" % i, "name": "x" * 400} for i in range(60)], "count": 60}
        payload = tool_message_payload(result_id="res_1", summary="s", data=data, budget_chars=12_000)
        note = payload["_paging"][0]
        shown = note["returned"]
        self.assertLess(shown, 60)
        trace = [{"name": "search_graph_entities", "arguments": {"query": "x"},
                  "record": run_record.call_facts("search_graph_entities", {"query": "x"},
                                                  {"result_id": "res_1", "data": data}, payload)}]
        before = run_record.examine(trace, answer="", artifacts=[])
        self.assertEqual(sum(1 for r in before["items"] if not r["shown_to_model"]), 60 - shown)
        self.assertEqual(before["calls"][0]["model_not_shown"], 60 - shown)
        # The real page tool: its data is the page (items and its own _paging note), as tools.py returns it.
        from services.agent.model_payloads import model_view, page_for_model
        page = page_for_model(model_view(data), budget_chars=6_000, result_id="res_1", offset=shown,
                              path=["data", "items"])
        page_data = {"page_of": "res_1", **page}
        read = page["_paging"][0]["returned"]
        page_payload = tool_message_payload(result_id="res_2", summary="p", data=page_data, budget_chars=600_000)
        trace.append({"name": "read_tool_result_page",
                      "arguments": {"result_id": "res_1", "path": ["data", "items"], "offset": shown},
                      "record": run_record.call_facts("read_tool_result_page", {}, {"data": page_data},
                                                      page_payload)})
        after = run_record.examine(trace, answer="", artifacts=[])
        self.assertGreater(read, 0)
        self.assertEqual(after["calls"][0]["model_not_shown"], 60 - shown - read)
        self.assertEqual(sum(1 for r in after["items"] if not r["shown_to_model"]), 60 - shown - read)
        # The page's items are the first call's items: not listed a second time.
        self.assertEqual(len(after["items"]), 60)
        # Reading a page shows items; it does not count as opening them.
        self.assertFalse(any(r["opened"] for r in after["items"]))

    def test_continuation_pages_count_as_read(self):
        def page2(outputs):
            d = _first(outputs)
            return "get_financial_transactions", {"limit": 2, "offset": d["next_offset"],
                                                  "expected_revision": d["revision"]}
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2}), page2], lambda o: "ok")
        calls = run_record.examine(result["tool_trace"], answer="", artifacts=[])["calls"]
        self.assertEqual((calls[0]["tool_not_returned"], calls[1]["continuation_of"]), (1, 1))

    def test_budget_stopped_calls_are_recorded_as_not_run(self):
        steps = [lambda o: ("get_financial_coverage", {}), lambda o: ("get_financial_transactions", {"limit": 2})]
        result = self.run_agent(steps, lambda o: "", max_tool_calls=1)
        unrun = run_record.unrun_tool_calls(result["messages"])
        self.assertEqual([c["name"] for c in unrun], ["get_financial_transactions"])

    # -- C: exports --------------------------------------------------------------------------------------------

    def test_both_exports_list_exactly_the_clipped_and_unopened_items(self):
        from services.agent import run_record_export as rx
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2})],
                                lambda o: "Payment %s." % _first(o)["items"][0]["key"])
        run = self.store(result)
        strategy = rx.render_csv("strategy", rx.build_statement(self.fx.db, run, "strategy"))
        self.assertIn("get_financial_transactions", strategy)
        self.assertIn("not deterministic", strategy)
        self.assertIn("describes in words without its identifier", strategy)
        self.assertIn("v1 · 2026-11-03 · aaaaaaaa", strategy)
        statement = rx.not_examined_rows(rx.load_record(self.fx.db, run), material={}, phone_types=[])
        self.assertEqual(statement["counts"]["hits_not_opened"], 1)
        self.assertEqual(statement["counts"]["tool_paging_items"], 3)
        self.assertEqual([c["material"] for c in statement["categories"]][:1], [rx.CATEGORY_LABELS["graph"]])
        rows = list(csv.reader(io.StringIO(rx.render_csv("not_examined", statement))))
        self.assertIn(["Items returned but not opened, cited or used", "1"], rows)
        self.assertTrue(any("not deterministic" in " ".join(r) for r in rows))
        html_text = rx.render_html("not_examined", statement)
        self.assertIn("Material clipped by paging or by the tool budget (1)", html_text)

    def test_a_document_page_is_credited_only_where_that_page_is_named(self):
        chunk = lambda page: {"id": "chunk-%d" % page, "text": "t", "metadata": {
            "doc_name": "Statement March.pdf", "file_name": "Statement March.pdf", "page_start": page}}
        data = {"available": True, "chunks": [chunk(1), chunk(2), chunk(3)], "count": 3}
        trace = [{"name": "search_documents", "arguments": {"query": "rent"},
                  "record": run_record.call_facts("search_documents", {"query": "rent"}, {"data": data}, {})},
                 {"name": "build_table_artifact_from_rows", "arguments": {"rows": [{"source": "chunk-3"}]},
                  "record": run_record.call_facts("build_table_artifact_from_rows", {}, {"data": {}}, {})}]
        answer = "Rent was paid [Statement March.pdf, p.2](doc://Statement%20March.pdf/2); see Statement March.pdf."
        rows = run_record.examine(trace, answer=answer, artifacts=[{"rows": [{"source": "chunk-3"}]}])["items"]
        self.assertEqual([(r["ref"], r["cited"], r["opened"], r["in_artifact"]) for r in rows], [
            ("Statement March.pdf#p1", False, False, False),
            ("Statement March.pdf#p2", True, False, False),
            ("Statement March.pdf#p3", False, False, True)])

    def test_rows_without_an_identifier_are_counted_not_dropped(self):
        data = {"rows": [{"name": "a", "total": 3}, {"key": "entity-0001", "name": "b"}], "count": 2,
                "totals": [{"currency": "EUR"}]}
        facts = run_record.call_facts("run_readonly_cypher", {"query": "MATCH (n) RETURN n"}, {"data": data}, {})
        self.assertEqual((len(facts["items"]), facts["items_without_id"], facts["returned"]), (1, 1, 2))
        self.assertEqual(run_record.category_of("get_contact_and_money_between"), "phones")
        cross = run_record.call_facts("get_money_signal_matches", {}, {"data": {"items": [
            {"txn": "txn://abc123-def", "outcome": "matched"}], "total_matching": 1, "returned": 1}}, {})
        self.assertEqual([(i["kind"], i["ref"]) for i in cross["items"]], [("payment", "abc123-def")])

    def test_a_failed_search_is_not_counted_as_searched_and_is_listed_as_refused(self):
        # Live 2026-11-03, run e3a4a15d: search_documents raised a provider 429; the record said documents searched.
        facts = run_record.call_facts("search_documents", {"query": "rent"},
                                      {"summary": "failed", "data": {"error": "Error code: 429"}}, {})
        self.assertFalse(facts["available"])
        self.assertIn("429", facts["reason"])

    def test_case_search_document_and_phone_hits_are_followed(self):
        data = {"schema": "loupe.agent.phone_search_case/1", "items": [
            {"kind": "document", "title": "Stmt.pdf", "page": 3, "evidence_file_id": "51d805b9", "record_uid": None},
            {"kind": "message", "rec": "rec://0fca69af-2ac1", "record_uid": None}], "total_matching": 2, "returned": 2}
        facts = run_record.call_facts("search_case", {"query": "rent"}, {"data": data}, {})
        self.assertEqual([(i["kind"], i["ref"]) for i in facts["items"]],
                         [("document", "Stmt.pdf#p3"), ("phone_record", "0fca69af-2ac1")])
        self.assertEqual(facts["items_without_id"], 0)
        rows = run_record.examine([{"name": "search_case", "arguments": {}, "record": facts}],
                                  answer="See [Stmt.pdf, p.3](doc://51d805b9/3).", artifacts=[])["items"]
        self.assertTrue(rows[0]["cited"])

    def test_a_reference_is_not_credited_by_a_longer_one_it_starts(self):
        self.assertFalse(run_record._mentions("see doc://f.pdf/12 and [f.pdf, p.12]", "doc://f.pdf/1"))
        self.assertFalse(run_record._mentions("see [f.pdf, p.12]", "f.pdf, p.1"))
        self.assertFalse(run_record._mentions('{"entity_key": "john-smith-jr"}', "john-smith"))
        self.assertTrue(run_record._mentions('{"entity_key": "john-smith"}', "john-smith"))
        self.assertTrue(run_record._mentions("[f.pdf, p.1](doc://f.pdf/1).", "doc://f.pdf/1"))

    def test_earlier_runs_are_rebuilt_from_previews_and_say_so(self):
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2})], lambda o: "ok")
        db, user = self.fx.db, self.fx.user
        thread = storage.create_thread(db, user=user, case_id=self.fx.case.id, title="old")
        run = storage.create_run(db, thread=thread, user=user, provider="openai", model_id="m", input_message="q")
        run.for_user_email = None
        for item in result["tool_trace"]:
            item.pop("record")  # as stored before the run record
        storage.persist_tool_trace(db, run=run, trace=result["tool_trace"])
        storage.finish_run(db, run=run, status="completed", final_answer="ok")
        db.commit()
        summary = run_record.backfill_run(db, run)
        self.assertEqual(summary["items_returned"], 2)
        call = db.query(AgentToolCall).filter_by(run_id=run.id).one()
        self.assertEqual((call.total, call.returned, len(call.ledger_revision)), (5, 2, 64))
        self.assertIn("first 25 items", run.record_summary["basis"])
        self.assertEqual(run.for_user_email, user.email)
        self.assertEqual(run.prompt_version_label, "not recorded (run made before the run record)")
        self.assertIsNone(run_record.backfill_run(db, run))
        # --rebuild recomputes a preview-built record through the same path, and only those.
        db.commit()
        with patch("postgres.session._get_session_local", return_value=self.fx.SessionLocal):
            run_record.main(["--backfill", "--rebuild", "--apply"])
        db.expire_all()
        self.assertEqual(db.query(AgentRunItem).filter_by(run_id=run.id).count(), 2)
        self.assertIn("first 25 items", db.get(AgentRun, run.id).record_summary["basis"])

    def test_backfill_keeps_the_calls_a_killed_run_stored_as_it_ran(self):
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2})], lambda o: "ok")
        db, user = self.fx.db, self.fx.user
        thread = storage.create_thread(db, user=user, case_id=self.fx.case.id, title="killed")
        run = storage.create_run(db, thread=thread, user=user, provider="deepseek", model_id="m", input_message="q",
                                 tool_budget=28, prompt_version="b" * 64, prompt_version_label="v2 · x · bbbbbbbb")
        storage.persist_tool_call(db, run=run, sequence=1, item=result["tool_trace"][0])
        db.commit()
        run_record.backfill_run(db, run)
        call = db.query(AgentToolCall).filter_by(run_id=run.id).one()
        self.assertEqual((call.total, call.returned), (5, 2))
        self.assertEqual(run.prompt_version_label, "v2 · x · bbbbbbbb")
        self.assertIn("did not finish", run.record_summary["basis"])

    def test_withheld_phone_material_and_significant_scope_are_listed_out_of_scope(self):
        from services.agent import run_record_export as rx
        record = {"case_layer": "significant", "items": [], "unrun_tool_calls": [], "tool_calls_used": 1,
                  "tool_budget": 28, "for_user": {}, "run_id": "r", "case_id": "c", "status": "completed",
                  "provider": "p", "model_id": "m", "summary": {}, "calls": [{
                      "sequence": 1, "name": "phone_messages", "category": "phones", "available": True,
                      "withheld": {"count": 12, "what": "Messages on the victim's phone",
                                   "reason": "No external-processing decision", "reason_code":
                                   "external_processing_not_allowed", "decision_id": None},
                      "tool_not_returned": 0, "model_not_shown": 0, "items_not_listed": 0, "items_without_id": 0}]}
        st = rx.not_examined_rows(record, material={}, phone_types=[])
        whats = [r["what"] for r in st["scope"]]
        self.assertEqual(whats, ["Everything outside the Significant layer", "Messages on the victim's phone (12)"])
        self.assertIn("external_processing_not_allowed", st["scope"][1]["decision"])

    def test_case_material_not_held_is_not_listed_as_unsearched(self):
        from services.agent import run_record_export as rx
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 5})], lambda o: "ok")
        run = self.store(result)
        statement = rx.not_examined_rows(rx.load_record(self.fx.db, run),
                                         material={"phones": {"count": 0, "unit": "phone extractions"},
                                                   "documents": {"count": 3, "unit": "evidence files"}},
                                         phone_types=[])
        names = [c["material"] for c in statement["categories"]]
        self.assertNotIn(rx.CATEGORY_LABELS["phones"], names)
        self.assertNotIn(rx.CATEGORY_LABELS["ledger"], names)
        self.assertIn(rx.CATEGORY_LABELS["documents"], names)

    # -- D: retention ------------------------------------------------------------------------------------------

    def test_removing_a_person_cannot_cascade_away_run_records(self):
        fk = next(iter(AgentThread.__table__.c.owner_user_id.foreign_keys))
        self.assertEqual(fk.ondelete, "RESTRICT")
        run_fk = next(iter(AgentRun.__table__.c.user_id.foreign_keys))
        self.assertEqual(run_fk.ondelete, "SET NULL")


class RunRecordServiceTests(RunRecordFixture):
    """The streamed service path: each call is stored as it runs; a run that fails keeps its calls."""

    def stream_service(self, events, usage=None):
        from types import SimpleNamespace
        from services.agent import service as svc
        from services.agent.schemas import AgentMessageRequest

        class FakeRunner:
            def __init__(self, **_k):
                pass

            def spent_so_far(self):
                return usage

            def stream(self, **_k):
                for event in events:
                    if isinstance(event, Exception):
                        raise event
                    yield event

        mandate = SimpleNamespace(override=None, block="")
        with patch.object(svc, "check_case_access"), \
                patch.object(svc, "get_workload_model", return_value=("deepseek", "deepseek-v4-pro")), \
                patch.object(svc, "get_provider_api_key", return_value="k"), \
                patch.object(svc, "AgentGraphRunner", FakeRunner), \
                patch.object(svc.mandate_context_service, "resolve", return_value=mandate), \
                patch.object(svc.mandate_context_service, "active_version", return_value=None), \
                patch.object(svc.system_log_service, "log"), \
                patch.object(svc.storage, "check_case_access"):
            request = AgentMessageRequest(message="Which payments?", case_id=self.fx.case.id)
            return list(svc.agent_service.stream_message(db=self.fx.db, user=self.fx.user, request=request))

    def test_failed_run_keeps_its_calls_and_browser_events_omit_the_record(self):
        result = self.run_agent([lambda o: ("get_financial_transactions", {"limit": 2})], lambda o: "ok")
        tool = result["tool_trace"][0]
        out = self.stream_service([{"type": "tool_result", "tool": tool}, RuntimeError("provider went away")])
        sent = [e for e in out if e["type"] == "tool_result"][0]["tool"]
        self.assertNotIn("record", sent)
        self.assertEqual(out[-1]["type"], "error")
        run = self.fx.db.query(AgentRun).one()
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.tool_calls_used, 1)
        self.assertTrue(run.prompt_version_label.startswith("v1 · "))
        self.assertEqual(len(run.prompt_version), 64)
        call = self.fx.db.query(AgentToolCall).filter_by(run_id=run.id).one()
        self.assertEqual((call.total, call.returned), (5, 2))
        self.assertEqual(self.fx.db.query(AgentRunItem).filter_by(run_id=run.id).count(), 2)

    def test_a_spend_record_error_still_marks_the_failed_run_failed(self):
        from services.agent import service as svc
        def boom(**_k):
            raise RuntimeError("cost table unavailable")

        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        with patch.object(svc, "record_cost", side_effect=boom), self.assertLogs(svc.logger, level="ERROR"):
            out = self.stream_service([RuntimeError("provider went away")], usage=usage)
        self.assertEqual(out[-1]["type"], "error")
        run = self.fx.db.query(AgentRun).one()
        self.assertEqual(run.status, "failed")
        self.assertIn("provider went away", run.error or "")


if __name__ == "__main__":
    unittest.main()
