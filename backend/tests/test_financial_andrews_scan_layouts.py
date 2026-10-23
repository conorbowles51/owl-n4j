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
        # A glyph inside the ID or date is still not read as a digit (a point beside all four
        # digits is a speck, SHARE_ID_SPECK; a comma or a point standing for a digit is not). A
        # look-alike date is read only when it then is the period start (SHARE_HEADING_LOOKALIKES,
        # tests/test_financial_andrews_file_structure.py), so ``06/l0`` stays unread.
        for heading in ('06/01 ID 004,0 FREE CHECKING Previous Balance', '06/01 ID 00.4 FREE CHECKING Previous Balance',
                        '06/l0 ID 0040 FREE CHECKING Previous Balance'):
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

    def test_a_pinned_cell_pins_its_disputed_neighbour_in_the_next_round(self):
        from services.financial import statement_reading_quality as quality
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-10.00'), (350, '9?.00')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-?.00'), (350, '85.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '85.00')]])
        held = {(0, 10, 3), (0, 11, 2)}
        confirmed = money_cells(data) - held
        candidates = {(0, 10, 3): ['90.00', '96.00'], (0, 11, 2): ['-5.00', '-6.00']}
        result = quality.pinned_andrews_values(tables(data), candidates, confirmed)
        self.assertEqual(result['values'], {(0, 10, 3): dict(text='90.00', pinned_by=[[0, 9, 1], [0, 10, 2]]),
                                            (0, 11, 2): dict(text='-5.00', pinned_by=[[0, 10, 3], [0, 11, 3]])})
        try:
            quality.PROPAGATE_PINNED = False
            self.assertEqual(quality.pinned_andrews_values(tables(data), candidates, confirmed), {})
        finally:
            quality.PROPAGATE_PINNED = True
        # A neighbour that is itself only fixed by a disputed cell is never used.
        self.assertEqual(quality.pinned_andrews_values(tables(data), {(0, 10, 3): [], (0, 11, 2): ['-5.00']},
                                                       confirmed), {})

    def test_a_continuation_notice_read_with_spaces_or_stray_points_links_the_next_page(self):
        first = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-10.00'), (350, '90.00')],
            [(15, '- - - Continued\u00b7on fol low.ing page - - -')]])
        second = source([
            [(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '85.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '85.00')]], page=2, printed_page=2, names=False)
        groups, _, _ = andrews_catalog([first, second])
        self.assertEqual([g['page_numbers'] for g in groups], [[1, 2]])
        # A letter misread inside the notice is not a notice.
        first['rows'][-1]['cells'][0]['expected_text'] = '--- Continued on fo1lowing page ---'
        groups, _, _ = andrews_catalog([first, second])
        self.assertEqual([g['page_numbers'] for g in groups], [[1]])

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
        # Without the neighbour's page reading its confirmed balance cannot be read in one round:
        # nothing is pinned when pinned cells do not propagate.
        from services.financial import statement_reading_quality as quality
        try:
            quality.PROPAGATE_PINNED = False
            self.assertEqual(pinned_andrews_values(tables(data), candidates, confirmed), {})
        finally:
            quality.PROPAGATE_PINNED = True
        # With propagation the neighbour is pinned first by its own payment (its balance confirmed),
        # and then fixes the next cell: the same readings as with its page reading given.
        propagated = pinned_andrews_values(tables(data), candidates, confirmed)
        self.assertEqual({k: v['text'] for k, v in propagated['values'].items()},
                         {(0, 10, 2): '-1.00 99.00', (0, 11, 2): '-26.11 72.89'})
        result = pinned_andrews_values(tables(data), candidates, confirmed, {(0, 10, 2): '-1.00 99.00'})
        self.assertEqual(result['values'][(0, 11, 2)]['pinned_by'], [[0, 10, 2], [0, 12, 2]])
        self.assertEqual(result['values'][(0, 10, 2)]['pinned_by'], [[0, 9, 1]])
        # The neighbour's unconfirmed amount never counts: a wrong page amount there changes nothing for the next cell,
        # but its own equation then fails and its section stays held.
        result = pinned_andrews_values(tables(data), {(0, 10, 2): ['-2.00 99.00'], (0, 11, 2): ['-26.11 72.89']},
                                       confirmed, {(0, 10, 2): '-2.00 99.00'})
        self.assertEqual(result, {})


class ContinuationOnlyPageTests(unittest.TestCase):
    """A page whose cycle reads a letter for a digit, or whose title reads a lower-case s, only continues."""

    def pages(self, period='06/0l/20 06/30/20', title=None, mark=True):
        first = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-10.00'), (350, '90.00')],
            [(15, '--- Continued on following page ---')]])
        second = source([
            [(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '85.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '85.00')]], page=2, printed_page=2, names=False, period=period)
        if title:
            second['rows'][0]['cells'][0]['expected_text'] = title
        if not mark:
            second['rows'][1]['cells'][0]['expected_text'] = 'unreadable logo'
        return first, second

    def test_it_continues_the_previous_page_when_the_dates_then_agree_exactly(self):
        for period, title, mark in (('06/0l/20 06/30/20', None, True), ('06/01/20 O6/30/20', None, True),
                                    ('06/01/20 06/30/20', 'Ac count statement', False)):
            with self.subTest(period=period, title=title):
                first, second = self.pages(period, title, mark)
                self.assertTrue(andrews_page(second, allow_unbranded=True)['continuation_only'])
                groups, _, _ = andrews_catalog([first, second])
                self.assertEqual([g['page_numbers'] for g in groups], [[1, 2]])
                rows = propose_andrews_statement([first, second], 'USD', groups[0])['rows']
                self.assertEqual([r['fields']['balance'] for r in rows if r['kind'] == 'balance'], ['10000', '8500'])

    def test_it_never_opens_a_period_or_continues_other_dates(self):
        # Other dates once the letter is read as a digit.
        first, second = self.pages('06/0l/20 06/29/20')
        self.assertEqual([g['page_numbers'] for g in andrews_catalog([first, second])[0]], [[1]])
        # Alone, it opens nothing, not even an unassigned group.
        from services.financial.statement_import_andrews import unassigned_andrews_groups
        _, second = self.pages()
        self.assertEqual(andrews_catalog([second])[0], [])
        self.assertEqual(unassigned_andrews_groups([second], set()), [])
        # A branded page's lower-case title is still not a title; other letters are not digits.
        _, second = self.pages('06/01/20 06/30/20', 'Ac count statement', True)
        self.assertIsNone(andrews_page(second, allow_unbranded=True))
        _, second = self.pages('06/0B/20 06/30/20')
        self.assertIsNone(andrews_page(second, allow_unbranded=True))


class OrderedDamagedDateTests(unittest.TestCase):
    """A row date damaged only by OCR marks is read when the payment order fixes it."""

    def read(self, damaged, before='06/03', after='06/05', second=None):
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, before), (75, 'Withdrawal Debit Card'), (310, '-1.00'), (350, '99.00')],
            [(15, damaged), (75, (second + ' ' if second else '') + 'Withdrawal Debit Card'), (310, '-2.00'), (350, '97.00')],
            [(15, after), (75, 'Withdrawal Debit Card'), (310, '-3.00'), (350, '94.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '94.00')]])
        groups, _, _ = andrews_catalog([data])
        rows = propose_andrews_statement([data], 'USD', groups[0])['rows']
        return [r for r in rows if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')][1]

    def test_marks_and_measured_lookalikes_are_set_aside_between_ordered_neighbours(self):
        from services.financial.statement_import_andrews import DATE_READ_IN_ORDER
        for damaged in ('06/04·', '_06/04', '06/04.', '-06/04', '06/O4', 'O6/O4', '06/:04', '06/0.4', '06i04'):
            with self.subTest(damaged=damaged):
                row = self.read(damaged)
                self.assertEqual((row['fields'].get('date'), row['fields'].get('date_reading'), row['issues']),
                                 ('2020-06-04', DATE_READ_IN_ORDER, []))
                self.assertEqual(row['source_cells'][0]['expected_text'], damaged)
        self.assertEqual(self.read('06/l4', before='06/13', after='06/15')['fields'].get('date'), '2020-06-14')

    def test_it_stays_held_out_of_order_without_clean_neighbours_or_with_other_damage(self):
        cases = (dict(damaged='06/0l', before='06/12', after='06/14'),    # reads 06/01: before the payment above
                 dict(damaged='06/04·', before='06/0?'),            # neighbour not read cleanly
                 dict(damaged='06/0B'), dict(damaged='06/04 x'), dict(damaged='0604'), dict(damaged='06/41'),
                 dict(damaged='07/04·', after='07/05'))            # outside the printed period
        for case in cases:
            with self.subTest(**case):
                row = self.read(**case)
                self.assertIsNone(row['fields'].get('date'))
                self.assertTrue(row['issues'])

    def test_the_opening_and_ending_lines_bound_the_first_and_last_payment(self):
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, 'O6/02'), (75, 'Withdrawal Debit Card'), (310, '-1.00'), (350, '99.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '99.00')]])
        groups, _, _ = andrews_catalog([data])
        rows = propose_andrews_statement([data], 'USD', groups[0])['rows']
        self.assertEqual(next(r for r in rows if r['kind'] == 'transaction')['fields'].get('date'), '2020-06-02')

    def test_switch_turns_the_rule_off(self):
        from services.financial import statement_import_andrews as reader
        try:
            reader.ORDERED_DAMAGED_DATES = False
            self.assertIsNone(self.read('06/04·')['fields'].get('date'))
        finally:
            reader.ORDERED_DAMAGED_DATES = True


class VoucherLayoutTests(unittest.TestCase):
    """Long credit-voucher payments printed in three more ways."""

    def read(self, voucher_rows, after=('06/05', '-3.00', '97.36')):
        data = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            *voucher_rows,
            [(75, 'EXAMPLE REFUND')],
            [(15, after[0]), (75, 'Withdrawal Debit Card'), (310, after[1]), (350, after[2])],
            [(15, '06/30'), (75, 'Ending Balance'), (350, after[2])]])
        return data, data['rows'][10]

    def payments(self, data):
        groups, _, _ = andrews_catalog([data])
        result = propose_andrews_statement([data], 'USD', groups[0])
        return [r for r in result['rows'] if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]

    def test_amount_and_balance_inside_the_label_cell_are_read_and_checked_by_both_balances(self):
        data, label_row = self.read([[(15, '06/03'), (75, 'Recurring Withdrawal Adjustment Debit Card Credit Voucher 0.36 100.36')]])
        label_row['cells'][1]['locator']['rect'][2] = 375000   # the label cell reaches the balance column
        voucher, after = self.payments(data)
        self.assertEqual((voucher['fields']['amount_minor'], voucher['fields']['direction'], voucher['fields']['balance'],
                          voucher['issues']), ('36', 'credit', '10036', []))
        self.assertEqual(set(voucher['value_sources']), {'amount', 'balance'})
        self.assertEqual(after['issues'], [])
        # A misread balance in the label cell breaks the next payment's check: held.
        label_row['cells'][1]['expected_text'] = 'Recurring Withdrawal Adjustment Debit Card Credit Voucher 0.36 100.63'
        voucher, after = self.payments(data)
        self.assertTrue(voucher['issues'] or after['issues'])
        # A label cell that stops short of the money columns is not this layout.
        label_row['cells'][1]['expected_text'] = 'Recurring Withdrawal Adjustment Debit Card Credit Voucher 0.36 100.36'
        label_row['cells'][1]['locator']['rect'][2] = 250000
        self.assertNotIn('amount_minor', self.payments(data)[0]['fields'])

    def test_a_lower_case_or_spaced_credit_and_a_joined_wrapped_money_line(self):
        for label in ('Recurring Withdrawal Adjustment Debit Card credit Voucher',
                      'Recurring Withdrawal Adjustment Debit Card Cr edit Voucher'):
            with self.subTest(label=label):
                data, label_row = self.read([[(15, '06/03'), (75, label)], [(310, '0.36 100.36')]])
                data['rows'][11]['cells'][0]['locator']['rect'][2] = 375000
                voucher = self.payments(data)[0]
                self.assertEqual((voucher['fields']['amount_minor'], voucher['fields']['balance'], voucher['issues']),
                                 ('36', '10036', []))
        # Other letters read wrongly are not the label.
        data, _ = self.read([[(15, '06/03'), (75, 'Recurring Withdrawal Adjustment Debit Card Credlt Voucher')],
                             [(310, '0.36'), (350, '100.36')]])
        self.assertNotIn('amount_minor', self.payments(data)[0]['fields'])

    def test_date_additional_date_and_label_read_as_one_cell(self):
        data, _ = self.read([[(15, '06/03 06/02 Recurring Withdrawal Adjustment Debit Card Credit Voucher')],
                             [(310, '0.36'), (350, '100.36')]])
        data['rows'][10]['cells'][0]['locator']['rect'][2] = 300000
        voucher = self.payments(data)[0]
        self.assertEqual((voucher['fields']['date'], voucher['fields']['additional_printed_date'],
                          voucher['fields']['amount_minor'], voucher['issues']), ('2020-06-03', '06/02', '36', []))
