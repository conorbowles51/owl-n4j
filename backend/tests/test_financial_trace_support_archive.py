import hashlib
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from tests import test_financial_trace_replay as scenario_fixture
from tests import test_financial_extraction_evaluation as corpus_fixture
from services.financial.trace_support_archive import build_trace_support_archive
from services.financial.ledger_summary import LedgerSummaryError


class TraceSupportArchiveTests(unittest.TestCase):
    def setUp(self):
        self.f = scenario_fixture.TraceReplayTests()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def test_original_bytes_hashes_and_conditional_support_preserved(self):
        content = build_trace_support_archive([self.f.content])
        self.assertEqual(content, build_trace_support_archive([self.f.content]))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(archive.read('scenarios/01/scenario.json'), self.f.content)
            self.assertEqual(manifest['completeness'], 'incomplete_expert_packet')
            self.assertEqual(manifest['validation']['status'], 'unavailable')
            for entry in manifest['files']:
                data = archive.read(entry['filename'])
                self.assertEqual(entry['byte_count'], len(data))
                self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
            support = json.loads(archive.read('scenarios/01/expert-support.json'))
            self.assertEqual(support['tracing']['status'], 'selected_conditional_scenario')
            self.assertEqual(support['tracing']['scenario_sha256'], hashlib.sha256(self.f.content).hexdigest())

    def test_supplied_synthetic_measurements_stay_synthetic(self):
        corpus = corpus_fixture.ExtractionEvaluationTests().corpus()
        archive_bytes = build_trace_support_archive([self.f.content], validation_corpus=corpus)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['validation']['label_status'], 'synthetic_test')
            self.assertEqual(json.loads(archive.read('validation/corpus.json')), corpus)
            report = json.loads(archive.read('validation/measurements.json'))
            self.assertEqual(report['layers'][0]['errors_surviving_gate']['numerator'], 2)

    def test_duplicates_and_modified_calculations_refused(self):
        with self.assertRaises(LedgerSummaryError): build_trace_support_archive([self.f.content] * 2)
        scenario = json.loads(self.f.content)
        scenario['limitations'].append('Altered interpretation')
        with self.assertRaises(LedgerSummaryError): build_trace_support_archive([json.dumps(scenario).encode()])
        with self.assertRaises(LedgerSummaryError): build_trace_support_archive([])
        with self.assertRaises(LedgerSummaryError): build_trace_support_archive([self.f.content] * 9)

    def test_different_case_is_not_combined(self):
        from services.financial.trace_replay import replay_trace
        original = replay_trace(self.f.content)
        other = {**original, 'case_id':'other', 'original_sha256':'b' * 64}
        with patch('services.financial.trace_support_archive.replay_trace', side_effect=[original, other]):
            with self.assertRaisesRegex(LedgerSummaryError, 'same case'):
                build_trace_support_archive([self.f.content, self.f.content + b' '])
