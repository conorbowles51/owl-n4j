"""The agent's search_documents reads chat's passages, and searches the Significant layer (lx-retrieval E).

Before, the agent's document search returned the chunk vectors alone, in distance order, and refused to run at all
in the Significant layer. These tests fail on that code.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

CASE = "11111111-1111-1111-1111-111111111111"
CHUNK = {"id": "f:r:chunk:0", "text": "Rent: $650.00 a month for bay 4.", "distance": 0.8,
         "metadata": {"case_id": CASE, "doc_key": "bay4-lease-2023-10-01pdf", "doc_name": "bay4-lease-2023-10-01.pdf",
                      "evidence_file_id": "33333333-3333-3333-3333-333333333333", "page_start": 1}}
EVIDENCE = {"id": "g:r:chunk:2@40", "text": "Kell paid the rent for bay 4 on the 1st.", "distance": None,
            "metadata": {"doc_name": "kell-2024-01.pdf", "evidence_file_id": "44444444-4444-4444-4444-444444444444",
                         "page_start": 2}, "about": "Travis Kell -[PAID]-> Ruiz Auto & Tire",
            "quote": "paid the rent for bay 4", "_graph_evidence": True}


class Vectors:
    def __init__(self):
        self.filters = []

    def search_chunks(self, embedding, top_k, filter_metadata):
        self.filters.append(filter_metadata)
        return [dict(CHUNK)]


class Embeddings:
    def generate_embedding(self, text):
        return [0.1, 0.2]


def _tools(allowed=None):
    from services.agent.tools import AgentToolContext, make_agent_tools
    context = AgentToolContext(case_id=CASE, allowed_entity_keys=allowed)
    return {tool.name: tool for tool in make_agent_tools(context)}


class AgentDocumentSearchPathTests(unittest.TestCase):
    def _search(self, allowed=None, documents=("DOC-1",)):
        from services.rag_service import rag_service
        vectors = Vectors()
        calls = {}

        def search_passages(question, case_id, chunks, **kwargs):
            calls.update(question=question, case_id=case_id, chunks=chunks, **kwargs)
            return [dict(EVIDENCE)] + list(chunks)

        with patch("services.agent.tools.get_vector_db_service", return_value=vectors), patch(
                "services.vector_db_service.get_vector_db_health", return_value={"available": True}), patch(
                "services.embedding_service.embedding_service", Embeddings()), patch.object(
                rag_service, "search_passages", search_passages), patch.object(
                rag_service, "_get_documents_for_entities", lambda keys, case_id: list(documents)), patch.object(
                rag_service, "_chunk_doc_keys", lambda keys, case_id: ["bay4-lease-2023-10-01pdf"] if keys else []):
            result = _tools(allowed)["search_documents"].invoke({"query": "bay 4 rent", "limit": 5})
        return result, calls, vectors

    def test_the_agent_reads_the_passages_behind_graph_connections_ranked_with_its_chunks(self):
        result, calls, vectors = self._search()
        self.assertEqual(result["status"], "success")
        chunks = result["data"]["chunks"]
        self.assertEqual(chunks[0]["source_of"], ["Travis Kell -[PAID]-> Ruiz Auto & Tire"])
        self.assertEqual(chunks[0]["quote"], "paid the rent for bay 4")
        self.assertEqual(chunks[0]["cite"], "doc://44444444-4444-4444-4444-444444444444/2")
        self.assertEqual(calls["query_embedding"], [0.1, 0.2])  # the question is embedded once
        self.assertIsNone(calls["scope_entity_keys"])
        self.assertEqual(vectors.filters, [{"case_id": CASE}])

    def test_the_significant_layer_searches_the_documents_of_its_entities(self):
        result, calls, vectors = self._search(allowed={"kell"})
        self.assertEqual(result["status"], "success")
        self.assertEqual(vectors.filters, [{"$and": [{"case_id": CASE},
                                                     {"doc_key": {"$in": ["bay4-lease-2023-10-01pdf"]}}]}])
        self.assertEqual(calls["scope_entity_keys"], ["kell"])
        self.assertEqual(len(result["data"]["chunks"]), 2)

    def test_the_significant_layer_says_so_when_no_document_is_linked(self):
        result, calls, vectors = self._search(allowed={"kell"}, documents=())
        self.assertEqual(result["data"]["chunks"], [])
        self.assertIn("No document is linked to the entities in the Significant layer", result["summary"])
        self.assertEqual(vectors.filters, [])  # nothing outside the layer was searched


if __name__ == "__main__":
    unittest.main()
