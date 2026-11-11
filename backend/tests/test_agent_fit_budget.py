"""lx-agentfit B: reading results again does not use up the investigative budget, the agent keeps working notes, a
second whole re-read of one result is refused with its digest, and a wrong page path is answered with the right one.

Measured 11 Nov 2026 on the demo case (b75f3f2c, 11 runs, 258 calls): 66 whole-result re-reads and 28 page reads,
7 of 11 runs stopped at the 28-call budget; Q4 spent calls 16 to 28 re-reading results. Every test here fails on the
code before this change."""
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from services.agent import graph
from services.agent.graph import AgentGraphRunner
from services.agent.tools import AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-0000000000ab"


class Args(BaseModel):
    pass


def big(i):
    return {"rows": [{"k": i, "j": j, "t": "x" * 300} for j in range(20)], "count": 20}


class Script:
    """A scripted model: each turn returns the calls ``plan(turn, messages)`` gives, then a draft."""

    def __init__(self, plan):
        self.plan, self.turn, self.requests = plan, 0, []

    def bind_tools(self, tools):
        owner = self

        class Bound:
            def invoke(self, messages):
                owner.requests.append(list(messages))
                calls, owner.turn = owner.plan(owner.turn, messages), owner.turn + 1
                return AIMessage(content="", tool_calls=calls) if calls else AIMessage(content="Draft.")
        return Bound()

    def invoke(self, messages):
        return AIMessage(content="Final answer.")


def tools_with_search(context):
    counter = {"n": 0}

    def search():
        counter["n"] += 1
        return context.result("search", big(counter["n"]), summary="Found 20.")
    real = [t for t in make_agent_tools(context) if t.name in ("read_tool_result_page", "record_working_notes")]
    return [StructuredTool.from_function(func=search, name="search", description="Stub.", args_schema=Args)] + real


def run(plan, budget):
    model = Script(plan)
    runner = object.__new__(AgentGraphRunner)
    runner.base_model, runner.model_id, runner.provider = model, "deepseek-v4-pro", "deepseek"
    with patch("services.agent.graph.make_agent_tools", side_effect=tools_with_search):
        result = runner.invoke(case_id=CASE, messages=[HumanMessage(content="Q?")], max_tool_calls=budget)
    return result, model


def first_result_id(messages):
    for m in messages:
        if isinstance(m, ToolMessage) and m.name == "search":
            p = json.loads(m.content)
            return p.get("result_id") or p.get("digest_of")


def call(i, name, **args):
    return {"id": "c%d_%s" % (i, name), "name": name, "args": args}


class BudgetTests(unittest.TestCase):
    def test_reading_again_does_not_use_the_investigative_budget(self):
        # 3 searches with a budget of 3, and a page read and a notes call between them: old code stopped at the
        # budget before the third search (5 calls counted against 3).
        def plan(turn, messages):
            rid = first_result_id(messages)
            return {0: [call(0, "search")],
                    1: [call(1, "read_tool_result_page", result_id=rid, path=["data", "rows"], offset=5),
                        call(1, "record_working_notes", facts=[{"fact": "k is 1", "cite": "rec://a"}])],
                    2: [call(2, "search")], 3: [call(3, "search")]}.get(turn, [])
        result, model = run(plan, 3)
        self.assertEqual([t["name"] for t in result["tool_trace"]].count("search"), 3)
        self.assertIsNone(result.get("clarification"))

    def test_free_calls_have_their_own_cap_and_a_looping_run_still_ends(self):
        def plan(turn, messages):
            rid = first_result_id(messages)
            return [call(0, "search")] if turn == 0 else \
                [call(turn, "read_tool_result_page", result_id=rid, path=["data", "rows"], offset=turn % 20)]
        result, model = run(plan, 3)
        trace = result["tool_trace"]
        # free calls up to the cap, then each refused call counts: 1 search + 16 free + 2 charged refusals = 19.
        self.assertEqual(len(trace), 1 + graph.FREE_CALL_CAP + 2)
        self.assertIn("not run", trace[-1]["summary"])

    def test_notes_stay_whole_on_every_later_turn(self):
        def plan(turn, messages):
            return {0: [call(0, "search"), call(0, "record_working_notes",
                                                facts=[{"fact": "Payment of 500 on 3 May", "cite": "txn://t1"}])],
                    1: [call(1, "search")], 2: [call(2, "search")]}.get(turn, [])
        result, model = run(plan, 10)
        last = model.requests[-1]
        notes = [m for m in last if isinstance(m, ToolMessage) and m.name == "record_working_notes"]
        self.assertEqual(len(notes), 1)
        payload = json.loads(notes[0].content)
        self.assertNotIn("digest_of", payload)
        self.assertEqual(payload["data"]["noted"][0]["cite"], "txn://t1")
        # the search result of turn 0 is a digest by now
        searches = [json.loads(m.content) for m in last if isinstance(m, ToolMessage) and m.name == "search"]
        self.assertIn("digest_of", searches[0])


class PageToolTests(unittest.TestCase):
    def tool(self):
        context = AgentToolContext(case_id=CASE, page_budget_chars=100_000)
        context.model_views["res_1"] = {"data": {"rows": [{"k": i, "t": "z" * 100} for i in range(25)], "count": 25}}
        return context, {t.name: t for t in make_agent_tools(context)}["read_tool_result_page"]

    def test_a_second_whole_re_read_is_refused_with_the_digest(self):
        context, tool = self.tool()
        first = tool.invoke({"result_id": "res_1"})
        self.assertEqual(len(first["data"]["data"]["rows"]), 25)
        # re-reading the re-read is the same result
        second = tool.invoke({"result_id": first["result_id"]})
        self.assertEqual(second["data"]["not_read_again"], "res_1")
        self.assertIn("working notes", second["summary"])
        self.assertEqual(second["data"]["digest"]["facts"]["count"], 25)
        self.assertNotIn("rows", json.dumps(second["data"]["digest"].get("facts")))

    def test_a_path_without_its_root_reads_the_right_page(self):
        context, tool = self.tool()
        out = tool.invoke({"result_id": "res_1", "path": ["rows"], "offset": 2})
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["data"]["items"][0]["k"], 2)
        self.assertEqual(out["data"]["path_used"], ["data", "rows"])

    def test_a_wrong_path_lists_the_right_paths(self):
        context, tool = self.tool()
        out = tool.invoke({"result_id": "res_1", "path": ["data", "items"]})
        self.assertEqual(out["status"], "success")
        self.assertIn({"path": ["data", "rows"], "items": 25}, out["data"]["paths"])


if __name__ == "__main__":
    unittest.main()
