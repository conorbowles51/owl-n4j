"""lx-agentfit round 2: how requests are sent to DeepSeek and how many steps a question takes, one switch per item.

R compact results, T descriptions and errors written for the model, P plan/batch/stop prompt lines, M several names
or searches per call, G graph tools for several entities, X a step's calls side by side, N notes and re-read caps.
Measured on 81 recorded runs (headless/LX-AGENTFIT-STATUS.md). Each test fails on the code before round 2, and the
"off" tests pin that nothing changes while an item is off."""
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from services.agent import graph, lean_history, model_payloads, tool_errors
from services.agent.cypher_safety import UnsafeCypherError, validate_readonly_cypher
from services.agent.graph import AgentGraphRunner
from services.agent.tools import AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-0000000000ad"


def on(items):
    return patch.dict(os.environ, {"LOUPE_AGENT_FIT": items})


def leaves(value, out=None):
    out = [] if out is None else out
    if isinstance(value, dict):
        for item in value.values():
            leaves(item, out)
    elif isinstance(value, list):
        for item in value:
            leaves(item, out)
    elif value is not None and value != "":
        out.append(json.dumps(value, ensure_ascii=False))
    return out


ROWS = [{"rec": "rec://%d" % i, "kind": "call", "body": None, "subject": None, "to": ["X"], "attachments": [],
         "n": i, "flag": False} for i in range(5)]


class CompactResultsTests(unittest.TestCase):
    def test_r_drops_empty_fields_and_sends_records_as_one_table_keeping_every_value_and_link(self):
        data = {"total": 5, "next_offset": None, "items": ROWS, "note": ""}
        with on("R"):
            payload = model_payloads.tool_message_payload(result_id="res_1", summary="5.", data=data)
        compact = payload["data"]
        self.assertEqual(compact["items"]["columns"], ["rec", "kind", "to", "n", "flag"])
        self.assertEqual(len(compact["items"]["rows"]), 5)
        self.assertNotIn("next_offset", compact)
        self.assertEqual(sorted(leaves(data)), sorted(leaves(compact["items"]["rows"]) + leaves(compact["total"])))
        self.assertLess(len(json.dumps(compact)), len(json.dumps(data)) * 0.7)

    def test_r_off_sends_the_result_as_before(self):
        data = {"total": 5, "next_offset": None, "items": ROWS}
        with on(""):
            payload = model_payloads.tool_message_payload(result_id="res_1", summary="5.", data=data)
        self.assertEqual(payload["data"], data)

    def test_a_ledger_digest_keeps_its_group_figures_from_a_table(self):
        groups = [{"group": "g%d" % i, "currency": "MXN", "transaction_count": i, "credits_minor": "10",
                   "debits_minor": "0", "net_minor": "10", "pad": "x" * 900} for i in range(3)]
        data = {"schema": lean_history.LEDGER_SCHEMA, "view": "groups", "items": groups}
        with on("R"):
            payload = model_payloads.tool_message_payload(result_id="res_2", summary="3 groups.", data=data)
            digest = lean_history.digest_payload(payload)
        self.assertEqual([f["group"] for f in digest["facts"]["group_figures"]], ["g0", "g1", "g2"])


class ErrorsForTheModelTests(unittest.TestCase):
    def test_t_says_how_to_fix_a_refused_query_with_an_example(self):
        text = tool_errors.cypher_fix("Nested graph patterns, list expressions and map projections are not supported")
        self.assertIn("How to fix", text)
        self.assertIn(tool_errors.CYPHER_EXAMPLE, text)

    def test_t_accepts_a_list_of_literal_values_and_still_refuses_patterns_maps_and_comprehensions(self):
        good = "MATCH (n {case_id: $case_id}) WHERE n.key IN ['a', 'b'] RETURN n.key, labels(n)[0] AS t LIMIT 5"
        bad = ["MATCH (n {case_id: $case_id}) WHERE n.key IN [(m)-[]-()] RETURN n.key LIMIT 5",
               "MATCH (n {case_id: $case_id}) RETURN {a: n.key} LIMIT 5",
               "MATCH (n {case_id: $case_id}) RETURN [x IN n.list | x] AS xs LIMIT 5",
               "MATCH (n) WHERE n.key IN ['a'] RETURN n.key LIMIT 5"]
        with on(""):
            self.assertRaises(UnsafeCypherError, validate_readonly_cypher, good)
        with on("T"):
            validate_readonly_cypher(good)
            for query in bad:
                self.assertRaises(UnsafeCypherError, validate_readonly_cypher, query)

    def test_t_prompt_no_longer_says_with_and_unwind_are_allowed(self):
        with on(""):
            self.assertIn("MATCH/OPTIONAL MATCH/WITH/UNWIND", graph._cypher_rule_lines())
        with on("T"):
            self.assertNotIn("WITH/UNWIND", graph._cypher_rule_lines())
            self.assertIn("No WITH, UNWIND", graph._cypher_rule_lines())

    def test_t_turns_an_argument_error_into_a_line_per_field_without_the_input_dump(self):
        class Args(BaseModel):
            people: list[str]
        try:
            Args.model_validate({"people": "Ann", "case_id": "secret-dump"})
        except Exception as exc:  # noqa: BLE001
            text = tool_errors.model_error("phone_messages", exc)
        self.assertTrue(text.startswith("The call's arguments were not accepted. people:"))
        self.assertNotIn("secret-dump", text)

    def test_t_mends_a_page_path_copied_from_a_digest_or_with_a_position_as_text(self):
        context = AgentToolContext(case_id=CASE)
        context.model_views["res_9"] = {"data": {"items": [{"a": i} for i in range(4)]}}
        page = next(t for t in make_agent_tools(context) if t.name == "read_tool_result_page")
        with on("T"):
            out = page.invoke({"result_id": "res_9", "path": ["not_in_digest", "items"]})
        self.assertEqual(out["data"]["path_used"], ["data", "items"])
        self.assertEqual(len(out["data"]["items"]), 4)
        with on(""):
            out = page.invoke({"result_id": "res_9", "path": ["not_in_digest", "items"]})
        self.assertEqual(out["status"], "error")


class PromptTests(unittest.TestCase):
    def test_p_adds_the_plan_batch_and_stop_line_only_when_on(self):
        with on(""):
            self.assertNotIn("decide which lookups", graph._fit_prompt_lines())
        with on("P"):
            self.assertIn("decide which lookups", graph._fit_prompt_lines())
            self.assertIn("several tool calls together", graph._fit_prompt_lines())


def tool(name, func):
    class Args(BaseModel):
        query: str = ""
    return StructuredTool.from_function(func=func, name=name, description="Stub.", args_schema=Args)


class ManyAtOnceTests(unittest.TestCase):
    def test_m_searches_several_names_in_one_call_and_off_keeps_the_one_name_tool(self):
        context = AgentToolContext(case_id=CASE)
        with on("M"), patch("services.agent.tools.graph_service.search_nodes",
                            side_effect=lambda query, limit, case_id: [{"key": query.lower()}]):
            search = next(t for t in make_agent_tools(context) if t.name == "search_graph_entities")
            out = search.invoke({"queries": ["Ann", "Bob", "Ann"]})
        self.assertEqual([x["query"] for x in out["data"]["searches"]], ["Ann", "Bob"])
        self.assertEqual(out["data"]["count"], 2)
        with on(""):
            search = next(t for t in make_agent_tools(context) if t.name == "search_graph_entities")
        self.assertEqual(set(search.args_schema.model_fields), {"query", "limit"})

    def test_m_groups_ledger_totals_by_counterparty_and_month(self):
        from services.agent.financial_ledger_tools import _totals

        def reading(day, name, minor):
            return {"row": {"currency": "MXN", "account_type": "bank", "direction": "debit", "amount_minor": minor,
                            "to_name": name, "ordering_date": day, "account_id": "a", "source_document_id": "d"}}
        items = _totals([reading("2024-05-02", "ACME", 100), reading("2024-05-20", "ACME", 50),
                         reading("2024-06-01", "ACME", 7)], "counterparty_month")
        self.assertEqual([(i["month"], i["debits_minor"]) for i in items], [("2024-05", "150"), ("2024-06", "7")])

    def test_g_reads_several_neighbourhoods_and_keeps_only_the_asked_relationship_types(self):
        def around(key, depth, case_id):
            return {"nodes": [{"key": key}, {"key": key + "-w"}, {"key": key + "-p"}],
                    "links": [{"source": key, "target": key + "-w", "type": "WORKS_FOR"},
                              {"source": key, "target": key + "-p", "type": "SENT_PAYMENT"}]}
        context = AgentToolContext(case_id=CASE)
        with on("G"), patch("services.agent.tools.graph_service.get_node_with_neighbours", side_effect=around):
            hood = next(t for t in make_agent_tools(context) if t.name == "get_entity_neighborhood")
            out = hood.invoke({"entity_keys": ["a", "b"], "relationship_types": ["works_for"]})
        got = out["data"]["neighborhoods"]
        self.assertEqual([g["key"] for g in got], ["a", "b"])
        self.assertEqual([l["type"] for l in got[0]["links"]], ["WORKS_FOR"])
        self.assertEqual(got[0]["links_of_other_types"], 1)
        self.assertEqual({n["key"] for n in got[0]["nodes"]}, {"a", "a-w"})


class SideBySideTests(unittest.TestCase):
    def test_x_runs_a_steps_calls_together_and_keeps_their_order(self):
        seen = []

        def slow(name):
            def run(query=""):
                seen.append(threading.current_thread().name)
                time.sleep(0.3)
                return {"status": "success", "summary": name, "data": {"name": name}}
            return run
        tools = {n: tool(n, slow(n)) for n in ("one", "two", "three")}
        calls = [{"name": n, "args": {}, "id": n} for n in ("one", "two", "three")]
        with on("X"):
            started = time.perf_counter()
            done = graph._run_side_by_side(calls, tools)
            wall = time.perf_counter() - started
        self.assertLess(wall, 0.75)
        self.assertEqual([done[i][0]["summary"] for i in (1, 2, 3)], ["one", "two", "three"])
        with on(""):
            self.assertEqual(graph._run_side_by_side(calls, tools), {})

    def test_x_leaves_rereads_notes_and_artifacts_in_order(self):
        tools = {n: tool(n, lambda query="": {}) for n in ("read_tool_result_page", "build_table_artifact", "a")}
        calls = [{"name": n, "args": {}} for n in tools]
        with on("X"):
            self.assertEqual(graph._run_side_by_side(calls, tools), {})


class NotesAndRereadCapTests(unittest.TestCase):
    def test_n_caps_the_notes_by_size_and_says_so(self):
        context = AgentToolContext(case_id=CASE)
        notes = next(t for t in make_agent_tools(context) if t.name == "record_working_notes")
        with on("B,N"):
            for _ in range(8):
                out = notes.invoke({"facts": [{"fact": "y" * 600, "cite": "txn://1"}]})
        self.assertEqual(sum(len(n["fact"]) for n in context.working_notes), 3_600)
        self.assertIn("the notes are full", out["summary"])

    def test_n_allows_ten_rereads_and_notes_apart_from_them(self):
        context = AgentToolContext(case_id=CASE)
        with on("B,N"):
            refused = [graph._free_call_refusal("read_tool_result_page", context) for _ in range(12)]
            self.assertIsNone(graph._free_call_refusal("record_working_notes", context))
        self.assertEqual(sum(r is None for r in refused), graph.REREAD_CAP)
        self.assertEqual(context.free_calls, graph.REREAD_CAP + 1)


if __name__ == "__main__":
    unittest.main()
