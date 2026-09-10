"""Text provenance survives extraction without confusing embedded OCR with digital text."""
import fitz

from app.pipeline import pdf_extraction
from app.pipeline.extract_text import ExtractedDocument
from app.services.evidence_document_text import build_canonical_document_text


def _pdf(path, *, overlay=False, image_only=False):
    with fitz.open() as doc:
        page = doc.new_page()
        if overlay or image_only:
            pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
            pixmap.clear_with(255)
            page.insert_image(page.rect, stream=pixmap.tobytes("png"))
        if not image_only:
            page.insert_textbox(fitz.Rect(40, 40, 550, 300),
                "Statement text with amount 1234 and enough words to keep the embedded text. " * 8)
        doc.save(path)


def test_embedded_scan_layer_is_not_called_digital(tmp_path):
    path = tmp_path / "overlay.pdf"
    _pdf(path, overlay=True)
    result = pdf_extraction._extract_pdf_sync(str(path))
    span = result.metadata["page_spans"][0]
    assert span["extraction_method"] == "native"
    assert span["text_origin"] == "recognised_glyphs"
    assert "1234" in result.text
    canonical = build_canonical_document_text(ExtractedDocument(
        text=result.text, metadata=result.metadata, tables=result.tables))
    assert canonical.content == result.text
    assert canonical.source_locations[0]["text_origin"] == "recognised_glyphs"


def test_digital_page_origin_is_measured(tmp_path):
    path = tmp_path / "digital.pdf"
    _pdf(path)
    result = pdf_extraction._extract_pdf_sync(str(path))
    assert result.metadata["page_spans"][0]["text_origin"] == "digital_text_layer"


def test_successful_ocr_always_records_recognised_origin(tmp_path, monkeypatch):
    path = tmp_path / "scan.pdf"
    _pdf(path, image_only=True)
    monkeypatch.setattr(pdf_extraction, "_ocr_page", lambda page: ("1234", 99.0, 150, None))
    result = pdf_extraction._extract_pdf_sync(str(path))
    assert result.metadata["page_spans"][0]["text_origin"] == "recognised_glyphs"
    assert result.text == "1234"


def test_missing_reader_does_not_promote_embedded_text(tmp_path, monkeypatch):
    path = tmp_path / "unknown.pdf"
    _pdf(path)
    monkeypatch.setattr(pdf_extraction, "_origin_reader_attempted", True)
    monkeypatch.setattr(pdf_extraction, "_origin_reader", None)
    result = pdf_extraction._extract_pdf_sync(str(path))
    assert result.metadata["page_spans"][0]["text_origin"] == "unknown"
    assert "1234" in result.text


def test_failed_measurement_is_unknown(monkeypatch):
    def fail(page):
        raise RuntimeError("Cannot inspect image coverage")
    monkeypatch.setattr(pdf_extraction, "_origin_reader_attempted", True)
    monkeypatch.setattr(pdf_extraction, "_origin_reader", fail)
    assert pdf_extraction._embedded_text_origin(object()) == "unknown"
