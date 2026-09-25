"""Saving one review stays local; importing still checks all competing sources."""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import event, select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches, statement_import
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import StatementReviewDraft
from tests import test_financial_statement_overlap as fixtures


class BatchReviewSaveScopeTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.StatementOverlapTests()
        self.fixture.setUp()
        self.f = self.fixture.f

    def tearDown(self):
        self.fixture.tearDown()

    def test_saving_one_review_does_not_read_unrelated_legacy_statements(self):
        f = self.f
        batch = self.fixture.create(self.fixture.primary)
        with f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item_id = item.id
            original = db.get(EvidenceFile, f.file.id)
            text = db.get(EvidenceDocumentText, original.id)
            geometry = db.get(EvidenceTableGeometry, (original.id, 1))
            legacy = {key: value for key, value in item.summary.items()
                if key not in ('institution', 'account_type', 'review_model', 'can_import')}
            # Old summaries need hydration when comparing a batch. They must
            # not turn saving one draft into 100 source reads under its locks.
            for number in range(99):
                file_id = uuid4()
                db.add(EvidenceFile(id=file_id, case_id=f.case.id,
                    original_filename=f'Synthetic old statement {number}.pdf',
                    stored_path=original.stored_path, size=original.size,
                    sha256=original.sha256, status='processed', metadata_={}))
                db.add(EvidenceDocumentText(evidence_file_id=file_id, content=text.content,
                    content_sha256=text.content_sha256, character_count=text.character_count,
                    engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
                db.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=1,
                    engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
                db.add(Item(id=uuid4(), batch_id=batch, file_id=file_id,
                    statement_key=item.statement_key, status='attention',
                    summary={**deepcopy(legacy), 'source_id':str(file_id),
                        'filename':f'Synthetic old statement {number}.pdf'}))
            db.commit()
        raw = f.request()
        raw['rows'][1].update(description='Saved investigator correction', reason='Checked original.')
        request = StatementReviewDraft.model_validate(raw)
        saved_request = request.model_dump(mode='json')
        reads, queries = [], []
        reader = statement_import.read_statement_import

        def read(db, **kwargs):
            reads.append(kwargs['evidence_file_id'])
            return reader(db, **kwargs)

        def sql(*args):
            queries.append(args[2])

        event.listen(f.engine, 'before_cursor_execute', sql)
        try:
            with f.SessionLocal() as db, \
                    patch.object(batches, 'read_statement_import', side_effect=read), \
                    patch.object(statement_import, 'read_statement_import', side_effect=read):
                result = batches.save_review(db, case_id=f.case.id, batch_id=batch,
                    item_id=item_id, request=request,
                    expected_review_revision=batches._digest({}))
        finally:
            event.remove(f.engine, 'before_cursor_execute', sql)
        self.assertEqual(reads, [f.file.id])
        self.assertLessEqual(len(queries), 20, 'Save must not query every other statement.')
        # This is the saved draft assessment, not permission to import.
        self.assertEqual(result['status'], 'ready')
        with f.SessionLocal() as db:
            saved = db.get(Item, item_id)
            self.assertEqual(saved.review_request, saved_request)
            self.assertEqual(result['review_revision'], batches._digest(saved_request))
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])

    def test_saved_draft_status_does_not_bypass_overlapping_source_import_check(self):
        f = self.f
        other = self.fixture.copy_file(revised=True)
        batch = self.fixture.create(self.fixture.primary, other)
        state = self.fixture.b.status(batch)
        item = next(value for value in state['items'] if value['file_id'] == str(other.id))
        f.file = other
        raw = f.request()
        raw['rows'][1].update(description='Saved investigator correction', reason='Checked original.')
        request = StatementReviewDraft.model_validate(raw)
        with f.SessionLocal() as db:
            result = batches.save_review(db, case_id=f.case.id, batch_id=batch,
                item_id=UUID(item['id']), request=request,
                expected_review_revision=batches._digest({}))
        self.assertEqual(result['status'], 'ready')  # Local draft assessment only.
        reopened = self.fixture.b.status(batch)
        projected = next(value for value in reopened['items'] if value['id'] == item['id'])
        self.assertEqual(projected['status'], 'attention')
        self.assertFalse(projected['can_import'])
        self.assertTrue(projected['coverage_review']['candidates'])
        with f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'no new statement records'):
                batches.queue_import(db, case_id=f.case.id, batch_id=batch,
                    expected_revision=reopened['ready_revision'], actor=f.actor)
        with self.assertRaises(PdfMappingError):
            batches.confirm_review(session_factory=f.SessionLocal, case_id=f.case.id,
                batch_id=batch, item_id=UUID(item['id']), request=request,
                expected_review_revision=result['review_revision'], actor=f.actor,
                resolve_path=lambda file:Path(file.stored_path))
        with f.SessionLocal() as db:
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
            self.assertEqual(db.get(Item, UUID(item['id'])).review_request, request.model_dump(mode='json'))
            self.assertIsNotNone(db.get(EvidenceFile, other.id))
