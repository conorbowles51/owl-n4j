"""Pinned crop repair on generic running-balance statements; synthetic cells only.

Rows of the synthetic page: 0-4 labelled header lines, 5 column headings,
6 opening balance (balance in column 2), 7-9 payments (amount column 2,
running balance column 3), 10 closing balance (column 2).
"""
import unittest

from services.financial.statement_reading_quality import pinned_running_balance_values
from tests.test_financial_generic_reading_quality import PAYMENTS, payments_with, statement


class GenericPinnedRepairTests(unittest.TestCase):
    def test_contradicted_amount_fixed_by_two_agreed_balances_is_accepted(self):
        held = statement(payments=payments_with(0, amount='1,2?0.00'))
        accepted = pinned_running_balance_values(held, {(0, 7, 2): '1,280.00'})
        self.assertEqual(accepted, {(0, 7, 2): dict(text='1,280.00', pinned_by=[[0, 6, 2], [0, 7, 3]])})

    def test_opening_running_and_closing_balances_can_each_be_pinned(self):
        for table, key, text in ((statement(opening='14,2?6.17'), (0, 6, 2), '14,276.17'),
                                 (statement(payments=payments_with(1, balance='15,4?1.04')), (0, 8, 3), '15,471.04'),
                                 (statement(closing='15,3?7.84'), (0, 10, 2), '15,327.84')):
            with self.subTest(key=key):
                self.assertEqual(pinned_running_balance_values(table, {key: text})[key]['text'], text)

    def test_crop_value_that_does_not_reconcile_is_refused(self):
        held = statement(payments=payments_with(0, amount='1,2?0.00'))
        self.assertEqual(pinned_running_balance_values(held, {(0, 7, 2): '1,230.00'}), {})

    def test_compensating_misreads_fixed_only_jointly_stay_held(self):
        # A purchase, its running balance and the next purchase all disputed:
        # two equations, three unknowns. Every value reconciles, none is pinned.
        held = statement(payments=[PAYMENTS[0], ('2023-03-08', 'Card purchase B', 'debit', '8?.13', '15,4?1.04'),
                                   ('2023-03-13', 'Utility debit C', 'debit', '14?.20', '15,327.84')])
        disputed = {(0, 8, 2): '85.13', (0, 8, 3): '15,471.04', (0, 9, 2): '143.20'}
        self.assertEqual(pinned_running_balance_values(held, disputed), {})
        # The same two cancelling amounts with their own balances agreed are each pinned.
        held = statement(payments=[PAYMENTS[0], ('2023-03-08', 'Card purchase B', 'debit', '8?.13', '15,471.04'),
                                   ('2023-03-13', 'Utility debit C', 'debit', '14?.20', '15,327.84')])
        self.assertEqual(set(pinned_running_balance_values(held, {(0, 8, 2): '85.13', (0, 9, 2): '143.20'})),
                         {(0, 8, 2), (0, 9, 2)})

    def test_one_unpinned_cell_leaves_every_cell_held(self):
        held = statement(payments=[('2023-03-03', 'Incoming transfer A', 'credit', '1,2?0.00', '15,556.17'),
                                   ('2023-03-08', 'Card purchase B', 'debit', '8?.13', '15,4?1.04'),
                                   ('2023-03-13', 'Utility debit C', 'debit', '14?.20', '15,327.84')])
        disputed = {(0, 7, 2): '1,280.00', (0, 8, 2): '85.13', (0, 8, 3): '15,471.04', (0, 9, 2): '143.20'}
        self.assertEqual(pinned_running_balance_values(held, disputed), {})

    def test_pages_without_a_complete_agreed_chain_are_refused(self):
        key, text = (0, 7, 2), '1,280.00'
        held = payments_with(0, amount='1,2?0.00')
        no_balances = [(day, description, direction, amount, '') for day, description, direction, amount, _ in held]
        header = ['Bank: Example Synthetic Bank', 'Statement Period: March 1, 2023 - March 31, 2023']
        for name, table in (('no running balances', statement(payments=no_balances)),
                            ('no closing balance', statement(payments=held, closing='')),
                            ('no printed account', statement(header=header, payments=held))):
            with self.subTest(name):
                self.assertEqual(pinned_running_balance_values(table, {key: text}), {})
        two_tables = statement(payments=held) + statement()
        self.assertEqual(pinned_running_balance_values(two_tables, {key: text}), {})

    def test_disputed_cell_outside_the_balance_chain_is_refused(self):
        held = statement(payments=payments_with(0, amount='1,2?0.00'))
        self.assertEqual(pinned_running_balance_values(held, {(0, 7, 2): '1,280.00', (0, 3, 0): '1.00'}), {})


if __name__ == '__main__':
    unittest.main()
