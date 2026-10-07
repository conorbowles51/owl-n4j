"""Money cells as real text-layer scans print and crop-read them; synthetic values only."""
import pytest

from app.pipeline import statement_money_verification as verification


def six(texts):
    return [dict(dpi=300 if i < 3 else 450, threshold=0, text=t) for i, t in enumerate(texts)]


@pytest.mark.parametrize('text, value', [
    ('-13.01', (True, '1301')), ('-13,01', (True, '1301')), ('7.00.', (False, '700')), ('31.00,', (False, '3100')),
    ('-1,234,56', (True, '123456')), ('1,234.56', (False, '123456')), ('- 4 5 . 67', (True, '4567')),
    ('1,234', None), ('12,345', None), ('1.234,56', None), ('-88..12', None), ('13.571', None), ('+-11.00', None),
])
def test_a_crop_reading_states_its_amount_whatever_mark_it_read_for_the_point(text, value):
    assert verification.crop_money_value(text) == value


def test_a_page_reading_with_only_its_decimal_mark_wrong_is_reread_but_never_confirmed():
    assert verification.separator_garbled_money('-16,61') == (True, '1661')
    assert verification.separator_garbled_money('-16.61') is None
    assert verification.separator_garbled_money('“16.61') is None
    assert verification.classify('-16,61', six(['-16.61'] * 6)) == ('contradicted', '-16.61')


def test_crop_readings_confirm_by_amount_not_by_the_glyph_read_for_the_point():
    assert verification.classify('-13.01', six(['-13,01'] * 5 + ['-13.01'])) == ('confirmed', None)
    assert verification.classify('-13.01', six(['-13,01', '-13,01', '-13.02', '-13.02', '-13.02', '-13.02'])) == (
        'contradicted', '-13.02')
    assert verification.classify('-13.01', six(['-13,01', '-13,01', '-13.02', '-13.02', '', ''])) == ('unconfirmed', None)


@pytest.mark.parametrize('text, value', [
    ('-56.781234.56', ((True, '5678'), (False, '123456'))),
    ('-56.78 1234.56', ((True, '5678'), (False, '123456'))),
    ('-2,104321.98', ((True, '210'), (False, '432198'))),
    ('-30.006543,.21', None),
    ('-56.78', None),
])
def test_a_joined_amount_and_balance_reading_splits_only_one_way(text, value):
    assert verification.crop_money_pair(text) == value


def test_a_joined_amount_and_balance_cell_is_confirmed_when_both_amounts_agree():
    assert verification.classify('-56.78 1234.56', six(['-56.781234.56'] * 6), 'pair') == ('confirmed', None)
    assert verification.classify('-56.78 1234.56', six(['-56.781234.57'] * 6), 'pair')[0] == 'contradicted'
    assert verification.money_text(((True, '5678'), (False, '123456'))) == '-56.78 1234.56'


@pytest.mark.parametrize('cell, expected', [
    # A page reading whose decimal mark is wrong is offered in its canonical form.
    (dict(original_text='-16,61', observations=six(['-16.61'] * 6)), [('-16.61', 'page_reading_normalised')]),
    # Spaces OCR put between digits are the reader's own reading of the cell.
    (dict(original_text='512. 3 4', kind='spaced', observations=six(['512.34'] * 2 + ['512.33'] * 4)),
     [('512. 3 4', 'page_reading'), ('512.33', 'crop_reading')]),
    # A joined cell offers whole readings of both amounts.
    (dict(original_text='-30.00 6543.21', kind='pair', observations=six(['-30.006543,.21'] * 3 + ['-30.006543.21'] * 3)),
     [('-30.00 6543.21', 'page_reading')]),
    (dict(original_text='-62,15 2468.13', kind='pair', observations=six(['-62.152468.13'] * 6)),
     [('-62.15 2468.13', 'page_reading_normalised')]),
    # A minus read as a middle dot is an unreadable sign glyph.
    (dict(original_text='·41.00', observations=six(['-41.00'] * 6)), [('-41.00', 'crop_reading')]),
])
def test_held_scan_cells_offer_the_readings_the_print_gave(cell, expected):
    assert verification._printed_readings(dict(cell, rect=[1, 2, 3, 4])) == expected


@pytest.mark.parametrize('printed, readings, expected', [
    # Letters the layer put for printed digits are accounted for by the date the crops read.
    ('Ol/l9', ['01/19'] * 6, '01/19'),
    ('O l / l 4', ['01/14'] * 4 + ['0/14', ''], '01/14'),
    ('O l / l 4', ['01/14'] * 4 + ['01/15', ''], None),
    # A digit the page read differently is not a look-alike: the cell stays unreadable.
    ('Ol/l8', ['01/19'] * 6, None),
    # Outside the printed period, too few agreeing readings, or a first reading that failed.
    ('Ol/l9', ['02/19'] * 6, None),
    ('Ol/l9', ['01/19'] * 3 + ['01/18'] * 3, None),
    ('Ol/l9', [''] + ['01/19'] * 5, None),
])
def test_an_unreadable_andrews_row_date_is_read_from_its_own_cell(monkeypatch, printed, readings, expected):
    from datetime import date
    from app.pipeline import financial_amount_ocr as amounts
    monkeypatch.setattr(amounts, '_cleaned_line_readings', lambda *args, **kwargs: [
        dict(dpi=300 if i < 3 else 450, text=t) for i, t in enumerate(readings)])
    value, observations = amounts._reread_row_date(None, [0, 0, 1, 1], printed,
        (date(2021, 1, 1), date(2021, 1, 31)), 0, 'eng')
    assert value == expected and len(observations) == 6


def test_a_decimal_mark_the_crops_read_as_a_point_is_confirmed_in_canonical_form():
    assert verification._normalised_reading('-16,61', six(['-16.61'] * 4 + ['-16,61', '16.61']), 'single') == '-16.61'
    assert verification._normalised_reading('-62,15 2468.13', six(['-62.152468.13'] * 6), 'pair') == '-62.15 2468.13'
    # Fewer than four agreeing readings, or agreement at one size only, stays held for the controls.
    assert verification._normalised_reading('-16,61', six(['-16.61'] * 3 + ['-16.56'] * 3), 'single') is None
    assert verification._normalised_reading('-16,61', six(['-16.16'] * 3 + ['-16.61'] * 3), 'single') is None
    # A complete page reading is never rewritten.
    assert verification._normalised_reading('-16.61', six(['-16.61'] * 6), 'single') is None
    assert verification._normalised_reading('-56.78 1234.56', six(['-56.781234.56'] * 6), 'pair') is None


@pytest.mark.parametrize('text, kind, value', [
    ('-B7.65', 'single', (True, '8765')), ('o.oo', 'single', (False, '000')), ('-S6.OD', 'single', (True, '5600')),
    ('-B4.21 9B76.54', 'pair', ((True, '8421'), (False, '987654'))), ('-37.20 i234.56', 'pair', ((True, '3720'), (False, '123456'))),
    ('-56.78', 'single', None), ('-X6.00', 'single', None), ("-52.0'Z", 'single', None),
])
def test_letters_measured_to_stand_for_digits_are_read_only_as_those_digits(text, kind, value):
    assert verification.lookalike_money(text, kind) == value


def test_a_letter_for_a_digit_is_only_a_candidate_for_the_agreed_controls():
    assert verification._normalised_reading('-B7.65', six(['-87.65'] * 6), 'single') is None
    assert verification._printed_readings(dict(original_text='-B7.65', rect=[1, 2, 3, 4], observations=six(
        ['-87.65'] * 6))) == [('-87.65', 'page_reading_normalised')]
    assert verification._printed_readings(dict(original_text='-B7.65', rect=[1, 2, 3, 4], observations=six(
        ['-87.65', '-37.65', '-37.65', '-37.65', '-37.65', '-37.65']))) == [
        ('-87.65', 'page_reading_normalised'), ('-37.65', 'crop_reading')]


def test_each_part_of_a_joined_cell_is_confirmed_on_its_own():
    # Measured pattern: the 300 dpi crops read the balance's last digit differently, the amount identically.
    readings = six(['-6.244948.63'] * 3 + ['-6.244948.62'] * 3)
    assert verification.classify('-6.24 4948.62', readings, 'pair')[0] == 'unconfirmed'
    assert verification.confirmed_parts('-6.24 4948.62', readings) == ['amount']
    assert verification.confirmed_parts('-310.00 4638.62', six(['-310,004638.63'] * 3 + ['-310.004638.62'] * 3)) == ['amount']
    assert verification.confirmed_parts('-3.00 2432.81', six(['-23.00 2432.81'] * 2 + ['-2.00 2432.81', '-3,00 2432.81',
                                                                '-3,002433.81', '-2,002432.81'])) == ['balance']
    assert verification.confirmed_parts('-6.24 4948.62', six(['-6.244948.63'] * 3 + ['-6.294948.62'] * 3)) == []
    # Candidates keep the confirmed part's page value.
    cell = dict(original_text='-6.24 4948.62', kind='pair', rect=[1, 2, 3, 4], observations=readings,
                confirmed_parts=['amount'])
    assert verification._printed_readings(cell) == [('-6.24 4948.62', 'page_reading')]
