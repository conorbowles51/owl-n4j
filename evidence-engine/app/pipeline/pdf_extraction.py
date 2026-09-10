from __future__ import annotations

import asyncio
import logging
import math
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import fitz
import pytesseract
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

MIN_MEANINGFUL_ALNUM = 100
MIN_MEANINGFUL_WORDS = 15
MIN_IMAGE_COVERAGE = 0.50
MIN_VECTOR_DRAWINGS = 1000
LOW_CONFIDENCE_THRESHOLD = 60.0
MIN_OCR_DPI = 150
MIN_RELIABLE_OSD_CONFIDENCE = 15.0
MAX_OSD_TIMEOUT_SECONDS = 30.0
OSD_INSUFFICIENT_TEXT_MARKERS = ("too few characters", "skipping this page")


class PdfOcrError(RuntimeError):
    """Raised when a PDF page selected for OCR cannot be processed."""


@dataclass(frozen=True)
class PdfExtractionProgress:
    message: str
    completed: int
    total: int
    pdf_page: int | None = None


PdfProgressCallback = Callable[[PdfExtractionProgress], Awaitable[None]]


@dataclass(frozen=True)
class PdfExtractionResult:
    text: str
    metadata: dict
    tables: list[str] = field(default_factory=list)


@dataclass
class _PageResult:
    page_number: int
    text: str
    text_origin: str = "unknown"
    extraction_method: str = "native"
    detection_reason: str = "usable_native_text"
    ocr_status: str | None = None
    ocr_confidence: float | None = None
    ocr_dpi: int | None = None
    ocr_language: str | None = None


_semaphore_loop: asyncio.AbstractEventLoop | None = None
_pdf_extraction_semaphore: asyncio.Semaphore | None = None


def _get_pdf_extraction_semaphore() -> asyncio.Semaphore:
    global _semaphore_loop, _pdf_extraction_semaphore
    loop = asyncio.get_running_loop()
    if _pdf_extraction_semaphore is None or _semaphore_loop is not loop:
        _semaphore_loop = loop
        _pdf_extraction_semaphore = asyncio.Semaphore(
            max(1, int(settings.pdf_ocr_max_concurrency))
        )
    return _pdf_extraction_semaphore


def _native_text_stats(text: str) -> tuple[int, list[str]]:
    tokens = re.findall(r"\S+", text or "")
    return sum(character.isalnum() for character in text or ""), tokens


def _native_text_has_invalid_characters(text: str) -> bool:
    non_whitespace = [character for character in text if not character.isspace()]
    if not non_whitespace:
        return False
    invalid = sum(
        character == "\ufffd"
        or (ord(character) < 32 and character not in "\t\n\r")
        for character in non_whitespace
    )
    return invalid / len(non_whitespace) > 0.02


def _native_text_is_suspicious(text: str, tokens: list[str]) -> bool:
    if _native_text_has_invalid_characters(text):
        return True

    if len(tokens) >= 20:
        single_character_tokens = sum(
            len(re.sub(r"\W", "", token, flags=re.UNICODE)) == 1
            for token in tokens
        )
        if single_character_tokens / len(tokens) > 0.60:
            return True
    return False


def _image_coverage(page: fitz.Page) -> float:
    page_area = page.rect.get_area()
    if page_area <= 0:
        return 0.0

    covered_area = 0.0
    for image_info in page.get_image_info():
        try:
            image_rect = fitz.Rect(image_info["bbox"]) & page.rect
            if not image_rect.is_empty:
                covered_area += image_rect.get_area()
        except (KeyError, TypeError, ValueError):
            continue
    return min(1.0, covered_area / page_area)


def _ocr_detection_reason(page: fitz.Page, native_text: str) -> str | None:
    alnum_count, tokens = _native_text_stats(native_text)
    if alnum_count == 0:
        return "no_native_text"

    # A broken font encoding can yield thousands of alphanumeric characters
    # alongside control/replacement glyphs. Text quantity is not evidence that
    # such a layer is usable. Keep the weaker token-shape heuristic gated below.
    if _native_text_has_invalid_characters(native_text):
        return "suspicious_text_layer"

    weak_native_text = (
        alnum_count < MIN_MEANINGFUL_ALNUM
        or len(tokens) < MIN_MEANINGFUL_WORDS
    )
    coverage = _image_coverage(page)
    if coverage >= MIN_IMAGE_COVERAGE and weak_native_text:
        return "sparse_text_over_image"

    if weak_native_text and _native_text_is_suspicious(native_text, tokens):
        return "suspicious_text_layer"

    if weak_native_text:
        try:
            if len(page.get_drawings()) >= MIN_VECTOR_DRAWINGS:
                return "vector_text"
        except Exception:
            logger.debug("Unable to inspect page vector drawings", exc_info=True)

    return None


_table_reader: Any = None
_table_reader_attempted = False
_table_reader_failure: str | None = None

_origin_reader: Any = None
_origin_reader_attempted = False


def _embedded_text_origin(page: fitz.Page) -> str:
    """Measure embedded text provenance; embedded does not imply digital.

    Reuse the financial reader's conservative scan-overlay check. A separately
    deployed engine without that reader must say unknown, never assume digital.
    This labels provenance only; it does not identify amounts or change text.
    """
    global _origin_reader, _origin_reader_attempted
    if not _origin_reader_attempted:
        _origin_reader_attempted = True
        repo_root = Path(__file__).resolve().parents[3]
        for candidate in reversed([repo_root / "backend", Path("/backend")]):
            if candidate.exists() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        try:
            from services.financial.suspect_amounts import page_text_origin

            _origin_reader = page_text_origin
        except Exception:
            logger.warning(
                "PDF text-origin reader unavailable; recording unknown origin", exc_info=True
            )
    if _origin_reader is None:
        return "unknown"
    try:
        return _origin_reader(page).value
    except Exception:
        logger.warning(
            "PDF text-origin measurement failed; recording unknown origin", exc_info=True
        )
        return "unknown"


def _load_table_reader() -> Any:
    """``services.financial.pdf_tables``, or ``None`` if it cannot be reached.

    Imported here rather than at module scope for the reason
    ``cellebrite_ingestion`` does the same: the backend is a sibling package on
    disk, not an installed dependency, so its location is only known once the
    process is running.  Cached because the answer cannot change within a
    process and a failed import per page would be a per-page cost.

    A failure is remembered rather than retried, and surfaces in the extraction
    metadata, because the alternative -- geometry quietly absent, indistinguish-
    able from a document that simply had no tables -- is the shape a deployment
    fault takes when nobody notices it for a month.
    """
    global _table_reader, _table_reader_attempted, _table_reader_failure
    if _table_reader_attempted:
        return _table_reader
    _table_reader_attempted = True

    repo_root = Path(__file__).resolve().parents[3]
    candidates = [repo_root / "backend", Path("/backend")]
    for candidate in reversed(candidates):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    try:
        from services.financial import pdf_tables

        _table_reader = pdf_tables
    except Exception as exc:  # noqa: BLE001 - any import failure means no geometry
        _table_reader_failure = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Table geometry unavailable; falling back to text-only table extraction: %s",
            _table_reader_failure,
        )
    return _table_reader


def _extract_native_tables_unaided(page: fitz.Page, page_number: int) -> list[str]:
    """Table text exactly as it was produced before geometry existed.

    Kept verbatim rather than reimplemented in terms of the backend, so that a
    deployment which cannot reach the backend produces the text it produced
    yesterday, character for character, instead of something merely similar.
    """
    table_chunks: list[str] = []
    try:
        tables = page.find_tables()
        for table in tables.tables:
            extracted = table.extract()
            rows: list[str] = []
            for row in extracted:
                cells = [str(cell).strip() if cell is not None else "" for cell in row]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                table_chunks.append(f"[Page: {page_number}]\n" + "\n".join(rows))
    except Exception:
        logger.debug("Native table extraction failed for PDF page %s", page_number, exc_info=True)
    return table_chunks


def _extract_native_tables(
    page: fitz.Page, page_number: int
) -> tuple[list[str], list[Any]]:
    """The page's tables as text, and their geometry when it can be had.

    The text is the contract.  ``result.tables`` is already chunked, embedded
    and shown to readers, so it must come out of here byte-identical to what it
    was before geometry existed; the geometry is additive and may be absent.

    Every judgement about how to read geometry -- which coordinate space, what
    to do when a reader offers rows but no cell rectangles, when a table should
    be dropped rather than mispaired -- lives in the backend module, where it is
    tested.  What is left here is the part that cannot be moved: reaching that
    module, and carrying on without it.
    """
    reader = _load_table_reader()
    if reader is None:
        return _extract_native_tables_unaided(page, page_number), []

    try:
        tables = reader.read_tables(page, page_number)
    except Exception:
        # The same failure the unaided path swallows, swallowed the same way:
        # a page whose tables cannot be read costs its tables, never the
        # document.
        logger.debug(
            "Native table extraction failed for PDF page %s", page_number, exc_info=True
        )
        return [], []
    return reader.chunks_of(tables), list(tables)


def _table_geometry_metadata(chunk_count: int, extracted_tables: list[Any]) -> dict:
    """What was recovered, said plainly enough to be acted on.

    ``available`` is reported separately from the counts because zero located
    values means two different things -- a build that cannot see the backend at
    all, and one that read every table and found no rectangles in any of them --
    and a reader who cannot tell them apart will investigate the wrong thing.

    On size, measured rather than guessed: ``per_table`` carries a rectangle per
    located value and costs about 221 bytes each, so a forty-page statement with
    a thirty-by-six table on every page produces 1.52 MB of metadata, 99.7% of
    it this one key.  That is affordable only because this dict is transient --
    it is passed to ``build_extraction_quality_report``, which reads named keys,
    and is never written to a column.  Anything that later persists document
    metadata wholesale must bound or drop ``per_table`` first; the summary above
    it is complete without it, and is the part worth keeping.
    """
    reader = _load_table_reader()
    if reader is None:
        return {
            "available": False,
            "reason": _table_reader_failure or "table geometry reader not loaded",
            "text_only_tables": chunk_count,
        }
    return {
        "available": True,
        "coordinate_space": reader.TABLE_COORDINATE_SPACE.value,
        **reader.geometry_summary(extracted_tables),
        "per_table": [table.to_json() for table in extracted_tables],
    }


def _progress_checkpoints(page_count: int) -> set[int]:
    update_count = min(20, max(0, page_count))
    if update_count == 0:
        return set()
    return {
        math.ceil(index * page_count / update_count)
        for index in range(1, update_count + 1)
    }


def _render_dpi(page: fitz.Page) -> int:
    configured_dpi = max(MIN_OCR_DPI, int(settings.pdf_ocr_dpi))
    max_pixels = max(1, int(settings.pdf_ocr_max_pixels))
    width_pixels = page.rect.width * configured_dpi / 72.0
    height_pixels = page.rect.height * configured_dpi / 72.0
    configured_pixels = width_pixels * height_pixels
    if configured_pixels <= max_pixels:
        return configured_dpi

    reduced_dpi = math.floor(configured_dpi * math.sqrt(max_pixels / configured_pixels))
    effective_dpi = max(MIN_OCR_DPI, reduced_dpi)
    minimum_pixels = (
        page.rect.width * effective_dpi / 72.0
        * page.rect.height * effective_dpi / 72.0
    )
    if minimum_pixels > max_pixels:
        raise PdfOcrError(
            "page exceeds the configured OCR pixel limit even at 150 DPI"
        )
    return effective_dpi


def _text_and_confidence_from_tesseract(data: dict) -> tuple[str, float | None]:
    paragraphs: list[list[str]] = []
    paragraph_lines: list[str] = []
    line_words: list[str] = []
    current_paragraph: tuple[object, object] | None = None
    current_line: tuple[object, object, object] | None = None
    weighted_confidence = 0.0
    confidence_characters = 0

    texts = data.get("text") or []
    confidences = data.get("conf") or []
    block_numbers = data.get("block_num") or []
    paragraph_numbers = data.get("par_num") or []
    line_numbers = data.get("line_num") or []

    for index, raw_word in enumerate(texts):
        word = str(raw_word or "").strip()
        if not word:
            continue

        block_number = block_numbers[index] if index < len(block_numbers) else 0
        paragraph_number = paragraph_numbers[index] if index < len(paragraph_numbers) else 0
        line_number = line_numbers[index] if index < len(line_numbers) else 0
        paragraph_key = (block_number, paragraph_number)
        line_key = (block_number, paragraph_number, line_number)

        if current_line is not None and line_key != current_line:
            paragraph_lines.append(" ".join(line_words))
            line_words = []
        if current_paragraph is not None and paragraph_key != current_paragraph:
            if paragraph_lines:
                paragraphs.append(paragraph_lines)
            paragraph_lines = []

        current_paragraph = paragraph_key
        current_line = line_key
        line_words.append(word)

        if index < len(confidences):
            try:
                confidence = float(confidences[index])
            except (TypeError, ValueError):
                confidence = -1.0
            if confidence >= 0:
                weight = max(1, len(word))
                weighted_confidence += confidence * weight
                confidence_characters += weight

    if line_words:
        paragraph_lines.append(" ".join(line_words))
    if paragraph_lines:
        paragraphs.append(paragraph_lines)

    text = "\n\n".join("\n".join(lines) for lines in paragraphs).strip()
    mean_confidence = (
        round(weighted_confidence / confidence_characters, 1)
        if confidence_characters
        else None
    )
    return text, mean_confidence


def _remaining_ocr_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("Tesseract process timeout")
    return max(0.1, remaining)


def _is_insufficient_text_osd_error(exc: pytesseract.TesseractError) -> bool:
    message = str(exc).lower()
    return all(marker in message for marker in OSD_INSUFFICIENT_TEXT_MARKERS)


def _is_tesseract_timeout_error(exc: RuntimeError) -> bool:
    return "tesseract" in str(exc).lower() and "timeout" in str(exc).lower()


def _run_tesseract_data(
    image: Image.Image,
    *,
    dpi: int,
    deadline: float,
    page_segmentation_mode: int = 1,
) -> tuple[str, float | None]:
    data = pytesseract.image_to_data(
        image,
        lang=settings.tesseract_lang,
        config=f"--oem 1 --psm {page_segmentation_mode} --dpi {dpi}",
        output_type=pytesseract.Output.DICT,
        timeout=_remaining_ocr_timeout(deadline),
    )
    return _text_and_confidence_from_tesseract(data)


def _ocr_at_rotation(
    image: Image.Image,
    *,
    clockwise_rotation: int,
    dpi: int,
    deadline: float,
    page_segmentation_mode: int = 1,
) -> tuple[str, float | None]:
    normalized_rotation = clockwise_rotation % 360
    if normalized_rotation == 0:
        return _run_tesseract_data(
            image,
            dpi=dpi,
            deadline=deadline,
            page_segmentation_mode=page_segmentation_mode,
        )

    oriented_image = image.rotate(
        -normalized_rotation,
        expand=True,
        fillcolor="white",
    )
    try:
        return _run_tesseract_data(
            oriented_image,
            dpi=dpi,
            deadline=deadline,
            page_segmentation_mode=page_segmentation_mode,
        )
    finally:
        oriented_image.close()


def _ocr_page(page: fitz.Page) -> tuple[str, float | None, int]:
    deadline = time.monotonic() + max(
        1,
        int(settings.pdf_ocr_page_timeout_seconds),
    )
    dpi = _render_dpi(page)
    pixmap = page.get_pixmap(
        dpi=dpi,
        colorspace=fitz.csRGB,
        alpha=False,
        annots=True,
    )
    image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    try:
        try:
            osd = pytesseract.image_to_osd(
                image,
                config=f"--dpi {dpi}",
                output_type=pytesseract.Output.DICT,
                timeout=min(
                    MAX_OSD_TIMEOUT_SECONDS,
                    _remaining_ocr_timeout(deadline),
                ),
            )
            rotation = int(osd.get("rotate") or 0) % 360
            try:
                osd_confidence = float(osd.get("orientation_conf") or 0.0)
            except (TypeError, ValueError):
                osd_confidence = 0.0
        except pytesseract.TesseractError as exc:
            if not _is_insufficient_text_osd_error(exc):
                raise
            rotation = 0
            osd_confidence = None
        except RuntimeError as exc:
            if not _is_tesseract_timeout_error(exc):
                raise
            logger.warning(
                "PDF OCR orientation detection timed out; continuing with "
                "the unrotated page (dpi=%d)",
                dpi,
            )
            rotation = 0
            osd_confidence = None

        text, confidence = _ocr_at_rotation(
            image,
            clockwise_rotation=rotation,
            dpi=dpi,
            deadline=deadline,
        )

        uncertain_orientation = (
            osd_confidence is not None
            and osd_confidence < MIN_RELIABLE_OSD_CONFIDENCE
        )
        low_text_confidence = (
            confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD
        )
        if uncertain_orientation or low_text_confidence:
            alternative_rotations = [
                (rotation + offset) % 360 for offset in (0, 180, 90, 270)
            ]
        else:
            alternative_rotations = []

        best_score = (confidence if confidence is not None else -1.0, len(text))
        for alternative_rotation in alternative_rotations:
            try:
                alternative_text, alternative_confidence = _ocr_at_rotation(
                    image,
                    clockwise_rotation=alternative_rotation,
                    dpi=dpi,
                    deadline=deadline,
                    page_segmentation_mode=3,
                )
            except RuntimeError as exc:
                if not _is_tesseract_timeout_error(exc):
                    raise
                logger.warning(
                    "Optional PDF OCR orientation retry timed out; retaining "
                    "the best successful result (rotation=%d dpi=%d)",
                    alternative_rotation,
                    dpi,
                )
                break
            alternative_score = (
                alternative_confidence
                if alternative_confidence is not None
                else -1.0,
                len(alternative_text),
            )
            if alternative_score > best_score:
                text, confidence = alternative_text, alternative_confidence
                best_score = alternative_score
            if alternative_confidence is not None and alternative_confidence >= 80.0:
                break
    finally:
        image.close()
    return text, confidence, dpi


def _page_span(page_result: _PageResult, start_char: int) -> dict:
    span = {
        "page": page_result.page_number,
        "start_char": start_char,
        "end_char": start_char + len(page_result.text),
        "extraction_method": page_result.extraction_method,
        "text_origin": page_result.text_origin,
        "detection_reason": page_result.detection_reason,
    }
    if page_result.extraction_method == "tesseract_ocr":
        span.update(
            {
                "ocr_status": page_result.ocr_status,
                "ocr_confidence": page_result.ocr_confidence,
                "ocr_low_confidence": (
                    page_result.ocr_confidence is not None
                    and page_result.ocr_confidence < LOW_CONFIDENCE_THRESHOLD
                ),
                "ocr_dpi": page_result.ocr_dpi,
                "ocr_language": page_result.ocr_language,
            }
        )
    return span


def _extract_pdf_sync(
    file_path: str,
    report_progress: Callable[[PdfExtractionProgress], None] | None = None,
) -> PdfExtractionResult:
    started = time.perf_counter()
    table_chunks: list[str] = []
    # Positionally aligned with table_chunks: the reader returns both from one
    # pass precisely so that alignment is a property of the data rather than
    # something these two lists have to be trusted to maintain.
    extracted_tables: list[Any] = []

    try:
        document = fitz.open(file_path)
    except Exception as exc:
        raise PdfOcrError(f"Unable to open PDF: {exc}") from exc

    try:
        if document.needs_pass:
            raise PdfOcrError("PDF is password-protected")
        if document.page_count > settings.max_pdf_pages:
            raise PdfOcrError(
                f"PDF has {document.page_count} pages; the configured limit is "
                f"{settings.max_pdf_pages} pages"
            )

        pages: list[_PageResult] = []
        ocr_indexes: list[int] = []
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            native_text = page.get_text()
            detection_reason = _ocr_detection_reason(page, native_text)
            if detection_reason is None:
                page_result = _PageResult(
                    page_number=page_number, text=native_text,
                    text_origin=_embedded_text_origin(page),
                )
                page_chunks, page_tables = _extract_native_tables(page, page_number)
                table_chunks.extend(page_chunks)
                extracted_tables.extend(page_tables)
            else:
                page_result = _PageResult(
                    page_number=page_number,
                    text=native_text,
                    extraction_method="tesseract_ocr",
                    detection_reason=detection_reason,
                )
                ocr_indexes.append(page_index)
            pages.append(page_result)

        ocr_count = len(ocr_indexes)
        if report_progress:
            message = (
                f"OCR required for {ocr_count} of {len(pages)} PDF pages"
                if ocr_count
                else f"Embedded text found on all {len(pages)} PDF pages"
            )
            report_progress(PdfExtractionProgress(message, 0, ocr_count))

        progress_checkpoints = _progress_checkpoints(ocr_count)
        ocr_started = time.perf_counter()
        for completed, page_index in enumerate(ocr_indexes, start=1):
            page_result = pages[page_index]
            try:
                text, confidence, dpi = _ocr_page(document[page_index])
            except PdfOcrError as exc:
                logger.error(
                    "PDF OCR failed page=%d reason=%s",
                    page_result.page_number,
                    exc,
                )
                raise PdfOcrError(
                    f"OCR failed on PDF page {page_result.page_number}: {exc}"
                ) from exc
            except pytesseract.TesseractNotFoundError as exc:
                logger.error(
                    "PDF OCR failed page=%d reason=tesseract_not_found",
                    page_result.page_number,
                )
                raise PdfOcrError(
                    f"OCR failed on PDF page {page_result.page_number}: "
                    "Tesseract executable was not found"
                ) from exc
            except Exception as exc:
                logger.error(
                    "PDF OCR failed page=%d reason=%s",
                    page_result.page_number,
                    exc,
                )
                raise PdfOcrError(
                    f"OCR failed on PDF page {page_result.page_number}: {exc}"
                ) from exc

            page_result.text = text
            page_result.text_origin = "recognised_glyphs"
            page_result.ocr_status = "success" if text else "no_text"
            page_result.ocr_confidence = confidence
            page_result.ocr_dpi = dpi
            page_result.ocr_language = settings.tesseract_lang

            if report_progress and completed in progress_checkpoints:
                report_progress(
                    PdfExtractionProgress(
                        message=(
                            f"OCR page {completed} of {ocr_count} "
                            f"(PDF page {page_result.page_number})"
                        ),
                        completed=completed,
                        total=ocr_count,
                        pdf_page=page_result.page_number,
                    )
                )

        ocr_elapsed = time.perf_counter() - ocr_started if ocr_count else 0.0

        page_spans: list[dict] = []
        offset = 0
        for page_result in pages:
            page_spans.append(_page_span(page_result, offset))
            offset += len(page_result.text) + 2

        text = "\n\n".join(page.text for page in pages)
        low_confidence_count = sum(
            page.ocr_confidence is not None
            and page.ocr_confidence < LOW_CONFIDENCE_THRESHOLD
            for page in pages
        )
        if not ocr_count:
            extraction_mode = "native"
        elif ocr_count == len(pages):
            extraction_mode = "ocr"
        else:
            extraction_mode = "hybrid"

        metadata = {
            "file_type": "pdf",
            "page_count": len(pages),
            "is_scanned": ocr_count > 0,
            "extraction_mode": extraction_mode,
            "ocr_page_count": ocr_count,
            "native_page_count": len(pages) - ocr_count,
            "low_confidence_page_count": low_confidence_count,
            "page_spans": page_spans,
            "table_geometry": _table_geometry_metadata(
                len(table_chunks), extracted_tables
            ),
        }
        if ocr_count:
            metadata.update(
                {
                    "ocr_provider": "tesseract",
                    "ocr_language": settings.tesseract_lang,
                    "ocr_elapsed_seconds": round(ocr_elapsed, 3),
                }
            )

        logger.info(
            "PDF extraction complete mode=%s pages=%d native_pages=%d ocr_pages=%d "
            "low_confidence_pages=%d ocr_seconds=%.3f total_seconds=%.3f",
            extraction_mode,
            len(pages),
            len(pages) - ocr_count,
            ocr_count,
            low_confidence_count,
            ocr_elapsed,
            time.perf_counter() - started,
        )
        return PdfExtractionResult(text=text, metadata=metadata, tables=table_chunks)
    finally:
        document.close()


async def extract_pdf(
    file_path: str,
    progress_callback: PdfProgressCallback | None = None,
) -> PdfExtractionResult:
    semaphore = _get_pdf_extraction_semaphore()
    async with semaphore:
        if progress_callback is None:
            return await asyncio.to_thread(_extract_pdf_sync, file_path)

        queue: asyncio.Queue[PdfExtractionProgress] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def report_from_thread(progress: PdfExtractionProgress) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, progress)

        worker = asyncio.create_task(
            asyncio.to_thread(_extract_pdf_sync, file_path, report_from_thread)
        )
        while not worker.done():
            try:
                progress = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            await progress_callback(progress)

        result = await worker
        while not queue.empty():
            await progress_callback(queue.get_nowait())
        return result
