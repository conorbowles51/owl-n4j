"""What the model reads of each tool result (lx-agent item B): the whole result when it fits, otherwise a page that
states total, returned and next_page, with the rest readable through read_tool_result_page. There is no fixed
20-item cut, and no payload loses its totals. Each test failed on the code that cut every list to 20 items."""
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.agent.graph import AgentGraphRunner
from services.agent.model_payloads import (
    MIN_MESSAGE_CHARS,
    message_budget_chars,
    page_for_model,
    run_budget_chars,
    tool_message_payload,
)
from services.agent.tools import AgentToolContext, make_agent_tools

ROWS = [{"key": f"entity-{index:02d}", "name": f"Synthetic entity {index}", "note": "x" * 900} for index in range(25)]


class ScriptedModel:
    """Calls the scripted tools in order, then answers; records every tool message it was sent."""

    def __init__(self, steps):
        self.steps, self.index, self.seen = steps, 0, {}

    def _record(self, messages):
        for message in messages:
            if isinstance(message, ToolMessage):
                self.seen[message.tool_call_id] = json.loads(message.content)

    def bind_tools(self, tools):
        owner = self

        class Bound:
            def invoke(self, messages):
                owner._record(messages)
                if owner.index == len(owner.steps):
                    return AIMessage(content="Done.")
                name, arguments = owner.steps[owner.index](owner.seen)
                owner.index += 1
                return AIMessage(content="", tool_calls=[{"id": f"step-{owner.index}", "name": name, "args": arguments}])

        return Bound()

    def invoke(self, messages):
        self._record(messages)
        return AIMessage(content="Done.")


def run(steps, *, model_id="deepseek-v4-pro"):
    model = ScriptedModel(steps)
    runner = object.__new__(AgentGraphRunner)
    runner.base_model, runner.model_id = model, model_id
    with patch("services.agent.tools.run_readonly_cypher", return_value=[dict(row) for row in ROWS]):
        runner.invoke(case_id="00000000-0000-0000-0000-0000000000aa", messages=[HumanMessage(content="List them.")])
    return model.seen


CYPHER = ("run_readonly_cypher", {"query": "MATCH (n {case_id: $case_id}) RETURN n.key AS key LIMIT 25", "limit": 25})


class ModelPayloadTests(unittest.TestCase):
    def test_twenty_five_rows_reach_the_model_whole(self):
        seen = run([lambda _: CYPHER])
        message = seen["step-1"]
        self.assertEqual(len(message["data"]["rows"]), 25)
        self.assertEqual(message["data"]["count"], 25)
        self.assertNotIn("_paging", message)

    def test_a_result_larger_than_the_budget_is_paged_with_stated_totals(self):
        page = tool_message_payload(result_id="res_1", summary="25 rows.", data={"rows": ROWS, "count": 25},
                                    budget_chars=MIN_MESSAGE_CHARS)
        note = page["_paging"][0]
        self.assertEqual(note["path"], ["data", "rows"])
        self.assertEqual(note["total"], 25)
        self.assertEqual(note["returned"], len(page["data"]["rows"]))
        self.assertLess(note["returned"], 25)
        self.assertEqual(note["next_page"], {"tool": "read_tool_result_page", "result_id": "res_1",
                                             "path": ["data", "rows"], "offset": note["returned"]})
        self.assertIn(f"Showing {note['returned']} of 25", note["message"])
        self.assertIn("shown in part", page["summary"])
        # The envelope is a record, never cut: its count stays.
        self.assertEqual(page["data"]["count"], 25)

    def test_the_page_tool_returns_the_rest_and_every_item_is_read_once(self):
        context = AgentToolContext(case_id="00000000-0000-0000-0000-0000000000aa", page_budget_chars=MIN_MESSAGE_CHARS)
        context.model_views["res_1"] = {"data": {"rows": ROWS, "count": 25}}
        tool = {t.name: t for t in make_agent_tools(context)}["read_tool_result_page"]
        first = tool_message_payload(result_id="res_1", summary="", data={"rows": ROWS, "count": 25},
                                     budget_chars=MIN_MESSAGE_CHARS)
        keys = [row["key"] for row in first["data"]["rows"]]
        offset = first["_paging"][0]["next_page"]["offset"]
        while offset is not None:
            data = tool.invoke({"result_id": "res_1", "path": ["data", "rows"], "offset": offset})["data"]
            keys += [row["key"] for row in data["items"]]
            note = data["_paging"][0]
            self.assertEqual(note["total"], 25)
            offset = note["next_page"]["offset"] if note.get("next_page") else None
        self.assertEqual(keys, [row["key"] for row in ROWS])

    def test_the_runner_pages_when_the_run_budget_is_spent_and_the_model_reads_the_rest(self):
        # An unrecorded model gets the conservative 128k-token budget; fill it, then a 25-row result must page.
        big = [{"key": f"big-{index}", "text": "y" * 1000} for index in range(300)]
        rows_by_call = iter([big, big, ROWS])

        def cypher(*_args, **_kwargs):
            return [dict(row) for row in next(rows_by_call)]

        model = ScriptedModel([
            lambda _: CYPHER, lambda _: CYPHER, lambda _: CYPHER,
            lambda seen: ("read_tool_result_page", {key: seen["step-3"]["_paging"][0]["next_page"][key]
                                                    for key in ("result_id", "path", "offset")}),
        ])
        runner = object.__new__(AgentGraphRunner)
        runner.base_model, runner.model_id = model, "an-unrecorded-model"
        with patch("services.agent.tools.run_readonly_cypher", side_effect=cypher):
            runner.invoke(case_id="00000000-0000-0000-0000-0000000000aa", messages=[HumanMessage(content="List.")])
        third, rest = model.seen["step-3"], model.seen["step-4"]
        note = third["_paging"][0]
        self.assertEqual((note["total"], note["returned"] + note["remaining"]), (25, 25))
        self.assertEqual(rest["data"]["_paging"][0]["offset"], note["returned"])
        self.assertEqual([row["key"] for row in third["data"]["rows"] + rest["data"]["items"]][:25],
                         [row["key"] for row in ROWS][:note["returned"] + len(rest["data"]["items"])])

    def test_no_payload_drops_its_total_or_keys(self):
        data = {"total": 900, "count": 900, "next_cursor": "abc", "events": [{"id": i, "t": "z" * 200} for i in range(900)],
                "labels": {f"L{i}": {"count": i, "properties": {f"p{j}": j for j in range(30)}} for i in range(40)}}
        page = page_for_model(data, budget_chars=MIN_MESSAGE_CHARS)
        self.assertEqual({key for key in data}, {key for key in page} - {"_paging"})
        self.assertEqual((page["total"], page["count"], page["next_cursor"]), (900, 900, "abc"))
        for note in page["_paging"]:
            if "total" in note:
                self.assertEqual(note["returned"] + note["remaining"], note["total"] - note["offset"])

    def test_the_paging_notes_count_toward_the_budget(self):
        # Forty lists each cut to fit: the notes stating their totals are part of the message the model reads.
        data = {f"list{i:02d}": [{"k": j, "t": "z" * 200} for j in range(30)] for i in range(40)}
        for budget in (30_000, 60_000):
            with self.subTest(budget=budget):
                page = page_for_model(data, budget_chars=budget)
                self.assertLessEqual(len(json.dumps(page, ensure_ascii=False, separators=(",", ":"))), budget)
                for note in page["_paging"]:
                    self.assertEqual((note["total"], note["returned"] + note["remaining"]), (30, 30))

    def test_the_whole_tool_message_fits_its_budget(self):
        # The summary and ids around a page are part of what the model reads.
        rows = [{"key": f"r{i}", "t": "z" * 2000} for i in range(40)]
        for budget in (MIN_MESSAGE_CHARS, 20_000, 40_000):
            with self.subTest(budget=budget):
                message = tool_message_payload(result_id="res_0123456789", summary="Forty rows. " * 200,
                                               data={"rows": rows, "count": 40}, budget_chars=budget)
                self.assertIn("_paging", message)
                self.assertLessEqual(len(json.dumps(message, ensure_ascii=False, separators=(",", ":"))), budget)

    def test_inspected_properties_are_not_cut_at_twenty(self):
        schema = {"labels": {"FinancialTransaction": {"count": 5, "properties": {f"p{i}": {"type": "str"} for i in range(32)}}}}
        page = tool_message_payload(result_id="r", summary="", data=schema)
        self.assertEqual(len(page["data"]["labels"]["FinancialTransaction"]["properties"]), 32)

    def test_budget_follows_the_models_context_window(self):
        self.assertEqual(run_budget_chars(1_000_000), 1_800_000)
        self.assertEqual(run_budget_chars(None), run_budget_chars(128_000))
        self.assertEqual(message_budget_chars(100_000, 99_000), MIN_MESSAGE_CHARS)

    def test_claude_and_gemini_models_page_on_their_recorded_context_window(self):
        # Anthropic's and Google's published input limits; unrecorded, they fell back to 128k tokens.
        from services.agent.model_payloads import context_window_for
        expected = {"claude-sonnet-5": 1_000_000, "claude-opus-4-8": 1_000_000, "claude-haiku-4-5": 200_000,
                    "gemini-3.6-flash": 1_048_576, "gemini-3.5-flash": 1_048_576, "gemini-3.5-flash-lite": 1_048_576}
        self.assertEqual({model: context_window_for(model) for model in expected}, expected)


class MapTotalTests(unittest.TestCase):
    def test_map_locations_state_total_and_next_offset(self):
        locations = [{"key": f"place-{i}", "latitude": 1.0, "longitude": 2.0} for i in range(75)]
        context = AgentToolContext(case_id="00000000-0000-0000-0000-0000000000aa")
        tools = {t.name: t for t in make_agent_tools(context)}
        with patch("services.agent.tools.geo_service.get_entities_with_locations", return_value=locations):
            first = tools["get_map_locations"].invoke({"limit": 50})["data"]
            second = tools["get_map_locations"].invoke({"limit": 50, "offset": 50})["data"]
            built = tools["build_map_artifact"].invoke({"limit": 50})["data"]
        self.assertEqual((first["total"], first["returned"], first["next_offset"]), (75, 50, 50))
        self.assertEqual((second["returned"], second["has_more"], second["next_offset"]), (25, False, None))
        self.assertEqual((built["location_count"], built["total_locations"]), (50, 75))


if __name__ == "__main__":
    unittest.main()


class RecordAndCitationTests(unittest.TestCase):
    def test_a_tools_data_record_is_never_cut_by_key(self):
        data = {"nodes": [{"key": f"n{i}", "t": "z" * 300} for i in range(60)],
                "links": [{"source": f"n{i}", "target": f"n{i + 1}"} for i in range(59)]}
        page = tool_message_payload(result_id="r", summary="", data=data, budget_chars=MIN_MESSAGE_CHARS)
        self.assertEqual(set(page["data"]), {"nodes", "links"})
        self.assertTrue(all(note["path"][0] == "data" and len(note["path"]) == 2 for note in page["_paging"]))

    def test_document_citations_with_spaces_become_links(self):
        from services.agent.citations import link_document_citations
        text = ("See [March statement.pdf, p.4](doc://March statement.pdf/4) and [Ledger.pdf](doc://Ledger.pdf) "
                "and [Already.pdf, p.2](doc://Already%20done.pdf/2).")
        self.assertEqual(link_document_citations(text),
            "See [March statement.pdf, p.4](doc://March%20statement.pdf/4) and [Ledger.pdf](doc://Ledger.pdf) "
            "and [Already.pdf, p.2](doc://Already%20done.pdf/2).")
