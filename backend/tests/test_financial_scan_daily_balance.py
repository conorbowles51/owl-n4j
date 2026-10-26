"""A scanned M&T period whose scan misread a month's figure or lost an amount's figure (scan_daily_balance)."""
import unittest
from unittest import mock

from services.financial import scan_daily_balance as scan
from services.financial import statement_engine

# Left and right edges of the printed columns (page units), as the layout prints them.
DESCRIPTION = (47, 400)
CREDIT, DEBIT, BALANCE = (600, 650), (750, 792), (880, 933)


def cell(index, text, edges):
    return dict(column_index=index, expected_text=text, locator=dict(rect=[edges[0], 0, edges[1], 10]))


def row(page, index, cells, kind='header', fields=None):
    return dict(id='%d:0:%d' % (page, index), page_number=page, table_index=0, row_index=index, source_revision='r',
                source_cells=cells, fields=fields or {}, issues=[], excluded=kind != 'unresolved', kind=kind)


def line(page, index, text, credit=None, debit=None, balance=None, kind='unresolved'):
    cells = [cell(0, text, DESCRIPTION)]
    for value, edges in ((credit, CREDIT), (debit, DEBIT), (balance, BALANCE)):
        if value is not None:
            cells.append(cell(len(cells), value, edges))
    return row(page, index, cells, kind=kind)


def heading(page, index):
    return row(page, index, [cell(0, 'DATE', (61, 95)), cell(1, 'CREDITS (+)', (561, 637)),
                             cell(2, 'OTHER DEBITS (-)', (684, 797)), cell(3, 'BALANCE', (851, 914))])


def statement(period=('2024-10-09', '2024-11-08'), rent='?00.00', rent_balance='1,050.00', summary=None, **extra):
    summary = summary or ['$1,000.00', '1', '$500.00', '0', '$0.00', '4', '$455.00', '$0.01', '$1,045.01']
    rows = [
        row(1, 7, [cell(0, 'BEGINNING BALANCE', (50, 200)), cell(1, '$1,000.00', (300, 360))], kind='balance',
            fields=dict(description='Opening Balance', balance='100000')),
        row(1, 14, [cell(0, 'ENDING BALANCE', (50, 200)), cell(1, '$1,045.01', (300, 360))], kind='balance',
            fields=dict(description='Closing Balance', balance='104501')),
        row(1, 22, [cell(i, text, (40 + 100 * i, 90 + 100 * i)) for i, text in enumerate(summary)]),
        heading(1, 26),
        line(1, 27, '10/09/2024 | BEGINNING BALANCE', balance='$1,000.00', kind='header'),
        line(1, 28, '10/11/2024 | SHOP ONE', debit='20.00'),
        line(1, 29, 'CITY ST', kind='header'),
        line(1, 30, '10/11/2024 | SHOP TWO', debit='30.00', balance='950.00'),
        line(1, 31, '11/01/2024 | PAYROLL', credit='$500.00', balance='1,450.00'),
        line(1, 32, '41/05/2024 | RENT', debit=rent, balance=rent_balance, kind='header'),
        line(1, 33, '41/08/2024 | INTEREST PAYMENT', credit='0.01', kind='header'),
        row(1, 34, [cell(0, 'PAGE 1 OF 2', (800, 900))]),
        row(2, 3, [cell(0, 'ACCOUNT NUMBER', (50, 200))]),
        heading(2, 10),
        line(2, 11, '11/08/2024 | FEE', debit='5.00', balance='1,045.01'),
        row(2, 13, [cell(0, 'ENDING BALANCE', (50, 200)), cell(1, '$1,045.01', (880, 933))]),
    ]
    data = dict(id='this', period_start=period[0], period_end=period[1], currency='USD',
                balance_convention='asset_balance', engine_profile='mt-bank',
                engine=dict(proved=False, reason='not_reconciled'), _rows=rows)
    data.update(extra)
    return data


class ScanDailyBalanceTests(unittest.TestCase):
    def test_the_period_is_read_from_its_printed_columns_when_every_figure_agrees(self):
        rows = scan.scan_rows(statement(), 'USD')
        self.assertIsNotNone(rows, scan.LAST_REFUSAL)
        moves = [(r['fields']['date'], r['fields']['direction'], r['fields']['amount_minor'])
                 for r in rows if r['kind'] == 'transaction']
        self.assertEqual(moves, [('2024-10-11', 'debit', '2000'), ('2024-10-11', 'debit', '3000'),
                                 ('2024-11-01', 'credit', '50000'), ('2024-11-05', 'debit', '40000'),
                                 ('2024-11-08', 'credit', '1'), ('2024-11-08', 'debit', '500')])
        rent = next(r for r in rows if r['id'] == '1:0:32')
        self.assertEqual((rent['fields']['date_basis'], rent['fields']['amount_basis']),
                         (scan.DATE_BASIS, scan.AMOUNT_BASIS))
        first = next(r for r in rows if r['id'] == '1:0:28')
        self.assertEqual(first['fields']['description'], 'SHOP ONE CITY ST')
        self.assertFalse(any(r['issues'] for r in rows))

    def test_the_general_reader_returns_it_for_the_held_period(self):
        held = statement()
        with mock.patch.object(statement_engine, 'read_statements', return_value=[held]):
            rows = statement_engine.propose_engine_statement([], 'USD', dict(id='this'))['rows']
        self.assertEqual(sum(r['kind'] == 'transaction' for r in rows), 6)

    def test_a_daily_balance_that_differs_holds_the_period(self):
        self.assertIsNone(scan.scan_rows(statement(rent='400.00', rent_balance='1,051.00'), 'USD'))
        self.assertEqual(scan.LAST_REFUSAL['step'], 'daily_balance')

    def test_a_figure_the_balance_does_not_fix_holds_the_period(self):
        self.assertIsNone(scan.scan_rows(statement(rent='?10.00'), 'USD'))
        self.assertEqual(scan.LAST_REFUSAL['step'], 'unread_figure_not_fixed')

    def test_two_unread_figures_between_balances_hold_the_period(self):
        held = statement()
        for row_id, text in (('1:0:28', '2?.00'), ('1:0:30', '3?.00')):  # both before one printed balance
            next(r for r in held['_rows'] if r['id'] == row_id)['source_cells'][1]['expected_text'] = text
        self.assertIsNone(scan.scan_rows(held, 'USD'))
        self.assertEqual(scan.LAST_REFUSAL['step'], 'several_unread_figures')

    def test_a_month_the_period_does_not_fix_holds_the_period(self):
        self.assertIsNone(scan.scan_rows(statement(period=('2024-01-01', '2024-11-08')), 'USD'))
        self.assertEqual(scan.LAST_REFUSAL['step'], 'date_unread')

    def test_summary_counts_or_totals_that_differ_hold_the_period(self):
        summary = ['$1,000.00', '2', '$500.00', '0', '$0.00', '4', '$455.00', '$0.01', '$1,045.01']
        self.assertIsNone(scan.scan_rows(statement(summary=summary), 'USD'))
        self.assertEqual(scan.LAST_REFUSAL['step'], 'summary_counts')

    def test_a_line_with_two_amounts_holds_the_period(self):
        held = statement()
        shop = next(r for r in held['_rows'] if r['id'] == '1:0:28')
        shop['source_cells'].append(cell(2, '20.00', CREDIT))
        self.assertIsNone(scan.scan_rows(held, 'USD'))
        self.assertEqual(scan.LAST_REFUSAL['step'], 'line_amounts')

    def test_another_hold_another_layout_or_switch_off_leaves_the_held_reading(self):
        self.assertIsNone(scan.scan_rows(statement(engine=dict(proved=False, reason='principal_only_balance')), 'USD'))
        self.assertIsNone(scan.scan_rows(statement(engine_profile='other'), 'USD'))
        with mock.patch.object(scan, 'ENABLED', False):
            self.assertIsNone(scan.scan_rows(statement(), 'USD'))


if __name__ == '__main__':
    unittest.main()
