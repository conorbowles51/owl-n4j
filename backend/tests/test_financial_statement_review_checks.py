import unittest
from services.financial.statement_review_checks import check_statement_rows, add_period_checks
from tests.test_financial_statement_import_catalog import page
from tests.test_financial_statement_import_proposal import source
from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_layout_context import statement_layout_context


def control(role, amount):
    return dict(kind='balance', excluded=True, issues=[], fields=dict(description=role+' Balance', balance=amount))


def payment(amount='500', direction='debit'):
    return dict(kind='transaction', excluded=False, issues=[], fields=dict(date='2020-05-15', description='Shop', amount_minor=amount, direction=direction))


class StatementReviewChecksTests(unittest.TestCase):
    def test_bank_and_card_conventions_and_missing_values(self):
        self.assertEqual(check_statement_rows([control('Opening','1000'),payment(),control('Closing','500')])['balance_status'], 'matches')
        rows = [control('Opening','1000'),payment(),control('Closing','1500')]
        self.assertEqual(check_statement_rows(rows, liability=True)['balance_status'], 'matches')
        self.assertEqual(check_statement_rows(rows)['difference_minor'], '-1000')
        self.assertEqual(check_statement_rows([payment()])['balance_status'], 'unavailable')
        rows[1]['fields']['amount_minor'] = 'unreadable'
        result = check_statement_rows(rows, liability=True)
        self.assertEqual((result['transaction_count'], result['flagged_rows'], result['balance_status']), (1, 1, 'unavailable'))

    def test_matching_balances_do_not_clear_flagged_dates_or_duplicate_controls(self):
        rows = [control('Opening','1000'),payment(),control('Closing','500')]
        rows[1]['issues'] = ['Check the printed date.']
        result = check_statement_rows(rows)
        self.assertEqual(result['balance_status'], 'matches')
        self.assertEqual(result['flagged_rows'], 1)
        rows.append(control('Closing','500'))
        self.assertEqual(check_statement_rows(rows)['balance_status'], 'unavailable')

    def test_all_periods_checked_with_their_own_summary_and_transactions(self):
        sources = []
        for number, amount in ((1,'5.00'),(3,'7.00')):
            current = page(number, card='3539' if number == 1 else '9999')
            more = source([['Account Summary'],['Previous Balance','$0.00'],['New Balance','$5.00'],
                           ['EXAMPLE #'+('3539' if number == 1 else '9999')+': Transactions'],
                           ['Date','Description','Amount'],['May 15','Shop','$'+amount]])['rows']
            current['rows'] += [{**r, 'row_index': r['row_index']+3} for r in more]
            for row in current['rows']:
                for cell in row['cells']:
                    x = 10000 + cell['column_index'] * 200000
                    y = 10000 + row['row_index'] * 20000
                    cell['locator'] = dict(kind='page_rectangle', page=number, rect=[x,y,x+180000,y+10000], page_size=[612000,792000], units='millipoints', space='pdf_displayed')
            current['layout_context'] = statement_layout_context(current['rows'])
            sources.append(current)
        choices = statement_catalog(sources)['statements']
        result = add_period_checks(choices, sources, 'USD')
        self.assertEqual([c['checks']['balance_status'] for c in result], ['matches','difference'])
        self.assertEqual([c['checks']['transaction_count'] for c in result], [1,1])
        self.assertNotIn('checks', choices[0])
        self.assertEqual(add_period_checks(choices, sources, ''), choices)
