from __future__ import annotations

import unittest
from unittest.mock import patch

from services.neo4j.geo_service import GeoService
from services.neo4j.graph_service import GraphService
from services.neo4j.timeline_service import TimelineService
from services.neo4j.algorithm_service import AlgorithmService


class _Result:
    def __init__(self, rows=None, single=None):
        self.rows = rows or []
        self.single_value = single

    def __iter__(self):
        return iter(self.rows)

    def single(self):
        return self.single_value


class _Session:
    def __init__(self, captured, results):
        self.captured = captured
        self.results = iter(results)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.captured.append({"query": query, "params": params})
        return next(self.results)


class SignificantProjectionTests(unittest.TestCase):
    def test_graph_projection_uses_manifest_keys_and_only_links_returned_nodes(self):
        captured = []
        node_rows = [
            {
                "key": "person-1",
                "name": "Mark",
                "type": "Person",
                "confidence": 0.9,
                "node_props": {
                    "source_files": ["registry.pdf", "report.pdf", "registry.pdf"]
                },
            },
            {
                "key": "event-2",
                "name": "Meeting",
                "type": "Event",
                "confidence": 0.8,
                "node_props": {},
            },
        ]
        link_rows = [
            {
                "source": "person-1",
                "target": "event-2",
                "type": "ATTENDED",
                "rel_props": {},
            }
        ]
        with patch(
            "services.neo4j.graph_service.driver.session",
            return_value=_Session(captured, [_Result(node_rows), _Result(link_rows)]),
        ):
            graph = GraphService().get_graph_structure(
                "case-1",
                entity_keys=["person-1", "event-2"],
            )

        self.assertEqual({node["key"] for node in graph["nodes"]}, {"person-1", "event-2"})
        self.assertEqual(graph["links"][0]["source"], "person-1")
        person = next(node for node in graph["nodes"] if node["key"] == "person-1")
        self.assertEqual(person["source_count"], 2)
        self.assertIn("n.key IN $entity_keys", captured[0]["query"])
        self.assertEqual(captured[0]["params"]["entity_keys"], ["person-1", "event-2"])
        self.assertIn("a.key IN $node_keys AND b.key IN $node_keys", captured[1]["query"])

    def test_node_details_include_complete_relationship_properties_for_merges(self):
        captured = []
        row = {
            "id": "person-1",
            "key": "person-1",
            "name": "Victoria Blackwood",
            "type": "Person",
            "summary": "Summary",
            "notes": None,
            "verified_facts": "[]",
            "ai_insights": "[]",
            "properties": {},
            "connections": [
                {
                    "key": "company-1",
                    "name": "Nexus Trading Ltd",
                    "type": "Organization",
                    "relationship": "DIRECTOR_OF",
                    "direction": "outgoing",
                    "rel_properties": {
                        "source_claim_ids": ["claim-1"],
                        "source_locations": '[{"page_start":2}]',
                        "detail": "Named director",
                    },
                }
            ],
        }
        with patch(
            "services.neo4j.graph_service.driver.session",
            return_value=_Session(captured, [_Result(single=row)]),
        ):
            details = GraphService().get_node_details("person-1", case_id="case-1")

        self.assertIn("rel_properties: properties(r)", captured[0]["query"])
        self.assertEqual(
            details["connections"][0]["rel_properties"]["source_claim_ids"],
            ["claim-1"],
        )

    def test_empty_manifest_short_circuits_all_projections_without_queries(self):
        graph = GraphService().get_graph_structure("case-1", entity_keys=[])
        timeline = TimelineService().get_timeline_page(case_id="case-1", entity_keys=[])
        geo = GeoService()
        with patch("services.neo4j.geo_service.driver.session") as session:
            locations = geo.get_entities_with_locations(case_id="case-1", entity_keys=[])

        self.assertEqual(graph, {"nodes": [], "links": []})
        self.assertEqual(
            timeline,
            {"events": [], "count": 0, "total": 0, "next_cursor": None},
        )
        self.assertEqual(locations, [])
        session.assert_not_called()

    def test_timeline_projection_filters_events_and_connected_entities(self):
        captured = []
        row = {
            "key": "event-2",
            "name": "Meeting",
            "type": "Event",
            "date": "2026-01-02",
            "time": "09:00",
            "amount": None,
            "summary": None,
            "notes": None,
            "connections": [],
        }
        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_Session(captured, [_Result([row]), _Result(single={"total": 1})]),
        ):
            result = TimelineService().get_timeline_page(
                case_id="case-1",
                entity_keys=["event-2", "person-1"],
            )

        self.assertEqual(result["count"], 1)
        self.assertIn("n.key IN $entity_keys", captured[0]["query"])
        self.assertIn("connected.key IN $entity_keys", captured[0]["query"])
        self.assertEqual(captured[0]["params"]["entity_keys"], ["event-2", "person-1"])

    def test_map_projection_filters_locations_and_connections(self):
        captured = []
        with patch(
            "services.neo4j.geo_service.driver.session",
            return_value=_Session(captured, [_Result([])]),
        ):
            GeoService().get_entities_with_locations(
                case_id="case-1",
                entity_keys=["location-1", "person-1"],
            )

        self.assertIn("n.key IN $entity_keys", captured[0]["query"])
        self.assertIn("connected.key IN $entity_keys", captured[0]["query"])
        self.assertEqual(captured[0]["params"]["entity_keys"], ["location-1", "person-1"])

    def test_graph_analysis_uses_the_induced_manifest_graph(self):
        captured = []
        focus_rows = [{"key": "person-1"}, {"key": "event-2"}]
        node_rows = [
            {"key": "person-1", "name": "Mark", "type": "Person"},
            {"key": "event-2", "name": "Meeting", "type": "Event"},
        ]
        link_rows = [{"source": "person-1", "target": "event-2"}]
        with patch(
            "services.neo4j.algorithm_service.driver.session",
            return_value=_Session(
                captured,
                [_Result(focus_rows), _Result(node_rows), _Result(link_rows)],
            ),
        ):
            result = AlgorithmService().get_pagerank_subgraph(
                node_keys=["person-1", "event-2"],
                case_id="case-1",
                induced_only=True,
            )

        self.assertEqual(len(result["results"]), 2)
        self.assertNotIn("MATCH path", captured[0]["query"])
        self.assertIn("n.key IN $node_keys", captured[0]["query"])
        self.assertIn("a.key IN $keys AND b.key IN $keys", captured[2]["query"])

    def test_significant_shortest_paths_require_every_path_node_to_be_allowed(self):
        captured = []
        with patch(
            "services.neo4j.algorithm_service.driver.session",
            return_value=_Session(captured, [_Result([])]),
        ):
            result = AlgorithmService().get_shortest_paths_subgraph(
                ["person-1", "event-2"],
                case_id="case-1",
                allowed_node_keys=["person-1", "event-2"],
            )

        self.assertEqual(result, {"paths": []})
        self.assertIn(
            "all(node IN nodes(path) WHERE node.key IN $allowed_node_keys)",
            captured[0]["query"],
        )
        self.assertEqual(
            captured[0]["params"]["allowed_node_keys"],
            ["person-1", "event-2"],
        )


if __name__ == "__main__":
    unittest.main()
