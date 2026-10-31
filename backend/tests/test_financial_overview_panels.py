"""The Overview's lower panels on the server: the browser's own calculations over the same ledger rows.

The equality with the browser's code over the six live cases is a gate run outside the suite; these tests pin the
behaviours that differ between Python and the browser unless written out (JavaScript's \\b, ??, ||, the final sort
of the money-in-then-out pairs) and the shape the page reads."""
import unittest

from services.financial.overview_panels import (money_connections, nearby_payments, overview_panels,
                                                payment_totals, unidentified_payment)

CASE = 'c1'


def row(key, **fields):
    base = {'key': key, 'case_id': CASE, 'account_id': 'acc-1', 'currency': 'MXN', 'direction': 'debit',
            'amount_minor': '100', 'ordering_date': '2025-01-02', 'row_index': 0}
    base.update(fields)
    return base


class PaymentTotalsTests(unittest.TestCase):
    def test_groups_in_the_order_first_met_with_unreadable_amounts_counted_apart(self):
        rows = [row('a', currency='USD', direction='credit', amount_minor='500'),
                row('b', account_type='credit_card', amount_minor='70', account_id='card'),
                row('c', direction='debit', amount_minor='200'),
                row('d', amount_minor='1.5'),
                row('e', amount_minor='-3')]
        totals = payment_totals(rows)
        self.assertEqual(totals['groups'], [
            {'group': 'USD:bank', 'credit': '500', 'debit': '0', 'count': 1, 'accounts': 1},
            {'group': 'MXN:card', 'credit': '0', 'debit': '70', 'count': 1, 'accounts': 1},
            {'group': 'MXN:bank', 'credit': '0', 'debit': '200', 'count': 1, 'accounts': 1}])
        self.assertEqual((totals['payments'], totals['unreadable']), (5, 2))

    def test_inventory_keeps_first_met_order_and_counts_unnamed_and_undated(self):
        rows = [row('a', account_label='Zeta', account_institution=' BBVA Bancomer ', to_name='Shop'),
                row('b', account_id='acc-2', account_label='Alpha', ordering_date=None, counterparty_raw='  '),
                row('c', account_id='acc-2', account_institution='bbva', ordering_date='2024-12-31',
                    to_name=None, counterparty_raw='Raw')]
        inventory = payment_totals(rows)['inventory']
        self.assertEqual([a['label'] for a in inventory['accounts']], ['Zeta', 'Alpha'])
        # "BBVA Bancomer" and "bbva" are one bank; the last spelling met is the one shown.
        self.assertEqual(inventory['banks'], ['bbva'])
        self.assertEqual((inventory['first'], inventory['last'], inventory['undated']), ('2024-12-31', '2025-01-02', 1))
        self.assertEqual((inventory['unknown_banks'], inventory['unidentified_counterparties']), (1, 1))


class UnidentifiedPaymentTests(unittest.TestCase):
    def test_a_named_or_linked_payment_is_not_unidentified(self):
        self.assertIsNone(unidentified_payment(row('a', to_name='Shop')))
        self.assertIsNone(unidentified_payment(row('a', to_name='', counterparty_link={'kind': 'party', 'id': 'p'})))

    def test_word_boundaries_are_ascii_as_in_the_browser(self):
        self.assertEqual(unidentified_payment(row('a', description='Pago IVA'))['kind'], 'tax')
        self.assertEqual(unidentified_payment(row('a', description='XIVA'))['kind'], 'unidentified')
        # Accents are removed first ("éIVA" reads "EIVA"); a letter outside ASCII is not a word character to the
        # browser's \b, so "ЖIVA" still has a boundary before IVA (Python's own \b would say it has none).
        self.assertEqual(unidentified_payment(row('a', description='éIVA'))['kind'], 'unidentified')
        self.assertEqual(unidentified_payment(row('a', description='ЖIVA'))['kind'], 'tax')
        self.assertEqual(unidentified_payment(row('a', description='SPEI ENVIADO'))['kind'], 'sent')

    def test_an_empty_name_from_review_and_a_stated_reason_come_first(self):
        cleared = row('a', label_sources={'to_name': {'source': 'investigator'}}, description='IVA')
        self.assertEqual(unidentified_payment(cleared)['kind'], 'cleared')
        missing = row('a', label_sources={'to_name': {'source': 'missing', 'reason': 'Not printed'}})
        self.assertEqual(unidentified_payment(missing), {'kind': 'reason:Not printed', 'label': 'Not printed',
                                                         'reason': 'Not printed'})


class ConnectionsTests(unittest.TestCase):
    def test_names_accounts_and_unnamed_payments_per_group_with_their_keys(self):
        rows = [row('a', direction='credit', from_name='Ana', amount_minor='300',
                    label_sources={'from_name': {'source': 'description'}}),
                row('b', to_name='Ana', amount_minor='100'),
                row('c', to_name=None, counterparty_raw=None, description='IVA', amount_minor='x')]
        group, = money_connections(rows)['groups']
        self.assertEqual(group['group'], 'MXN:bank')
        self.assertEqual((group['credit_total'], group['debit_total']), ('300', None))
        self.assertEqual(group['names'], [{'id': 'name:Ana', 'name': 'Ana',
                                           'credit': {'keys': ['a'], 'total': '300', 'suggested': True},
                                           'debit': {'keys': ['b'], 'total': '100', 'suggested': False}}])
        self.assertEqual(group['accounts'], [{'id': 'account:acc-1', 'name': 'Account name not recorded',
                                              'keys': ['a', 'b', 'c']}])
        self.assertEqual([(u['direction'], u['kind'], u['keys'], u['total']) for u in group['unnamed']],
                         [('debit', 'tax', ['c'], None)])


class NearbyPaymentsTests(unittest.TestCase):
    def test_pairs_are_listed_by_the_day_money_came_in_across_accounts(self):
        rows = [row('late-in', direction='credit', ordering_date='2025-02-01'),
                row('late-out', ordering_date='2025-02-03', row_index=1),
                row('early-in', account_id='acc-2', direction='credit', ordering_date='2025-01-01'),
                row('early-out', account_id='acc-2', ordering_date='2025-01-08', row_index=1),
                row('too-late-in', account_id='acc-3', direction='credit', ordering_date='2025-01-01'),
                row('too-late-out', account_id='acc-3', ordering_date='2025-01-09', row_index=1)]
        self.assertEqual(nearby_payments(rows), {'pairs': 2, 'keys': ['early-in', 'early-out', 'late-in', 'late-out']})

    def test_a_missing_row_position_counts_as_zero_as_in_the_browser(self):
        # Same day: the browser orders by row_index - row_index, where null is 0, so the null row comes first.
        # Comparing keys instead would put "a-out" first and find no pair.
        rows = [row('a-out', row_index=1), row('z-in', direction='credit', row_index=None)]
        self.assertEqual(nearby_payments(rows), {'pairs': 1, 'keys': ['z-in', 'a-out']})
        # A missing field is NaN to the browser: the keys decide.
        rows = [row('a-out', row_index=1), {k: v for k, v in row('z-in', direction='credit').items() if k != 'row_index'}]
        self.assertEqual(nearby_payments(rows), {'pairs': 0, 'keys': []})

    def test_cards_and_statement_end_dates_are_left_out(self):
        rows = [row('in', direction='credit', account_type='credit_card'), row('out', row_index=1),
                row('in2', account_id='b', direction='credit', ordering_date_context='statement_end_ordering_only'),
                row('out2', account_id='b', row_index=1)]
        self.assertEqual(nearby_payments(rows), {'pairs': 0, 'keys': []})


class OverviewPanelsTests(unittest.TestCase):
    def test_categories_restrict_the_rows_and_an_incomplete_answer_shows_nothing(self):
        rows = [row('a', category='Fees'), row('b', category=None)]
        panels = overview_panels(rows, CASE, ['Uncategorized'])
        self.assertEqual((panels['complete'], panels['totals']['payments']), (True, 1))
        other = overview_panels(rows, 'another case', [])
        self.assertEqual((other['complete'], other['totals']['payments'], other['connections']['groups']),
                         (False, 0, []))
        duplicate = overview_panels([row('a'), row('a')], CASE, [])
        self.assertFalse(duplicate['complete'])


if __name__ == '__main__':
    unittest.main()
