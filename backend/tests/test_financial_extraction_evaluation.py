import unittest
from copy import deepcopy
from pydantic import ValidationError
from services.financial.extraction_evaluation import evaluate_extraction

class ExtractionEvaluationTests(unittest.TestCase):
    def corpus(self):
        return dict(schema_version='loupe.extraction_evaluation/1',corpus_id='synthetic',corpus_version='1',reviewer_ids=['synthetic-a','synthetic-b'],adjudication_reference='synthetic-review',label_status='synthetic_test',documents=[dict(source_sha256='a'*64,extraction_layer='ocr_model',extractor_version='test-1',proof_class='p3',balance_gate='unavailable',quarantined=False,truth=[dict(source_id='row-1',fields={'amount_minor':'100','direction':'credit'}),dict(source_id='row-2',fields={'amount_minor':'200','direction':'debit'})],predictions=[dict(source_id='row-1',fields={'amount_minor':'100','direction':'debit'},admitted=True),dict(source_id='invented',fields={'amount_minor':'300'},admitted=True)])])
    def test_missed_invented_and_wrong_direction_rows_are_separate_measurements(self):
        result=evaluate_extraction(self.corpus());layer=result['layers'][0]
        self.assertEqual(layer['row_recall'],dict(numerator=1,denominator=2,status='available'))
        self.assertEqual(layer['row_precision']['numerator'],1)
        self.assertEqual(layer['direction_accuracy']['numerator'],0)
        self.assertEqual(layer['fields']['amount_minor']['precision']['numerator'],1)
        self.assertEqual(layer['errors_surviving_gate']['numerator'],2)
        self.assertEqual(layer['balance_gate_by_class']['p3']['pass_rate']['status'],'unavailable')
    def test_no_predictions_means_zero_recall_and_unavailable_precision(self):
        corpus=self.corpus();corpus['documents'][0]['predictions']=[]
        layer=evaluate_extraction(corpus)['layers'][0]
        self.assertEqual(layer['row_recall']['numerator'],0)
        self.assertEqual(layer['row_precision']['status'],'unavailable')
        self.assertEqual(layer['errors_surviving_gate']['status'],'unavailable')
        self.assertEqual(layer['fields']['amount_minor']['missing'],2)
    def test_prediction_change_preserves_ground_truth_digest(self):
        corpus=self.corpus();first=evaluate_extraction(corpus)
        corpus['documents'][0]['predictions'][0]['fields']['direction']='credit'
        second=evaluate_extraction(corpus)
        self.assertEqual(first['ground_truth_sha256'],second['ground_truth_sha256'])
        self.assertNotEqual(first['corpus_sha256'],second['corpus_sha256'])
    def test_refuses_duplicate_rows_reviewers_sources_and_non_boolean_admission(self):
        for change in ('row','reviewer','source','boolean'):
            corpus=self.corpus();doc=corpus['documents'][0]
            if change=='row':doc['truth']*=2
            if change=='reviewer':corpus['reviewer_ids']=['same','same']
            if change=='source':corpus['documents']*=2
            if change=='boolean':doc['predictions'][0]['admitted']='false'
            with self.subTest(change=change),self.assertRaises(ValidationError):evaluate_extraction(corpus)
    def test_inputs_unchanged_and_synthetic_status_never_promoted(self):
        corpus=self.corpus();before=deepcopy(corpus)
        self.assertEqual(evaluate_extraction(corpus)['label_status'],'synthetic_test')
        self.assertEqual(corpus,before)

    def test_regression_compares_exact_rates_and_requires_unchanged_labels(self):
        from services.financial.extraction_evaluation import compare_extraction_evaluations
        baseline=self.corpus();current=deepcopy(baseline)
        current['documents'][0]['predictions']=[]
        comparison=compare_extraction_evaluations(baseline,current)
        self.assertEqual(comparison['status'],'regression')
        self.assertIn('row_recall',[r['metric'] for r in comparison['regressions']])
        self.assertEqual(compare_extraction_evaluations(baseline,baseline)['status'],'no_measured_regression')
        current['documents'][0]['truth'][0]['fields']['amount_minor']='changed'
        with self.assertRaises(ValueError):compare_extraction_evaluations(baseline,current)

    def test_command_writes_report_and_exits_nonzero_on_regression(self):
        import json, subprocess, sys, tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);baseline=self.corpus();current=deepcopy(baseline)
            current['documents'][0]['predictions']=[]
            (folder/'baseline.json').write_text(json.dumps(baseline))
            (folder/'current.json').write_text(json.dumps(current))
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[2]/'scripts/evaluate_financial_extraction.py'),str(folder/'current.json'),'--baseline',str(folder/'baseline.json'),'--output',str(folder/'report.json')],capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stderr)
            report=json.loads((folder/'report.json').read_text())
            self.assertEqual(report['comparison']['status'],'regression')
            self.assertEqual(report['label_status'],'synthetic_test')
