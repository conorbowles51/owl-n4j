"""Fresh synthetic Merrick readings through the extraction repair path."""
from dataclasses import replace
import time

import fitz
from app.pipeline import financial_amount_ocr as cells
from app.pipeline import pdf_extraction as pdf


def tables(amount='1O.00'):
    lines = [
        [(30, 'MERRICK BANK')],
        [(30, 'Statement Date: 04/25/21')],
        [(30, 'Account Number: 1111 2222 3333 4444')],
        [(30, 'Send Payments to:'), (270, 'EXAMPLE HOLDER')],
        [(30, 'Transactions, Payments and Credits')],
        [(30, 'Trans Date'), (270, 'Item Description'), (490, 'Amount')],
        [(30, '04/22'), (150, '24137463GEJBPDNXO'), (270, 'EXAMPLE SHOP'), (490, amount)],
        [(30, '04/23'), (150, '24137463JHEZKK04F'), (270, 'EXAMPLE CAFE'), (490, '100.00')],
        [(30, '2021 Totals Year-to-Date')],
    ]
    def locator(x, y, width):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x, y, x+width, y+12)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = [dict(row=i, column=j, text=text, locator=locator(x, 30+i*25,
        45 if x==490 else 90 if x==150 else 150 if x==270 else 50 if i>=5 else 400))
        for i,row in enumerate(lines) for j,(x,text) in enumerate(row)]
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=locator(0,0,600), values=values, unlocated_values=0)))])


def test_real_source_crop_recovers_amount_without_investigator_values():
    original = tables()
    # The visible original prints 14.00; the simulated damaged embedded layer
    # says 1O.00. This invokes real rasterisation and Tesseract, not an OCR stub.
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((490, 190), '14.00', fontsize=10)
        repaired, records = cells.refine_statement_native_cells(page, original,
            deadline=time.monotonic()+30, language='eng')
    assert records and records[0]['text'] == '14.00'
    assert records[0]['original_text'] == '1O.00'
    assert records[0]['refined_quality']['unreadable'] == 0
    assert len(repaired[0].geometry.cells) == len(original[0].geometry.cells)
    assert next(c.text for c in original[0].geometry.cells if (c.row,c.column)==(6,3)) == '1O.00'


def test_extraction_automatically_tries_crop_when_page_reread_loses_payment(tmp_path, monkeypatch):
    path = tmp_path/'synthetic-merrick.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        page.insert_text((490, 190), '14.00', fontsize=10)
        doc.save(path)
    native = tables()
    missing = [replace(native[0], geometry=replace(native[0].geometry,
        cells=tuple(c for c in native[0].geometry.cells if c.row != 7)))]
    reader = pdf._load_table_reader()
    monkeypatch.setattr(pdf, '_ocr_detection_reason', lambda *args: None)
    monkeypatch.setattr(pdf, '_extract_native_tables', lambda *args: (reader.chunks_of(native), native))
    monkeypatch.setattr(pdf, '_ocr_page', lambda *args, **kwargs: ('Synthetic image reading',90,300,[],[]))
    monkeypatch.setattr(reader, 'read_positioned_ocr_words', lambda *args, **kwargs: missing)
    result = pdf._extract_pdf_sync(str(path))
    records = result.metadata['page_spans'][0]['ocr_refinements']
    assert any(r.get('method') == 'tesseract_native_statement_cell_consensus' and r['text']=='14.00' for r in records)
    assert any(r.get('decision') == 'native_retained' for r in records)
