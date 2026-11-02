"""Migration 20261102_batches_status_index: the batch polls get an index on status, built only in a moment nobody
holds the table, never failing a release."""
import contextlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

import sqlalchemy as sa

from postgres.models.financial_import_batches import FinancialImportBatch

PATH = Path(__file__).resolve().parents[1] / 'postgres/alembic/versions/20261102_batches_status_index.py'


def _load():
    spec = importlib.util.spec_from_file_location('batches_status_index', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Bind:
    def __init__(self, holders=(), create_errors=(), exists=0):
        self.dialect = mock.Mock()
        self.dialect.name = 'postgresql'
        self.holders = list(holders)
        self.create_errors = list(create_errors)
        self.exists = exists
        self.statements = []

    def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        result = mock.Mock()
        if 'FROM pg_locks' in text:
            result.scalar.return_value = self.holders.pop(0) if self.holders else 0
        elif 'FROM pg_indexes' in text:
            result.scalar.return_value = self.exists
        elif text.startswith('CREATE INDEX') and self.create_errors:
            raise self.create_errors.pop(0)
        return result


def _lock_timeout():
    return sa.exc.OperationalError('CREATE INDEX', {}, Exception('canceling statement due to lock timeout'))


class BatchesStatusIndexTest(unittest.TestCase):
    def run_upgrade(self, bind):
        module = _load()
        context = mock.Mock(autocommit_block=contextlib.nullcontext)
        with mock.patch.object(module, 'op') as op, mock.patch.object(module, 'time', Clock()):
            op.get_bind.return_value = bind
            op.get_context.return_value = context
            module.upgrade()

    def creates(self, bind):
        return [s for s in bind.statements if s.startswith('CREATE INDEX')]

    def test_follows_the_head_and_the_model_declares_the_index(self):
        module = _load()
        self.assertEqual(module.down_revision, '20261101_users_password_changed_at')
        names = {index.name: [c.name for c in index.columns] for index in FinancialImportBatch.__table__.indexes}
        self.assertEqual(names.get('ix_financial_import_batches_status'), ['status'])

    def test_waits_for_a_moment_nobody_holds_the_table_then_builds_once(self):
        bind = Bind(holders=[1, 2, 0])
        self.run_upgrade(bind)
        self.assertEqual(self.creates(bind),
                         ['CREATE INDEX IF NOT EXISTS ix_financial_import_batches_status ON financial_import_batches '
                          '(status)'])
        first = bind.statements.index(self.creates(bind)[0])
        self.assertEqual(sum('FROM pg_locks' in s for s in bind.statements[:first]), 3)
        self.assertIn("SET lock_timeout = '1s'", bind.statements)
        self.assertEqual(bind.statements[first + 1], 'RESET lock_timeout')

    def test_a_lock_timeout_tries_again(self):
        bind = Bind(create_errors=[_lock_timeout()])
        self.run_upgrade(bind)
        self.assertEqual(len(self.creates(bind)), 2)

    def test_a_table_held_for_the_whole_window_skips_the_index_and_says_so(self):
        bind = Bind(holders=[1] * 10000)
        with mock.patch('builtins.print') as printed:
            self.run_upgrade(bind)
        self.assertEqual(self.creates(bind), [])
        self.assertIn('not created in 300 s', printed.call_args[0][0])

    def test_an_existing_index_is_left_alone(self):
        bind = Bind(exists=1)
        self.run_upgrade(bind)
        self.assertEqual(self.creates(bind), [])
        self.assertFalse(any('FROM pg_locks' in s for s in bind.statements))

    def test_other_errors_fail_the_migration(self):
        bind = Bind(create_errors=[sa.exc.OperationalError('CREATE INDEX', {}, Exception('disk full'))])
        with self.assertRaises(sa.exc.OperationalError):
            self.run_upgrade(bind)


if __name__ == '__main__':
    unittest.main()
