"""lx-agentquick C: the agent's document search applies chat's relevance floor, returns its total and next_offset,
and counts what fell below the floor (fails on the code before: no floor, no total)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.test_agent_document_search_path import CASE, CHUNK, Embeddings, _tools


def _chunk(i, distance):
    return dict(CHUNK, id="c%d" % i, distance=distance)


class Vectors:
    def search_chunks(self, embedding, top_k, filter_metadata):
        return [_chunk(0, 0.8), _chunk(1, 0.9), _chunk(2, 1.0), _chunk(3, 3.5), _chunk(4, 3.8)]


class FloorTests(unittest.TestCase):
    def _run(self, **args):
        from services.rag_service import rag_service
        with patch("services.agent.tools.get_vector_db_service", return_value=Vectors()), patch(
                "services.vector_db_service.get_vector_db_health", return_value={"available": True}), patch(
                "services.embedding_service.embedding_service", Embeddings()), patch(
                "services.vector_search_settings.get_confidence_threshold", return_value=1.0), patch.object(
                rag_service, "_chunk_space", lambda: "l2"), patch.object(
                rag_service, "search_passages", lambda q, c, chunks, **k: list(chunks)):
            return _tools()["search_documents"].invoke(dict(query="bay 4 rent", **args))["data"]

    def test_weak_passages_are_counted_not_returned(self):
        data = self._run(limit=5)
        self.assertEqual([c["id"] for c in data["chunks"]], ["c0", "c1", "c2"])
        self.assertEqual(data["below_floor"], 2)
        self.assertEqual(data["total_matching"], 3)
        self.assertIsNone(data["next_offset"])
        self.assertIn("2 more passage(s) fell below", data["search_coverage"]["floor_note"])

    def test_paging_gives_next_offset(self):
        data = self._run(limit=2)
        self.assertEqual(data["total_matching"], 3)
        self.assertEqual(data["returned"], 2)
        self.assertEqual(data["next_offset"], 2)
        self.assertTrue(data["has_more"])

    def test_the_weak_passages_can_be_read_marked(self):
        data = self._run(limit=10, include_below_floor=True)
        self.assertEqual(len(data["chunks"]), 5)
        self.assertEqual([c.get("below_floor") for c in data["chunks"]], [None, None, None, True, True])


if __name__ == "__main__":
    unittest.main()
