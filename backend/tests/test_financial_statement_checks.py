"""Current diagnostics remain exact, case scoped, read-only and distinct from admission."""
from sqlalchemy import select
from services.financial.statement_checks import list_statement_checks, capture_statement_checks, StatementCheckError
from services.financial.periods import BalanceObservation
from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
from tests import test_financial_duplicates as fixture


class StatementCheckTests(fixture.DuplicateTestCase):
    def read(self, **changes):
        return list_statement_checks(self.db, **{'case_id': self.case.id, **changes})

    def test_current_arithmetic_does_not_overwrite_recorded_result(self):
        doc = self.make_copy()
        period = self.db.scalar(select(FinancialStatementPeriod))
        prior = (period.reconciliation_status, period.reconciled_at, doc.proof_class, doc.status)
        result = self.read()
        item = result['items'][0]
        self.assertEqual(item['status'], 'unbalanced')
        self.assertEqual(item['amounts'], dict(opening='10000', credits='42000', debits='0', computed_closing='52000', closing='38000', difference='14000'))
        self.assertEqual(item['counted_rows'], 2)
        self.assertTrue(item['independent'])
        self.assertFalse(result['applied'])
        self.assertEqual(prior, (period.reconciliation_status, period.reconciled_at, doc.proof_class, doc.status))
        self.assertFalse(self.db.dirty or self.db.new)

    def test_missing_balance_is_not_zero(self):
        self.make_copy(opening=BalanceObservation.absent())
        item = self.read()['items'][0]
        self.assertEqual(item['status'], 'unavailable')
        self.assertIsNone(item['amounts']['opening'])
        self.assertIsNone(item['amounts']['difference'])
        self.assertEqual(item['amounts']['credits'], '42000')

    def test_exact_integer_above_javascript_range_and_excluded_rows(self):
        self.make_copy(rows=((9007199254740993, 'aa'),))
        item = self.read()['items'][0]
        self.assertEqual(item['amounts']['credits'], '9007199254740993')
        row = self.db.scalar(select(FinancialTransaction))
        row.ledger_status = 'superseded'; self.db.commit()
        item = self.read()['items'][0]
        self.assertEqual(item['amounts']['credits'], '0')
        self.assertEqual(item['counted_rows'], 0)
        self.assertEqual(item['excluded_rows'], 1)

    def test_balance_does_not_promote_excluded_source(self):
        doc = self.make_copy(closing=fixture.printed(52000))
        doc.status = 'superseded'; self.db.commit()
        item = self.read()['items'][0]
        self.assertEqual(item['status'], 'balanced')
        self.assertEqual(item['source_status'], 'superseded')
        self.assertEqual(doc.status, 'superseded')
        self.assertFalse(self.db.dirty)

    def test_other_case_and_pagination(self):
        self.make_copy(); self.make_copy()
        page = self.read(limit=1)
        self.assertTrue(page['has_more'])
        second = self.read(offset=1, limit=1)
        self.assertFalse(second['has_more'])
        self.assertNotEqual(page['items'][0]['period_id'], second['items'][0]['period_id'])
        self.assertEqual(self.read(case_id=self.other_case.id)['items'], [])
        for kwargs in ({'offset': -1}, {'limit': 26}, {'limit': True}):
            with self.assertRaises(StatementCheckError): self.read(**kwargs)

    def test_cross_case_document_is_refused(self):
        doc = self.make_copy(); doc.case_id = self.other_case.id; self.db.commit()
        with self.assertRaises(StatementCheckError): self.read()

    def test_cross_account_row_is_refused(self):
        self.make_copy()
        row = self.db.scalar(select(FinancialTransaction))
        row.account_id = self.other_account.id; self.db.commit()
        with self.assertRaises(StatementCheckError): self.read()

    def test_mixed_admitted_currency_refuses_period_without_hiding_other_periods(self):
        self.make_copy(); self.make_copy()
        row = self.db.scalar(select(FinancialTransaction)); row.currency = 'USD'; self.db.commit()
        items = self.read()['items']
        self.assertEqual({item['status'] for item in items}, {'refused', 'unbalanced'})
        self.assertIsNone(next(item for item in items if item['status'] == 'refused')['amounts'])

    def test_capture_refuses_non_postgres_connection(self):
        with self.assertRaises(StatementCheckError): capture_statement_checks(self.db.get_bind(), case_id=self.case.id)
