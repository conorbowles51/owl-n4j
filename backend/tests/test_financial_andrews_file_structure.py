"""Andrews multi-period files whose statement pages were not grouped; synthetic data only.

Each test is one root cause measured on scanned share statements carrying an
embedded OCR layer, where a statement's pages fell apart into unassigned
pages or lost a share section:

- a stray mark inside a printed heading word (``Andr,ews``, ``A.ccount``);
- the first page's account cell read with digits wrong, completed only from
  its own printed page 2;
- a share heading read with look-alike letters in its ID (confirmed by the
  same label printed in digits elsewhere in the file) or in its date (read
  only as the printed period start).
"""
import unittest
from copy import deepcopy

from services.financial import statement_import_andrews as andrews
from services.financial.statement_import_andrews import (andrews_catalog, andrews_page,
    propose_andrews_statement, unassigned_andrews_groups)
from tests.test_financial_statement_import_andrews import source


def renumber(data, page):
    data['page_number'] = page
    for row in data['rows']:
        for cell in row['cells']:
            cell['locator']['page'] = page
    return data


def statement(first_account='1234 6 789', second_account='123456789'):
    """A two-page statement: printed page 1 opens both shares, page 2 continues the checking share."""
    first = source([
        [(15, '06/01 ID 0000 BASE SHARE SAVINGS Previous Balance'), (350, '0.00')],
        [(15, '06/30'), (75, 'Ending Balance'), (350, '0.00')],
        [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
        [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-10.00'), (350, '90.00')],
        [(15, '--- Continued on following page ---')]], account=first_account)
    second = renumber(source([
        [(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '85.00')],
        [(15, '06/30'), (75, 'Ending Balance'), (350, '85.00')]], printed_page=2, names=False,
        account=second_account), 2)
    return first, second


class HeadingSpeckTests(unittest.TestCase):
    def test_one_stray_mark_inside_the_brand_or_a_title_word_still_identifies_the_page(self):
        for row, text in ((0, 'A.ccount Statement'), (0, 'Account State,ment'), (1, 'Andr,ews'), (1, "Andre'ws")):
            data = source([])
            data['rows'][row]['cells'][0]['expected_text'] = text
            with self.subTest(text=text):
                page = andrews_page(data)
                self.assertIsNotNone(page)
                self.assertTrue(page['branded'])

    def test_other_damage_or_two_marks_are_not_read(self):
        for row, text in ((0, 'A.ccount. Statement'), (0, 'A..ccount Statement'), (0, 'Acc0unt Statement'),
                          (1, 'Andr,ew.s'), (1, 'Andrevvs'), (1, ',Andrews')):
            data = source([])
            data['rows'][row]['cells'][0]['expected_text'] = text
            with self.subTest(text=text):
                page = andrews_page(data, allow_unbranded=True)
                if row == 0:
                    self.assertIsNone(page)
                else:
                    self.assertFalse(page['branded'])

    def test_switch_turns_the_rule_off(self):
        data = source([])
        data['rows'][1]['cells'][0]['expected_text'] = 'Andr,ews'
        andrews.HEADING_SPECK = False
        try:
            self.assertFalse(andrews_page(data, allow_unbranded=True)['branded'])
        finally:
            andrews.HEADING_SPECK = True


class DamagedAccountTests(unittest.TestCase):
    def test_page_two_completes_a_first_page_account_read_with_two_digits_wrong(self):
        first, second = statement('1234 6 709')  # one digit lost, one misread
        before = deepcopy([first, second])
        self.assertIsNone(andrews_page(first, allow_unbranded=True))
        groups, handled, incomplete = andrews_catalog([first, second])
        self.assertEqual(incomplete, set())
        self.assertEqual(handled, {(1, 0), (2, 0)})
        self.assertEqual([(g['account_reference'], g['page_numbers']) for g in groups],
                         [('123456789 / Share 0000', [1]), ('123456789 / Share 0040', [1, 2])])
        self.assertEqual(groups[1]['account_reading'],
                         dict(basis='printed_on_next_page', digits_read='12346709', page_number=2))
        self.assertEqual(unassigned_andrews_groups([first, second], handled), [])
        rows = propose_andrews_statement([first, second], 'USD', groups[1])['rows']
        self.assertEqual([r['fields']['balance'] for r in rows if r['kind'] == 'balance'], ['10000', '8500'])
        self.assertFalse(any(r['issues'] for r in rows if not r['excluded']))
        quiet = propose_andrews_statement([first], 'USD', groups[0])
        self.assertTrue(quiet['no_activity_evidence']['verified'])
        self.assertEqual([first, second], before)

    def test_nothing_is_inferred_without_every_corroboration(self):
        cases = {
            'three digits wrong': statement('1234 0 709'),
            'letters in the cell': statement('1234 6 7O9'),
            'next page prints another account': statement('1234 6 789', '987654321'),
            'next page account spaced too': statement('1234 6 789', '1234 56789'),
        }
        first, second = statement()
        second['rows'][4]['cells'][0]['expected_text'] = '3'
        cases['next page is not printed page 2'] = (first, second)
        first, second = statement()
        second['rows'][3]['cells'][0]['expected_text'] = '06/01/20 06/29/20'
        cases['next page prints other dates'] = (first, second)
        first, second = statement()
        first['rows'] = [r for r in first['rows'] if 'Continued' not in andrews._text(r)]
        cases['no continuation notice'] = (first, second)
        first, second = statement()
        cases['not adjacent'] = (first, renumber(second, 3))
        first, second = statement()
        first['rows'][1]['cells'][0]['expected_text'] = 'unreadable logo'
        cases['first page unbranded'] = (first, second)
        for name, (first, second) in cases.items():
            with self.subTest(name):
                groups, handled, _ = andrews_catalog([first, second])
                self.assertNotIn((1, 0), handled)
                self.assertFalse(any(1 in g['page_numbers'] for g in groups))
        # Alone, the damaged page opens nothing.
        first, _ = statement()
        self.assertEqual(andrews_catalog([first])[0], [])

    def test_switch_turns_the_rule_off(self):
        first, second = statement()
        andrews.DAMAGED_ACCOUNT_FROM_NEXT_PAGE = False
        try:
            self.assertNotIn((1, 0), andrews_catalog([first, second])[1])
            self.assertIsNone(andrews_page(first, damaged_account=True))
        finally:
            andrews.DAMAGED_ACCOUNT_FROM_NEXT_PAGE = True

    def test_digit_edits(self):
        self.assertEqual(andrews._digit_edits('12346709', '123456789'), 2)
        self.assertEqual(andrews._digit_edits('12345678', '123456789'), 1)
        self.assertEqual(andrews._digit_edits('123456789', '123456789'), 0)
        self.assertEqual(andrews._digit_edits('98765432', '123456789'), 8)


def heading_file(heading, *, other='07/01 ID 0000 BASE SHARE SAVINGS Previous Balance'):
    """Page 1 carries ``heading``; page 2 (another period, same account) prints ``other``."""
    first = source([
        [(15, heading), (350, '10.00')],
        [(15, '06/03'), (75, 'Deposit Dividend 0.050%'), (310, '0.02'), (350, '10.02')],
        [(15, '06/30'), (75, 'Ending Balance'), (350, '10.02')]])
    second = renumber(source([
        [(15, other), (350, '10.02')],
        [(15, '07/31'), (75, 'Ending Balance'), (350, '10.02')]], period='07/01/20 07/31/20'), 2)
    return first, second


class LookalikeShareHeadingTests(unittest.TestCase):
    def test_a_share_id_read_in_letters_is_the_one_the_file_prints_for_that_label(self):
        first, second = heading_file('06/01 ID ODDO BASE SHARE SAVINGS Previous Balance')
        before = deepcopy([first, second])
        groups, _, incomplete = andrews_catalog([first, second])
        self.assertEqual(incomplete, set())
        june = next(g for g in groups if g['period_start'] == '2020-06-01')
        self.assertEqual(june['account_reference'], '123456789 / Share 0000')
        self.assertEqual(june['share_heading']['bases'], [andrews.SHARE_ID_FROM_FILE])
        rows = propose_andrews_statement([first], 'USD', june)['rows']
        balances = [(r['fields']['date'], r['fields']['balance']) for r in rows if r['kind'] == 'balance']
        self.assertEqual(balances, [('2020-06-01', '1000'), ('2020-06-30', '1002')])
        self.assertFalse(any(r['issues'] for r in rows if not r['excluded']))
        self.assertEqual([first, second], before)

    def test_a_heading_date_read_in_letters_is_read_only_as_the_period_start(self):
        first, second = heading_file('06/0l ID 0000 BASE SHARE SAVINGS Previous Balance')
        groups, _, incomplete = andrews_catalog([first, second])
        self.assertEqual(incomplete, set())
        june = next(g for g in groups if g['period_start'] == '2020-06-01')
        self.assertEqual(june['share_heading']['bases'], [andrews.HEADING_DATE_IS_PERIOD_START])
        rows = propose_andrews_statement([first], 'USD', june)['rows']
        opening = next(r for r in rows if r['kind'] == 'balance')
        self.assertEqual((opening['fields']['date'], opening['fields']['date_reading']),
                         ('2020-06-01', andrews.HEADING_DATE_IS_PERIOD_START))
        # A heading date read as another day is not the period start.
        first, second = heading_file('06/l0 ID 0000 BASE SHARE SAVINGS Previous Balance')
        groups, _, incomplete = andrews_catalog([first, second])
        self.assertIn((1, 0), incomplete)
        self.assertFalse(any(g['period_start'] == '2020-06-01' for g in groups))

    def test_an_id_the_file_does_not_confirm_is_not_read(self):
        cases = {
            'label printed with no digits elsewhere': heading_file('06/01 ID ODDO BASE SHARE SAVINGS Previous Balance',
                                                                   other='07/01 ID 0040 FREE CHECKING Previous Balance'),
            'label printed with another ID': heading_file('06/01 ID OO1O BASE SHARE SAVINGS Previous Balance'),
            'label damaged': heading_file('06/01 ID ODDO BASE SHARE SAV1NGS Previous Balance'),
            'not a look-alike': heading_file('06/01 ID OXDO BASE SHARE SAVINGS Previous Balance'),
        }
        for name, (first, second) in cases.items():
            with self.subTest(name):
                groups, _, incomplete = andrews_catalog([first, second])
                self.assertIn((1, 0), incomplete)
                self.assertFalse(any(g['period_start'] == '2020-06-01' for g in groups))
        # The same label printed in digits with two IDs elsewhere confirms neither.
        first, second = heading_file('06/01 ID ODDO BASE SHARE SAVINGS Previous Balance')
        third = renumber(source([[(15, '08/01 ID 0001 BASE SHARE SAVINGS Previous Balance'), (350, '1.00')],
                                 [(15, '08/31'), (75, 'Ending Balance'), (350, '1.00')]],
                                period='08/01/20 08/31/20'), 3)
        groups, _, incomplete = andrews_catalog([first, second, third])
        self.assertIn((1, 0), incomplete)
        # Another account's pages confirm nothing.
        first, _ = heading_file('06/01 ID ODDO BASE SHARE SAVINGS Previous Balance')
        second = renumber(source([[(15, '07/01 ID 0000 BASE SHARE SAVINGS Previous Balance'), (350, '1.00')],
                                  [(15, '07/31'), (75, 'Ending Balance'), (350, '1.00')]],
                                 account='987654321', period='07/01/20 07/31/20'), 2)
        self.assertIn((1, 0), andrews_catalog([first, second])[2])

    def test_switch_turns_the_rule_off(self):
        first, second = heading_file('06/01 ID ODDO BASE SHARE SAVINGS Previous Balance')
        andrews.SHARE_HEADING_LOOKALIKES = False
        try:
            self.assertIn((1, 0), andrews_catalog([first, second])[2])
        finally:
            andrews.SHARE_HEADING_LOOKALIKES = True


if __name__ == '__main__':
    unittest.main()
