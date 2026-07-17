import unittest
from datetime import datetime
from unittest.mock import patch

from routers import graph
from services.cypher_generator import format_properties, generate_cypher_from_graph
from services.graph_edit_schema import SYSTEM_PROPERTY_KEYS
from services.neo4j.entity_service import EntityService


class ManualNodeProvenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_node_stamps_manual_provenance_and_logs_it(self):
        captured = {}

        def capture_cypher(cypher, params):
            captured["cypher"] = cypher
            captured["params"] = params

        with patch.object(
            graph.neo4j_service,
            "run_cypher",
            side_effect=capture_cypher,
        ), patch.object(graph.system_log_service, "log") as log:
            response = await graph.create_node(
                graph.CreateNodeRequest(
                    name="Investigator Assertion",
                    type="Person",
                    case_id="case-1",
                    properties={
                        "created_by": "client-forged@example.com",
                        "source": "ingestion",
                        "role": "director",
                    },
                ),
                user={"username": "analyst@example.com"},
            )

        self.assertTrue(response.success)
        cypher = captured["cypher"]
        self.assertIn("user_created: true", cypher)
        self.assertIn("created_by: 'analyst@example.com'", cypher)
        self.assertIn("source: 'manual'", cypher)
        self.assertIn("role: 'director'", cypher)
        self.assertNotIn("client-forged@example.com", cypher)

        details = log.call_args.kwargs["details"]
        self.assertEqual(details["created_by"], "analyst@example.com")
        self.assertTrue(details["user_created"])
        self.assertEqual(details["source"], "manual")
        datetime.fromisoformat(details["created_at"])

    def test_manual_provenance_fields_are_system_fields(self):
        self.assertTrue(
            {"user_created", "created_by", "created_at", "source"}.issubset(
                SYSTEM_PROPERTY_KEYS,
            )
        )


class CypherGeneratorBooleanTests(unittest.TestCase):
    def test_format_properties_writes_boolean_literals(self):
        self.assertIn("user_created: true", format_properties({"user_created": True}))

    def test_generate_cypher_does_not_default_manual_provenance(self):
        cypher = generate_cypher_from_graph(
            {
                "nodes": [
                    {
                        "key": "ingested-1",
                        "id": "ingested-1",
                        "name": "Ingested Entity",
                        "type": "Person",
                    }
                ],
                "links": [],
            },
            case_id="case-1",
        )

        self.assertNotIn("user_created", cypher)
        self.assertNotIn("source: 'manual'", cypher)


class RecycleSnapshotProvenanceTests(unittest.TestCase):
    def test_snapshot_restore_props_preserve_manual_provenance(self):
        props = EntityService()._props_for_snapshot(
            {
                "original_key": "node-1",
                "properties": {
                    "name": "Manual Node",
                    "user_created": True,
                    "created_by": "analyst@example.com",
                    "created_at": "2026-07-17T12:00:00+00:00",
                    "source": "manual",
                },
            },
            "case-1",
        )

        self.assertTrue(props["user_created"])
        self.assertEqual(props["created_by"], "analyst@example.com")
        self.assertEqual(props["created_at"], "2026-07-17T12:00:00+00:00")
        self.assertEqual(props["source"], "manual")
        self.assertEqual(props["case_id"], "case-1")


if __name__ == "__main__":
    unittest.main()
