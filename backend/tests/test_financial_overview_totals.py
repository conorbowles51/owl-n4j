"""overview_totals: the Financial Overview's headline figures, the browser's calculation done on the server.

The frontend twin is InvestigatorOverview (before the server totals) over useInvestigatorPayments' rows; the
equality of the two on the six live cases is the release gate (fin-speed STATUS). These tests pin each rule."""
import unittest

from services.financial.overview_totals import amount, category_name, overview_totals, payment_day

CASE = 'c0ffee00-0000-0000-0000-000000000001'


def row(key, direction='debit', minor='100', currency='MXN', category='Fees', day='2025-01-02', account='a',
        context='transaction', case=CASE):
    return {'key': key, 'case_id': case, 'direction': direction, 'amount_minor': minor, 'currency': currency,
            'category': category, 'ordering_date': day, 'ordering_date_context': context, 'account_id': account}


class FigureRules(unittest.TestCase):
    def test_category_name_is_uncategorized_when_empty(self):
        self.assertEqual(category_name({'category': ''}), 'Uncategorized')
        self.assertEqual(category_name({'category': None}), 'Uncategorized')
        self.assertEqual(category_name({}), 'Uncategorized')
        self.assertEqual(category_name({'category': 'Fees'}), 'Fees')

    def test_payment_day_is_a_real_calendar_day_not_a_statement_end_only_date(self):
        self.assertEqual(payment_day({'ordering_date': '2025-02-28T10:00:00'}), '2025-02-28')
        self.assertIsNone(payment_day({'ordering_date': '2025-02-30'}))
        self.assertIsNone(payment_day({'ordering_date': '2025-2-3'}))
        self.assertIsNone(payment_day({'ordering_date': '٢٠٢٥-01-02'}))  # JavaScript's \\d is ASCII only
        self.assertIsNone(payment_day({'ordering_date': None}))
        self.assertIsNone(payment_day({'ordering_date': '2025-01-02',
                                       'ordering_date_context': 'statement_end_ordering_only'}))

    def test_amount_follows_bigint_and_counts_a_refused_value_as_zero(self):
        cases = {'12345': 12345, '-7': -7, '+7': 7, ' 42\n': 42, '': 0, '0x1f': 31, '12.5': 0, '1e3': 0,
                 '1_000': 0, '-0x5': 0, None: 0}
        for value, expected in cases.items():
            self.assertEqual(amount({'amount_minor': value}), expected, value)
        self.assertEqual(amount({'amount_minor': 9}), 9)


class OverviewTotals(unittest.TestCase):
    def test_every_figure_over_the_rows(self):
        rows = [
            row('1', 'credit', '500000', category='Transfers', day='2025-03-04'),
            row('2', 'debit', '120000', category='Uncategorized', day='2024-12-31', account='b'),
            row('3', 'debit', '1000', currency='USD', category=None, context='statement_end_ordering_only'),
            row('4', 'debit', 'bad', currency='USD', day='not a day'),
        ]
        self.assertEqual(overview_totals(rows, CASE, []), {
            'complete': True, 'categories': [], 'payments': 4, 'accounts': 2, 'unknown_dates': 1,
            'uncategorised': 2, 'first_day': '2024-12-31', 'last_day': '2025-03-04',
            'currencies': [{'currency': 'MXN', 'payments': 2, 'credit': '500000', 'debit': '120000'},
                           {'currency': 'USD', 'payments': 2, 'credit': '0', 'debit': '1000'}]})

    def test_only_the_chosen_categories_count_and_empty_choices_are_ignored(self):
        rows = [row('1', category='Fees'), row('2', category=None), row('3', category='Rent')]
        result = overview_totals(rows, CASE, ['Uncategorized', '', 'Fees', 'Fees'])
        self.assertEqual(result['categories'], ['Uncategorized', 'Fees'])
        self.assertEqual((result['payments'], result['uncategorised']), (2, 1))
        self.assertEqual(overview_totals(rows, CASE, [''])['payments'], 3)

    def test_an_incomplete_answer_counts_nothing_as_the_page_does(self):
        for rows in ([row('1'), row('1')], [row('1'), row('2', case='another-case')]):
            result = overview_totals(rows, CASE, [])
            self.assertFalse(result['complete'])
            self.assertEqual((result['payments'], result['currencies'], result['first_day']), (0, [], None))

    def test_no_rows(self):
        self.assertEqual(overview_totals([], CASE, []), {
            'complete': True, 'categories': [], 'payments': 0, 'accounts': 0, 'unknown_dates': 0,
            'uncategorised': 0, 'first_day': None, 'last_day': None, 'currencies': []})


if __name__ == '__main__':
    unittest.main()
