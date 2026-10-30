"""A graph read is reused only while the database has committed nothing since it
was read, and never when something committed while it was being read."""

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.neo4j.graph_read_cache import GraphReadCache, graph_bookmark


class _Graph:
    """A database whose last committed transaction the test moves by hand."""

    def __init__(self):
        self.tx = 1


class _Session:
    def __init__(self, graph):
        self.graph = graph
        self._seen = None

    def run(self, query, **params):
        self._seen = self.graph.tx
        return SimpleNamespace(consume=lambda: None)

    def last_bookmarks(self):
        return SimpleNamespace(raw_values=[f"FB:{self._seen}"])


class GraphReadCacheTests(unittest.TestCase):
    def setUp(self):
        self.graph = _Graph()
        self.session = _Session(self.graph)
        self.cache = GraphReadCache()
        self.calls = 0

    def compute(self, during=None):
        def run():
            self.calls += 1
            if during:
                during()
            return {"rows": [{"key": "a", "n": self.graph.tx}], "calls": self.calls}
        return run

    def test_bookmark_is_the_last_committed_transaction(self):
        self.assertEqual(graph_bookmark(self.session), ("FB:1",))
        self.graph.tx = 2
        self.assertEqual(graph_bookmark(self.session), ("FB:2",))

    def test_reused_while_nothing_committed(self):
        first = self.cache.read(self.session, "k", self.compute())
        second = self.cache.read(self.session, "k", self.compute())
        self.assertEqual(first, second)
        self.assertEqual(self.calls, 1)

    def test_any_commit_reads_again(self):
        self.cache.read(self.session, "k", self.compute())
        self.graph.tx = 2
        again = self.cache.read(self.session, "k", self.compute())
        self.assertEqual(self.calls, 2)
        self.assertEqual(again["rows"][0]["n"], 2)

    def test_commit_during_the_read_is_not_saved(self):
        def write():
            self.graph.tx = 2
        self.cache.read(self.session, "k", self.compute(during=write))
        self.cache.read(self.session, "k", self.compute())
        self.assertEqual(self.calls, 2)
        self.assertEqual(self.cache.stats["changed_during_read"], 1)

    def test_callers_get_independent_copies(self):
        first = self.cache.read(self.session, "k", self.compute())
        first["rows"][0]["locator"] = "added by the caller"
        second = self.cache.read(self.session, "k", self.compute())
        second["rows"].clear()
        third = self.cache.read(self.session, "k", self.compute())
        self.assertEqual(third["rows"], [{"key": "a", "n": 1}])

    def test_keys_are_separate(self):
        self.cache.read(self.session, ("transactions", "case-a"), self.compute())
        self.cache.read(self.session, ("transactions", "case-b"), self.compute())
        self.assertEqual(self.calls, 2)

    def test_oldest_dropped_when_over_the_byte_limit(self):
        cache = GraphReadCache(max_bytes=1)
        cache.read(self.session, "k", self.compute())
        cache.read(self.session, "k", self.compute())
        self.assertEqual(self.calls, 2)
        self.assertEqual(cache.stats["too_large"], 2)

    def test_least_recently_used_is_dropped_first(self):
        from services.neo4j import graph_read_cache as module
        one = len(module._pack({"rows": [{"key": "a", "n": 1}], "calls": 1}))
        cache = GraphReadCache(max_bytes=one * 2 + one // 2)
        for key in ("a", "b"):
            cache.read(self.session, key, self.compute())
        cache.read(self.session, "a", self.compute())   # a is now the most recent
        cache.read(self.session, "c", self.compute())   # drops b
        calls = self.calls
        cache.read(self.session, "a", self.compute())
        cache.read(self.session, "c", self.compute())
        self.assertEqual(self.calls, calls)
        cache.read(self.session, "b", self.compute())
        self.assertEqual(self.calls, calls + 1)

    def test_a_failed_read_saves_nothing_and_the_next_call_reads(self):
        def boom():
            raise RuntimeError("database unavailable")
        with self.assertRaises(RuntimeError):
            self.cache.read(self.session, "k", boom)
        self.cache.read(self.session, "k", self.compute())
        self.assertEqual(self.calls, 1)

    def test_a_value_that_cannot_be_kept_is_still_returned(self):
        value = {"big": 2 ** 70}
        with self.assertLogs("services.neo4j.graph_read_cache", level="ERROR"):
            self.assertEqual(self.cache.read(self.session, "k", lambda: value), value)
        self.assertEqual(self.cache.stats["saved"], 0)

    def test_a_call_after_a_commit_waits_for_the_older_read_and_never_gets_its_result(self):
        release = threading.Event()
        entered = threading.Event()
        running = []

        def slow():
            running.append("old")
            entered.set()
            release.wait(5)
            running.remove("old")
            return {"rows": ["old"]}

        def new():
            self.assertEqual(running, [], "two reads of one key ran at once")
            return {"rows": ["new"]}

        first, second = [], []
        t = threading.Thread(target=lambda: first.append(self.cache.read(_Session(self.graph), "k", slow)))
        t.start()
        entered.wait(5)
        self.graph.tx = 2  # a write committed while the first read is running
        u = threading.Thread(target=lambda: second.append(self.cache.read(_Session(self.graph), "k", new)))
        u.start()
        time.sleep(0.2)
        self.assertEqual(second, [])  # still waiting for the older read
        release.set()
        t.join(); u.join()
        self.assertEqual(first, [{"rows": ["old"]}])
        self.assertEqual(second, [{"rows": ["new"]}])

    def test_a_failed_read_is_shared_with_its_waiters_instead_of_read_again_by_each(self):
        """Live d5b330d1: each waiter of a timed-out read read again at once, and the concurrent
        reads timed out in turn, so the case's financial graph kept answering 503."""
        started = threading.Event()

        def failing():
            self.calls += 1
            started.set()
            time.sleep(0.3)
            raise RuntimeError("transaction time limit")

        errors = []

        def call():
            try:
                self.cache.read(_Session(self.graph), "k", failing)
            except RuntimeError as exc:
                errors.append(str(exc))

        leader = threading.Thread(target=call)
        leader.start()
        started.wait(5)
        waiters = [threading.Thread(target=call) for _ in range(3)]
        for t in waiters:
            t.start()
        for t in [leader, *waiters]:
            t.join()
        self.assertEqual(self.calls, 1)
        self.assertEqual(errors, ["transaction time limit"] * 4)
        self.assertEqual(self.cache.stats["joined_failure"], 3)
        self.assertEqual(self.cache.read(self.session, "k", self.compute())["calls"], 2)  # the next call reads

    def test_concurrent_identical_reads_cost_one_read(self):
        started = threading.Event()

        def slow():
            self.calls += 1
            started.set()
            time.sleep(0.2)
            return {"rows": []}

        results = []
        threads = [
            threading.Thread(target=lambda: results.append(self.cache.read(_Session(self.graph), "k", slow)))
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(self.calls, 1)
        self.assertEqual(results, [{"rows": []}] * 4)
        self.assertEqual(self.cache.stats["hit"] + self.cache.stats["joined"], 3)


class PackingKeepsTypesTests(unittest.TestCase):
    def test_plain_rows_round_trip_exactly(self):
        from services.neo4j import graph_read_cache as module
        value = {"transactions": [{"amount": 1.0, "count": 1, "flag": True, "name": "Ω", "none": None,
                                   "nested": {"x": [0.1, -2, "3"]}}], "total": 1}
        blob = module._pack(value)
        self.assertEqual(blob[:1], b"J")
        back = module._unpack(blob)
        self.assertEqual(back, value)
        self.assertIs(type(back["transactions"][0]["amount"]), float)
        self.assertIs(type(back["transactions"][0]["count"]), int)
        self.assertIs(type(back["transactions"][0]["flag"]), bool)

    def test_values_json_would_change_are_pickled(self):
        from neo4j.time import Date
        from services.neo4j import graph_read_cache as module
        for value in ({"t": (1, 2)}, {"d": Date(2024, 1, 2)}, {1: "int key"}):
            blob = module._pack(value)
            self.assertEqual(blob[:1], b"P", value)
            back = module._unpack(blob)
            self.assertEqual(back, value)
            self.assertEqual(type(next(iter(back.values()))), type(next(iter(value.values()))))
        blob = module._pack({"x": float("nan")})
        self.assertEqual(blob[:1], b"P")
        self.assertNotEqual(module._unpack(blob)["x"], module._unpack(blob)["x"])  # still NaN


class FinancialServiceUsesTheCacheTests(unittest.TestCase):
    def test_filters_are_part_of_the_key(self):
        from importlib import import_module
        module = import_module("services.neo4j.financial_service")
        service = module.FinancialService()
        cache = GraphReadCache()
        graph = _Graph()
        reads = []

        def fake_read(session, case_id, types, start_date, end_date, categories, mode):
            reads.append((case_id, start_date, mode))
            return {"transactions": [], "total": 0}

        class _Driver:
            def session(self):
                return _CM()

        class _CM:
            def __enter__(self):
                return _Session(graph)

            def __exit__(self, *exc):
                return False

        with patch.object(module, "driver", _Driver()), patch.object(module, "financial_graph_reads", cache), \
                patch.object(service, "_read_financial_transactions", side_effect=fake_read):
            service.get_financial_transactions(case_id="c")
            service.get_financial_transactions(case_id="c")
            service.get_financial_transactions(case_id="c", start_date="2024-01-01")
            service.get_financial_transactions(case_id="c", mode="intelligence")
            graph.tx = 2
            service.get_financial_transactions(case_id="c")
        with patch.object(module, "driver", _Driver()), patch.object(module, "financial_graph_reads", cache), \
                patch.object(service, "_read_financial_entities", side_effect=lambda session, case_id: [{"key": case_id}]) as ent:
            self.assertEqual(service.get_financial_entities("c"), [{"key": "c"}])
            self.assertEqual(service.get_financial_entities("c"), [{"key": "c"}])
            service.get_financial_entities("d")
        self.assertEqual(ent.call_count, 2)
        self.assertEqual(reads, [
            ("c", None, "transactions"),
            ("c", "2024-01-01", "transactions"),
            ("c", None, "intelligence"),
            ("c", None, "transactions"),
        ])


if __name__ == "__main__":
    unittest.main()
