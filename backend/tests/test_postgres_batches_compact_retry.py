"""Migration 20261031_batches_compact_retry: compacts only in a moment nobody holds the table; rows proven unchanged."""
import contextlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

import sqlalchemy as sa

PATH = Path(__file__).resolve().parents[1] / 'postgres/alembic/versions/20261031_batches_compact_retry.py'


def _load():
    spec = importlib.util.spec_from_file_location('batches_compact_retry', PATH)
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
    """Fake connection: holders per poll, VACUUM outcomes, rows before/after."""

    def __init__(self, holders=(), vacuum_errors=(), rows_after=None):
        self.dialect = mock.Mock()
        self.dialect.name = 'postgresql'
        self.holders = list(holders)
        self.vacuum_errors = list(vacuum_errors)
        self.rows = [('b1', 'd1', 't1'), ('b2', 'd2', 't2')]
        self.rows_after = rows_after
        self.statements = []

    def execute(self, statement):
        text = str(statement)
        self.statements.append(text)
        result = mock.Mock()
        if 'FROM pg_locks' in text:
            result.scalar.return_value = self.holders.pop(0) if self.holders else 0
        elif text.startswith('VACUUM'):
            if self.vacuum_errors:
                raise self.vacuum_errors.pop(0)
            if self.rows_after is not None:
                self.rows = self.rows_after
        elif 'md5(b::text)' in text:
            result.all.return_value = list(self.rows)
        else:
            result.scalar.return_value = 100
        return result


def _lock_timeout():
    return sa.exc.OperationalError('VACUUM', {}, Exception('canceling statement due to lock timeout'))


class BatchesCompactRetryTest(unittest.TestCase):
    def run_upgrade(self, bind):
        module = _load()
        clock = Clock()
        context = mock.Mock(autocommit_block=contextlib.nullcontext)
        with mock.patch.object(module, 'op') as op, mock.patch.object(module, 'time', clock):
            op.get_bind.return_value = bind
            op.get_context.return_value = context
            module.upgrade()
        return clock

    def vacuums(self, bind):
        return sum(s.startswith('VACUUM') for s in bind.statements)

    def test_follows_the_first_try(self):
        module = _load()
        self.assertEqual((module.revision, module.down_revision),
                         ('20261031_batches_compact_retry', '20261031_batches_compact'))

    def test_never_asks_for_the_lock_while_another_session_holds_the_table(self):
        bind = Bind(holders=[2, 1, 1, 0])
        self.run_upgrade(bind)
        self.assertEqual(self.vacuums(bind), 1)
        first_vacuum = next(i for i, s in enumerate(bind.statements) if s.startswith('VACUUM'))
        polls = [i for i, s in enumerate(bind.statements) if 'FROM pg_locks' in s]
        self.assertEqual(len([i for i in polls if i < first_vacuum]), 4)
        self.assertIn("SET lock_timeout = '1s'", bind.statements)

    def test_a_held_table_for_the_whole_window_is_skipped_without_failing(self):
        bind = Bind(holders=[1] * 100000)
        with mock.patch('builtins.print') as printed:
            clock = self.run_upgrade(bind)
        self.assertEqual(self.vacuums(bind), 0)
        self.assertGreaterEqual(clock.now, _load().WINDOW_SECONDS)
        self.assertIn('0 tries for the lock', printed.call_args[0][0])
        self.assertIn('rows unchanged', printed.call_args[0][0])

    def test_every_lost_race_is_reported_as_tries_not_as_a_held_table(self):
        bind = Bind(vacuum_errors=[_lock_timeout()] * 100000)
        with mock.patch('builtins.print') as printed:
            self.run_upgrade(bind)
        line = printed.call_args[0][0]
        self.assertIn('0 polls found the table held', line)
        self.assertIn('%d tries for the lock' % self.vacuums(bind), line)

    def test_a_lost_race_for_the_lock_is_tried_again(self):
        bind = Bind(vacuum_errors=[_lock_timeout(), _lock_timeout()])
        self.run_upgrade(bind)
        self.assertEqual(self.vacuums(bind), 3)
        self.assertEqual(bind.statements.count('RESET lock_timeout'), 3)

    def run_printed(self, bind):
        with mock.patch('builtins.print') as printed:
            self.run_upgrade(bind)
        return printed.call_args[0][0]

    def test_rows_are_checked_just_before_and_after_the_compaction(self):
        bind = Bind()
        line = self.run_printed(bind)
        reads = [i for i, s in enumerate(bind.statements) if 'md5(b::text)' in s]
        vacuum = next(i for i, s in enumerate(bind.statements) if s.startswith('VACUUM'))
        self.assertEqual(len(reads), 2)
        self.assertTrue(reads[0] < vacuum < reads[1])
        self.assertIn('2 rows before, 2 after, 2 identical; changed by a writer: none; added: none; removed: none', line)

    def test_a_row_a_writer_changed_or_added_is_listed_not_fatal(self):
        line = self.run_printed(Bind(rows_after=[('b1', 'd1', 't1'), ('b2', 'dX', 't9'), ('b3', 'd3', 't8')]))
        self.assertIn("2 rows before, 3 after, 1 identical; changed by a writer: [('b2', 't9')]; "
                      "added: [('b3', 't8')]; removed: none", line)

    def test_a_row_a_writer_removed_is_listed_not_fatal(self):
        line = self.run_printed(Bind(rows_after=[('b1', 'd1', 't1')]))
        self.assertIn("2 rows before, 1 after, 1 identical; changed by a writer: none; added: none; removed: ['b2']",
                      line)

    def test_any_other_error_fails_the_migration(self):
        with self.assertRaises(sa.exc.OperationalError):
            self.run_upgrade(Bind(vacuum_errors=[sa.exc.OperationalError('VACUUM', {}, Exception('disk full'))]))


if __name__ == '__main__':
    unittest.main()
