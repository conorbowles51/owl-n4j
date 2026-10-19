"""Targeted image rereads never discard an already readable statement page."""
from types import SimpleNamespace
from unittest.mock import Mock

import fitz
import pytest
from app.pipeline import pdf_extraction as pdf


@pytest.mark.parametrize('outcome', ['better', 'worse', 'failure', 'no_geometry'])
def test_native_statement_reread_retains_identity_and_falls_back(tmp_path, monkeypatch, outcome):
    path = tmp_path / 'synthetic.pdf'
    document = fitz.open()
    document.new_page().insert_text((30, 30), 'Synthetic statement original text')
    document.save(path)
    document.close()
    native = SimpleNamespace(chunk='native table', to_json=lambda: {'reading': 'native'})
    image = SimpleNamespace(chunk='image table', to_json=lambda: {'reading': 'image'},
        geometry_source=SimpleNamespace(value='cell_rectangles'))
    reader = SimpleNamespace(chunks_of=lambda tables: [t.chunk for t in tables],
        read_positioned_ocr_words=lambda *args, **kwargs: [image],
        TABLE_COORDINATE_SPACE=SimpleNamespace(value='pdf_displayed'),
        geometry_summary=lambda tables: {})
    monkeypatch.setattr(pdf, '_ocr_detection_reason', lambda *args: None)
    monkeypatch.setattr(pdf, '_extract_native_tables', lambda *args: (['native table'], [native]))
    monkeypatch.setattr(pdf, '_load_table_reader', lambda: reader)
    monkeypatch.setattr(pdf, '_statement_reading_quality', lambda tables:
        {'unreadable': 1 if tables == [native] else 0} if tables else None)
    monkeypatch.setattr(pdf, '_prefer_statement_image', lambda original, candidate:
        outcome == 'better' and candidate is not None)
    ocr = Mock(return_value=('Synthetic image reading', 95.0, 300,
        None if outcome == 'no_geometry' else ['synthetic words'], []))
    if outcome == 'failure':
        ocr.side_effect = pdf.PdfOcrError('synthetic image timeout')
    monkeypatch.setattr(pdf, '_ocr_page', ocr)
    result = pdf._extract_pdf_sync(str(path))
    ocr.assert_called_once()
    span = result.metadata['page_spans'][0]
    self_same = outcome != 'better'
    assert result.tables == ['native table' if self_same else 'image table']
    assert result.text == ('Synthetic statement original text\n' if self_same else 'Synthetic image reading')
    assert result.metadata['ocr_attempted_page_count'] == 1
    assert result.metadata['ocr_page_count'] == (0 if self_same else 1)
    assert span['detection_reason'] == 'unreadable_statement_fields'
    assert span['ocr_refinements'][-1]['decision'] == ('native_retained' if self_same else 'image_selected')


def test_readable_native_pages_do_not_incur_an_image_reread(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.pdf'
    document = fitz.open()
    document.new_page().insert_text((30, 30), 'Synthetic readable statement')
    document.save(path)
    document.close()
    monkeypatch.setattr(pdf, '_ocr_detection_reason', lambda *args: None)
    monkeypatch.setattr(pdf, '_extract_native_tables', lambda *args: ([], []))
    monkeypatch.setattr(pdf, '_statement_reading_quality', lambda tables: {'unreadable': 0})
    ocr = Mock(side_effect=AssertionError('A readable page must not be reread'))
    monkeypatch.setattr(pdf, '_ocr_page', ocr)
    result = pdf._extract_pdf_sync(str(path))
    ocr.assert_not_called()
    assert result.metadata['ocr_attempted_page_count'] == 0
