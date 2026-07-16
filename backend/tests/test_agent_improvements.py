import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from services.agent.graph import (
    _budget_continuation_clarification,
    _looks_like_tool_planning_text,
    _messages_for_finalizer,
    _messages_without_dangling_tool_calls,
    _tool_budget_exhausted,
    _used_tools,
)
from services.agent.service import AgentService
from services.agent.tools import AgentToolContext, _extract_graph_selection, _filter_graph, make_agent_tools


class AgentImprovementTests(unittest.TestCase):
    def test_finalizer_drops_unexecuted_trailing_tool_request(self):
        messages = [
            HumanMessage(content="Create several charts"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "name": "build_chart_artifact",
                        "args": {"title": "Extra chart"},
                    }
                ],
            ),
        ]

        sanitized = _messages_without_dangling_tool_calls(messages)

        self.assertEqual(len(sanitized), 1)
        self.assertIs(sanitized[0], messages[0])

    def test_finalizer_keeps_served_tool_request_history(self):
        messages = [
            HumanMessage(content="Create a chart"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "name": "build_chart_artifact",
                        "args": {"title": "Chart"},
                    }
                ],
            ),
            ToolMessage(
                tool_call_id="call_1",
                name="build_chart_artifact",
                content='{"summary": "Built chart artifact."}',
            ),
        ]

        sanitized = _messages_without_dangling_tool_calls(messages)

        self.assertEqual(sanitized, messages)

    def test_finalizer_detects_tool_budget_exhaustion_from_planning_text(self):
        messages = [
            HumanMessage(content="Build a graph of ownership links"),
            ToolMessage(
                tool_call_id="call_1",
                name="run_readonly_cypher",
                content='{"summary": "Found ownership rows."}',
            ),
            AIMessage(content="I'll run a Cypher to collect the remaining links. to=functions.run_readonly_cypher"),
        ]
        state = {
            "messages": messages,
            "tool_iterations": 28,
            "max_tool_calls": 28,
            "tool_trace": [{"name": "run_readonly_cypher"}],
        }

        self.assertTrue(_used_tools(state))
        self.assertTrue(_tool_budget_exhausted(state))
        self.assertTrue(_looks_like_tool_planning_text(messages[-1].content))
        self.assertEqual(_messages_for_finalizer(state), messages[:-1])

    def test_budget_continuation_clarification_can_be_resumed_by_user(self):
        payload = _budget_continuation_clarification(28)
        clarification = AgentService._clarification_from_runner(
            payload,
            thread_id="thread-1",
            run_id="run-1",
            original_message="build the graph",
        )

        self.assertIsNotNone(clarification)
        self.assertEqual(
            clarification.question,
            "I reached the investigation step limit before I could finish cleanly. Would you like me to continue?",
        )
        self.assertEqual(clarification.options[0].label, "Continue")
        self.assertEqual(clarification.options[1].label, "Stop here")
        self.assertEqual(clarification.context["reason"], "tool_budget_exhausted")
        self.assertEqual(clarification.context["max_tool_calls"], 28)
        self.assertTrue(AgentService._is_tool_budget_clarification(clarification))

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

    def test_graph_selection_extracts_keys_and_relationships_from_rows(self):
        graph, keys = _extract_graph_selection(
            [
                {
                    "transaction_key": "tx1",
                    "sender_key": "acct1",
                    "receiver_key": "org1",
                    "source_key": "tx1",
                    "target_key": "acct1",
                    "relationship_type": "VIA_ACCOUNT",
                    "amount": 18400,
                }
            ]
        )

        self.assertEqual(set(keys), {"tx1", "acct1", "org1"})
        self.assertEqual(graph["links"][0]["source"], "tx1")
        self.assertEqual(graph["links"][0]["target"], "acct1")
        self.assertEqual(graph["links"][0]["type"], "VIA_ACCOUNT")

    def test_graph_artifact_builds_selected_subgraph_from_prior_result_rows(self):
        class FakeResult:
            def single(self):
                return {
                    "nodes": [
                        {"id": "tx1", "key": "tx1", "name": "Payment", "type": "Transaction", "properties": {}},
                        {"id": "acct1", "key": "acct1", "name": "AMB-4418", "type": "Account", "properties": {}},
                        {"id": "org1", "key": "org1", "name": "Northstar Trucking", "type": "Organization", "properties": {}},
                    ],
                    "links": [
                        {"source": "tx1", "target": "acct1", "type": "VIA_ACCOUNT", "properties": {}},
                        {"source": "tx1", "target": "org1", "type": "RECEIVED_PAYMENT", "properties": {}},
                    ],
                }

        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                self.kwargs = kwargs
                return FakeResult()

        class FakeDriver:
            def session(self, **kwargs):
                return FakeSession()

        context = AgentToolContext(case_id="case-1")
        context.result_store["res_tx"] = [
            {
                "transaction_key": "tx1",
                "sender_key": "acct1",
                "receiver_key": "org1",
                "source_key": "tx1",
                "target_key": "acct1",
                "relationship_type": "VIA_ACCOUNT",
            }
        ]
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        with patch("services.agent.tools.driver", FakeDriver()):
            result = tools["build_graph_artifact"].invoke(
                {
                    "title": "Selected transaction graph",
                    "source_result_ids": ["res_tx"],
                    "depth": 0,
                }
            )

        self.assertEqual(result["status"], "success")
        artifact = result["artifact"]
        self.assertEqual(artifact["metadata"]["mode"], "selected_subgraph")
        self.assertEqual(artifact["metadata"]["source_result_ids"], ["res_tx"])
        self.assertEqual({node["key"] for node in artifact["data"]["nodes"]}, {"tx1", "acct1", "org1"})
        self.assertEqual(len(artifact["data"]["links"]), 2)

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

    def test_inspect_graph_schema_reports_actual_properties_and_samples(self):
        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                if "count(n) AS node_count" in query:
                    return [{"label": "Person", "node_count": 2}]
                if "UNWIND keys(n) AS property" in query:
                    return [
                        {
                            "label": "Person",
                            "properties": [
                                {"key": "key", "present_count": 2},
                                {"key": "name", "present_count": 2},
                            ],
                        }
                    ]
                if "collect(sample) AS samples" in query and "MATCH (n)" in query:
                    return [
                        {
                            "label": "Person",
                            "samples": [
                                {"key": "person-1", "name": "Daniel Rook"},
                                {"key": "person-2", "name": "Elena Morrow"},
                            ],
                        }
                    ]
                if "count(r) AS relationship_count" in query:
                    return [{"relationship_type": "ASSOCIATED_WITH", "relationship_count": 1}]
                if "UNWIND keys(r) AS property" in query:
                    return [
                        {
                            "relationship_type": "ASSOCIATED_WITH",
                            "properties": [{"key": "case_id", "present_count": 1}],
                        }
                    ]
                if "type(r) = relationship_type" in query:
                    return [
                        {
                            "relationship_type": "ASSOCIATED_WITH",
                            "samples": [{"case_id": "case-1"}],
                        }
                    ]
                return []

        class FakeDriver:
            def session(self, **kwargs):
                return FakeSession()

        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        with patch("services.agent.tools.driver", FakeDriver()):
            result = tools["inspect_graph_schema"].invoke({"labels": ["Person"], "sample_limit": 2})

        self.assertEqual(result["status"], "success")
        person = result["data"]["labels"]["Person"]
        self.assertEqual(person["count"], 2)
        self.assertEqual(person["properties"]["name"]["present_count"], 2)
        self.assertEqual(person["properties"]["name"]["sample_values"], ["Daniel Rook", "Elena Morrow"])
        self.assertIn("coalesce(n.name", result["data"]["display_name_expression"])

    def test_table_artifact_enriches_blank_name_from_entity_key(self):
        class FakeSession:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def run(self, query, **kwargs):
                return [{"key": "person-1", "display_name": "Daniel Rook"}]

        class FakeDriver:
            def session(self, **kwargs):
                return FakeSession()

        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        with patch(
            "services.agent.tools.run_readonly_cypher",
            return_value=[{"person_key": "person-1", "name": None, "rel_count": 44}],
        ), patch("services.agent.tools.driver", FakeDriver()):
            result = tools["build_table_artifact"].invoke(
                {
                    "query": "MATCH (p:Person) WHERE p.case_id = $case_id RETURN p.key AS person_key, p.display_name AS name",
                    "title": "Top people",
                    "limit": 3,
                }
            )

        self.assertEqual(result["status"], "success")
        rows = result["artifact"]["data"]["rows"]
        self.assertEqual(rows[0]["name"], "Daniel Rook")
        self.assertEqual(rows[0]["person_key"], "person-1")

    def test_direct_table_artifact_builds_from_synthesized_rows(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_table_artifact_from_rows"].invoke(
            {
                "title": "Ranked contradictions",
                "columns": [
                    {"key": "rank", "label": "Rank"},
                    {"key": "severity", "label": "Severity"},
                    {"key": "notes", "label": "Notes"},
                ],
                "rows": [
                    {
                        "rank": 1,
                        "severity": "High",
                        "notes": "Witness A says control; Witness B says customer.",
                        "sources": "a.txt; b.txt",
                    }
                ],
                "source_result_ids": ["res_123"],
                "notes": "Synthesized from prior tool results.",
            }
        )

        self.assertEqual(result["status"], "success")
        artifact = result["artifact"]
        self.assertEqual(artifact["type"], "table")
        self.assertEqual(artifact["metadata"]["direct_rows"], True)
        self.assertEqual(artifact["metadata"]["source_result_ids"], ["res_123"])
        self.assertEqual([column["key"] for column in artifact["data"]["columns"]], ["rank", "severity", "notes", "sources"])
        self.assertEqual(artifact["data"]["rows"][0]["sources"], "a.txt; b.txt")

    def test_direct_table_artifact_rejects_nested_values(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_table_artifact_from_rows"].invoke(
            {
                "title": "Bad table",
                "rows": [
                    {
                        "rank": 1,
                        "nested": {"not": "allowed"},
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("non-scalar", result["error"])

    def test_report_artifact_embeds_available_table_snapshot(self):
        context = AgentToolContext(
            case_id="case-1",
            artifact_store={
                "table-1": {
                    "id": "table-1",
                    "type": "table",
                    "title": "Contradictions table",
                    "data": {
                        "columns": [{"key": "severity"}, {"key": "note"}],
                        "rows": [{"severity": "High", "note": "Control account differs."}],
                    },
                    "metadata": {"direct_rows": True},
                    "citations": [{"label": "Witness statement", "result_id": "res-witness"}],
                }
            },
        )
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_report_artifact"].invoke(
            {
                "title": "Defense contradictions report",
                "purpose": "Summarize contradictions for review.",
                "report_scope": "Witness statements and communications.",
                "included_items": ["Control contradiction", "Source notes"],
                "sections": [
                    {
                        "heading": "Key issues",
                        "content": "The evidence conflicts on who controlled the account.",
                        "level": 2,
                        "embeds": [{"artifact_id": "table-1", "caption": "Ranked contradictions"}],
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "success")
        artifact = result["artifact"]
        self.assertEqual(artifact["type"], "report")
        self.assertEqual(artifact["metadata"]["embedded_artifact_count"], 1)
        embed = artifact["data"]["sections"][0]["embeds"][0]
        self.assertTrue(embed["available"])
        self.assertEqual(embed["type"], "table")
        self.assertEqual(embed["data"]["rows"][0]["severity"], "High")
        self.assertEqual(
            embed["citations"],
            [{"label": "Witness statement", "result_id": "res-witness"}],
        )

    def test_report_artifact_embeds_available_chart_snapshot(self):
        context = AgentToolContext(
            case_id="case-1",
            artifact_store={
                "chart-1": {
                    "id": "chart-1",
                    "type": "chart",
                    "title": "Payments by person",
                    "data": {
                        "chart_type": "bar",
                        "x_key": "person",
                        "y_keys": ["total_amount"],
                        "series": [{"key": "total_amount", "label": "Total amount"}],
                        "rows": [
                            {"person": "Daniel Rook", "total_amount": 145000},
                            {"person": "Elena Morrow", "total_amount": 78000},
                        ],
                    },
                    "metadata": {"direct_rows": True},
                }
            },
        )
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_report_artifact"].invoke(
            {
                "title": "Financial comparison report",
                "purpose": "Summarize payment concentration.",
                "report_scope": "Payment totals by person.",
                "included_items": ["Payment comparison chart"],
                "sections": [
                    {
                        "heading": "Payment concentration",
                        "content": "The chart compares total payments by named person.",
                        "level": 2,
                        "embeds": [{"artifact_id": "chart-1", "caption": "Totals by person"}],
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "success")
        artifact = result["artifact"]
        self.assertEqual(artifact["type"], "report")
        self.assertEqual(artifact["metadata"]["embedded_artifact_count"], 1)
        embed = artifact["data"]["sections"][0]["embeds"][0]
        self.assertTrue(embed["available"])
        self.assertEqual(embed["type"], "chart")
        self.assertEqual(embed["data"]["chart_type"], "bar")
        self.assertEqual(embed["data"]["rows"][0]["person"], "Daniel Rook")

    def test_chart_artifact_builds_bar_chart_from_rows(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_chart_artifact"].invoke(
            {
                "title": "Payments by person",
                "chart_type": "bar",
                "rows": [
                    {"person": "Daniel Rook", "amount": 145000, "count": 3},
                    {"person": "Elena Morrow", "amount": 78000, "count": 2},
                ],
                "x_key": "person",
                "y_keys": ["amount", "count"],
                "series": [
                    {"key": "amount", "label": "Amount"},
                    {"key": "count", "label": "Transactions"},
                ],
                "source_result_ids": ["res_abc"],
            }
        )

        self.assertEqual(result["status"], "success")
        artifact = result["artifact"]
        self.assertEqual(artifact["type"], "chart")
        self.assertEqual(artifact["data"]["chart_type"], "bar")
        self.assertEqual(artifact["data"]["x_key"], "person")
        self.assertEqual(artifact["data"]["y_keys"], ["amount", "count"])
        self.assertEqual(artifact["metadata"]["source_result_ids"], ["res_abc"])

    def test_chart_artifact_infers_pie_keys(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_chart_artifact"].invoke(
            {
                "title": "Severity mix",
                "chart_type": "donut",
                "rows": [
                    {"severity": "High", "count": 4},
                    {"severity": "Medium", "count": 2},
                ],
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["artifact"]["data"]["category_key"], "severity")
        self.assertEqual(result["artifact"]["data"]["value_key"], "count")

    def test_chart_artifact_rejects_non_numeric_series(self):
        context = AgentToolContext(case_id="case-1")
        tools = {tool.name: tool for tool in make_agent_tools(context)}

        result = tools["build_chart_artifact"].invoke(
            {
                "title": "Bad chart",
                "chart_type": "line",
                "rows": [{"month": "Jan", "amount": "not a number"}],
                "x_key": "month",
                "y_keys": ["amount"],
            }
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("numeric", result["error"])


if __name__ == "__main__":
    unittest.main()
