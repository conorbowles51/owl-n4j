"""After a release that reads statements differently, prepared files are prepared again with no click.

A synthetic replay of a release: a file is prepared by an "old reader" that
misses one printed row (so its statement does not reconcile and waits), then
the current reader is deployed. The batch loop's sweep finds the file, reads it
again read-only, sees the reading differs, and hands it back to the batch's own
preparation. Nothing is lost: drafts, imports and decisions stay as they were.
"""
import asyncio
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select

from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial import queue_save, reader_release
from services.financial.review_queue import case_review_queue
from services.financial.statement_import import read_statement_import as current_reader
from tests import test_financial_statement_overlap as overlap_fixture

OLD = 'old-reader-stamp'


def old_reader(*args, **kwargs):
    """The reading an earlier release produced: one printed payment missed."""
    proposal = current_reader(*args, **kwargs)
    if kwargs.get('statement_id') is None and proposal.get('statement_choices'):
        return proposal
    proposal = deepcopy(proposal)
    rows = [row for row in proposal['rows'] if row['kind'] == 'transaction' and not row['excluded']]
    proposal['rows'] = [row for row in proposal['rows'] if row is not rows[-1] and row['id'] != rows[-1]['id']]
    proposal['revision'] = 'old-' + proposal['revision']
    return proposal


class ReaderReleaseTests(TestCase):
    def setUp(self):
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        self.auto_save = patch.object(queue_save, 'AUTO_SAVE_READY', False)
        self.auto_save.start()

    def tearDown(self):
        self.auto_save.stop()
        self.fixture.tearDown()

    def turn(self, batch):
        process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(batches.advance_batch(self.f.SessionLocal, batch, Path, process))

    def drain(self, batch):
        for _ in range(20):
            self.turn(batch)
            with self.f.SessionLocal() as db:
                if batches.batch_for(db, self.f.case.id, batch).status != 'preparing':
                    return
        self.fail('batch did not finish')

    def prepare_with_old_reader(self):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id], folder_ids=[], actor=self.f.actor)
        with patch.object(batches, 'read_statement_import', old_reader), \
                patch.object(reader_release, 'reader_stamp', return_value=OLD):
            self.drain(batch)
        return batch

    def item(self, batch):
        with self.f.SessionLocal() as db:
            return db.scalar(select(Item).where(Item.batch_id == batch))

    def files(self, batch):
        with self.f.SessionLocal() as db:
            return deepcopy(batches.batch_for(db, self.f.case.id, batch).files)

    def test_a_statement_waiting_for_a_reader_fix_becomes_ready_after_the_release_with_no_click(self):
        batch = self.prepare_with_old_reader()
        self.assertEqual(self.item(batch).status, 'attention')
        self.assertEqual(self.files(batch)[0]['reader_stamp'], OLD)
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['compared'], outcome['rechecked']), (1, 1))
        self.assertEqual(self.files(batch)[0]['status'], 'processing')
        # While it is prepared again the queue says so instead of asking for work.
        with self.f.SessionLocal() as db:
            queue = case_review_queue(db, case_id=self.f.case.id, use_cache=False)
        self.assertEqual((queue['counts']['rechecking'], queue['counts']['waiting']), (1, 0))
        self.drain(batch)
        item = self.item(batch)
        self.assertEqual(item.status, 'ready')
        self.assertTrue(item.summary['can_import'])
        files = self.files(batch)
        self.assertEqual((files[0]['status'], files[0]['reader_stamp']), ('checked', reader_release.reader_stamp()))
        self.assertNotIn('recheck', files[0])
        # The next sweep has nothing left to do.
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['files'], 0)

    def test_with_automatic_save_the_fixed_statement_is_saved_by_the_system(self):
        batch = self.prepare_with_old_reader()
        reader_release.sweep(self.f.SessionLocal)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.drain(batch)
        item = self.item(batch)
        self.assertEqual(item.status, 'imported')
        self.assertEqual(item.summary['import_actor']['email'], queue_save.SYSTEM_ACTOR.email)

    def test_a_release_that_reads_the_file_the_same_way_changes_nothing_but_the_stamp(self):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id], folder_ids=[], actor=self.f.actor)
        with patch.object(reader_release, 'reader_stamp', return_value=OLD):
            self.drain(batch)
        before = self.item(batch)
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['compared'], outcome['rechecked'], outcome['left']), (1, 0, {'unchanged': 1}))
        after = self.item(batch)
        self.assertEqual((after.status, after.summary, after.updated_at), (before.status, before.summary, before.updated_at))
        with self.f.SessionLocal() as db:
            self.assertEqual(batches.batch_for(db, self.f.case.id, batch).status, 'review')
        self.assertEqual(self.files(batch)[0]['reader_stamp'], reader_release.reader_stamp())

    def test_a_draft_is_kept_through_the_re_preparation(self):
        batch = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            record = db.scalar(select(Item).where(Item.batch_id == batch))
            proposal = old_reader(db, case_id=self.f.case.id, evidence_file_id=record.file_id,
                                  currency=record.summary.get('currency'), statement_id=record.statement_key or None)
            draft = batches.initial_request(proposal)
            draft['holder'] = 'Holder typed by the investigator'
            record.review_request = draft
            db.commit()
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['rechecked'], 1)
        self.drain(batch)
        self.assertEqual(self.item(batch).review_request['holder'], 'Holder typed by the investigator')

    def test_an_imported_statement_and_a_paused_batch_are_left_alone(self):
        batch = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            db.scalar(select(Item).where(Item.batch_id == batch)).status = 'imported'
            db.commit()
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['rechecked'], outcome['left']), (0, {'nothing_open': 1}))
        self.assertEqual(self.item(batch).status, 'imported')
        other = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            batches.batch_for(db, self.f.case.id, other, True).status = 'paused'
            db.commit()
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['files'], 0)

    def test_a_conflicting_saved_review_is_left_for_the_investigator(self):
        batch = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            from postgres.models.evidence import EvidenceFile
            record = db.scalar(select(Item).where(Item.batch_id == batch))
            file = db.get(EvidenceFile, record.file_id)
            file.metadata_ = {**(file.metadata_ or {}), 'financial_review_progress': {
                record.statement_key or '': dict(request=dict(expected_revision='old-revision'))}}
            db.commit()
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['rechecked'], outcome['left']), (0, {'saved_review': 1}))
        self.assertEqual(self.files(batch)[0]['status'], 'checked')

    def test_every_changed_file_of_a_batch_is_prepared_again_in_the_same_run(self):
        other = self.fixture.copy_file(revised=True)
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id, other.id], folder_ids=[], actor=self.f.actor)
        with patch.object(batches, 'read_statement_import', old_reader), \
                patch.object(reader_release, 'reader_stamp', return_value=OLD):
            self.drain(batch)
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['compared'], outcome['rechecked']), (2, 2))
        self.assertEqual([f['status'] for f in self.files(batch)], ['processing', 'processing'])
        self.drain(batch)
        with self.f.SessionLocal() as db:
            statuses = [i.status for i in db.scalars(select(Item).where(Item.batch_id == batch))]
        self.assertNotIn('attention', statuses, statuses)

    def test_switch_off_and_bounded_and_resumable(self):
        batch = self.prepare_with_old_reader()
        with patch.object(reader_release, 'RECHECK_AFTER_RELEASE', False):
            self.assertEqual(reader_release.sweep(self.f.SessionLocal)['files'], 0)
        self.assertEqual(reader_release.sweep(self.f.SessionLocal, max_files=0)['compared'], 0)
        self.assertEqual(self.files(batch)[0]['reader_stamp'], OLD)
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['rechecked'], 1)

    def test_the_stamp_covers_every_listed_reader_module(self):
        root = Path(reader_release.__file__).resolve().parent
        for pattern in reader_release.READER_MODULES:
            with self.subTest(pattern=pattern):
                self.assertTrue(list(root.glob(pattern)), pattern)
        reader_release._stamp = None
        first = reader_release.reader_stamp()
        with patch.object(Path, 'read_bytes', return_value=b'changed reader'):
            reader_release._stamp = None
            self.assertNotEqual(reader_release.reader_stamp(), first)
        reader_release._stamp = None
        self.assertEqual(reader_release.reader_stamp(), first)
