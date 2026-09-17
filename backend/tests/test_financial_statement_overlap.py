"""Coverage decisions use actual statement imports and durable batch records."""
from copy import deepcopy
import hashlib
from pathlib import Path
from unittest import TestCase
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry, EvidenceFile
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial import statement_import_overlap as overlap
from services.financial.statement_import import StatementReviewDraft
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_import_batches import BatchImportTests as BatchFixture


class StatementOverlapTests(TestCase):
    def setUp(self):
        self.b = BatchFixture('test_folder_preparation_bulk_confirmation_and_repeat_do_not_duplicate')
        self.b.setUp()
        self.f = self.b.f
        text = self.f.db.get(EvidenceDocumentText, self.f.file.id)
        text.content += 'Bank: Synthetic Bank\nStatement Period: January 1, 2023 - December 31, 2023\n'
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        text.character_count = len(text.content)
        self.f.db.commit()
        self.primary = self.f.file

    def tearDown(self):
        self.b.tearDown()

    def copy_file(self):
        f = self.f
        raw = f.path.read_bytes() + ('\n% copy ' + str(uuid4())).encode()
        path = Path(f._directory) / (str(uuid4()) + '.pdf')
        path.write_bytes(raw)
        file = f.evidence(hashlib.sha256(raw).hexdigest())
        file.stored_path = str(path)
        file.original_filename = 'Comparison copy.pdf'
        file.status = 'processed'
        text = f.db.get(EvidenceDocumentText, self.primary.id)
        geometry = f.db.get(EvidenceTableGeometry, (self.primary.id, 1))
        f.db.add(EvidenceDocumentText(evidence_file_id=file.id, content=text.content,
            content_sha256=text.content_sha256, character_count=text.character_count,
            engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
        f.db.add(EvidenceTableGeometry(evidence_file_id=file.id, page_number=1,
            engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
        f.db.commit()
        return file

    def create(self, *files):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[file.id for file in files], folder_ids=[], actor=self.f.actor)
        self.b.advance(batch)
        return batch

    def review(self, file, request=None):
        self.f.file = file
        request = request or self.f.request()
        with self.f.SessionLocal() as db:
            return overlap.coverage_review(db, case_id=self.f.case.id, file_id=file.id, request=request)

    def test_pending_overlap_skip_import_and_restore_preserve_original_and_draft(self):
        other = self.copy_file()
        batch = self.create(self.primary, other)
        status = self.b.status(batch)
        self.assertEqual(status['counts']['attention'], 2, status)
        self.assertEqual(status['counts']['ready'], 0)
        item = next(i for i in status['items'] if i['file_id'] == str(other.id))
        self.f.file = other
        raw = self.f.request()
        raw['rows'][1]['description'] = 'Retained local correction'
        raw['rows'][1]['reason'] = 'Checked against the original source.'
        with self.f.SessionLocal() as db:
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=batches._digest({}))
        item = next(i for i in self.b.status(batch)['items'] if i['file_id'] == str(other.id))
        with self.f.SessionLocal() as db:
            batches.leave_unimported(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                action='skip', reason='A copy of the primary statement.', expected_revision=item['disposition_revision'], actor=self.f.actor)
        status = self.b.status(batch)
        self.assertEqual(status['counts']['ready'], 1, status)
        self.assertEqual(status['counts']['skipped'], 1)
        with self.f.SessionLocal() as db:
            batches.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=status['ready_revision'], actor=self.f.actor)
        self.b.advance(batch)
        status = self.b.status(batch)
        self.assertEqual(status['counts']['imported'], 1, status)
        item = next(i for i in status['items'] if i['file_id'] == str(other.id))
        with self.f.SessionLocal() as db:
            batches.leave_unimported(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                action='restore', reason='Revisit the additional notes.', expected_revision=item['disposition_revision'], actor=self.f.actor)
            saved = db.get(Item, UUID(item['id']))
            self.assertEqual(saved.review_request['rows'][1]['description'], 'Retained local correction')
            self.assertEqual(len(saved.summary['import_decision_history']), 2)
            self.assertIsNotNone(db.get(EvidenceFile, other.id))
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)
        status = self.b.status(batch)
        self.assertEqual(status['counts']['attention'], 1, status)
        self.assertEqual(next(i for i in status['items'] if i['file_id'] == str(other.id))['coverage_review']['candidates'][0]['status'], 'imported')

    def test_reason_bound_to_coverage_stays_valid_when_peer_imports(self):
        other = self.copy_file()
        batch = self.create(self.primary, other)
        for item in self.b.status(batch)['items']:
            file = self.primary if item['file_id'] == str(self.primary.id) else other
            self.f.file = file
            raw = self.f.request()
            raw.update(coverage_review_revision=item['coverage_review']['revision'],
                       coverage_review_reason='Compared sources; retain both for this synthetic test.')
            with self.f.SessionLocal() as db:
                result = batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                    request=StatementReviewDraft.model_validate(raw), expected_review_revision=batches._digest({}))
                self.assertEqual(result['status'], 'ready')
        status = self.b.status(batch)
        self.assertEqual(status['counts']['ready'], 2, status)
        with self.f.SessionLocal() as db:
            batches.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=status['ready_revision'], actor=self.f.actor)
        self.b.advance(batch)
        self.assertEqual(self.b.status(batch)['counts']['imported'], 2)
        self.b.advance(batch)
        with self.f.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 24)

    def test_single_import_requires_comparison_and_rejects_stale_decision(self):
        self.f.confirm()
        other = self.copy_file()
        self.f.file = other
        raw = self.f.request()
        with self.assertRaisesRegex(PdfMappingError, 'Another statement covers'):
            self.f.confirm(raw)
        review = self.review(other, raw)
        self.assertEqual(len(review['candidates']), 1)
        raw.update(coverage_review_revision=review['revision'], coverage_review_reason='Both contain records needed for this synthetic test.')
        edited = {**raw, 'period_end': '2024-01-01', 'details_reason': 'Date was corrected.'}
        with self.assertRaisesRegex(PdfMappingError, 'Another statement covers'):
            self.f.confirm(edited)
        result = self.f.confirm(raw)
        self.assertTrue(result['created'])
        self.assertFalse(self.f.confirm(raw)['created'])

    def test_legacy_batch_and_scope_changes_and_duplicate_batch_membership(self):
        other = self.copy_file()
        first = self.create(self.primary, other)
        with self.f.SessionLocal() as db:
            for item in db.scalars(select(Item).where(Item.batch_id == first)):
                summary = dict(item.summary); summary.pop('institution')
                item.summary = summary
            db.commit()
        status = self.b.status(first)
        self.assertEqual(status['counts']['attention'], 2, status)
        self.create(self.primary)
        self.assertEqual(len(self.review(self.primary)['candidates']), 1)
        self.f.file = self.primary
        raw = self.f.request()
        for changes in ({'currency': 'USD'}, {'account_number': '99999'}, {'institution': 'Another Bank'},
                        {'period_start': '2024-01-01', 'period_end': '2024-12-31'}):
            self.assertEqual(self.review(self.primary, {**raw, **changes})['candidates'], [])
        unavailable = self.review(self.primary, {**raw, 'period_start': '', 'period_end': ''})
        self.assertFalse(unavailable['available'])
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                overlap.coverage_review(db, case_id=uuid4(), file_id=self.primary.id, request=raw)

    def test_stale_and_cross_case_import_choices_are_rejected(self):
        batch = self.create(self.primary)
        item = self.b.status(batch)['items'][0]
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'changed'):
                batches.leave_unimported(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                    action='skip', reason='Copy', expected_revision='0'*64, actor=self.f.actor)
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                batches.leave_unimported(db, case_id=uuid4(), batch_id=batch, item_id=UUID(item['id']),
                    action='skip', reason='Copy', expected_revision=item['disposition_revision'], actor=self.f.actor)

    def test_retry_of_older_successful_request_keeps_original_receipt(self):
        receipt = self.f.confirm()
        from services.financial.statement_import import _digest
        from postgres.models.financial import FinancialSourceDocument
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, UUID(receipt['source_document_id']))
            metadata = deepcopy(source.metadata_)
            raw = metadata['statement_import_request']
            raw.pop('coverage_review_revision', None)
            raw.pop('coverage_review_reason', None)
            for row in raw['rows']:
                row.pop('date_unprinted', None)
            metadata['statement_import_request_sha256'] = _digest(raw)
            source.metadata_ = metadata
            db.commit()
        self.assertFalse(self.f.confirm(raw)['created'])
