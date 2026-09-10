import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tests import test_financial_reference_reviews as review_fixtures
from tests import test_financial_extraction_evaluation as corpus_fixtures
from services.financial.reference_reviews import reconcile_reference_reviews


class ExtractionReleaseTests(unittest.TestCase):
    def run_check(self, *, synthetic=False, wrong_pin=False, regression=False, tampered=False):
        first, second = review_fixtures.ReferenceReviewTests().reviews()
        if not synthetic:
            first['label_status'] = second['label_status'] = 'independent_reader'
        record = reconcile_reference_reviews(first, second)
        document = corpus_fixtures.ExtractionEvaluationTests().corpus()['documents'][0]
        document.pop('truth')
        document['predictions'] = [{**first['documents'][0]['rows'][0], 'admitted':True}]
        baseline = dict(schema_version='loupe.extraction_predictions/1', corpus_id=record['corpus_id'],
            corpus_version=record['corpus_version'], documents=[document])
        current = json.loads(json.dumps(baseline))
        if regression:
            current['documents'][0]['predictions'][0]['fields']['direction'] = 'debit'
        if tampered:
            record['documents'][0]['truth'][0]['fields']['direction'] = 'debit'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, value in [('review',record), ('baseline',baseline), ('current',current)]:
                (directory / (name + '.json')).write_text(json.dumps(value))
            digest = hashlib.sha256((directory / 'baseline.json').read_bytes()).hexdigest()
            result = subprocess.run([sys.executable,
                str(Path(__file__).resolve().parents[2] / 'scripts/check_financial_extraction_release.py'),
                '--review-record', str(directory / 'review.json'), '--expected-review-sha256', record['review_record_sha256'],
                '--baseline', str(directory / 'baseline.json'), '--expected-baseline-sha256', '0'*64 if wrong_pin else digest,
                '--current', str(directory / 'current.json'), '--output', str(directory / 'result.json')],
                capture_output=True, text=True, timeout=20)
            report = json.loads((directory / 'result.json').read_text()) if (directory / 'result.json').exists() else None
            return result, report

    def test_pinned_declared_independent_inputs_pass_without_claiming_absolute_accuracy(self):
        result, report = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['status'], 'no_measured_regression')
        self.assertIn('acceptable absolute accuracy', report['limitation'])

    def test_regression_writes_report_and_returns_failure(self):
        result, report = self.run_check(regression=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['status'], 'regression')
        self.assertTrue(report['comparison']['regressions'])

    def test_synthetic_changed_pins_and_tampered_reviews_never_pass(self):
        for option in ('synthetic', 'wrong_pin', 'tampered'):
            with self.subTest(option=option):
                result, report = self.run_check(**{option:True})
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(report)
