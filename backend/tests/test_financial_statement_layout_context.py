import unittest
from copy import deepcopy
from services.financial.statement_layout_context import statement_layout_context

class LayoutContextTests(unittest.TestCase):
    def source(self):
        texts=[('Platinum MasterCard Account Ending in 3539',),
          ('May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle',),
          ('Visit www.capitalone.com to see detailed transactions.',),
          ('PERSON #3539: Payments, Credits and Adjustments',),('Date','Description','Amount'),
          ('May 30','PAYMENT','- $180.00'),('PERSON #8441: Transactions',),('Date','Description','Amount'),
          ('May 29','SHOP','$61.62'),('PERSON #8441: Total','$61.62'),
          ('Interest Charged',),('Interest Charge on Purchases','$56.16')]
        return [dict(row_index=i,cells=[dict(column_index=j,expected_text=t,locator={'kind':'page','page':3}) for j,t in enumerate(row)]) for i,row in enumerate(texts)]
    def test_exact_profile_preserves_distinct_card_sections_and_dates(self):
        source=self.source(); result=statement_layout_context(source)
        self.assertEqual(result['version'],1)
        self.assertEqual([(r['row_index'],r['card_ending'],r['date_proposals']) for r in result['rows']],[(5,'3539',['2020-05-30']),(8,'8441',['2020-05-29'])])
        self.assertEqual(result['rows'][0]['amount_source']['expected_text'],'- $180.00')
        self.assertEqual(result['rows'][0]['section_source']['locator'],source[3]['cells'][0]['locator'])
        self.assertTrue(all(r['direction'] is None and r['requires_source_review'] for r in result['rows']))
        self.assertFalse(result['applied'])
        self.assertEqual(result,statement_layout_context(deepcopy(source)))
    def test_ambiguous_cycles_wrong_brand_and_invalid_calendar_are_unmatched(self):
        for mode in ('duplicate','brand','calendar','length','ocr'):
            source=self.source()
            if mode=='duplicate':source.append(deepcopy(source[1]))
            elif mode=='brand':source[2]['cells'][0]['expected_text']='Capital One maybe'
            elif mode=='calendar':source[1]['cells'][0]['expected_text']='Feb 30, 2020 - Mar 31, 2020 | 31 days in Billing Cycle'
            elif mode=='length':source[1]['cells'][0]['expected_text']='May 12, 2020 - Jun. 11, 2020 | 30 days in Billing Cycle'
            else:source[0]['cells'][0]['expected_text']='Platinum MasterCard Account Ending in 35O9'
            with self.subTest(mode=mode):self.assertIsNone(statement_layout_context(source))
    def test_year_boundary_and_out_of_cycle_dates_remain_explicit(self):
        source=self.source();source[1]['cells'][0]['expected_text']='Dec 12, 2020 - Jan. 11, 2021 | 31 days in Billing Cycle'
        source[5]['cells'][0]['expected_text']='Jan 03';source[8]['cells'][0]['expected_text']='Feb 01'
        rows=statement_layout_context(source)['rows']
        self.assertEqual(rows[0]['date_proposals'],['2021-01-03'])
        self.assertEqual(rows[1]['date_proposals'],[])
    def test_totals_and_unsupported_headers_do_not_supply_a_card_context(self):
        source=self.source();source[7]['cells'][0]['expected_text']='TransDfla'
        rows=statement_layout_context(source)['rows']
        self.assertEqual([r['row_index'] for r in rows],[5])

    def test_heading_before_the_confirmed_cycle_is_not_associated(self):
        rows=self.source();cycle=rows.pop(1);rows.append({**cycle,'row_index':99})
        self.assertEqual(statement_layout_context(rows)['rows'],[])

    def test_supported_later_card_headings_and_split_cycle_preserve_both_cells(self):
        for heading in ('Platinum Mastercard ending in 3539','Platinum Card ending in 8441','Platinum Card | Platinum Mastercard ending in 8441'):
            source=self.source();source[0]['cells'][0]['expected_text']=heading
            source[2]['cells'][0]['expected_text']='Visit capitalone.com to see detailed transactions.'
            source[1]['cells'][0]['expected_text']='May 12, 2020 - Jun. 11, 2020'
            source[1]['cells'].append({'column_index':1,'expected_text':'| 31 days in Billing Cycle','locator':{'kind':'page','page':3}})
            result=statement_layout_context(source)
            self.assertEqual(result['cycle_source']['expected_text'],'May 12, 2020 - Jun. 11, 2020')
            self.assertEqual(result['cycle_count_source']['expected_text'],'| 31 days in Billing Cycle')
            self.assertEqual(len(result['rows']),2)
            source[1]['cells'][1]['column_index']=3
            self.assertIsNone(statement_layout_context(source))

    def test_printed_transaction_and_posting_dates_remain_separate(self):
        source=self.source()
        source[4]['cells']=[dict(column_index=i,expected_text=t,locator={'kind':'page','page':3}) for i,t in enumerate(('Trans Date','Post Date','Description','Amount'))]
        source[5]['cells']=[dict(column_index=i,expected_text=t,locator={'kind':'page','page':3}) for i,t in enumerate(('May 29','May 30','PAYMENT','- $180.00'))]
        row=statement_layout_context(source)['rows'][0]
        self.assertEqual(row['date_label'],'Trans Date')
        self.assertEqual(row['date_proposals'],['2020-05-29'])
        self.assertEqual(row['posting_date_proposals'],['2020-05-30'])
        self.assertEqual(row['posting_date_source']['expected_text'],'May 30')
        self.assertEqual(row['date_header_source']['expected_text'],'Trans Date')
        self.assertEqual(row['posting_date_header_source']['expected_text'],'Post Date')
