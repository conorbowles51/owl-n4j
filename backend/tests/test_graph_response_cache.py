"""Graph and Timeline responses are served again, as compressed bytes, only while the graph is unchanged."""
import contextlib
import gzip
import json
import unittest
from unittest.mock import patch

from services.financial.view_cache import json_response
from services.neo4j import graph_response_cache
from services.neo4j.graph_response_cache import cached_json, keys_digest


class GraphResponseCacheTests(unittest.TestCase):
    def setUp(self):
        graph_response_cache.graph_responses.clear()
        self.bookmark = ["b1"]
        self.calls = 0
        session = patch.object(graph_response_cache.driver, "session", side_effect=lambda: contextlib.nullcontext(object()))
        bookmark = patch("services.neo4j.graph_read_cache.graph_bookmark", side_effect=lambda _s: (self.bookmark[0],))
        session.start(); bookmark.start()
        self.addCleanup(session.stop); self.addCleanup(bookmark.stop)

    def compute(self):
        self.calls += 1
        return {"nodes": [{"key": "a", "name": "Ação", "n": self.calls}], "links": [], "total": 1.5}

    def test_repeat_is_served_from_saved_bytes_identical_to_the_route_response(self):
        first = cached_json(("graph", "c1"), self.compute, "gzip, deflate")
        second = cached_json(("graph", "c1"), self.compute, "gzip")
        self.assertEqual(self.calls, 1)
        self.assertEqual(first.headers["content-encoding"], "gzip")
        self.assertEqual(first.body, second.body)
        expected = json_response({"nodes": [{"key": "a", "name": "Ação", "n": 1}], "links": [], "total": 1.5}).body
        self.assertEqual(gzip.decompress(second.body), expected)

    def test_client_without_gzip_gets_the_plain_body(self):
        cached_json(("graph", "c1"), self.compute, "gzip")
        plain = cached_json(("graph", "c1"), self.compute, None)
        self.assertNotIn("content-encoding", plain.headers)
        self.assertEqual(json.loads(plain.body)["nodes"][0]["n"], 1)

    def test_a_committed_write_reads_again(self):
        cached_json(("graph", "c1"), self.compute, "gzip")
        self.bookmark[0] = "b2"
        again = cached_json(("graph", "c1"), self.compute, "gzip")
        self.assertEqual(self.calls, 2)
        self.assertEqual(json.loads(gzip.decompress(again.body))["nodes"][0]["n"], 2)

    def test_other_parameters_or_significant_keys_read_again(self):
        cached_json(("graph", "c1", keys_digest(["a"])), self.compute, "gzip")
        cached_json(("graph", "c1", keys_digest(["a", "b"])), self.compute, "gzip")
        cached_json(("graph", "c2", keys_digest(["a"])), self.compute, "gzip")
        self.assertEqual(self.calls, 3)
        self.assertIsNone(keys_digest(None))


if __name__ == "__main__":
    unittest.main()
