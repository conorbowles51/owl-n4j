import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch as Batch
from services.financial import import_batches
from services.financial.import_removal import preview_removal, remove_imports
from services.financial.evidence_intake import prepare_existing_financial_file
from services.financial.file_visibility import financial_file_visibility
from services.financial.statement_import import read_statement_import, confirm_statement_import
from services.financial.transaction_query import list_transactions
from services.financial.review_recovery import saved_ancestor_reviews
from services.financial.pdf_candidates import PdfMappingError


class FinancialImportRemovalTests(TestCase):
    def setUp(self):
        from tests.test_financial_import_batches import BatchImportTests
        self.fixture = BatchImportTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        from postgres.base import Base
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.batch = self.fixture.create()
        self.fixture.advance(self.batch)
        self.receipt = self.f.confirm()

    def tearDown(self):
        self.fixture.tearDown()

    def preview(self, **selection):
        return preview_removal(self.f.db, case_id=self.f.case.id, **(selection or dict(batch_ids=[self.batch])))

    def remove(self, preview=None, **selection):
        return remove_imports(self.f.db, case_id=self.f.case.id, actor=self.f.actor,
            expected_revision=(preview or self.preview(**selection))['revision'],
            **(selection or dict(batch_ids=[self.batch])))

    def test_bulk_removal_excludes_payments_and_archives_related_batches_but_retains_source_history(self):
        second = self.fixture.create()
        self.fixture.advance(second)
        proposal = self.preview(batch_ids=[self.batch, second])
        self.assertEqual((proposal['file_count'], proposal['batch_count'], proposal['transaction_count']), (1, 2, 12))
        original_bytes = self.f.path.read_bytes()
        self.remove(proposal, batch_ids=[self.batch, second])
        self.assertEqual(list_transactions(self.f.db, self.f.case.id), [])
        self.assertEqual(self.f.path.read_bytes(), original_bytes)
        self.assertIsNotNone(self.f.db.get(EvidenceFile, self.f.file.id))
        source = self.f.db.get(FinancialSourceDocument, UUID(self.receipt['source_document_id']))
        self.assertEqual(source.status, 'rejected')
        self.assertEqual(source.metadata_['financial_import_removal']['actor']['user_id'], str(self.f.actor.user_id))
        self.assertEqual(len(list(self.f.db.scalars(select(FinancialTransaction)))), 12)
        from services.financial.statement_file_status import statement_file_status
        self.assertEqual(statement_file_status(self.f.db, case_id=self.f.case.id)['files'], [])
        for batch_id in (self.batch, second):
            with self.assertRaisesRegex(PdfMappingError, 'removed'):
                import_batches.batch_for(self.f.db, self.f.case.id, batch_id, lock=True)
        with self.assertRaisesRegex(PdfMappingError, 'removed'):
            self.f.preview()

    def test_stale_preview_cross_case_and_running_worker_cannot_remove_anything(self):
        preview = self.preview()
        batch = self.f.db.get(Batch, self.batch)
        batch.worker_token = 'active'
        batch.lease_until = datetime.now(timezone.utc) + timedelta(minutes=5)
        self.f.db.commit()
        current = self.preview()
        self.assertFalse(current['can_remove'])
        with self.assertRaises(PdfMappingError):
            self.remove(preview)
        self.f.db.rollback()
        with self.assertRaisesRegex(PdfMappingError, 'running'):
            self.remove(current)
        self.f.db.rollback()
        with self.assertRaises(PdfMappingError):
            preview_removal(self.f.db, case_id=uuid4(), batch_ids=[self.batch])
        self.assertEqual(len(list_transactions(self.f.db, self.f.case.id)), 12)

    def test_fresh_processing_has_new_reading_no_old_draft_and_reimport_counts_once(self):
        # Preserve a bad saved review to prove it cannot be silently recovered.
        file = self.f.db.get(EvidenceFile, self.f.file.id)
        bad = self.f.request()
        bad['holder'] = 'Old incorrect holder'
        file.metadata_ = {**(file.metadata_ or {}), 'financial_review_progress': {'': {'request': bad}}}
        self.f.db.commit()
        result = self.remove(file_ids=[file.id])
        process = AsyncMock(return_value={'job_ids': [str(uuid4())]})
        args = dict(case_id=self.f.case.id, evidence_file_id=file.id,
            expected_revision=result['removal_id'], actor=self.f.actor, resolve_path=Path, process_files=process)
        fresh = asyncio.run(prepare_existing_financial_file(self.f.db, **args))
        process.assert_awaited_once()

        new_id = UUID(fresh['evidence_file_id'])
        self.assertNotEqual(new_id, file.id)
        new_file = self.f.db.get(EvidenceFile, new_id)
        self.assertEqual(Path(new_file.stored_path).read_bytes(), self.f.path.read_bytes())
        self.assertEqual(saved_ancestor_reviews(self.f.db, new_file), [])
        self.assertFalse(financial_file_visibility(new_file)['financial_removed'])
        self.assertIsNone(self.f.db.scalar(select(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id == new_id)))
        # Simulate the extraction worker returning a new reading of the same PDF.
        old_text = self.f.db.scalar(select(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id == file.id))
        new_job = uuid4()
        self.f.db.add(EvidenceDocumentText(evidence_file_id=new_id, content=old_text.content,
            content_sha256=old_text.content_sha256, character_count=old_text.character_count,
            engine_job_id=new_job, source_locations=deepcopy(old_text.source_locations)))
        for geometry in self.f.db.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == file.id)):
            self.f.db.add(EvidenceTableGeometry(evidence_file_id=new_id, page_number=geometry.page_number,
                engine_job_id=new_job, payload=deepcopy(geometry.payload)))
        new_file.status = 'processed'
        self.f.db.commit()
        proposal = read_statement_import(self.f.db, case_id=self.f.case.id, evidence_file_id=new_id)
        self.assertIsNone(proposal.get('current_import'))
        self.assertFalse(proposal.get('previous_saved_review'))
        self.assertFalse(proposal.get('saved_review'))
        request = import_batches.initial_request(proposal)
        receipt = confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            evidence_file_id=new_id, request=request, actor=self.f.actor, resolve_path=Path)
        self.assertNotEqual(receipt['source_document_id'], self.receipt['source_document_id'])
        self.f.db.expire_all()
        self.assertEqual(len(list_transactions(self.f.db, self.f.case.id)), 12)
        again = asyncio.run(prepare_existing_financial_file(self.f.db, **args))
        self.assertEqual(again['evidence_file_id'], str(new_id))
        process.assert_awaited_once()

    def test_removing_one_pdf_keeps_other_files_and_reviews_in_a_shared_batch(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        other = self.f.evidence('b' * 64)
        other.original_filename = 'Keep this PDF.pdf'
        other.status = 'processed'
        other.metadata_ = {'case_note': 'Keep this file and its review'}
        batch = self.f.db.get(Batch, self.batch)
        batch.files = [*batch.files, dict(source_id=str(other.id), file_id=str(other.id),
            filename=other.original_filename, status='checked', expected_revision='initial')]
        item = Item(id=uuid4(), batch_id=batch.id, file_id=other.id, statement_key='keep',
            status='attention', summary={}, review_request={'holder': 'Keep my correction', 'rows': []})
        self.f.db.add(item)
        self.f.db.commit()
        preview = self.preview(file_ids=[self.f.file.id])
        self.assertEqual((preview['archived_batch_count'], preview['updated_batch_count']), (0, 1))
        self.remove(preview, file_ids=[self.f.file.id])
        self.assertEqual(batch.status, 'review')
        self.assertEqual([f['file_id'] for f in batch.files], [str(other.id)])
        self.assertEqual(item.status, 'attention')
        self.assertEqual(item.review_request['holder'], 'Keep my correction')
        self.assertEqual(other.metadata_, {'case_note': 'Keep this file and its review'})

    def test_concurrent_transaction_edit_requires_a_new_preview(self):
        preview = self.preview()
        row = self.f.db.scalar(select(FinancialTransaction))
        row.metadata_ = {**row.metadata_, 'investigation_labels': {'category': 'Reviewed'}}
        self.f.db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'changed since the preview'):
            self.remove(preview)
        self.f.db.rollback()
        self.assertEqual(len(list_transactions(self.f.db, self.f.case.id)), 12)
