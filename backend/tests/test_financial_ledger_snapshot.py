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
            self.assertEqual(set(archive.namelist()),{'ledger-snapshot.json','manifest.json','ledger-report.html','expert-support.json'})
            self.assertEqual(archive.read('ledger-snapshot.json'),snapshot.content.encode('utf-8'))
            report=archive.read('ledger-report.html')
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['report']['sha256'],hashlib.sha256(report).hexdigest())
            self.assertEqual(manifest['report']['byte_count'],len(report))
            self.assertEqual(manifest['report']['derived_from_sha256'],snapshot.sha256)
            support=archive.read('expert-support.json')
            self.assertEqual(manifest['expert_support']['sha256'],hashlib.sha256(support).hexdigest())
            self.assertEqual(json.loads(support)['derived_from_sha256'],snapshot.sha256)
            self.assertEqual(json.loads(support)['validation']['status'],'unavailable')
            self.assertEqual(json.loads(support)['completeness'],'incomplete_expert_packet')

    def test_optional_pdf_is_bound_to_the_same_snapshot_manifest(self):
        import io, zipfile
        from services.financial.ledger_snapshot import LedgerExport, ledger_export_archive
        from services.financial.ledger_pdf import render_ledger_pdf
        snapshot = self.capture()
        content = b'%PDF-1.7 synthetic renderer fixture'
        with patch('services.financial.ledger_pdf.render_ledger_pdf', return_value=content) as render:
            zipped = ledger_export_archive(LedgerExport(snapshot,'{}'), include_pdf=True)
        self.assertEqual(render.call_args.args[0],snapshot)
        with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
            self.assertEqual(archive.read('ledger-report.pdf'),content)
            proof=json.loads(archive.read('manifest.json'))['pdf_report']
            self.assertEqual(proof['derived_from_sha256'],snapshot.sha256)
            self.assertEqual(proof['sha256'],hashlib.sha256(content).hexdigest())
            self.assertEqual(proof['byte_count'],len(content))
        self.add()
        with patch('services.financial.ledger_pdf.MAX_PDF_READINGS',0):
            with self.assertRaises(LedgerSummaryError):render_ledger_pdf(self.capture(),'')

    def test_download_route_is_scoped_attachment_and_hides_internal_errors(self):
        from routers import financial_ledger as router
        from services.financial.ledger_snapshot import LedgerExport
        from fastapi import HTTPException
        case_id=self.case.id
        with patch.object(router,'capture_ledger_export',return_value=LedgerExport(self.capture(),'{}')) as call, patch.object(router,'record_prepared_export',return_value=dict(export_id='synthetic',entry_sha256='a'*64,sequence=1)) as audited:
            response=router.download_ledger_export(case_id,None,None,None,self.db)
            call.assert_called_once_with(self.db.get_bind(),case_id=case_id,account_id=None,start_date=None,end_date=None,privilege_marking="unmarked",generated_by=None)
            self.assertEqual(response.headers['content-type'],'application/zip')
            self.assertEqual(response.headers['x-loupe-case-id'],str(case_id))
            self.assertEqual(response.headers['cache-control'],'no-store')
            self.assertEqual(response.headers['x-loupe-export-event-sha256'],'a'*64)
            self.assertEqual(audited.call_args.kwargs['content'],response.body)
        with patch.object(router,'capture_ledger_export',side_effect=RuntimeError('private')):
            with self.assertRaises(HTTPException) as caught:router.download_ledger_export(case_id,None,None,None,self.db)
            self.assertNotIn('private',caught.exception.detail)

    def test_report_escapes_evidence_preserves_exact_money_and_limits(self):
        from services.financial.ledger_snapshot import render_ledger_report
        row, _ = self.add(amount=9007199254740993)
        row.description = '<script>alert("evidence")</script>'
        row.provenance = {'unsafe': '<img src="https://example.org/track">'}
        self.db.commit()
        report = render_ledger_report(self.capture())
        self.assertIn('9007199254740993', report)
        self.assertIn('&lt;script&gt;', report)
        self.assertNotIn('<script>', report)
        self.assertNotIn('<img ', report)
        self.assertIn('minor units', report)
        self.assertIn('Decision history has not been captured', report)
        with patch('services.financial.ledger_snapshot.MAX_EXPORT_BYTES', 1):
            with self.assertRaises(LedgerSummaryError): render_ledger_report(self.capture())

    def test_report_money_uses_exact_currency_exponents_and_honest_fallback(self):
        from services.financial.ledger_snapshot import render_ledger_report, LedgerSnapshot
        self.add()
        document = json.loads(self.capture().content)
        for currency, value, expected in (
            ('USD', '9007199254740993', '90,071,992,547,409.93 USD'),
            ('JPY', '-1234', '-1,234 JPY'),
            ('KWD', '1234', '1.234 KWD'),
            ('CLF', '1234', '0.1234 CLF'),
            ('IEP', '1234', '12.34 IEP (historical currency)'),
            ('ZZZ', '1234', '1234 minor units (unscaled: unsupported currency)'),
        ):
            with self.subTest(currency=currency):
                row = document['ledger']['readings'][0]['row']
                row['currency'], row['amount_minor'] = currency, value
                report = render_ledger_report(LedgerSnapshot(json.dumps(document), 'test', 0))
                self.assertIn(expected, report)
                self.assertIn(value, report)

    def test_export_actor_and_selected_marking_are_server_supplied(self):
        from routers import financial_ledger as router
        from services.financial.ledger_snapshot import LedgerExport
        from types import SimpleNamespace
        user=SimpleNamespace(id=self.user.id,name='Recorded exporter',email='recorded@example.test')
        with patch.object(router,'capture_ledger_export',return_value=LedgerExport(self.capture(),'{}')) as call, patch.object(router,'record_prepared_export',return_value=dict(export_id='synthetic',entry_sha256='a'*64,sequence=1)) as audited:
            response=router.download_ledger_export(self.case.id,None,None,None,self.db,privilege_marking='confidential',current_user=user)
        self.assertEqual(call.call_args.kwargs['generated_by']['id'],str(user.id))
        self.assertEqual(call.call_args.kwargs['privilege_marking'],'confidential')
        self.assertEqual(response.headers['x-loupe-privilege-marking'],'confidential')

    def test_ledger_audit_failure_withholds_prepared_archive(self):
        from routers import financial_ledger as router
        from services.financial.ledger_snapshot import LedgerExport
        from fastapi import HTTPException
        with patch.object(router,'capture_ledger_export',return_value=LedgerExport(self.capture(),'{}')),patch.object(router,'record_prepared_export',side_effect=RuntimeError('private audit failure')):
            with self.assertRaises(HTTPException) as caught:
                router.download_ledger_export(self.case.id,None,None,None,self.db)
        self.assertEqual(caught.exception.status_code,500)
        self.assertNotIn('private',caught.exception.detail)

    def test_report_includes_authored_notes_and_escapes_their_content(self):
        from services.financial.ledger_snapshot import LedgerSnapshot, render_ledger_report
        self.add()
        document=json.loads(self.capture().content)
        document['investigation_notes']=[dict(title='Payment question',author_name='Investigator',version=2,
            review_state='accepted',body='Ask about <script>this payment</script>',
            links=[dict(filename='statement.pdf',transactions=[dict(ref_id='source-reference')])])]
        report=render_ledger_report(LedgerSnapshot(json.dumps(document),'test',0))
        self.assertIn('Investigation notes',report)
        self.assertIn('source-reference',report)
        self.assertIn('&lt;script&gt;this payment&lt;/script&gt;',report)
        self.assertNotIn('<script>',report)
