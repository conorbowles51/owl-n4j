"""Printed lines an embedded OCR layer left unread send the page to the image reading; synthetic corpus only."""
from pathlib import Path

import fitz
import pytest
from app.pipeline import pdf_extraction as pdf

CORPUS = Path(__file__).resolve().parents[2] / 'backend' / 'benchmarks' / 'statement_automation' / 'corpus'
LOST = 'andrews-2020-12-ocr-lost-lines-equal-balances.pdf'


def test_lines_the_embedded_layer_lost_are_measured_on_the_page_image():
    with fitz.open(CORPUS / LOST) as doc:
        assert pdf._unread_printed_lines(doc[0]) == [(282.24, 288.72), (294.48, 299.52)]


def test_a_complete_embedded_layer_has_no_unread_line():
    with fitz.open(CORPUS / 'andrews-2020-10-quiet-checking-scan.pdf') as doc:
        assert pdf._unread_printed_lines(doc[0]) == []


def test_a_ruled_line_or_a_smudge_is_not_a_printed_text_line():
    with fitz.open(CORPUS / 'andrews-2020-10-quiet-checking-scan.pdf') as doc:
        page = doc[0]
        page.draw_line((15, 292), (380, 292), width=4)
        page.draw_rect(fitz.Rect(100, 300, 104, 305), fill=(0, 0, 0))
        assert pdf._unread_printed_lines(page) == []


def test_no_other_corpus_scan_with_a_complete_layer_is_sent_to_the_image_reading():
    found = {}
    for path in sorted(CORPUS.glob('*.pdf')):
        with fitz.open(path) as doc:
            for index, page in enumerate(doc):
                if (pdf._ocr_detection_reason(page, page.get_text()) is None
                        and pdf._embedded_text_origin(page) == 'recognised_glyphs'
                        and pdf._unread_printed_lines(page)):
                    found[(path.name, index + 1)] = True
    assert list(found) == [(LOST, 1)]


def _statement_record(result):
    return [r for span in result.metadata['page_spans'] for r in span.get('ocr_refinements') or []
            if r.get('field') == 'statement_page_reading']


def test_the_image_reading_that_adds_exactly_the_lost_lines_replaces_the_embedded_layer():
    # Real rasterisation and Tesseract: the scan prints two equal and opposite payments the layer lost.
    result = pdf._extract_pdf_sync(str(CORPUS / LOST))
    record, = _statement_record(result)
    assert (record['decision'], record['reason']) == ('image_selected', 'recovered_unread_lines')
    assert [(r['date'], r['amount_minor'], r['direction'], r['balance']) for r in record['added_rows']] == [
        ('2020-12-07', '5000', 'credit', '235000'), ('2020-12-09', '5000', 'debit', '230000')]
    span = result.metadata['page_spans'][0]
    assert (span['extraction_method'], span['detection_reason']) == ('tesseract_ocr', 'unread_printed_lines')
    verification = [r for r in span['ocr_refinements'] if r.get('method') == 'tesseract_money_cell_verification']
    assert [r['decision'] for r in verification] == ['all_confirmed']


def test_an_image_reading_that_does_not_recover_the_lines_keeps_the_embedded_layer(monkeypatch):
    monkeypatch.setattr(pdf, '_recovered_unread_lines', lambda original, tables: None)
    result = pdf._extract_pdf_sync(str(CORPUS / LOST))
    record, = _statement_record(result)
    assert record['decision'] == 'native_retained'
    assert record['unread_lines'] == [[282.24, 288.72], [294.48, 299.52]]
    assert result.metadata['page_spans'][0]['extraction_method'] == 'native'


def test_a_failed_measurement_never_costs_the_page(monkeypatch):
    def broken(page):
        raise RuntimeError('render failed')
    monkeypatch.setattr(pdf, '_unread_printed_lines', broken)
    result = pdf._extract_pdf_sync(str(CORPUS / LOST))
    assert _statement_record(result) == []
    assert result.metadata['page_spans'][0]['detection_reason'] == 'usable_native_text'
