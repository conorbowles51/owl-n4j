import unittest

from services.agent.graph import activity_for_tool_call, activity_for_tool_result, message_content_to_text
from services.agent.tools import _compact_graph


class AgentGraphUtilsTests(unittest.TestCase):
    def test_message_content_to_text_handles_openai_responses_blocks(self):
        content = [
            {"type": "reasoning", "summary": []},
            {"type": "text", "text": "Final answer"},
        ]

        self.assertEqual(message_content_to_text(content), "Final answer")

    def test_activity_for_schema_inspection_explains_field_lookup(self):
        activity = activity_for_tool_call(
            "inspect_graph_schema",
            {"labels": ["Person"]},
            "call_1",
        )

        self.assertEqual(activity["title"], "Inspected available graph fields")
        self.assertIn("before writing Cypher", activity["detail"])
        self.assertEqual(activity["status"], "running")

    def test_activity_for_tool_result_keeps_plan_and_adds_result(self):
        trace_item = {
            "id": "call_2",
            "name": "search_graph_entities",
            "arguments": {"query": "Daniel Rook"},
            "status": "success",
            "duration_ms": 42,
            "summary": "Found 3 graph entities matching 'Daniel Rook'.",
            "activity": activity_for_tool_call(
                "search_graph_entities",
                {"query": "Daniel Rook"},
                "call_2",
            ),
        }

        activity = activity_for_tool_result(trace_item)

        self.assertEqual(activity["id"], "call_2")
        self.assertEqual(activity["phase"], "result")
        self.assertIn("Daniel Rook", activity["title"])
        self.assertIn("matching", activity["result_detail"])

    def test_compact_graph_removes_verbose_node_and_relationship_payloads(self):
        graph = {
            "nodes": [
                {
                    "id": "n1",
                    "key": "marcus",
                    "name": "Marcus",
                    "type": "Person",
                    "summary": "A" * 1000,
                    "properties": {"verified_facts": "very large"},
                }
            ],
            "links": [
                {
                    "source": "marcus",
                    "target": "victoria",
                    "type": "CONNECTED_TO",
                    "properties": {
                        "detail": "B" * 1000,
                        "source_quotes": ["too much"],
                        "source_files": ["a.pdf", "b.pdf"],
                    },
                }
            ],
        }

        compact = _compact_graph(graph)

        self.assertNotIn("verified_facts", compact["nodes"][0])
        self.assertLessEqual(len(compact["nodes"][0]["summary"]), 500)
        self.assertNotIn("source_quotes", compact["links"][0]["properties"])
        self.assertEqual(compact["links"][0]["properties"]["source_files"], ["a.pdf", "b.pdf"])


if __name__ == "__main__":
    unittest.main()
