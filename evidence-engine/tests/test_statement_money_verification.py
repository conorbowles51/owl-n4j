"""Recognised money cells are confirmed against the page image or held.

Synthetic cells only; no client documents or extracted values.
"""
import time

import fitz
import pytest

from app.pipeline import pdf_extraction as pdf
from app.pipeline import statement_money_verification as verify


def _tables(cells):
    """One measured table on a 600x800 page from ``(row, column, x, y, text)``."""
    def locator(x, y, width=40, height=8):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x, y, x + width, y + height)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = [dict(row=row, column=column, text=text, locator=locator(x, y)) for row, column, x, y, text in cells]
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=locator(0, 0, 600, 800), values=values,
            unlocated_values=0)))])


CARD = [(0, 0, 140, 270, 'EXAMPLE SHOP'), (0, 1, 430, 270, '28.11'),
        (1, 0, 140, 282, 'PAYMENT'), (1, 1, 430, 282, '-40.00'),
        (2, 0, 140, 294, 'EXAMPLE CAFE'), (2, 1, 430, 294, '15.79'),
        (3, 0, 140, 306, 'Reference 1234')]


def _run(monkeypatch, per_cell, cells=CARD, rotation=0):
    """``per_cell`` maps original text to the six crop readings for that cell."""
    def fake(page, rects, *, rotation, deadline, language):
        texts = [t for _, _, _, _, t in cells if verify.money_value(t) is not None]
        assert len(rects) == len(texts)
        return {i: [(per_cell.get(t, [t] * 6)[i], 90.0) for t in texts] for i in range(6)}
    monkeypatch.setattr(verify, 'stacked_readings', fake)
    tables = _tables(cells)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        result, records = verify.verify_money_cells(page, tables, rotation=rotation,
            deadline=time.monotonic() + 30, language='eng')
    return tables, result, records


@pytest.mark.parametrize('text,value', [
    ('28.11', (False, '2811')), ('-40.00', (True, '4000')), ('$1,234.56', (False, '123456')),
    ('- $25.00', (True, '2500')), ('25.00-', (True, '2500')), ('(12.00)', (True, '1200')),
    ('+ $114.76', (False, '11476')), ('1 234.56', None), ('2B.11', None), ('28.11?', None),
    ('12.3', None), ('--1.00', None), ('(1.00', None), ('4111 1111 1111 1111', None), ('01/04', None)])
def test_money_value_reads_only_complete_amounts(text, value):
    assert verify.money_value(text) == value


def test_cancelling_misreads_are_held_even_though_they_parse(monkeypatch):
    tables, result, records = _run(monkeypatch, {'28.11': ['25.11'] * 6, '15.79': ['18.79'] * 6})
    changed = {(c.row, c.column): c.text for c in result[0].geometry.cells
               if c.text != {(o.row, o.column): o.text for o in tables[0].geometry.cells}[(c.row, c.column)]}
    # The disputed digit is marked; the crop's digit is never substituted.
    assert changed == {(0, 1): '2?.11', (2, 1): '1?.79'}
    assert all(verify.money_value(text) is None for text in changed.values())
    assert all(a.locator == b.locator for a, b in zip(tables[0].geometry.cells, result[0].geometry.cells))
    assert '2?.11' in result[0].chunk and '25.11' not in result[0].chunk
    [record] = records
    assert (record['method'], record['decision'], record['confirmed'], record['contradicted']) == (
        verify.METHOD, 'held', 1, 2)
    held = [c for c in record['cells'] if c['status'] != 'confirmed']
    assert [(c['original_text'], c['marked_text'], c['reason']) for c in held] == [
        ('28.11', '2?.11', 'crop_readings_contradict_page_reading'),
        ('15.79', '1?.79', 'crop_readings_contradict_page_reading')]
    assert [o['text'] for o in held[0]['observations']] == ['25.11'] * 6


def test_confirmed_cells_are_unchanged_and_recorded(monkeypatch):
    tables, result, records = _run(monkeypatch, {'-40.00': ['-40.00', '-40.00', '-46.00', '-40.00', '-40.00', '']})
    assert result is tables
    assert records[0]['decision'] == 'all_confirmed' and records[0]['confirmed'] == 3


@pytest.mark.parametrize('readings,status', [
    (['25.11', '25.11', '25.11', '28.11', '28.11', '28.11'], 'unconfirmed'),   # split vote
    (['28.11', '28.11', '28.11', '', '', ''], 'unconfirmed'),                # too few agreeing
    (['', '', '', '', '', ''], 'unconfirmed'),                                  # nothing read
    (['25.11', '25.11', '25.11', '', '', ''], 'unconfirmed'),                # too few contradicting
    (['25.11', '25.11', '28.11', '25.11', '25.11', '28.11'], 'contradicted'),
    (['28.11', '28.11', '25.11', '28.11', '28.11', '25.11'], 'confirmed'),
])
def test_ambiguous_readings_are_never_admitted(monkeypatch, readings, status):
    _, result, records = _run(monkeypatch, {'28.11': readings})
    cell = next(c for c in records[0]['cells'] if c['original_text'] == '28.11')
    assert cell['status'] == status
    text = next(c.text for c in result[0].geometry.cells if (c.row, c.column) == (0, 1))
    assert (text == '28.11') == (status == 'confirmed')
    if status == 'unconfirmed':
        assert text == '28.11?'


def test_a_lost_sign_is_held_not_admitted_as_the_other_direction(monkeypatch):
    _, result, _ = _run(monkeypatch, {'-40.00': ['40.00'] * 6})
    assert next(c.text for c in result[0].geometry.cells if (c.row, c.column) == (1, 1)) == '-40.00?'


def test_rotated_pdf_pages_and_failed_verification_hold_every_money_cell(monkeypatch):
    monkeypatch.setattr(verify, 'stacked_readings', lambda *a, **k: pytest.fail('nothing to measure'))
    tables = _tables(CARD)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        result, records = verify.verify_money_cells(page, tables, deadline=time.monotonic() + 30,
            language='eng', measure=False)
    assert sorted(c.text for c in result[0].geometry.cells if '?' in c.text) == ['-40.00?', '15.79?', '28.11?']
    assert {c['reason'] for c in records[0]['cells']} == {'cell_not_measured'}


def test_tesseract_failure_holds_rather_than_admits(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('Tesseract process timeout')
    monkeypatch.setattr(verify, 'stacked_readings', broken)
    tables = _tables(CARD)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        result, records = verify.verify_money_cells(page, tables, deadline=time.monotonic() + 30, language='eng')
    assert records[0]['decision'] == 'held' and records[0]['unconfirmed'] == 3
    assert 'Tesseract process timeout' in records[0]['error']


def test_digital_pages_are_never_verified(monkeypatch):
    monkeypatch.setattr(verify, 'verify_money_cells', lambda *a, **k: pytest.fail('digital text is exact'))
    tables = _tables(CARD)
    with fitz.open() as document:
        page = document.new_page(width=600, height=800)
        chunks, result, records = pdf._verify_recognised_money(page, tables, ['c'],
            text_origin='digital_text_layer', extraction_method='native')
    assert (chunks, result, records) == (['c'], tables, [])
    assert verify.page_needs_verification('unknown', 'native')
    assert verify.page_needs_verification('digital_text_layer', 'tesseract_ocr')


def test_real_tesseract_contradicts_a_cancelling_text_layer(tmp_path):
    """The image prints 25.11 and 18.79; the invisible layer says 28.11 and 15.79."""
    lines = [(270, 'EXAMPLE SHOP', '25.11', '28.11'), (282, 'PAYMENT', '-40.00', '-40.00'),
             (294, 'EXAMPLE CAFE', '18.79', '15.79')]
    # Enough recognised words that the embedded layer is read, not replaced.
    lines += [(400 + 12 * i, f'Synthetic statement notice line number {i}', '', '') for i in range(12)]
    printed = fitz.open()
    source = printed.new_page(width=600, height=800)
    for y, label, amount, _ in lines:
        source.insert_text((140, y + 7), label, fontsize=7, fontname='helv')
        if amount:
            source.insert_text((470 - fitz.get_text_length(amount, 'helv', 7), y + 7), amount, fontsize=7, fontname='helv')
    pixmap = source.get_pixmap(dpi=200, colorspace=fitz.csGRAY, alpha=False)
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    page.insert_image(page.rect, stream=pixmap.tobytes('png'))
    for y, label, _, layer in lines:
        page.insert_text((140, y + 7), label, fontsize=7, fontname='helv', render_mode=3)
        if layer:
            page.insert_text((470 - fitz.get_text_length(layer, 'helv', 7), y + 7), layer, fontsize=7,
                fontname='helv', render_mode=3)
    path = tmp_path / 'synthetic-scan.pdf'
    document.save(path)
    document.close()
    printed.close()
    result = pdf._extract_pdf_sync(str(path))
    records = [r for span in result.metadata['page_spans'] for r in span.get('ocr_refinements') or []
               if r.get('method') == verify.METHOD]
    assert len(records) == 1 and records[0]['decision'] == 'held'
    statuses = {c['original_text']: c['status'] for c in records[0]['cells']}
    assert statuses == {'28.11': 'contradicted', '-40.00': 'confirmed', '15.79': 'contradicted'}
    text = '\n'.join(result.tables)
    assert '2?.11' in text and '1?.79' in text and '28.11' not in text
