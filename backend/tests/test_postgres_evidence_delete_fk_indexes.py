"""Migration 20261109_evidence_delete_fk_indexes: every column that points at evidence_files has an index, so
deleting a file never reads a whole table (a 5,000-file purge took 807.5 s on 9 Nov, holding the case audit lock)."""
import contextlib
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

import sqlalchemy as sa

import postgres.models  # noqa: F401  (registers every table)
from postgres.base import Base

PATH = Path(__file__).resolve().parents[1] / 'postgres/alembic/versions/20261109_evidence_delete_fk_indexes.py'


def _load():
    spec = importlib.util.spec_from_file_location('evidence_delete_fk_indexes', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns_pointing_at_evidence_files():
    found = set()
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == 'evidence_files':
                found.add((table.name, fk.parent.name))
    return found


def _leading_columns(table):
    lead = {list(index.columns)[0].name for index in table.indexes if len(index.columns)}
    for constraint in table.constraints:
        if isinstance(constraint, (sa.UniqueConstraint, sa.PrimaryKeyConstraint)) and len(constraint.columns):
            lead.add(list(constraint.columns)[0].name)
    return lead


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

    def execute(self, statement, params=None):
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


class EvidenceDeleteFkIndexesTest(unittest.TestCase):
    def run_upgrade(self, bind):
        module = _load()
        context = mock.Mock(autocommit_block=contextlib.nullcontext)
        with mock.patch.object(module, 'op') as op, mock.patch.object(module, 'time', Clock()):
            op.get_bind.return_value = bind
            op.get_context.return_value = context
            module.upgrade()

    def creates(self, bind):
        return [s for s in bind.statements if s.startswith('CREATE INDEX')]

    def test_every_column_pointing_at_evidence_files_leads_an_index(self):
        tables = {t.name: t for t in Base.metadata.sorted_tables}
        missing = sorted((t, c) for t, c in _columns_pointing_at_evidence_files() if c not in _leading_columns(tables[t]))
        self.assertEqual(missing, [], 'deleting an evidence file reads these whole tables; add an index')

    def test_the_migration_builds_the_index_each_model_declares(self):
        module = _load()
        self.assertEqual(module.down_revision, '20261109_significant_relationships')
        tables = {t.name: t for t in Base.metadata.sorted_tables}
        for table, column in module.INDEXES:
            names = {i.name: [c.name for c in i.columns] for i in tables[table].indexes}
            self.assertEqual(names.get('ix_%s_%s' % (table, column)), [column], table)
        self.assertIn(('evidence_upload_sessions', 'evidence_id'), module.INDEXES)

    def test_builds_each_index_once_when_nobody_holds_the_table(self):
        bind = Bind(holders=[1, 0])
        self.run_upgrade(bind)
        module = _load()
        self.assertEqual(len(self.creates(bind)), len(module.INDEXES))
        self.assertEqual(self.creates(bind)[0], 'CREATE INDEX IF NOT EXISTS ix_evidence_upload_sessions_evidence_id '
                                                'ON evidence_upload_sessions (evidence_id)')
        first = bind.statements.index(self.creates(bind)[0])
        self.assertEqual(bind.statements[first + 1], 'RESET lock_timeout')

    def test_a_lock_timeout_tries_again(self):
        error = sa.exc.OperationalError('CREATE INDEX', {}, Exception('canceling statement due to lock timeout'))
        bind = Bind(create_errors=[error])
        self.run_upgrade(bind)
        self.assertEqual(len(self.creates(bind)), len(_load().INDEXES) + 1)

    def test_a_table_held_for_the_whole_window_skips_and_says_so(self):
        bind = Bind(holders=[1] * 100000)
        with mock.patch('builtins.print') as printed:
            self.run_upgrade(bind)
        self.assertEqual(self.creates(bind), [])
        self.assertIn('not created in 300 s', printed.call_args_list[0][0][0])

    def test_existing_indexes_are_left_alone(self):
        bind = Bind(exists=1)
        self.run_upgrade(bind)
        self.assertEqual(self.creates(bind), [])

    def test_other_errors_fail_the_migration(self):
        bind = Bind(create_errors=[sa.exc.OperationalError('CREATE INDEX', {}, Exception('disk full'))])
        with self.assertRaises(sa.exc.OperationalError):
            self.run_upgrade(bind)


if __name__ == '__main__':
    unittest.main()
