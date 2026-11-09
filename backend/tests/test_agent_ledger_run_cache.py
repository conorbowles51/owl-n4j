"""One agent run reads a ledger capture once per scope while the rows it read are unchanged
(services.agent.ledger_run_cache); a changed row, a missing fingerprint or another database reads it again.
Every ledger view reads a shared capture without changing it: test_agent_financial_ledger_tools.SharedCaptureTests."""
import unittest
from unittest.mock import MagicMock, patch

CASE = "00000000-0000-0000-0000-0000000000aa"


class LedgerRunCacheTests(unittest.TestCase):
    def session(self):
        session = MagicMock()
        session.connection.return_value.dialect.name = "postgresql"
        return session

    def cache_with(self, fingerprints):
        from services.agent.ledger_run_cache import LedgerRunCache
        cache = LedgerRunCache()
        patches = [patch("services.financial.view_cache.fingerprint", side_effect=fingerprints),
                   patch("services.financial.view_cache._load_tables", return_value={"financial_transactions": "uuid"}),
                   patch("services.agent.ledger_run_cache.event")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return cache

    def test_an_unchanged_capture_is_read_once(self):
        cache = self.cache_with([("fp",), ("fp",)])
        captures = []

        def compute():
            captures.append(1)
            return {"available": True, "readings": [{"row": {"amount_minor": "5"}}]}
        session = self.session()
        first = cache.read(session, ("k",), CASE, self._recording(compute))
        second = cache.read(session, ("k",), CASE, compute)
        self.assertEqual(len(captures), 1)
        self.assertIs(second, first)
        self.assertEqual(cache.stats["hits"], 1)

    def test_a_changed_row_reads_the_capture_again(self):
        cache = self.cache_with([("fp1",), ("fp2",), ("fp2",)])
        values = iter([{"available": True, "v": 1}, {"available": True, "v": 2}])
        session = self.session()
        self.assertEqual(cache.read(session, ("k",), CASE, self._recording(lambda: next(values)))["v"], 1)
        self.assertEqual(cache.read(session, ("k",), CASE, self._recording(lambda: next(values)))["v"], 2)
        self.assertEqual(cache.stats["changed"], 1)

    def test_off_when_no_fingerprint_or_not_postgresql(self):
        cache = self.cache_with([None, None])
        session = self.session()
        calls = []
        cache.read(session, ("k",), CASE, self._recording(lambda: calls.append(1) or {"available": True}))
        cache.read(session, ("k",), CASE, self._recording(lambda: calls.append(1) or {"available": True}))
        self.assertEqual(len(calls), 2)
        sqlite = MagicMock()
        sqlite.connection.return_value.dialect.name = "sqlite"
        cache.read(sqlite, ("k",), CASE, lambda: calls.append(1) or {"available": True})
        self.assertEqual(len(calls), 3)

    @staticmethod
    def _recording(compute):
        """The SQL a capture runs names the tables it read (the cache records them through a cursor event)."""
        from services.agent import ledger_run_cache

        def run():
            listener = ledger_run_cache.event.listen.call_args[0][2]
            listener(None, None, "SELECT * FROM financial_transactions", None, None, False)
            return compute()
        return run


if __name__ == "__main__":
    unittest.main()
