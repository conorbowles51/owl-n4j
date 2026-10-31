"""Relationship analysis reads the case's node list, not the full graph with every property and link."""
import unittest
from unittest.mock import patch

from routers import graph
from services.neo4j.graph_service import GraphService


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
            {"key": "a", "name": "a", "type": "Person", "summary": "s"},
            {"key": "b", "name": "B", "type": "Company", "summary": None},
        ])
        self.assertNotIn("properties(", captured[0])
        self.assertNotIn("-[", captured[0])

    def test_analysis_does_not_read_the_full_graph(self):
        request = graph.AnalyzeRelationshipsRequest(case_id="case-1")
        with (
            patch.object(graph.neo4j_service, "get_node_details", return_value={"key": "a", "name": "A", "type": "Person"}),
            patch.object(graph.neo4j_service, "get_full_graph", side_effect=AssertionError("full graph read")),
            patch.object(graph.neo4j_service, "get_case_node_index", return_value=[{"key": "a", "name": "A", "type": "Person", "summary": None}]) as index,
        ):
            result = graph.analyze_node_relationships("a", request)
        index.assert_called_once_with("case-1")
        self.assertEqual(result["relationships"], [])
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
