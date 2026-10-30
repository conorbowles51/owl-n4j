"""Statements that become ready after their file's preparation are saved by the worker, with no click.

Synthetic statements (the overlap fixture: one PDF, 12 payments). The
automatic save (queue_save.AUTO_SAVE_READY) used to fire only when a file's
preparation ended, so a statement that became ready later (the readiness
sweep, a refresh after a change elsewhere) or whose automatic save failed (a
database lock) waited for "Save all ready". ``queue_save.sweep_save`` saves
them in the worker's readiness round exactly as at the end of preparation.
"""
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from postgres.models.financial_import_batches import FinancialImportOperation as Operation
from services.financial import import_batches as batches
from services.financial import queue_save
from tests import test_financial_auto_save_copies as copies_fixture


def locked(*_, **__):
    raise OperationalError('UPDATE financial_import_batch_items', {}, Exception('database is locked'))


class SweepSaveTests(TestCase):
    def setUp(self):
        self.copies = copies_fixture.CopySavedOnceTests('test_automatic_save_with_both_files_prepared_in_one_turn')
        self.copies.setUp()
        self.addCleanup(self.copies.tearDown)
        self.fixture, self.f, self.primary = self.copies.fixture, self.copies.f, self.copies.primary
        for name in ('batch', 'drain', 'items', 'saved', 'byte_copy', 'assert_saved_once'):
            setattr(self, name, getattr(self.copies, name))
        queue_save._SWEPT.clear()
        self.addCleanup(queue_save._SWEPT.clear)

    def prepare(self, *batch_ids, **patches):
        """Prepare with automatic save on, but the statement not saved at the end of preparation."""
        hold = patches.pop('hold', dict(fully_reconciled=lambda *a, **k: False))
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), patch.multiple(queue_save, **hold):
            self.drain(*batch_ids)

    def sweep(self):
        with patch.object(queue_save, 'AUTO_SAVE_READY', True):
            return queue_save.sweep_save(self.f.SessionLocal, budget_seconds=None)

    def status_of(self, file_id):
        return self.items()[file_id][0]

    def import_actor(self, file_id):
        return (self.items()[file_id][1].get('import_actor') or {}).get('name')

    def test_statement_ready_after_preparation_is_saved_by_the_sweep_as_system(self):
        batch = self.batch(self.primary)
        self.prepare(batch)
        self.assertEqual(self.status_of(self.primary.id), 'ready')
        report = self.sweep()
        self.assertEqual(report['queued'], 1)
        self.assertEqual(len(report['item_ids']), 1)
        self.drain(batch)
        self.assertEqual(self.status_of(self.primary.id), 'imported')
        self.assertEqual(self.import_actor(self.primary.id), 'System')
        with self.f.SessionLocal() as db:
            sources, transactions = self.saved(db, self.primary)
        self.assertEqual((len(sources), transactions), (1, 12))
        # Once: a later round has nothing left to save.
        queue_save._SWEPT.clear()
        self.assertEqual(self.sweep()['queued'], 0)

    def test_failed_automatic_save_is_saved_by_the_next_round(self):
        batch = self.batch(self.primary)
        self.prepare(batch, hold=dict(save_statements=locked))
        self.assertEqual(self.status_of(self.primary.id), 'ready')
        self.assertEqual(self.sweep()['queued'], 1)
        self.drain(batch)
        self.assertEqual(self.status_of(self.primary.id), 'imported')
        self.assertEqual(self.import_actor(self.primary.id), 'System')

    def test_a_locked_round_saves_nothing_and_the_next_round_retries(self):
        batch = self.batch(self.primary)
        self.prepare(batch)
        with patch.object(queue_save, 'save_statements', locked):
            self.assertEqual(self.sweep()['queued'], 0)
        self.assertEqual(self.status_of(self.primary.id), 'ready')
        self.assertEqual(self.sweep()['queued'], 1)

    def test_unchanged_file_is_not_checked_again(self):
        batch = self.batch(self.primary)
        self.prepare(batch)
        with patch.object(queue_save, 'fully_reconciled', return_value=False):
            self.assertEqual(self.sweep()['queued'], 0)
        with patch.object(queue_save, '_auto_save_once', side_effect=AssertionError('unchanged file read again')):
            self.assertEqual(self.sweep()['queued'], 0)

    def test_a_file_held_while_another_statement_is_pending_is_looked_at_once_that_save_ends(self):
        # fdaf956c 2026-10-30 (Capital One 2023-01-11, ready 03:16-04:40 until a restart): the sweep's one look came
        # while another statement of the case was pending_import; that item leaving pending_import changed nothing
        # the sweep compared, so the ready statement was never looked at again.
        from uuid import uuid4
        batch = self.batch(self.primary)
        self.prepare(batch)
        with self.f.SessionLocal() as db:
            other = Item(id=uuid4(), batch_id=batch, file_id=self.primary.id, statement_key='another-statement',
                         status='pending_import', summary={})
            db.add(other)
            db.commit()
            other_id = other.id
        with patch.object(queue_save, 'fully_reconciled', return_value=False):
            self.assertEqual(self.sweep()['queued'], 0)
        with self.f.SessionLocal() as db:
            db.get(Item, other_id).status = 'imported'
            db.commit()
        self.assertEqual(self.sweep()['queued'], 1)

    def test_two_workers_save_it_once(self):
        batch = self.batch(self.primary)
        self.prepare(batch)
        real_claim = batches.claim_ready
        other = {}

        def claim_after_the_other_worker(session, **values):
            # Worker B runs its whole round between worker A's checks and its claim.
            if not other:
                saved = dict(queue_save._SWEPT)
                queue_save._SWEPT.clear()
                with patch.object(batches, 'claim_ready', real_claim):
                    other.update(queue_save.sweep_save(self.f.SessionLocal, budget_seconds=None))
                queue_save._SWEPT.clear()
                queue_save._SWEPT.update(saved)
            return real_claim(session, **values)

        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(batches, 'claim_ready', claim_after_the_other_worker):
            mine = queue_save.sweep_save(self.f.SessionLocal, budget_seconds=None)
        self.assertEqual(other['queued'] + mine['queued'], 1, (other, mine))
        self.drain(batch)
        with self.f.SessionLocal() as db:
            claims = [row for op in db.scalars(select(Operation).where(Operation.batch_id == batch))
                      for row in op.outcomes]
            sources, transactions = self.saved(db, self.primary)
        self.assertEqual(len(claims), 1)
        self.assertEqual((len(sources), transactions), (1, 12))

    def test_statement_with_an_investigator_draft_is_not_saved(self):
        batch = self.batch(self.primary)
        self.prepare(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.review_request = batches.initial_request(batches.read_statement_import(db, case_id=self.f.case.id,
                evidence_file_id=item.file_id, statement_id=item.statement_key or None))
            db.commit()
        self.assertEqual(self.sweep()['queued'], 0)
        self.assertEqual(self.status_of(self.primary.id), 'ready')

    def test_file_prepared_before_automatic_save_is_left_for_the_explicit_backlog(self):
        batch = self.batch(self.primary)
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.drain(batch)
        self.assertEqual(self.status_of(self.primary.id), 'ready')
        self.assertEqual(self.sweep()['queued'], 0)
        self.assertEqual(self.status_of(self.primary.id), 'ready')

    def test_switch_off_saves_nothing(self):
        batch = self.batch(self.primary)
        self.prepare(batch)
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.assertEqual(queue_save.sweep_save(self.f.SessionLocal)['queued'], 0)
        self.assertEqual(self.status_of(self.primary.id), 'ready')

    def copy_becomes_ready(self):
        """Both statements stored ready (as a readiness refresh could leave a copy before its original saves)."""
        with self.f.SessionLocal() as db:
            for item in db.scalars(select(Item).where(Item.status == 'duplicate_ignored')):
                item.status = 'ready'
                item.summary = {key: value for key, value in item.summary.items()
                                if key not in ('duplicate_disposition', 'readiness')} | dict(
                    can_import=True, problems=[], problem_count=0)
            db.commit()
        self.assertEqual(sorted(status for status, _ in self.items().values()), ['ready', 'ready'])

    def shown(self, *batch_ids):
        """What the batch views show for each statement: (status, offered for saving)."""
        return sorted((entry['status'], entry['can_import']) for batch in batch_ids
                      for entry in self.fixture.b.status(batch)['items'])

    def sweep_rounds(self, *batch_ids):
        with patch.object(queue_save, 'AUTO_SAVE_READY', True):
            for _ in range(3):
                queue_save.sweep_save(self.f.SessionLocal, budget_seconds=None)
                self.drain(*batch_ids)
                batches.refresh_stale_readiness(self.f.SessionLocal, budget_seconds=60)

    def test_a_copy_that_becomes_ready_is_set_aside_never_saved(self):
        copy = self.byte_copy()
        first, second = self.batch(self.primary), self.batch(copy)
        self.prepare(first, second)
        self.copy_becomes_ready()
        self.sweep_rounds(first, second)
        with self.f.SessionLocal() as db:
            sources, transactions = self.saved(db, copy)
        self.assertEqual((len(sources), transactions), (1, 12))
        self.assertEqual(self.shown(first, second), [('duplicate_ignored', False), ('imported', False)])

    def test_a_printed_copy_in_other_bytes_is_saved_once(self):
        copy = self.fixture.copy_file()
        first, second = self.batch(self.primary), self.batch(copy)
        self.prepare(first, second)
        self.copy_becomes_ready()
        self.sweep_rounds(first, second)
        with self.f.SessionLocal() as db:
            sources, transactions = self.saved(db, copy)
        self.assertEqual((len(sources), transactions), (1, 12))
        self.assertEqual(self.shown(first, second), [('duplicate_ignored', False), ('imported', False)])
