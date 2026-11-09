"""Relationship analysis reads the case's node list, not the full graph with every property and link."""
import unittest
from unittest.mock import patch

from routers import graph
from services.neo4j.graph_service import GraphService


# The route meters model calls against the case by UUID (c1e88a8b0), as every real case id is.
CASE_ID = "5d0e1c2a-3b4f-4a6e-9c8d-7f1e2d3c4b5a"


class _Result(list):
    pass


class _Session:
    def __init__(self, captured, rows):
        self.captured, self.rows = captured, rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, **params):
        self.captured.append(query)
        return _Result(self.rows)


class RelationshipAnalysisNodesTests(unittest.TestCase):
    def setUp(self):
        # The route checks the case's AI spend limit first (c1e88a8b0), reading it from PostgreSQL. These tests are
        # about which nodes reach the model, so the case is under its limit; the check itself is asserted below.
        budget = patch("services.ai_budget.check_new_session")
        self.budget_check = budget.start()
        self.addCleanup(budget.stop)

    def test_node_index_keeps_first_row_per_key_and_reads_no_property_map(self):
        captured = []
        rows = [
            {"key": "a", "name": None, "type": "Person", "summary": "s"},
            {"key": "b", "name": "B", "type": "Company", "summary": None},
            {"key": "a", "name": "dup", "type": "Person", "summary": None},
        ]
        with patch("services.neo4j.graph_service.driver.session", return_value=_Session(captured, rows)):
            nodes = GraphService().get_case_node_index("case-1")
        self.assertEqual(nodes, [
            {"key": "a", "name": "a", "type": "Person", "summary": "s", "degree": 0},
            {"key": "b", "name": "B", "type": "Company", "summary": None, "degree": 0},
        ])
        self.assertNotIn("properties(", captured[0])
        self.assertNotIn("-[", captured[0])

    def test_analysis_does_not_read_the_full_graph(self):
        request = graph.AnalyzeRelationshipsRequest(case_id=CASE_ID)
        with (
            patch.object(graph.neo4j_service, "get_node_details", return_value={"key": "a", "name": "A", "type": "Person"}),
            patch.object(graph.neo4j_service, "get_full_graph", side_effect=AssertionError("full graph read")),
            patch.object(graph.neo4j_service, "get_case_node_index", return_value=[{"key": "a", "name": "A", "type": "Person", "summary": None}]) as index,
        ):
            result = graph.analyze_node_relationships("a", request)
        index.assert_called_once_with(CASE_ID)
        self.budget_check.assert_called_once_with(CASE_ID, "these relationship suggestions")
        self.assertEqual(result["relationships"], [])
        self.assertTrue(result["success"])


    def test_node_index_is_ordered_most_connected_first_then_key(self):
        captured = []
        with patch("services.neo4j.graph_service.driver.session", return_value=_Session(captured, [])):
            GraphService().get_case_node_index("case-1")
        query = " ".join(captured[0].split())
        self.assertIn("COUNT { (n)--() } AS degree", query)
        self.assertIn("ORDER BY degree DESC, key ASC", query)

    def _analyse(self, nodes, llm_reply='{"relationships": []}'):
        from services import relationship_analyzer as ra
        prompts = []

        class _LLM:
            def call(self, prompt, **kw):
                prompts.append(prompt)
                return llm_reply

            def parse_json_response(self, text):
                import json
                return json.loads(text)

        request = graph.AnalyzeRelationshipsRequest(case_id=CASE_ID)
        with (
            patch.object(graph.neo4j_service, "get_node_details", return_value={"key": "x", "name": "X", "type": "Person"}),
            patch.object(graph.neo4j_service, "get_case_node_index", return_value=nodes),
            patch.object(ra, "_llm_available", True),
            patch.object(ra, "llm_service", _LLM(), create=True),
            patch.object(ra, "get_ingestion_config", return_value={}),
        ):
            result = graph.analyze_node_relationships("x", request)
        return result, prompts

    def test_analysis_over_the_limit_states_the_cut_in_prompt_and_response(self):
        nodes = [{"key": f"k{i:03d}", "name": f"N{i}", "type": "Person", "summary": None} for i in range(150)]
        result, prompts = self._analyse(nodes)
        self.assertTrue(result["success"])
        self.assertEqual(result["nodes_considered"], 100)
        self.assertEqual(result["nodes_total"], 150)
        self.assertTrue(result["truncated"])
        self.assertIn("100 most-connected of 150 nodes", result["message"])
        self.assertIn("the 100 most-connected of 150 nodes", prompts[0])
        self.assertIn("key: k099", prompts[0])
        self.assertNotIn("key: k100", prompts[0])

    def test_analysis_under_the_limit_says_all_nodes(self):
        nodes = [{"key": "b", "name": "B", "type": "Company", "summary": None}]
        result, prompts = self._analyse(nodes)
        self.assertFalse(result["truncated"])
        self.assertEqual((result["nodes_considered"], result["nodes_total"]), (1, 1))
        self.assertIn("all 1 nodes", prompts[0])


if __name__ == "__main__":
    unittest.main()
