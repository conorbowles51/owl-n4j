import unittest
from uuid import uuid4
from unittest.mock import patch
from services.financial.candidate_progress import candidate_document_progress
from services.financial.candidate_store import CandidateStoreError
from tests import test_financial_candidate_store as fixture

class DocumentProgressTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CandidateStoreTests()
        self.f.setUp()
    def tearDown(self):
        self.f.tearDown()
    def read(self, **changes):
        return candidate_document_progress(self.f.db, **{**dict(case_id=self.f.case, evidence_file_id=self.f.file), **changes})
    def test_unselected_page_and_saved_batch_resume(self):
        self.assertEqual(self.read()['pages'][0]['counts'], dict(pending=0, resolved=0, rejected=0))
        saved = self.f.save()
        result = self.read()
        self.assertEqual(result['counts']['pending'], 2)
        self.assertTrue(result['pages'][0]['prepared'])
        self.assertEqual(result['pages'][0]['batches'][0]['mapping_id'], saved['id'])
        self.assertEqual(result['pages'][0]['batches'][0]['next_pending_candidate_id'], saved['candidates'][0]['id'])
        self.assertFalse(self.f.db.new or self.f.db.dirty)
    def test_missing_internal_pages_visible(self):
        self.f.text.source_locations = [self.f.location, {**self.f.location, 'page_number': 3}]
        self.f.db.commit()
        result = self.read()
        self.assertEqual([p['page_number'] for p in result['pages']], [1, 2, 3])
        self.assertEqual([p['prepared'] for p in result['pages']], [True, False, False])
    def test_stale_geometry_not_prepared(self):
        self.f.geometry.engine_job_id = uuid4()
        self.f.db.commit()
        self.assertFalse(self.read()['pages'][0]['prepared'])
    def test_case_and_bounds_fail_closed(self):
        with self.assertRaises(CandidateStoreError) as caught: self.read(case_id=uuid4())
        self.assertEqual(caught.exception.status_code, 404)
        self.f.save()
        with patch('services.financial.candidate_progress.MAX_PROGRESS_READINGS', 1):
            with self.assertRaises(CandidateStoreError): self.read()
        with patch('services.financial.candidate_progress.MAX_PROGRESS_PAGES', 0):
            with self.assertRaises(CandidateStoreError): self.read()
