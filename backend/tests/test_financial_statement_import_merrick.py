import unittest
from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
from tests.test_financial_statement_import_proposal import source


def statement():
    return source([['Statement Date: 04/25121'],['Account Number: 1111 2222 3333 4444'],
        ['MERRICK BANK'],['Send Payments to:','EXAMPLE HOLDER'],
        ['Transactions, Payments and Credits'],['TransDfla','Item Description','Amount'],
        ['04/22','24137463GEJBPDNXO','EXAMPLE SHOP','14.00'],
        ['04/23','24137463JHEZKK04F','EXAMPLE CAFE','100.00'],
        ['Fees'],['TOTAL FEES FOR THIS PERIOD','0.00'],['Interest Charged'],
        ['04/25','Interest Charge on Purchases','0.00'],['TOTAL INTEREST FOR THIS PERIOD','0.00'],
        ['2021 Totals Year-to-Date']])


class MerrickStatementTests(unittest.TestCase):
    def test_header_damage_is_not_repaired_but_transaction_dates_use_printed_year_context(self):
        data=statement();group=merrick_statement(data)
        self.assertEqual(group['statement_date'],'')
        self.assertEqual(group['printed_statement_date'],'04/25121')
        self.assertEqual(group['holder'],'EXAMPLE HOLDER')
        proposal=propose_merrick_table(data,'USD',group)
        rows=[r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual(len(rows),2)
        self.assertEqual([r['fields']['date'] for r in rows],['2021-04-22','2021-04-23'])
        self.assertEqual([r['fields']['amount_minor'] for r in rows],['1400','10000'])
        self.assertEqual(rows[0]['fields']['bank_reference'],'24137463GEJBPDNXO')
        self.assertFalse(any(r['issues'] for r in rows))

    def test_out_of_context_date_and_unreadable_money_are_retained_as_exceptions(self):
        data=statement()
        data['rows'][6]['cells'][0]['expected_text']='12/22'
        data['rows'][7]['cells'][-1]['expected_text']='1O0.00'
        rows=[r for r in propose_merrick_table(data,'USD',merrick_statement(data))['rows'] if not r['excluded']]
        self.assertEqual(len(rows),2)
        self.assertNotIn('date',rows[0]['fields'])
        self.assertTrue(rows[0]['issues'])
        self.assertNotIn('amount_minor',rows[1]['fields'])
        self.assertTrue(rows[1]['issues'])

    def test_conflicting_statement_year_is_not_used_to_fill_transaction_dates(self):
        data=statement()
        data['rows'][0]['cells'][0]['expected_text']='Statement Date: 04/25/22'
        group=merrick_statement(data)
        self.assertIsNone(group['date_year'])
        rows=[r for r in propose_merrick_table(data,'USD',group)['rows'] if not r['excluded']]
        self.assertTrue(all('date' not in r['fields'] for r in rows))
