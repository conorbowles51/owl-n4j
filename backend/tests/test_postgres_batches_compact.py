"""Migration 20261031_batches_compact: compacts financial_import_batches, never fails a release on a held lock."""
import contextlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

import sqlalchemy as sa

PATH = Path(__file__).resolve().parents[1] / 'postgres/alembic/versions/20261031_batches_compact.py'


def _load():
    spec = importlib.util.spec_from_file_location('batches_compact', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Bind:
    def __init__(self, vacuum_errors):
        self.dialect = mock.Mock()
        self.dialect.name = 'postgresql'
        self.vacuum_errors = list(vacuum_errors)
        self.statements = []

    def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        if text.startswith('VACUUM') and self.vacuum_errors:
            raise self.vacuum_errors.pop(0)
        return mock.Mock(scalar=mock.Mock(return_value=100))


def _lock_timeout():
    return sa.exc.OperationalError('VACUUM', {}, Exception('canceling statement due to lock timeout'))


class BatchesCompactTest(unittest.TestCase):
    def run_upgrade(self, bind):
        module = _load()
        context = mock.Mock(autocommit_block=contextlib.nullcontext)
        with mock.patch.object(module, 'op') as op, mock.patch.object(module.time, 'sleep'):
            op.get_bind.return_value = bind
            op.get_context.return_value = context
            module.upgrade()
        return module

    def test_follows_the_statistics_migration(self):
        module = _load()
        self.assertEqual((module.revision, module.down_revision),
                         ('20261031_batches_compact', '20261031_slow_pool_wait'))

    def test_compacts_with_a_short_lock_wait(self):
        bind = Bind([])
        self.run_upgrade(bind)
        self.assertIn("SET lock_timeout = '2s'", bind.statements)
        self.assertIn('VACUUM (FULL, ANALYZE) financial_import_batches', bind.statements)
        self.assertEqual(bind.statements[-1], "SELECT pg_relation_size('financial_import_batches')")

    def test_a_held_table_is_tried_again_then_skipped_without_failing(self):
        tries = _load().TRIES
        self.assertGreaterEqual(tries, 20)
        bind = Bind([_lock_timeout() for _ in range(tries)])
        self.run_upgrade(bind)
        self.assertEqual(sum(s.startswith('VACUUM') for s in bind.statements), tries)
        self.assertEqual(bind.statements.count('RESET lock_timeout'), tries)

    def test_a_lock_free_retry_compacts(self):
        bind = Bind([_lock_timeout()])
        self.run_upgrade(bind)
        self.assertEqual(sum(s.startswith('VACUUM') for s in bind.statements), 2)

    def test_any_other_error_fails_the_migration(self):
        bind = Bind([sa.exc.OperationalError('VACUUM', {}, Exception('disk full'))])
        with self.assertRaises(sa.exc.OperationalError):
            self.run_upgrade(bind)


if __name__ == '__main__':
    unittest.main()
