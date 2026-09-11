import hashlib
import io
import json
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
from services.financial.export_comparison import compare_ledger_exports, read_verified_ledger_archive
from services.financial.ledger_summary import LedgerSummaryError


class ExportComparisonTests(unittest.TestCase):
    def document(self):
        return dict(schema='loupe.financial.ledger_snapshot/3', export_ready=True,
            ledger=dict(case_id='case', account_id=None, start_date=None, end_date=None, included_classes=['p1'],
                readings=[dict(row=dict(key='stable-row', amount_minor='9007199254740993', currency='GBP'), source={'id':'source'})]),
            decisions=[], pdf_review_history={}, export_context={'generated_at':'first'})

    def archive(self, document=None, *, manifest_changes=None, report=b'<p>Captured report</p>', extra=None):
        document = document if document is not None else self.document()
        raw = json.dumps(document).encode()
        digest = hashlib.sha256(raw).hexdigest()
        manifest = dict(schema='loupe.financial.ledger_export_manifest/1', digest_covers='ledger_snapshot_json_utf8',
            document_sha256=digest, byte_count=len(raw), case_id=document['ledger']['case_id'], snapshot_schema=document['schema'],
            report=dict(filename='ledger-report.html', sha256=hashlib.sha256(report).hexdigest(), byte_count=len(report), derived_from_sha256=digest))
        manifest.update(manifest_changes or {})
        target = io.BytesIO()
        with ZipFile(target, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            archive.writestr('ledger-snapshot.json', raw)
            archive.writestr('ledger-report.html', report)
            if extra: archive.writestr(*extra)
        return target.getvalue()

    def test_same_data_and_preparation_only_changes_are_distinguished(self):
        before = self.archive()
        self.assertEqual(compare_ledger_exports(before, before)['status'], 'same_captured_content')
        changed = self.document();changed['export_context']['generated_at'] = 'later'
        result = compare_ledger_exports(before, self.archive(changed))
        self.assertEqual(result['status'], 'same_captured_content')
        self.assertTrue(result['export_preparation_changed'])
        self.assertTrue(result['packaging_or_generation_changed'])
        self.assertFalse(result['readings']['changed'])

    def support_archive(self, *, support_changes=None):
        document = self.document()
        digest = hashlib.sha256(json.dumps(document).encode()).hexdigest()
        support = dict(schema_version='loupe.financial.expert_support/1', case_id='case', derived_from_sha256=digest)
        support.update(support_changes or {})
        content = json.dumps(support, indent=2).encode()
        entry = dict(filename='expert-support.json', sha256=hashlib.sha256(content).hexdigest(),
                     byte_count=len(content), derived_from_sha256=digest)
        return self.archive(document, manifest_changes={'expert_support': entry}, extra=('expert-support.json', content)), content

    def test_saved_support_bytes_retained_and_bound_to_snapshot(self):
        archive, support = self.support_archive()
        self.assertEqual(read_verified_ledger_archive(archive)['expert_support_content'], support)
        self.assertIsNone(read_verified_ledger_archive(self.archive())['expert_support_content'])
        for change in ({'case_id': 'another-case'}, {'derived_from_sha256': '0' * 64}, {'schema_version': 'unknown'}):
            with self.subTest(change=change):
                archive, _ = self.support_archive(support_changes=change)
                with self.assertRaises(LedgerSummaryError):
                    read_verified_ledger_archive(archive)

    def test_exact_reading_fields_and_review_additions_are_identified(self):
        changed = self.document();changed['ledger']['readings'][0]['row']['amount_minor'] = '9007199254740994'
        changed['pdf_review_history']['reviews'] = [{'id':'new-review', 'reason':'Synthetic correction'}]
        result = compare_ledger_exports(self.archive(), self.archive(changed))
        self.assertEqual(result['status'], 'captured_content_changed')
        self.assertEqual(result['readings']['changed'], [{'id':'stable-row', 'changed_paths':['/row/amount_minor'], 'changed_path_count':1, 'paths_truncated':False}])
        self.assertEqual(result['pdf_review_history']['reviews']['added'], ['new-review'])

    def test_filter_change_is_not_reported_as_an_unqualified_data_change(self):
        changed = self.document();changed['ledger']['start_date'] = '2026-01-01';changed['ledger']['readings'] = []
        result = compare_ledger_exports(self.archive(), self.archive(changed))
        self.assertEqual(result['status'], 'scope_changed')
        self.assertEqual(result['readings']['removed'], ['stable-row'])
        self.assertTrue(result['scope']['changed'])

    def test_other_cases_ambiguous_ids_and_unlisted_files_are_refused(self):
        changed = self.document();changed['ledger']['case_id'] = 'other'
        with self.assertRaises(LedgerSummaryError): compare_ledger_exports(self.archive(), self.archive(changed))
        changed = self.document();changed['ledger']['readings'] *= 2
        with self.assertRaises(LedgerSummaryError): compare_ledger_exports(self.archive(), self.archive(changed))
        for extra in (('unlisted.txt', b'not listed'), ('../escape', b'no'), ('ledger-report.html', b'duplicate')):
            with self.assertRaises(LedgerSummaryError): read_verified_ledger_archive(self.archive(extra=extra))

    def test_wrong_snapshot_or_report_digest_is_refused(self):
        for change in ({'document_sha256':'a'*64}, {'byte_count':True}, {'report':dict(filename='ledger-report.html', sha256='a'*64, byte_count=22, derived_from_sha256='b'*64)}):
            with self.assertRaises(LedgerSummaryError): read_verified_ledger_archive(self.archive(manifest_changes=change))
