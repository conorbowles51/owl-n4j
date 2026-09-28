"""Automatic reread selection with synthetic source cells; no saved corrections."""
import unittest
from copy import deepcopy

from services.financial.statement_reading_quality import assess_statement_reading, prefer_image_reading
from tests.test_financial_statement_import_merrick import measured_statement


def clean_statement():
    data = measured_statement()
    data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25/21'
    return data


def quality(data):
    return assess_statement_reading([dict(table=dict(page=data['page_number'], values=[
        dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
        for r in data['rows'] for c in r['cells']]))])


class MerrickReadingQualityTests(unittest.TestCase):
    def test_damaged_amount_or_date_requests_reread_and_accepts_source_candidate(self):
        clean = clean_statement()
        for column, text in ((3, '1O.00'), (0, 'O4/22')):
            with self.subTest(column=column):
                damaged = deepcopy(clean)
                damaged['rows'][6]['cells'][column]['expected_text'] = text
                before, after = quality(damaged), quality(clean)
                self.assertGreater(before['unreadable'], 0)
                self.assertEqual(after['unreadable'], 0)
                self.assertTrue(prefer_image_reading(before, after))
                self.assertEqual(damaged['rows'][6]['cells'][column]['expected_text'], text)

    def test_repair_cannot_change_another_readable_payment(self):
        damaged = clean_statement()
        damaged['rows'][6]['cells'][3]['expected_text'] = '1O.00'
        before = quality(damaged)
        for column, text in ((3, '101.00'), (0, '04/24'), (2, 'ANOTHER SHOP')):
            with self.subTest(column=column):
                candidate = clean_statement()
                candidate['rows'][7]['cells'][column]['expected_text'] = text
                self.assertFalse(prefer_image_reading(before, quality(candidate)))

    def test_identity_loss_changes_and_payment_omission_are_rejected(self):
        damaged = clean_statement()
        damaged['rows'][6]['cells'][3]['expected_text'] = '1O.00'
        for index, text in ((1, 'Account Number: unreadable'),
                            (1, 'Account Number: 5555 6666 7777 8888'),
                            (0, 'Statement Date: unreadable'),
                            (0, 'Statement Date: 04/26/21')):
            candidate = clean_statement()
            candidate['rows'][index]['cells'][0]['expected_text'] = text
            self.assertFalse(prefer_image_reading(quality(damaged), quality(candidate)))
        candidate = clean_statement()
        candidate['rows'].pop(7)
        self.assertFalse(prefer_image_reading(quality(damaged), quality(candidate)))

    def test_complete_values_are_not_replaced_to_make_arithmetic_fit(self):
        data = clean_statement()
        self.assertEqual(quality(data)['unreadable'], 0)
        candidate = deepcopy(data)
        candidate['rows'][6]['cells'][3]['expected_text'] = '15.00'
        self.assertFalse(prefer_image_reading(quality(data), quality(candidate)))


if __name__ == '__main__':
    unittest.main()
