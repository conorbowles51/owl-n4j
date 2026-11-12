from unittest import TestCase
from uuid import UUID, uuid4

from sqlalchemy import select

from postgres.models.financial import FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_compare_facts import statement_compare_facts
from services.financial.statement_details import read_statement_details
from tests import test_financial_statement_import as _test_financial_statement_import


class StatementCompareFactsTests(TestCase):
    def setUp(self):
        self.f = _test_financial_statement_import.StatementImportTests(
            'test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.source = UUID(self.f.confirm()['source_document_id'])

    def tearDown(self):
        self.f.tearDown()

    def facts(self, case_id=None):
        with self.f.SessionLocal() as db:
            return statement_compare_facts(db, case_id=case_id or self.f.case.id, source_id=self.source)

    def rows(self, db):
        return list(db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.source).order_by(FinancialTransaction.row_index)))

    def test_facts_are_the_saved_details_balances_and_ledger_sums(self):
        facts = self.facts()
        with self.f.SessionLocal() as db:
            details = read_statement_details(db, case_id=self.f.case.id, source_id=self.source)
            rows = self.rows(db)
        self.assertTrue(rows)
        self.assertEqual(facts['payment_count'], len(rows))
        self.assertEqual(facts['money_in_minor'], str(sum(r.amount_minor for r in rows if r.direction == 'credit')))
        self.assertEqual(facts['money_out_minor'], str(sum(r.amount_minor for r in rows if r.direction == 'debit')))
        self.assertEqual(facts['opening_balance_minor'], details['balances']['opening']['amount_minor'])
        self.assertEqual(facts['closing_balance_minor'], details['balances']['closing']['amount_minor'])
        for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end'):
            self.assertEqual(facts[key], details['details'][key])
        self.assertEqual(facts['pages'], details['pages'])
        self.assertEqual(facts['held_from_ledger'], 0)
        self.assertTrue(facts['filename'])

    def test_a_replaced_reading_does_not_count_and_a_quarantined_row_is_named_not_summed(self):
        before = self.facts()
        with self.f.SessionLocal() as db:
            rows = self.rows(db)
            self.assertGreaterEqual(len(rows), 2)
            first, second = rows[0], rows[1]
            first.ledger_status = 'quarantined'
            first.quarantine_reason = 'unreadable_row'
            second.ledger_status = 'superseded'
            second.superseded_by_id = rows[-1].id if rows[-1].id != second.id else first.id
            gone = {first.id: first, second.id: second}
            db.commit()
            removed = {d: sum(r.amount_minor for r in gone.values() if r.direction == d) for d in ('credit', 'debit')}
        after = self.facts()
        self.assertEqual(after['payment_count'], before['payment_count'] - 2)
        self.assertEqual(int(after['money_in_minor']), int(before['money_in_minor']) - removed['credit'])
        self.assertEqual(int(after['money_out_minor']), int(before['money_out_minor']) - removed['debit'])
        self.assertEqual(after['held_from_ledger'], 1)

    def test_another_case_cannot_read_the_statement(self):
        with self.assertRaises(PdfMappingError):
            self.facts(uuid4())
