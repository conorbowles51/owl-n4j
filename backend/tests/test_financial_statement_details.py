from copy import deepcopy
from uuid import UUID, uuid4
from unittest import TestCase
from unittest.mock import patch
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details
from services.financial.statement_import_controls import read_import_controls
from tests.test_financial_statement_import import StatementImportTests as Fixture

class StatementDetailsTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.receipt = self.f.confirm()
        self.source_id = UUID(self.receipt['source_document_id'])

    def tearDown(self):
        self.f.tearDown()

    def read(self):
        with self.f.SessionLocal() as db:
            return read_statement_details(db, case_id=self.f.case.id, source_id=self.source_id)

    def request(self, **changes):
        view = self.read()
        return dict(expected_revision=view['revision'], **{key: view['details'][key] for key in ('holder', 'account_number', 'institution')}, **changes)

    def save(self, request, case_id=None):
        with self.f.SessionLocal() as db:
            return update_statement_details(db, case_id=case_id or self.f.case.id, source_id=self.source_id,
                request=StatementDetailsRequest.model_validate(request), actor=self.f.actor)

    def test_account_correction_keeps_payments_original_and_history(self):
        before = self.read()
        with self.f.SessionLocal() as db:
            original = deepcopy(db.get(FinancialSourceDocument, self.source_id).metadata_['statement_import_request'])
            rows = {row.id: row.ref_id for row in db.scalars(select(FinancialTransaction))}
        request = self.request(); request['account_number'] = '000123456789'
        saved = self.save(request)
        self.assertEqual(self.read(), saved)
        self.assertNotEqual(saved['account_id'], before['account_id'])
        self.assertEqual(self.save(request), saved)
        self.assertEqual(self.f.preview()['current_import']['details']['account_number'], '000123456789')
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            self.assertEqual(source.metadata_['statement_import_request'], original)
            self.assertEqual(len(source.metadata_['statement_details_history']), 1)
            self.assertEqual(source.metadata_['statement_details_history'][0]['actor_id'], str(self.f.actor.user_id))
            transactions = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual({r.id: r.ref_id for r in transactions}, rows)
            self.assertTrue(all(str(r.account_id) == saved['account_id'] for r in transactions))
            self.assertEqual(db.get(FinancialAccount, UUID(saved['account_id'])).identifier_as_printed, '000123456789')
            self.assertEqual(db.get(FinancialAccount, UUID(before['account_id'])).identifier_as_printed, 'TEST123')

    def test_add_missing_balances_reconciles_with_page_citations(self):
        saved = self.save(self.request(opening=dict(amount_minor='1245000', page=1), closing=dict(amount_minor='4745000', page=1)))
        with self.f.SessionLocal() as db:
            period = db.get(FinancialStatementPeriod, UUID(saved['period_id']))
            self.assertEqual(period.reconciliation_status, 'balanced')
            controls = read_import_controls(period, db.get(FinancialSourceDocument, self.source_id), self.f.file)
            self.assertEqual([c['reviewed_value'] for c in controls['controls']], ['1245000', '4745000'])
            self.assertTrue(all(c['locator'] == dict(kind='page_only', page=1) for c in controls['controls']))
        self.assertEqual(self.read()['balances'], saved['balances'])

    def test_zero_is_distinct_from_missing(self):
        zero = self.save(self.request(opening=dict(amount_minor='0', page=1)))
        self.assertEqual(zero['balances']['opening']['amount_minor'], '0')
        removed = self.save(self.request(opening=dict(amount_minor=None)))
        self.assertIsNone(removed['balances']['opening']['amount_minor'])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialStatementPeriod, UUID(removed['period_id'])).opening_balance_source, 'absent')

    def test_stale_and_cross_case_edits_fail(self):
        first = self.request()
        self.save({**first, 'account_number': '000123456789'})
        with self.assertRaisesRegex(PdfMappingError, 'changed since'):
            self.save({**first, 'account_number': 'DIFFERENT'})
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            self.save(self.request(), case_id=uuid4())
        self.assertEqual(self.read()['details']['account_number'], '000123456789')

    def test_validation_and_late_failure_are_atomic(self):
        before = self.read()
        for value, page in [('100', 999), ('9223372036854775808', 1)]:
            request = self.request(opening=dict(amount_minor=value, page=page)); request['account_number'] = '000123456789'
            with self.assertRaises(PdfMappingError): self.save(request)
            self.assertEqual(self.read(), before)
        request = self.request(opening=dict(amount_minor='100', page=1)); request['account_number'] = '000123456789'
        with patch('services.financial.reconcile.reconcile_period', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError): self.save(request)
        self.assertEqual(self.read(), before)

    def test_card_balance_convention(self):
        with self.f.SessionLocal() as db:
            db.get(FinancialAccount, UUID(self.receipt['account_id'])).account_type = 'credit_card'; db.commit()
        saved = self.save(self.request(opening=dict(amount_minor='6000', page=1), closing=dict(amount_minor='2520', page=1)))
        self.assertEqual(saved['balances']['opening']['amount_minor'], '6000')
        with self.f.SessionLocal() as db:
            period = db.get(FinancialStatementPeriod, UUID(saved['period_id']))
            self.assertEqual(period.opening_balance_minor, -6000)
            self.assertEqual(read_import_controls(period, db.get(FinancialSourceDocument, self.source_id), self.f.file)['balance_convention'], 'liability_owed')

    def test_excluded_import_cannot_be_edited(self):
        request = self.request()
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            source.status = 'quarantined'
            source.quarantine_reason = 'adjudicated'
            db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'current imported'): self.save(request)

    def test_currency_change_preserves_values_categories_exclusions_and_originals(self):
        from postgres.models.financial import AdjudicationEvent
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            original = deepcopy(source.metadata_['statement_import_request'])
            rows = list(db.scalars(select(FinancialTransaction).order_by(FinancialTransaction.id)))
            rows[0].metadata_ = {'investigation_labels': {'category': 'Fees', 'from_name': 'Sender', 'version': 1}}
            rows[0].ledger_status = 'quarantined'; rows[0].quarantine_reason = 'adjudicated'
            prior = {row.id: (row.ref_id, row.amount_minor, row.currency) for row in rows}
            db.commit()
        request = self.request(currency='MXN')
        saved = self.save(request)
        self.assertEqual(saved['currency'], 'MXN')
        self.assertEqual(self.save(request), saved)
        self.assertEqual(self.f.preview()['current_import']['currency'], 'MXN')
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, self.source_id)
            self.assertEqual(source.metadata_['statement_import_request'], original)
            current = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.superseded_by_id.is_(None))))
            self.assertEqual(len(current), len(prior))
            self.assertTrue(all(row.currency == 'MXN' for row in current))
            for old_id, (reference, amount, currency) in prior.items():
                old = db.get(FinancialTransaction, old_id)
                self.assertEqual((old.ref_id, old.amount_minor, old.currency), (reference, amount, currency))
                self.assertEqual(old.ledger_status, 'superseded')
                new = db.get(FinancialTransaction, old.superseded_by_id)
                self.assertEqual(new.amount_minor, amount)
                self.assertEqual(new.metadata_, old.metadata_)
            self.assertEqual(sum(row.ledger_status == 'quarantined' for row in current), 1)
            period = db.get(FinancialStatementPeriod, UUID(saved['period_id']))
            self.assertEqual(read_import_controls(period, source, self.f.file)['currency'], 'MXN')
            self.assertEqual(len(list(db.scalars(select(AdjudicationEvent).where(
                AdjudicationEvent.decision == 'correct_transaction')))), len(prior))
        restored = self.save(self.request(currency='EUR'))
        self.assertEqual(restored['currency'], 'EUR')
        self.assertEqual(self.read(), restored)

    def test_currency_late_failure_rolls_back_rows_and_period(self):
        before = self.read()
        with self.f.SessionLocal() as db:
            ids = list(db.scalars(select(FinancialTransaction.id).order_by(FinancialTransaction.id)))
        with patch('services.financial.reconcile.reconcile_period', side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError): self.save(self.request(currency='MXN'))
        self.assertEqual(self.read(), before)
        with self.f.SessionLocal() as db:
            self.assertEqual(list(db.scalars(select(FinancialTransaction.id).order_by(FinancialTransaction.id))), ids)

    def test_currency_can_be_chosen_for_an_import_with_no_period(self):
        # Unknown-currency imports retain records but could previously never add
        # balances because the editor hid its fields until a period existed.
        with self.f.SessionLocal() as db:
            for row in db.scalars(select(FinancialTransaction)):
                db.delete(row)
            period = db.scalar(select(FinancialStatementPeriod))
            db.delete(period)
            source = db.get(FinancialSourceDocument, self.source_id)
            metadata = deepcopy(source.metadata_)
            metadata.pop('statement_import_controls', None); metadata.pop('statement_import_controls_sha256', None)
            source.metadata_ = metadata
            db.commit()
        saved = self.save(self.request(currency='MXN', opening=dict(amount_minor='0', page=1), closing=dict(amount_minor='0', page=1)))
        self.assertIsNotNone(saved['period_id'])
        self.assertEqual(saved['currency'], 'MXN')
        self.assertEqual(saved['balances']['opening']['amount_minor'], '0')


class ManualBalanceImportTests(TestCase):
    def test_enter_missing_balances_before_import_without_creating_payments(self):
        f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        f.setUp()
        try:
            request = f.request()
            for row in request['rows']:
                row['excluded'] = True
                row['balance_minor'] = None
            for role in ('opening', 'closing'):
                request['rows'].append(dict(id=f'manual:{role}-balance', excluded=True, manual_page=1,
                    date='', description=f'{role} balance', counterparty='', amount_minor='0', direction=None,
                    balance_minor='0', reason=''))
            imported = f.confirm(request)
            self.assertEqual(imported['transaction_count'], 0)
            self.assertEqual(imported['incomplete_count'], 0)
            with f.SessionLocal() as db:
                period = db.scalar(select(FinancialStatementPeriod))
                self.assertEqual(period.opening_balance_minor, 0)
                self.assertEqual(period.closing_balance_minor, 0)
                self.assertEqual(period.reconciliation_status, 'balanced')
                controls = read_import_controls(period, db.get(FinancialSourceDocument, UUID(imported['source_document_id'])), f.file)
                self.assertEqual(len(controls['controls']), 2)
                self.assertTrue(all(c['locator'] == {'kind': 'page_only', 'page': 1} for c in controls['controls']))
            self.assertFalse(f.confirm(request)['created'])
        finally:
            f.tearDown()
