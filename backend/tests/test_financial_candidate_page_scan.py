import unittest
from uuid import uuid4
from unittest.mock import patch
from services.financial.candidate_page_scan import scan_candidate_pages
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_pdf_geometry_candidates as fixture

class PageScanTests(unittest.TestCase):
    def setUp(self):self.f=fixture.GridBindingTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def scan(self,**updates):
        return scan_candidate_pages(self.f.db,**{**dict(case_id=self.f.case,evidence_file_id=self.f.file,start_page=1,end_page=2,date_column=0,amount_column=1,currency='GBP'),**updates})
    def test_scan_retains_exact_suggestions_and_reports_missing_pages(self):
        result=self.scan()
        self.assertFalse(result['applied'])
        self.assertEqual(len(result['pages']),2)
        self.assertTrue(result['pages'][0]['checked'])
        self.assertEqual(result['pages'][0]['checked_rows'],2)
        self.assertFalse(result['pages'][1]['checked'])
        self.assertIn('not found',result['pages'][1]['reason'])
        self.assertEqual(result['suggested_rows'],2)
        self.assertEqual(result['pages'][0]['suggestions'][0]['amount_source']['expected_text'],'1234')
        self.assertFalse(self.f.db.new or self.f.db.dirty)
    def test_conflict_is_not_reported_as_an_unchecked_page(self):
        self.f.geometry.engine_job_id=uuid4();self.f.db.commit()
        with self.assertRaises(PdfMappingError) as caught:self.scan()
        self.assertEqual(caught.exception.status_code,409)
    def test_wrong_case_bad_columns_and_limits_refused(self):
        for updates in ({'case_id':uuid4()},{'end_page':51},{'date_column':1},{'currency':'???'}):
            with self.subTest(updates=updates),self.assertRaises(PdfMappingError):self.scan(**updates)
        with patch('services.financial.candidate_page_scan.MAX_SUGGESTED_ROWS',1):
            with self.assertRaises(PdfMappingError):self.scan()
