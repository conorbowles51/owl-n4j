"""Whole-period pinned reading of held Andrews money cells (synthetic two-page sections only)."""
import unittest
from copy import deepcopy

from services.financial import andrews_period_pinning as period
from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_import_andrews import propose_andrews_statement
from tests.test_financial_statement_import_andrews import source

CONTINUED = [(15, '--- Continued on following page ---')]


def pages(first_rows, second_rows):
    """Page 1 opens share 0040; page 2 continues it (body rows start at index 9 and 5)."""
    one = source([[(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')], *first_rows, CONTINUED])
    two = source(second_rows, page=2, printed_page=2, names=False)
    return [one, two]


def record(page, cells):
    """An engine verification record: ``cells`` maps (row, column) to a status or a held cell entry."""
    entries = []
    for (row, column), value in cells.items():
        entry = dict(table_index=0, row_index=row, column_index=column, rect=[0, 0, 1, 1],
                     observations=[dict(dpi=300, text='x')] * 6)
        if value == 'confirmed':
            entry.update(status='confirmed', original_text='')
        else:
            entry.update(status='unconfirmed', **value)
        entries.append(entry)
    return dict(kind='page', page_number=page, ocr_refinements=[dict(
        method=period.VERIFICATION, page=page, decision='held', cells=entries)])


def read(sources, locations):
    statement = next(s for s in statement_catalog(sources)['statements'] if s['share_reference'] == '0040')
    chosen = [s for s in sources if s['page_number'] in statement['page_numbers']]
    proposal = propose_andrews_statement(chosen, 'USD', statement)
    return proposal, period.pin_period(proposal, chosen, 'USD', statement, locations)


def payments(proposal):
    return [r for r in proposal['rows'] if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]


class PeriodPinningTests(unittest.TestCase):
    def first_payment_held(self, readings=(('-10.00', 'page_reading_normalised'), ('-16.00', 'crop_reading')),
                           ending='65.00', second_page_extra=None):
        sources = pages(
            [[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00'), (350, '80.00')]],
            [[(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-1?.00'), (350, '70.00')],
             [(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '65.00')],
             *(second_page_extra or []),
             [(15, '06/30'), (75, 'Ending Balance'), (350, ending)]])
        held = dict(original_text='-1O.00', marked_text='-1?.00', printed_readings=[list(r) for r in readings])
        locations = [record(1, {(9, 1): 'confirmed', (10, 2): 'confirmed', (10, 3): 'confirmed'}),
                     record(2, {(5, 2): held, (5, 3): 'confirmed', (6, 2): 'confirmed', (6, 3): 'confirmed',
                                (7, 2): 'confirmed'})]
        return sources, locations

    def test_first_payment_on_a_page_is_pinned_by_the_previous_pages_balance(self):
        sources, locations = self.first_payment_held()
        before = deepcopy(sources)
        proposal, result = read(sources, locations)
        self.assertTrue(payments(proposal)[1]['issues'])
        self.assertIsNot(result, proposal)
        row = payments(result)[1]
        self.assertEqual((row['fields']['amount_minor'], row['fields']['direction'], row['fields']['balance']),
                         ('1000', 'debit', '7000'))
        self.assertEqual(row['issues'], [])
        [repair] = row['value_repairs']
        self.assertEqual((repair['method'], repair['page_reading'], repair['held_text'], repair['text'],
                          repair['accepted_reading']),
                         (period.METHOD, '-1O.00', '-1?.00', '-10.00', 'page_reading_normalised'))
        self.assertEqual(repair['pinned_by'], [[1, 0, 10, 3], [2, 0, 5, 3]])
        self.assertEqual(result['period_pinned']['reconciles'], True)
        self.assertFalse(any(r['issues'] for r in result['rows']))
        self.assertEqual(sources, before)

    def test_two_readings_that_both_reconcile_or_none_that_does_leave_it_held(self):
        for readings in ((('-10.00', 'page_reading'), ('-10.00 ', 'crop_reading')),
                         (('-16.00', 'crop_reading'),), ()):
            with self.subTest(readings=readings):
                sources, locations = self.first_payment_held(readings=readings)
                proposal, result = read(sources, locations)
                if len({r[0].strip() for r in readings}) == 1 and readings[0][0] == '-10.00':
                    # The same amount twice is one reading, not two.
                    self.assertIsNot(result, proposal)
                else:
                    self.assertIs(result, proposal)

    def test_a_neighbour_the_crops_did_not_confirm_cannot_pin(self):
        sources, locations = self.first_payment_held()
        # The previous page's last balance has no verification record.
        locations[0]['ocr_refinements'][0]['cells'] = [c for c in locations[0]['ocr_refinements'][0]['cells']
                                                       if (c['row_index'], c['column_index']) != (10, 3)]
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)

    def test_a_reading_without_stored_printed_readings_is_left_as_it_is(self):
        sources, locations = self.first_payment_held()
        for cell in locations[1]['ocr_refinements'][0]['cells']:
            cell.pop('printed_readings', None)
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)

    def test_every_held_cell_of_the_period_must_be_pinned(self):
        extra = [[(15, '06/07'), (75, 'Withdrawal Debit Card'), (310, '-?.00'), (350, '6?.00')]]
        sources, locations = self.first_payment_held(second_page_extra=extra, ending='60.00')
        locations[1]['ocr_refinements'][0]['cells'] = [c for c in locations[1]['ocr_refinements'][0]['cells']
                                                       if c['row_index'] != 7]
        locations[1]['ocr_refinements'][0]['cells'] += [
            dict(table_index=0, row_index=7, column_index=column, rect=[0, 0, 1, 1], status='unconfirmed',
                 original_text=text, marked_text=text, observations=[], printed_readings=[])
            for column, text in ((2, '-?.00'), (3, '6?.00'))]
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)

    def test_the_whole_period_must_reconcile_to_its_ending_balance(self):
        sources, locations = self.first_payment_held(ending='64.00')
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)

    def test_switch_turns_the_pass_off(self):
        sources, locations = self.first_payment_held()
        try:
            period.PERIOD_PINNING = False
            proposal, result = read(sources, locations)
        finally:
            period.PERIOD_PINNING = True
        self.assertIs(result, proposal)

    def test_a_joined_cell_at_a_page_end_needs_its_own_and_the_next_pages_control(self):
        sources = pages(
            [[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00 8?.00')]],
            [[(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-10.00'), (350, '70.00')],
             [(15, '06/30'), (75, 'Ending Balance'), (350, '70.00')]])
        held = dict(kind='pair', original_text='-20.00 8O.00', marked_text='-20.00 8?.00',
                    printed_readings=[['-20.00 80.00', 'page_reading_normalised'], ['-20.00 86.00', 'crop_reading']])
        locations = [record(1, {(9, 1): 'confirmed', (10, 2): held}),
                     record(2, {(5, 2): 'confirmed', (5, 3): 'confirmed', (6, 2): 'confirmed'})]
        proposal, result = read(sources, locations)
        self.assertIsNot(result, proposal)
        row = payments(result)[0]
        self.assertEqual((row['fields']['amount_minor'], row['fields']['balance']), ('2000', '8000'))
        self.assertEqual(row['value_repairs'][0]['pinned_by'], [[1, 0, 9, 1], [2, 0, 5, 2], [2, 0, 5, 3]])
        # Without the next page's payment only its own control holds: not enough for two unconfirmed parts.
        locations[1]['ocr_refinements'][0]['cells'] = [c for c in locations[1]['ocr_refinements'][0]['cells']
                                                       if c['row_index'] != 5]
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)


if __name__ == '__main__':
    unittest.main()
