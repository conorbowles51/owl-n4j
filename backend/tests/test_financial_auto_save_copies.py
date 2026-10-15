"""A copy of a statement reaches the ledger once, whichever save gets there first.

Synthetic statements (the overlap fixture: one PDF, 12 payments). Under the
duplicate evidence principle a copy is set aside as a linked duplicate of the
statement that was saved, never saved a second time and never deleted. These
cover the orders the automatic save (queue_save.AUTO_SAVE_READY) makes
possible: the original saved before its copy is even prepared, the copy
arriving in a later batch, and two claims racing to the import worker.
"""
import asyncio
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial import queue_save
from services.financial.decisions import Actor
from tests import test_financial_statement_overlap as overlap_fixture


class CopySavedOnceTests(TestCase):
    def setUp(self):
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        self.primary = self.f.file

    def tearDown(self):
        self.fixture.tearDown()

    def byte_copy(self):
        other = self.fixture.copy_file()
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, other.id)
            file.sha256 = self.primary.sha256
            file.stored_path = self.primary.stored_path
            file.original_filename = 'Copy of the statement.pdf'
            db.commit()
        return other

    def batch(self, *files):
        with self.f.SessionLocal() as db:
            return batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[file.id for file in files], folder_ids=[], actor=self.f.actor)

    def turn(self, batch):
        process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(batches.advance_batch(self.f.SessionLocal, batch, Path, process))

    def drain(self, *batch_ids, limit=40):
        for _ in range(limit):
            for batch in batch_ids:
                self.turn(batch)
            with self.f.SessionLocal() as db:
                states = [batches.batch_for(db, self.f.case.id, b).status for b in batch_ids]
            if all(state != 'preparing' for state in states):
                return
        self.fail('batches did not finish')

    def items(self):
        with self.f.SessionLocal() as db:
            return {item.file_id: (item.status, dict(item.summary)) for item in db.scalars(select(Item))
                    if item.status not in ('removed', 'superseded_reading')}

    def saved(self, db, copy):
        """Admitted statements of the two files and their payments (the fixture's case has others)."""
        sources = list(db.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == self.f.case.id, FinancialSourceDocument.status == 'admitted',
            FinancialSourceDocument.evidence_file_id.in_([self.primary.id, copy.id]))))
        transactions = len(list(db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id.in_([s.id for s in sources]))))) if sources else 0
        return sources, transactions

    def assert_saved_once(self, copy):
        with self.f.SessionLocal() as db:
            sources, transactions = self.saved(db, copy)
        self.assertEqual(len(sources), 1)
        self.assertEqual(transactions, 12)
        saved = sources[0]
        items = self.items()
        original = next(file_id for file_id in items if file_id == saved.evidence_file_id)
        self.assertEqual(items[original][0], 'imported')
        status, summary = items[copy.id if original != copy.id else self.primary.id]
        # Set aside as a linked duplicate, visible as such: not "already saved".
        self.assertEqual(status, 'duplicate_ignored', summary.get('problems'))
        disposition = summary['duplicate_disposition']
        self.assertEqual((disposition['status'], disposition['basis']), ('ignored', 'identical_bytes'))
        self.assertEqual(disposition['retained']['evidence_file_id'], str(saved.evidence_file_id))
        return saved

    def test_byte_copy_in_a_later_batch_is_set_aside_not_shown_as_saved(self):
        first = self.batch(self.primary)
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.drain(first)
            state = self.fixture.b.status(first)
            with self.f.SessionLocal() as db:
                batches.queue_import(db, case_id=self.f.case.id, batch_id=first,
                    expected_revision=state['ready_revision'], actor=self.f.actor)
            self.drain(first)
            copy = self.byte_copy()
            second = self.batch(copy)
            self.drain(second)
        saved = self.assert_saved_once(copy)
        view = self.fixture.b.status(second)
        entry = next(item for item in view['items'] if item['file_id'] == str(copy.id))
        self.assertEqual(entry['status'], 'duplicate_ignored')
        self.assertEqual(entry['duplicate_disposition']['retained']['source_document_id'], str(saved.id))
        self.assertFalse(entry['can_import'])

    def test_automatic_save_of_the_original_before_its_copy_is_prepared(self):
        copy = self.byte_copy()
        batch = self.batch(self.primary, copy)
        # One file per turn: the original is prepared and saved by System, and
        # imported at the start of the next turn, before its copy is prepared.
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), patch.object(batches, 'FILES_PER_TURN', 1), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.drain(batch)
        self.assert_saved_once(copy)
        view = self.fixture.b.status(batch)
        self.assertEqual((view['counts']['imported'], view['counts']['duplicate_ignored']), (1, 1))

    def test_automatic_save_with_both_files_prepared_in_one_turn(self):
        copy = self.byte_copy()
        batch = self.batch(self.primary, copy)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.drain(batch)
        self.assert_saved_once(copy)

    def test_automatic_save_of_two_batches_prepared_side_by_side(self):
        copy = self.byte_copy()
        first, second = self.batch(self.primary), self.batch(copy)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.drain(first, second)
        self.assert_saved_once(copy)

    def claim_directly(self, batch):
        """A claim made before the copy was set aside (the race the import writer must survive)."""
        with self.f.SessionLocal() as db:
            record = db.scalar(select(Item).where(Item.batch_id == batch))
            record.status = 'ready'
            record.summary = {**record.summary, 'can_import': True, 'problems': [], 'problem_count': 0}
            db.flush()
            projection = batches.checked_batch_items(db, self.f.case.id, [record], reading='all')[0]
            operation = batches.claim_ready(db, case_id=self.f.case.id, batch=batches.batch_for(db, self.f.case.id, batch, True),
                ready=[record], checked=[projection], operation_id=uuid4(), expected_revision='race',
                actor=Actor(name='System', email='auto-save@system.local'))
            self.assertIsNotNone(operation)
            db.commit()

    def race(self, copy):
        first, second = self.batch(self.primary), self.batch(copy)
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.drain(first, second)
            # Both claimed before either import ran; the copy's claim is stale.
            self.claim_directly(first)
            self.claim_directly(second)
            self.drain(first, second)

    def test_two_claims_of_a_byte_copy_reach_the_ledger_once(self):
        copy = self.byte_copy()
        self.race(copy)
        self.assert_saved_once(copy)

    def test_two_claims_of_a_printed_copy_in_other_bytes_reach_the_ledger_once(self):
        copy = self.fixture.copy_file()
        self.race(copy)
        with self.f.SessionLocal() as db:
            sources, transactions = self.saved(db, copy)
            self.assertEqual((len(sources), transactions), (1, 12))
        statuses = sorted(status for status, _ in self.items().values())
        self.assertEqual(statuses, ['duplicate_ignored', 'imported'])
