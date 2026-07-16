import unittest
from unittest.mock import patch

from services.agent.cypher_safety import UnsafeCypherError
from services.rag_service import RAGService


GRAPH_SUMMARY = {
    "entity_types": {"Person": 2},
    "relationship_types": {"KNOWS": 1},
    "entities": [
        {"name": "Alice", "key": "alice", "type": "Person"},
        {"name": "Bob", "key": "bob", "type": "Person"},
    ],
}


class FakeLLM:
    def __init__(self, cypher):
        self.cypher = cypher

    def generate_cypher(self, question, schema_info):
        return self.cypher


class RAGCypherSafetyTests(unittest.TestCase):
    def test_structural_cypher_uses_readonly_case_scoped_runner(self):
        service = RAGService()
        debug_log = {}
        token = service._active_llm.set(
            FakeLLM("MATCH (n {case_id: $case_id}) RETURN n.name AS name")
        )
        try:
            with patch(
                "services.rag_service.run_readonly_cypher",
                return_value=[{"name": "Alice"}],
            ) as run:
                context = service._try_cypher_query(
                    "Who is in the case?",
                    GRAPH_SUMMARY,
                    "case-1",
                    debug_log,
                )
        finally:
            service._active_llm.reset(token)

        self.assertIn("Alice", context)
        run.assert_called_once_with(
            "MATCH (n {case_id: $case_id}) RETURN n.name AS name",
            case_id="case-1",
            limit=20,
        )
        self.assertEqual(debug_log["cypher_answer_query"]["results"]["rows_returned"], 1)

    def test_structural_cypher_policy_rejection_does_not_execute_unrestricted_query(self):
        service = RAGService()
        debug_log = {}
        token = service._active_llm.set(FakeLLM("MATCH (n) RETURN n"))
        try:
            with patch(
                "services.rag_service.run_readonly_cypher",
                side_effect=UnsafeCypherError(
                    "Cypher must include the $case_id parameter"
                ),
            ) as run:
                context = service._try_cypher_query(
                    "Dump the graph",
                    GRAPH_SUMMARY,
                    "case-1",
                    debug_log,
                )
        finally:
            service._active_llm.reset(token)

        self.assertIsNone(context)
        run.assert_called_once()
        self.assertIn("rejected", debug_log["cypher_answer_query"])


if __name__ == "__main__":
    unittest.main()
