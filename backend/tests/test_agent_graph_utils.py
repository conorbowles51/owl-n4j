import unittest

from services.agent.graph import message_content_to_text
from services.agent.tools import _compact_graph


class AgentGraphUtilsTests(unittest.TestCase):
    def test_message_content_to_text_handles_openai_responses_blocks(self):
        content = [
            {"type": "reasoning", "summary": []},
            {"type": "text", "text": "Final answer"},
        ]

        self.assertEqual(message_content_to_text(content), "Final answer")

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
