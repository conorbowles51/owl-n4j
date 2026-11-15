"""Searched passages are ranked together by reciprocal rank fusion (lx-retrieval D).

The answer sorted every passage by raw distance: a phone window's invented distance competed with real vector
distances, and passages with no distance came last and fell outside the 15 kept. The threshold assumed one distance
space while the code did not read the collection's. These tests fail on that code.
"""
from __future__ import annotations

import unittest


def _vector(n, distance):
    return {"id": "f%d:r:chunk:0" % n, "text": "vector passage %d" % n, "distance": distance,
            "metadata": {"doc_name": "doc%d.pdf" % n}}


def _service():
    from services.rag_service import RAGService
    return RAGService.__new__(RAGService)


class FusionTests(unittest.TestCase):
    def test_the_best_word_match_is_kept_beside_twenty_close_vector_passages(self):
        chunks = [_vector(i, 0.5 + i * 0.01) for i in range(20)]
        # the phone search's best window: all question words on the line, its distance stands for word coverage
        phone = {"id": "phone:r1:0-80", "text": "left something in the tow truck, need it back", "distance": 0.4,
                 "metadata": {"doc_name": "Phone 2"}}
        weak_phone = {"id": "phone:r2:0-80", "text": "see you", "distance": 1.0, "metadata": {"doc_name": "Phone 2"}}
        kept, _ = _service()._rerank_by_score(chunks + [weak_phone, phone], [], 15, 10, 80000, {})
        ids = [c["id"] for c in kept]
        self.assertIn("phone:r1:0-80", ids)
        self.assertIn("phone:r2:0-80", ids)  # first and second of their own list rank with vector ranks 1 and 2
        self.assertEqual(sum(1 for c in kept if not c.get("_graph_evidence")), 15)

    def test_passages_behind_graph_connections_take_no_searched_passages_place(self):
        chunks = [_vector(i, 0.5 + i * 0.01) for i in range(20)]
        evidence = [{"id": "g:r:chunk:%d@10" % i, "text": "quote %d" % i, "metadata": {}, "distance": None,
                     "about": "A -[PAID]-> B", "about_keys": ["a", "b"], "_graph_evidence": True} for i in range(3)]
        debug = {}
        kept, _ = _service()._rerank_by_score(chunks, [{"key": "a"}], 15, 10, 80000, debug, graph_evidence=evidence)
        self.assertEqual(sum(1 for c in kept if c.get("_graph_evidence")), 3)
        self.assertEqual(sum(1 for c in kept if not c.get("_graph_evidence")), 15)
        self.assertEqual(debug["rerank"]["fusion"]["method"], "rrf")

    def test_a_graph_passage_from_a_chunk_already_found_is_folded_into_it(self):
        from services import retrieval_fusion
        chunks = [_vector(1, 0.6), _vector(2, 0.7)]
        evidence = [{"id": "f2:r:chunk:0@120", "text": "short", "metadata": {}, "about": "A -[PAID]-> B",
                     "about_keys": ["a"], "_graph_evidence": True}]
        pinned, fused, stats = retrieval_fusion.fuse(chunks, evidence, [{"key": "a"}])
        kept = retrieval_fusion.select(pinned, fused, 15, stats)
        # folding names what the chunk is the source of and adds no score: the closer chunk stays first
        self.assertEqual([c["id"] for c in kept], ["f1:r:chunk:0", "f2:r:chunk:0"])
        self.assertEqual(kept[1]["_about"], ["A -[PAID]-> B"])
        self.assertEqual(stats["graph_evidence_folded"], 1)

    def test_a_graph_passage_whose_chunk_is_cut_is_sent_on_its_own(self):
        from services import retrieval_fusion
        chunks = [_vector(i, 0.5 + i * 0.01) for i in range(20)]
        evidence = [{"id": "f19:r:chunk:0@120", "text": "short", "metadata": {}, "about": "A -[PAID]-> B",
                     "about_keys": ["a"], "_graph_evidence": True}]
        pinned, fused, stats = retrieval_fusion.fuse(chunks, evidence, [{"key": "a"}])
        kept = retrieval_fusion.select(pinned, fused, 15, stats)
        self.assertIn("f19:r:chunk:0@120", [c["id"] for c in kept])  # its chunk (rank 20) was not kept
        self.assertEqual(stats["graph_evidence_folded"], 0)

    def test_selected_documents_and_selected_phone_records_stay_first(self):
        from services import retrieval_fusion
        chunks = [_vector(1, 0.2), dict(_vector(2, 1.4), _doc_scoped=True),
                  {"id": "phone-selected:u1", "text": "chosen", "distance": 0.0, "metadata": {}}]
        pinned, fused, _ = retrieval_fusion.fuse(chunks, [], [])
        self.assertEqual([c["id"] for c in pinned], ["phone-selected:u1", "f2:r:chunk:0"])
        self.assertEqual([c["id"] for c in fused], ["f1:r:chunk:0"])


class ThresholdSpaceTests(unittest.TestCase):
    def test_similarity_reads_the_collections_space(self):
        from services.retrieval_fusion import collection_space, min_similarity, similarity

        class L2:
            configuration_json = {"hnsw": {"space": "l2"}}

        class Cosine:
            configuration_json = {}
            metadata = {"hnsw:space": "cosine"}

        self.assertEqual(collection_space(L2()), "l2")
        self.assertEqual(collection_space(Cosine()), "cosine")
        self.assertAlmostEqual(similarity(1.2, "l2"), 0.4)  # squared L2 of unit vectors = 2 - 2 cos
        self.assertAlmostEqual(similarity(0.6, "cosine"), 0.4)
        self.assertAlmostEqual(min_similarity(2.0), 0.0)

    def test_the_threshold_means_the_same_in_a_cosine_collection(self):
        import services.rag_service as rag
        from unittest.mock import patch

        class Vectors:
            def count_chunks(self):
                return 2

            def search_chunks(self, query_embedding, top_k, filter_metadata):
                # cosine distances 0.6 (cos 0.4) and 1.2 (cos -0.2)
                return [{"id": "a", "text": "a", "metadata": {}, "distance": 0.6},
                        {"id": "b", "text": "b", "metadata": {}, "distance": 1.2}]

        class Embeddings:
            def generate_embedding(self, text):
                return [1.0]

        service = _service()
        service._chunk_space_cache = "cosine"
        with patch.object(rag, "VECTOR_DB_AVAILABLE", True), patch.object(rag, "vector_db_service", Vectors()), \
                patch.object(rag, "embedding_service", Embeddings()):
            found = service._retrieve_chunks_by_meaning("q", "case", confidence_threshold=2.0, debug_log={})
        # 2.0 keeps cosine similarity >= 0: the cosine distance 1.2 (cos -0.2) is dropped
        self.assertEqual([c["id"] for c in found], ["a"])


if __name__ == "__main__":
    unittest.main()
