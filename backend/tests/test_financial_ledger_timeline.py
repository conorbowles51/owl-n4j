import hashlib
import json
from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace
from services.financial.ledger_timeline import ledger_timeline
from services.financial.ledger_summary import LedgerSummaryError

class LedgerTimelineTests(TestCase):
    def capture(self, rows):
        ledger=dict(case_id='case',account_id=None,start_date=None,end_date=None,history_captured=True,readings=rows)
        content=json.dumps(dict(export_ready=True,ledger=ledger))
        return SimpleNamespace(snapshot=SimpleNamespace(content=content,sha256=hashlib.sha256(content.encode()).hexdigest()))
    def reading(self, key, **dates):
        return dict(included=False,exclusion_reason='proof_class_not_included',account={'label':'Account A'},row=dict(key=key,account_id='account',ordering_date='2026-01-15',**dates))
    def test_value_date_precedes_transaction_and_undated_remains_explicit(self):
        first=self.reading('first',value_date='2026-01-02',transaction_date='2026-01-03')
        unknown=self.reading('unknown',effective_date='2026-01-15',ordering_date_context='statement_end_ordering_only')
        result=ledger_timeline(self.capture([unknown,first]))
        self.assertEqual([r['key'] for r in result['rows']],['first','unknown'])
        self.assertEqual(result['rows'][0]['chronology_date'],'2026-01-02')
        self.assertEqual(result['rows'][0]['chronology_basis'],'value_date')
        self.assertEqual(result['rows'][1]['chronology_basis'],'statement_end_ordering_only')
        self.assertEqual(result['rows'][1]['account_label'],'Account A')
    def test_verified_excludes_p3_and_working_excludes_decisions(self):
        p3=self.reading('p3');excluded=self.reading('excluded');excluded['exclusion_reason']='explicitly_excluded'
        capture=self.capture([p3,excluded])
        self.assertEqual(ledger_timeline(capture,population='verified')['rows'],[])
        self.assertEqual(len(ledger_timeline(capture)['rows']),1)
        self.assertEqual(ledger_timeline(capture)['excluded_rows'],1)
    def test_limit_and_invalid_population_refuse(self):
        capture=self.capture([self.reading('one')])
        with self.assertRaises(LedgerSummaryError):ledger_timeline(capture,population='all')
        with patch('services.financial.ledger_timeline.MAX_TIMELINE_ROWS',0),self.assertRaises(LedgerSummaryError):ledger_timeline(capture)
