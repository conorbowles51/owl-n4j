import json
from pathlib import Path
import tempfile
import unittest
from tests import test_financial_export_comparison as fixtures
from services.financial.audit_chain import verify_financial_audit_chain
from services.financial.audit_timestamp import checkpoint


class AuditTimestampCheckpointTests(unittest.TestCase):
    def document(self, case_id='00000000-0000-0000-0000-000000000001'):
        document = fixtures.ExportComparisonTests().document()
        document['ledger']['case_id'] = case_id
        document['case_financial_history'] = {'audit_chain': {'entries': [],
            'verification': verify_financial_audit_chain([], case_id=case_id)}}
        return document

    def captured(self, document):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'export.zip'
            archive.write_bytes(fixtures.ExportComparisonTests().archive(document))
            return checkpoint(archive)

    def test_empty_chains_still_bind_case_and_exact_export(self):
        first = json.loads(self.captured(self.document()))
        second = json.loads(self.captured(self.document('00000000-0000-0000-0000-000000000002')))
        self.assertEqual(first['head_sha256'], second['head_sha256'])
        self.assertNotEqual(first['snapshot_sha256'], second['snapshot_sha256'])
        self.assertNotEqual(first['archive_sha256'], second['archive_sha256'])
        self.assertNotEqual(first['case_id'], second['case_id'])

    def test_saved_summary_is_recomputed(self):
        document = self.document()
        document['case_financial_history']['audit_chain']['verification']['event_count'] = 1
        with self.assertRaisesRegex(ValueError, 'differs'):
            self.captured(document)

    def test_history_is_required(self):
        document = self.document()
        del document['case_financial_history']
        with self.assertRaisesRegex(ValueError, 'history'):
            self.captured(document)
