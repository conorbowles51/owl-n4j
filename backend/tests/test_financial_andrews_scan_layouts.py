"""Andrews scan layouts the reader must read completely; synthetic data only.

Each test is one root cause found on scanned share statements carrying an
embedded OCR layer: club shares, a mailing block printed without (or with a
damaged) mailing code, spaces or a stray mark inside fixed heading text, and a
section that continues from the previous page.
"""
import unittest
from copy import deepcopy

from services.financial.statement_import_andrews import (andrews_catalog, andrews_page,
    leading_continuation_rows, propose_andrews_statement)
from services.financial.statement_import_catalog import statement_catalog
from tests.test_financial_statement_import_andrews import source


def unmarked(lines, *, names=('EXAMPLE PERSON', 'JOINT PERSON'), street='12 EXAMPLE ST NE APT 3',
             city='EXAMPLE CITY DC 20001', marker=None, **kwargs):
    block = ([[(20, marker)]] if marker else []) + [[(20, n)] for n in names]
    block += ([[(20, street)]] if street else []) + ([[(20, city)]] if city else [])
    return source(block + lines, names=False, **kwargs)


QUIET = [[(15, '06/01 ID 0000 BASE SHARE SAVINGS Previous Balance'), (350, '0.00')],
         [(15, '06/30'), (75, 'Ending Balance'), (350, '0.00')]]


class ClubShareTests(unittest.TestCase):
    def test_club_shares_are_read_as_their_own_savings_sections(self):
        data = source([
            [(15, '06/01 ID 0010 HOLIDAY CLUB Previous Balance'), (350, '150.40')],
            [(15, '06/30'), (75, 'Deposit Dividend 0.050%'), (310, '0.02'), (350, '150.42')],
            [(75, 'Annual Percentage Yield Earned 0.05%')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '150.42')],
            [(15, '06/01 ID 0011 VACATION CLUB Previous Balance'), (350, '0.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '0.00')],
            [(75, 'VACATION CLUB will mature on 01/01/21')],
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '10.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '10.00')]])
        before = deepcopy(data)
        groups, handled, incomplete = andrews_catalog([data])
        self.assertEqual(incomplete, set())
        self.assertEqual([(g['share_reference'], g['account_label'], g['account_type']) for g in groups],
                         [('0010', 'HOLIDAY CLUB', 'savings'), ('0011', 'VACATION CLUB', 'savings'),
                          ('0040', 'FREE CHECKING', 'checking')])
        holiday = propose_andrews_statement([data], 'USD', groups[0])
        payments = [r for r in holiday['rows'] if not r['excluded']]
        self.assertEqual([(r['kind'], r['fields']['amount_minor'], r['fields']['direction']) for r in payments],
                         [('transaction', '2', 'credit')])
        self.assertFalse(any(r['issues'] for r in holiday['rows']))
        vacation = propose_andrews_statement([data], 'USD', groups[1])
        self.assertTrue(vacation['no_activity_evidence']['verified'])
        self.assertFalse(statement_catalog([data])['unclassified_sources'])
        self.assertEqual(data, before)

    def test_a_damaged_club_heading_is_still_not_guessed(self):
        data = source([[(15, '06/01 ID 0010 HOL1DAY CLUB Previous Balance'), (350, '150.40')],
                       [(15, '06/30'), (75, 'Ending Balance'), (350, '150.40')]])
        groups, _, incomplete = andrews_catalog([data])
        self.assertEqual(groups, [])
        self.assertTrue(incomplete)


class UnmarkedHolderTests(unittest.TestCase):
    def holder(self, data):
        groups, _, _ = andrews_catalog([data])
        return groups[0]['holder']

    def test_complete_mailing_block_without_a_code_names_the_holder(self):
        data = unmarked(QUIET)
        before = deepcopy(data)
        self.assertEqual(self.holder(data), 'EXAMPLE PERSON / JOINT PERSON')
        self.assertEqual(data, before)

    def test_a_damaged_code_line_or_unread_page_number_is_passed_over(self):
        for kwargs in (dict(marker='~1234567890<'), dict(marker='>1234567890~'), dict(printed_page='l')):
            with self.subTest(**kwargs):
                self.assertEqual(self.holder(unmarked(QUIET, **kwargs)), 'EXAMPLE PERSON / JOINT PERSON')

    def test_an_incomplete_or_damaged_block_names_nobody(self):
        for kwargs in (dict(street=None), dict(city=None), dict(city='EXAMPLE CITY DC 2OOO1'),
                       dict(names=('EXAMPLE PERSON', 'J0INT PERSON')), dict(marker='Some other text'),
                       dict(names=('A', 'B', 'C', 'D'))):
            with self.subTest(**kwargs):
                self.assertEqual(self.holder(unmarked(QUIET, **kwargs)), '')

    def test_text_between_the_block_and_the_first_share_heading_names_nobody(self):
        self.assertEqual(self.holder(unmarked([[(20, 'IMPORTANT NOTICE')]] + QUIET)), '')


class HeadingTextTests(unittest.TestCase):
    def test_a_stray_mark_between_the_title_words_still_identifies_the_page(self):
        data = source(QUIET)
        data['rows'][0]['cells'][0]['expected_text'] = 'Account. Statement'
        self.assertEqual(andrews_page(data)['account'], '123456789')

    def test_spaces_inside_the_account_number_need_the_same_digits_on_an_adjacent_page(self):
        previous = source(QUIET, page=1)
        spaced = source(QUIET, page=2, account='1234 56 789', period='07/01/20 07/31/20')
        for row in spaced['rows']:
            for cell in row['cells']:
                cell['locator']['page'] = 2
        self.assertEqual(andrews_page(spaced)['account'], '123456789')
        self.assertTrue(andrews_page(spaced)['account_spaced'])
        groups, _, _ = andrews_catalog([previous, spaced])
        self.assertEqual(sorted(g['period_start'] for g in groups), ['2020-06-01', '2020-07-01'])
        # Alone, or beside a page whose digits differ, the spaced number opens nothing.
        self.assertEqual(andrews_catalog([spaced])[0], [])
        other = source(QUIET, page=1, account='123456780')
        self.assertEqual([g['period_start'] for g in andrews_catalog([other, spaced])[0]], ['2020-06-01'])
        # Letters are never read as digits.
        self.assertIsNone(andrews_page(source(QUIET, account='1234 56 78O')))


class LeadingContinuationTests(unittest.TestCase):
    def test_payments_carried_over_end_at_the_ending_balance_before_the_next_heading(self):
        data = source([
            [(75, 'EXAMPLE SHOP CONTINUED')],
            [(15, '06/20'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '95.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '95.00')],
            [(75, 'Dividends Paid Year to Date'), (350, '0.00')]] + QUIET, printed_page=2, names=False)
        page = andrews_page(data)
        rows = leading_continuation_rows(data, page)
        self.assertEqual(rows, [5, 6, 7])
        self.assertEqual(leading_continuation_rows(source(QUIET), andrews_page(source(QUIET))), [])


if __name__ == '__main__':
    unittest.main()


def tables(data):
    """The stored page-reading form of a synthetic source (what the engine passes)."""
    return [dict(table_source='text_alignment', geometry_source='cell_rectangles', table=dict(
        page=data['page_number'], values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                                               locator=c['locator']) for r in data['rows'] for c in r['cells']]))]


def money_cells(data):
    from services.financial.statement_import_proposal import exact_amount
    found = set()
    for r in data['rows']:
        for c in r['cells']:
            try:
                exact_amount(c['expected_text'].replace(' ', '').replace(',', ''), 'USD')
            except Exception:
                continue
            if c['locator']['rect'][0] >= 300000:
                found.add((0, r['row_index'], c['column_index']))
    return found


class PinnedSectionTests(unittest.TestCase):
    def page(self):
        return source([
            [(15, '06/01 ID 0000 BASE SHARE SAVINGS Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-16,61'), (350, '83.39')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '78.39')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '78.39')],
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '50.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-1O.00'), (350, '40.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '40.00')]])

    def test_each_section_is_decided_on_its_own(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = self.page()
        held = {(0, 10, 2), (0, 15, 2)}
        confirmed = money_cells(data) - held
        result = pinned_andrews_values(tables(data), {(0, 10, 2): ['-16.61'], (0, 15, 2): []}, confirmed)
        self.assertEqual({k: v['text'] for k, v in result['values'].items()}, {(0, 10, 2): '-16.61'})
        self.assertEqual(result['values'][(0, 10, 2)]['pinned_by'], [[0, 9, 1], [0, 10, 3]])
        self.assertEqual(result['controls']['unresolved'], [[0, 15, 2]])

    def test_neighbours_must_have_been_confirmed_by_the_crops(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = self.page()
        held = {(0, 10, 2), (0, 15, 2)}
        unchecked = money_cells(data) - held - {(0, 10, 3)}
        self.assertEqual(pinned_andrews_values(tables(data), {(0, 10, 2): ['-16.61'], (0, 15, 2): []}, unchecked), {})

    def test_a_reading_the_balances_do_not_fix_is_not_accepted(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = self.page()
        confirmed = money_cells(data) - {(0, 10, 2)}
        self.assertEqual(pinned_andrews_values(tables(data), {(0, 10, 2): ['-14.82']}, confirmed), {})
        self.assertEqual(pinned_andrews_values(tables(data), {(0, 10, 2): ['-16.61', '16.61']}, confirmed)['values'][
            (0, 10, 2)]['text'], '-16.61')

    def test_joined_amount_and_balance_cell_takes_one_pinned_reading_of_both(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-16,61 83.39')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '78.39')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '78.39')]])
        confirmed = money_cells(data) | {(0, 11, 2), (0, 11, 3)}
        result = pinned_andrews_values(tables(data), {(0, 10, 2): ['-16.61 83.39']}, confirmed)
        self.assertEqual(result['values'][(0, 10, 2)]['text'], '-16.61 83.39')
        # A reading whose amount and balance both drift by the same cents still breaks the next payment.
        self.assertEqual(pinned_andrews_values(tables(data), {(0, 10, 2): ['-16.71 83.29']}, confirmed), {})
        # Only one equation (its own payment's) cannot fix two amounts: with nothing after it, it stays held.
        last = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-16,61 83.39')],
            [(15, '--- Continued on following page ---')]])
        self.assertEqual(pinned_andrews_values(tables(last), {(0, 10, 2): ['-16.61 83.39']}, money_cells(last)), {})
        # Nor can the next payment's equation alone, which fixes only the balance.
        opening = source([
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-16,61 83.39')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '78.39')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '78.39')]], printed_page=2, names=False)
        self.assertEqual(pinned_andrews_values(tables(opening), {(0, 5, 2): ['-16.61 83.39']},
                                               money_cells(opening) | {(0, 6, 2), (0, 6, 3)}), {})

    def test_a_section_continued_from_the_previous_page_is_pinned_from_its_own_rows(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = source([
            [(15, '06/20'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '95.00')],
            [(15, '06/21'), (75, 'Withdrawal Debit Card'), (310, '-1 0 ,00'), (350, '85.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '85.00')]] + QUIET, printed_page=2, names=False)
        confirmed = money_cells(data) - {(0, 6, 2)}
        result = pinned_andrews_values(tables(data), {(0, 6, 2): ['-10.00']}, confirmed)
        self.assertEqual(result['values'][(0, 6, 2)], dict(text='-10.00', pinned_by=[[0, 5, 3], [0, 6, 3]]))

    def test_a_readable_running_balance_still_pins_the_next_payment(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-1?.00'), (350, '88.00')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-8,00'), (350, '80.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '80.00')]])
        held = {(0, 10, 2), (0, 11, 2)}
        confirmed = money_cells(data) - held
        result = pinned_andrews_values(tables(data), {(0, 10, 2): [], (0, 11, 2): ['-8.00']}, confirmed)
        # The 06/03 amount stays held, so its section is not accepted; the 06/04 amount is pinned on its own.
        self.assertEqual(result, {})
        data['rows'][10]['cells'][2]['expected_text'] = '-12.00'
        confirmed = money_cells(data) - {(0, 11, 2)}
        result = pinned_andrews_values(tables(data), {(0, 11, 2): ['-8.00']}, confirmed)
        self.assertEqual(result['values'][(0, 11, 2)]['pinned_by'], [[0, 10, 3], [0, 11, 3]])
        # With the 06/03 amount unreadable, its printed balance still opens the 06/04 equation.
        from services.financial.statement_reading_quality import _andrews_equations, _andrews_page_sections, _with_texts
        data['rows'][10]['cells'][2]['expected_text'] = '-1?.00'
        rows, = _andrews_page_sections(_with_texts(tables(data), {(0, 11, 2): '-8.00'}))
        self.assertIn(([(0, 10, 3), (0, 11, 2), (0, 11, 3)], True), _andrews_equations(rows))
        self.assertFalse(any((0, 10, 2) in cells for cells, _ in _andrews_equations(rows)))


class SpacedHeadingTests(unittest.TestCase):
    def test_spaces_inside_a_share_heading_date_or_id_keep_the_section(self):
        data = source([
            [(15, '06 / 01 ID 0011 VACATION CLUB Previous Balance'), (350, '0.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '0.00')],
            [(15, '06/01 ID 004 0 FREE CHECKING Previous Balance'), (350, '10.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-2.00'), (350, '8.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '8.00')]])
        groups, _, incomplete = andrews_catalog([data])
        self.assertEqual(incomplete, set())
        self.assertEqual([(g['share_reference'], g['account_reference']) for g in groups],
                         [('0011', '123456789 / Share 0011'), ('0040', '123456789 / Share 0040')])
        rows = propose_andrews_statement([data], 'USD', groups[0])['rows']
        self.assertEqual([r['fields']['date'] for r in rows if r['kind'] == 'balance'], ['2020-06-01', '2020-06-30'])
        # A glyph inside the ID or date is still not read as a digit.
        for heading in ('06/01 ID 004.0 FREE CHECKING Previous Balance', '06/0l ID 0040 FREE CHECKING Previous Balance'):
            bad = source([[(15, heading), (350, '10.00')], [(15, '06/30'), (75, 'Ending Balance'), (350, '10.00')]])
            with self.subTest(heading=heading):
                self.assertEqual(andrews_catalog([bad])[0], [])

    def test_adjacent_joined_cells_resolve_when_the_crops_confirm_one_part_of_each(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-6.24 93.76')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-50.00 43.76')],
            [(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-4.00 39.76')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '39.76')]])
        held = {(0, 10, 2), (0, 11, 2)}
        whole = money_cells(data) | {(0, 12, 2)}
        candidates = {(0, 10, 2): ['-6.24 93.76'], (0, 11, 2): ['-50.00 43.76']}
        # Each cell's balance is disputed and each shares an equation with the other: nothing is pinned.
        self.assertEqual(pinned_andrews_values(tables(data), candidates, whole - held), {})
        # The crops confirmed both amounts: each balance is fixed by agreed values alone.
        parts = (whole - held) | {(0, 10, 2, 'amount'), (0, 11, 2, 'amount')}
        result = pinned_andrews_values(tables(data), candidates, parts)
        self.assertEqual({k: v['text'] for k, v in result['values'].items()}, {k: t[0] for k, t in candidates.items()})
        # A confirmed balance alone needs the cell's own equation, which here holds a disputed neighbour.
        balances = (whole - held) | {(0, 11, 2, 'balance')}
        self.assertEqual(pinned_andrews_values(tables(data), candidates, balances), {})

    def test_a_confirmed_part_of_a_held_neighbour_opens_the_next_equation(self):
        from services.financial.statement_reading_quality import pinned_andrews_values
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-1.00 99.00?')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-26.11 72.89?')],
            [(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-4.00 68.89')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '68.89')]])
        held = {(0, 10, 2), (0, 11, 2)}
        confirmed = (money_cells(data) | {(0, 12, 2)}) - held | {(0, 10, 2, 'balance')}
        candidates = {(0, 10, 2): ['-1.00 99.00'], (0, 11, 2): ['-26.11 72.89']}
        # Without the neighbour's page reading its confirmed balance cannot be read: nothing is pinned.
        self.assertEqual(pinned_andrews_values(tables(data), candidates, confirmed), {})
        result = pinned_andrews_values(tables(data), candidates, confirmed, {(0, 10, 2): '-1.00 99.00'})
        self.assertEqual(result['values'][(0, 11, 2)]['pinned_by'], [[0, 10, 2], [0, 12, 2]])
        self.assertEqual(result['values'][(0, 10, 2)]['pinned_by'], [[0, 9, 1]])
        # The neighbour's unconfirmed amount never counts: a wrong page amount there changes nothing for the next cell,
        # but its own equation then fails and its section stays held.
        result = pinned_andrews_values(tables(data), {(0, 10, 2): ['-2.00 99.00'], (0, 11, 2): ['-26.11 72.89']},
                                       confirmed, {(0, 10, 2): '-2.00 99.00'})
        self.assertEqual(result, {})
