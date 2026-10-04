"""An image reading may replace an embedded OCR layer only by adding the lines it left unread; synthetic data only.

The fixture is the synthetic benchmark page andrews-2020-12 (a scan whose
embedded OCR layer lost two printed payment lines of the checking section)
as the engine reads it twice: the embedded layer, and the full-page image
reading, plus the two bands where the image prints a line no embedded word
covers.
"""
import copy
import json
import unittest
from pathlib import Path

from services.financial.statement_reading_quality import assess_statement_reading, recovers_unread_lines

FIXTURE = json.loads((Path(__file__).parent / 'financial_unread_lines_fixture.json').read_text())


def reading(name, **texts):
    tables = copy.deepcopy(FIXTURE[name])
    for value in tables[0]['table']['values']:
        value['text'] = texts.get(f"r{value['row']}c{value['column']}", value['text'])
    return tables


def bands():
    return [tuple(b) for b in FIXTURE['unread_lines']]


class RecoversUnreadLinesTests(unittest.TestCase):
    def setUp(self):
        self.embedded = assess_statement_reading(reading('embedded'))

    def test_image_reading_that_adds_exactly_the_unread_lines_is_accepted(self):
        result = recovers_unread_lines(self.embedded, reading('image'), bands())
        self.assertEqual([(r['date'], r['amount_minor'], r['direction'], r['balance'], r['row_id']) for r in result['added']],
                         [('2020-12-07', '5000', 'credit', '235000', '1:0:14'),
                          ('2020-12-09', '5000', 'debit', '230000', '1:0:15')])
        self.assertEqual([tuple(r['band']) for r in result['added']], bands())

    def test_an_added_line_outside_every_unread_band_is_refused(self):
        self.assertIsNone(recovers_unread_lines(self.embedded, reading('image'), bands()[:1]))
        self.assertIsNone(recovers_unread_lines(self.embedded, reading('image'), []))
        shifted = [(top + 12, bottom + 12) for top, bottom in bands()]
        self.assertIsNone(recovers_unread_lines(self.embedded, reading('image'), shifted))

    def test_an_image_reading_that_changes_any_embedded_row_is_refused(self):
        for name, texts in (('amount', dict(r10c2='80.00')), ('running balance', dict(r11c3='730.69')),
                            ('description', dict(r10c1='Deposit Online Banking Transfer From Share 0041')),
                            ('ending balance', dict(r16c2='2,300.01'))):
            with self.subTest(name):
                self.assertIsNone(recovers_unread_lines(self.embedded, reading('image', **texts), bands()))

    def test_an_added_line_with_an_unreadable_field_is_refused(self):
        for texts in (dict(r14c2='5?.00'), dict(r15c3='2,3?0.00')):
            with self.subTest(texts=texts):
                self.assertIsNone(recovers_unread_lines(self.embedded, reading('image', **texts), bands()))

    def test_a_different_statement_or_no_added_payment_is_refused(self):
        self.assertIsNone(recovers_unread_lines(self.embedded, reading('image', r2c0='123456780'), bands()))
        self.assertIsNone(recovers_unread_lines(self.embedded, reading('embedded'), bands()))
        self.assertIsNone(recovers_unread_lines(None, reading('image'), bands()))

    def test_an_embedded_reading_with_unreadable_fields_is_not_assessed_here(self):
        damaged = assess_statement_reading(reading('embedded', r10c2='3?.00'))
        self.assertTrue(damaged['unreadable'])
        self.assertIsNone(recovers_unread_lines(damaged, reading('image'), bands()))


if __name__ == '__main__':
    unittest.main()
