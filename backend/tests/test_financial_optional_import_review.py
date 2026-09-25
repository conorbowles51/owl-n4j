from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, AsyncMock
from uuid import UUID, uuid4
from sqlalchemy import select
from tests import test_financial_statement_import as fixtures
from services.financial.statement_import import StatementImportRequest
from services.financial.statement_admission import assess_admission
from services.financial.pdf_candidates import PdfMappingError
from services.financial.import_batches import initial_request, assess
from services.financial.imported_records import imported_records, complete_record, CompleteImportedRecord
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument


class OptionalImportReviewTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def proposal(self, missing=None):
        proposal = deepcopy(self.f.preview())
        row = next(r for r in proposal['rows'] if not r['excluded'])
        if missing:
            row['fields'].pop(missing, None)
        row['issues'] = ['Check this reading against the statement.']
        return proposal, row

    def save(self, proposal):
        raw = initial_request(proposal)
        with patch('services.financial.statement_import.read_statement_import', return_value=proposal):
            return self.f.confirm(raw)

    def save_legacy(self, proposal):
        # Rehearse records left by the former permissive importer. Only fixture
        # construction bypasses admission; every correction/retry below uses
        # the current production gate and immutable saved source contract.
        with patch('services.financial.statement_admission.require_admission', side_effect=assess_admission):
            return self.save(proposal)

    def test_unchanged_flagged_reading_stays_in_review_without_new_payments(self):
        proposal, row = self.proposal()
        state, summary = assess(proposal)
        self.assertEqual(state, 'attention')
        self.assertFalse(summary['can_import'])
        self.assertTrue(any(i.get('row_id') == row['id'] for i in summary['admission']['blockers']))
        with self.f.SessionLocal() as db:
            existing_sources = set(db.scalars(select(FinancialSourceDocument.id)))
        with self.assertRaisesRegex(PdfMappingError, 'remains in review'):
            self.save(proposal)
        with self.f.SessionLocal() as db:
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
            self.assertEqual(set(db.scalars(select(FinancialSourceDocument.id))), existing_sources)

    def test_missing_amount_is_retained_without_zero_and_can_be_completed_once(self):
        proposal, row = self.proposal('amount_minor')
        with self.assertRaises(PdfMappingError):
            self.save(proposal)
        receipt = self.save_legacy(proposal)
        self.assertEqual((receipt['record_count'], receipt['transaction_count'], receipt['incomplete_count']), (12, 11, 1))
        with self.f.SessionLocal() as db:
            result = imported_records(db, case_id=self.f.case.id)
            self.assertEqual(result['total'], 1)
            record = result['records'][0]
            self.assertEqual(record['fields']['amount_minor'], '')
            self.assertEqual(imported_records(db, case_id=uuid4())['total'], 0)
            self.assertTrue(all(t.amount_minor > 0 for t in db.scalars(select(FinancialTransaction))))
        corrected = {**record['fields'], 'amount_minor':'12500000', 'reason':''}
        request = CompleteImportedRecord(row=corrected, currency='EUR', version=0)
        args = dict(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            source_id=UUID(receipt['source_document_id']), request=request, actor=self.f.actor)
        saved = complete_record(**args)
        self.assertTrue(saved['created'])
        self.assertFalse(complete_record(**args)['created'])
        with self.f.SessionLocal() as db:
            self.assertEqual(imported_records(db, case_id=self.f.case.id)['total'], 0)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)
            transaction = db.get(FinancialTransaction, UUID(saved['transaction_id']))
            self.assertEqual(transaction.amount_minor, 12500000)
            self.assertEqual(transaction.row_index, 0)
            self.assertNotIn('amount_minor', transaction.provenance['statement_import_original']['fields'])
            document = db.get(FinancialSourceDocument, UUID(receipt['source_document_id']))
            self.assertFalse(any(i.get('row_id') == row['id'] for i in document.metadata_['statement_import_issues']))
            from services.financial.review_recovery import saved_ancestor_reviews
            next_file = self.f.evidence(self.f.file.sha256)
            next_file.metadata_ = {'statement_parent_evidence_id': str(self.f.file.id)}
            self.f.db.commit()
            reviews = saved_ancestor_reviews(db, next_file)
            recovered = next(r for r in reviews if r['origin'].startswith('Corrected imported'))
            self.assertEqual(next(r for r in recovered['request']['rows'] if r['id'] == row['id'])['amount_minor'], '12500000')
            self.assertEqual(next(r for r in document.metadata_['statement_import_request']['rows'] if r['id'] == row['id'])['amount_minor'], '')

    def test_missing_date_is_not_replaced_with_an_invented_date(self):
        proposal, _ = self.proposal('date')
        with self.assertRaises(PdfMappingError):
            self.save(proposal)
        receipt = self.save_legacy(proposal)
        self.assertEqual(receipt['incomplete_count'], 1)
        with self.f.SessionLocal() as db:
            record = imported_records(db, case_id=self.f.case.id)['records'][0]
            self.assertEqual(record['fields']['date'], '')

    def test_import_retry_retains_incomplete_count(self):
        proposal, _ = self.proposal('amount_minor')
        first = self.save_legacy(proposal)
        second = self.save(proposal)
        self.assertFalse(second['created'])
        self.assertEqual(first['source_document_id'], second['source_document_id'])
        self.assertEqual(second['record_count'], 12)
        self.assertEqual(second['incomplete_count'], 1)

    def test_incomplete_correction_rejects_wrong_case_conflicting_version_and_fabricated_date_basis(self):
        from services.financial.pdf_candidates import PdfMappingError
        proposal, row = self.proposal('date')
        receipt = self.save_legacy(proposal)
        with self.f.SessionLocal() as db:
            record = imported_records(db, case_id=self.f.case.id)['records'][0]
        corrected = {**record['fields'], 'date':'2023-03-18', 'reason':'Checked original date.'}
        args = dict(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            source_id=UUID(receipt['source_document_id']), actor=self.f.actor)
        for case_id, version, fields, status in [
            (uuid4(), 0, corrected, 404),
            (self.f.case.id, 1, corrected, 409),
            (self.f.case.id, 0, {**corrected, 'date':'', 'date_unprinted':True}, 422),
            (self.f.case.id, 0, {**corrected, 'date_values':{'booking_date':'2023-03-18'}}, 422),
        ]:
            with self.assertRaises(PdfMappingError) as error:
                complete_record(**{**args, 'case_id':case_id}, request=CompleteImportedRecord(row=fields, currency='EUR', version=version))
            self.assertEqual(error.exception.status_code, status)
        with self.f.SessionLocal() as db:
            self.assertEqual(imported_records(db, case_id=self.f.case.id)['total'], 1)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 11)

    def test_unknown_currency_keeps_all_records_outside_calculation(self):
        proposal, _ = self.proposal()
        proposal['currency'] = ''
        with self.assertRaises(PdfMappingError):
            self.save(proposal)
        receipt = self.save_legacy(proposal)
        self.assertEqual((receipt['record_count'], receipt['transaction_count'], receipt['incomplete_count']), (12, 0, 12))
        with self.f.SessionLocal() as db:
            page = imported_records(db, case_id=self.f.case.id, offset=5, limit=3)
            self.assertEqual(page['total'], 12)
            self.assertEqual(len(page['records']), 3)
            self.assertTrue(all('currency' in record['missing_fields'] for record in page['records']))
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
            record = page['records'][0]
        corrected = complete_record(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            source_id=UUID(receipt['source_document_id']), actor=self.f.actor,
            request=CompleteImportedRecord(row={**record['fields'], 'reason':'Currency read from the original.'},
                currency='EUR', version=0))
        self.assertTrue(corrected['pending_reconciliation'])
        with self.f.SessionLocal() as db:
            retained = imported_records(db, case_id=self.f.case.id)
            self.assertEqual(retained['total'], 12)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 0)
            self.assertEqual(next(row for row in retained['records'] if row['id'] == record['id'])['currency'], 'EUR')

    def test_setting_statement_currency_after_import_materializes_usable_records_together(self):
        from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details
        proposal, _ = self.proposal()
        proposal['currency'] = ''
        for row in proposal['rows']:
            row['issues'] = []
        receipt = self.save_legacy(proposal)
        source_id = UUID(receipt['source_document_id'])
        with self.f.SessionLocal() as db:
            before = read_statement_details(db, case_id=self.f.case.id, source_id=source_id)
            request = StatementDetailsRequest(expected_revision=before['revision'], currency='EUR',
                **{key: before['details'][key] for key in ('holder', 'account_number', 'institution')})
            after = update_statement_details(db, case_id=self.f.case.id, source_id=source_id, request=request, actor=self.f.actor)
            self.assertEqual(imported_records(db, case_id=self.f.case.id)['total'], 0)
            rows = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(rows), 12)
            self.assertTrue(all(row.currency == 'EUR' and str(row.statement_period_id) == after['period_id'] for row in rows))
            self.assertEqual(update_statement_details(db, case_id=self.f.case.id, source_id=source_id, request=request, actor=self.f.actor), after)
            source = db.get(FinancialSourceDocument, source_id)
            self.assertEqual(source.metadata_['statement_import_request']['currency'], '')
            self.assertFalse(any(issue.get('kind') == 'missing_field' for issue in source.metadata_['statement_import_issues']))

    def test_bulk_reassesses_legacy_ready_summary_and_blocks_flagged_records(self):
        from services.financial import import_batches as service
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        f = self.f
        f.file.status = "processed"
        f.db.commit()
        with f.SessionLocal() as db:
            batch = service.create_batch(db, case_id=f.case.id, request_id=uuid4(), file_ids=[f.file.id], folder_ids=[], actor=f.actor)
        import asyncio
        asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, AsyncMock(side_effect=AssertionError("Reuse prepared geometry"))))
        proposal, row = self.proposal('amount_minor')
        with f.SessionLocal() as db, patch.object(service, 'read_statement_import', return_value=proposal):
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.status = 'attention'
            item.review_request = initial_request(proposal)
            item.summary = {key:value for key,value in item.summary.items() if key != 'can_import'}
            db.commit()
            status = service.batch_status(db, case_id=f.case.id, batch_id=batch)
            self.assertEqual(status['available_statements'], 0)
            with self.assertRaisesRegex(PdfMappingError, 'no new statement records'):
                service.queue_import(db, case_id=f.case.id, batch_id=batch, expected_revision=status['ready_revision'], actor=f.actor)
            self.assertEqual(status['counts'].get('imported', 0), 0, status)
            self.assertEqual(status['items'][0]['incomplete_count'], 1)
            self.assertGreater(status['issues_count'], 0)
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
