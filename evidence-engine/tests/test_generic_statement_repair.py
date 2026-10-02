"""Synthetic generic labelled statement cells through the native-cell repair path."""
from dataclasses import replace
import time

import fitz
import pytest
from app.pipeline import financial_amount_ocr as cells
from app.pipeline import pdf_extraction as pdf

FONT = 7


def _width(text):
    return fitz.get_text_length(text, fontname='helv', fontsize=FONT)


def lines(debit='8S.13', balance='15,471.04'):
    """(x, align, text) per printed line, positioned as the corpus generic layout prints them."""
    return [
        [(40, 'left', 'Bank: Example Synthetic Bank')],
        [(40, 'left', 'Account Name: Example Holder LLC')],
        [(40, 'left', 'Account Number: 11112222')],
        [(40, 'left', 'Currency: USD')],
        [(40, 'left', 'Statement Period: March 1, 2023 - March 31, 2023')],
        [(40, 'left', 'Date'), (120, 'left', 'Description'), (380, 'right', 'Credit'),
         (460, 'right', 'Debit'), (560, 'right', 'Balance')],
        [(40, 'left', '2023-03-01'), (120, 'left', 'Opening Balance'), (560, 'right', '15,556.17')],
        [(40, 'left', '2023-03-08'), (120, 'left', 'Card purchase B'), (460, 'right', debit),
         (560, 'right', balance)],
        [(40, 'left', '2023-03-31'), (120, 'left', 'Closing Balance'), (560, 'right', '15,471.04')],
    ]


def _y(row):
    return 40 + row * 14


def tables(**printed):
    def locator(x0, y0, x1, y1):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x0, y0, x1, y1)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = []
    for row, line in enumerate(lines(**printed)):
        for column, (x, align, text) in enumerate(line):
            left = x - _width(text) if align == 'right' else x
            values.append(dict(row=row, column=column, text=text,
                locator=locator(left, _y(row), left + _width(text), _y(row) + 9.6)))
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=locator(0, 0, 600, 800), values=values,
        unlocated_values=0)))])


def printed_page(doc):
    """The page image prints the true values, as a scan beneath a damaged text layer does."""
    page = doc.new_page(width=600, height=800)
    for row, line in enumerate(lines(debit='85.13')):
        for x, align, text in line:
            left = x - _width(text) if align == 'right' else x
            page.insert_text((left, _y(row) + FONT), text, fontsize=FONT, fontname='helv')
    return page


def observations(values):
    return [dict(text=value, dpi=300 if i < 3 else 450, threshold=(150, 190, 220)[i % 3])
            for i, value in enumerate(values)]


def refine(monkeypatch, values, **printed):
    original = tables(**printed)
    monkeypatch.setattr(cells, '_cleaned_line_readings', lambda *args: observations(values))
    with fitz.open() as doc:
        result, records = cells.refine_statement_native_cells(doc.new_page(width=600, height=800), original,
            deadline=time.monotonic() + 30, language='eng')
    return original, result, records


def test_unreadable_debit_is_recovered_from_its_own_printed_cell_only(monkeypatch):
    original, result, records = refine(monkeypatch, ['85.13'] * 6)
    before, after = original[0].geometry.cells, result[0].geometry.cells
    assert [(a.row, a.column) for a, b in zip(before, after) if a.text != b.text] == [(7, 2)]
    assert all(a.locator == b.locator for a, b in zip(before, after))
    assert records[0]['field'] == 'debit' and records[0]['original_text'] == '8S.13' and records[0]['text'] == '85.13'
    assert records[0]['original_quality']['identity'][0] == 'generic-labelled'
    assert records[0]['refined_quality']['unreadable'] == 0
    assert next(c.text for c in before if (c.row, c.column) == (7, 2)) == '8S.13'


def test_unreadable_running_balance_is_a_repair_target(monkeypatch):
    original, result, records = refine(monkeypatch, ['15,471.04'] * 6, debit='85.13', balance='15,47l.04')
    assert [(r['field'], r['text']) for r in records] == [('balance', '15,471.04')]


@pytest.mark.parametrize('values', [
    ['85.13'] * 5 + ['88.13'], [''] * 6, ['85.13'] * 3 + [''] * 3, ['85.13'] * 4, ['8S.13'] * 6,
])
def test_conflicting_or_incomplete_crop_readings_leave_the_cell_for_review(monkeypatch, values):
    original, result, records = refine(monkeypatch, values)
    assert result is original and records == []


def test_complete_values_are_never_crop_targets(monkeypatch):
    original, result, records = refine(monkeypatch, ['88.13'] * 6, debit='85.13')
    assert result is original and records == []


def test_page_without_printed_account_is_not_repaired(monkeypatch):
    original = tables()
    table = original[0]
    original = [replace(table, geometry=replace(table.geometry, cells=tuple(
        c for c in table.geometry.cells if c.row != 2)))]
    called = []
    monkeypatch.setattr(cells, '_cleaned_line_readings', lambda *args: called.append(args) or [])
    with fitz.open() as doc:
        result, records = cells.refine_statement_native_cells(doc.new_page(width=600, height=800), original,
            deadline=time.monotonic() + 30, language='eng')
    assert result is original and records == [] and called == []


def test_real_source_crop_recovers_the_printed_debit():
    # Real rasterisation and Tesseract on a synthetic page; no OCR stub.
    original = tables()
    with fitz.open() as doc:
        repaired, records = cells.refine_statement_native_cells(printed_page(doc), original,
            deadline=time.monotonic() + 30, language='eng')
    assert [(r['field'], r['text']) for r in records] == [('debit', '85.13')]
    assert len(repaired[0].geometry.cells) == len(original[0].geometry.cells)


def test_extraction_rereads_a_generic_page_with_an_unreadable_amount(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic-generic.pdf'
    with fitz.open() as doc:
        printed_page(doc)
        doc.save(path)
    native = tables()
    reader = pdf._load_table_reader()
    monkeypatch.setattr(pdf, '_ocr_detection_reason', lambda *args: None)
    monkeypatch.setattr(pdf, '_extract_native_tables', lambda *args: (reader.chunks_of(native), native))
    result = pdf._extract_pdf_sync(str(path))
    span = result.metadata['page_spans'][0]
    assert span['detection_reason'] == 'unreadable_statement_fields'
    records = span['ocr_refinements']
    assert any(r.get('field') == 'statement_page_reading' for r in records)
    from services.financial.statement_reading_quality import assess_statement_reading
    quality = assess_statement_reading(result.metadata['table_geometry']['per_table'])
    assert quality['payments'] == 1 and quality['unreadable'] == 0
