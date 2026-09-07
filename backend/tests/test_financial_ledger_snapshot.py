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

    def test_history_retains_actor_and_reason_and_is_case_scoped(self):
        from services.financial.quarantine_row import quarantine_case_row
        from services.financial.ledger_snapshot import _capture_history
        row,_=self.add()
        quarantine_case_row(self.db,case_id=self.case.id,transaction_id=row.id,actor=self.user,reason='Snapshot history test')
        document=json.loads(self.capture().content)
        result=_capture_history(self.db,document,case_id=self.case.id)
        self.assertTrue(result['ledger']['history_captured'])
        self.assertEqual(len(result['decisions']),1)
        self.assertEqual(result['decisions'][0]['reason'],'Investigator: Snapshot history test')
        self.assertEqual(result['decisions'][0]['actor_email'],self.user.email)
        self.assertEqual(result['decisions'][0]['subject_id'],str(row.id))
        self.assertEqual(_capture_history(self.db,json.loads(self.capture().content),case_id=self.other_case.id)['decisions'],[])
        with patch('services.financial.ledger_snapshot.MAX_EXPORT_DECISIONS',0):
            with self.assertRaises(LedgerSummaryError):_capture_history(self.db,document,case_id=self.case.id)

    def test_live_export_refuses_non_postgres_connections(self):
        from services.financial.ledger_snapshot import capture_ledger_export
        with self.assertRaises(LedgerSummaryError):capture_ledger_export(self.db.get_bind(),case_id=self.case.id)

    def test_archive_preserves_snapshot_bytes_and_safe_names(self):
        import io,zipfile
        from services.financial.ledger_snapshot import LedgerExport,ledger_export_archive
        snapshot=self.capture()
        with zipfile.ZipFile(io.BytesIO(ledger_export_archive(LedgerExport(snapshot,'{"manifest":true}')))) as archive:
            self.assertEqual(set(archive.namelist()),{'ledger-snapshot.json','manifest.json'})
            self.assertEqual(archive.read('ledger-snapshot.json'),snapshot.content.encode('utf-8'))

    def test_download_route_is_scoped_attachment_and_hides_internal_errors(self):
        from routers import financial_ledger as router
        from services.financial.ledger_snapshot import LedgerExport
        from fastapi import HTTPException
        case_id=self.case.id
        with patch.object(router,'capture_ledger_export',return_value=LedgerExport(self.capture(),'{}')) as call:
            response=router.download_ledger_export(case_id,None,None,None,self.db)
            call.assert_called_once_with(self.db.get_bind(),case_id=case_id,account_id=None,start_date=None,end_date=None)
            self.assertEqual(response.headers['content-type'],'application/zip')
            self.assertEqual(response.headers['x-loupe-case-id'],str(case_id))
            self.assertEqual(response.headers['cache-control'],'no-store')
        with patch.object(router,'capture_ledger_export',side_effect=RuntimeError('private')):
            with self.assertRaises(HTTPException) as caught:router.download_ledger_export(case_id,None,None,None,self.db)
            self.assertNotIn('private',caught.exception.detail)
