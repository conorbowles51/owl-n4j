"""Backfill status counts a large vector store page by page.

An unpaged Chroma get of a large collection fails ("too many SQL variables": live 9 Nov, 46,694 chunks and
34,112 entities); the status screen then showed 0 chunks and 0 entities.
"""
import unittest
from unittest import mock

from fastapi import HTTPException

from routers import backfill


class _Collection:
    """Fails like Chroma's SQLite backend when one get asks for more than `cap` rows."""

    def __init__(self, metadatas, cap=7):
        self.metadatas = metadatas
        self.cap = cap
        self.calls = []

    def get(self, include=None, limit=None, offset=None, where=None):
        self.calls.append((limit, offset))
        start = offset or 0
        stop = len(self.metadatas) if limit is None else min(len(self.metadatas), start + limit)
        if stop - start > self.cap:
            raise RuntimeError("too many SQL variables")
        return {"ids": [f"id{i}" for i in range(start, stop)], "metadatas": self.metadatas[start:stop]}


class BackfillStatusPagedTest(unittest.TestCase):
    @staticmethod
    def _engine(case_id=None, include_phones=False):
        keys = {"id0": "Person", "id1": "Event", "id99": "Location"}
        if include_phones:
            keys["id2"] = "PhoneNumber"
        return keys

    def _status(self, chunks, entities):
        neo = mock.Mock()
        neo.run_cypher.side_effect = [
            [{"total": 4, "with_summary": 2, "with_case_id": 3}],
            [{"total": 30, "with_case_id": 25}],
        ]
        vdb = mock.Mock(chunk_collection=chunks, entity_collection=entities)
        with mock.patch("services.entity_vectors.engine_entity_labels", self._engine), \
                mock.patch.object(backfill, "neo4j_service", neo), \
                mock.patch.object(backfill, "vector_db_service", vdb), \
                mock.patch.object(backfill, "STATUS_PAGE_SIZE", 5):
            return backfill.get_backfill_status(user={"username": "t"})

    def test_counts_every_row_of_collections_larger_than_one_read(self):
        chunk_meta = [{"doc_id": f"d{i % 3}", "case_id": "c" if i % 4 else ""} for i in range(23)]
        entity_meta = [{"case_id": "c"} if i % 5 else {} for i in range(17)] + [None]
        chunks, entities = _Collection(chunk_meta), _Collection(entity_meta)
        out = self._status(chunks, entities)
        self.assertEqual(out.chunks["total"], 23)
        self.assertEqual(out.chunks["with_case_id"], sum(1 for i in range(23) if i % 4))
        self.assertEqual(out.documents["with_chunks"], 3)
        self.assertEqual(out.entities["total_chromadb"], 18)
        self.assertEqual(out.entities["with_case_id_metadata"], sum(1 for i in range(17) if i % 5))
        self.assertTrue(all(limit == 5 for limit, _ in chunks.calls))

    def test_exact_multiple_of_page_size(self):
        out = self._status(_Collection([{"doc_id": "d"}] * 10), _Collection([{"case_id": "c"}] * 5))
        self.assertEqual(out.chunks["total"], 10)
        self.assertEqual(out.entities["total_chromadb"], 5)

    def test_missing_counts_only_entities_the_engine_embeds(self):
        """Payments, statement periods and file Documents are never embedded: the old count (every non-Document node
        minus every vector) reported 46,067 missing on live 9 Nov while no entity vector was stale."""
        out = self._status(_Collection([]), _Collection([{"case_id": "c"}] * 4))  # vectors id0..id3
        self.assertEqual(out.entities["missing_embeddings"], 1)   # id99
        self.assertEqual(out.entities["orphaned_embeddings"], 1)  # id3: no engine entity

    def test_failed_read_is_an_error_not_zero(self):
        broken = mock.Mock()
        broken.get.side_effect = RuntimeError("vector store down")
        with self.assertRaises(HTTPException):
            self._status(broken, _Collection([]))


if __name__ == "__main__":
    unittest.main()
