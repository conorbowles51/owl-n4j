from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from services.financial.money import Money
from services.financial.statement_delta_hints import statement_delta_hints


class StatementDeltaHintTests(TestCase):
    def setUp(self):
        self.period=SimpleNamespace(id='period',case_id='case',account_id='account',source_document_id='source',currency='GBP')
        self.rows=[]
        self.session=Mock()
        self.session.scalars.side_effect=lambda _:self.rows

    def add(self,amount,direction='credit'):
        id='row-'+str(len(self.rows))
        self.rows.append(SimpleNamespace(id=id,ref_id=id,row_index=len(self.rows),case_id='case',account_id='account',source_document_id='source',currency='GBP',amount_minor=amount,direction=direction))
        return id

    def hints(self,difference,opening=0):
        return statement_delta_hints(self.session,self.period,SimpleNamespace(
            delta=None if difference is None else Money(difference,'GBP'),opening=Money(opening,'GBP')))

    def test_candidates_respect_direction_and_distinguish_arithmetic_effects(self):
        flipped=self.add(10);extra=self.add(20);missing=self.add(20,'debit');wrong_direction=self.add(10,'debit')
        result=self.hints(20)
        self.assertEqual({r['transaction_id']:r['kind'] for r in result['candidates']},
            {flipped:'direction_change',extra:'extra_entry',missing:'missing_entry'})
        self.assertNotIn(wrong_direction,[r['transaction_id'] for r in result['candidates']])
        self.assertEqual(result['rows_checked'],4)

    def test_negative_difference_reverses_the_relevant_direction(self):
        self.add(10,'debit');self.add(10)
        result=self.hints(-20)
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['candidates'][0]['direction'],'debit')

    def test_balanced_and_unknown_are_distinct_and_do_not_scan_rows(self):
        self.assertFalse(self.hints(None)['available'])
        result=self.hints(0)
        self.assertTrue(result['available']);self.assertEqual(result['candidates'],[])
        self.session.scalars.assert_not_called()

    def test_bounds_do_not_emit_truncated_leads(self):
        self.add(10);self.add(10)
        for bound in ('MAX_HINT_ROWS','MAX_HINTS'):
            with patch('services.financial.statement_delta_hints.'+bound,1):
                self.assertFalse(self.hints(20)['available'])

    def test_foreign_row_refused(self):
        self.add(10);self.rows[0].case_id='other'
        with self.assertRaises(ValueError):self.hints(20)

    def test_bigint_and_opening_signatures_remain_exact(self):
        amount=9007199254740993;self.add(amount)
        result=self.hints(amount,amount)
        self.assertEqual(result['difference_minor'],str(amount))
        self.assertEqual(result['candidates'][0]['amount_minor'],str(amount))
        self.assertIn('opening_omitted',[s['kind'] for s in result['signatures']])
