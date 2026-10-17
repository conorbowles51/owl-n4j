"""One log line per import with the seconds of each step (import_batches.IMPORT_TIMING).

Synthetic data only (the batch import fixture's one-statement PDF). The line
names fixed steps and counts only, never case or financial values, so the
first live import after a deploy reports its end-to-end time with no extra
work.
"""
import re
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import select

from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial import request_timing
from services.financial.row_versions import RowValues
from tests import test_financial_import_batches as fixtures
from tests.test_financial_row_versions import FakePostgres, Record

STEPS = ('claim', 'accept_read', 'writer_locks', 'writer_read', 'existing_check', 'duplicate_decision', 'checks',
         'write_account', 'write_source_document', 'write_period', 'write_transactions', 'reconcile', 'commit',
         'run_record', 'graph_request', 'own_readiness', 'writer_rest', 'record_outcome')
LOGGER = 'services.financial.import_batches'


class ImportTimingLineTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.BatchImportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.f = self.fixture.f
        self.batch = self.fixture.create()
        self.fixture.advance(self.batch)
        with self.f.SessionLocal() as db:
            batches.queue_import(db, case_id=self.f.case.id, batch_id=self.batch,
                expected_revision=self.fixture.status(self.batch)['ready_revision'], actor=self.f.actor)
            self.item = db.scalar(select(Item.id).where(Item.batch_id == self.batch))

    def run_import(self):
        batches._import_item(self.f.SessionLocal, self.f.case.id, self.batch, self.item, Path)

    def timing_lines(self, records):
        return [r.getMessage() for r in records if r.getMessage().startswith('Financial import timing')]

    def test_an_import_logs_every_step_once_on_sqlite(self):
        with self.assertLogs(LOGGER, 'INFO') as logs:
            self.run_import()
        lines = self.timing_lines(logs.records)
        self.assertEqual(len(lines), 1, lines)
        line = lines[0]
        self.assertTrue(line.startswith(f'Financial import timing (item {str(self.item)[:8]}, imported): total '), line)
        steps = dict(re.findall(r'(\w+) (\d+\.\d{3})', line.split(': ', 1)[1]))
        for step in STEPS:
            self.assertIn(step, steps, line)
        total = float(re.search(r'total (\d+\.\d+) s', line).group(1))
        laps = sum(float(steps[step]) for step in STEPS)
        self.assertLessEqual(laps, total + 0.02)
        counts = dict(re.findall(r'(sql(?:_writes)?) (\d+)', line))
        self.assertGreater(int(counts['sql']), int(counts['sql_writes']))
        self.assertGreater(int(counts['sql_writes']), 0)
        # Fixed step names and counts only: no file name, holder or amount.
        self.assertIsNone(re.search(r'[A-Z][a-z]+ [A-Z][a-z]+|\.pdf|\$', line.split(': ', 1)[1]))

    def test_a_statement_no_longer_pending_logs_nothing(self):
        self.run_import()
        with self.assertNoLogs(LOGGER, 'INFO'):
            self.run_import()

    def test_switch_off_logs_nothing(self):
        with patch.object(batches, 'IMPORT_TIMING', False), self.assertNoLogs(LOGGER, 'INFO'):
            self.run_import()
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, self.item).status, 'imported')

    def test_a_failed_import_reports_the_failed_writer(self):
        with patch.object(batches, 'confirm_statement_import', side_effect=RuntimeError('synthetic')), \
                self.assertLogs(LOGGER, 'INFO') as logs:
            self.run_import()
        line = self.timing_lines(logs.records)[0]
        self.assertIn('(item ' + str(self.item)[:8] + ', attention)', line)
        self.assertIn('writer_failed', line)


class TimingOnPostgresTests(TestCase):
    """The stub PostgreSQL session of the row-version tests: reused and re-read rows reach the line."""

    def test_row_version_reuse_is_counted(self):
        cache, session = RowValues(Record), FakePostgres({1: ('a', '10', 'one'), 2: ('a', '11', 'two')})
        read = lambda: cache.rows(session, (Record.id, Record.owner), (Record.metadata_['value'].label('value'),),
                                  (Record.owner == 'a',), order_by=Record.id)
        with request_timing.recording() as first:
            read()
        session.table[2] = ('a', '12', 'changed')
        with request_timing.recording() as second:
            request_timing.lap('existing_check')
            read()
        self.assertEqual(first.counts, dict(rows_reused=0, rows_reread=2))
        self.assertEqual(second.counts, dict(rows_reused=1, rows_reread=1))
        self.assertRegex(request_timing.summary(second),
                         r'^total \d+\.\d\d s: existing_check \d+\.\d{3}; rows_reused 1, rows_reread 1$')

    def test_outside_a_recorder_nothing_is_kept(self):
        request_timing.lap('claim')
        request_timing.count('sql')
        self.assertIsNone(request_timing._current.get())
