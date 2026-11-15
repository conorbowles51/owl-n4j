"""The Significant scope finds the passages of marked entities (lx-retrieval C).

Passages carry ``doc_key``, the file name's document key. The scope found its documents as Document nodes linked to
the marked entities and filtered passages by the node's key, but Document nodes are keyed ``DOC-<hash>`` (the ledger's
projection) or by an entity id (the extraction model), so the filter matched no passage. These tests fail on that
code.
"""
from __future__ import annotations

import unittest
from contextvars import ContextVar
from unittest.mock import patch

CASE = "11111111-1111-1111-1111-111111111111"
PASSAGE = {"id": "f:r:chunk:0", "text": "Rent: $650.00 a month for bay 4.", "distance": 0.4,
           "metadata": {"case_id": CASE, "doc_key": "bay4-lease-2023-10-01pdf", "doc_name": "bay4-lease-2023-10-01.pdf",
                        "evidence_file_id": "33333333-3333-3333-3333-333333333333", "page_start": 1}}


class Session:
    def run(self, query, **params):
        if "MENTIONED_IN" in query:
            assert params["entity_keys"] == ["kell"]
            return [{"key": "DOC-6fd393a243e3bea3be6914870e640b97"}]
        if "d.key IN $keys RETURN d.key AS key, d.name AS name" in query:
            return [{"key": k, "name": "bay4-lease-2023-10-01.pdf"} for k in params["keys"]]
        if "MATCH (d:Document {key: $doc_key" in query:
            class One:
                def single(self):
                    return {"name": "bay4-lease-2023-10-01.pdf"}
            return One()
        return []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Vectors:
    def __init__(self):
        self.filters = []
        self.chunk_collection = None

    def count_chunks(self):
        return 1

    def search_chunks(self, query_embedding, top_k, filter_metadata):
        self.filters.append(filter_metadata)
        wanted = filter_metadata["$and"][1]["doc_key"] if "$and" in filter_metadata else None
        keys = wanted.get("$in", []) if isinstance(wanted, dict) else [wanted]
        return [dict(PASSAGE)] if PASSAGE["metadata"]["doc_key"] in keys else []


class Embeddings:
    def generate_embedding(self, text):
        return [0.0, 1.0]


class SignificantScopeTests(unittest.TestCase):
    def test_the_significant_scope_reads_the_passages_of_a_marked_entitys_documents(self):
        import services.rag_service as rag

        sent = {}

        class Neo4j:
            def session(self):
                return Session()

            def get_context_for_nodes(self, keys, case_id):
                return {"selected_entities": []}

        class LLM:
            provider, model_id, last_prompt, last_raw_response = "fake", "fake", "", ""

            def answer_question_with_prompt(self, question, context, conversation_history=None):
                sent["context"] = context
                return "answer", "prompt"

        service = rag.RAGService.__new__(rag.RAGService)
        service.neo4j = Neo4j()
        service._active_llm = ContextVar("t", default=None)
        vectors = Vectors()
        with patch.object(rag, "QUESTION_CLASSIFICATION_ENABLED", False), \
                patch.object(rag, "VECTOR_DB_AVAILABLE", True), \
                patch.object(rag, "vector_db_service", vectors), \
                patch.object(rag, "embedding_service", Embeddings()), \
                patch.object(rag, "get_confidence_threshold", lambda: 2.0), \
                patch.object(rag.RAGService, "_retrieve_entities", lambda self, *a, **k: []), \
                patch.object(rag.RAGService, "_pin_citations", lambda self, case_id, answer: answer), \
                patch.object(rag.RAGService, "_build_result_graph", lambda self, **k: {"nodes": [], "links": []}):
            result = service.answer_question("What is the rent for bay 4?", case_id=CASE, llm_context=LLM(),
                                             scope_entity_keys=["kell"])
        self.assertIn("Rent: $650.00 a month for bay 4.", sent["context"])
        self.assertEqual(result["context_mode"], "significant")
        # never a case-wide search in the strict scope
        self.assertTrue(all("$and" in f for f in vectors.filters))

    def test_document_node_keys_become_passage_keys_by_file_name(self):
        import services.rag_service as rag

        class Neo4j:
            def session(self):
                return Session()

        service = rag.RAGService.__new__(rag.RAGService)
        service.neo4j = Neo4j()
        self.assertEqual(service._chunk_doc_keys(["DOC-6fd393a243e3bea3be6914870e640b97"], CASE),
                         ["DOC-6fd393a243e3bea3be6914870e640b97", "bay4-lease-2023-10-01pdf"])


if __name__ == "__main__":
    unittest.main()
