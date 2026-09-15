import copy
import hashlib
import io
import json
import unittest
import zipfile

from services.financial.ledger_snapshot import LedgerExport
from services.financial.network_tracing import evaluate_network_trace
from services.financial.trace_scenario_report import render_scenario_report
from services.financial.trace_support_archive import build_trace_support_archive, verify_trace_support_archive
from tests.test_financial_network_tracing import NetworkTracingTests


class TraceScenarioReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = NetworkTracingTests()
        self.fixture.setUp()
        export, request, rows = self.fixture.network()
        # A separate incoming payment follows the purchase and is explicitly
        # selected as its resale receipt in this synthetic calculation.
        ordered = request['ordered_transaction_ids']
        ordered.append(ordered.pop(1))
        request['asset_uses'] = [dict(transaction_id=str(rows[-1].id), asset_label='<script>Equipment</script>',
            basis='Synthetic purchase reason', asset_amount_minor='1200', allocation_basis='proportional_share',
            resale=dict(transaction_id=str(rows[1].id), proceeds_minor='3001',
                        basis='Synthetic resale reason', allocation_basis='proportional_cost_share'))]
        manifest = dict(case_id=str(self.fixture.case.id), document_sha256=export.snapshot.sha256,
                        byte_count=export.snapshot.byte_count, code_version='saved-version')
        self.content = evaluate_network_trace(LedgerExport(export.snapshot, json.dumps(manifest)), request)['scenario_json'].encode()

    def tearDown(self):
        self.fixture.tearDown()

    def test_network_reports_include_transfer_claims_asset_and_resale_reasons(self):
        content = build_trace_support_archive([self.content], preparation={'privilege_marking': 'confidential'})
        self.assertEqual(verify_trace_support_archive(content)['status'], 'verified_bytes_matching_rebuild')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            report = archive.read('scenarios/01/report.html').decode()
            for value in ('Confidential', 'Synthetic purchase reason', 'Synthetic resale reason',
                          'Explicit synthetic transfers', 'Money carried through each transfer',
                          'Claim carried to receiving account', '12.00 GBP', '30.01 GBP',
                          'Lowest intermediate balance', 'Direct tracing', '&lt;script&gt;Equipment&lt;/script&gt;'):
                self.assertIn(value, report)
            self.assertNotIn('<script>', report)
            self.assertIn(hashlib.sha256(self.content).hexdigest(), report)
            self.assertEqual(archive.read('scenarios/01/scenario.json'), self.content)
        self.assertFalse(self.fixture.db.new or self.fixture.db.dirty)

    def test_outside_claim_amount_does_not_count_unidentified_and_unfunded_twice(self):
        scenario = json.loads(self.content)
        # Rendering check only: these deliberately supplied components total
        # 12.00. No claim is made that this is an accepted/replayed scenario.
        asset = scenario['results']['direct']['asset_uses'][0]
        asset.update(allocated_by_claim={'claim': '100'}, outside_claims_minor='1100',
                     unidentified_minor='300', unfunded_minor='200')
        asset.pop('resale', None)
        before = copy.deepcopy(scenario)
        report = render_scenario_report(scenario, scenario_sha256='a'*64).decode()
        self.assertIn('Other recorded funds</td><td data-label="Amount">6.00 GBP', report)
        self.assertIn('Not assigned by this method</td><td data-label="Amount">3.00 GBP', report)
        self.assertIn('Not covered by the recorded funds</td><td data-label="Amount">2.00 GBP', report)
        self.assertEqual(scenario, before)

    def test_broken_payment_link_is_refused_instead_of_silent_unlinked_output(self):
        scenario = json.loads(self.content)
        scenario['inputs']['attributions'][0]['transaction_id'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'outside the captured'):
            render_scenario_report(scenario, scenario_sha256='a'*64)
