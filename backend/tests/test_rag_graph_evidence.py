"""Answers read the passages behind graph connections (lx-retrieval B).

Before this change graph expansion gave the model a neighbour's name, type and summary only: a question about a
relationship never saw the passage the relationship was read from, though every relationship carries its
``source_locations``. These tests fail on that code.
"""
from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

CASE = "11111111-1111-1111-1111-111111111111"
FILE = "22222222-2222-2222-2222-222222222222"
REV = "rev1"
CHUNK = (
    "Interview notes. " * 30
    + "Kell said he paid Lena Marsh five hundred dollars by Pocketwire the morning after each night. "
    + "Other matters followed. " * 30
)
QUOTE = "paid Lena Marsh five hundred dollars by Pocketwire"
LOCATION = {"source_document_id": FILE, "revision_id": REV, "source_file": "kell-interview.pdf", "chunk_index": 3,
            "page_start": 4, "page_end": 4, "quote": QUOTE, "coordinate_space": "document_text"}


class Rows(list):
    pass


class FakeSession:
    def __init__(self, rel_locations, node_locations):
        self.rel_locations, self.node_locations = rel_locations, node_locations
        self.queries = []

    def run(self, query, **params):
        self.queries.append((query, params))
        if "UNWIND $pairs" in query:
            assert params["case_id"] == CASE
            return [{"i": p["i"], "locations": self.rel_locations.get((p["a"], p["b"], p["t"]), [])}
                    for p in params["pairs"]]
        if "n.key IN $keys" in query:
            return [{"key": k, "locations": self.node_locations.get(k)} for k in params["keys"]]
        raise AssertionError(query)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeChunks:
    def __init__(self, chunks):
        self.chunks = chunks

    def get(self, ids, include):
        found = [i for i in ids if i in self.chunks]
        return {"ids": found, "documents": [self.chunks[i][0] for i in found],
                "metadatas": [self.chunks[i][1] for i in found]}


def _graph():
    entities = [{"key": "kell", "name": "Travis Kell", "type": "Person", "distance": 0.3},
                {"key": "marsh", "name": "Lena Marsh", "type": "Person", "distance": 0.4},
                {"key": "okafor", "name": "Desmond Okafor", "type": "Person", "distance": 0.5}]
    graph = {"selected_entities": [
        {"key": "kell", "name": "Travis Kell", "type": "Person", "connections": [
            {"key": "okafor", "name": "Desmond Okafor", "type": "Person", "relationship": "KNOWS",
             "direction": "outgoing"},
            {"key": "marsh", "name": "Lena Marsh", "type": "Person", "relationship": "PAID",
             "direction": "outgoing"}]}]}
    return entities, graph


def _chunks(state="active", case=CASE, text=CHUNK):
    meta = {"case_id": case, "evidence_file_id": FILE, "doc_name": "kell-interview.pdf", "ingestion_state": state,
            "page_start": 3, "page_end": 5, "chunk_index": 3}
    return FakeChunks({"%s:%s:chunk:3" % (FILE, REV): (text, meta)})


class GraphEvidenceTests(unittest.TestCase):
    def _passages(self, chunks=None, rel_locations=None, question="What did Travis Kell pay Lena Marsh?"):
        from services import graph_evidence as ge
        entities, graph = _graph()
        session = FakeSession(rel_locations if rel_locations is not None else
                              {("kell", "marsh", "PAID"): [json.dumps([LOCATION])]}, {})
        stats = {}
        passages = ge.evidence_passages(question, entities, graph, CASE, session_factory=lambda: session,
                                        collection=chunks or _chunks(), stats=stats)
        return passages, stats

    def test_a_relationship_brings_its_own_source_passage_with_its_page_cite(self):
        passages, stats = self._passages()
        self.assertEqual(len(passages), 1)
        p = passages[0]
        self.assertEqual(p["about"], "Travis Kell -[PAID]-> Lena Marsh")
        self.assertEqual(p["quote"], QUOTE)
        self.assertIn("Kell said he " + QUOTE, p["text"])  # the text around the quote, not the quote alone
        self.assertLess(len(p["text"]), len(CHUNK))
        self.assertEqual(p["cite"], "doc://%s/4" % FILE)  # the quote's page, not the chunk's first page
        self.assertEqual(stats["unresolved_locations"], 0)

    def test_connections_between_entities_the_question_names_come_first(self):
        from services import graph_evidence as ge
        entities, graph = _graph()
        items = ge.candidate_items("What did Travis Kell pay Lena Marsh?", entities, graph)
        self.assertEqual((items[0]["kind"], items[0]["type"]), ("relationship", "PAID"))

    def test_a_passage_needs_its_quote_in_an_active_chunk_of_the_case(self):
        for chunks in (_chunks(state="deleted"), _chunks(case="other-case"), _chunks(text="no such words here")):
            passages, stats = self._passages(chunks=chunks)
            self.assertEqual(passages, [])
            self.assertEqual(stats["unresolved_locations"], 1)


class AnswerContextTests(unittest.TestCase):
    """Through answer_question: the context the model reads holds the relationship's own passage and cite."""

    def test_a_question_about_a_relationship_gets_the_relationships_source_passage(self):
        import services.rag_service as rag

        entities, graph = _graph()
        session = FakeSession({("kell", "marsh", "PAID"): [json.dumps([LOCATION])]}, {})
        sent = {}

        class Neo4j:
            def session(self):
                return session

            def get_context_for_nodes(self, keys, case_id):
                return graph

        class LLM:
            provider, model_id, last_prompt, last_raw_response = "fake", "fake", "", ""

            def answer_question_with_prompt(self, question, context, conversation_history=None):
                sent["context"] = context
                return "answer", "prompt"

        class Vectors:
            chunk_collection = _chunks()

        service = rag.RAGService.__new__(rag.RAGService)
        service.neo4j = Neo4j()
        from contextvars import ContextVar
        service._active_llm = ContextVar("t", default=None)
        with patch.object(rag, "QUESTION_CLASSIFICATION_ENABLED", False), \
                patch.object(rag, "vector_db_service", Vectors()), \
                patch.object(rag.RAGService, "_retrieve_chunks", lambda self, *a, **k: []), \
                patch.object(rag.RAGService, "_phone_windows", lambda self, *a, **k: []), \
                patch.object(rag.RAGService, "_retrieve_entities", lambda self, *a, **k: [dict(e) for e in entities]), \
                patch.object(rag.RAGService, "_pin_citations", lambda self, case_id, answer: answer), \
                patch.object(rag.RAGService, "_build_result_graph", lambda self, **k: {"nodes": [], "links": []}):
            service.answer_question("What did Travis Kell pay Lena Marsh?", case_id=CASE, llm_context=LLM())
        context = sent["context"]
        self.assertIn("Source of: Travis Kell -[PAID]-> Lena Marsh", context)
        self.assertIn("Kell said he " + QUOTE, context)
        self.assertIn("Cite: doc://%s/4" % FILE, context)


if __name__ == "__main__":
    unittest.main()
