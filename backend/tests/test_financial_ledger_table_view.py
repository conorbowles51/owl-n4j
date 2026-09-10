from unittest import TestCase
from services.financial.ledger_table_view import capture_table_view
from services.financial.ledger_summary import LedgerSummaryError

class LedgerTableViewTests(TestCase):
    def row(self,key,**values):
        return {'row':dict(key=key,ledger_status='admitted',proof_class='p3',currency='GBP',direction='credit',amount_minor='9007199254740993',ordering_date='2026-01-01',row_index=0,description='Invoice payment',**values)}
    def test_exact_sort_and_filters_retain_every_matching_id(self):
        a=self.row('a');b=self.row('b');b['row']['amount_minor']='9007199254740992'
        view=capture_table_view({'readings':[a,b]},dict(search='INVOICE',currency='GBP',sort='amount-asc'))
        self.assertEqual(view['row_ids'],['b','a']);self.assertEqual(view['matching_rows'],2)
        self.assertEqual(view['filters']['search'],'INVOICE')
        self.assertEqual(capture_table_view({'readings':[a,b]},dict(direction='debit'))['row_ids'],[])
    def test_full_capture_is_not_mutated_and_status_is_respected(self):
        from copy import deepcopy
        a=self.row('a');b=self.row('b');b['row']['ledger_status']='superseded'
        ledger={'readings':[a,b]};before=deepcopy(ledger)
        self.assertEqual(capture_table_view(ledger,{})['row_ids'],['a'])
        self.assertEqual(ledger,before)
    def test_stable_ledger_order_and_mixed_currency_sort_refusal(self):
        a=self.row('a');b=self.row('b');c=self.row('c');c['row']['ordering_date']='2026-01-02'
        self.assertEqual(capture_table_view({'readings':[c,b,a]}, {})['row_ids'],['a','b','c'])
        self.assertEqual(capture_table_view({'readings':[c,b,a]},dict(sort='newest'))['row_ids'],['c','a','b'])
        b['row']['currency']='USD'
        with self.assertRaises(LedgerSummaryError):capture_table_view({'readings':[a,b]},dict(sort='amount-desc'))
        for invalid in [dict(search='x'*257),dict(sort='raw_sql'),dict(extra=True)]:
            with self.assertRaises(LedgerSummaryError):capture_table_view({'readings':[]},invalid)

    def test_inclusive_bigint_range_requires_currency_and_preserves_full_capture(self):
        from copy import deepcopy
        a=self.row('a');b=self.row('b');b['row']['amount_minor']='9007199254740992'
        ledger={'readings':[a,b]};before=deepcopy(ledger)
        view=capture_table_view(ledger,dict(currency='GBP',minimum_minor='9007199254740993',maximum_minor='9007199254740993'))
        self.assertEqual(view['row_ids'],['a']);self.assertEqual(ledger,before)
        self.assertEqual(view['filters']['minimum_minor'],'9007199254740993')
        for invalid in [dict(minimum_minor='0'),dict(currency='GBP',minimum_minor='2',maximum_minor='1'),dict(currency='GBP',minimum_minor='9223372036854775808'),dict(currency='GBP',maximum_minor='1.2'),dict(currency='GBP',minimum_minor=0)]:
            with self.subTest(invalid=invalid),self.assertRaises(LedgerSummaryError):capture_table_view(ledger,invalid)
