"""A printed minus that the crop readings lose is confirmed only by its measured mark.

Synthetic cells and synthetic printed pages only; no client documents or values.
"""
import time

import fitz
import pytest

from app.pipeline import pdf_extraction as pdf
from app.pipeline import statement_money_verification as verify

RECT = (430, 282, 470, 290)


def _tables(text):
    locator = dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in RECT],
                   page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    whole = dict(kind='page_rectangle', page=1, rect=[0, 0, 600000, 800000],
                 page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = [dict(row=0, column=0, text='PAYMENT', locator=dict(locator, rect=[140000, 282000, 200000, 290000])),
              dict(row=0, column=1, text=text, locator=locator)]
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=whole, values=values, unlocated_values=0)))])


def _verify(monkeypatch, printed, page_text, crops):
    """Print ``printed`` right-aligned in the money cell, then verify the page reading ``page_text``."""
    monkeypatch.setattr(verify, 'stacked_readings', lambda page, rects, **_: {i: [(crops[i], 90.0)] for i in range(6)})
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        if printed:
            page.insert_text((RECT[2] - fitz.get_text_length(printed, 'helv', 7), RECT[3] - 1), printed,
                             fontsize=7, fontname='helv')
        result, records = verify.verify_money_cells(page, _tables(page_text), deadline=time.monotonic() + 30,
                                                    language='eng')
    cell = next(c for c in records[0]['cells'] if c['column_index'] == 1)
    text = next(c.text for c in result[0].geometry.cells if c.column == 1)
    return cell, text


DROPPED = ['40.00', '-40.00', '40.00', '-40.00-', '40.00', '-40.00']


def test_printed_minus_lost_by_the_crops_is_confirmed_by_its_measured_mark(monkeypatch):
    cell, text = _verify(monkeypatch, '-40.00', '-40.00', DROPPED)
    assert (cell['status'], cell['reason'], text) == ('confirmed', 'crop_figures_confirmed_printed_minus_measured',
                                                      '-40.00')
    assert cell['sign_mark']['side'] == 'lead' and cell['sign_mark']['dpi'] == verify.SIGN_DPI


def test_trailing_printed_minus_is_measured_on_its_own_side(monkeypatch):
    cell, text = _verify(monkeypatch, '40.00-', '40.00-', ['40.00'] * 6)
    assert (cell['status'], text) == ('confirmed', '40.00-')
    assert cell['sign_mark']['side'] == 'trail'


@pytest.mark.parametrize('printed', ['40.00', '_40.00', '=40.00', '.40.00'],
                         ids=['no-mark', 'underscore', 'two-bars', 'speck'])
def test_a_minus_the_print_does_not_show_stays_held(monkeypatch, printed):
    cell, text = _verify(monkeypatch, printed, '-40.00', ['40.00'] * 6)
    assert cell['status'] != 'confirmed' and text == '-40.00?' and 'sign_mark' not in cell


def test_a_minus_printed_after_the_figures_does_not_confirm_one_read_before_them(monkeypatch):
    cell, text = _verify(monkeypatch, '40.00-', '-40.00', ['40.00'] * 6)
    assert cell['status'] != 'confirmed' and text == '-40.00?'


@pytest.mark.parametrize('crops', [
    ['40.00', '40.00', '40.00', '+40.00', '40.00', '40.00'],   # a crop shows a plus
    ['40.00', '40.00', '40.00', '', '', ''],                   # figures not agreed at both resolutions
    ['46.00', '46.00', '40.00', '46.00', '46.00', '40.00'],    # the crops state other figures
])
def test_the_crops_must_agree_on_every_figure_and_show_no_plus(monkeypatch, crops):
    cell, text = _verify(monkeypatch, '-40.00', '-40.00', crops)
    assert cell['status'] != 'confirmed' and text != '-40.00'


def test_positive_amounts_never_take_a_measured_minus(monkeypatch):
    cell, text = _verify(monkeypatch, '-40.00', '40.00', ['40.00'] * 6)
    # The page reading is unsigned and the crops agree: confirmed exactly as before, unsigned.
    assert (cell['status'], text) == ('confirmed', '40.00') and 'sign_mark' not in cell


def test_an_s_read_for_the_dollar_sign_is_confirmed_only_when_the_crops_read_the_dollar_sign(monkeypatch):
    cell, text = _verify(monkeypatch, None, 'S0.45-', ['$0.45-'] * 6)
    assert (cell['status'], cell['reason'], text) == ('confirmed', 'page_dollar_sign_confirmed_by_crops', '$0.45-')
    assert cell['page_dollar_sign_unreadable'] and cell['normalised_text'] == '$0.45-'


@pytest.mark.parametrize('crops', [['0.00'] * 6, ['50.00'] * 6, ['$0.00'] * 3 + [''] * 3])
def test_an_s_that_the_crops_do_not_read_as_a_dollar_sign_stays_held(monkeypatch, crops):
    cell, text = _verify(monkeypatch, None, 'S0.00', crops)
    assert cell['status'] != 'confirmed' and verify.money_value(text) is None


def test_an_s_read_for_the_dollar_sign_is_offered_to_the_pinned_rule_with_its_sign_never_as_a_five():
    observations = [dict(text=t, dpi=d, threshold=0) for t, d in
                    (('80.45', 300), ('$0.45', 300), ('', 300), ('$0.45-', 450), ('$0.45-', 450), ('$0.45-', 450))]
    readings = verify._printed_readings(dict(original_text='S0.45-', observations=observations, rect=[1, 1, 2, 2]))
    assert ('$0.45-', 'page_reading_normalised') in readings
    assert not any(text.startswith('50') or text.startswith('-50') for text, _ in readings)
