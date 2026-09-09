from uuid import UUID, uuid4
from unittest.mock import patch
from sqlalchemy import select
from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
from services.financial.statement_balances import read_statement_running_balances
from services.financial.statement_checks import StatementCheckError
from services.financial.correction_balances import current_running_balances
from tests import test_financial_duplicates as fixture

class StatementBalanceTests(fixture.DuplicateTestCase):
    def setUp(self):
        # SQLite gives the PostgreSQL UUID type numeric affinity; a random
        # all-numeric/exponent-shaped hex ID must not become a float in fixtures.
        ids = patch('uuid.uuid4', side_effect=lambda: UUID('a' + uuid4().hex[1:]))
        ids.start(); self.addCleanup(ids.stop)
        super().setUp()
        self.document=self.make_copy()
        self.period=self.db.scalar(select(FinancialStatementPeriod))
        self.rows=list(self.db.scalars(select(FinancialTransaction).order_by(FinancialTransaction.row_index)))
        for row,balance in zip(self.rows,[50000,52000]):row.running_balance_minor=balance
        self.db.commit()
    def read(self,**changes):
        return read_statement_running_balances(self.db,**{'case_id':self.case.id,'period_id':self.period.id,**changes})
    def test_both_orders_are_returned_without_a_fake_correction_or_writes(self):
        result=self.read()
        self.assertFalse(result['applied'])
        interpretations=result['comparison']['interpretations']
        self.assertEqual(interpretations[0]['current']['mismatch_count'],0)
        self.assertGreater(interpretations[1]['current']['mismatch_count'],0)
        self.assertTrue(all('proposed' not in item for item in interpretations))
        self.assertFalse(self.db.dirty or self.db.new)
    def test_changed_reading_is_rechecked_and_exclusion_breaks_chain(self):
        self.rows[0].amount_minor=41000;self.db.commit()
        finding=self.read()['comparison']['interpretations'][0]['current']['findings'][0]
        self.assertEqual(finding['delta_minor'],'-1000')
        self.assertEqual(finding['after_transaction_id'],str(self.rows[0].id))
        self.rows[0].ledger_status='quarantined';self.rows[0].quarantine_reason='unreadable_row';self.db.commit()
        current=self.read()['comparison']['interpretations'][0]['current']
        self.assertEqual(current['excluded_rows'],1)
        self.assertEqual(current['unanchored_balances'],1)
    def test_missing_balances_are_unavailable(self):
        for row in self.rows:row.running_balance_minor=None
        self.db.commit()
        self.assertFalse(self.read()['comparison']['available'])
    def test_cross_case_and_cross_account_rows_refused(self):
        with self.assertRaises(StatementCheckError):self.read(case_id=self.other_case.id)
        self.rows[0].account_id=self.other_account.id;self.db.commit()
        with self.assertRaises(StatementCheckError):self.read()
    def test_bounded_comparison_and_same_position_ambiguity(self):
        self.assertFalse(current_running_balances(self.period,self.rows*501)['available'])
        self.rows[1].row_index=self.rows[0].row_index;self.db.commit()
        self.assertFalse(self.read()['comparison']['available'])
