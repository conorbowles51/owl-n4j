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

    def test_per_page_proposal_retains_columns_without_writes(self):
        result=self.scan(auto_columns=True,date_column=None,amount_column=None)
        self.assertTrue(result['auto_columns']);self.assertIsNone(result['date_column'])
        self.assertEqual(result['pages'][0]['chosen_columns']['date_column'],0)
        self.assertEqual(result['pages'][0]['chosen_columns']['amount_column'],1)
        self.assertEqual(result['suggested_rows'],2)
        self.assertFalse(self.f.db.new or self.f.db.dirty)

    def test_column_ties_remain_unchecked_and_exact_headers_can_resolve_them(self):
        from services.financial.candidate_page_scan import propose_scan_columns
        def row(i,*values):return dict(row_index=i,cells=[dict(column_index=n,expected_text=t) for n,t in enumerate(values)])
        source=dict(rows=[row(0,'2026-01-01','10.00','100.00'),row(1,'2026-01-02','20.00','120.00')])
        choice,reason=propose_scan_columns(source,'GBP');self.assertIsNone(choice);self.assertIn('equal support',reason)
        source['rows'].insert(0,row(2,'Date','Amount','Balance'))
        choice,reason=propose_scan_columns(source,'GBP');self.assertIsNone(reason);self.assertEqual(choice['amount_column'],1)
        self.assertEqual(choice['header_support'],2)

    def test_undated_charge_labels_preserve_exact_cells_and_unknown_date(self):
        from services.financial.candidate_page_scan import suggest_undated_charges
        def row(i,*values):return dict(row_index=i,cells=[dict(column_index=n,expected_text=t,locator={'page':1}) for n,t in enumerate(values)])
        source=dict(rows=[row(0,'Interest Charge on Purchases','$56.16'),row(1,'Total Interest for This Period','$56.16'),row(2,'Purchases','9.90%','$6679.78','$56.16'),row(3,'Late fee','2026-01-01','$10.00'),row(4,'Annual Fee','$20.00','$30.00')])
        hints=suggest_undated_charges(source,'USD')
        self.assertEqual([h['row_index'] for h in hints],[0,4])
        self.assertEqual(hints[0]['amount_sources'][0],source['rows'][0]['cells'][1])
        self.assertTrue(hints[0]['date_unknown'])
        self.assertEqual(len(hints[1]['amount_sources']),2)
        self.assertIn('no amount or date is selected',hints[1]['reason'])

    def test_undated_screen_survives_unavailable_dated_columns(self):
        from services.financial.candidate_page_scan import suggest_undated_charges
        with patch('services.financial.candidate_page_scan.propose_scan_columns',return_value=(None,'No dates')), patch('services.financial.candidate_page_scan.suggest_undated_charges',return_value=[{'row_index':0}]):
            result=self.scan(auto_columns=True,date_column=None,amount_column=None)
            self.assertFalse(result['pages'][0]['checked'])
            self.assertEqual(result['undated_charge_rows'],1)
            self.assertEqual(result['pages'][0]['undated_checked_rows'],2)
            with patch('services.financial.candidate_page_scan.MAX_SUGGESTED_ROWS',0):
                with self.assertRaises(PdfMappingError):self.scan(auto_columns=True,date_column=None,amount_column=None)

    def test_separate_labelled_amount_columns_preserve_both_source_cells(self):
        from copy import deepcopy
        payload=deepcopy(self.f.payload)
        values=[('Date','Money out','Money in'),('2026-01-01','20.00',''),('2026-01-02','','30.00'),('2026-01-03','0.00','40.00')]
        payload[0]['table']['values']=[dict(row=r,column=c,text=text,locator=fixture.rectangle(20+r*20,x=20+c*50)) for r,row in enumerate(values) for c,text in enumerate(row) if text]
        self.f.update_geometry(payload)
        result=self.scan(auto_columns=True,date_column=None,amount_column=None,end_page=1)
        page=result['pages'][0]
        self.assertEqual(page['chosen_columns']['additional_amount_columns'],[2])
        self.assertEqual([(r['row_index'],r['amount_source']['column_index']) for r in page['suggestions']],[(1,1),(2,2),(3,1),(3,2)])
        self.assertEqual([r['amount_header_source']['expected_text'] for r in page['suggestions']],['Money out','Money in','Money out','Money in'])
        self.assertEqual(page['suggestions'][0]['amount_header_source']['locator'],payload[0]['table']['values'][1]['locator'])
        self.assertEqual(result['suggested_rows'],4)
        self.assertNotIn('direction',page['suggestions'][0])
        self.assertFalse(self.f.db.new or self.f.db.dirty)

    def test_conflicting_split_header_positions_are_not_chosen(self):
        from services.financial.candidate_page_scan import propose_scan_columns
        rows=[('Date','Debit','Credit'),('Date','Credit','Debit'),('2026-01-01','10.00','20.00')]
        source={'rows':[dict(row_index=i,cells=[dict(column_index=c,expected_text=t) for c,t in enumerate(row)]) for i,row in enumerate(rows)]}
        chosen,reason=propose_scan_columns(source,'GBP')
        self.assertIsNone(chosen);self.assertIn('conflicting positions',reason)
