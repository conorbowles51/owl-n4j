from unittest.mock import patch
from tests.test_financial_ledger_timeline import LedgerTimelineTests
from services.financial.pattern_review import screen_ledger_patterns
from services.financial.ledger_summary import LedgerSummaryError

class PatternReviewTests(LedgerTimelineTests):
    def pair(self, direction='debit', date='2026-01-02'):
        rows=[]
        for key,d,day in [('credit','credit','2026-01-01'),('other',direction,date)]:
            r=self.reading(key,transaction_date=day,direction=d,currency='GBP',amount_minor='9007199254740993')
            r.update(source={'evidence_file_id':'file'},provenance={'original':'preserved'});rows.append(r)
        return rows
    def test_exact_amount_sources_and_rule_are_retained(self):
        result=screen_ledger_patterns(self.capture(self.pair()))
        self.assertEqual(len(result['hypotheses']),1)
        h=result['hypotheses'][0];self.assertEqual(h['kind'],'equal_amount_in_and_out');self.assertEqual(h['gap_days'],1)
        self.assertEqual(h['amount_minor'],'9007199254740993');self.assertEqual(h['sources'][0]['provenance'],{'original':'preserved'})
        self.assertEqual(screen_ledger_patterns(self.capture(self.pair('credit')))['hypotheses'][0]['kind'],'repeated_equal_amount')
    def test_scope_and_unknown_dates_do_not_suggest_matches(self):
        for field,value in [('currency','USD'),('account_id','other'),('amount_minor','9007199254740992'),('ordering_date_context','statement_end_ordering_only')]:
            rows=self.pair();rows[1]['row'][field]=value
            self.assertEqual(screen_ledger_patterns(self.capture(rows))['hypotheses'],[])
        self.assertEqual(screen_ledger_patterns(self.capture(self.pair()),window_days=0)['hypotheses'],[])
        self.assertEqual(screen_ledger_patterns(self.capture(self.pair()),population='verified')['hypotheses'],[])
    def test_large_and_invalid_screens_refuse(self):
        with patch('services.financial.pattern_review.MAX_HYPOTHESES',0),self.assertRaises(LedgerSummaryError):screen_ledger_patterns(self.capture(self.pair()))
        with self.assertRaises(LedgerSummaryError):screen_ledger_patterns(self.capture(self.pair()),window_days=31)

    def split_rows(self, amounts, days=None):
        rows=[]
        for i, amount in enumerate(amounts):
            row=self.pair('credit')[0]
            row['row'].update(key=str(i),amount_minor=str(amount),transaction_date=(days or ['2026-01-01']*len(amounts))[i])
            rows.append(row)
        return rows

    def split_screen(self, rows, **kwargs):
        result=screen_ledger_patterns(self.capture(rows),threshold_minor=kwargs.pop('threshold_minor',100),threshold_currency='GBP',**kwargs)
        return [h for h in result['hypotheses'] if h['kind']=='split_payment_threshold']

    def test_split_payments_exact_sum_and_all_sources(self):
        rows=self.split_rows([9007199254740992,2,1])
        hits=self.split_screen(rows,threshold_minor=9007199254740994)
        self.assertEqual(len(hits),1)
        self.assertEqual(hits[0]['amount_minor'],'9007199254740995')
        self.assertEqual(hits[0]['transaction_ids'],['0','1','2'])
        self.assertEqual(len(hits[0]['sources']),3)
        self.assertIn('not a statutory threshold',hits[0]['explanation'])
        self.assertNotEqual(hits[0]['id'],self.split_screen(rows,threshold_minor=9007199254740993)[0]['id'])

    def test_split_threshold_boundaries_and_partitions(self):
        self.assertEqual(self.split_screen(self.split_rows([100,40,50])),[])
        self.assertEqual(self.split_screen(self.split_rows([40,60]))[0]['amount_minor'],'100')
        for field,value in [('currency','USD'),('account_id','other'),('direction','debit'),('ordering_date_context','statement_end_ordering_only')]:
            rows=self.split_rows([40,60]);rows[1]['row'][field]=value
            self.assertEqual(self.split_screen(rows),[])
        self.assertEqual(self.split_screen(self.split_rows([40,60]),population='verified'),[])

    def test_split_windows_keep_new_payments_but_not_subsets(self):
        rows=self.split_rows([40,60,70],['2026-01-01','2026-01-02','2026-01-03'])
        self.assertEqual([h['transaction_ids'] for h in self.split_screen(rows,window_days=1)],[['0','1'],['1','2']])
        self.assertEqual([h['transaction_ids'] for h in self.split_screen(rows,window_days=3)],[['0','1','2']])

    def test_split_invalid_and_oversized_refuse_whole_result(self):
        for args in [dict(threshold_minor=100),dict(threshold_currency='GBP'),dict(threshold_minor=True,threshold_currency='GBP'),dict(threshold_minor=100,threshold_currency='gbp')]:
            with self.assertRaises(LedgerSummaryError):screen_ledger_patterns(self.capture([]),**args)
        with self.assertRaisesRegex(LedgerSummaryError,'more than 50'):
            self.split_screen(self.split_rows(range(1,52)),threshold_minor=1000)
