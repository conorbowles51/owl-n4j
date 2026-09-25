"""The register reflects live duplicate decisions without rereading every PDF."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.statement_file_status import statement_file_status
from tests import test_financial_pending_duplicates as fixtures


class DuplicateFileStatusTests(TestCase):
    def setUp(self):
        self.p = fixtures.PendingDuplicateTests()
        self.p.setUp()
        self.f = self.p.f
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()
        self.f.confirm()
        self.other = self.p.fixture.copy_file()
        self.ignored = self.p.decision(self.other)

    def tearDown(self):
        self.p.tearDown()

    def status(self):
        with self.f.SessionLocal() as db:
            with patch('services.financial.statement_import.read_statement_import',
                       side_effect=AssertionError('A register must not reconstruct statements.')):
                result = statement_file_status(db, case_id=self.f.case.id)
            return next(item for item in result['files'] if item['evidence_file_id'] == str(self.other.id))

    def add_batch(self, *, mixed=False):
        with self.f.SessionLocal() as db:
            batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.actor.user_id,
                actor={}, files=[], status='review')
            db.add(batch)
            db.flush()
            db.add(Item(id=uuid4(), batch_id=batch.id, file_id=self.other.id, statement_key='',
                status='attention', summary=dict(can_import=True, problem_count=99, revision=self.ignored['reading_revision'])))
            if mixed:
                db.add(Item(id=uuid4(), batch_id=batch.id, file_id=self.other.id,
                    statement_key='separate-period', status='ready', summary=dict(can_import=True, problem_count=0)))
                db.add(Item(id=uuid4(), batch_id=batch.id, file_id=self.other.id,
                    statement_key='earlier-reading', status='superseded_reading', summary=dict(can_import=True, problem_count=99)))
            db.commit()

    def test_direct_ignored_decision_is_visible_without_a_batch_or_reextraction(self):
        shown = self.status()
        self.assertEqual(shown['ignored_periods'], 1)
        self.assertEqual(shown['prepared_periods'], 1)
        self.assertEqual(shown.get('available_periods', 0), 0)
        self.assertEqual(shown.get('periods_with_checks', 0), 0)
        decision = shown['duplicate_dispositions'][0]['decision']
        self.assertEqual(decision['label'], 'Duplicate - Ignored by system')
        self.assertTrue(decision['current'])
        self.assertEqual(decision['retained']['evidence_file_id'], str(self.p.primary.id))

    def test_removed_file_retains_duplicate_history_without_active_prepared_periods(self):
        self.add_batch(mixed=True)
        with self.f.SessionLocal() as db:
            original = deepcopy(db.get(EvidenceFile, self.other.id).metadata_)
        for removal in (
            {'financial_file_visibility': {'removed': True, 'revision': 'removed'}},
            {'financial_import_removal': {'id': 'removed-imports'}},
        ):
            with self.subTest(removal=removal):
                with self.f.SessionLocal() as db:
                    file = db.get(EvidenceFile, self.other.id)
                    file.metadata_ = {**deepcopy(original), **removal}
                    db.commit()
                with self.f.SessionLocal() as db:
                    with patch('services.financial.statement_import.read_statement_import',
                               side_effect=AssertionError('Removal history must not trigger reextraction.')):
                        result = statement_file_status(db, case_id=self.f.case.id)
                    self.assertNotIn(str(self.other.id), [item['evidence_file_id'] for item in result['files']])
                    self.assertEqual(db.get(EvidenceFile, self.other.id).metadata_['financial_duplicate_dispositions'],
                                     original['financial_duplicate_dispositions'])
                    self.assertIn(str(self.p.primary.id), [item['evidence_file_id'] for item in result['files']])

    def test_mixed_file_ignores_only_confirmed_copy_and_excludes_superseded_reading(self):
        self.add_batch(mixed=True)
        shown = self.status()
        self.assertEqual(shown['ignored_periods'], 1)
        self.assertEqual(shown['prepared_periods'], 2)
        self.assertEqual(shown['available_periods'], 1)
        self.assertEqual(shown['periods_with_checks'], 0)
        self.assertEqual([item['statement_id'] for item in shown['ready_periods']], ['separate-period'])

    def test_direct_restore_overrides_stale_batch_status_and_reopens_comparison(self):
        self.add_batch()
        restored = self.p.decision(self.other, 'restore', expected_decision_revision=self.ignored['revision'])
        self.assertEqual(restored['status'], 'restored')
        shown = self.status()
        self.assertEqual(shown['ignored_periods'], 0)
        self.assertEqual(shown['available_periods'], 0)
        self.assertEqual(shown['periods_with_checks'], 1)
        self.assertEqual(shown['duplicate_dispositions'][0]['decision']['status'], 'restored')

    def test_changed_geometry_same_job_invalidates_ignored_status_without_writing_metadata(self):
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (self.other.id, 1))
            changed = deepcopy(geometry.payload)
            changed[0]['table']['values'][0]['text'] += ' revised'
            geometry.payload = changed
            before = deepcopy(db.get(EvidenceFile, self.other.id).metadata_)
            db.commit()
        shown = self.status()
        self.assertEqual(shown['ignored_periods'], 0)
        self.assertEqual(shown['periods_with_checks'], 1)
        self.assertFalse(shown['duplicate_dispositions'][0]['decision']['current'])
        self.assertEqual(shown['duplicate_dispositions'][0]['decision']['label'], 'Compare this statement')
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(EvidenceFile, self.other.id).metadata_, before)

    def test_missing_legacy_guard_cannot_hide_a_statement(self):
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.other.id)
            metadata = deepcopy(file.metadata_)
            metadata['financial_duplicate_dispositions'][''].pop('projection_guard')
            file.metadata_ = metadata
            db.commit()
        self.assertEqual(self.status()['ignored_periods'], 0)
        self.assertEqual(self.status()['periods_with_checks'], 1)
