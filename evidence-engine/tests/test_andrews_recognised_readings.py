"""Andrews held money cells: every reading a recogniser stated, damaged cells, glyph agreement. Synthetic values only."""
import time

import fitz
import pytest

from app.pipeline import pdf_extraction as pdf
from app.pipeline import statement_money_verification as verification


def six(texts):
    return [dict(dpi=300 if i < 3 else 450, threshold=0, text=t) for i, t in enumerate(texts)]


def cell(text, texts, **extra):
    return dict(original_text=text, rect=[1, 2, 3, 4], observations=six(texts), **extra)


def test_the_page_reading_is_offered_even_when_no_crop_repeats_it():
    # The crops join a dash between the amount and the balance; the page reading has none.
    held = cell('-41.07 2315.20', ['-41.07-2315.20'] * 6, kind='pair')
    assert verification._printed_readings(held) == [('-41.07 -2315.20', 'crop_reading')]
    assert verification.recognised_readings(held) == [('-41.07 2315.20', 'page_reading'),
                                                      ('-41.07 -2315.20', 'crop_reading')]


def test_a_minus_the_crops_read_as_a_point_leaves_the_page_reading_offered():
    held = cell('-57.13 3821.44', ['.57.133821.44'] * 5 + ['57.13 3821.44'], kind='pair')
    assert verification._printed_readings(held) == []
    assert verification.recognised_readings(held) == [('-57.13 3821.44', 'page_reading'),
                                                      ('57.13 3821.44', 'crop_reading')]


def test_each_distinct_crop_amount_is_offered_once_whatever_its_count():
    held = cell('-317.42', ['-317.48', '-317.48', '-317.48', '-317.42', '-317,42', '-317.47'])
    assert verification.recognised_readings(held) == [('-317.42', 'page_reading'), ('-317.48', 'crop_reading'),
                                                      ('-317.47', 'crop_reading')]


def test_a_page_reading_with_look_alike_glyphs_is_offered_as_its_interpretation():
    held = cell('-50.00 4S12 .O7', ['-50.00 4812.07'] * 6, kind='pair')
    assert verification.recognised_readings(held) == [('-50.00 4512.07', 'page_reading_normalised'),
                                                      ('-50.00 4812.07', 'crop_reading')]


def test_nothing_is_offered_without_every_crop_profile():
    assert verification.recognised_readings(dict(original_text='-1.00', rect=[1, 2, 3, 4],
                                                 observations=six(['-1.00'] * 6)[:5])) == []
    assert verification.recognised_readings(dict(original_text='-1.00', observations=six(['-1.00'] * 6))) == []


@pytest.mark.parametrize('text, texts, kind, agreed', [
    ('-63,4l', ['-63.41', '-63.41', '-63.44', '-63.41', '-63.42', '-63.41'], 'single', '-63.41'),
    ('-48.25 2716.3i', ['-48.252716.31'] * 6, 'pair', '-48.25 2716.31'),
    # The crops' majority states other digits than the page's glyphs.
    ('-63,4l', ['-63.44'] * 6, 'single', None),
    # Agreement at one resolution only.
    ('-63,4l', ['-63.41'] * 3 + ['-63.44'] * 3, 'single', None),
    # A page reading without look-alike glyphs is the ordinary confirmation, not this one.
    ('-63.41', ['-63.41'] * 6, 'single', None),
    # A dropped minus is not the page's amount.
    ('-63,4l', ['63.41'] * 6, 'single', None),
])
def test_page_glyphs_agree_with_crops_only_on_exactly_the_same_amount(text, texts, kind, agreed):
    assert verification.page_glyphs_agree_with_crops(cell(text, texts, kind=kind)) == agreed


def _tables(cells):
    def locator(x, y, width=40, height=8):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x, y, x + width, y + height)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = [dict(row=row, column=column, text=text, locator=locator(x, y)) for row, column, x, y, text in cells]
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=locator(0, 0, 600, 800), values=values,
            unlocated_values=0)))])


PAGE = [(0, 0, 40, 270, '03/02'), (0, 1, 90, 270, 'Withdrawal Debit Card'), (0, 2, 330, 270, '-12.73 1987:40'),
        (1, 0, 40, 282, '03/03'), (1, 1, 90, 282, 'Withdrawal Debit Card'), (1, 2, 330, 282, '-7.31'),
        (1, 3, 430, 282, '1980.09'),
        (2, 0, 40, 294, '03/04'), (2, 1, 90, 294, 'Deposit Transfer'), (2, 2, 330, 294, '20.00'),
        (2, 3, 430, 294, '20O0;30'),
        (3, 0, 40, 306, 'Total Fees'), (3, 1, 330, 306, 'l:00'),
        (4, 0, 40, 318, '03/05'), (4, 1, 90, 318, 'Ref 1234 5678'), (4, 2, 330, 318, '-3.00'),
        (4, 3, 430, 318, '1997.30')]


def _verify(monkeypatch, andrews=True, damaged=True):
    calls = []

    def fake(page, rects, *, rotation, deadline, language):
        calls.append(len(rects))
        if len(calls) == 1:
            texts = ['-7.31', '1980.09', '20.00', '-3.00', '1997.30']
            return {i: [(t, 90.0) for t in texts] for i in range(6)}
        return {i: [(t, 80.0) for t in ['-12.731987.40', '2000.30']] for i in range(6)}
    monkeypatch.setattr(verification, 'stacked_readings', fake)
    monkeypatch.setattr(verification, '_andrews_page', lambda tables: andrews)
    monkeypatch.setattr(verification, 'CROP_DAMAGED_MONEY', damaged)
    tables = _tables(PAGE)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        result, records = verification.verify_money_cells(page, tables, deadline=time.monotonic() + 30,
                                                          language='eng')
    return tables, result, records, calls


def test_damaged_money_cells_of_payment_rows_are_cropped_on_their_own_and_their_text_kept(monkeypatch):
    tables, result, records, calls = _verify(monkeypatch)
    # The ordinary money cells are read exactly as before, in their own call; the damaged ones after.
    assert calls == [5, 2]
    record = records[0]
    assert record['decision'] == 'all_confirmed'
    damaged = {c['original_text']: c for c in record['damaged_cells']}
    # A summary row (no printed date) and a description cell are never taken for money.
    assert set(damaged) == {'-12.73 1987:40', '20O0;30'}
    assert damaged['-12.73 1987:40']['kind'] == 'pair' and damaged['20O0;30']['kind'] == 'single'
    assert all(c['status'] == 'unconfirmed' and c['page_money_damaged'] for c in damaged.values())
    assert damaged['-12.73 1987:40']['recognised_readings'] == [['-12.73 1987.40', 'crop_reading']]
    assert damaged['20O0;30']['recognised_readings'] == [['2000.30', 'crop_reading']]
    # Nothing on the page changes.
    assert [c.text for c in result[0].geometry.cells] == [c.text for c in tables[0].geometry.cells]


@pytest.mark.parametrize('andrews, damaged', [(False, True), (True, False)])
def test_damaged_cells_are_cropped_only_on_andrews_pages_with_the_switch_on(monkeypatch, andrews, damaged):
    _, _, records, calls = _verify(monkeypatch, andrews=andrews, damaged=damaged)
    assert calls == [5] and 'damaged_cells' not in records[0]


def test_held_andrews_cells_store_recognised_readings_and_glyph_agreement(monkeypatch):
    cells = [(0, 0, 40, 270, '03/02'), (0, 1, 90, 270, 'Withdrawal'), (0, 2, 330, 270, '-63,4l'),
             (0, 3, 430, 270, '117.40')]

    def fake(page, rects, *, rotation, deadline, language):
        crops = [['-63.41', '117.40']] * 2 + [['-63.44', '117.40']] + [['-63.41', '117.40']] * 3
        return {i: [(t, 90.0) for t in crops[i]] for i in range(6)}
    monkeypatch.setattr(verification, 'stacked_readings', fake)
    monkeypatch.setattr(verification, '_andrews_page', lambda tables: True)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        _, records = verification.verify_money_cells(page, _tables(cells), deadline=time.monotonic() + 30,
                                                     language='eng')
    held = {c['original_text']: c for c in records[0]['cells']}['-63,4l']
    assert held['status'] != 'confirmed'
    assert held['recognised_readings'] == [['-63.41', 'page_reading_normalised'], ['-63.44', 'crop_reading']]
    assert held['page_glyphs_agree_with_crops'] == '-63.41'
