import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from services.financial.audit_chain import verify_financial_audit_chain
from services.financial.audit_timestamp import checkpoint
from services.financial.periodic_audit_anchor import anchor_financial_case_once
from tests.test_financial_audit_chain import FinancialAuditChainTests
from tests.test_financial_export_comparison import ExportComparisonTests
MODULE='services.financial.periodic_audit_anchor.'


class PeriodicAnchorTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.case=uuid4()
        fixture=FinancialAuditChainTests();fixture.case=self.case
        self.entries=fixture.entries();self.chain=dict(entries=self.entries,verification=verify_financial_audit_chain(self.entries,case_id=self.case))
        self.document=ExportComparisonTests().document();self.document['ledger']['case_id']=str(self.case)
        self.document['case_financial_history']=dict(audit_chain=self.chain)
        self.archive=ExportComparisonTests().archive(self.document)
        self.folder=self.root/str(self.case)
        self.options=dict(case_id=self.case,output=self.root,tsa_url='https://synthetic.invalid/tsa',ca_file=self.root/'roots.pem')
        self.head=self.patch('_current_chain',return_value=self.chain)
        self.capture=self.patch('capture_ledger_export',return_value=SimpleNamespace(snapshot=SimpleNamespace(content=json.dumps(self.document))))
        self.package=self.patch('ledger_export_archive',return_value=self.archive)
        def submit(archive,output,**kwargs):
            output.mkdir();(output/'response.tsr').write_bytes(b'SYNTHETIC MOCK SIGNATURE')
        self.submit=self.patch('submit_financial_audit_timestamp',side_effect=submit)
        self.verify=self.patch('verify_financial_audit_timestamp_response',side_effect=lambda archive,*a,**k:dict(checkpoint=json.loads(checkpoint(archive))))
    def patch(self,name,**kwargs):
        p=patch(MODULE+name,**kwargs);self.addCleanup(p.stop);return p.start()
    def run_once(self,**changes):return anchor_financial_case_once(None,**{**self.options,**changes})
    def test_one_submission_then_verified_unchanged_head_skips_capture(self):
        first=self.run_once();self.assertEqual(first['status'],'timestamp_verified')
        self.assertEqual(self.run_once()['status'],'unchanged_verified_head')
        self.assertEqual(self.submit.call_count,1);self.assertEqual(self.capture.call_count,1)
        self.assertFalse((self.folder/'pending.json').exists())
        self.assertEqual((self.folder/first['attempt_id']/'captured-ledger.zip').read_bytes(),self.archive)
    def test_failure_retained_and_no_blind_scheduled_retry(self):
        self.submit.side_effect=ValueError('Delivery uncertain')
        with self.assertRaises(ValueError):self.run_once()
        self.assertEqual(self.run_once()['status'],'attention_required')
        self.assertEqual(self.submit.call_count,1)
        pending=json.loads((self.folder/'pending.json').read_text())
        self.assertEqual(pending['error_type'],'ValueError');self.assertNotIn('Delivery',str(pending))
        self.assertFalse((self.folder/'latest.json').exists())
        with self.assertRaises(ValueError):self.run_once(retry_failed=True)
        self.assertEqual(self.submit.call_count,2)
    def test_completed_response_recovers_after_interrupted_pointer_write_without_network(self):
        first=self.run_once();pointer=(self.folder/'latest.json').read_bytes()
        (self.folder/'pending.json').write_bytes(pointer);(self.folder/'latest.json').unlink()
        self.assertEqual(self.run_once()['status'],'recovered_verified_timestamp')
        self.assertEqual(self.submit.call_count,1)
        self.assertEqual(json.loads((self.folder/'latest.json').read_text())['attempt_id'],first['attempt_id'])
    def test_invalid_retained_signature_cannot_be_used_as_skip_or_recovered_success(self):
        self.run_once();self.verify.side_effect=ValueError('Invalid signature')
        with self.assertRaises(ValueError):self.run_once()
        self.assertEqual(self.submit.call_count,1)
    def test_current_history_must_extend_independently_verified_prior_head(self):
        self.run_once()
        self.head.return_value=dict(entries=self.entries[:-1],verification=verify_financial_audit_chain(self.entries[:-1],case_id=self.case))
        with self.assertRaisesRegex(ValueError,'does not extend'):self.run_once()
        self.assertEqual(self.submit.call_count,1)
    def test_no_events_and_parallel_runner_do_not_submit(self):
        import fcntl
        self.head.return_value=dict(entries=[],verification=verify_financial_audit_chain([],case_id=self.case))
        self.assertEqual(self.run_once()['status'],'no_recorded_events')
        with (self.folder/'runner.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.run_once()['status'],'already_running')
        self.submit.assert_not_called()

    def test_cli_requires_explicit_mode_and_prevents_watch_retry_loop(self):
        import os, subprocess, sys
        root=Path(__file__).resolve().parents[2]
        command=[sys.executable,str(root/'scripts/anchor_financial_cases.py')]
        env={**os.environ,'PYTHON_DOTENV_DISABLED':'1'}
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        result=subprocess.run(command+['--watch','--retry-failed','--case-id',str(self.case),
            '--output',str(self.root/'unused'),'--tsa-url','https://synthetic.invalid',
            '--ca-file',str(self.root/'absent.pem')],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('automatic retry loops are not permitted',result.stderr)
        self.assertFalse((self.root/'unused').exists())
