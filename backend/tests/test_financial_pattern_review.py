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

    def path_fixture(self, returning=False):
        rows=[];pairs=[]
        for i,(a,b) in enumerate([('A','B'),('B','A' if returning else 'C')]):
            for label,account,direction in [('d',a,'debit'),('c',b,'credit')]:
                row=self.pair()[0];row['row'].update(key=f'{label}{i}',account_id=account,direction=direction,transaction_date=f'2026-01-0{i+1}')
                rows.append(row)
            pairs.append(dict(debit_id=f'd{i}',credit_id=f'c{i}',currency='GBP',amount_minor='9007199254740993',outcome='ambiguous'))
        return rows,pairs

    def test_optional_paths_retain_every_posting_and_candidate_pair(self):
        for returning,kind in [(False,'possible_transfer_chain'),(True,'possible_return_flow')]:
            rows,pairs=self.path_fixture(returning)
            with patch('services.financial.ledger_transfers.ledger_transfer_candidates',return_value={'candidates':pairs}):
                found=screen_ledger_patterns(self.capture(rows),cross_account=True)
            paths=[h for h in found['hypotheses'] if h['kind']==kind]
            self.assertEqual(len(paths),1)
            self.assertEqual(paths[0]['transaction_ids'],['d0','c0','d1','c1'])
            self.assertEqual(paths[0]['transfer_pairs'],pairs)
            self.assertEqual(len(paths[0]['sources']),4)
            self.assertTrue(found['cross_account'])

    def test_path_screen_respects_dates_currency_zero_and_no_reused_posting(self):
        for update in ['backward','zero','reuse','currency']:
            rows,pairs=self.path_fixture()
            if update=='backward':rows[2]['row']['transaction_date']='2025-12-31'
            if update=='zero':pairs[0]['amount_minor']='0'
            if update=='reuse':pairs[1]['debit_id']='d0'
            if update=='currency':pairs[1]['currency']='USD'
            with patch('services.financial.ledger_transfers.ledger_transfer_candidates',return_value={'candidates':pairs}):
                found=screen_ledger_patterns(self.capture(rows),cross_account=True)
            self.assertFalse(any(h['kind'].startswith('possible_') for h in found['hypotheses']),update)
        with self.assertRaises(LedgerSummaryError):screen_ledger_patterns(self.capture([]),cross_account='yes')
