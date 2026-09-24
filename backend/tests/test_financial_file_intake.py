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
        general = resolve_financial_selection(self.db, case_id=self.case.id, file_ids=[two.id],
            folder_ids=[parent.id, child.id], include_other_formats=True)
        self.assertEqual({f['original_filename'] for f in general['files']}, {'one.PDF', 'two.pdf', 'notes.txt'})
        self.assertEqual(general['skipped_non_pdf'], 0)
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

    def test_evidence_upload_then_send_to_financial_keeps_one_search_result_on_repeat(self):
        from uuid import UUID
        from services.evidence_db_storage import EvidenceDBStorage
        # One existing Evidence upload, already processed for the investigation.
        parent = EvidenceFolder(id=uuid4(), case_id=self.case.id, name='Statements')
        self.db.add(parent); self.db.flush()
        self.file.folder_id = parent.id; self.db.commit()
        processed = []
        async def prepare_reading(db, **kwargs):
            target = db.get(EvidenceFile, kwargs['file_ids'][0])
            processed.append(target.id)
            target.status = 'processed'
            db.add(EvidenceDocumentText(evidence_file_id=target.id, content='synthetic statement',
                content_sha256='a'*64, character_count=19, engine_job_id=uuid4()))
            db.add(EvidenceTableGeometry(evidence_file_id=target.id, page_number=1,
                payload=[], engine_job_id=uuid4()))
            db.commit()
            return {'job_ids': ['financial-reading']}
        self.prepare(process=prepare_reading)
        for _ in range(3):
            selection = resolve_financial_selection(self.db, case_id=self.case.id,
                file_ids=[self.file.id], folder_ids=[parent.id])
            self.assertEqual(len(selection['files']), 1)
            selected = self.db.get(EvidenceFile, UUID(selection['files'][0]['id']))
            self.assertEqual(self.prepare(file=selected, process=prepare_reading)['outcome'], 'ready')
            results = EvidenceDBStorage.search_files(self.db, self.case.id, 'letter')
            self.assertEqual(results['file_total'], 1)
            self.assertEqual(results['files'][0]['id'], str(self.file.id))
            self.assertEqual(len(results['files'][0]['reading_versions']), 1)
        self.assertEqual(len(processed), 1)
        self.assertEqual(self.file.summary, 'Retain completed general processing')

    def test_active_processing_is_not_started_twice(self):
        self.file.status = 'processing'; self.db.commit()
        process = AsyncMock()
        self.assertEqual(self.prepare(process=process)['outcome'], 'processing')
        process.assert_not_awaited()

    def test_retry_of_an_empty_internal_reading_reuses_its_id(self):
        from uuid import UUID
        first = self.prepare()
        version = self.db.get(EvidenceFile, UUID(first['evidence_file_id']))
        version.status = 'processed'
        self.db.commit()
        process = AsyncMock(return_value={'job_ids': ['retry-job']})
        retried = self.prepare(file=version, process=process)
        self.assertEqual(retried['evidence_file_id'], str(version.id))
        self.assertEqual(len(list(self.db.scalars(select(EvidenceFile)))), 2)
        self.assertTrue(process.call_args.kwargs['force_reprocess'])
        self.assertEqual(self.file.summary, 'Retain completed general processing')

    def test_generated_readings_collapse_but_independent_disclosures_do_not(self):
        from uuid import UUID
        from services.financial.source_lineage import lineage_groups
        prepared = self.prepare()
        version = self.db.get(EvidenceFile, UUID(prepared['evidence_file_id']))
        independent = self.new_file(self.file.original_filename)
        foreign = self.new_file(self.file.original_filename, case=self.other_case)
        # Corrupt/cross-case lineage must not absorb a separate disclosure.
        foreign.metadata_ = {'statement_root_evidence_id': str(self.file.id)}
        self.db.commit()
        chosen = resolve_financial_selection(self.db, case_id=self.case.id,
            file_ids=[self.file.id, version.id, independent.id], folder_ids=[])
        self.assertEqual({f['id'] for f in chosen['files']}, {str(version.id), str(independent.id)})
        self.assertEqual(chosen['grouped_readings'], 1)
        self.assertEqual(len(lineage_groups([self.file, version, foreign, independent])), 3)
        original_only = resolve_financial_selection(self.db, case_id=self.case.id, file_ids=[self.file.id], folder_ids=[])
        self.assertEqual(original_only['files'][0]['id'], str(version.id))

    def test_evidence_name_search_and_folder_counts_show_original_once_with_history(self):
        from services.evidence_db_storage import EvidenceDBStorage
        parent = EvidenceFolder(id=uuid4(), case_id=self.case.id, name='Statements')
        self.db.add(parent); self.db.flush()
        self.file.folder_id = parent.id; self.db.commit()
        self.prepare()
        # Same filename/bytes independently disclosed must remain separate.
        independent = self.new_file(self.file.original_filename, folder=parent.id)
        self.db.commit()
        found = EvidenceDBStorage.search_files(self.db, self.case.id, 'letter')
        self.assertEqual(found['file_total'], 2)
        self.assertEqual({f['id'] for f in found['files']}, {str(self.file.id), str(independent.id)})
        original = next(f for f in found['files'] if f['id'] == str(self.file.id))
        self.assertEqual(len(original['reading_versions']), 1)
        contents = EvidenceDBStorage.list_contents(self.db, self.case.id, parent.id, limit=1)
        self.assertEqual(contents['file_total'], 2)
        self.assertEqual(len(contents['files']), 1)
        self.assertEqual(EvidenceDBStorage.get_folder_tree(self.db, self.case.id)[0]['file_count'], 2)
        self.assertEqual(len(EvidenceDBStorage.list_files(self.db, self.case.id, include_reading_versions=False)), 2)
        version_id = original['reading_versions'][0]['id']
        from uuid import UUID
        location = EvidenceDBStorage.get_file_location(self.db, self.case.id, UUID(version_id))
        self.assertEqual(location['folder_id'], str(parent.id))
        self.assertEqual(location['file_id'], version_id)
        self.assertEqual(EvidenceDBStorage.search_files(self.db, self.other_case.id, 'letter')['file_total'], 0)

    def test_already_existing_copy_chain_is_grouped_without_deleting_or_reprocessing(self):
        from services.evidence_db_storage import EvidenceDBStorage
        # Reproduce the old stored state: one uploaded PDF plus two internal
        # readings, all displayed previously as ordinary same-name files.
        first = self.new_file(self.file.original_filename)
        second = self.new_file(self.file.original_filename)
        first.metadata_ = {'statement_root_evidence_id': str(self.file.id),
            'statement_parent_evidence_id': str(self.file.id)}
        second.metadata_ = {'statement_root_evidence_id': str(self.file.id),
            'statement_parent_evidence_id': str(first.id)}
        self.db.commit()
        original_state = {f.id: (f.status, f.stored_path, f.sha256, dict(f.metadata_))
            for f in (self.file, first, second)}
        result = EvidenceDBStorage.search_files(self.db, self.case.id, 'letter')
        self.assertEqual(result['file_total'], 1)
        self.assertEqual(result['files'][0]['id'], str(self.file.id))
        self.assertEqual({r['id'] for r in result['files'][0]['reading_versions']}, {str(first.id), str(second.id)})
        self.assertEqual({f.id: (f.status, f.stored_path, f.sha256, dict(f.metadata_))
            for f in self.db.scalars(select(EvidenceFile))}, original_state)
        self.assertTrue(all(Path(path).exists() for _, path, _, _ in original_state.values()))
        # Corrupt lineage cannot hide genuinely different contents.
        different = self.new_file(self.file.original_filename)
        different.sha256 = 'f' * 64
        different.metadata_ = {'statement_root_evidence_id': str(self.file.id)}
        self.db.commit()
        self.assertEqual(EvidenceDBStorage.search_files(self.db, self.case.id, 'letter')['file_total'], 2)

    def test_removed_financial_version_is_not_reported_as_ready(self):
        result = self.prepare()
        from uuid import UUID
        version = self.db.get(EvidenceFile, UUID(result['evidence_file_id']))
        version.status = 'processed'
        self.db.commit()
        self.change(True, file=version)
        with self.assertRaisesRegex(PdfMappingError, 'removed from Financial'):
            self.prepare()
