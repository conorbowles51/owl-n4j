from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from services.financial.reference_reviews import reconcile_reference_reviews, evaluation_from_reference_reviews, parse_review_json


class ReferenceReviewTests(unittest.TestCase):
    def reviews(self):
        first = dict(schema_version='loupe.extraction_reader_review/1', corpus_id='synthetic-corpus', corpus_version='1',
            review_id='review-a', reviewer_id='reader-a', label_status='synthetic_test', documents=[dict(source_sha256='a'*64,
            complete_source_reviewed=True, rows=[dict(source_id='page-1/row-1', fields={'amount_minor':'9007199254740993','direction':'credit'})])])
        second = deepcopy(first);second.update(review_id='review-b', reviewer_id='reader-b')
        return first, second

    def adjudication(self, report, resolutions):
        return dict(schema_version='loupe.extraction_review_adjudication/1', adjudication_id='adjudication-1', adjudicator_id='review-lead',
            first_review_sha256=report['first_review_sha256'], second_review_sha256=report['second_review_sha256'], resolutions=resolutions)

    def test_agreed_labels_are_exact_and_synthetic_status_preserved(self):
        a, b = self.reviews();before = deepcopy((a,b))
        result = reconcile_reference_reviews(a,b)
        self.assertEqual(result['status'],'labels_reconciled')
        self.assertEqual(result['label_status'],'synthetic_test')
        self.assertEqual(result['documents'][0]['truth'],a['documents'][0]['rows'])
        self.assertEqual((a,b),before)
        self.assertIsNone(result['adjudication'])

    def test_field_or_presence_disagreement_never_emits_partial_truth(self):
        a,b = self.reviews();b['documents'][0]['rows'][0]['fields']['direction']='debit'
        result = reconcile_reference_reviews(a,b)
        self.assertEqual(result['status'],'needs_adjudication')
        self.assertNotIn('documents',result)
        self.assertEqual(result['disagreements'][0]['disagreement'],'field_values')
        b['documents'][0]['rows']=[]
        self.assertEqual(reconcile_reference_reviews(a,b)['disagreements'][0]['disagreement'],'row_presence')

    def test_explicit_exclusion_and_corrected_fields_require_bound_resolution(self):
        a,b = self.reviews();b['documents'][0]['rows']=[]
        result = reconcile_reference_reviews(a,b)
        resolution=dict(source_sha256='a'*64,source_id='page-1/row-1',final_fields=None,reason='Synthetic summary row, not a transaction.')
        resolved=reconcile_reference_reviews(a,b,adjudication=self.adjudication(result,[resolution]))
        self.assertEqual(resolved['status'],'labels_reconciled')
        self.assertEqual(resolved['documents'][0]['truth'],[])
        resolution['final_fields']={'amount_minor':'25','direction':'credit'}
        resolved=reconcile_reference_reviews(a,b,adjudication=self.adjudication(result,[resolution]))
        self.assertEqual(resolved['documents'][0]['truth'][0]['fields']['amount_minor'],'25')
        b['review_id']='a-new-reader-version'
        with self.assertRaisesRegex(ValueError,'versions'):
            reconcile_reference_reviews(a,b,adjudication=self.adjudication(result,[resolution]))

    def test_same_reader_source_mismatch_partial_coverage_and_agreement_override_refused(self):
        for change in ('reader','inventory','coverage'):
            a,b=self.reviews()
            if change=='reader':b['reviewer_id']=a['reviewer_id']
            elif change=='inventory':b['documents'][0]['source_sha256']='b'*64
            else:b['documents'][0]['complete_source_reviewed']=False
            with self.subTest(change=change),self.assertRaises(ValueError):reconcile_reference_reviews(a,b)
        a,b=self.reviews();result=reconcile_reference_reviews(a,b)
        resolution=dict(source_sha256='a'*64,source_id='page-1/row-1',final_fields=None,reason='Cannot override agreed label silently')
        with self.assertRaises(ValueError):reconcile_reference_reviews(a,b,adjudication=self.adjudication(result,[resolution]))

    def test_partial_adjudication_does_not_emit_truth_and_duplicate_resolution_refused(self):
        a,b=self.reviews();a['documents'][0]['rows'].append(dict(source_id='row-2',fields={'amount_minor':'12'}));b['documents'][0]['rows']=[]
        result=reconcile_reference_reviews(a,b)
        resolution=dict(source_sha256='a'*64,source_id='row-2',final_fields=None,reason='Synthetic exclusion')
        partial=reconcile_reference_reviews(a,b,adjudication=self.adjudication(result,[resolution]))
        self.assertEqual(partial['unresolved_count'],1)
        self.assertNotIn('documents',partial)
        with self.assertRaises(ValueError):reconcile_reference_reviews(a,b,adjudication=self.adjudication(result,[resolution,resolution]))

    def test_cli_unresolved_reviews_exit_two_and_preserve_inputs(self):
        a,b=self.reviews();b['documents'][0]['rows']=[]
        with tempfile.TemporaryDirectory() as folder:
            first,second,out=(Path(folder)/name for name in ('first.json','second.json','report.json'))
            first.write_text(json.dumps(a));second.write_text(json.dumps(b))
            before=(first.read_bytes(),second.read_bytes())
            script=Path(__file__).resolve().parents[2]/'scripts/reconcile_financial_reference_reviews.py'
            run=subprocess.run([sys.executable,str(script),str(first),str(second),'--output',str(out)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2,run.stderr)
            self.assertNotIn('documents',json.loads(out.read_text()))
            self.assertEqual((first.read_bytes(),second.read_bytes()),before)

    def predictions(self):
        return dict(schema_version='loupe.extraction_predictions/1',corpus_id='synthetic-corpus',corpus_version='1',
            documents=[dict(source_sha256='a'*64,extraction_layer='native',extractor_version='synthetic-version',proof_class='p3',
                balance_gate='unavailable',quarantined=False,predictions=[dict(source_id='page-1/row-1',fields={'amount_minor':'9007199254740993','direction':'credit'},admitted=False)])])

    def test_prediction_binding_retains_exact_labels_and_rejects_changed_truth(self):
        record=reconcile_reference_reviews(*self.reviews())
        result=evaluation_from_reference_reviews(record,self.predictions())
        self.assertEqual(result['label_status'],'synthetic_test')
        self.assertEqual(result['documents'][0]['truth'][0]['fields']['amount_minor'],'9007199254740993')
        record['documents'][0]['truth'][0]['fields']['amount_minor']='1'
        from services.financial.pdf_candidates import _digest
        record['review_record_sha256']=_digest({key:value for key,value in record.items() if key!='review_record_sha256'})
        with self.assertRaisesRegex(ValueError,'changed'):evaluation_from_reference_reviews(record,self.predictions())

    def test_duplicate_json_keys_and_nonfinite_values_are_refused(self):
        for value in ('{"amount":"1","amount":"2"}', '{"value":NaN}'):
            with self.assertRaises(ValueError):parse_review_json(value)

    def test_predictions_cannot_substitute_truth_or_omit_sources(self):
        record=reconcile_reference_reviews(*self.reviews())
        predictions=self.predictions();predictions['documents'][0]['truth']=[]
        with self.assertRaises(ValueError):evaluation_from_reference_reviews(record,predictions)
        predictions=self.predictions();predictions['documents']=[]
        with self.assertRaises(ValueError):evaluation_from_reference_reviews(record,predictions)

    def test_measurement_cli_links_review_record_and_retains_prepared_corpus(self):
        record=reconcile_reference_reviews(*self.reviews())
        with tempfile.TemporaryDirectory() as folder:
            paths={name:Path(folder)/(name+'.json') for name in ('record','predictions','measurements','prepared')}
            paths['record'].write_text(json.dumps(record));paths['predictions'].write_text(json.dumps(self.predictions()))
            script=Path(__file__).resolve().parents[2]/'scripts/evaluate_financial_extraction.py'
            run=subprocess.run([sys.executable,str(script),str(paths['predictions']),'--review-record',str(paths['record']),
                '--output',str(paths['measurements']),'--prepared-corpus',str(paths['prepared'])],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            report=json.loads(paths['measurements'].read_text())
            self.assertEqual(report['reference_review_sha256'],record['review_record_sha256'])
            self.assertEqual(report['layers'][0]['row_recall']['numerator'],1)
            self.assertEqual(json.loads(paths['prepared'].read_text())['label_status'],'synthetic_test')
