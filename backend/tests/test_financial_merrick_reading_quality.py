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

    def test_a_layer_that_cannot_read_the_statement_identity_is_replaced_by_an_image_reading_that_can(self):
        layer = clean_statement()
        layer['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25121'
        before, after = quality(layer), quality(clean_statement())
        self.assertIsNotNone(before)
        self.assertIs(before['identity_complete'], False)
        self.assertEqual(before['identity'][2], '')
        self.assertGreater(before['missing_fields']['identity'], 0)
        self.assertIs(after['identity_complete'], True)
        self.assertTrue(prefer_image_reading(before, after))

    def test_identity_recovery_needs_a_complete_agreeing_identity_and_fewer_unreadable_fields(self):
        layer = clean_statement()
        layer['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25121'
        before = quality(layer)
        for index, text in ((1, 'Account Number: 5555 6666 7777 8888'),   # the account the layer did read differs
                            (0, 'Statement Date: 04/25l21')):           # the image cannot read the date either
            candidate = clean_statement()
            candidate['rows'][index]['cells'][0]['expected_text'] = text
            self.assertFalse(prefer_image_reading(before, quality(candidate)))
        # Two readings that both miss the identity never match on their empty parts.
        self.assertFalse(prefer_image_reading(before, quality(deepcopy(layer))))
        # A native cell repair of such a page (the identity still unread) is never preferred.
        repaired = deepcopy(layer)
        damaged = deepcopy(layer)
        damaged['rows'][6]['cells'][3]['expected_text'] = '1O.00'
        self.assertFalse(prefer_image_reading(quality(damaged), quality(repaired)))

    def test_a_card_page_whose_layer_reads_no_summary_balance_takes_an_image_reading_that_reads_both(self):
        from services.financial.statement_reading_quality import _card_summary_recovered
        identity = ['merrick-card', '4111 1111 1111 1111', '2021-04-25']
        layer = dict(identity=identity, balances=0, unreadable=3, identity_complete=True)
        image = dict(identity=identity, balances=2, unreadable=1, identity_complete=True)
        self.assertTrue(_card_summary_recovered(layer, image))
        self.assertFalse(_card_summary_recovered(dict(layer, balances=1), image))       # the layer read a balance
        self.assertFalse(_card_summary_recovered(layer, dict(image, balances=1)))       # the image reads only one
        self.assertFalse(_card_summary_recovered(dict(layer, unreadable=0), image))     # the layer reading is complete
        self.assertFalse(_card_summary_recovered(layer, dict(image, unreadable=3)))     # not fewer unreadable fields
        self.assertFalse(_card_summary_recovered(layer, dict(image, identity=identity[:2] + ['2021-04-26'])))
        other = ['andrews-share-statement', '123', '2021-04-01', '2021-04-30', '1']
        self.assertFalse(_card_summary_recovered(dict(layer, identity=other), dict(image, identity=other)))


if __name__ == '__main__':
    unittest.main()
