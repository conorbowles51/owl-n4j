import unittest
from services.financial.statement_import_card import propose_card_table
from services.financial.statement_layout_context import statement_layout_context
from tests.test_financial_statement_import_proposal import source


def card_source():
    result=source([
        ['Platinum MasterCard Account Ending in 1234'],
        ['May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle'],
        ['Visit www.capitalone.com to see detailed transactions.'],
        ['SAMPLE HOLDER #1234: Payments, Credits and Adjustments'],
        ['Date','Description','Amount'], ['May 30','PAYMENT','- $180.00'],
        ['SAMPLE HOLDER #1234: Transactions'],['Date','Description','Amount'],
        ['May 29','EXAMPLE SHOP','$61.62'],['Total Transactions for This Period','$61.62'],
        ['Interest Charged'],['Interest Charge on Purchases','$56.16'],
        ['Interest Charge on Cash Advances','$0.00'],['Total Interest for This Period','$56.16']])
    result['layout_context']=statement_layout_context(result['rows'])
    return result


class CardStatementImportTests(unittest.TestCase):
    def test_payment_purchase_and_undated_interest_remain_distinct(self):
        result=propose_card_table(card_source(),'USD',dict(period_start='2020-05-12',period_end='2020-06-11',account_reference='****1234'))
        included=[r for r in result['rows'] if not r['excluded']]
        self.assertEqual(len(included),3)
        self.assertEqual(included[0]['fields']['date'],'2020-05-30')
        self.assertEqual(included[0]['fields']['direction'],'credit')
        self.assertEqual(included[0]['fields']['amount_minor'],'18000')
        self.assertEqual(included[1]['fields']['direction'],'debit')
        self.assertEqual(included[1]['fields']['amount_minor'],'6162')
        self.assertNotIn('date',included[2]['fields'])
        self.assertTrue(included[2]['issues'])
        self.assertEqual(included[2]['fields']['amount_minor'],'5616')

    def test_an_unrecognised_dated_row_stays_visible_for_review(self):
        data=card_source()
        extra=source([['May 31','Possible missed payment','$12.00']])['rows'][0]
        extra['row_index']=99
        data['rows'].append(extra)
        result=propose_card_table(data,'USD',dict(period_start='2020-05-12',period_end='2020-06-11',account_reference='****1234'))
        self.assertFalse(result['rows'][-1]['excluded'])
        self.assertTrue(result['rows'][-1]['issues'])
