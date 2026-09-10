import hashlib
import io
import json
import unittest
import zipfile
from unittest.mock import patch

from tests import test_financial_trace_replay as scenario_fixture
from tests import test_financial_extraction_evaluation as corpus_fixture
from services.financial.trace_support_archive import build_trace_support_archive, verify_trace_support_archive
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
        self.assertEqual(verify_trace_support_archive(content)['status'], 'verified_bytes_matching_rebuild')
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

    def review_inputs(self):
        from services.financial.reference_reviews import reconcile_reference_reviews
        corpus = corpus_fixture.ExtractionEvaluationTests().corpus()
        first = dict(schema_version='loupe.extraction_reader_review/1', corpus_id=corpus['corpus_id'],
            corpus_version=corpus['corpus_version'], review_id='first', reviewer_id='reader-a',
            label_status='synthetic_test', documents=[dict(source_sha256=d['source_sha256'],
                complete_source_reviewed=True, rows=d['truth']) for d in corpus['documents']])
        second = {**first, 'review_id':'second', 'reviewer_id':'reader-b'}
        record = reconcile_reference_reviews(first, second)
        predictions = dict(schema_version='loupe.extraction_predictions/1', corpus_id=corpus['corpus_id'],
            corpus_version=corpus['corpus_version'], documents=[{k:v for k,v in d.items() if k != 'truth'} for d in corpus['documents']])
        return record, predictions

    def test_reference_evidence_retained_and_linked_from_each_expert_index(self):
        record, predictions = self.review_inputs()
        content = build_trace_support_archive([self.f.content], reference_review=record, validation_predictions=predictions)
        self.assertEqual(verify_trace_support_archive(content)['status'], 'verified_bytes_matching_rebuild')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(json.loads(archive.read('validation/reference-review.json')), record)
            self.assertEqual(json.loads(archive.read('validation/predictions.json')), predictions)
            support = json.loads(archive.read('scenarios/01/expert-support.json'))
            self.assertEqual({key:value for key,value in support['validation'].items() if key != 'source_overlap'}, manifest['validation'])
            self.assertEqual(support['validation']['label_status'], 'synthetic_test')
            self.assertEqual(support['validation']['reference_review_sha256'], record['review_record_sha256'])
            for entry in manifest['files']:
                self.assertEqual(hashlib.sha256(archive.read(entry['filename'])).hexdigest(), entry['sha256'])

    def test_reference_tampering_and_ambiguous_inputs_refused(self):
        record, predictions = self.review_inputs()
        with self.assertRaises(ValueError):
            build_trace_support_archive([self.f.content], reference_review=record)
        with self.assertRaises(ValueError):
            build_trace_support_archive([self.f.content], reference_review=record,
                validation_predictions=predictions, validation_corpus={})
        record['documents'][0]['truth'][0]['fields']['direction'] = 'debit'
        with self.assertRaisesRegex(ValueError, 'changed'):
            build_trace_support_archive([self.f.content], reference_review=record, validation_predictions=predictions)

    def test_source_overlap_does_not_infer_version_equivalence(self):
        from services.financial.trace_support_archive import validation_source_overlap
        corpus = corpus_fixture.ExtractionEvaluationTests().corpus()
        result = validation_source_overlap({'sources': [dict(sha256_at_ingestion='a'*64),
            dict(sha256_at_ingestion='b'*64), dict(sha256_at_ingestion=None)]}, corpus)
        self.assertEqual(result['matching_source_sha256'], ['a'*64])
        self.assertEqual(result['unmeasured_source_sha256'], ['b'*64])
        self.assertEqual(result['sources_without_digest'], 1)
        self.assertEqual(result['extraction_version_equivalence'], 'not_established')

    def test_saved_ledger_bytes_retained_with_separate_scope(self):
        from tests import test_financial_export_comparison as ledger_fixture
        fixture = ledger_fixture.ExportComparisonTests()
        document = fixture.document()
        document['ledger']['case_id'] = json.loads(self.f.content)['ledger_snapshot']['ledger']['case_id']
        original = fixture.archive(document)
        content = build_trace_support_archive([self.f.content], ledger_archive=original)
        self.assertEqual(verify_trace_support_archive(content)['status'], 'verified_bytes_matching_rebuild')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(archive.read('ledger/original-export.zip'), original)
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['captured_ledger']['archive_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(manifest['captured_ledger']['wider_case_history'], 'not_selected')
            self.assertIsNone(manifest['captured_ledger']['audit_verification'])
        document['ledger']['case_id'] = 'different-case'
        with self.assertRaisesRegex(ValueError, 'different case'):
            build_trace_support_archive([self.f.content], ledger_archive=fixture.archive(document))
        with self.assertRaises(ValueError):
            build_trace_support_archive([self.f.content], ledger_archive=fixture.archive(document, manifest_changes={'document_sha256':'b'*64}))

    def test_saved_ledger_chain_recomputed_before_attachment(self):
        from tests import test_financial_export_comparison as ledger_fixture
        from services.financial.audit_chain import verify_financial_audit_chain
        fixture = ledger_fixture.ExportComparisonTests()
        document = fixture.document()
        case_id = json.loads(self.f.content)['ledger_snapshot']['ledger']['case_id']
        document['ledger']['case_id'] = case_id
        document['case_financial_history'] = {'audit_chain': {'entries': [],
            'verification': verify_financial_audit_chain([], case_id=case_id)}}
        content = build_trace_support_archive([self.f.content], ledger_archive=fixture.archive(document))
        self.assertEqual(verify_trace_support_archive(content)['status'], 'verified_bytes_matching_rebuild')
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            captured = json.loads(archive.read('manifest.json'))['captured_ledger']
            self.assertEqual(captured['wider_case_history'], 'included')
            self.assertEqual(captured['audit_verification']['event_count'], 0)
        document['case_financial_history']['audit_chain']['verification']['event_count'] = 1
        with self.assertRaisesRegex(ValueError, 'summary differs'):
            build_trace_support_archive([self.f.content], ledger_archive=fixture.archive(document))

    def rewrite_archive(self, content, change):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        change(files)
        target = io.BytesIO()
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return target.getvalue()

    def test_verifier_refuses_missing_extra_changed_and_unsafe_members(self):
        content = build_trace_support_archive([self.f.content])
        for change in (lambda files: files.pop('scenarios/01/replay.json'),
                       lambda files: files.update({'extra.txt': b'unlisted'}),
                       lambda files: files.update({'../escape': b'unsafe'}),
                       lambda files: files.update({'scenarios/01/replay.json': b'{}'})):
            with self.assertRaises(ValueError):
                verify_trace_support_archive(self.rewrite_archive(content, change))
        with self.assertRaises(ValueError):
            verify_trace_support_archive(content, expected_sha256='0'*64)
        result = verify_trace_support_archive(content, expected_sha256=hashlib.sha256(content).hexdigest())
        self.assertEqual(result['checkpoint_status'], 'matches_supplied_digest')

    def test_rehashed_derived_content_is_reported_as_rebuild_difference(self):
        content = build_trace_support_archive([self.f.content])
        def change(files):
            name = 'scenarios/01/expert-support.json'
            support = json.loads(files[name]); support['completeness'] = 'invented-completeness-claim'
            files[name] = json.dumps(support).encode()
            manifest = json.loads(files['manifest.json'])
            for item in manifest['files']:
                if item['filename'] == name:
                    item.update(byte_count=len(files[name]), sha256=hashlib.sha256(files[name]).hexdigest())
            files['manifest.json'] = json.dumps(manifest).encode()
        result = verify_trace_support_archive(self.rewrite_archive(content, change))
        self.assertEqual(result['status'], 'verified_bytes_different_rebuild')
        self.assertEqual(result['changed_members'], ['scenarios/01/expert-support.json'])

    def test_verifier_refuses_duplicate_members_and_manifest_keys(self):
        content = build_trace_support_archive([self.f.content])
        target = io.BytesIO(content)
        with zipfile.ZipFile(target, 'a') as archive:
            archive.writestr('scenarios/01/replay.json', '{}')
        with self.assertRaises(ValueError):
            verify_trace_support_archive(target.getvalue())
        def change(files):
            files['manifest.json'] = b'{"case_id":"one","case_id":"two"}'
        with self.assertRaises(ValueError):
            verify_trace_support_archive(self.rewrite_archive(content, change))

    def test_changed_replay_code_version_is_explicit_without_false_calculation_failure(self):
        with patch('services.financial.version.code_version', return_value='captured-code'):
            content = build_trace_support_archive([self.f.content])
        with patch('services.financial.version.code_version', return_value='current-code'):
            result = verify_trace_support_archive(content)
        self.assertEqual(result['status'], 'verified_bytes_matching_calculations')
        self.assertEqual(result['changed_members'], [])
        self.assertEqual(result['replay_version_changes'], [dict(member='scenarios/01/replay.json',
            captured_replay_code_version='captured-code', current_replay_code_version='current-code')])

    def test_combined_archive_size_limit_is_enforced_on_build(self):
        with patch('services.financial.trace_support_archive.MAX_SUPPORT_ARCHIVE_BYTES', 10):
            with self.assertRaisesRegex(ValueError, 'Combined support'):
                build_trace_support_archive([self.f.content])

    def test_case_binding_is_checked_before_rebuild(self):
        content = build_trace_support_archive([self.f.content])
        with patch('services.financial.trace_support_archive.build_trace_support_archive') as rebuild:
            with self.assertRaises(ValueError):
                verify_trace_support_archive(content, expected_case_id='another-case')
        rebuild.assert_not_called()
