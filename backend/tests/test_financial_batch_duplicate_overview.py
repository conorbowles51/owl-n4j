"""Copies the system set aside are announced before anything is opened, and never steer the to-do list.

Synthetic two-file case: a statement and a second production of it (same
money, other bytes) which the batch read sets aside as a copy.
"""
from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial import import_batches as service
from services.financial.batch_selection_preview import selection_preview
from services.financial.statement_file_status import statement_file_status
from tests import test_financial_pending_duplicates as fixtures

NO_READING = AssertionError('This read must not reconstruct a statement.')


class BatchDuplicateOverviewTests(TestCase):
    def setUp(self):
        self.p = fixtures.PendingDuplicateTests('test_identical_masked_copies_have_one_ready_period_and_one_excluded_copy')
        self.p.setUp()
        self.f = self.p.f
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()

    def tearDown(self):
        self.p.tearDown()

    def copy_batch(self, identical=False):
        self.other, self.batch = self.p.masked_copy_batch(identical=identical)
        state = self.p.fixture.b.status(self.batch)
        self.assertEqual(state['counts']['duplicate_ignored'], 1, state)
        return state

    def status(self, **kwargs):
        with self.f.SessionLocal() as db, \
                patch('services.financial.statement_import.read_statement_import', side_effect=NO_READING), \
                patch.object(service, 'read_statement_import', side_effect=NO_READING):
            return service.batch_status(db, case_id=self.f.case.id, batch_id=self.batch, **kwargs)

    def register(self, file):
        with self.f.SessionLocal() as db, \
                patch('services.financial.statement_import.read_statement_import', side_effect=NO_READING):
            result = statement_file_status(db, case_id=self.f.case.id, use_cache=False)
        return next(item for item in result['files'] if item['evidence_file_id'] == str(file.id))

    def preview(self, *files):
        with self.f.SessionLocal() as db, \
                patch('services.financial.statement_import.read_statement_import', side_effect=NO_READING):
            result = selection_preview(db, case_id=self.f.case.id, file_ids=[str(f.id) for f in files])
            self.assertFalse(db.new or db.dirty or db.deleted)
            return result

    def system_copy_without_file_decision(self):
        """The live shape: a stored copy readiness record, no investigator decision on the file."""
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.other.id)
            metadata = deepcopy(file.metadata_)
            metadata.pop('financial_duplicate_dispositions')
            file.metadata_ = metadata
            db.flush()
            item = db.scalar(select(Item).where(Item.file_id == self.other.id))
            summary = {k: v for k, v in deepcopy(item.summary).items() if k != 'readiness'}
            self.assertEqual(summary['duplicate_disposition']['status'], 'ignored')
            change = service._readiness_change(service._ProjectionInputs(db, self.f.case.id, [item]),
                item, 'duplicate_ignored', summary, item.review_request)
            service._apply_readiness(item, change)
            db.commit()

    # -- batch read ---------------------------------------------------------

    def test_file_overview_names_the_retained_file_and_sorts_copies_last(self):
        self.copy_batch()
        state = self.status(review_group='')
        overview = {entry['file_id']: entry for entry in state['file_overview']}
        copy, primary = overview[str(self.other.id)], overview[str(self.p.primary.id)]
        self.assertTrue(copy['all_copies'])
        self.assertEqual((copy['statements'], copy['copies'], copy['unfinished']), (1, 1, 0))
        self.assertEqual(copy['retained'][0]['evidence_file_id'], str(self.p.primary.id))
        self.assertEqual(copy['retained'][0]['filename'], self.p.primary.original_filename)
        self.assertFalse(primary['all_copies'])
        self.assertEqual(primary['copies'], 0)
        self.assertEqual(state['file_overview'][-1]['file_id'], str(self.other.id))
        self.assertEqual(state['items'][-1]['file_id'], str(self.other.id))
        self.assertEqual(state['items'][-1]['status'], 'duplicate_ignored')

    def test_default_to_do_and_navigation_skip_copies(self):
        self.copy_batch()
        unfinished = self.status(review_group='unfinished')
        self.assertEqual([i['file_id'] for i in unfinished['items']], [str(self.p.primary.id)])
        everything = self.status()
        primary = next(i for i in everything['items'] if i['file_id'] == str(self.p.primary.id))
        copy = next(i for i in everything['items'] if i['file_id'] == str(self.other.id))
        with self.f.SessionLocal() as db:
            following = service.next_statement(db, case_id=self.f.case.id, batch_id=self.batch, item_id=UUID(primary['id']))
            self.assertIsNone(following['item_id'])
            self.assertEqual(following['total'], 1)
            # A copy opened from the list can still step back to the work.
            back = service.next_statement(db, case_id=self.f.case.id, batch_id=self.batch,
                item_id=UUID(copy['id']), direction='previous')
            self.assertEqual(back['item_id'], primary['id'])

    # -- file register --------------------------------------------------------

    def test_register_counts_a_current_system_copy_as_ignored_not_as_work(self):
        self.copy_batch()
        self.system_copy_without_file_decision()
        self.assertEqual(self.status()['counts']['duplicate_ignored'], 1)
        shown = self.register(self.other)
        self.assertEqual((shown['prepared_periods'], shown['ignored_periods']), (1, 1))
        self.assertEqual(shown.get('periods_with_checks', 0), 0)
        decision = shown['duplicate_dispositions'][0]['decision']
        self.assertEqual(decision['retained']['filename'], self.p.primary.original_filename)

    def test_register_keeps_an_outdated_system_copy_as_a_check(self):
        self.copy_batch()
        self.system_copy_without_file_decision()
        with self.f.SessionLocal() as db:
            # A new reading of the copy's pages: the stored copy record no
            # longer describes current inputs, so it cannot hide the statement.
            geometry = db.get(EvidenceTableGeometry, (self.other.id, 1))
            geometry.extracted_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
            db.commit()
        self.assertEqual(self.status()['counts']['duplicate_ignored'], 0)
        shown = self.register(self.other)
        self.assertEqual(shown.get('ignored_periods', 0), 0)
        self.assertEqual(shown['periods_with_checks'], 1)

    # -- before a batch starts ----------------------------------------------

    def test_preview_offers_the_open_batch_and_names_copies(self):
        self.copy_batch()
        result = self.preview(self.p.primary, self.other)
        self.assertEqual(result['suggested_batch_id'], str(self.batch))
        offered = result['open_batches'][0]
        self.assertTrue(offered['covers_selection'])
        self.assertEqual((offered['shared_files'], offered['selected_files'], offered['other_files']), (2, 2, []))
        copies = {entry['file_id']: entry['findings'] for entry in result['copies']}
        self.assertEqual(list(copies), [str(self.other.id)])
        finding = copies[str(self.other.id)][0]
        self.assertEqual((finding['kind'], finding['copies'], finding['statements']), ('statements_already_copies', 1, 1))
        self.assertEqual(finding['retained'][0]['evidence_file_id'], str(self.p.primary.id))

    def test_preview_names_identical_bytes_before_any_reading(self):
        self.copy_batch(identical=True)
        twin = self.p.fixture.copy_file()
        with self.f.SessionLocal() as db:
            db.get(EvidenceFile, twin.id).sha256 = self.p.primary.sha256
            db.commit()
        findings = {e['file_id']: e['findings'] for e in self.preview(twin)['copies']}
        kinds = [f['kind'] for f in findings[str(twin.id)]]
        self.assertEqual(kinds, ['identical_bytes_in_financial'])
        retained = {r['evidence_file_id'] for r in findings[str(twin.id)][0]['retained']}
        self.assertIn(str(self.p.primary.id), retained)

    def test_finished_batch_is_not_offered(self):
        self.copy_batch()
        with self.f.SessionLocal() as db:
            for item in db.scalars(select(Item).where(Item.batch_id == self.batch, Item.status.in_(('ready', 'attention')))):
                item.status = 'skipped'
            db.commit()
        self.assertEqual(self.preview(self.p.primary)['open_batches'], [])

    # -- starting a batch ------------------------------------------------------

    def test_selection_inside_an_open_batch_continues_it_unless_a_new_batch_is_explicit(self):
        self.copy_batch()
        with self.f.SessionLocal() as db:
            continued = service.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.p.primary.id], folder_ids=[], actor=self.f.actor)
        self.assertEqual(continued, self.batch)
        fresh_id = uuid4()
        with self.f.SessionLocal() as db:
            fresh = service.create_batch(db, case_id=self.f.case.id, request_id=fresh_id,
                file_ids=[self.p.primary.id], folder_ids=[], actor=self.f.actor, start_new=True)
            self.assertEqual(fresh, fresh_id)
            self.assertEqual(db.scalar(select(Batch).where(Batch.id == fresh_id)).status, 'preparing')
