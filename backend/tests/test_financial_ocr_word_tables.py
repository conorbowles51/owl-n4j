import unittest
from services.financial.pdf_tables import read_positioned_ocr_words


class OcrWordTableTests(unittest.TestCase):
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

    def test_overlapping_ocr_tokens_share_one_union_while_adjacent_amounts_stay_separate(self):
        words=[(10,10,90,20,'Mark'),(35,10,45,20,'as'),(50,10,90,20,'Returned'),
               (10,40,40,50,'500.00'),(43,40,63,50,'0.00')]
        table=read_positioned_ocr_words(words,page_number=51,page_width=200,page_height=300)[0].to_json()
        self.assertEqual(table['geometry_source'],'cell_rectangles')
        values=table['table']['values']
        self.assertEqual([v['text'] for v in values],['Mark as Returned','500.00','0.00'])
        self.assertEqual(values[0]['locator']['rect'][::2],[10000,90000])
