"""Automatic reread selection for generic labelled statements; synthetic cells only."""
import unittest

from services.financial.statement_reading_quality import (assess_statement_reading, labelled_statement,
    prefer_image_reading, sources_from_tables)

HEADER = ['Bank: Example Synthetic Bank', 'Account Name: Example Holder LLC', 'Account Number: 11112222',
          'Currency: USD', 'Statement Period: March 1, 2023 - March 31, 2023']
PAYMENTS = [('2023-03-03', 'Incoming transfer A', 'credit', '1,280.00', '15,556.17'),
            ('2023-03-08', 'Card purchase B', 'debit', '85.13', '15,471.04'),
            ('2023-03-13', 'Utility debit C', 'debit', '143.20', '15,327.84')]


def cell(x, y, text, *, right=False):
    width = max(10, int(len(text) * 3.5))
    left = x - width if right else x
    return dict(text=text, locator=dict(kind='page_rectangle', page=1, rect=[left * 1000, y * 1000,
        (left + width) * 1000, (y + 10) * 1000], page_size=[600000, 800000], units='millipoints',
        space='pdf_displayed'))


def statement(header=None, payments=None, *, opening='14,276.17', closing='15,327.84', split_period=False):
    """One text-aligned table as the native reader and the image reader both produce it."""
    lines = []
    for text in HEADER if header is None else header:
        if split_period and text.startswith('Statement Period'):
            first, second = text.split(' - ')
            lines.append([cell(40, 0, first), cell(160, 0, '- ' + second)])
        else:
            lines.append([cell(40, 0, text)])
    lines.append([cell(40, 0, 'Date'), cell(120, 0, 'Description'), cell(380, 0, 'Credit', right=True),
                  cell(460, 0, 'Debit', right=True), cell(560, 0, 'Balance', right=True)])
    lines.append([cell(40, 0, '2023-03-01'), cell(120, 0, 'Opening Balance'), cell(560, 0, opening, right=True)])
    for day, description, direction, amount, balance in PAYMENTS if payments is None else payments:
        lines.append([cell(40, 0, day), cell(120, 0, description),
                      cell(380 if direction == 'credit' else 460, 0, amount, right=True),
                      cell(560, 0, balance, right=True)])
    lines.append([cell(40, 0, '2023-03-31'), cell(120, 0, 'Closing Balance'), cell(560, 0, closing, right=True)])
    values = []
    for row, cells in enumerate(lines):
        y = 40 + row * 14
        for column, item in enumerate(cells):
            rect = item['locator']['rect']
            values.append(dict(row=row, column=column, text=item['text'],
                locator={**item['locator'], 'rect': [rect[0], y * 1000, rect[2], (y + 10) * 1000]}))
    return [dict(table_source='text_alignment', geometry_source='cell_rectangles',
                 table=dict(page=1, values=values))]


def payments_with(index, **changes):
    rows = [list(p) for p in PAYMENTS]
    for position, key in enumerate(('day', 'description', 'direction', 'amount', 'balance')):
        if key in changes:
            rows[index][position] = changes[key]
    return [tuple(r) for r in rows]


class GenericReadingQualityTests(unittest.TestCase):
    def test_clean_page_is_assessed_with_every_printed_header_fact(self):
        quality = assess_statement_reading(statement())
        self.assertEqual(quality['identity'], ['generic-labelled', 'Example Synthetic Bank', 'Example Holder LLC',
                                               '11112222', 'USD', '2023-03-01', '2023-03-31'])
        self.assertEqual((quality['payments'], quality['balances'], quality['unreadable']), (3, 2, 0))

    def test_damaged_amount_or_balance_requests_reread_and_accepts_the_image_reading(self):
        clean = assess_statement_reading(statement(split_period=True))
        for damaged in (payments_with(1, amount='8S.13'), payments_with(2, balance='15,3Z7.84')):
            with self.subTest(damaged=damaged):
                before = assess_statement_reading(statement(payments=damaged))
                self.assertGreater(before['unreadable'], 0)
                self.assertTrue(prefer_image_reading(before, clean))
        before = assess_statement_reading(statement(opening='14,Z76.17'))
        self.assertEqual(before['missing_fields']['statement_balance'], 1)
        self.assertTrue(prefer_image_reading(before, clean))

    def test_image_reading_that_changes_any_header_fact_is_refused(self):
        before = assess_statement_reading(statement(payments=payments_with(1, amount='8S.13')))
        for index, text in ((0, 'Bank: Another Synthetic Bank'), (1, 'Account Name: Another Holder'),
                            (2, 'Account Number: 11112228'), (3, 'Currency: EUR'),
                            (4, 'Statement Period: March 1, 2023 - March 30, 2023')):
            with self.subTest(text=text):
                header = list(HEADER)
                header[index] = text
                self.assertFalse(prefer_image_reading(before, assess_statement_reading(statement(header=header))))

    def test_page_without_its_own_account_or_period_is_not_assessed(self):
        for index in (2, 4):
            with self.subTest(index=index):
                header = [text for i, text in enumerate(HEADER) if i != index]
                self.assertIsNone(assess_statement_reading(statement(header=header)))
        header = list(HEADER)
        header[4] = 'Statement Period: unreadable'
        self.assertIsNone(assess_statement_reading(statement(header=header)))
        # Labelled lines with no payments table beneath them are not a statement page.
        sources = sources_from_tables(statement())
        sources[0]['rows'] = sources[0]['rows'][:len(HEADER)]
        self.assertIsNone(labelled_statement(sources))

    def test_repair_cannot_change_another_readable_payment_or_the_row_count(self):
        before = assess_statement_reading(statement(payments=payments_with(1, amount='8S.13')))
        for candidate in (payments_with(0, amount='1,230.00'), payments_with(2, description='Utility debit D'),
                          payments_with(2, day='2023-03-14'), payments_with(0, balance='15,556.71'),
                          PAYMENTS[:2], PAYMENTS + [('2023-03-20', 'Unprinted E', 'debit', '1.00', '15,326.84')]):
            with self.subTest(candidate=candidate):
                self.assertFalse(prefer_image_reading(before, assess_statement_reading(statement(payments=candidate))))

    def test_valid_complete_values_are_never_replaced_to_make_arithmetic_fit(self):
        clean = assess_statement_reading(statement())
        changed = assess_statement_reading(statement(payments=payments_with(1, amount='88.13')))
        self.assertEqual(changed['unreadable'], 0)
        self.assertFalse(prefer_image_reading(clean, changed))
        self.assertFalse(prefer_image_reading(changed, clean))

    def test_image_row_that_fits_no_printed_column_counts_as_an_unreadable_payment(self):
        before = assess_statement_reading(statement(payments=payments_with(1, amount='8S.13')))
        table = statement()
        # An image reading that merges one amount across the credit and debit
        # columns: no printed layout can place it.
        for value in table[0]['table']['values']:
            if value['text'] == '85.13':
                rect = value['locator']['rect']
                value['locator']['rect'] = [300000, rect[1], 470000, rect[3]]
        after = assess_statement_reading(table)
        self.assertEqual(after['payments'], 3)
        self.assertGreater(after['unreadable'], 0)
        self.assertFalse(prefer_image_reading(before, after))


if __name__ == '__main__':
    unittest.main()
