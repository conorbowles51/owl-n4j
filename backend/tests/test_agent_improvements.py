import unittest
from unittest.mock import patch

from services.agent.service import AgentService
from services.agent.tools import AgentToolContext, _filter_graph, make_agent_tools


class AgentImprovementTests(unittest.TestCase):
    def test_runner_clarification_payload_preserves_pending_context(self):
        clarification = AgentService._clarification_from_runner(
            {
                "question": "Which graph should I build?",
                "options": [
                    {"id": "only", "label": "Only transactions"},
                    {"id": "flow", "label": "Transaction flow"},
                ],
                "allow_free_text": True,
                "context": {"reason": "agent_requested_clarification"},
            },
            thread_id="thread-1",
            run_id="run-1",
            original_message="show me a graph",
        )

        self.assertIsNotNone(clarification)
        self.assertEqual(clarification.pending_run_id, "run-1")
        self.assertEqual(clarification.thread_id, "thread-1")
        self.assertEqual(len(clarification.options), 2)
        self.assertEqual(clarification.context["reason"], "agent_requested_clarification")

    def test_filter_graph_keeps_strict_transaction_only_shape(self):
        graph = {
            "nodes": [
                {"key": "tx1", "type": "Transaction", "name": "Payment"},
                {"key": "acct1", "type": "Account", "name": "Account"},
            ],
            "links": [
                {"source": "tx1", "target": "acct1", "type": "VIA_ACCOUNT"},
            ],
        }

        filtered = _filter_graph(
            graph,
            node_types=["Transaction"],
            include_bridge_nodes=False,
            max_nodes=20,
            max_relationships=20,
        )

        self.assertEqual([node["key"] for node in filtered["nodes"]], ["tx1"])
        self.assertEqual(filtered["links"], [])

    def test_filter_graph_can_include_bridge_nodes(self):
        graph = {
            "nodes": [
                {"key": "tx1", "type": "Transaction", "name": "Payment"},
                {"key": "acct1", "type": "Account", "name": "Account"},
            ],
            "links": [
                {"source": "tx1", "target": "acct1", "type": "VIA_ACCOUNT"},
            ],
        }

        filtered = _filter_graph(
            graph,
            node_types=["Transaction"],
            include_bridge_nodes=True,
            max_nodes=20,
            max_relationships=20,
        )

        self.assertEqual({node["key"] for node in filtered["nodes"]}, {"tx1", "acct1"})
        self.assertEqual(len(filtered["links"]), 1)

    def test_unsafe_cypher_tool_reports_error_status(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["run_readonly_cypher"].invoke(
            {
                "query": "MATCH (n) WHERE $case_id IS NOT NULL RETURN n",
                "params": {},
                "limit": 10,
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("case_id", result["error"])

    def test_request_clarification_tool_returns_structured_payload(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["request_clarification"].invoke(
            {
                "question": "Which graph should I build?",
                "options": [
                    {"id": "only", "label": "Only transactions"},
                    {"id": "flow", "label": "Transaction flow"},
                ],
                "allow_free_text": True,
                "reason": "ambiguous graph scope",
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["clarification"]["question"], "Which graph should I build?")
        self.assertEqual(len(result["clarification"]["options"]), 2)

    def test_refinement_metadata_links_new_artifact_to_previous_one(self):
        class Previous:
            id = "source-id"
            type = "graph"
            title = "Original graph"
            created_at = 1

        class Thread:
            artifacts = [Previous()]

        enriched = AgentService._with_refinement_metadata(
            [{"type": "graph", "metadata": {}, "data": {}}],
            request_message="remove all nodes except transactions",
            thread=Thread(),
        )

        metadata = enriched[0]["metadata"]
        self.assertTrue(metadata["refinement"])
        self.assertEqual(metadata["source_artifact_id"], "source-id")

    def test_vector_health_reports_missing_service_explicitly(self):
        import services.vector_db_service as vector_db_service

        with patch.object(vector_db_service, "_vector_db_service", None), patch.object(
            vector_db_service, "_vector_db_last_error", None
        ), patch.object(vector_db_service, "VectorDBService", side_effect=ImportError("missing chromadb")):
            health = vector_db_service.get_vector_db_health()

        self.assertFalse(health["available"])
        self.assertIn("missing chromadb", health["reason"])

    def test_search_documents_tool_uses_vector_chunks_when_available(self):
        class FakeVectorDB:
            def search_chunks(self, embedding, top_k, filter_metadata):
                self.embedding = embedding
                self.top_k = top_k
                self.filter_metadata = filter_metadata
                return [
                    {
                        "id": "chunk-1",
                        "text": "Relevant passage",
                        "metadata": {"filename": "evidence.pdf"},
                        "distance": 0.12,
                    }
                ]

        class FakeEmbeddingService:
            def generate_embedding(self, text):
                self.text = text
                return [0.1, 0.2, 0.3]

        fake_vector = FakeVectorDB()
        fake_embedding = FakeEmbeddingService()
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        with patch("services.agent.tools.get_vector_db_service", return_value=fake_vector), patch(
            "services.vector_db_service.get_vector_db_health",
            return_value={"available": True, "chunks_healthy": True, "chunk_count": 1},
        ), patch("services.embedding_service.embedding_service", fake_embedding):
            result = tools["search_documents"].invoke({"query": "Marcus emails", "limit": 5})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["count"], 1)
        self.assertEqual(fake_vector.filter_metadata, {"case_id": "case-1"})


if __name__ == "__main__":
    unittest.main()
