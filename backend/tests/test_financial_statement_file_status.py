from services.financial.statement_file_status import statement_file_status
from tests.test_financial_duplicates import DuplicateTestCase


class StatementFileStatusTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        from postgres.base import Base
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
        Base.metadata.create_all(self.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__, FinancialImportBatch.__table__, FinancialImportBatchItem.__table__])

    def test_identical_upload_links_saved_source_without_double_counting(self):
        from uuid import uuid4
        from postgres.models.evidence import EvidenceFile
        document = self.make_document()
        document.document_type = 'statement_review'
        period = self.make_period(document)
        self.add_row(period, document, amount=100)
        copy = EvidenceFile(id=uuid4(), case_id=self.case.id, original_filename='copy.pdf',
            stored_path='/synthetic/copy.pdf', sha256=document.sha256_at_ingestion)
        foreign = EvidenceFile(id=uuid4(), case_id=self.other_case.id, original_filename='other.pdf',
            stored_path='/synthetic/other.pdf', sha256=document.sha256_at_ingestion)
        self.db.add_all([copy, foreign]); self.db.commit()
        files = statement_file_status(self.db, case_id=self.case.id)['files']
        linked = next(f for f in files if f['evidence_file_id'] == str(copy.id))
        self.assertEqual(linked['same_pdf_saved_file_ids'], [str(document.evidence_file_id)])
        self.assertEqual(linked['current_transactions'], 0)
        self.assertEqual(linked['periods'], [])
        self.assertEqual(sum(f['current_transactions'] for f in files), 1)
        self.assertFalse(any(f['evidence_file_id'] == str(foreign.id) for f in files))
        document.status = 'superseded'; self.db.commit()
        self.assertFalse(any(f['evidence_file_id'] == str(copy.id) for f in statement_file_status(self.db, case_id=self.case.id)['files']))

    def test_individual_import_cannot_still_be_offered_as_ready_by_old_batch_snapshot(self):
        from uuid import uuid4
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        document = self.make_document()
        document.document_type = 'statement_review'
        document.metadata_ = {'statement_import_statement_id': 'saved-period'}
        self.make_period(document)
        batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, files=[], status='review')
        self.db.add(batch); self.db.flush()
        for key in ('saved-period', 'new-period'):
            self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                statement_key=key, status='ready', summary={'can_import': True}))
        self.db.commit()
        file = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(file['prepared_periods'], 2)
        self.assertEqual(file['available_periods'], 1)
        self.assertEqual([p['statement_id'] for p in file['ready_periods']], ['new-period'])
        self.assertEqual(len(file['periods']), 1)

    def test_ready_period_destinations_use_latest_case_scoped_importable_snapshot(self):
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        document = self.make_document()
        now = datetime.now(timezone.utc)
        summary = dict(can_import=True, holder='Synthetic holder', institution='Synthetic bank',
            account='TEST-ACCOUNT', currency='USD', period_start='2024-01-01', period_end='2024-01-31',
            transaction_count=7, incomplete_count=1, problem_count=2)
        for index, batch_state in enumerate(('review', 'review', 'removed')):
            batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, files=[], status=batch_state)
            self.db.add(batch); self.db.flush()
            self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                statement_key='one-period', status='attention', summary={**summary, 'transaction_count': index+6},
                updated_at=now+timedelta(seconds=index)))
            if index == 1:
                for key, state, can_import in [('blocked', 'attention', False), ('pending', 'pending_import', True), ('skipped', 'skipped', True)]:
                    self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                        statement_key=key, status=state, summary={**summary, 'can_import': can_import}))
        self.db.commit()
        status = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(status['available_periods'], 1)
        self.assertEqual(status['ready_periods'], [dict(statement_id='one-period', **{key:value for key,value in summary.items() if key != 'can_import'})])
        self.assertEqual(statement_file_status(self.db, case_id=self.other_case.id)['files'], [])

    def test_saved_file_status_counts_current_payments_and_preserves_periods(self):
        document = self.make_document()
        period = self.make_period(document)
        original = self.add_row(period, document, amount=100)
        replacement = self.add_row(period, document, amount=200)
        original.ledger_status = 'superseded'
        original.superseded_by_id = replacement.id
        self.db.commit()
        result = statement_file_status(self.db, case_id=self.case.id)
        item = next(f for f in result['files'] if f['evidence_file_id'] == str(document.evidence_file_id))
        self.assertEqual(item['current_transactions'], 1)
        self.assertEqual(item['periods'][0]['account_id'], str(period.account_id))
        self.assertEqual(item['periods'][0]['start'], period.period_start.isoformat())
        document.status = 'superseded'
        self.db.commit()
        result = statement_file_status(self.db, case_id=self.case.id)
        self.assertEqual(result['files'][0]['current_transactions'], 0)
        self.assertEqual(result['files'][0]['periods'][0]['source_status'], 'superseded')
        self.assertEqual(statement_file_status(self.db, case_id=self.other_case.id)['files'], [])

    def test_saved_file_status_omits_a_file_with_inconsistent_case_ownership(self):
        from postgres.models.evidence import EvidenceFile
        document = self.make_document()
        self.make_period(document)
        self.db.get(EvidenceFile, document.evidence_file_id).case_id = self.other_case.id
        self.db.commit()
        self.assertEqual(statement_file_status(self.db, case_id=self.case.id)['files'], [])

    def test_incomplete_records_without_a_period_are_visible_and_not_counted_as_payments(self):
        document = self.make_document()
        document.document_type = 'statement_review'
        document.metadata_ = {'statement_incomplete_records': [dict(id='one'), dict(id='two'), dict(id='resolved', resolved_transaction_id='saved')]}
        self.db.commit()
        item = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(item['current_transactions'], 0)
        self.assertEqual(item['incomplete_count'], 2)
        self.assertEqual(item['periods'], [])
        document.status = 'superseded'
        self.db.commit()
        self.assertEqual(statement_file_status(self.db, case_id=self.case.id)['files'], [])

    def test_incomplete_records_name_their_period_and_separate_complete_values_held_for_reconciliation(self):
        document = self.make_document()
        document.document_type = 'statement_review'
        period = self.make_period(document)
        blocker = dict(kind='arithmetic', message='The payments do not add up to the printed closing balance.')
        document.metadata_ = {'statement_admission': {'blockers': [blocker]}, 'statement_incomplete_records': [
            dict(id='7:0:17', missing_fields=['date']),
            dict(id='manual:one', missing_fields=[]),
            dict(id='manual:two', missing_fields=[], resolved_transaction_id='saved')]}
        self.db.commit()
        item = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(item['incomplete_count'], 2)
        self.assertEqual(item['awaiting_reconciliation_count'], 1)
        self.assertEqual(item['incomplete_sources'], [dict(source_document_id=str(document.id),
            period_start=period.period_start.isoformat(), period_end=period.period_end.isoformat(),
            missing_count=1, awaiting_reconciliation_count=1, blockers=[blocker['message']])])

    def _prepared(self, document, rows):
        from uuid import uuid4
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, files=[], status='review')
        self.db.add(batch); self.db.flush()
        for key, status, summary in rows:
            self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                statement_key=key, status=status, summary=summary))
        self.db.commit()
        return statement_file_status(self.db, case_id=self.case.id)['files'][0]

    def test_a_coverage_note_is_counted_as_an_overlap_not_a_check(self):
        document = self.make_document()
        document.document_type = 'statement_review'
        document.metadata_ = {'statement_import_statement_id': 'saved'}
        self.make_period(document)
        coverage = dict(kind='coverage', row_id=None, message='Another supplied statement covers some of these dates.')
        file = self._prepared(document, [
            ('saved', 'imported', dict(problem_count=1, problems=[coverage])),
            ('flagged', 'imported', dict(problem_count=2, problems=[coverage, dict(kind='reading', message='Check the date.')])),
            ('legacy', 'imported', dict(problem_count=1))])
        self.assertEqual(file['overlapping_periods'], 1)
        self.assertEqual(file['periods_with_checks'], 2)

    def test_a_second_reading_of_a_saved_period_is_a_repeat_not_unsaved(self):
        document = self.make_document()
        document.document_type = 'statement_review'
        document.metadata_ = {'statement_import_statement_id': 'saved'}
        period = self.make_period(document)
        dates = dict(period_start=period.period_start.isoformat(), period_end=period.period_end.isoformat())
        coverage = dict(kind='coverage', message='Another supplied statement covers some of these dates.')
        file = self._prepared(document, [
            ('saved', 'imported', dict(dates, problem_count=1, problems=[coverage])),
            ('second-key', 'imported', dict(dates, problem_count=1, problems=[coverage])),
            ('other-dates', 'imported', dict(period_start='2001-01-01', period_end='2001-01-31'))])
        self.assertEqual(file['prepared_periods'], 3)
        self.assertEqual(file['repeat_periods'], 1)
        self.assertEqual(len(file['periods']), 1)
        self.assertEqual(file['overlapping_periods'], 1)
        self.assertEqual(file['periods_with_checks'], 0)

    def _empty_file(self, origins, summary=None):
        from uuid import uuid4
        from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        EvidenceDocumentText.__table__.create(self.db.connection(), checkfirst=True)
        file = EvidenceFile(id=uuid4(), case_id=self.case.id, original_filename='empty.pdf',
            stored_path='/synthetic/empty.pdf', sha256=uuid4().hex * 2, status='processed')
        self.db.add(file); self.db.flush()
        if origins is not None:
            self.db.add(EvidenceDocumentText(evidence_file_id=file.id, content='x', content_sha256='0' * 64,
                character_count=1, source_locations=[dict(kind='page', page_number=n + 1, text_origin=origin)
                    for n, origin in enumerate(origins)]))
        batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, files=[], status='review')
        self.db.add(batch); self.db.flush()
        self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=file.id, statement_key='', status='attention',
            summary=summary or dict(can_import=False, transaction_count=0, record_count=None, period_start='',
                period_end='', currency='', problem_count=1,
                problems=[dict(message='Choose the currency printed on these statements.')])))
        self.db.commit()
        return next(f for f in statement_file_status(self.db, case_id=self.case.id)['files']
                    if f['evidence_file_id'] == str(file.id))

    def test_an_empty_reading_says_why_nothing_was_read(self):
        scanned = self._empty_file(['recognised_glyphs', 'recognised_glyphs'])
        self.assertEqual(scanned['empty_reading']['reason'], 'scanned_image')
        self.assertIn('scanned image', scanned['empty_reading']['message'])
        layout = self._empty_file(['recognised_glyphs', 'digital_text_layer'])
        self.assertEqual(layout['empty_reading']['reason'], 'layout_not_supported')
        nothing = self._empty_file(None)
        self.assertEqual(nothing['empty_reading']['reason'], 'no_statement')

    def test_a_reading_that_found_rows_or_dates_is_not_empty(self):
        found = self._empty_file(['digital_text_layer'], summary=dict(can_import=False, transaction_count=0,
            period_start='2024-01-01', period_end='2024-01-31', problem_count=1, problems=[]))
        self.assertNotIn('empty_reading', found)
        rows = self._empty_file(['digital_text_layer'], summary=dict(can_import=False, transaction_count=3,
            period_start='', period_end='', problem_count=1, problems=[]))
        self.assertNotIn('empty_reading', rows)

    def test_status_is_reused_only_while_the_fingerprint_is_unchanged(self):
        from unittest import mock
        import importlib
        module = importlib.import_module('services.financial.statement_file_status')
        fingerprint = [('items', 1, 'a')]
        with mock.patch.object(module, 'status_fingerprint', lambda session, case_id: tuple(fingerprint)), \
                mock.patch.object(module, '_statement_file_status', wraps=module._statement_file_status) as compute:
            module._cache.clear()
            first = module.statement_file_status(self.db, case_id=self.case.id)
            first['files'].append('caller mutation must not leak into the cache')
            second = module.statement_file_status(self.db, case_id=self.case.id)
            self.assertEqual(compute.call_count, 1)
            self.assertNotIn('caller mutation must not leak into the cache', second['files'])
            fingerprint[0] = ('items', 2, 'b')
            module.statement_file_status(self.db, case_id=self.case.id)
            self.assertEqual(compute.call_count, 2)
            module.statement_file_status(self.db, case_id=self.case.id, use_cache=False)
            self.assertEqual(compute.call_count, 3)
        module._cache.clear()

    def test_sqlite_is_never_cached(self):
        from services.financial.statement_file_status import status_fingerprint
        self.assertIsNone(status_fingerprint(self.db, self.case.id))
