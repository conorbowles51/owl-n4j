"""Real ledger tools through both agent runners, with a deterministic fake model.

Only the provider and session factory are replaced. All records are synthetic;
the service reads committed SQL state and the model consumes actual ToolMessages.
"""
from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import event

from services.agent.graph import AgentGraphRunner
from services.financial.transactions import LOCATOR_PROVENANCE_KEY
from tests import test_agent_financial_ledger_tools as ledger_fixture


class ScriptedFinancialModel:
    def __init__(self, steps):
        self.steps = steps
        self.outputs = {}
        self.finalizer_messages = []
        self.names = set()
        self.schemas = {}
        self.index = 0

    def record(self, messages):
        for message in messages:
            if isinstance(message, ToolMessage):
                self.outputs[message.tool_call_id] = json.loads(message.content)

    def bind_tools(self, tools):
        self.names = {tool.name for tool in tools}
        self.schemas = {tool.name: tool.args_schema.model_fields for tool in tools}
        owner = self

        class Bound:
            def invoke(self, messages):
                owner.record(messages)
                if owner.index == len(owner.steps):
                    return AIMessage(content="The saved payment analysis is complete within the returned scope.")
                step = owner.steps[owner.index]
                owner.index += 1
                name, arguments = step(owner.outputs)
                return AIMessage(content="", tool_calls=[{
                    "id": f"financial-step-{owner.index}", "name": name, "args": arguments,
                }])

        return Bound()

    def invoke(self, messages):
        self.record(messages)
        self.finalizer_messages = messages
        return AIMessage(content="Analysis covers the current imported payment population. Currency and bank/card totals are separate; missing or unprocessed evidence remains outside this result.")


class AgentFinancialJourneyTests(unittest.TestCase):
    def fixture(self):
        fixture = ledger_fixture.FinancialAgentLedgerTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def run_agent(self, fixture, path, steps, *, significant=False, unavailable=False):
        model = ScriptedFinancialModel(steps)
        runner = object.__new__(AgentGraphRunner)
        runner.base_model = model
        opened = []

        @contextmanager
        def read_session(*_args, **_kwargs):
            opened.append(True)
            if unavailable:
                raise RuntimeError("synthetic private SQL connection failure")
            with fixture.SessionLocal() as session:
                yield session
                self.assertFalse(session.new or session.dirty or session.deleted)

        kwargs = dict(case_id=str(fixture.case.id),
            messages=[HumanMessage(content="Analyse all imported payments and show the supporting records.")],
            allowed_entity_keys=["synthetic-significant-node"] if significant else None)
        with patch("services.agent.tools._financial_session", read_session), patch(
            "services.agent.tools.financial_service.get_financial_transactions",
            side_effect=AssertionError("Relational ledger analysis must never fall back to graph payments"),
        ) as graph:
            if path == "invoke":
                result = runner.invoke(**kwargs)
            else:
                events = list(runner.stream(**kwargs))
                result = events[-1]["result"]
                self.assertTrue(any(e["type"] == "activity" for e in events))
            graph.assert_not_called()
        self.assertTrue({"get_financial_transactions", "get_financial_coverage",
            "analyze_financial_transactions"}.issubset(model.names))
        return model, result, opened

    def test_full_case_aggregates_and_all_bounded_rows_reach_both_models(self):
        for path in ("invoke", "stream"):
            with self.subTest(path=path):
                fixture = self.fixture()
                _, period, bank_rows = fixture.source(rows=121, amount=9007199254740993)
                fixture.source(fixture.card, currency="USD", rows=11, amount=10)
                fixture.source(fixture.card, currency="EUR", rows=3, amount=20)
                fixture.source(fixture.quiet)
                bank_rows[0].provenance = {LOCATOR_PROVENANCE_KEY: {"kind": "page_only", "page": 7}}
                fixture.db.commit()
                sql = []

                def record(_connection, _cursor, statement, *_args):
                    sql.append(statement)

                steps = [
                    lambda _: ("get_financial_coverage", {}),
                    lambda outputs: ("analyze_financial_transactions", {"group_by": "account",
                        "expected_ledger_revision": outputs["financial-step-1"]["data"]["ledger_revision"]}),
                    lambda outputs: ("get_financial_transactions", {"limit": 100,
                        "expected_ledger_revision": outputs["financial-step-1"]["data"]["ledger_revision"]}),
                    lambda outputs: ("get_financial_transactions", {
                        "limit": 100, "offset": outputs["financial-step-3"]["data"]["next_offset"],
                        "expected_revision": outputs["financial-step-3"]["data"]["revision"],
                    }),
                ]
                event.listen(fixture.engine, "before_cursor_execute", record)
                try:
                    model, result, opened = self.run_agent(fixture, path, steps)
                finally:
                    event.remove(fixture.engine, "before_cursor_execute", record)
                self.assertEqual(len(opened), 4)
                self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in sql))
                self.assertTrue(all(item["status"] == "success" for item in result["tool_trace"]))
                first, last = (model.outputs[f"financial-step-{i}"]["data"] for i in (3, 4))
                self.assertEqual((first["total_matching"], first["returned"], last["returned"]), (135, 100, 35))
                self.assertEqual((len(first["items"]), len(last["items"])), (100, 35))
                self.assertFalse(last["has_more"])
                self.assertIsNone(last["next_offset"])
                rows = first["items"] + last["items"]
                self.assertEqual(len({row["transaction_id"] for row in rows}), 135)
                self.assertEqual({row["transaction_id"] for row in rows if row["statement_period_id"] == str(period.id)}, {str(row.id) for row in bank_rows})
                self.assertEqual(first["totals"], last["totals"])
                self.assertEqual(len({output["data"]["ledger_revision"] for output in model.outputs.values()}), 1)
                totals = {(row["currency"], row["account_type"]): row for row in first["totals"]}
                self.assertEqual(set(totals), {("EUR", "bank"), ("EUR", "credit_card"), ("USD", "credit_card")})
                self.assertEqual(totals["EUR", "bank"]["credits_minor"], str(sum(9007199254740993 + i for i in range(0, 121, 2))))
                grouped = model.outputs["financial-step-2"]["data"]
                self.assertEqual(sum(group["transaction_count"] for group in grouped["items"]), 135)
                coverage = model.outputs["financial-step-1"]["data"]["coverage"]
                self.assertEqual(coverage["registered_accounts"], 3)
                self.assertEqual(coverage["registered_accounts_without_matching_payments"], 1)
                for row in rows:
                    self.assertIsInstance(row["amount_minor"], str)
                    self.assertEqual(row["case_id"], str(fixture.case.id))
                    self.assertIn(f"/cases/{fixture.case.id}/evidence?file=", row["source"]["evidence_href"])
                    self.assertEqual(row["source"]["source_document_id"], row["source_document_id"])
                    self.assertIn("locator", row)
                located = next(row for row in rows if row["transaction_id"] == str(bank_rows[0].id))
                self.assertEqual(located["locator"], {"kind": "page_only", "page": 7})
                final_pages = [json.loads(message.content)["data"] for message in model.finalizer_messages
                    if isinstance(message, ToolMessage) and message.name == "get_financial_transactions"]
                self.assertEqual([len(page["items"]) for page in final_pages], [100, 35])

    def test_saved_correction_invalidates_continuation_then_fresh_query_sees_it(self):
        from services.financial.payment_labels import PaymentLabelsRequest, update_payment_labels

        for path in ("invoke", "stream"):
            with self.subTest(path=path):
                fixture = self.fixture()
                _, _, rows = fixture.source(rows=3)

                def change_then_continue(outputs):
                    update_payment_labels(fixture.db, case_id=fixture.case.id, actor=fixture.actor,
                        request=PaymentLabelsRequest(transactions=[{"id": rows[0].id, "version": 0}],
                            category="Investigator reviewed", from_name="Reviewed synthetic sender"))
                    return "get_financial_transactions", {
                        "limit": 1, "offset": 1,
                        "expected_revision": outputs["financial-step-1"]["data"]["revision"],
                    }

                model, result, _ = self.run_agent(fixture, path, [
                    lambda _: ("get_financial_transactions", {"limit": 1}),
                    change_then_continue,
                    lambda _: ("get_financial_transactions", {"categories": ["Investigator reviewed"]}),
                ])
                stale = model.outputs["financial-step-2"]["data"]
                self.assertFalse(stale["available"])
                self.assertEqual(stale["reason_code"], "stale_revision")
                self.assertEqual(stale["items"], [])
                self.assertEqual(stale["totals"], [])
                self.assertIsNone(stale["total_matching"])
                fresh = model.outputs["financial-step-3"]["data"]
                self.assertTrue(fresh["available"])
                self.assertEqual(fresh["total_matching"], 1)
                self.assertEqual(fresh["items"][0]["transaction_id"], str(rows[0].id))
                self.assertEqual(fresh["items"][0]["from_name"], "Reviewed synthetic sender")
                self.assertEqual(result["tool_trace"][1]["status"], "error")

    def test_significant_and_unavailable_fail_closed_without_graph_fallback(self):
        for path in ("invoke", "stream"):
            for significant in (False, True):
                with self.subTest(path=path, significant=significant):
                    fixture = self.fixture()
                    fixture.source(rows=1)
                    model, result, opened = self.run_agent(fixture, path, [
                        lambda _: ("get_financial_coverage", {}),
                        lambda _: ("get_financial_transactions", {}),
                        lambda _: ("analyze_financial_transactions", {}),
                    ], significant=significant, unavailable=not significant)
                    self.assertEqual(len(opened), 0 if significant else 3)
                    self.assertTrue(all(item["status"] == "error" for item in result["tool_trace"]))
                    for output in model.outputs.values():
                        self.assertNotIn("synthetic private SQL connection failure", json.dumps(output))
                        self.assertNotIn(str(fixture.account.id), json.dumps(output))
                        if significant:
                            self.assertIn("Significant", output["summary"])

    def test_model_supplied_foreign_identifiers_cannot_expand_the_authorized_case(self):
        for path in ("invoke", "stream"):
            with self.subTest(path=path):
                fixture = self.fixture()
                fixture.source(rows=2)
                foreign_document = fixture.make_document(case=fixture.other_case, run=fixture.other_run)
                foreign_period = fixture.make_period(foreign_document, account=fixture.other_account,
                    run=fixture.other_run)
                foreign_row = fixture.add_row(foreign_period, foreign_document,
                    account=fixture.other_account, run=fixture.other_run, amount=7777777)
                model, result, _ = self.run_agent(fixture, path, [
                    lambda _: ("get_financial_transactions", {"case_id": str(fixture.other_case.id)}),
                    lambda _: ("get_financial_transactions", {"account_ids": [str(fixture.other_account.id)]}),
                    lambda _: ("get_financial_transactions", {"source_document_id": str(foreign_document.id)}),
                ])
                self.assertEqual([output["data"]["total_matching"] for output in model.outputs.values()], [2, 0, 0])
                self.assertTrue(all(item["status"] == "success" for item in result["tool_trace"]))
                for output in model.outputs.values():
                    self.assertEqual(output["data"]["case_id"], str(fixture.case.id))
                    self.assertNotIn(str(foreign_row.id), json.dumps(output))
                for name in ("get_financial_transactions", "get_financial_coverage", "analyze_financial_transactions"):
                    self.assertNotIn("case_id", model.schemas[name])


if __name__ == "__main__":
    unittest.main()
