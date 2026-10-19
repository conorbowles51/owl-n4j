import unittest
from uuid import uuid4
from services.financial.candidate_assessment import candidate_source_readings
from services.financial.candidate_store import CandidateStoreError
from tests.test_financial_candidate_assessment import CandidateAssessmentTests

class CandidateSourceReadingTests(unittest.TestCase):
    def setUp(self):
        self.f = CandidateAssessmentTests(); self.f.setUp(); self.f.save()
    def tearDown(self): self.f.tearDown()
    def read(self, **kwargs):
        return candidate_source_readings(self.f.fixture.db, **{**dict(case_id=self.f.fixture.case,candidate_id=self.f.candidate_id),**kwargs})
    def test_all_original_cells_and_locations_without_numeric_assessment(self):
        result=self.read()
        self.assertEqual(result['evidence_file_id'],str(self.f.fixture.file))
        self.assertEqual(len(result['cells']),2)
        self.assertEqual(result['cells'][1]['text'],'1234')
        self.assertEqual(result['cells'][1]['locator']['rect'],[70000,20000,110000,30000])
        self.assertFalse(result['applied'])
        self.assertFalse(self.f.fixture.db.new or self.f.fixture.db.dirty)
    def test_cross_case_and_stale_source_refused(self):
        with self.assertRaises(CandidateStoreError): self.read(case_id=uuid4())
        self.f.fixture.text.content += ' changed'
        self.f.fixture.db.commit()
        with self.assertRaises(CandidateStoreError): self.read()
