"""lx-agentfit R3 (item W): the answer written at the tool limit keeps the sources of what the run found.

Measured 11 Nov 2026 on BNB2 replays that stopped at the limit: a record lookup's answer went from 24 cited sources to
1 and a build request's from 12 to 1, while the results read still held every row's link. Each test fails on the code
before this change (no list of found records in the finalizer's request, no records listed under the answer)."""
import os
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from services.agent import wrap_up
from services.agent.graph import KEPT_SOURCES_HEADING, AgentGraphRunner

CASE = "00000000-0000-0000-0000-0000000000ac"
ROW = "11111111-2222-3333-4444-555555555555"
OTHER = "11111111-2222-3333-4444-666666666666"


class Args(BaseModel):
    pass


def ledger(i):
    return {"items": [
        {"key": ROW, "cite": "txn://" + ROW, "transaction_date": "2024-05-22", "amount_minor": "138000000",
         "currency": "MXN", "currency_exponent": 2, "description": "PRESTAMO CLANA"},
        {"key": OTHER, "cite": "txn://" + OTHER, "transaction_date": "2024-06-01", "amount_minor": "99999",
         "currency": "MXN", "currency_exponent": 2, "description": "OTHER"},
    ], "total": 2}


class Script:
    """Asks for one ledger read per turn until the limit; the finalizer answers with a figure and no link."""

    def __init__(self):
        self.final_requests = []

    def bind_tools(self, tools):
        class Bound:
            def invoke(self, messages):
                return AIMessage(content="", tool_calls=[{"name": "ledger", "args": {}, "id": "c%d" % len(messages)}])
        return Bound()

    def invoke(self, messages):
        self.final_requests.append(list(messages))
        return AIMessage(content="CLANA paid 1,380,000.00 MXN on 22/05/2024.")


def tools(context):
    def read():
        return context.result("ledger", ledger(1), summary="2 rows.")
    return [StructuredTool.from_function(func=read, name="ledger", description="Stub.", args_schema=Args)]


def run(env):
    model = Script()
    runner = object.__new__(AgentGraphRunner)
    runner.base_model, runner.model_id, runner.provider = model, "deepseek-v4-pro", "deepseek"
    with patch.dict(os.environ, env), patch("services.agent.graph.make_agent_tools", side_effect=tools), \
            patch("services.agent.graph.call_facts", side_effect=lambda name, args, output, payload: {
                "items": [{"kind": "payment", "ref": i["key"], "alts": [i["cite"]], "label": i["description"]}
                          for i in output["data"]["items"]]}):
        result = runner.invoke(case_id=CASE, messages=[HumanMessage(content="Who paid?")], max_tool_calls=2)
    return result, model


class LimitAnswerTests(unittest.TestCase):
    def test_a_figure_the_limit_answer_states_gets_the_record_that_carries_it(self):
        result, model = run({"LOUPE_AGENT_FIT": "W"})
        self.assertEqual((result["clarification"] or {}).get("context", {}).get("reason"), "tool_budget_exhausted")
        self.assertIn(KEPT_SOURCES_HEADING, result["answer"])
        self.assertIn("(txn://%s)" % ROW, result["answer"])
        self.assertNotIn(OTHER, result["answer"])  # a record whose figure the answer does not state is not listed

    def test_the_finalizer_at_the_limit_is_given_each_found_record_with_its_link(self):
        _, model = run({"LOUPE_AGENT_FIT": "W"})
        last = model.final_requests[-1][-1].content
        self.assertIn("Records found so far", last)
        self.assertIn("PRESTAMO CLANA: txn://" + ROW, last)

    def test_with_w_off_the_answer_is_left_as_written(self):
        result, model = run({"LOUPE_AGENT_FIT": ""})
        self.assertNotIn(KEPT_SOURCES_HEADING, result["answer"])
        self.assertNotIn("Records found so far", model.final_requests[-1][-1].content)


class KeepSourcesTests(unittest.TestCase):
    views = {"res_1": {"data": ledger(1)}}

    def test_a_record_the_answer_already_links_is_not_listed_again(self):
        text = "Paid 1,380,000.00 MXN [22 May](txn://%s)." % ROW
        kept, counts = wrap_up.keep_sources(text, self.views, heading="H")
        self.assertEqual(kept, text)
        self.assertEqual(counts["listed"], 0)

    def test_a_short_figure_is_never_matched(self):
        kept, counts = wrap_up.keep_sources("It cost 999.99 MXN.", self.views, heading="H")
        self.assertEqual(counts["figures"], 0)

    def test_a_figure_many_records_carry_lists_three_and_counts_the_rest(self):
        rows = [{"cite": "txn://%032d" % i, "amount_minor": "500000", "currency_exponent": 2} for i in range(5)]
        kept, counts = wrap_up.keep_sources("Five payments of 5,000.00.", {"r": {"data": {"items": rows}}},
                                            heading="H")
        self.assertEqual(counts["listed"], wrap_up.MAX_PER_FIGURE)
        self.assertEqual(counts["not_listed"], 5 - wrap_up.MAX_PER_FIGURE)
        self.assertIn("2 more records carry these figures and are not listed.", kept)


if __name__ == "__main__":
    unittest.main()
