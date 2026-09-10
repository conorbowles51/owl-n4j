import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests import test_financial_ledger_tracing as fixture
from services.financial.ledger_snapshot import LedgerExport
from services.financial.ledger_tracing import evaluate_ledger_trace
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.trace_replay import replay_trace


class TraceReplayTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.LedgerTracingTests()
        self.f.setUp()
        export, request, _, _ = self.f.scenario()
        manifest = dict(case_id=str(self.f.case.id), document_sha256=export.snapshot.sha256,
                        byte_count=export.snapshot.byte_count, code_version='historical-test-version')
        export = LedgerExport(export.snapshot, json.dumps(manifest))
        self.content = evaluate_ledger_trace(export, request)['scenario_json'].encode('utf-8')

    def tearDown(self):
        self.f.tearDown()

    def test_all_five_methods_replay_exactly_without_changing_input(self):
        original = bytes(self.content)
        report = replay_trace(self.content, expected_sha256=hashlib.sha256(self.content).hexdigest())
        self.assertEqual(report['status'], 'matching_calculations')
        self.assertEqual(report['difference_count'], 0)
        self.assertEqual(report['canonical_original_sha256'], report['recalculated_sha256'])
        self.assertEqual(report['captured_code_version'], 'historical-test-version')
        self.assertTrue(report['independently_supplied_digest_checked'])
        self.assertEqual(self.content, original)

    def test_changed_result_is_reported_at_exact_path(self):
        captured = json.loads(self.content)
        captured['comparison']['results']['first_in_first_out']['outcomes']['claim-a']['surviving']['minor_units'] = '1'
        report = replay_trace(json.dumps(captured).encode())
        self.assertEqual(report['status'], 'different_replay_output')
        self.assertEqual(report['difference_paths'], ['/comparison/results/first_in_first_out/outcomes/claim-a/surviving/minor_units'])

    def test_source_drift_case_change_and_wrong_digest_are_refused(self):
        for field in ('case', 'source', 'size'):
            captured = json.loads(self.content)
            if field == 'case': captured['case_id'] = 'different-case'
            elif field == 'source': captured['ledger_snapshot']['ledger']['readings'][0]['row']['amount_minor'] = '1'
            else: captured['ledger_manifest']['byte_count'] = True
            with self.assertRaises(LedgerSummaryError): replay_trace(json.dumps(captured).encode())
        with self.assertRaises(LedgerSummaryError): replay_trace(self.content, expected_sha256='a' * 64)

    def test_ambiguous_json_and_false_conditional_claim_are_refused(self):
        for content in (b'{"schema":1,"schema":2}', b'{"n":NaN}', b'[]', b'null'):
            with self.assertRaises(LedgerSummaryError): replay_trace(content)
        captured = json.loads(self.content)
        captured['assumptions_verified'] = True
        with self.assertRaises(LedgerSummaryError): replay_trace(json.dumps(captured).encode())

    def test_cli_returns_nonzero_for_changed_results_and_preserves_original(self):
        captured = json.loads(self.content)
        captured['limitations'].append('Changed original explanation')
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / 'scenario.json', Path(folder) / 'report.json'
            source.write_text(json.dumps(captured))
            before = source.read_bytes()
            root = Path(__file__).resolve().parents[2]
            run = subprocess.run([sys.executable, str(root / 'scripts/replay_financial_trace.py'), str(source), '--output', str(output)],
                                 env={**os.environ, 'PYTHON_DOTENV_DISABLED':'1'}, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertEqual(json.loads(output.read_text())['difference_count'], 1)
            self.assertEqual(source.read_bytes(), before)
