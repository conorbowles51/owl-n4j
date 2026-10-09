"""Crop readings that miss or misread a decimal or grouping mark still confirm the page's figures.

Synthetic cells only; no client documents or extracted values.
"""
import pytest

from app.pipeline import statement_money_verification as verify
from tests.test_statement_money_verification import _run

CELLS = [(0, 0, 140, 270, 'EXAMPLE SHOP'), (0, 1, 430, 270, '23.45'),
         (1, 0, 140, 282, 'PAYMENT'), (1, 1, 430, 282, '-40.00'),
         (2, 0, 140, 294, 'Previous Balance'), (2, 1, 430, 294, '$1,234.56')]


def _status(monkeypatch, text, readings):
    _, result, records = _run(monkeypatch, {text: readings}, cells=CELLS)
    cell = next(c for c in records[0]['cells'] if c['original_text'] == text)
    return cell['status'], next(c.text for c in result[0].geometry.cells if c.text.startswith(text[:2]))


@pytest.mark.parametrize('text,readings', [
    ('23.45', ['2345', '23.45', '2345', '2345', '23.45', '2345']),                 # point lost at some profiles
    ('$1,234.56', ['$1.23456', '$1.234.56', '$1,234.50', '$1.23456', '$1.234.56', '']),  # comma read as point
    ('-40.00', ['-4000', '-40.00', '', '-4000', '-40.00', '']),
])
def test_figures_read_without_their_marks_confirm_the_page_reading(monkeypatch, text, readings):
    assert _status(monkeypatch, text, readings) == ('confirmed', text)


@pytest.mark.parametrize('text,readings', [
    ('23.45', ['2335', '2335', '2335', '2335', '23.45', '2335']),   # other figures: never a contradiction either
    ('23.45', ['2345', '2345', '2345', '', '', '']),                # one resolution only
    ('-40.00', ['4000', '4000', '4000', '4000', '4000', '4000']),   # the sign differs
    ('23.45', ['23450', '23450', '23450', '23450', '23450', '23450']),
])
def test_mark_free_readings_never_confirm_other_figures_or_sign(monkeypatch, text, readings):
    status, value = _status(monkeypatch, text, readings)
    assert status == 'unconfirmed' and verify.money_value(value) is None


def test_mark_free_readings_are_never_a_value_of_their_own():
    # A crop reading without marks can confirm a page reading; it never contradicts or replaces one.
    observations = [dict(text='2335', dpi=dpi) for dpi in (300, 300, 300, 450, 450, 450)]
    assert verify.classify('23.45', observations) == ('unconfirmed', None)
    assert verify.crop_money_value('2335') is None


def _figures_run(monkeypatch, row, crops):
    """Verify one card row ``(date, description, amount)``; ``crops`` maps a cell text to its six readings."""
    import time
    import fitz
    from tests.test_statement_money_verification import _tables
    cells = [(0, 0, 60, 270, row[0]), (0, 1, 140, 270, row[1]), (0, 2, 430, 270, row[2]),
             (1, 0, 60, 282, '01/06'), (1, 1, 140, 282, 'EXAMPLE CAFE'), (1, 2, 430, 282, '15.79')]
    tables = _tables(cells)
    by_rect = {tuple(c.locator.to_json()['rect']): c.text for c in tables[0].geometry.cells}

    def fake(page, rects, *, rotation, deadline, language):
        texts = [by_rect[tuple(rect)] for rect in rects]
        return {i: [(crops.get(t, [t] * 6)[i], 90.0) for t in texts] for i in range(6)}
    monkeypatch.setattr(verify, 'stacked_readings', fake)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        result, records = verify.verify_money_cells(page, tables, deadline=time.monotonic() + 30, language='eng')
    text = next(c.text for c in result[0].geometry.cells if (c.row, c.column) == (0, 2))
    return text, records[0]


def test_an_amount_whose_point_the_page_reading_lost_takes_the_point_the_crops_read(monkeypatch):
    text, record = _figures_run(monkeypatch, ('01/05', 'EXAMPLE SHOP', '6789'), {'6789': ['67.89'] * 6})
    assert text == '67.89'
    cell = next(c for c in record['cells'] if c['row_index'] == 0)
    assert (cell['kind'], cell['reason'], cell['original_text']) == (
        'figures', 'page_figures_confirmed_by_crops_with_their_point', '6789')


@pytest.mark.parametrize('row,crops', [
    (('01/05', 'EXAMPLE SHOP', '6789'), ['67.89', '67.89', '67.89', '', '', '']),     # one resolution only
    (('01/05', 'EXAMPLE SHOP', '6789'), ['67.83'] * 6),                               # other figures
    (('01/05', 'EXAMPLE SHOP', '6789'), ['-67.89'] * 6),                              # a sign the page never read
    (('01/05', 'EXAMPLE SHOP', '6789'), ['6789'] * 6),                                # no point read either
    (('REF', 'EXAMPLE SHOP', '6789'), ['67.89'] * 6),                                 # the row has no printed date
])
def test_figures_stay_exactly_as_read_unless_the_crops_read_that_amount(monkeypatch, row, crops):
    text, record = _figures_run(monkeypatch, row, {'6789': crops})
    assert text == '6789'
    assert not any(c['row_index'] == 0 for c in record['cells'])
    assert record['decision'] == 'all_confirmed'
