import hashlib
import json
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from services.financial.ledger_snapshot import capture_ledger_snapshot
from services.financial.ledger_summary import LedgerSummaryError
from tests.test_financial_ledger_summary import LedgerSummaryTests

class LedgerSnapshotTests(LedgerSummaryTests):
    def capture(self):return capture_ledger_snapshot(self.db,case_id=self.case.id)

    def test_content_is_exact_stable_and_immutable(self):
        row,doc=self.add(9007199254740993)
        row.provenance={'note':'Original £ source'};self.db.commit()
        case_id=self.case.id  # Resolve the expired test fixture before measuring capture reads.
        with patch.object(self.db,'execute',wraps=self.db.execute) as read:
            first=capture_ledger_snapshot(self.db,case_id=case_id)
            self.assertEqual(read.call_count,1)
        second=self.capture()
        self.assertEqual(first,second)
        self.assertEqual(first.sha256,hashlib.sha256(first.content.encode('utf-8')).hexdigest())
        self.assertEqual(first.byte_count,len(first.content.encode('utf-8')))
        data=json.loads(first.content)
        self.assertFalse(data['export_ready'])
        self.assertFalse(data['ledger']['history_captured'])
        reading=data['ledger']['readings'][0]
        self.assertEqual(reading['row']['amount_minor'],'9007199254740993')
        self.assertEqual(reading['source']['sha256_at_ingestion'],doc.sha256_at_ingestion)
        self.assertEqual(data['ledger']['currencies'][0]['credits_minor'],reading['row']['amount_minor'])
        with self.assertRaises(FrozenInstanceError):first.content='changed'
        row.provenance={'note':'later'};self.db.commit()
        self.assertNotEqual(first.sha256,self.capture().sha256)
        self.assertIn('Original £ source',first.content)

    def test_excluded_reading_is_preserved_without_entering_totals(self):
        row,_=self.add();row.proof_class='p3';self.db.commit()
        data=json.loads(self.capture().content)['ledger']
        self.assertEqual(data['currencies'],[])
        self.assertEqual(data['readings'][0]['exclusion_reason'],'proof_class_not_included')
        self.assertFalse(data['readings'][0]['included'])
        self.assertEqual(data['excluded_rows'],1)

    def test_no_partial_snapshot_above_the_limit(self):
        self.add();self.add()
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS',1):
            with self.assertRaises(LedgerSummaryError):self.capture()
