from unittest import TestCase
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from services.financial.statement_progress import save_progress, previous_review_progress
from services.financial.statement_import import StatementReviewDraft
from services.financial.statement_import import StatementImportRequest, check_import_request
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_statement_import import StatementImportTests as Fixture


class StatementProgressTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def save(self, raw, revision='initial', case_id=None):
        with self.f.SessionLocal() as db:
            return save_progress(db, case_id=case_id or self.f.case.id, evidence_file_id=self.f.file.id,
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=revision, actor=self.f.actor)

    def test_incomplete_progress_reopens_without_import_and_detects_concurrent_save(self):
        raw = self.f.request()
        payment = next(row for row in raw['rows'] if not row['excluded'])
        payment.update(date='', description='Corrected description', reason='Checking the printed date')
        saved = self.save(raw)
        reopened = self.f.preview()['saved_review']
        self.assertEqual(reopened['request']['rows'], saved['request']['rows'])
        self.assertEqual(reopened['saved_by']['name'], self.f.actor.name)
        with self.assertRaisesRegex(PdfMappingError, 'Another reviewer'):
            self.save(raw)
        payment['date'] = '2023-03-18'
        newer = self.save(raw, saved['review_revision'])
        self.assertNotEqual(newer['review_revision'], saved['review_revision'])
        with self.f.SessionLocal() as db:
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))

    def test_scope_source_binding_and_imported_record_guard(self):
        raw = self.f.request()
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            self.save(raw, case_id=uuid4())
        changed = {**raw, 'expected_revision': 'a'*64}
        with self.assertRaisesRegex(PdfMappingError, 'reading changed'):
            self.save(changed)
        missing = deepcopy(raw)
        missing['rows'].pop()
        with self.assertRaisesRegex(PdfMappingError, 'each original row'):
            self.save(missing)
        self.f.confirm(raw)
        with self.assertRaisesRegex(PdfMappingError, 'is imported'):
            self.save(raw)

    def test_source_change_retains_previous_values_in_history(self):
        raw = self.f.request()
        saved = self.save(raw)
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            metadata = deepcopy(file.metadata_)
            metadata['financial_review_progress']['']['request']['expected_revision'] = 'a'*64
            file.metadata_ = metadata
            db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'Save progress before importing'):
            check_import_request(self.f.preview(), StatementImportRequest.model_validate(raw))
        self.save(raw, saved['review_revision'])
        with self.f.SessionLocal() as db:
            history = db.get(EvidenceFile, self.f.file.id).metadata_['financial_review_history']
            self.assertEqual(history[0]['request']['expected_revision'], 'a'*64)
            self.assertEqual(history[0]['request']['rows'], saved['request']['rows'])

    def test_reprocessed_file_can_recover_only_its_own_parent_period(self):
        raw = self.f.request()
        saved = self.save(raw)
        with self.f.SessionLocal() as db:
            from types import SimpleNamespace
            version = SimpleNamespace(case_id=self.f.case.id, metadata_={'statement_parent_evidence_id': str(self.f.file.id)})
            previous = previous_review_progress(db, version, None)
            self.assertEqual(previous['request'], saved['request'])
            self.assertEqual(previous['evidence_file_id'], str(self.f.file.id))
            self.assertIsNone(previous_review_progress(db, version, 'a'*64))
            version.case_id = uuid4()
            self.assertIsNone(previous_review_progress(db, version, None))
