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

    def test_a_value_json_cannot_hold_is_a_server_error_not_a_bad_request(self):
        with self.assertRaises(RuntimeError):
            cached_json(("graph", "nan"), lambda: {"total": float("nan")}, "gzip")


class WarmedPageTests(unittest.TestCase):
    """The release's warm-up fills the very key the Graph and Timeline pages ask for (view_warmup)."""

    def setUp(self):
        graph_response_cache.graph_responses.clear()
        self.addCleanup(graph_response_cache.graph_responses.clear)
        self.calls = []
        session = patch.object(graph_response_cache.driver, "session", side_effect=lambda: contextlib.nullcontext(object()))
        bookmark = patch("services.neo4j.graph_read_cache.graph_bookmark", side_effect=lambda _s: ("b1",))
        session.start(); bookmark.start()
        self.addCleanup(session.stop); self.addCleanup(bookmark.stop)

    def read(self, name):
        def run(**kwargs):
            self.calls.append((name, kwargs))
            return {"read": name}
        return run

    def test_the_graph_page_after_the_warm_up_is_served_without_a_read(self):
        from routers import graph
        case = "d5b330d1-b3fe-4b03-8539-98d9cc3115e0"
        with patch.object(graph.neo4j_service, "get_graph_structure", side_effect=self.read("graph")):
            graph.warm_graph_page(__import__("uuid").UUID(case))
            response = graph.get_graph(case_id=case, start_date=None, end_date=None, lightweight=True, limit=None,
                                       sort_by=None, scope="all", request=None, db=None, user={})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads(response.body), {"read": "graph"})
        self.assertEqual(self.calls[0][1], dict(case_id=case, start_date=None, end_date=None, limit=None,
                                                sort_by=None, entity_keys=None))

    def test_the_timeline_page_after_the_warm_up_is_served_without_a_read(self):
        import uuid
        from routers import timeline
        case = uuid.UUID("d5b330d1-b3fe-4b03-8539-98d9cc3115e0")
        with patch.object(timeline.neo4j_service, "get_timeline_whole", side_effect=self.read("timeline")), \
                patch.object(timeline, "get_case_if_allowed"):
            timeline.warm_timeline_page(case)
            response = timeline.get_timeline(types=None, start_date=None, end_date=None, case_id=case, limit=500,
                                             cursor=None, scope="all", whole=True, request=None, db=None,
                                             current_user=None)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(json.loads(response.body), {"read": "timeline"})
        self.assertEqual(self.calls[0][1], dict(event_types=None, start_date=None, end_date=None, case_id=str(case)))

    def test_a_timeline_above_the_ceiling_is_a_refusal_for_the_warm_up_and_nothing_is_saved(self):
        import uuid
        from fastapi import HTTPException
        from routers import timeline
        from services.neo4j.timeline_service import TimelineTooLarge
        with patch.object(timeline.neo4j_service, "get_timeline_whole",
                          side_effect=TimelineTooLarge("Timeline has 250,000 events; the whole-Timeline limit is 200,000")):
            with self.assertRaises(HTTPException) as refused:
                timeline.warm_timeline_page(uuid.UUID("d5b330d1-b3fe-4b03-8539-98d9cc3115e0"))
        self.assertEqual(refused.exception.status_code, 422)
        self.assertIn("250,000 events", refused.exception.detail)
        self.assertIn("nothing saved", refused.exception.detail)
        self.assertEqual(len(graph_response_cache.graph_responses._entries), 0)

if __name__ == "__main__":
    unittest.main()
