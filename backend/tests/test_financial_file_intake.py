import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock
from sqlalchemy import select
from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry, IngestionLog
from services.financial.decisions import Actor
from services.financial.pdf_candidates import PdfMappingError
from services.financial.file_visibility import set_financial_file_visibility, financial_file_visibility
from services.financial.evidence_intake import resolve_financial_selection, prepare_existing_financial_file
from services.financial.statement_import import read_statement_import
from tests.test_financial_duplicates import DuplicateTestCase


class FinancialFileIntakeTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(), tables=[IngestionLog.__table__, EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__])
        self.actor = Actor(self.user.name, self.user.email, self.user.id)
        self.file = self.new_file('letter.pdf')
        self.db.commit()

    def new_file(self, name, folder=None, case=None, status='processed'):
        identifier = uuid4()
        path = Path(self._directory) / str(identifier)
        path.write_bytes(b'%PDF-1.4\nSynthetic intake test')
        file = EvidenceFile(id=identifier, case_id=(case or self.case).id, folder_id=folder,
            original_filename=name, stored_path=str(path), size=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), status=status,
            summary='Retain completed general processing', metadata_={'unrelated': {'keep': True}})
        self.db.add(file); self.db.flush()
        return file

    def change(self, removed, revision='initial', file=None, case=None):
        return set_financial_file_visibility(self.db, case_id=(case or self.case).id,
            evidence_file_id=(file or self.file).id, removed=removed, expected_revision=revision, actor=self.actor)

    def prepare(self, file=None, revision='initial', process=None):
        return asyncio.run(prepare_existing_financial_file(self.db, case_id=self.case.id,
            evidence_file_id=(file or self.file).id, expected_revision=revision, actor=self.actor,
            resolve_path=Path, process_files=process or AsyncMock(return_value={'job_ids': ['job']})))

    def test_remove_restore_persist_with_original_and_history(self):
        before = (self.file.sha256, self.file.stored_path, self.file.status, self.file.summary)
        hidden = self.change(True)
        self.db.expire_all()
        self.assertTrue(financial_file_visibility(self.db.get(EvidenceFile, self.file.id))['financial_removed'])
        self.assertEqual(self.file.metadata_['unrelated'], {'keep': True})
        with self.assertRaisesRegex(PdfMappingError, 'removed from Financial'):
            read_statement_import(self.db, case_id=self.case.id, evidence_file_id=self.file.id)
        restored = self.change(False, hidden['financial_visibility_revision'])
        self.assertFalse(restored['financial_removed'])
        self.assertEqual(before, (self.file.sha256, self.file.stored_path, self.file.status, self.file.summary))
        self.assertTrue(Path(self.file.stored_path).is_file())
        logs = list(self.db.scalars(select(IngestionLog)))
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].extra['actor']['user_id'], str(self.user.id))
        with self.assertRaisesRegex(PdfMappingError, 'Another user'):
            self.change(True, 'initial')

    def test_retry_does_not_duplicate_events_and_case_scope_is_checked(self):
        first = self.change(True)
        self.assertEqual(self.change(True), first)
        self.assertEqual(len(list(self.db.scalars(select(IngestionLog)))), 1)
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            self.change(False, case=self.other_case)

    def test_imported_and_excluded_statement_records_cannot_be_hidden(self):
        document = self.make_document()
        period = self.make_period(document)
        self.add_row(period, document, amount=100)
        self.db.commit()
        for status in ('admitted', 'superseded'):
            document.status = status; self.db.commit()
            with self.assertRaisesRegex(PdfMappingError, 'already has imported'):
                self.change(True, file=self.db.get(EvidenceFile, document.evidence_file_id))
            self.db.rollback()

    def test_folder_selection_includes_descendants_deduplicates_and_skips_other_types(self):
        parent = EvidenceFolder(id=uuid4(), case_id=self.case.id, name='Financial')
        self.db.add(parent); self.db.flush()
        child = EvidenceFolder(id=uuid4(), case_id=self.case.id, parent_id=parent.id, name='Bank')
        self.db.add(child); self.db.flush()
        one = self.new_file('one.PDF', folder=parent.id)
        two = self.new_file('two.pdf', folder=child.id)
        self.new_file('notes.txt', folder=child.id)
        self.db.commit()
        result = resolve_financial_selection(self.db, case_id=self.case.id, file_ids=[two.id], folder_ids=[parent.id, child.id])
        self.assertEqual({f['id'] for f in result['files']}, {str(one.id), str(two.id)})
        self.assertEqual(result['skipped_non_pdf'], 1)
        foreign = self.new_file('foreign.pdf', case=self.other_case); self.db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'no longer available'):
            resolve_financial_selection(self.db, case_id=self.case.id, file_ids=[foreign.id], folder_ids=[parent.id])

    def test_readable_processed_file_is_reused_without_upload_or_processing(self):
        self.db.add(EvidenceDocumentText(evidence_file_id=self.file.id, content='synthetic', content_sha256='a'*64, character_count=9, engine_job_id=uuid4()))
        self.db.add(EvidenceTableGeometry(evidence_file_id=self.file.id, page_number=1, payload=[], engine_job_id=uuid4()))
        self.db.commit()
        hidden = self.change(True)
        process = AsyncMock()
        result = self.prepare(revision=hidden['financial_visibility_revision'], process=process)
        self.assertEqual(result['outcome'], 'ready')
        self.assertEqual(result['evidence_file_id'], str(self.file.id))
        self.assertFalse(financial_file_visibility(self.file)['financial_removed'])
        process.assert_not_awaited()

    def test_processed_evidence_keeps_prior_results_and_reuses_same_financial_version(self):
        async def process(db, **kwargs):
            target = db.get(EvidenceFile, kwargs['file_ids'][0])
            target.status = 'processing'; target.engine_job_id = 'job'; db.commit()
            return {'job_ids': ['job']}
        first = self.prepare(process=process)
        self.assertNotEqual(first['evidence_file_id'], str(self.file.id))
        second = self.prepare(process=AsyncMock(side_effect=AssertionError('duplicate processing')))
        self.assertEqual(second['evidence_file_id'], first['evidence_file_id'])
        self.assertEqual(second['outcome'], 'processing')
        self.assertEqual(self.file.status, 'processed')
        self.assertEqual(self.file.summary, 'Retain completed general processing')
        self.assertEqual(self.file.metadata_, {'unrelated': {'keep': True}})
        self.assertEqual(len(list(self.db.scalars(select(EvidenceFile)))), 2)

    def test_active_processing_is_not_started_twice(self):
        self.file.status = 'processing'; self.db.commit()
        process = AsyncMock()
        self.assertEqual(self.prepare(process=process)['outcome'], 'processing')
        process.assert_not_awaited()

    def test_removed_financial_version_is_not_reported_as_ready(self):
        result = self.prepare()
        from uuid import UUID
        version = self.db.get(EvidenceFile, UUID(result['evidence_file_id']))
        version.status = 'processed'
        self.db.commit()
        self.change(True, file=version)
        with self.assertRaisesRegex(PdfMappingError, 'removed from Financial'):
            self.prepare()
