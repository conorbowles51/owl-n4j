"""A held statement whose reading is current gets the details its account establishes, with no click.

A synthetic prepared statement is held only for its currency. The background round fills it as System
through the details save (stood in here, as in the queue-save tests), and the automatic-save round then saves
it through every gate. Pins: only current readings (the deployed reader's stamp, or its 'unchanged' mark),
only untouched statements, only when the fills answer every question, the switch, the per-state memo, and
the selection SQL on PostgreSQL.
"""
from copy import deepcopy
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import autofill_reapply as reapply
from services.financial import field_proposals
from services.financial import held_reprepare as held
from services.financial import import_batches as service
from services.financial import queue_save
from tests import test_financial_queue_save as queue_tests
from tests.test_financial_review_queue import CURRENCY

FILLS = dict(currency=dict(value='USD', confirmed=True, basis='account_ledger', field='currency',
                           label="account currency: same account's 3 saved statements, all USD; balances continue "
                                 "its saved statements"))
BALANCE = dict(message='The closing balance does not match the payments.', row_id=None, review_reason='balance')


class AutofillReapplyTests(queue_tests.FilledDetailsTests):

    def setUp(self):
        super().setUp()
        reapply._SEEN.clear()
        self.batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.advance(self.batch)
        self.item_id = self.hold_for_currency(self.batch)

    def sweep(self, fills=FILLS, fill=None):
        fill = fill or self.fake_fill(self.item_id)
        with patch.object(field_proposals, 'propose', return_value=dict(currency=dict(FILLS['currency'], basis='same_account'))), \
                patch.object(field_proposals, 'automatic_fills', return_value=fills), \
                patch.object(field_proposals, 'apply_confirmed_proposals', fill):
            return reapply.sweep(self.f.SessionLocal)

    def entry(self, change):
        with self.f.SessionLocal() as db:
            batch = db.get(Batch, self.batch)
            files = deepcopy(batch.files)
            change(files[0])
            batch.files = files
            db.commit()

    def status(self):
        with self.f.SessionLocal() as db:
            return db.get(Item, self.item_id).status

    def test_a_current_held_statement_is_filled_as_system_and_then_saved_by_the_backlog_round(self):
        report = self.sweep()
        self.assertEqual((report['statements'], report['filled'], report['failed']), (1, 1, 0))
        call, = self.fill_calls
        self.assertTrue(call['apply'])
        self.assertEqual(call['entries'][0]['proposals'], FILLS)
        self.assertEqual(self.status(), 'ready')
        with patch.object(queue_save, 'AUTO_SAVE_READY', True):
            saved = queue_save.sweep_backlog(self.f.SessionLocal)
        self.assertEqual(saved['queued'], 1, saved)
        self.assertEqual(self.status(), 'pending_import')

    def test_a_reading_by_an_older_reader_is_left_to_held_reprepare(self):
        self.entry(lambda e: e.update({held.STAMP: 'older-reader'}))
        self.assertEqual(self.sweep()['statements'], 0)
        self.assertEqual(self.fill_calls, [])
        # The deployed reader found it prepared exactly the same way: its keys are current.
        reapply._SEEN.clear()
        self.entry(lambda e: e.update({held.MARK: dict(stamp=held.preparation_stamp(), state=held.LEFT,
                                                       reason='unchanged')}))
        self.assertEqual(self.sweep()['filled'], 1)

    def test_a_statement_someone_worked_on_is_never_filled(self):
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            file.metadata_ = {**(file.metadata_ or {}), 'financial_review_progress': {'': dict(request={}, saved_by=dict(name='Alex'))}}
            db.commit()
        self.assertEqual(self.sweep()['statements'], 0)
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            file.metadata_ = {k: v for k, v in file.metadata_.items() if k != 'financial_review_progress'}
            item = db.get(Item, self.item_id)
            item.review_request = dict(currency='EUR')
            db.commit()
        reapply._SEEN.clear()
        self.assertEqual(self.sweep()['statements'], 0)
        self.assertEqual(self.fill_calls, [])

    def test_a_statement_with_another_question_is_not_filled(self):
        with self.f.SessionLocal() as db:
            item = db.get(Item, self.item_id)
            item.summary = dict(item.summary, problems=[CURRENCY, BALANCE], problem_count=2)
            db.commit()
        self.assertEqual(self.sweep()['statements'], 0)
        reapply._SEEN.clear()
        # Fills that do not answer the currency question either.
        with self.f.SessionLocal() as db:
            item = db.get(Item, self.item_id)
            item.summary = dict(item.summary, problems=[CURRENCY], problem_count=1)
            db.commit()
        self.assertEqual(self.sweep(fills={})['statements'], 0)
        self.assertEqual(self.fill_calls, [])

    def test_switch_off_and_a_paused_batch_fill_nothing(self):
        with patch.dict('os.environ', {'LOUPE_FINANCIAL_AUTOFILL_REAPPLY': '0'}):
            self.assertEqual(self.sweep()['considered'], 0)
        with self.f.SessionLocal() as db:
            db.get(Batch, self.batch).status = 'paused'
            db.commit()
        self.assertEqual(self.sweep()['considered'], 0)
        self.assertEqual(self.fill_calls, [])

    def test_an_unchanged_statement_is_decided_once_and_a_failure_is_retried(self):
        failing = lambda *a, **k: (_ for _ in ()).throw(RuntimeError('database lock'))
        self.assertEqual(self.sweep(fill=failing)['failed'], 1)
        self.assertEqual(self.status(), 'attention')
        # Failed: looked at again next round.
        self.assertEqual(self.sweep(fills={})['considered'], 1)
        # Decided (nothing to fill) for this state: not looked at again until it or the case changes.
        self.assertEqual(self.sweep(fills={})['considered'], 0)

    def test_the_selection_sql_compiles_for_postgres(self):
        with self.f.SessionLocal() as db:
            statements = []
            original = db.execute

            def capture(statement, *args, **kwargs):
                statements.append(statement)
                return original(statement, *args, **kwargs)
            with patch.object(db, 'execute', capture):
                reapply.held_candidates(db)
        sql = str(statements[0].compile(dialect=postgresql.dialect()))
        self.assertIn('NOT IN', sql)
        self.assertNotIn('CAST', sql)


# Only this module's tests: the fixture's own tests run in their modules.
for _name in dir(queue_tests.FilledDetailsTests):
    if _name.startswith('test_') and _name not in vars(AutofillReapplyTests):
        setattr(AutofillReapplyTests, _name, None)
