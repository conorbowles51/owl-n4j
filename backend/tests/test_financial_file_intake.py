import asyncio
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock
from sqlalchemy import select
from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry, IngestionLog
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from postgres.models.financial_recovery import FinancialRecoveryRun, FinancialRecoveryItem
from services.financial.decisions import Actor
from services.financial.pdf_candidates import PdfMappingError
from services.financial.file_visibility import set_financial_file_visibility, financial_file_visibility
from services.financial.evidence_intake import resolve_financial_selection, prepare_existing_financial_file
from services.financial.statement_import import read_statement_import
from tests.test_financial_duplicates import DuplicateTestCase


class FinancialFileIntakeTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(), tables=[IngestionLog.__table__, EvidenceDocumentText.__table__, EvidenceTableGeometry.__table__, Batch.__table__, Item.__table__, FinancialRecoveryRun.__table__, FinancialRecoveryItem.__table__])
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

    def test_membership_removal_supports_every_format_without_clearing_saved_work(self):
        for filename in ('reading.pdf', 'ledger.csv', 'accounts.xlsx', 'report.docx', 'scan.jpeg', 'unusual.source'):
            with self.subTest(filename=filename):
                file = self.new_file(filename)
                file.metadata_ = {**file.metadata_, 'financial_workspace': {'schema': 'loupe.financial.file/1', 'selected_by': str(self.user.id)},
                    'financial_review_progress': {'': {'request': {'holder': 'Preserve investigator correction'}}},
                    'financial_duplicate_dispositions': {'': {'status': 'needs_comparison'}}}
                batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, status='review',
                    files=[{'source_id': str(file.id), 'file_id': str(file.id), 'status': 'checked'}])
                self.db.add(batch); self.db.flush()
                item = Item(id=uuid4(), batch_id=batch.id, file_id=file.id, statement_key='', status='attention',
                    summary={'problem_count': 1}, review_request={'holder': 'Saved batch correction'})
                self.db.add(item); self.db.commit()
                original, draft = deepcopy(file.metadata_), deepcopy(item.review_request)
                hidden = self.change(True, file=file)
                self.assertTrue(hidden['financial_removed'])
                self.assertFalse(hidden['financial_imports_removed'])
                self.assertEqual({key: file.metadata_[key] for key in original}, original)
                self.assertEqual(item.review_request, draft)
                self.assertEqual((batch.status, item.status), ('review', 'attention'))
                self.change(False, hidden['financial_visibility_revision'], file=file)
                self.assertFalse(financial_file_visibility(file)['financial_removed'])
                self.assertEqual(item.review_request, draft)
                self.assertTrue(Path(file.stored_path).exists())

    def test_membership_removal_guards_processing_queued_and_pending_imports_without_changing_jobs(self):
        batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, status='review',
            files=[{'source_id': str(self.file.id), 'file_id': str(self.file.id), 'status': 'checked'}])
        self.db.add(batch); self.db.flush()
        item = Item(id=uuid4(), batch_id=batch.id, file_id=self.file.id, statement_key='', status='attention', summary={}, review_request={'holder': 'Keep'})
        self.db.add(item); self.db.commit()
        scenarios = (
            ('processing', 'checked', 'attention', None, None, 'still processing'),
            ('processed', 'waiting', 'attention', None, None, 'queued or being processed'),
            ('processed', 'processing', 'attention', None, None, 'queued or being processed'),
            ('processed', 'checked', 'pending_import', None, None, 'import for this file is pending'),
            ('processed', 'preparing', 'attention', 'worker', datetime.now(timezone.utc) + timedelta(minutes=5), 'queued or being processed'),
        )
        for file_state, batch_file_state, item_state, token, lease, message in scenarios:
            with self.subTest(message=message):
                self.file.status = file_state
                batch.files = [{**batch.files[0], 'status': batch_file_state}]
                batch.worker_token, batch.lease_until = token, lease
                item.status = item_state
                self.db.commit()
                before = (deepcopy(self.file.metadata_), deepcopy(batch.files), batch.status, batch.worker_token, item.status, deepcopy(item.review_request))
                with self.assertRaisesRegex(PdfMappingError, message):
                    self.change(True)
                self.db.rollback()
                self.assertEqual((self.file.metadata_, batch.files, batch.status, batch.worker_token, item.status, item.review_request), before)
                self.assertFalse(list(self.db.scalars(select(IngestionLog))))

    def test_finished_file_can_be_hidden_while_an_independent_file_is_processing(self):
        other = self.new_file('independent.pdf', status='processing')
        batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, status='preparing',
            worker_token='worker', lease_until=datetime.now(timezone.utc) + timedelta(minutes=5),
            files=[{'source_id': str(self.file.id), 'file_id': str(self.file.id), 'status': 'checked'},
                   {'source_id': str(other.id), 'file_id': str(other.id), 'status': 'processing'}])
        self.db.add(batch); self.db.commit()
        previous = deepcopy(batch.files)
        self.change(True)
        self.assertTrue(financial_file_visibility(self.file)['financial_removed'])
        self.assertFalse(financial_file_visibility(other)['financial_removed'])
        self.assertEqual(batch.files, previous)
        self.assertEqual((other.status, batch.worker_token), ('processing', 'worker'))

    def test_processing_in_a_verified_reading_protects_the_family_but_not_a_separate_upload(self):
        child = self.new_file('reading.pdf', status='processing')
        child.metadata_ = {'statement_root_evidence_id': str(self.file.id)}
        independent = self.new_file('letter.pdf')
        self.db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'still processing'):
            self.change(True)
        self.db.rollback()
        self.change(True, file=independent)
        self.assertFalse(financial_file_visibility(self.file)['financial_removed'])
        self.assertFalse(financial_file_visibility(child)['financial_removed'])
        self.assertTrue(financial_file_visibility(independent)['financial_removed'])

    def test_removal_groups_only_verified_readings_and_restore_keeps_earlier_removals(self):
        from services.financial.source_lineage import current_version
        child = self.new_file('reading.pdf')
        earlier = self.new_file('earlier.pdf')
        independent = self.new_file('independently uploaded.pdf')
        for file in (child, earlier):
            file.metadata_ = {'statement_root_evidence_id': str(self.file.id), 'statement_parent_evidence_id': str(self.file.id),
                'financial_review_progress': {'': {'request': {'holder': 'Keep this review'}}}}
        earlier.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
        earlier.metadata_ = {**earlier.metadata_, 'financial_file_visibility': {'removed': True, 'revision': 'earlier-choice', 'changed_at': '2020-01-01T12:00:00+00:00'}}
        self.db.commit()
        hidden = self.change(True, file=child)
        self.assertTrue(all(financial_file_visibility(file)['financial_removed'] for file in (self.file, child, earlier)))
        self.assertFalse(financial_file_visibility(independent)['financial_removed'])
        representative = current_version([self.file, child, earlier])
        self.assertNotEqual(representative.id, earlier.id)
        self.assertEqual(financial_file_visibility(representative)['financial_visibility_revision'], hidden['financial_visibility_revision'])
        self.change(False, hidden['financial_visibility_revision'], file=child)
        self.assertFalse(any(financial_file_visibility(file)['financial_removed'] for file in (self.file, child, independent)))
        self.assertTrue(financial_file_visibility(earlier)['financial_removed'])
        self.assertEqual(child.metadata_['financial_review_progress']['']['request']['holder'], 'Keep this review')

    def test_an_import_on_a_retained_reading_protects_the_entire_family(self):
        document = self.make_document()
        root = self.db.get(EvidenceFile, document.evidence_file_id)
        self.file.sha256 = root.sha256
        self.file.metadata_ = {**self.file.metadata_, 'statement_root_evidence_id': str(root.id)}
        self.db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'already has imported financial records'):
            self.change(True)
        self.db.rollback()
        self.assertFalse(financial_file_visibility(self.file)['financial_removed'])

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
        self.assertTrue(financial_file_visibility(self.file)['financial_removed'])
        self.assertTrue(financial_file_visibility(version)['financial_removed'])
        # The stale prepare request must not restore the family or return an
        # older reading as ready after the investigator removed it.
        with self.assertRaisesRegex(PdfMappingError, 'Another user changed this file'):
            self.prepare()
