"""The engine keeps recent document readings pickled and only the documents in use live."""
import gc
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from services.financial import statement_engine as engine
from tests.test_financial_statement_engine import mx_statement, card_statement, MOVES


class EngineReadingCacheTests(unittest.TestCase):
    def setUp(self):
        engine._READINGS.clear()
        engine._LIVE_READINGS.clear()

    def tearDown(self):
        engine._READINGS.clear()
        engine._LIVE_READINGS.clear()

    def test_readings_are_kept_pickled_and_only_documents_in_use_stay_live(self):
        documents = [mx_statement(MOVES), card_statement(), mx_statement(MOVES, closing='1,250.00')]
        first = engine.read_statements(documents[0])
        # The document in use is answered from its live reading: nothing is read or decoded again.
        with patch.object(engine, '_read_statements', side_effect=AssertionError('read again')), \
                patch.object(engine.pickle, 'loads', side_effect=AssertionError('decoded again')):
            self.assertIs(engine.read_statements(documents[0]), first)
        engine.read_statements(documents[1])
        engine.read_statements(documents[2])
        self.assertEqual(len(engine._READINGS), 3)
        self.assertTrue(all(isinstance(value, bytes) for value in engine._READINGS.values()))
        self.assertEqual(len(engine._LIVE_READINGS), engine.LIVE_READINGS)
        # A document no longer live is decoded from its pickle, never read again, and reads the same.
        with patch.object(engine, '_read_statements', side_effect=AssertionError('read again')):
            again = engine.read_statements(documents[0])
        self.assertIsNot(again, first)
        self.assertEqual(again, first)
        self.assertEqual(len(engine._LIVE_READINGS), engine.LIVE_READINGS)

    def test_the_pickled_cache_is_bounded(self):
        with patch.object(engine, 'READINGS_KEPT', 2):
            for closing in ('1,250.00', '1,260.00', '1,270.00'):
                engine.read_statements(mx_statement(MOVES, closing=closing))
        self.assertEqual(len(engine._READINGS), 2)

    def test_a_document_without_revisions_is_not_cached(self):
        sources = mx_statement(MOVES)
        for source in sources:
            source['source_revision'] = None
        engine.read_statements(sources)
        self.assertEqual((len(engine._READINGS), len(engine._LIVE_READINGS)), (0, 0))


class StartupFreezeTests(unittest.TestCase):
    def test_startup_objects_are_excluded_from_later_collections(self):
        # In a separate interpreter: freezing is process-wide.
        code = ('import gc; from services.process_memory import freeze_startup_objects\n'
                'held = [{"k": [i]} for i in range(1000)]\n'
                'frozen = freeze_startup_objects()\n'
                'assert frozen >= 1000 and gc.get_freeze_count() == frozen\n'
                'assert not any(o is held for o in gc.get_objects())\n'
                'later = [[i] for i in range(10)]\n'
                'assert any(o is later for o in gc.get_objects())\n'
                'print("ok")')
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.stdout.strip(), 'ok', result.stderr)


if __name__ == '__main__':
    unittest.main()
