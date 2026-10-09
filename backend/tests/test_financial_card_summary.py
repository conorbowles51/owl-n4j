"""Card account summary totals must equal the card lines read; synthetic cells only."""
import unittest
from copy import deepcopy

from services.financial.card_summary import check_card_period, summary_components
from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
from tests.test_financial_pdf_geometry_candidates import rectangle
from tests.test_financial_statement_import_merrick import summary_statement

PURCHASES = 4  # the summary line 'Purchases + $114.00' (the two card lines read are 14.00 and 100.00)


def _checked(data, layout='merrick-card'):
    rows = propose_merrick_table(data, 'USD', merrick_statement(data))['rows']
    return check_card_period(layout, deepcopy(rows), [data], 'USD'), rows


def _held(rows):
    return [(r['id'], r['issues'][-1]) for r in rows if r['kind'] == 'unresolved']


def _with_interest(data, text):
    """Add an 'Interest Charged' summary line below Purchases."""
    row = deepcopy(data['rows'][PURCHASES])
    row['row_index'] += 50
    row['cells'] = row['cells'][:2]
    row['cells'][0]['expected_text'], row['cells'][1]['expected_text'] = 'Interest Charged', text
    for cell, x in zip(row['cells'], (95, 230)):
        cell['locator'] = rectangle(235, x=x, width=45 if x == 230 else 70, height=8)
    data['rows'].insert(PURCHASES + 1, row)
    return data


class CardSummaryTests(unittest.TestCase):
    def test_the_printed_components_are_read_from_the_summary_box_only(self):
        lines = summary_components(summary_statement(), 'SUMMARY OF ACCOUNT ACTIVITY', 'PAYMENT INFORMATION', 'USD')
        self.assertEqual([(role, value) for role, _, _, value, _ in lines], [('debit_component', (11400, True))])

    def test_agreeing_totals_leave_the_period_unchanged(self):
        checked, original = _checked(summary_statement())
        self.assertEqual(checked, original)

    def test_a_total_that_differs_from_the_lines_read_holds_the_period(self):
        data = summary_statement()
        data['rows'][PURCHASES]['cells'][1]['expected_text'] = '+ $115.00'
        checked, _ = _checked(data)
        [(row_id, message)] = _held(checked)
        self.assertTrue(row_id.endswith(':104'))
        self.assertIn('differ from the card lines read', message)

    def test_an_unconfirmed_or_look_alike_total_agrees_only_by_equalling_the_confirmed_lines(self):
        for text, held in (('+ $114.00?', False), ('+ $1l4.OO', False), ('+ $113.00?', True),
                           ('+ 114.00', True), ('+ $1?4.00', True)):
            with self.subTest(text=text):
                data = summary_statement()
                data['rows'][PURCHASES]['cells'][1]['expected_text'] = text
                checked, _ = _checked(data)
                self.assertEqual(bool(_held(checked)), held)
                if held:
                    self.assertIn('could not be read', _held(checked)[0][1])

    def test_two_doubtful_totals_on_one_side_stay_held_even_when_their_sum_fits(self):
        data = _with_interest(summary_statement(), '$0.0O')
        data['rows'][PURCHASES]['cells'][1]['expected_text'] = '+ $114.00?'
        checked, _ = _checked(data)
        self.assertEqual(len(_held(checked)), 2)
        confirmed = _with_interest(summary_statement(), '$0.00')
        self.assertEqual(_held(_checked(confirmed)[0]), [])

    def test_lines_that_are_unreadable_themselves_are_left_to_their_own_issues(self):
        data = summary_statement()
        data['rows'][PURCHASES]['cells'][1]['expected_text'] = '+ $115.00'
        payment = next(r for r in data['rows'] if r['cells'][0]['expected_text'] == '04/22')
        payment['cells'][-1]['expected_text'] = '14.0O'
        checked, original = _checked(data)
        self.assertEqual(_held(checked), [])
        self.assertEqual(checked, original)

    def test_a_charge_section_the_summary_prints_no_line_for_is_not_part_of_its_total(self):
        data = summary_statement()
        interest = next(r for r in data['rows'] if r['cells'][0]['expected_text'] == '04/25')
        interest['cells'][-1]['expected_text'] = '2.00'
        total = next(r for r in data['rows'] if r['cells'][0]['expected_text'] == 'TOTAL INTEREST FOR THIS PERIOD')
        total['cells'][-1]['expected_text'] = '2.00'
        # The summary prints Purchases 114.00 and no interest line: the 2.00 interest is not in that total.
        checked, original = _checked(data)
        self.assertEqual(_held(checked), [])
        # Once the summary prints an interest line, the interest lines count on the debit side.
        data = _with_interest(data, '$0.00')
        self.assertIn('differ from the card lines read', _held(_checked(data)[0])[0][1])

    def test_only_the_card_layouts_it_names_are_checked(self):
        data = summary_statement()
        data['rows'][PURCHASES]['cells'][1]['expected_text'] = '+ $115.00'
        checked, original = _checked(data, layout='capital-one-card')
        self.assertEqual(checked, original)


if __name__ == '__main__':
    unittest.main()


class CardPinnedReadingTests(unittest.TestCase):
    """A held money cell of a card statement page takes the printed reading its page's controls fix."""

    def tables(self, data):
        return [dict(table=dict(page=data['page_number'], values=[
            dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
            for r in data['rows'] for c in r['cells']]))]

    def cell(self, data, text):
        return next((0, r['row_index'], c['column_index']) for r in data['rows'] for c in r['cells']
                    if c['expected_text'] == text)

    def run_pinned(self, data, held):
        """``held`` maps a printed cell text to (marked text, candidate readings)."""
        from services.financial.statement_reading_quality import pinned_card_values
        keys = {self.cell(data, text): value for text, value in held.items()}
        for row in data['rows']:
            for c in row['cells']:
                if (0, row['row_index'], c['column_index']) in keys:
                    c['expected_text'] = keys[(0, row['row_index'], c['column_index'])][0]
        everything = {(0, r['row_index'], c['column_index']) for r in data['rows'] for c in r['cells']}
        return keys, pinned_card_values(self.tables(data), {k: v[1] for k, v in keys.items()}, everything - set(keys))

    def test_one_held_line_is_fixed_by_the_balance_and_summary_controls(self):
        keys, result = self.run_pinned(summary_statement(), {'14.00': ('14.00?', ['14.00'])})
        [key] = keys
        self.assertEqual(result['values'][key]['text'], '14.00')
        self.assertIn('balance', result['controls']['equations'])

    def test_a_held_previous_balance_is_fixed_by_the_balance_equation(self):
        keys, result = self.run_pinned(summary_statement(), {'$0.00': ('$0.00?', ['$0.00'])})
        self.assertEqual([v['text'] for v in result['values'].values()], ['$0.00'])

    def test_compensating_or_unfitting_readings_stay_held(self):
        for held in ({'14.00': ('14.00?', ['14.00']), '100.00': ('100.00?', ['100.00'])},  # two held in each control
                     {'14.00': ('14.00?', ['41.00'])},                                     # the reading does not fit
                     {'14.00': ('14.00?', ['14.00', '41.00'])}):                           # only one may fit: here one does
            with self.subTest(held=held):
                keys, result = self.run_pinned(summary_statement(), held)
                if held == {'14.00': ('14.00?', ['14.00', '41.00'])}:
                    self.assertEqual([v['text'] for v in result['values'].values()], ['14.00'])
                else:
                    self.assertEqual(result, {})

    def test_a_control_with_an_unconfirmed_cell_cannot_fix_anything(self):
        from services.financial.statement_reading_quality import pinned_card_values
        data = summary_statement()
        key = self.cell(data, '14.00')
        next(c for r in data['rows'] for c in r['cells'] if (0, r['row_index'], c['column_index']) == key)['expected_text'] = '14.00?'
        everything = {(0, r['row_index'], c['column_index']) for r in data['rows'] for c in r['cells']}
        closing, purchases = self.cell(data, '$114.00'), self.cell(data, '+ $114.00')
        # The summary purchases total alone still fixes it when only the closing balance is unconfirmed.
        self.assertTrue(pinned_card_values(self.tables(data), {key: ['14.00']}, everything - {key, closing}))
        self.assertEqual(pinned_card_values(self.tables(data), {key: ['14.00']},
                                            everything - {key, closing, purchases}), {})

    def test_a_page_without_the_end_of_its_lines_or_another_layout_is_not_judged(self):
        from services.financial.statement_reading_quality import pinned_card_values
        data = summary_statement()
        data['rows'] = [r for r in data['rows'] if 'Year-to-Date' not in r['cells'][0]['expected_text']]
        keys, result = self.run_pinned(data, {'14.00': ('14.00?', ['14.00'])})
        self.assertFalse(result)
        from services.financial.statement_reading_quality import _card_equations
        whole = summary_statement()
        rows = propose_merrick_table(whole, 'USD', merrick_statement(whole))['rows']
        self.assertTrue(_card_equations([whole], rows))
        self.assertEqual(_card_equations([data], rows), [])   # the end of the lines is not on this page
        other = summary_statement()
        for row in other['rows']:
            for c in row['cells']:
                c['expected_text'] = c['expected_text'].replace('MERRICK BANK', 'ANOTHER BANK')
        self.assertIsNone(pinned_card_values(self.tables(other), {}, set()))


class PaymentSignTests(unittest.TestCase):
    """A payment line whose minus was lost takes the credit direction only when the period's controls fix it."""

    def statement(self, payment='100.00', new='$14.00', summary_credits=None):
        data = summary_statement()
        for row in data['rows']:
            texts = [c['expected_text'] for c in row['cells']]
            if texts[:1] == ['04/23']:
                row['cells'][2]['expected_text'] = 'MOBILE PAYMENT - THANK YOU'
                row['cells'][3]['expected_text'] = payment
            if texts[:1] == ['Purchases']:
                row['cells'][1]['expected_text'] = '+ $14.00'
            if texts[:1] == ['New Balance'] and row['row_index'] == 105:
                row['cells'][1]['expected_text'] = new
        if summary_credits:
            row = deepcopy(next(r for r in data['rows'] if r['cells'][0]['expected_text'] == 'Purchases'))
            row['row_index'] += 60
            row['cells'] = row['cells'][:2]
            row['cells'][0]['expected_text'], row['cells'][1]['expected_text'] = 'Payments', summary_credits
            for cell, x in zip(row['cells'], (95, 230)):
                cell['locator'] = rectangle(212, x=x, width=45 if x == 230 else 70, height=8)
            data['rows'].insert(PURCHASES, row)
        return data

    def payment(self, data):
        checked, _ = _checked(data)
        return next(r for r in checked if 'PAYMENT' in (r['fields'].get('description') or ''))

    def test_the_balance_equation_and_summary_fix_a_lost_payment_minus(self):
        # Previous 0.00 + purchases 14.00 - payment 100.00 = new -86.00 is not printed; with the
        # printed new balance -86.00 only a credit reconciles.
        for credits in (None, '$100.00'):
            with self.subTest(summary=credits):
                line = self.payment(self.statement(new='-$86.00', summary_credits=credits))
                self.assertEqual((line['fields']['direction'], line['fields']['direction_basis'], line['issues']),
                                 ('credit', 'pinned_by_printed_controls', []))

    def test_a_payment_the_controls_do_not_fix_stays_held(self):
        for kwargs in (dict(new='$114.00'),                                  # reconciles only as a charge
                       dict(new='-$86.00', summary_credits='$90.00'),        # the summary credits differ
                       dict(new='-$86.00', summary_credits='$100.00?'),      # the summary total is unconfirmed
                       dict(new='-$87.00')):                                 # reconciles neither way
            with self.subTest(**kwargs):
                line = self.payment(self.statement(**kwargs))
                self.assertNotIn('direction', line['fields'])
                self.assertTrue(line['issues'])


class CardChargeTotalPinnedTests(unittest.TestCase):
    tables = CardPinnedReadingTests.tables

    def test_a_held_interest_total_is_fixed_by_its_charge_lines(self):
        data = summary_statement()
        interest = next(r for r in data['rows'] if r['cells'][0]['expected_text'] == '04/25')
        interest['cells'][-1]['expected_text'] = '2.50'
        total = next(r for r in data['rows'] if r['cells'][0]['expected_text'] == 'TOTAL INTEREST FOR THIS PERIOD')
        total['cells'][-1]['expected_text'] = '2.50?'
        for row in data['rows']:
            # The summary prints no interest line: its Purchases total stays 114.00.
            if row['cells'][0]['expected_text'] == 'New Balance' and row['row_index'] == 105:
                row['cells'][1]['expected_text'] = '$116.50'
        from services.financial.statement_reading_quality import pinned_card_values
        key = (0, total['row_index'], total['cells'][-1]['column_index'])
        everything = {(0, r['row_index'], c['column_index']) for r in data['rows'] for c in r['cells']}
        result = pinned_card_values(self.tables(data), {key: ['2.50']}, everything - {key})
        self.assertEqual(result['values'][key]['text'], '2.50')
        self.assertIn('interest_total', result['controls']['equations'])
        self.assertEqual(pinned_card_values(self.tables(data), {key: ['3.50']}, everything - {key}), {})

