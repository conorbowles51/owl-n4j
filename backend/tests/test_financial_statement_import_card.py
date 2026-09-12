import unittest
from services.financial.statement_import_card import propose_card_table
from services.financial.statement_layout_context import statement_layout_context
from tests.test_financial_statement_import_proposal import source
from tests.test_financial_pdf_geometry_candidates import rectangle
from services.financial.statement_import_card_balances import summary_balances
from copy import deepcopy


def summary_source():
    grid = source([
        ['Platinum MasterCard Account Ending in 1234'],
        ['May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle'],
        ['www.capitalone.com'],
        ['Payment Information', 'Account Summary'],
        ['Previous Balance', '$1,000.00'],
        ['New Balance', 'Minimum Payment Due', 'Payments', '- $180.00'],
        ['$937.78', '$25.00', 'Other Credits', '$0.00'],
        ['Transactions', '+ $61.62'],
        ['Interest Charged', '+ $56.16'],
        ['New Balance', '= $937.78'],
        ['Credit Limit', '$10,000.00'],
        ['New Balance', '$999.00'],
    ])
    positions = {
        3: [(25, 70, 160), (400, 70, 100)],
        4: [(320, 95, 90), (530, 95, 55)],
        5: [(25, 120, 65), (150, 120, 100), (320, 120, 80), (530, 120, 55)],
        6: [(25, 140, 60), (150, 140, 60), (320, 140, 80), (530, 140, 55)],
        7: [(320, 160, 90), (530, 160, 55)],
        8: [(320, 180, 90), (530, 180, 55)],
        9: [(320, 200, 90), (530, 200, 55)],
        10: [(320, 230, 90), (530, 230, 55)],
        11: [(25, 500, 90), (160, 500, 55)],
    }
    for row in grid['rows']:
        for column, cell in enumerate(row['cells']):
            x, y, width = positions.get(row['row_index'], [(25, row['row_index'] * 18, 550)])[column]
            cell['locator'] = rectangle(y, x=x, width=width, height=10)
    return grid


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
    def test_summary_controls_ignore_coupon_and_minimum_due_with_exact_citations(self):
        data = summary_source()
        controls, issues = summary_balances(data, 'USD')
        self.assertEqual(issues, [])
        self.assertEqual(set(controls), {4, 9})
        self.assertEqual(controls[4]['fields']['balance'], '100000')
        self.assertEqual(controls[9]['fields']['balance'], '93778')
        self.assertTrue(all(c['excluded'] for c in controls.values()))
        self.assertEqual(controls[9]['fields']['balance_column'], '1')

    def test_no_geometry_or_ambiguous_summary_does_not_guess_balances(self):
        for change in ('heading', 'value', 'duplicate'):
            data = summary_source()
            if change == 'heading':
                data['rows'][3]['cells'][1]['locator'] = {'kind': 'page_only', 'page': 1}
            elif change == 'value':
                data['rows'][4]['cells'][1]['locator'] = rectangle(120, x=530)
            else:
                duplicate = deepcopy(data['rows'][4]); duplicate['row_index'] = 99
                data['rows'].append(duplicate)
            controls, issues = summary_balances(data, 'USD')
            self.assertEqual(controls, {})
            self.assertTrue(issues)

    def test_duplicate_closing_values_leave_only_the_known_opening(self):
        data = summary_source()
        duplicate = deepcopy(data['rows'][9]); duplicate['row_index'] = 99
        data['rows'].append(duplicate)
        controls, issues = summary_balances(data, 'USD')
        self.assertEqual(set(controls), {4})
        self.assertTrue(issues)

    def test_bad_amount_remains_a_balance_exception_and_credit_balance_keeps_its_sign(self):
        for text in ('$93?.78', '- $12.50', '= - $12.50', '- $92,233,720,368,547,758.08'):
            data = summary_source()
            data['rows'][9]['cells'][1]['expected_text'] = text
            controls, _ = summary_balances(data, 'USD')
            if '?' in text or '92,233' in text:
                self.assertNotIn('balance', controls[9]['fields'])
                self.assertTrue(controls[9]['issues'])
            else:
                self.assertEqual(controls[9]['fields']['balance'], '-1250')

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

    def test_recognised_card_with_unrecognised_section_layout_keeps_payment_exceptions_visible(self):
        data = card_source()
        data['layout_context'] = None
        result = propose_card_table(data, 'USD', dict(period_start='2020-05-12', period_end='2020-06-11', account_reference='****1234'))
        included = [r for r in result['rows'] if not r['excluded']]
        self.assertEqual(len(included), 3)
        self.assertTrue(all(r['issues'] for r in included))
        self.assertEqual([r['kind'] for r in included], ['unresolved', 'unresolved', 'transaction'])
