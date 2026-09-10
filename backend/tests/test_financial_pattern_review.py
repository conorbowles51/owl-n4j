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
