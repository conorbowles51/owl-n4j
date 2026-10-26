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

    def test_a_recognised_reading_no_crop_repeats_is_offered_and_pinned(self):
        # The crops gave no supported reading; the page reading itself is a recognised reading.
        sources, locations = self.first_payment_held(readings=())
        held = locations[1]['ocr_refinements'][0]['cells'][0]
        held['recognised_readings'] = [['-10.00', 'page_reading_normalised'], ['-1.00', 'crop_reading']]
        proposal, result = read(sources, locations)
        self.assertIsNot(result, proposal)
        [repair] = payments(result)[1]['value_repairs']
        self.assertEqual((repair['text'], repair['accepted_reading']), ('-10.00', 'page_reading_normalised'))
        try:
            period.RECOGNISED_READINGS = False
            proposal, result = read(sources, locations)
        finally:
            period.RECOGNISED_READINGS = True
        self.assertIs(result, proposal)

    def test_an_unparseable_reading_is_skipped_not_the_cells_other_readings(self):
        sources, locations = self.first_payment_held(readings=(('10.00-', 'crop_reading'),))
        held = locations[1]['ocr_refinements'][0]['cells'][0]
        held['recognised_readings'] = [['-10.00', 'page_reading_normalised']]
        proposal, result = read(sources, locations)
        self.assertIsNot(result, proposal)
        try:
            period.RECOGNISED_READINGS = False
            proposal, result = read(sources, locations)
        finally:
            period.RECOGNISED_READINGS = True
        self.assertIs(result, proposal)

    def test_a_damaged_cell_is_held_and_pinned_from_its_recognised_readings(self):
        sources, locations = self.first_payment_held()
        cells = locations[1]['ocr_refinements'][0]['cells']
        locations[1]['ocr_refinements'][0]['cells'] = [c for c in cells if (c['row_index'], c['column_index']) != (5, 2)]
        locations[1]['ocr_refinements'][0]['damaged_cells'] = [dict(
            table_index=0, row_index=5, column_index=2, rect=[0, 0, 1, 1], status='unconfirmed', kind='single',
            original_text='-1O.00', page_money_damaged=True, observations=[dict(dpi=300, text='x')] * 6,
            recognised_readings=[['-16.00', 'crop_reading'], ['-10.00', 'crop_reading']])]
        proposal, result = read(sources, locations)
        self.assertIsNot(result, proposal)
        [repair] = payments(result)[1]['value_repairs']
        self.assertEqual((repair['text'], repair['held_text'], repair['accepted_reading']),
                         ('-10.00', '-1O.00', 'crop_reading'))
        locations[1]['ocr_refinements'][0]['damaged_cells'][0]['recognised_readings'] = [['-16.00', 'crop_reading']]
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)
        # A damaged reading that failed is no cell at all; the period stays as the reader left it.
        locations[1]['ocr_refinements'][0]['damaged_cells'] = [dict(error='timed out')]
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)

    def adjacent_held(self):
        """Payment 1 on page 2 has amount and balance held; payment 2's amount is held with glyph agreement."""
        sources = pages(
            [[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00'), (350, '80.00')]],
            [[(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, '-1?.00'), (350, '7?.00')],
             [(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, '-?.00'), (350, '65.00')],
             [(15, '06/30'), (75, 'Ending Balance'), (350, '65.00')]])
        amount = dict(original_text='-10.00', marked_text='-1?.00', printed_readings=[],
                      recognised_readings=[['-10.00', 'page_reading'], ['-16.00', 'crop_reading']])
        balance = dict(original_text='70.00', marked_text='7?.00', printed_readings=[['70.00', 'page_reading']])
        glyphs = dict(original_text='-S.00', marked_text='-?.00', printed_readings=[['-5.00', 'page_reading_normalised']],
                      page_glyphs_agree_with_crops='-5.00')
        locations = [record(1, {(9, 1): 'confirmed', (10, 2): 'confirmed', (10, 3): 'confirmed'}),
                     record(2, {(5, 2): amount, (5, 3): balance, (6, 2): glyphs, (6, 3): 'confirmed',
                                (7, 2): 'confirmed'})]
        return sources, locations

    def test_a_cell_whose_page_glyphs_and_crops_agree_pins_its_neighbours(self):
        sources, locations = self.adjacent_held()
        proposal, result = read(sources, locations)
        self.assertIsNot(result, proposal)
        first, second = payments(result)[1:3]
        self.assertEqual((first['fields']['amount_minor'], first['fields']['balance'], second['fields']['amount_minor']),
                         ('1000', '7000', '500'))
        [glyph] = second['value_repairs']
        self.assertEqual((glyph['text'], glyph['basis'], glyph['pinned_by']), ('-5.00', 'page_glyphs_agree_with_crops', []))
        self.assertEqual(first['value_repairs'][1]['pinned_by'], [[2, 0, 6, 2], [2, 0, 6, 3]])
        # Without the agreement three disputed cells share two controls: nothing is pinned.
        try:
            period.GLYPH_AGREEMENT = False
            proposal, result = read(sources, locations)
        finally:
            period.GLYPH_AGREEMENT = True
        self.assertIs(result, proposal)

    def test_a_glyph_agreement_that_does_not_reconcile_leaves_the_period_held(self):
        sources, locations = self.adjacent_held()
        locations[1]['ocr_refinements'][0]['cells'][2].update(
            page_glyphs_agree_with_crops='-6.00', printed_readings=[['-6.00', 'page_reading_normalised']])
        proposal, result = read(sources, locations)
        self.assertIs(result, proposal)


if __name__ == '__main__':
    unittest.main()


class NativeTextLayerTests(unittest.TestCase):
    """A scan recognised by its producer (native text layer, no engine crop records)."""

    def sources(self, damaged='-1O,00', joined_balance=None, ending='65.00'):
        return pages(
            [[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00'), (350, '80.00')]],
            [[(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, damaged), (350, '70.00')],
             ([(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, joined_balance)] if joined_balance else
              [(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '65.00')]),
             [(15, '06/30'), (75, 'Ending Balance'), (350, ending)]])

    def native(self, extraction='native'):
        return [dict(kind='page', page_number=p, extraction_method=extraction, ocr_refinements=[]) for p in (1, 2)]

    def test_glyph_readings(self):
        for text, expected in (('-16,30', ['-16.30']), ('479·_54', ['479.54']), ('·ll . 20', ['11.20', '-11.20']),
                               ('-22 .6 8 1351 . 77', ['-22.68 1351.77']), ('56 .. 35', ['56.35']),
                               ('-78.4 7 1096.32', ['-78.47 1096.32']), ('abc', []), ('1,234.56', ['1,234.56']),
                               ('BOO.OD', ['800.00']), ('-SO.OD', ['-50.00']), ('l.171.75', ['1171.75']),
                               ('819-82', ['819.82']), ('3207.6.8', ['3207.68']), ('1200 , 00 1437.97', ['1200.00 1437.97']),
                               ('-1000.00 l.89l..70', ['-1000.00 1891.70']), ('20?2. 82', [])):
            with self.subTest(text=text):
                self.assertEqual(period.glyph_readings(text), expected)

    def test_a_damaged_amount_on_a_native_text_page_is_pinned_by_the_printed_balances(self):
        proposal, result = read(self.sources(), self.native())
        self.assertTrue(payments(proposal)[1]['issues'])
        self.assertIsNot(result, proposal)
        row = payments(result)[1]
        self.assertEqual((row['fields']['amount_minor'], row['fields']['direction'], row['fields']['balance']),
                         ('1000', 'debit', '7000'))
        [repair] = row['value_repairs']
        self.assertEqual((repair['page_reading'], repair['text'], repair['basis']), ('-1O,00', '-10.00', period.NATIVE_BASIS))
        self.assertEqual(result['period_pinned']['basis'], period.NATIVE_BASIS)
        self.assertFalse(any(r['issues'] for r in result['rows']))

    def test_a_joined_cell_with_a_speck_for_the_minus_is_pinned(self):
        proposal, result = read(self.sources(damaged='-10.00', joined_balance='·5 . 00 65,00'), self.native())
        self.assertTrue(payments(proposal)[2]['issues'])
        row = payments(result)[2]
        self.assertEqual((row['fields']['amount_minor'], row['fields']['direction'], row['fields']['balance']),
                         ('500', 'debit', '6500'))

    def test_a_reading_the_balances_do_not_pin_is_left_held(self):
        # ('-1?,00', '65.00') is read since ONE_GLYPH: see OneGlyphTests.
        for damaged, ending in (('-1O,00', '64.00'), ('-16,00', '65.00')):
            with self.subTest(damaged=damaged, ending=ending):
                proposal, result = read(self.sources(damaged=damaged, ending=ending), self.native())
                self.assertIs(result, proposal)

    def test_engine_ocr_pages_and_unknown_pages_are_left_as_they_are(self):
        for locations in (self.native('tesseract_ocr'), [], None, self.native()[:1]):
            with self.subTest(locations=locations):
                proposal, result = read(self.sources(), locations)
                self.assertIs(result, proposal)

    def test_the_switch_turns_it_off(self):
        old = period.NATIVE_TEXT_GLYPHS
        period.NATIVE_TEXT_GLYPHS = False
        try:
            proposal, result = read(self.sources(), self.native())
            self.assertIs(result, proposal)
        finally:
            period.NATIVE_TEXT_GLYPHS = old


class JointGlyphTests(unittest.TestCase):
    """Damaged cells next to one another, each with one reading of its own glyphs, taken together."""

    def sources(self, amount='-1O,00', balance='7O.OO', next_amount='-S.OO', ending='65.00'):
        return pages(
            [[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00'), (350, '80.00')]],
            [[(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, amount), (350, balance)],
             [(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, next_amount), (350, '65.00')],
             [(15, '06/30'), (75, 'Ending Balance'), (350, ending)]])

    def native(self):
        return [dict(kind='page', page_number=p, extraction_method='native', ocr_refinements=[]) for p in (1, 2)]

    def test_adjacent_damaged_cells_are_taken_together_when_every_control_holds(self):
        proposal, result = read(self.sources(), self.native())
        self.assertIsNot(result, proposal)
        moves = [(r['fields']['amount_minor'], r['fields']['direction'], r['fields']['balance']) for r in payments(result)]
        self.assertEqual(moves[1:], [('1000', 'debit', '7000'), ('500', 'debit', '6500')])
        bases = {repair['basis'] for row in payments(result) for repair in row.get('value_repairs') or []}
        self.assertEqual(bases, {period.JOINT_BASIS})
        self.assertFalse(any(r['issues'] for r in result['rows']))

    def test_a_colon_printed_for_the_point_is_a_reading(self):
        self.assertEqual(period.glyph_readings('1055:74'), ['1055.74'])
        self.assertEqual(period.glyph_readings('20.00 1055:74'), ['20.00 1055.74'])

    def test_readings_that_do_not_hold_together_are_left_held(self):
        for kwargs in (dict(next_amount='-6.OO'), dict(balance='7l.OO'), dict(ending='64.00')):
            with self.subTest(**kwargs):
                proposal, result = read(self.sources(**kwargs), self.native())
                self.assertIs(result, proposal)

    def test_the_switch_turns_it_off(self):
        old = period.JOINT_GLYPHS
        period.JOINT_GLYPHS = False
        try:
            proposal, result = read(self.sources(), self.native())
            self.assertIs(result, proposal)
        finally:
            period.JOINT_GLYPHS = old


class OneGlyphTests(unittest.TestCase):
    """A native text cell with one glyph that is no digit, the digit fixed twice by printed balances."""

    def sources(self, amount='-10.00', balance='70.00', next_amount='-5.00', next_balance='65.00', ending='65.00'):
        return pages(
            [[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00'), (350, '80.00')]],
            [[(15, '06/05'), (75, 'Withdrawal Debit Card'), (310, amount), *([(350, balance)] if balance else [])],
             [(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, next_amount), (350, next_balance)],
             [(15, '06/30'), (75, 'Ending Balance'), (350, ending)]])

    def native(self):
        return [dict(kind='page', page_number=p, extraction_method='native', ocr_refinements=[]) for p in (1, 2)]

    def moves(self, result):
        return [(r['fields']['amount_minor'], r['fields']['direction'], r['fields']['balance']) for r in payments(result)]

    def test_one_glyph_readings(self):
        self.assertEqual([r for r, _ in period.one_glyph_readings('~293.42')][:3], ['0293.42', '1293.42', '2293.42'])
        self.assertEqual({part for _, part in period.one_glyph_readings('-60.00 20?2. 82')}, {'balance'})
        self.assertIn(('-43.07 1346.69', 'amount'), period.one_glyph_readings("-43.0'Z 1346.69"))
        self.assertEqual(period.one_glyph_readings('-66.00 1052.69'), [])   # a digit read wrongly is no glyph
        self.assertEqual(period.one_glyph_readings('??.00'), [])            # two unread glyphs

    def test_a_balance_with_one_unread_glyph_is_the_digit_both_payments_fix(self):
        proposal, result = read(self.sources(balance='7?.00'), self.native())
        self.assertIsNot(result, proposal)
        self.assertEqual(self.moves(result)[1:], [('1000', 'debit', '7000'), ('500', 'debit', '6500')])
        [repair] = payments(result)[1]['value_repairs']
        self.assertEqual((repair['page_reading'], repair['text'], repair['basis']), ('7?.00', '70.00', period.ONE_GLYPH_BASIS))
        self.assertFalse(any(r['issues'] for r in result['rows']))

    def test_a_speck_for_a_digit_of_a_joined_balance_is_read(self):
        proposal, result = read(self.sources(amount='-10.00 ~0.00', balance=None), self.native())
        self.assertEqual(self.moves(result)[1], ('1000', 'debit', '7000'))

    def test_an_amount_with_one_unread_glyph_needs_both_its_balances_confirmed(self):
        for amount in ('-1?,00', '-1Z.00'):
            with self.subTest(amount=amount):
                proposal, result = read(self.sources(amount=amount), self.native())
                self.assertEqual(self.moves(result)[1], ('1000', 'debit', '7000'))
        # The first payment after the opening balance: no other control confirms the balance before it.
        sources = pages([[(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-2?.00'), (350, '80.00')]],
                        [[(15, '06/06'), (75, 'Withdrawal Debit Card'), (310, '-5.00'), (350, '75.00')],
                         [(15, '06/30'), (75, 'Ending Balance'), (350, '75.00')]])
        proposal, result = read(sources, self.native())
        self.assertIs(result, proposal)

    def test_a_digit_the_balances_do_not_fix_twice_is_left_held(self):
        for kwargs in (dict(balance='7?.00', next_amount='-6.00'),    # the payment after it disagrees
                       dict(balance='??.00'),                         # two unread glyphs
                       dict(balance='76.00 x'),                       # no reading at all
                       dict(amount='-1?.00', ending='64.00')):        # the period does not reconcile
            with self.subTest(**kwargs):
                proposal, result = read(self.sources(**kwargs), self.native())
                self.assertIs(result, proposal)

    def test_the_switch_turns_it_off(self):
        old = period.ONE_GLYPH
        period.ONE_GLYPH = False
        try:
            proposal, result = read(self.sources(balance='7?.00'), self.native())
            self.assertIs(result, proposal)
        finally:
            period.ONE_GLYPH = old
