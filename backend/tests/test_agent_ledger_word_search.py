"""lx-agentquick F: ledger text search reads the words of a query, and the boolean mode is reachable by the agent."""
import unittest

from services.agent.tools import FinancialArgs
from services.financial.ledger_table_view import LedgerTableView
from services.financial.transaction_search import transaction_search

ROW = dict(key='usd', from_name='Acme Holdings', to_name='Example Bank', description='Loan repayment, ref AA123',
           category='Transfers', currency='USD', amount_minor='12345', direction='debit', ledger_status='admitted',
           ordering_date='2021-01-01', row_index=0)


class LedgerWordSearch(unittest.TestCase):
    def test_terms_mode_needs_every_word_in_any_order(self):
        self.assertTrue(transaction_search('repayment loan', 'terms')(ROW))
        self.assertTrue(transaction_search('acme "loan repayment" AA123', 'terms')(ROW))
        self.assertTrue(transaction_search('from:acme bank', 'terms')(ROW))
        self.assertFalse(transaction_search('loan refund', 'terms')(ROW))
        self.assertFalse(transaction_search('"repayment loan"', 'terms')(ROW))  # a quoted phrase stays whole
        self.assertTrue(transaction_search('', 'terms')(ROW))

    def test_text_mode_is_unchanged_for_the_table(self):
        self.assertFalse(transaction_search('repayment loan', 'text')(ROW))
        self.assertTrue(transaction_search('loan repayment', 'text')(ROW))

    def test_the_agent_can_reach_terms_and_boolean_and_terms_is_the_default(self):
        self.assertEqual(FinancialArgs().search_mode, 'terms')
        for mode in ('terms', 'text', 'boolean'):
            self.assertEqual(LedgerTableView.model_validate({'search': 'a', 'search_mode': mode}).search_mode, mode)
        self.assertIn('AND', FinancialArgs.model_fields['search_mode'].description)


if __name__ == '__main__':
    unittest.main()
