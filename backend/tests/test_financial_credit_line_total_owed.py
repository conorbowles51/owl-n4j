"""A checking line of credit printing its principal balance only is read in amounts owed (credit_line_total_owed)."""
import unittest
from unittest import mock

from services.financial import credit_line_total_owed as owed
from services.financial import statement_engine

# Right edges of the printed columns (page units), as the layout prints them.
EDGES = dict(label=146000, amount=288000, fee=345600, interest=403200, principal=489600, balance=597600)
HEADING = ['Date', 'Transaction Detail', 'Amount($)', 'Fee(s) ($)', 'Interest($)', 'Principal ($)', 'Balance ($)']
HEADING_EDGES = [31800, 111800, 288000, 345600, 403200, 489600, 597600]


def cell(index, text, right):
    return dict(column_index=index, expected_text=text, locator=dict(rect=[right - 20000, 0, right, 10]))


def row(page, index, cells, kind='header', fields=None, **extra):
    return dict(dict(id='%d:1:%d' % (page, index), page_number=page, table_index=1, row_index=index,
                     source_revision='r', source_cells=cells, fields=fields or {}, issues=[], excluded=kind != 'unresolved',
                     kind=kind), **extra)


def line(page, index, text, *values, kind='unresolved'):
    cells = [cell(0, text, EDGES['label'])] + [cell(i + 1, t, EDGES[c]) for i, (t, c) in enumerate(values)]
    return row(page, index, cells, kind=kind)


def summary(page, start, principal, interest, fees, total, limit='$4,000.00', available=None):
    labels = (('Credit Limit', limit), ('Outstanding Principal Balance', principal),
              ('Outstanding Interest Charge', interest), ('Outstanding Fees', fees),
              ('Total Outstanding Balance', total), ('Available Credit', available))
    rows = []
    for offset, (label, value) in enumerate(labels):
        if value is None and label == 'Available Credit':
            continue
        cells = [cell(0, label, 120000)] + ([cell(1, value, 172000)] if value is not None else [])
        rows.append(row(page, start + offset, cells))
    return rows


def statement(period, rows, reason='principal_only_balance', id_='this'):
    return dict(id=id_, period_start=period[0], period_end=period[1], currency='USD', balance_convention='liability_owed',
                engine=dict(proved=False, reason=reason), _rows=rows)


def held_period():
    """06/17/20 - 07/16/20: an advance, a payment split into interest and principal, an interest charge."""
    rows = summary(16, 16, '$3,225.69', '$36.84', '$0.00', '$3,262.53', available='$737.47') + [
        row(16, 23, [cell(i, t, e) for i, (t, e) in enumerate(zip(HEADING, HEADING_EDGES))]),
        line(16, 24, '06-17 Beginning Balance', ('3,236.27', 'balance'), kind='balance'),
        line(16, 25, '06-30 Chkg Line Of Credit Advance', ('16.68', 'amount'), ('16.68', 'principal'),
             ('3,252.95', 'balance')),
        line(16, 26, '07-03 Payment', ('65.49', 'amount'), ('38.23 -', 'interest'), ('27.26 -', 'principal'),
             ('3,225.69', 'balance')),
        line(16, 27, '07-16 Interest Charge', ('36.84', 'interest'), ('3,225.69', 'balance')),
        line(16, 28, '07-16 Ending Balance', ('3,225.69', 'balance'), kind='balance'),
        line(16, 30, 'Total fee(s) for this period', ('0.00', 'amount'), kind='header'),
    ]
    beginning = next(r for r in rows if r['id'] == '16:1:24')
    beginning['fields'] = dict(description='Opening Balance', balance='323627')
    rows.insert(rows.index(beginning) + 1, dict(beginning, id='16:1:24:engine_hold', kind='unresolved', excluded=False,
                                                engine_hold='principal_only_balance'))
    return statement(('2020-06-17', '2020-07-16'), rows)


def previous_period(total='$3,274.50', available='$725.50'):
    return statement(('2020-05-17', '2020-06-16'),
                     summary(11, 15, '$3,236.27', '$38.23', '$0.00', total, available=available), id_='before')


class CreditLineTotalOwedTests(unittest.TestCase):
    def read(self, this=None, before=None):
        this = this or held_period()
        return owed.recover_rows(this, [before or previous_period(), this], 'USD')

    def test_the_period_is_read_in_amounts_owed_when_every_printed_figure_agrees(self):
        rows = self.read()
        self.assertIsNotNone(rows, owed.LAST_REFUSAL)
        by_id = {r['id']: r for r in rows}
        self.assertFalse(any(r.get('engine_hold') for r in rows))
        opening, closing = by_id['16:1:24'], by_id['16:1:20']
        self.assertEqual((opening['kind'], opening['fields']['balance']), ('balance', '327450'))
        self.assertEqual(opening['fields']['balance_basis'], owed.OPENING_BASIS)
        self.assertEqual(opening['fields']['balance_derivation']['previous_amount_owed_minor'], '327450')
        self.assertEqual((closing['kind'], closing['fields']['description'], closing['fields']['balance']),
                         ('balance', 'Closing Balance', '326253'))
        self.assertEqual(by_id['16:1:28']['kind'], 'header')
        moves = [(r['fields']['date'], r['fields']['direction'], r['fields']['amount_minor'])
                 for r in rows if r['kind'] == 'transaction']
        self.assertEqual(moves, [('2020-06-30', 'debit', '1668'), ('2020-07-03', 'credit', '6549'),
                                 ('2020-07-16', 'debit', '3684')])
        self.assertTrue(all('balance' not in r['fields'] for r in rows if r['kind'] == 'transaction'))

    def test_the_general_reader_returns_it_for_the_held_period(self):
        this, before = held_period(), previous_period()
        with mock.patch.object(statement_engine, 'read_statements', return_value=[before, this]):
            rows = statement_engine.propose_engine_statement([], 'USD', dict(id='this'))['rows']
        self.assertFalse(any(r.get('engine_hold') for r in rows))
        self.assertEqual(sum(r['kind'] == 'transaction' for r in rows), 3)

    def test_an_unread_previous_total_is_taken_from_its_credit_limit_less_available_credit(self):
        rows = self.read(before=previous_period(total=None))
        self.assertIsNotNone(rows, owed.LAST_REFUSAL)
        derivation = next(r for r in rows if r['id'] == '16:1:24')['fields']['balance_derivation']
        self.assertEqual(derivation['previous_amount_owed_basis'], 'credit_limit_less_available_credit')

    def test_the_period_stays_held_when_the_statement_before_prints_another_amount_owed(self):
        self.assertIsNone(self.read(before=previous_period(total='$3,274.51')))
        self.assertEqual(owed.LAST_REFUSAL['step'], 'previous_amount_owed_differs')

    def test_the_period_stays_held_without_the_statement_before(self):
        this = held_period()
        self.assertIsNone(owed.recover_rows(this, [this], 'USD'))
        self.assertEqual(owed.LAST_REFUSAL['step'], 'previous_statement')

    def test_a_principal_part_that_does_not_chain_holds_the_period(self):
        this = held_period()
        payment = next(r for r in this['_rows'] if r['id'] == '16:1:26')
        payment['source_cells'][3]['expected_text'] = '27.62 -'
        self.assertIsNone(self.read(this))

    def test_a_payment_whose_parts_do_not_make_its_amount_holds_the_period(self):
        this = held_period()
        payment = next(r for r in this['_rows'] if r['id'] == '16:1:26')
        payment['source_cells'][1]['expected_text'] = '65.94'
        self.assertIsNone(self.read(this))
        self.assertEqual(owed.LAST_REFUSAL['step'], 'line_unexplained')

    def test_a_summary_that_does_not_add_up_holds_the_period(self):
        this = held_period()
        total = next(r for r in this['_rows'] if r['source_cells'][0]['expected_text'] == 'Total Outstanding Balance')
        total['source_cells'][1]['expected_text'] = '$3,262.35'
        self.assertIsNone(self.read(this))
        self.assertEqual(owed.LAST_REFUSAL['step'], 'summary_does_not_add_up')

    def test_a_fee_total_that_differs_from_the_fees_read_holds_the_period(self):
        this = held_period()
        fee_total = next(r for r in this['_rows'] if r['id'] == '16:1:30')
        fee_total['source_cells'][1]['expected_text'] = '5.00'
        self.assertIsNone(self.read(this))
        self.assertEqual(owed.LAST_REFUSAL['step'], 'fee_total_differs')

    def test_a_line_printed_over_two_lines_is_one_movement_with_its_effective_date(self):
        this = held_period()
        rows = this['_rows']
        index = next(i for i, r in enumerate(rows) if r['id'] == '16:1:26')
        rows[index] = line(16, 26, '07-03 Payment')
        rows.insert(index + 1, line(16, 29, 'Effective Date 07-01-20', ('65.49', 'amount'), ('38.23 -', 'interest'),
                                    ('27.26 -', 'principal'), ('3,225.69', 'balance'), kind='header'))
        result = self.read(this)
        self.assertIsNotNone(result, owed.LAST_REFUSAL)
        payment = next(r for r in result if r['id'] == '16:1:26')
        self.assertEqual((payment['fields']['amount_minor'], payment['fields']['value_date']), ('6549', '2020-07-01'))

    def test_another_hold_or_switch_off_leaves_the_held_reading(self):
        other = held_period()
        other['engine']['reason'] = 'not_reconciled'
        self.assertIsNone(self.read(other))
        with mock.patch.object(owed, 'ENABLED', False):
            self.assertIsNone(self.read())


if __name__ == '__main__':
    unittest.main()
