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

    def test_decimal_amount_that_also_looks_like_a_date_is_not_silently_lost(self):
        from services.financial.candidate_page_scan import suggest_undated_charges
        def row(i, *texts):
            return dict(row_index=i, cells=[dict(column_index=n, expected_text=t, locator={'page':4}) for n,t in enumerate(texts)])
        source = dict(rows=[row(0, 'Interest Charge on Purchases', '11.18'),
                           row(1, '09/25', 'Interest Charge on Purchases', '11.18'),
                           row(2, '09.25', 'Interest Charge on Purchases', '11.18')])
        hints = suggest_undated_charges(source, 'USD')
        self.assertEqual([h['row_index'] for h in hints], [0, 2])
        self.assertEqual(hints[0]['amount_sources'], [source['rows'][0]['cells'][1]])
        self.assertEqual(len(hints[1]['amount_sources']), 2)
        self.assertTrue(all(h['date_unknown'] for h in hints))
        self.assertIn('no amount or date is selected', hints[1]['reason'])

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

    def test_withdrawal_deposit_headers_preserve_both_columns_without_admission(self):
        from copy import deepcopy
        for debit, credit in (('Withdrawals', 'Deposits'), ('Withdrawal', 'Deposit')):
            with self.subTest(headers=(debit, credit)):
                payload = deepcopy(self.f.payload)
                values = [('Date', debit, credit), ('2026-01-01', '20.00', ''),
                          ('2026-01-02', '', '30.00'), ('2026-01-03', '0.00', '40.00')]
                payload[0]['table']['values'] = [dict(row=r, column=c, text=text,
                    locator=fixture.rectangle(20+r*20, x=20+c*50))
                    for r,row in enumerate(values) for c,text in enumerate(row) if text]
                self.f.update_geometry(payload)
                page = self.scan(auto_columns=True, date_column=None, amount_column=None, end_page=1)['pages'][0]
                self.assertEqual([(r['row_index'], r['amount_source']['column_index'])
                    for r in page['suggestions']], [(1,1), (2,2), (3,1), (3,2)])
                self.assertEqual([r['amount_header_source']['expected_text'] for r in page['suggestions']],
                    [debit, credit, debit, credit])
                self.assertTrue(all('direction' not in row for row in page['suggestions']))
                self.assertFalse(self.f.db.new or self.f.db.dirty)

    def test_deposit_summary_labels_are_not_paired_headers(self):
        from services.financial.candidate_page_scan import propose_scan_columns
        for labels in (('Total withdrawals', 'Total deposits'), ('Withdrawal balance', 'Deposit balance')):
            source = {'rows': [dict(row_index=i, cells=[dict(column_index=c, expected_text=t)
                for c,t in enumerate(row)]) for i,row in enumerate([
                    ('Date', *labels), ('2026-01-01', '10.00', '20.00')])]}
            chosen, reason = propose_scan_columns(source, 'GBP')
            self.assertIsNone(chosen)
            self.assertTrue(reason)

    def test_conflicting_split_header_positions_are_not_chosen(self):
        from services.financial.candidate_page_scan import propose_scan_columns
        rows=[('Date','Debit','Credit'),('Date','Credit','Debit'),('2026-01-01','10.00','20.00')]
        source={'rows':[dict(row_index=i,cells=[dict(column_index=c,expected_text=t) for c,t in enumerate(row)]) for i,row in enumerate(rows)]}
        chosen,reason=propose_scan_columns(source,'GBP')
        self.assertIsNone(chosen);self.assertIn('conflicting positions',reason)

    def test_exact_transaction_section_keeps_summary_rows_out_of_automatic_nomination(self):
        from copy import deepcopy
        payload = deepcopy(self.f.payload)
        values = [('2026-01-01', '10.00'), ('Transactions', ''),
                  ('Date', 'Amount'), ('2026-01-02', '20.00'),
                  ('Interest Charge on Purchases', '11.18'),
                  ('2026 Totals Year-to-Date', ''), ('2026-01-03', '99.00')]
        payload[0]['table']['values'] = [dict(row=r, column=c, text=text,
            locator=fixture.rectangle(20+r*20,x=20+c*50))
            for r,row in enumerate(values) for c,text in enumerate(row) if text]
        self.f.update_geometry(payload)
        page = self.scan(auto_columns=True,date_column=None,amount_column=None,end_page=1)['pages'][0]
        self.assertEqual([r['row_index'] for r in page['suggestions']], [3])
        self.assertEqual([r['row_index'] for r in page['undated_charges']], [4])
        self.assertEqual(page['checked_rows'], 3)
        self.assertEqual(page['source_section']['omitted_rows'], 4)
        self.assertEqual(page['source_section']['start_source']['expected_text'], 'Transactions')
        manual = self.scan(end_page=1)['pages'][0]
        self.assertIsNone(manual['source_section'])
        self.assertEqual([r['row_index'] for r in manual['suggestions']], [0,3,6])

    def test_ambiguous_or_unbounded_sections_do_not_silently_hide_rows(self):
        from services.financial.candidate_page_scan import _transaction_section
        def source(labels):
            return dict(rows=[dict(row_index=i,cells=[dict(column_index=0,expected_text=t)]) for i,t in enumerate(labels)])
        for labels in [('Transactions', 'date'), ('Transactions','Transactions','date','Totals Year-to-Date'),
                       ('Transactions','date','Totals Year-to-Date','Totals Year-to-Date')]:
            original = source(labels)
            selected, section = _transaction_section(original)
            self.assertIs(selected, original)
            self.assertIsNone(section)

    def test_shifted_amount_positions_require_measured_shared_header(self):
        from copy import deepcopy
        from services.financial.candidate_page_scan import propose_scan_columns
        def cell(column, text, x, y, page=1):
            return dict(column_index=column, expected_text=text, locator={
                'kind':'page_rectangle','page':page,'rect':[x,y,x+10000,y+5000],
                'page_size':[612000,792000],'units':'millipoints','space':'pdf_displayed'})
        source = dict(rows=[dict(row_index=0,cells=[cell(0,'Date',10000,10000),cell(2,'Amount',480000,10000)]),
            *[dict(row_index=i,cells=[cell(0,f'2026-01-0{i}',10000,10000+i*10000),
                cell(3 if i < 3 else 2, f'{i*10}.00',480000,10000+i*10000)]) for i in range(1,5)]])
        choice, reason = propose_scan_columns(source,'GBP')
        self.assertIsNone(reason)
        self.assertEqual(choice['amount_column'],2)
        self.assertEqual(choice['additional_amount_columns'],[3])
        self.assertEqual(choice['supporting_rows'],4)
        self.assertEqual(choice['alignment_source'],source['rows'][0]['cells'][1])
        for change in ('missing','wrong_page','misaligned','above','invalid'):
            broken = deepcopy(source)
            value = broken['rows'][1]['cells'][1]
            if change == 'missing': value.pop('locator')
            elif change == 'wrong_page': value['locator']['page'] = 2
            elif change == 'misaligned': value['locator']['rect'] = [500000,20000,510000,25000]
            elif change == 'above': value['locator']['rect'] = [480000,0,490000,5000]
            else: value['locator']['rect'] = [1,2]
            with self.subTest(change=change):
                choice, _ = propose_scan_columns(broken,'GBP')
                self.assertNotIn('additional_amount_columns',choice)
        conflicting = deepcopy(source)
        for row in conflicting['rows'][1:]:
            row['cells'].append(cell(1,row['cells'][0]['expected_text'],100000,20000))
        conflicting['rows'][0]['cells'].append(cell(1,'Date',100000,10000))
        choice, reason = propose_scan_columns(conflicting,'GBP')
        self.assertIsNone(choice)
        self.assertIn('equal support',reason)

    def test_shifted_scan_keeps_both_positions_with_measured_sources(self):
        from copy import deepcopy
        payload = deepcopy(self.f.payload)
        values = [(0,0,'Date',20,20),(0,2,'Amount',140,20),
                  (1,0,'2026-01-01',20,40),(1,3,'14.00',140,40),
                  (2,0,'2026-01-02',20,60),(2,3,'100.00',140,60),
                  (3,0,'2026-01-03',20,80),(3,2,'0.00',140,80),
                  (4,0,'2026-01-04',20,100),(4,2,'0.00',140,100)]
        payload[0]['table']['values'] = [dict(row=r,column=c,text=t,locator=fixture.rectangle(y,x=x)) for r,c,t,x,y in values]
        self.f.update_geometry(payload)
        page = self.scan(auto_columns=True,end_page=1)['pages'][0]
        self.assertEqual([r['amount_source']['expected_text'] for r in page['suggestions']], ['14.00','100.00','0.00','0.00'])
        self.assertEqual(page['chosen_columns']['additional_amount_columns'],[3])
        self.assertTrue(all(r['amount_source']['locator']['kind']=='page_rectangle' for r in page['suggestions']))
        self.assertFalse(self.f.db.new or self.f.db.dirty)
