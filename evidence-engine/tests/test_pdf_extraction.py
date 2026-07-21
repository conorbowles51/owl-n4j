from __future__ import annotations

import asyncio
import hashlib
import shutil
import threading
import time
import uuid

import fitz
import pytesseract
import pytest

from app.config import settings
from app.models.job import JobStatus
from app.pipeline import batch_orchestrator
from app.pipeline import pdf_extraction
from app.pipeline.chunk_embed import chunk_document
from app.pipeline.extract_text import extract_text
from app.pipeline.pdf_extraction import PdfExtractionProgress
from app.pipeline.pdf_extraction import PdfExtractionResult
from app.pipeline.pdf_extraction import PdfOcrError
from app.services.evidence_document_text import build_canonical_document_text


def _add_text_to_page(page: fitz.Page, content: str) -> None:
    page.insert_textbox(fitz.Rect(72, 72, 520, 770), content, fontsize=12)


def _write_native_pdf(path, pages: list[str]) -> None:
    document = fitz.open()
    try:
        for content in pages:
            page = document.new_page()
            _add_text_to_page(page, content)
        document.save(path)
    finally:
        document.close()


def _write_scanned_pdf(path, pages: list[str], *, rotation: int = 0) -> None:
    source = fitz.open()
    scanned = fitz.open()
    try:
        for content in pages:
            source_page = source.new_page()
            _add_text_to_page(source_page, content)
            pixmap = source_page.get_pixmap(dpi=150, alpha=False)
            image_bytes = pixmap.tobytes("png")
            if rotation:
                from io import BytesIO

                from PIL import Image

                image = Image.open(BytesIO(image_bytes))
                image = image.rotate(rotation, expand=True, fillcolor="white")
                output = BytesIO()
                image.save(output, format="PNG")
                image_bytes = output.getvalue()
            page = scanned.new_page()
            page.insert_image(page.rect, stream=image_bytes)
        scanned.save(path)
    finally:
        source.close()
        scanned.close()


def _write_mixed_pdf(path, native_text: str, scanned_text: str) -> None:
    source = fitz.open()
    mixed = fitz.open()
    try:
        native_page = mixed.new_page()
        _add_text_to_page(native_page, native_text)

        scan_source_page = source.new_page()
        _add_text_to_page(scan_source_page, scanned_text)
        pixmap = scan_source_page.get_pixmap(dpi=150, alpha=False)
        scanned_page = mixed.new_page()
        scanned_page.insert_image(scanned_page.rect, stream=pixmap.tobytes("png"))
        mixed.save(path)
    finally:
        source.close()
        mixed.close()


@pytest.fixture
def mock_osd(monkeypatch):
    monkeypatch.setattr(
        pytesseract,
        "image_to_osd",
        lambda *_args, **_kwargs: {"rotate": 0, "orientation_conf": 20.0},
    )


async def test_native_pdf_keeps_embedded_text_and_records_page_provenance(tmp_path) -> None:
    pdf_path = tmp_path / "native.pdf"
    _write_native_pdf(pdf_path, ["Native evidence text for account ACME-4821."])

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert "Native evidence text" in result.text
    assert result.metadata["extraction_mode"] == "native"
    assert result.metadata["ocr_page_count"] == 0
    assert result.metadata["page_spans"][0]["extraction_method"] == "native"


async def test_native_pdf_keeps_table_extraction(tmp_path, monkeypatch) -> None:
    pdf_path = tmp_path / "native-table.pdf"
    document = fitz.open()
    try:
        page = document.new_page()
        columns = [72, 250, 430]
        rows = [72, 110, 148]
        for x_position in columns:
            page.draw_line(
                (x_position, rows[0]),
                (x_position, rows[-1]),
                width=1,
            )
        for y_position in rows:
            page.draw_line(
                (columns[0], y_position),
                (columns[-1], y_position),
                width=1,
            )
        for x_position, y_position, value in (
            (82, 95, "Name"),
            (260, 95, "Amount"),
            (82, 133, "Alice"),
            (260, 133, "25000"),
        ):
            page.insert_text((x_position, y_position), value, fontsize=10)
        document.save(pdf_path)
    finally:
        document.close()

    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: pytest.fail("native table page should not use OCR"),
    )

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.metadata["extraction_mode"] == "native"
    assert result.tables == ["[Page: 1]\nName | Amount\nAlice | 25000"]


async def test_image_only_pdf_is_ocrd_and_replaces_missing_native_text(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    _write_scanned_pdf(pdf_path, ["This raster text is not embedded in the PDF."])
    original_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    def fake_image_to_data(*_args, **_kwargs):
        return {
            "text": ["", "Recovered", "account", "ACME-4821"],
            "conf": ["-1", "96", "94", "92"],
            "block_num": [0, 1, 1, 1],
            "par_num": [0, 1, 1, 1],
            "line_num": [0, 1, 1, 1],
        }

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)
    monkeypatch.setattr(settings, "image_provider", "openai")

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.text == "Recovered account ACME-4821"
    assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == original_sha256
    assert result.metadata["extraction_mode"] == "ocr"
    assert result.metadata["ocr_page_count"] == 1
    assert result.metadata["page_spans"][0] == {
        "page": 1,
        "start_char": 0,
        "end_char": len(result.text),
        "extraction_method": "tesseract_ocr",
        "detection_reason": "no_native_text",
        "ocr_status": "success",
        "ocr_confidence": 94.0,
        "ocr_low_confidence": False,
        "ocr_dpi": 300,
        "ocr_language": "eng",
    }


async def test_ocr_page_provenance_is_persisted_in_source_locations(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "provenance.pdf"
    _write_scanned_pdf(pdf_path, ["Raster evidence"])
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["Recovered", "evidence"],
            "conf": ["55", "65"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        },
    )

    extracted = await extract_text(str(pdf_path), pdf_path.name)
    canonical = build_canonical_document_text(extracted)

    assert canonical.source_locations[0]["extraction_method"] == "tesseract_ocr"
    assert canonical.source_locations[0]["ocr_confidence"] == 59.7
    assert canonical.source_locations[0]["ocr_low_confidence"] is True
    assert canonical.source_locations[0]["ocr_language"] == "eng"


async def test_batch_pipeline_maps_pdf_progress_into_text_extraction_stage(
    monkeypatch,
) -> None:
    updates: list[tuple[JobStatus, float, str]] = []

    class FakeCostContext:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *_args):
            return None

    async def fake_update_job_status(
        _job_id,
        status,
        progress,
        message="",
        **_kwargs,
    ) -> None:
        updates.append((status, progress, message))

    async def fake_extract_text(
        _file_path,
        _file_name,
        progress_callback=None,
    ):
        assert progress_callback is not None
        await progress_callback(
            PdfExtractionProgress(
                message="OCR page 1 of 2 (PDF page 3)",
                completed=1,
                total=2,
                pdf_page=3,
            )
        )
        from app.pipeline.extract_text import ExtractedDocument

        return ExtractedDocument(text="Recovered evidence text long enough to process.")

    monkeypatch.setattr(
        batch_orchestrator,
        "ingestion_cost_context",
        lambda **_kwargs: FakeCostContext(),
    )
    monkeypatch.setattr(batch_orchestrator, "_update_job_status", fake_update_job_status)
    monkeypatch.setattr(batch_orchestrator, "extract_text", fake_extract_text)
    monkeypatch.setattr(batch_orchestrator, "get_transcription", lambda _doc: None)

    async def no_summary(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        batch_orchestrator,
        "generate_document_summary",
        no_summary,
    )

    async def no_chunks(*_args, **_kwargs):
        return []

    async def no_entities(*_args, **_kwargs):
        return [], []

    monkeypatch.setattr(batch_orchestrator, "chunk_and_embed", no_chunks)
    monkeypatch.setattr(
        batch_orchestrator,
        "extract_entities_and_relationships",
        no_entities,
    )

    await batch_orchestrator._extract_file(
        job_id=uuid.uuid4(),
        file_path="scan.pdf",
        file_name="scan.pdf",
        case_id="case-1",
        llm_profile="generic",
    )

    assert (
        JobStatus.EXTRACTING_TEXT,
        0.08,
        "OCR page 1 of 2 (PDF page 3)",
    ) in updates


async def test_mixed_pdf_uses_native_and_ocr_text_once_in_page_order(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "mixed.pdf"
    native_text = (
        "This native page contains enough embedded words to remain on the fast extraction "
        "path and preserve its original searchable text exactly."
    )
    _write_mixed_pdf(pdf_path, native_text, "Raster-only second page evidence")
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["OCR", "SECOND", "PAGE"],
            "conf": ["95", "95", "95"],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        },
    )

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.metadata["extraction_mode"] == "hybrid"
    assert result.metadata["native_page_count"] == 1
    assert result.metadata["ocr_page_count"] == 1
    assert result.text.count("OCR SECOND PAGE") == 1
    assert result.text.index("native page") < result.text.index("OCR SECOND PAGE")
    assert [
        span["extraction_method"] for span in result.metadata["page_spans"]
    ] == ["native", "tesseract_ocr"]
    chunks = chunk_document(result, pdf_path.name, "job-1")
    assert chunks[0].metadata["page_start"] == 1
    assert chunks[0].metadata["page_end"] == 2


async def test_sparse_overlay_on_full_page_image_is_replaced_by_ocr(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "sparse-overlay.pdf"
    _write_scanned_pdf(pdf_path, ["Dense raster evidence content"])
    document = fitz.open(pdf_path)
    rewritten = tmp_path / "rewritten.pdf"
    try:
        document[0].insert_text((72, 810), "CASE 42", fontsize=10)
        document.save(rewritten)
    finally:
        document.close()
    rewritten.replace(pdf_path)

    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["FULL", "RASTER", "TEXT"],
            "conf": ["90", "90", "90"],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
        },
    )

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.text == "FULL RASTER TEXT"
    assert result.metadata["page_spans"][0]["detection_reason"] == "sparse_text_over_image"
    assert "CASE 42" not in result.text


async def test_usable_existing_text_layer_is_not_reprocessed(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "existing-ocr-layer.pdf"
    _write_scanned_pdf(pdf_path, ["Background scan"])
    document = fitz.open(pdf_path)
    rewritten = tmp_path / "existing-ocr-layer-rewritten.pdf"
    embedded = (
        "Existing searchable OCR text has enough complete words to remain native and avoid "
        "an unnecessary second recognition pass over this scanned page."
    )
    try:
        _add_text_to_page(document[0], embedded)
        document.save(rewritten)
    finally:
        document.close()
    rewritten.replace(pdf_path)

    def fail_ocr(*_args, **_kwargs):
        pytest.fail("usable existing text layers must not be OCRed again")

    monkeypatch.setattr(pytesseract, "image_to_data", fail_ocr)

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.metadata["extraction_mode"] == "native"
    assert "Existing searchable OCR text" in result.text


async def test_empty_ocr_output_is_recorded_without_failing(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "photographic.pdf"
    _write_scanned_pdf(pdf_path, [""])

    def insufficient_text_osd(*_args, **_kwargs):
        raise pytesseract.TesseractError(
            1,
            "Too few characters. Skipping this page Error during processing.",
        )

    monkeypatch.setattr(pytesseract, "image_to_osd", insufficient_text_osd)
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "text": [],
            "conf": [],
            "block_num": [],
            "par_num": [],
            "line_num": [],
        },
    )

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.text == ""
    assert result.metadata["page_spans"][0]["ocr_status"] == "no_text"


async def test_tesseract_error_names_the_pdf_page(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "timeout.pdf"
    _write_scanned_pdf(pdf_path, ["Raster page one", "Raster page two"])

    def fail_ocr(*_args, **_kwargs):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pytesseract, "image_to_data", fail_ocr)

    with pytest.raises(PdfOcrError, match="PDF page 1: Tesseract process timeout"):
        await extract_text(str(pdf_path), pdf_path.name)


async def test_missing_configured_language_is_actionable(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "missing-language.pdf"
    _write_scanned_pdf(pdf_path, ["Raster evidence"])
    monkeypatch.setattr(settings, "tesseract_lang", "spa")

    def missing_language(*_args, **_kwargs):
        raise pytesseract.TesseractError(1, "Failed loading language 'spa'")

    monkeypatch.setattr(pytesseract, "image_to_data", missing_language)

    with pytest.raises(
        PdfOcrError,
        match="PDF page 1: .*Failed loading language 'spa'",
    ):
        await extract_text(str(pdf_path), pdf_path.name)


async def test_sparse_image_overlay_uses_either_weak_text_threshold(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "many-short-overlay-words.pdf"
    _write_scanned_pdf(pdf_path, ["Background scan"])
    document = fitz.open(pdf_path)
    rewritten = tmp_path / "many-short-overlay-words-rewritten.pdf"
    try:
        _add_text_to_page(document[0], " ".join(["word"] * 20))
        document.save(rewritten)
    finally:
        document.close()
    rewritten.replace(pdf_path)
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["RECOVERED", "SCAN"],
            "conf": ["95", "95"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        },
    )

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.text == "RECOVERED SCAN"
    assert result.metadata["page_spans"][0]["detection_reason"] == "sparse_text_over_image"


async def test_weak_single_character_text_layer_is_ocrd_without_an_image(
    tmp_path,
    monkeypatch,
    mock_osd,
) -> None:
    pdf_path = tmp_path / "simulated-characters.pdf"
    _write_native_pdf(pdf_path, [" ".join("ABCDEFGHIJKLMNOPQRST")])
    monkeypatch.setattr(
        pytesseract,
        "image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["NORMALIZED", "TEXT"],
            "conf": ["90", "90"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        },
    )

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.text == "NORMALIZED TEXT"
    assert result.metadata["page_spans"][0]["detection_reason"] == "suspicious_text_layer"


async def test_orientation_pass_rotates_page_before_ocr(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "sideways.pdf"
    _write_scanned_pdf(pdf_path, ["Sideways evidence"])
    monkeypatch.setattr(
        pytesseract,
        "image_to_osd",
        lambda *_args, **_kwargs: {"rotate": 90, "orientation_conf": 20.0},
    )

    def fake_image_to_data(image, **_kwargs):
        assert image.width > image.height
        assert "--psm 1" in _kwargs["config"]
        return {
            "text": ["ORIENTED", "TEXT"],
            "conf": ["95", "95"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert result.text == "ORIENTED TEXT"


async def test_low_confidence_orientation_retries_the_opposite_direction(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "upside-down.pdf"
    _write_scanned_pdf(pdf_path, ["Upside down evidence"])
    monkeypatch.setattr(
        pytesseract,
        "image_to_osd",
        lambda *_args, **_kwargs: {"rotate": 0, "orientation_conf": 1.0},
    )
    attempts = 0

    def fake_image_to_data(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {
                "text": ["uncertain"],
                "conf": ["80"],
                "block_num": [1],
                "par_num": [1],
                "line_num": [1],
            }
        return {
            "text": ["CORRECTED", "EVIDENCE"],
            "conf": ["95", "95"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert attempts == 2
    assert result.text == "CORRECTED EVIDENCE"
    assert result.metadata["page_spans"][0]["ocr_confidence"] == 95.0


async def test_low_ocr_confidence_checks_every_rotation_even_when_osd_is_confident(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "misleading-osd.pdf"
    _write_scanned_pdf(pdf_path, ["Misleading orientation evidence"])
    monkeypatch.setattr(
        pytesseract,
        "image_to_osd",
        lambda *_args, **_kwargs: {"rotate": 180, "orientation_conf": 20.0},
    )
    attempts = 0

    def fake_image_to_data(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 5:
            return {
                "text": ["CORRECT", "ROTATION"],
                "conf": ["96", "96"],
                "block_num": [1, 1],
                "par_num": [1, 1],
                "line_num": [1, 1],
            }
        return {
            "text": ["uncertain"],
            "conf": ["30"],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    result = await extract_text(str(pdf_path), pdf_path.name)

    assert attempts == 5
    assert result.text == "CORRECT ROTATION"


async def test_pdf_extraction_concurrency_is_bounded_to_configured_limit(
    monkeypatch,
) -> None:
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def fake_extract(_file_path, _report_progress=None):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return PdfExtractionResult(text="ok", metadata={})

    monkeypatch.setattr(pdf_extraction, "_extract_pdf_sync", fake_extract)
    await asyncio.gather(*(pdf_extraction.extract_pdf(str(index)) for index in range(6)))

    assert maximum_active == 2


def test_large_pdf_progress_is_limited_to_twenty_even_updates() -> None:
    checkpoints = pdf_extraction._progress_checkpoints(80)

    assert len(checkpoints) == 20
    assert min(checkpoints) == 4
    assert max(checkpoints) == 80
    assert pdf_extraction._progress_checkpoints(3) == {1, 2, 3}


@pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="real OCR integration requires the Tesseract executable",
)
@pytest.mark.parametrize("rotation", [90, 180, 270])
async def test_real_tesseract_recovers_rotated_scanned_pdf(tmp_path, rotation) -> None:
    pdf_path = tmp_path / f"rotated-{rotation}.pdf"
    content = "\n".join(
        [
            "INVESTIGATION REPORT ACCOUNT ACME 4821",
            "PAYMENT AMOUNT EUR 25000 WITNESS JANE OBRIEN",
            "TRANSACTION RECORDS CONFIRM THE PAYMENT DETAILS",
            "RECIPIENT NORTH ATLANTIC HOLDINGS REFERENCE KAPPA",
        ]
        * 3
    )
    _write_scanned_pdf(pdf_path, [content], rotation=rotation)

    result = await extract_text(str(pdf_path), pdf_path.name)

    normalized = result.text.upper().replace("-", " ")
    assert "INVESTIGATION REPORT" in normalized
    assert "ACME" in normalized
    assert "4821" in normalized
