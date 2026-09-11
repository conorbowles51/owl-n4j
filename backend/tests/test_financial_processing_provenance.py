import unittest
from uuid import UUID, uuid4
from services.financial.processing_provenance import capture_processing_provenance
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import capture_ledger_snapshot
from postgres.models.financial import FinancialIngestionRun
from tests import test_financial_ledger_summary as fixture
import json

class ProcessingProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.LedgerSummaryTests();self.f.setUp()
        self.row,self.doc=self.f.add()
        self.readings=json.loads(capture_ledger_snapshot(self.f.db,case_id=self.f.case.id).content)['ledger']['readings']
    def tearDown(self):self.f.tearDown()
    def capture(self,**changes):return capture_processing_provenance(self.f.db,**{**dict(case_id=self.f.case.id,readings=self.readings),**changes})
    def test_recorded_versions_and_nulls_are_preserved_without_runtime_substitution(self):
        run=self.f.db.get(FinancialIngestionRun,self.doc.ingestion_run_id)
        run.code_version='historic-code';run.ruleset_version=None
        run.config={'secret':'do not export'};run.error='private error';self.f.db.commit()
        captured=self.capture()
        self.assertEqual(captured['runs'][0]['code_version'],'historic-code')
        self.assertIsNone(captured['runs'][0]['ruleset_version'])
        self.assertNotIn('secret',json.dumps(captured));self.assertNotIn('private error',json.dumps(captured))
        self.assertNotIn('stored_path',json.dumps(captured))
        self.assertEqual(captured['source_documents'][0]['parser_version'],self.doc.parser_version)
        self.assertFalse(self.f.db.new or self.f.db.dirty)
    def test_cross_case_and_missing_runs_are_refused(self):
        with self.assertRaises(LedgerSummaryError):self.capture(case_id=self.f.other_case.id)
        self.readings[0]['row']['ingestion_run_id']=str(uuid4())
        with self.assertRaises(LedgerSummaryError):self.capture()
    def test_multiple_readings_deduplicate_sources_and_runs(self):
        self.readings*=3
        result=self.capture()
        self.assertEqual(len(result['runs']),1);self.assertEqual(len(result['source_documents']),1)
    def test_empty_scope_has_no_invented_history(self):
        result=self.capture(readings=[])
        self.assertEqual(result['runs'],[]);self.assertEqual(result['evidence_registrations'],[])

    def test_statement_review_originals_and_confirmation_are_bound_to_their_digests(self):
        from services.financial.pdf_candidates import _digest
        original={'rows':[{'kind':'header','excluded':True}], 'sources':[]}
        confirmation={'rows':[], 'reason':'Reviewed source'}
        self.doc.metadata_={**self.doc.metadata_, 'statement_import_original':original,
            'statement_import_original_sha256':_digest(original),'statement_import_request':confirmation,
            'statement_import_request_sha256':_digest(confirmation)}
        self.f.db.commit()
        history=self.capture()['statement_import_history']
        self.assertEqual(history[0]['original'],original)
        self.doc.metadata_={**self.doc.metadata_,'statement_import_original':{'rows':[]}}
        self.f.db.commit()
        with self.assertRaises(LedgerSummaryError):self.capture()
