import unittest
from services.financial.pdf_tables import read_positioned_ocr_words


class OcrWordTableTests(unittest.TestCase):
    def test_grouped_ocr_words_feed_the_statement_review_without_importing_headings(self):
        from services.financial.statement_import_catalog import statement_catalog
        from services.financial.statement_layout_context import statement_layout_context
        from services.financial.statement_import_card import propose_card_table
        lines = [
            [(10, 'Platinum MasterCard Account Ending in 1234')],
            [(10, 'May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle')],
            [(10, 'Visit www.capitalone.com to see detailed transactions.')],
            [(10, 'EXAMPLE HOLDER #1234: Payments, Credits and Adjustments')],
            [(10, 'Date'), (120, 'Description'), (380, 'Amount')],
            [(10, 'May 30'), (120, 'CARD PAYMENT'), (380, '- $180.00')],
            [(10, 'EXAMPLE HOLDER #1234: Transactions')],
            [(10, 'Date'), (120, 'Description'), (380, 'Amount')],
            [(10, 'May 29'), (120, 'EXAMPLE SHOP'), (380, '$61.62')],
            [(10, 'Total Transactions for This Period'), (380, '$61.62')],
            [(10, 'Interest Charged')],
            [(10, 'Interest Charge on Purchases'), (380, '$56.16')],
            [(10, 'Total Interest for This Period'), (380, '$56.16')],
        ]
        words = []
        for index, cells in enumerate(lines):
            for x, text in cells:
                for word in text.split():
                    width = len(word) * 4
                    words.append((x, 10 + index*20, x+width, 18 + index*20, word))
                    x += width + 2
        table = read_positioned_ocr_words(words, page_number=2, page_width=500, page_height=400)[0].to_json()
        rows = {}
        for value in table['table']['values']:
            row = rows.setdefault(value['row'], dict(row_index=value['row'], cells=[]))
            row['cells'].append(dict(column_index=value['column'], expected_text=value['text'], locator=value['locator']))
        source = dict(page_number=2, table_index=0, source_revision='a'*64, rows=list(rows.values()))
        source['layout_context'] = statement_layout_context(source['rows'])
        catalog = statement_catalog([source])
        self.assertEqual(len(catalog['statements']), 1)
        proposal = propose_card_table(source, 'USD', catalog['statements'][0])
        included = [r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual([r['fields']['amount_minor'] for r in included], ['18000', '6162', '5616'])
        self.assertEqual([r['fields']['direction'] for r in included], ['credit', 'debit', 'debit'])
        self.assertEqual(included[0]['fields']['date'], '2020-05-30')
        self.assertEqual(included[1]['fields']['description'], 'EXAMPLE SHOP')
        self.assertNotIn('date', included[2]['fields'])
        self.assertTrue(included[2]['issues'])

    def test_measured_words_preserve_text_and_displayed_page_locations(self):
        words=[(10,10,40,20,'Date'),(100,10,140,20,'Amount'),
               (10,40,60,50,'01/02'),(100,40,140,50,'12.34')]
        tables=read_positioned_ocr_words(words,page_number=51,page_width=200,page_height=300)
        self.assertEqual(len(tables),1)
        table=tables[0].to_json()
        self.assertEqual(table['table_source'],'text_alignment')
        values=table['table']['values']
        self.assertEqual([v['text'] for v in values],['Date','Amount','01/02','12.34'])
        self.assertTrue(all(v['locator']['page']==51 and v['locator']['space']=='pdf_displayed' for v in values))
        self.assertEqual(values[-1]['locator']['page_size'],[200000,300000])

    def test_bad_boxes_do_not_produce_partial_source_tables(self):
        for word in [(0,0,400,10,'outside'),(0,0,float('nan'),10,'nan'),(0,0,0,10,'empty')]:
            with self.subTest(word=word),self.assertRaises(ValueError):
                read_positioned_ocr_words([(0,0,10,10,'valid'),word],page_number=1,page_width=200,page_height=300)

    def test_single_line_does_not_invent_a_transaction_table(self):
        self.assertEqual(read_positioned_ocr_words([(10,10,40,20,'12.34')],page_number=1,page_width=200,page_height=300),())

    def test_ocr_phrases_and_dates_stay_together_without_joining_numeric_columns(self):
        words=[(10,10,42,20,'Previous'),(45,10,77,20,'Balance'),(150,10,185,20,'$0.00'),
               (10,40,27,50,'May'),(30,40,41,50,'30'),(100,40,123,50,'CARD'),(126,40,165,50,'PAYMENT'),
               (200,40,203,50,'-'),(206,40,245,50,'$180.00'),
               (10,70,32,80,'100'),(35,70,51,80,'20')]
        table=read_positioned_ocr_words(words,page_number=1,page_width=300,page_height=100)[0].to_json()
        values=table['table']['values']
        self.assertEqual([v['text'] for v in values],['Previous Balance','$0.00','May 30','CARD PAYMENT','- $180.00','100','20'])
        self.assertEqual(values[0]['locator']['rect'],[10000,10000,77000,20000])

    def test_overlapping_ocr_tokens_share_one_union_while_adjacent_amounts_stay_separate(self):
        words=[(10,10,90,20,'Mark'),(35,10,45,20,'as'),(50,10,90,20,'Returned'),
               (10,40,40,50,'500.00'),(43,40,63,50,'0.00')]
        table=read_positioned_ocr_words(words,page_number=51,page_width=200,page_height=300)[0].to_json()
        self.assertEqual(table['geometry_source'],'cell_rectangles')
        values=table['table']['values']
        self.assertEqual([v['text'] for v in values],['Mark as Returned','500.00','0.00'])
        self.assertEqual(values[0]['locator']['rect'][::2],[10000,90000])
