import copy
import unittest

from services.financial.expert_support import build_expert_support
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.pdf_candidates import _digest


class ExpertStatementSupportTests(unittest.TestCase):
    def document(self):
        original = {'rows': [{'date': '2026-01-02', 'amount_minor': '100'}]}
        confirmation = {'rows': [{'date': '2026-01-02', 'amount_minor': '200', 'reason': 'Checked PDF'}]}
        return {'ledger': {'case_id': 'case', 'readings': []},
                'processing_provenance': {'statement_import_history': [{
                    'source_document_id': 'source', 'evidence_file_id': 'file',
                    'original': original, 'original_sha256': _digest(original),
                    'confirmation': confirmation, 'confirmation_sha256': _digest(confirmation)}],
                    'custody_reports': [{'events': [{'id': 'receipt'}]}]}}

    def test_new_import_is_visible_without_legacy_pdf_mapping(self):
        document = self.document()
        before = copy.deepcopy(document)
        support = build_expert_support(document, snapshot_sha256='snapshot')
        self.assertEqual(support['extraction_and_review']['status'], 'captured_statement_import_scope')
        record = support['extraction_and_review']['statement_imports']['records'][0]
        self.assertEqual(record['snapshot_reference'], 'processing_provenance.statement_import_history[0]')
        self.assertEqual(support['human_decisions']['statement_import_confirmations'], 1)
        self.assertEqual(support['source_records']['source_custody_reports'], document['processing_provenance']['custody_reports'])
        self.assertEqual(document, before)

    def test_changed_original_or_confirmation_is_refused(self):
        for field in ('original', 'confirmation'):
            with self.subTest(field=field):
                document = self.document()
                document['processing_provenance']['statement_import_history'][0][field]['rows'][0]['amount_minor'] = '999'
                with self.assertRaisesRegex(LedgerSummaryError, 'recorded digest'):
                    build_expert_support(document, snapshot_sha256='snapshot')

    def test_missing_historical_digest_stays_unknown(self):
        document = self.document()
        document['processing_provenance']['statement_import_history'][0]['original_sha256'] = None
        support = build_expert_support(document, snapshot_sha256='snapshot')
        self.assertIsNone(support['extraction_and_review']['statement_imports']['records'][0]['original_sha256'])

    def test_old_capture_does_not_claim_zero_confirmations(self):
        support = build_expert_support({'ledger': {'case_id': 'case', 'readings': []}}, snapshot_sha256='snapshot')
        self.assertNotIn('statement_import_confirmations', support['human_decisions'])
