from copy import deepcopy
from unittest import TestCase
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.manual_statement_payment import ManualStatementPayment, append_payment
from services.financial.statement_details import read_statement_details
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_statement_import import StatementImportTests as Fixture


class ManualPaymentTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.source = UUID(self.f.confirm()['source_document_id'])

    def tearDown(self):
        self.f.tearDown()

    def request(self):
        with self.f.SessionLocal() as db:
            details = read_statement_details(db, case_id=self.f.case.id, source_id=self.source)
        identifier = uuid4()
        return dict(request_id=str(identifier), expected_revision=details['revision'], row=dict(
            id='manual:' + str(identifier), manual_page=1, date='2023-01-02', description='Manually read payment',
            direction='debit', amount_minor='12345', counterparty='Synthetic supplier'))

    def save(self, request, case_id=None):
        return append_payment(session_factory=self.f.SessionLocal, case_id=case_id or self.f.case.id,
            source_id=self.source, request=ManualStatementPayment.model_validate(request), actor=self.f.actor)

    def test_append_and_lost_response_retry_preserve_existing_payments_and_original(self):
        request = self.request()
        with self.f.SessionLocal() as db:
            original = deepcopy(db.get(FinancialSourceDocument, self.source).metadata_['statement_import_request'])
            before = {r.id: r.ref_id for r in db.scalars(select(FinancialTransaction))}
        first = self.save(request)
        again = self.save(request)
        self.assertEqual(first['transaction_id'], again['transaction_id'])
        self.assertFalse(again['created'])
        with self.f.SessionLocal() as db:
            after = {r.id: r.ref_id for r in db.scalars(select(FinancialTransaction))}
            self.assertEqual(len(after), len(before) + 1)
            self.assertEqual({k: after[k] for k in before}, before)
            self.assertEqual(db.get(FinancialSourceDocument, self.source).metadata_['statement_import_request'], original)
            row = db.get(FinancialTransaction, UUID(first['transaction_id']))
            self.assertEqual(row.amount_minor, 12345)
            self.assertEqual(row.direction, 'debit')
        request['row']['amount_minor'] = '999'
        with self.assertRaisesRegex(PdfMappingError, 'already saved'):
            self.save(request)

    def test_rejects_wrong_case_page_and_stale_details_without_appending(self):
        request = self.request()
        with self.assertRaises(PdfMappingError):
            self.save(request, uuid4())
        request['row']['manual_page'] = 499
        with self.assertRaisesRegex(PdfMappingError, 'PDF page'):
            self.save(request)
        request = self.request(); request['expected_revision'] = 'b' * 64
        with self.assertRaisesRegex(PdfMappingError, 'details changed'):
            self.save(request)

class BalanceOnlyManualPaymentTests(ManualPaymentTests):
    def setUp(self):
        self.f = Fixture('test_balance_only_keeps_differences_and_excluded_payments_in_the_record')
        self.f.setUp()
        _, request = self.f.andrews_request('0000', install=True)
        for row in request['rows']:
            row['excluded'] = True
        self.source = UUID(self.f.confirm(request)['source_document_id'])

    def test_first_manual_payment_opens_a_balance_only_statement_without_reimport(self):
        with self.f.SessionLocal() as db:
            self.assertEqual(list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == self.source))), [])
        result = self.save(self.request())
        with self.f.SessionLocal() as db:
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == self.source)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(str(rows[0].id), result['transaction_id'])
