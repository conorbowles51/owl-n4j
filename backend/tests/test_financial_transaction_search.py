import unittest
from services.financial.transaction_search import transaction_search
from services.financial.ledger_table_view import capture_table_view
class TransactionSearchTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(key='usd',from_name='Acme Holdings',to_name='Example Bank',description='Loan repayment, ref AA123',category='Transfers',currency='USD',amount_minor='12345',direction='debit',ledger_status='admitted',ordering_date='2021-01-01',row_index=0)
    def test_boolean_matches_same_cases_as_browser(self):
        for query in ['Acme','"Acme Holdings" AND NOT refund','from:"Acme Holdings" AND (category:Transfers OR category:Travel)','(refund OR loan) AND NOT category:Travel','amount:123.45','currency:USD loan','loan OR refund AND unknown']:
            with self.subTest(query=query): self.assertTrue(transaction_search(query,'boolean')(self.row))
        for query in ['NOT loan','from:Bank','category:Travel OR refund','(loan OR refund) AND unknown']:
            with self.subTest(query=query): self.assertFalse(transaction_search(query,'boolean')(self.row))
    def test_invalid_queries_refuse_instead_of_exporting_unfiltered_rows(self):
        for query in ['loan AND','(loan','loan)','"loan','from:','unknown:value']:
            with self.subTest(query=query), self.assertRaises(ValueError): transaction_search(query,'boolean')
    def test_export_filters_and_sorts_numeric_amounts_across_currencies(self):
        rows=[dict(self.row,key='usd',amount_minor='20000'),dict(self.row,key='jpy',currency='JPY',amount_minor='900'),dict(self.row,key='kwd',currency='KWD',amount_minor='50000')]
        view=capture_table_view(dict(readings=[dict(row=row) for row in rows]),dict(search='from:Acme AND NOT refund',search_mode='boolean',sort='amount-asc'))
        self.assertEqual(view['row_ids'],['kwd','usd','jpy'])
