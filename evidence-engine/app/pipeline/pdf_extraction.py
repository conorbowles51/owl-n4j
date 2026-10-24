from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import multiprocessing
import os
import re
import signal
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
MIN_OUTLINE_CHARACTERS_OVER_IMAGE = 300
LOW_CONFIDENCE_THRESHOLD = 60.0
MIN_OCR_DPI = 150
MIN_RELIABLE_OSD_CONFIDENCE = 15.0
MAX_OSD_TIMEOUT_SECONDS = 30.0
# v14 (r1-reproduced): pages whose text is mostly invisible are recognised text
# (backend page_text_origin), so their money cells are crop-verified.
# v15 (r3-andrews): on Andrews scans, joined amount/balance cells and cells whose
# only fault is the decimal mark are crop-verified, crop readings are compared by
# amount, and the pinned reading is decided per account section.
# v16 (r4-cards): a printed minus the crops lose is confirmed by its measured
# mark; crop readings agree whatever decimal/grouping marks they show; an "S"
# read for the dollar sign is confirmed when the crops read the sign; card row
# dates are reread from their cells; an image reading replaces a recognised
# layer that cannot read the statement identity or the card summary balances.
# v17 (r5-andrews-cards): period-wide pinned readings, stored printed readings for held cells.
# v18 (r6-vector-text): a page with no text layer that prints its text as vector outlines is
# classed vector_text; its OCR words are re-read from the character outlines and its money
# cells confirmed from them (vector_glyph_reading); words over blank paper are dropped and
# printed amounts OCR skipped are added from their outlines.
# v19 (r7-alex-queue): a vector-text page whose character outlines run left to right is read
# upright without asking orientation detection (vector_glyph_reading.drawn_upright).
# v20 (r8-mt-engine): on a vector-text page a printed line OCR skipped altogether is read from its
# own crop (vector_glyph_reading.unread_lines), the printed lines still unread are recorded, and a
# figure token whose narrow characters stand a space-wide bearing apart is re-read from its outlines;
# a page drawing its characters as outlines over an image covering most of it is vector text.
# v21 (r9-engine-santander): a mark shorter than half a character (a thousands comma, a period) joins the
# printed line it sits on, so a skipped line's amount is read whole instead of leaving its label alone.
# v22 (layer guard): the skipped-line layer is held aside while the targeted re-reads run and put
# back only where none of them added a word (_withhold_layer, _restore_layer). v21 is
# r9-engine-santander's revision; either order of merging keeps this one distinct.
# v23 (r11-bbva-vector): on a vector-text page a word OCR read with characters lost inside it (a date's
# slash and month letter read as one letter) is read whole from its labelled outlines, and a word whose OCR
# box cut off the outline of a character beside it keeps its OCR reading, and an amount OCR read as two
# words where it skipped the thousands comma is read as one (vector_glyph_reading.split_amounts).
# v24 (r12-kapital): on a vector-text page a day of the month OCR skipped as the first word of a movement line
# (one or two figures, every outline labelled, an amount to its right) is added from its outlines
# (vector_glyph_reading.LINE_START_DAYS).
PDF_READING_REVISION = 'bank-payment-rows-v25'
OSD_INSUFFICIENT_TEXT_MARKERS = ("too few characters", "skipping this page")


class PdfOcrError(RuntimeError):
    """Raised when a PDF page selected for OCR cannot be processed."""


# ``ocr_status`` of a page whose OCR ran out of time: kept unread, file not failed.
OCR_TIMEOUT_STATUS = 'timeout'


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
    ocr_geometry_status: str | None = None
    ocr_refinements: list[dict] = field(default_factory=list)


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


def _vector_text_page(page: fitz.Page) -> bool:
    """The page prints its text as filled vector outlines: mostly drawings, not an image.

    Measured on the real statements: weak-text pages that are not image-covered
    carry either fewer than 300 path segments or at least 4,066; outline-text
    pages group a whole printed line into one path (84 paths, 33,000 segments),
    so the path count alone (``MIN_VECTOR_DRAWINGS``) missed them.
    """
    covered = _image_coverage(page) >= MIN_IMAGE_COVERAGE
    try:
        drawings = page.get_drawings()
    except Exception:
        logger.debug("Unable to inspect page vector drawings", exc_info=True)
        return False
    from app.pipeline.vector_glyph_reading import MIN_VECTOR_SEGMENTS, page_glyphs, vector_segments
    if covered:
        # An image under most of the page is a scan, unless the page also draws its characters as
        # outlines over it (a shaded background image behind the tables; measured on the real truth
        # set: 6 such pages, each with more than 1,600 character outlines; the image-covered pages
        # that also carry vector drawings draw at most 3).
        try:
            return (vector_segments(drawings) >= MIN_VECTOR_SEGMENTS
                    and len(page_glyphs(page, drawings)) >= MIN_OUTLINE_CHARACTERS_OVER_IMAGE)
        except Exception:
            logger.debug("Unable to group page outlines", exc_info=True)
            return False
    return len(drawings) >= MIN_VECTOR_DRAWINGS or vector_segments(drawings) >= MIN_VECTOR_SEGMENTS


def _ocr_detection_reason(page: fitz.Page, native_text: str) -> str | None:
    alnum_count, tokens = _native_text_stats(native_text)
    if alnum_count == 0:
        return "vector_text" if _vector_text_page(page) else "no_native_text"

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

    if weak_native_text and _vector_text_page(page):
        return "vector_text"

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


def _statement_reading_quality(tables):
    """Optional source-bound check; unavailable backend support never blocks PDFs."""
    try:
        from services.financial.statement_reading_quality import assess_statement_reading
        return assess_statement_reading([table.to_json() for table in tables])
    except Exception:
        logger.debug('Statement reading assessment unavailable', exc_info=True)
        return None


def _prefer_statement_image(original, image):
    from services.financial.statement_reading_quality import prefer_image_reading
    return prefer_image_reading(original, image)


UNREAD_LINE_DPI = 100


def _unread_printed_lines(page):
    """``[(top, bottom)]`` in page points where the image prints a text line no embedded word covers.

    An embedded OCR layer can drop whole printed lines. The page image is
    rendered once at 100 dpi (embedded invisible text is not drawn) and split
    into horizontal ink bands. A band counts only when it lies strictly
    between the first and last embedded word, is as tall as the page's other
    text lines (0.6 to 1.6 times their median ink height), its ink falls into
    at least six separate runs across the page (characters, not a rule or a
    smudge), and no embedded word overlaps it by 30% of its height. Rotated
    pages and pages with too few words are not measured. This never changes
    a reading; it only sends the page to the image reading, whose result is
    accepted on its own conditions.
    """
    import numpy as np
    words = page.get_text('words')
    if page.rotation or len(words) < MIN_MEANINGFUL_WORDS:
        return []
    pix = page.get_pixmap(dpi=UNREAD_LINE_DPI, colorspace=fitz.csGRAY, alpha=False)
    ink = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)[:, :pix.width] < 128
    scale = UNREAD_LINE_DPI / 72
    rows = ink.any(axis=1)
    bands, y = [], 0
    while y < len(rows):
        if not rows[y]:
            y += 1
            continue
        start = y
        while y < len(rows) and rows[y]:
            y += 1
        top, bottom = start / scale, y / scale
        covered = any(min(w[3], bottom) - max(w[1], top) > (bottom - top) * .3 for w in words)
        columns = ink[start:y].any(axis=0)
        runs = int(columns[0]) + int(np.count_nonzero(columns[1:] & ~columns[:-1]))
        bands.append((top, bottom, covered, runs))
    heights = sorted(b - t for t, b, covered, _ in bands if covered and b - t > 1)
    if not heights:
        return []
    line = heights[len(heights) // 2]
    first, last = min(w[1] for w in words), max(w[3] for w in words)
    return [(round(top, 2), round(bottom, 2)) for top, bottom, covered, runs in bands
            if not covered and runs >= 6 and first < top and bottom < last
            and line * .6 <= bottom - top <= line * 1.6]


def _recovered_unread_lines(original, image_tables):
    from services.financial.statement_reading_quality import recovers_unread_lines
    return recovers_unread_lines(original['quality'], [table.to_json() for table in image_tables],
                                 original['unread_lines'])


def _outline_reader(page, refinements):
    """A cell reader from the page's character outlines, when the page was read from them; else ``None``."""
    record = next((r for r in refinements or () if r.get('field') == 'vector_glyph_reading'), None)
    if record is None or not record.get('labels') or page.rotation:
        return None
    from app.pipeline.vector_glyph_reading import TurnedPage, page_glyphs, read_rect, turn_rect
    labels = {shape: (label, votes, total) for shape, label, votes, total in record['labels']}
    rotation = record.get('rotation') or 0
    if rotation:
        # The labels were decided on the page turned upright: the cells are read in that frame too.
        glyphs = page_glyphs(TurnedPage(page, rotation))
        width, height = page.rect.width, page.rect.height
        return lambda rect: read_rect(glyphs, labels, turn_rect(rect, rotation, width, height))
    glyphs = page_glyphs(page)
    return lambda rect: read_rect(glyphs, labels, rect)


def _verify_recognised_money(page, tables, chunks, *, text_origin, extraction_method, rotation=0,
                             refinements=None):
    """Hold recognised money cells that the page image does not confirm.

    Digital text layers return unchanged at no cost. A valid-looking misread
    parses and can reconcile with every printed control, so recognised money
    is reread from crops of the page image and any cell those readings do not
    confirm is marked unreadable for review. A crop value replaces it only when
    the statement's own agreed controls pin that value (``repair_pinned_cells``), or
    when an independent glyph reader gives the same value and every printed control
    on the page reconciles with it (``repair_with_second_reader``). On an Andrews
    page, a held cell takes whichever of its printed readings (page or crop) the
    agreed controls pin (``repair_pinned_readings``).
    """
    from app.pipeline.statement_money_verification import (page_needs_verification, repair_pinned_cells,
        repair_pinned_readings, repair_with_second_reader, verify_money_cells)
    if not tables or not page_needs_verification(text_origin, extraction_method):
        return chunks, tables, []
    try:
        try:
            outline_reading = _outline_reader(page, refinements)
        except Exception:
            logger.warning('Vector outline cell reading unavailable; money cells are cropped', exc_info=True)
            outline_reading = None
        refined, records = verify_money_cells(page, tables, rotation=rotation,
            deadline=time.monotonic() + 30, language=settings.tesseract_lang, outline_reading=outline_reading)
        repairs = []
        try:
            refined, repairs = repair_pinned_cells(page, refined, records[0] if records else None)
            records = records + repairs
        except Exception:
            logger.warning('Pinned money repair unavailable; disputed cells stay held', exc_info=True)
        remaining = records[0] if records else None
        if not repairs:
            try:
                refined, pinned = repair_pinned_readings(page, refined, records[0] if records else None)
                records = records + pinned
                repairs = [r for r in pinned if r.get('decision') == 'repaired']
                if repairs and repairs[0].get('unresolved'):
                    # Sections the agreed controls resolved are repaired; the
                    # cells still held go to the independent reader as before.
                    done = {(c['table_index'], c['row_index'], c['column_index']) for c in repairs[0]['cells']}
                    remaining = dict(remaining, cells=[c for c in remaining['cells']
                        if (c['table_index'], c['row_index'], c['column_index']) not in done])
                    repairs = []
            except Exception:
                logger.warning('Pinned reading repair unavailable; disputed cells stay held', exc_info=True)
        if not repairs and settings.statement_glyph_second_reader:
            try:
                refined, second = repair_with_second_reader(page, refined, remaining,
                    rotation=rotation, deadline=time.monotonic() + 20, language=settings.tesseract_lang)
                records = records + second
            except Exception:
                logger.warning('Second money reader unavailable; disputed cells stay held', exc_info=True)
    except Exception:
        logger.warning('Money-cell verification failed; holding recognised money for review', exc_info=True)
        try:
            refined, records = verify_money_cells(page, tables, rotation=rotation,
                deadline=time.monotonic(), language=settings.tesseract_lang, measure=False)
        except Exception:
            logger.error('Recognised money could not be marked for review', exc_info=True)
            return chunks, tables, []
    if refined is not tables:
        reader = _load_table_reader()
        chunks = reader.chunks_of(refined) if reader is not None else [t.chunk for t in refined]
    return chunks, refined, records


def _prepare_scan(page):
    """The page straightened and clarified for reading, or ``None`` to read it as scanned.

    See ``scan_preprocessing``: only a full-page scan that measures tilted,
    coarse or pale is changed, and a failure here never costs the page.
    """
    if not settings.pdf_scan_preprocessing:
        return None
    try:
        from app.pipeline.scan_preprocessing import prepare_scan_page
        return prepare_scan_page(page)
    except Exception:
        logger.warning('Scan preprocessing unavailable; reading the page as scanned', exc_info=True)
        return None


def _crop_page_for_original_geometry(page, prepared, refinements):
    """The image that rectangles measured on ``page`` itself can be cropped from.

    A prepared page that was only resampled or contrast-stretched has the same
    frame as the original, so its clearer image serves the crop rereads. A
    turned page does not: the original page's own rectangles would land beside
    the printed cell, so the original image is used and the record says so.
    """
    if prepared is None:
        return page
    used = prepared.same_frame
    for index, entry in enumerate(refinements):
        if entry.get('field') == prepared.record['field']:
            refinements[index] = dict(entry, used_for='crop_rereads' if used else 'not_used')
    return prepared.page if used else page


def _page_rotation(refinements):
    return next((r['rotation'] for r in refinements or [] if r.get('field') == 'page_orientation'), 0)


def _retain_native_statement(page_result, original, table_chunks, extracted_tables, reason):
    page_result.text = original['text']
    page_result.text_origin = original['origin']
    page_result.extraction_method = 'native'
    page_result.ocr_status = 'native_retained'
    page_result.ocr_geometry_status = 'native_retained'
    page_result.ocr_refinements.append(dict(field='statement_page_reading', decision='native_retained',
        reason=reason, original_quality=original['quality'],
        **({'unread_lines': [list(b) for b in original['unread_lines']]} if original.get('unread_lines') else {})))
    table_chunks.extend(original['chunks'])
    extracted_tables.extend(original['tables'])


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
) -> tuple[str, float | None, dict]:
    data = pytesseract.image_to_data(
        image,
        lang=settings.tesseract_lang,
        config=f"--oem 1 --psm {page_segmentation_mode} --dpi {dpi}",
        output_type=pytesseract.Output.DICT,
        timeout=_remaining_ocr_timeout(deadline),
    )
    text, confidence = _text_and_confidence_from_tesseract(data)
    return text, confidence, data


def _ocr_at_rotation(
    image: Image.Image,
    *,
    clockwise_rotation: int,
    dpi: int,
    deadline: float,
    page_segmentation_mode: int = 1,
) -> tuple[str, float | None, dict]:
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


INKLESS_WORD_THRESHOLD = 128
INKLESS_WORD_PADDING = 4


def _drop_inkless_words(data: dict, image: Image.Image) -> tuple[dict, list[dict]]:
    """``data`` without low-confidence recognised words over blank paper.

    Tesseract can report a word in an empty gap (measured: an ``=`` at
    confidence 8 to 45 between an amount and its running balance on
    straightened and contrast-stretched scans, its box pure white). Such a
    word was not printed, and between two money columns it merges them into
    one cell. A word is dropped only when its confidence is below
    ``LOW_CONFIDENCE_THRESHOLD`` and its rectangle, widened by
    ``INKLESS_WORD_PADDING`` pixels (about one point at 300 dpi) on every
    side, has no pixel darker than ``INKLESS_WORD_THRESHOLD``. The widening
    matters: a real colon on a straightened BBVA page was reported at
    confidence 92 with a one-pixel box beside its dots (darkest pixel 174
    inside the box, 8 within four pixels of it). The caller applies this only
    to a prepared scan, where ink is black or measured darker than grey 125.
    """
    texts = data.get("text") or []
    fields = ("left", "top", "width", "height")
    if any(not isinstance(data.get(name), list) or len(data[name]) != len(texts) for name in fields):
        return data, []
    grey = image.convert("L")
    try:
        keep, dropped = [], []
        for index, raw in enumerate(texts):
            word = str(raw or "").strip()
            left, top, width, height = (data[name][index] for name in fields)
            try:
                confidence = float(data.get("conf", [None] * len(texts))[index])
            except (TypeError, ValueError):
                confidence = None
            if (word and width > 0 and height > 0 and confidence is not None
                    and 0 <= confidence < LOW_CONFIDENCE_THRESHOLD):
                pad = INKLESS_WORD_PADDING
                with grey.crop((max(0, left - pad), max(0, top - pad), min(grey.width, left + width + pad),
                                min(grey.height, top + height + pad))) as box:
                    if box.getextrema()[0] >= INKLESS_WORD_THRESHOLD:
                        dropped.append(dict(text=word, confidence=data.get("conf", [None] * len(texts))[index],
                                            box=[left, top, width, height]))
                        continue
            keep.append(index)
    finally:
        grey.close()
    if not dropped:
        return data, []
    filtered = {name: ([values[i] for i in keep] if isinstance(values, list) and len(values) == len(texts) else values)
                for name, values in data.items()}
    return filtered, dropped


# A printed line page OCR skipped is read from its own crop: at most this many lines per page, each
# word kept only at this OCR confidence or more (a lone mark or noise reads lower).
MAX_UNREAD_LINES = 40
UNREAD_LINE_MIN_CONFIDENCE = 60.0


def _read_unread_lines(image: Image.Image, data: dict, words: list, glyphs: list, dpi: int,
                       deadline: float | None) -> tuple[dict, list[dict]]:
    """``data`` with the words of printed lines page OCR skipped, each read from the line's own image.

    The character outlines show every printed line (``vector_glyph_reading.unread_lines``):
    a run of characters no OCR word covers is cropped from the page render, made black on
    white at the inkless threshold (vector print renders solid black; a shaded band does
    not), and read as one text line. A word is kept only when its confidence is at least
    ``UNREAD_LINE_MIN_CONFIDENCE`` and every character under it belongs to that run; a line
    with any word of letters or figures below that confidence is not read at all (part of a
    line is not its reading). Marks without a letter or figure are left out. Kept words are
    re-read from the outlines like every other word. Any failure (including the page's time
    budget) keeps the lines read so far.
    """
    from app.pipeline.vector_glyph_reading import _Index, unread_lines
    scale = 72.0 / dpi
    found = []
    index = _Index(glyphs)
    try:
        for box, run in unread_lines(glyphs, words)[:MAX_UNREAD_LINES]:
            x0, y0, x1, y1 = box
            pad = max(2.0, 0.5 * (y1 - y0))
            left, top = max(0, math.floor((x0 - pad) / scale)), max(0, math.floor((y0 - pad) / scale))
            right = min(image.width, math.ceil((x1 + pad) / scale))
            bottom = min(image.height, math.ceil((y1 + pad) / scale))
            if right <= left or bottom <= top:
                continue
            crop = image.crop((left, top, right, bottom)).convert('L').point(
                lambda value: 0 if value < INKLESS_WORD_THRESHOLD else 255)
            try:
                read = pytesseract.image_to_data(crop, lang=settings.tesseract_lang,
                    config=f"--oem 1 --psm 7 --dpi {dpi}", output_type=pytesseract.Output.DICT,
                    timeout=_remaining_ocr_timeout(deadline) if deadline is not None else 0)
            finally:
                crop.close()
            members = {id(g) for g in run}
            line = []
            for i, text in enumerate(read.get('text') or []):
                text = str(text or '').strip()
                try:
                    confidence = float(read['conf'][i])
                except (TypeError, ValueError):
                    confidence = -1.0
                if not text or not re.search(r'[0-9A-Za-z]', text):
                    continue
                if confidence < UNREAD_LINE_MIN_CONFIDENCE:
                    # Part of a line is not a reading of it: the line stays unread.
                    line = []
                    break
                w_left, w_top = left + read['left'][i], top + read['top'][i]
                w_width, w_height = read['width'][i], read['height'][i]
                page_box = (w_left * scale, w_top * scale, (w_left + w_width) * scale, (w_top + w_height) * scale)
                under = index.within(*page_box)
                if not under or not all(id(g) in members for g in under):
                    line = []
                    break
                line.append((text, confidence, (w_left, w_top, w_width, w_height)))
            if line:
                found.append(line)
    except Exception:
        logger.warning('Unread outline line reading stopped; keeping the lines read so far', exc_info=True)
    if not found:
        return data, []
    texts = data.get("text") or []
    data = {name: list(values) if isinstance(values, list) and len(values) == len(texts) else values
            for name, values in data.items()}
    block = max((b for b in data.get('block_num') or [0] if isinstance(b, int)), default=0)
    record = []
    for number, line in enumerate(found, start=1):
        for word_number, (text, confidence, (left, top, width, height)) in enumerate(line, start=1):
            row = dict(level=5, page_num=1, block_num=block + number, par_num=1, line_num=1, word_num=word_number,
                       left=left, top=top, width=width, height=height, conf=confidence, text=text)
            for name, values in data.items():
                if isinstance(values, list):
                    values.append(row.get(name, 0))
        boxes = [(l, t, l + w, t + h) for _, _, (l, t, w, h) in line]
        record.append(dict(text=' '.join(text for text, _, _ in line),
                           rect=[round(min(b[0] for b in boxes) * scale * 1000), round(min(b[1] for b in boxes) * scale * 1000),
                                 round(max(b[2] for b in boxes) * scale * 1000), round(max(b[3] for b in boxes) * scale * 1000)]))
    return data, record


# The layer guard. A reading step added after the targeted re-reads existed (the skipped-line layer,
# reading revision v20) only adds to a page. The targeted re-reads below (BBVA fields, dates, amounts,
# Santander closing strip) decide whether to run from what the page reading lacks, so a partial line
# the layer added could switch one off (v20: a closing label read without its amount stopped the
# Santander closing-strip re-read, and 18 periods that read before were held). The layer's rows are
# therefore held aside while those re-reads run, and put back after them only where no re-read added
# a word: a line overlapping a re-read's word is left out whole (part of a line is not its reading).
LAYER_ROWS = '_layer_rows'


def _withhold_layer(data: dict, rows: list[int]) -> tuple[dict, list[dict]]:
    """``data`` without the given rows, and those rows (one dict of field values each)."""
    texts = data.get("text") or []
    held = set(rows)
    if not held:
        return data, []
    columns = [name for name, values in data.items() if isinstance(values, list) and len(values) == len(texts)]
    layer = [{name: data[name][i] for name in columns} for i in sorted(held) if i < len(texts)]
    base = {name: ([v for i, v in enumerate(values) if i not in held] if name in columns else values)
            for name, values in data.items()}
    return base, layer


def _restore_layer(data: dict, layer: list[dict], before: dict) -> tuple[dict, list[dict]]:
    """``data`` with the layer's lines put back, except a line overlapping a word the targeted re-reads
    added or changed (any word of ``data`` that is not a word of ``before``, the page as they found it).
    Returns the data and the lines left out ({text, rect} in image pixels, words joined as read)."""
    if not layer:
        return data, []
    def box(row):
        return (row.get('left', 0), row.get('top', 0), row.get('left', 0) + row.get('width', 0),
                row.get('top', 0) + row.get('height', 0))
    def rows_of(values):
        texts = values.get("text") or []
        return [dict(text=str(texts[i] or '').strip(), left=values['left'][i], top=values['top'][i],
                     width=values['width'][i], height=values['height'][i]) for i in range(len(texts))]
    found = {(r['text'], box(r)) for r in rows_of(before) if r['text']}
    reread = [box(r) for r in rows_of(data) if r['text'] and (r['text'], box(r)) not in found]
    def overlaps(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    lines = {}
    for row in layer:
        lines.setdefault(row.get('block_num'), []).append(row)
    texts = data.get("text") or []
    columns = [name for name, values in data.items() if isinstance(values, list) and len(values) == len(texts)]
    data = {name: (list(values) if name in columns else values) for name, values in data.items()}
    block = max((b for b in data.get('block_num') or [0] if isinstance(b, int)), default=0)
    left_out = []
    for number, (_, line) in enumerate(sorted(lines.items(), key=lambda item: str(item[0])), start=1):
        if any(overlaps(box(row), other) for row in line for other in reread):
            boxes = [box(row) for row in line]
            left_out.append(dict(text=' '.join(str(row.get('text') or '') for row in line).strip(),
                                 rect=[min(b[0] for b in boxes), min(b[1] for b in boxes),
                                       max(b[2] for b in boxes), max(b[3] for b in boxes)]))
            continue
        for row in line:
            for name in columns:
                data[name].append(block + number if name == 'block_num' else row.get(name, 0))
    return data, left_out


def _read_vector_outlines(page: fitz.Page, data: dict, dpi: int, *, image: Image.Image | None = None,
                          deadline: float | None = None) -> tuple[dict, dict | None]:
    """``data`` with each recognised word re-read from the page's character outlines (``vector_glyph_reading``).

    Returns the record of what was read: the shape labels the page's OCR
    decided (kept so the money check can read a cell from its outlines) and
    every word whose reading changed, that was dropped as printed nowhere, or that
    was added as a printed amount OCR skipped.
    """
    from app.pipeline.vector_glyph_reading import (METHOD, inkless, other_ink, page_glyphs, read_words, shape_labels,
        split_amounts, unread_lines, unread_words)
    texts = data.get("text") or []
    fields = ("left", "top", "width", "height")
    if any(not isinstance(data.get(name), list) or len(data[name]) != len(texts) for name in fields):
        return data, None
    scale = 72.0 / dpi
    words = [(str(texts[i] or ''), (data["left"][i] * scale, data["top"][i] * scale,
              (data["left"][i] + data["width"][i]) * scale, (data["top"][i] + data["height"][i]) * scale))
             for i in range(len(texts))]
    drawings = page.get_drawings()
    glyphs = page_glyphs(page, drawings)
    lines_read = []
    layer_start = len(texts)
    if image is not None and glyphs:
        data, lines_read = _read_unread_lines(image, data, words, glyphs, dpi, deadline)
    layer_rows = list(range(layer_start, len(data.get("text") or [])))
    if lines_read:
        texts = data["text"]
        words = [(str(texts[i] or ''), (data["left"][i] * scale, data["top"][i] * scale,
                  (data["left"][i] + data["width"][i]) * scale, (data["top"][i] + data["height"][i]) * scale))
                 for i in range(len(texts))]
    ink = other_ink(page, drawings)
    labels = shape_labels(glyphs, words)
    readings = read_words(glyphs, labels, words)
    changed, dropped = [], []
    new_texts = list(texts)
    for index, ((text, box), reading) in enumerate(zip(words, readings)):
        if text.strip() and glyphs and inkless(glyphs, ink, box):
            # Nothing is printed under this word: OCR reported it over blank paper.
            dropped.append(dict(original_text=text.strip(), rect=[round(v * 1000) for v in box]))
            new_texts[index] = ''
        elif reading is not None and reading != text.strip():
            changed.append(dict(original_text=text.strip(), text=reading,
                                rect=[round(v * 1000) for v in box]))
            new_texts[index] = reading
    joined = []
    for first, second, text in split_amounts(glyphs, labels, [(t, box) for t, (_, box) in zip(new_texts, words)]):
        # One printed amount OCR split where it skipped the thousands comma: the first word becomes the whole
        # amount over both boxes, the second is emptied (as a word printed nowhere is).
        if not joined:
            data = {name: list(values) if isinstance(values, list) and len(values) == len(texts) else values
                    for name, values in data.items()}
        (a0, a1, a2, a3), (b0, b1, b2, b3) = words[first][1], words[second][1]
        box = (min(a0, b0), min(a1, b1), max(a2, b2), max(a3, b3))
        left, top = data["left"][first], min(data["top"][first], data["top"][second])
        data["width"][first] = max(data["left"][first] + data["width"][first],
                                   data["left"][second] + data["width"][second]) - left
        data["height"][first] = max(data["top"][first] + data["height"][first],
                                    data["top"][second] + data["height"][second]) - top
        data["top"][first] = top
        joined.append(dict(original_texts=[new_texts[first], new_texts[second]], text=text,
                           rect=[round(v * 1000) for v in box]))
        new_texts[first], new_texts[second] = text, ''
        words[first], words[second] = (text, box), ('', words[second][1])
    added = []
    image_width, image_height = math.floor(page.rect.width / scale), math.floor(page.rect.height / scale)
    for text, (x0, y0, x1, y1) in unread_words(glyphs, labels, [(t, box) for t, (_, box) in zip(new_texts, words)]):
        # Inside the rendered image, which the OCR geometry projection requires of every word.
        left, top = max(0, math.floor(x0 / scale)), max(0, math.floor(y0 / scale))
        right, bottom = min(image_width, math.ceil(x1 / scale)), min(image_height, math.ceil(y1 / scale))
        if right > left and bottom > top:
            added.append((text, (x0, y0, x1, y1), (left, top, right - left, bottom - top)))
    if added:
        # Amounts OCR skipped, as words of their own: no OCR confidence, each its own block and line.
        data = {name: list(values) if isinstance(values, list) and len(values) == len(texts) else values
                for name, values in data.items()}
        data['text'] = new_texts
        block = max((b for b in data.get('block_num') or [0] if isinstance(b, int)), default=0)
        for number, (text, _, (left, top, width, height)) in enumerate(added, start=1):
            row = dict(level=5, page_num=1, block_num=block + number, par_num=1, line_num=1, word_num=1,
                       left=left, top=top, width=width, height=height, conf=-1, text=text)
            for name, values in data.items():
                if isinstance(values, list) and name != 'text':
                    values.append(row.get(name, 0))
            new_texts.append(text)
    # Printed lines still under no word after every reading above: kept so a reader of the page knows
    # where its text is incomplete (``lines_checked`` marks a reading that looked).
    final_words = [(t, box) for t, (_, box) in zip(new_texts, words)] + [(t, box) for t, box, _ in added]
    lines_unread = [[round(v * 1000) for v in box] for box, _ in unread_lines(glyphs, final_words)]
    record = dict(field='vector_glyph_reading', method=METHOD,
                  decision='read' if changed or dropped or added or lines_read or joined else 'unchanged',
                  characters=len(glyphs), shapes=len({g.shape for g in glyphs}), labelled_shapes=len(labels),
                  characters_labelled=sum(g.shape in labels for g in glyphs),
                  words_read=sum(r is not None for r in readings), words_changed=changed, words_dropped=dropped,
                  words_joined=joined,
                  words_added=[dict(text=t, rect=[round(v * 1000) for v in box]) for t, box, _ in added],
                  lines_read=lines_read, lines_checked=True, lines_unread=lines_unread,
                  labels=[[shape, label, votes, total] for shape, (label, votes, total) in sorted(labels.items())])
    # Not stored: which rows of the returned data are the skipped-line layer (see _withhold_layer).
    record[LAYER_ROWS] = layer_rows
    return (dict(data, text=new_texts) if changed or dropped or added or lines_read or joined else data), record


def _turned_outlines_enabled() -> bool:
    from app.pipeline.vector_glyph_reading import TURNED_PAGES
    return TURNED_PAGES


def _ocr_page(page: fitz.Page, *, drop_inkless_words: bool = False,
              vector_text: bool = False) -> tuple[str, float | None, int, list | None, list[dict]]:
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
    # A vector-text page carries its own orientation: its character outlines
    # are drawn in reading order. When they clearly run left to right the page
    # is read upright; orientation detection is not asked (live: it turned
    # upright glossary, QR-code and closing pages 90 or 180 degrees, which
    # skipped the outline reading and lost printed closing balances).
    upright = False
    if vector_text and not page.rotation:
        try:
            from app.pipeline.vector_glyph_reading import drawn_upright
            upright = drawn_upright(page.get_drawings())
        except Exception:
            logger.warning('Vector outline orientation unavailable; detecting it from the image', exc_info=True)
    try:
        if upright:
            rotation, osd_confidence = 0, None
        else:
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

        text, confidence, best_data = _ocr_at_rotation(
            image,
            clockwise_rotation=rotation,
            dpi=dpi,
            deadline=deadline,
        )

        best_rotation = rotation
        uncertain_orientation = (
            osd_confidence is not None
            and osd_confidence < MIN_RELIABLE_OSD_CONFIDENCE
        )
        low_text_confidence = (
            confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD
        )
        if upright and low_text_confidence:
            alternative_rotations = [0]
        elif uncertain_orientation or low_text_confidence:
            alternative_rotations = [
                (rotation + offset) % 360 for offset in (0, 180, 90, 270)
            ]
        else:
            alternative_rotations = []

        best_score = (confidence if confidence is not None else -1.0, len(text))
        for alternative_rotation in alternative_rotations:
            try:
                alternative_text, alternative_confidence, alternative_data = _ocr_at_rotation(
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
                best_data, best_rotation = alternative_data, alternative_rotation
            if alternative_confidence is not None and alternative_confidence >= 80.0:
                break
        inkless = []
        outlines = None
        # A vector-text page renders its print solid black, like a prepared scan.
        # A vector-text page OCR read turned (a sideways landscape page) is read from its outlines turned
        # the same way (``vector_glyph_reading.TURNED_PAGES``): image, words and outlines share one frame.
        turned = (vector_text and best_rotation in (90, 180, 270) and not page.rotation
                  and _turned_outlines_enabled())
        oriented = image if not turned else image.rotate(-best_rotation, expand=True, fillcolor="white")
        try:
            if (drop_inkless_words or vector_text) and (best_rotation == 0 or turned):
                best_data, inkless = _drop_inkless_words(best_data, oriented)
                if inkless:
                    text, confidence = _text_and_confidence_from_tesseract(best_data)
            if vector_text and (best_rotation == 0 or turned) and not page.rotation:
                try:
                    if turned:
                        from app.pipeline.vector_glyph_reading import TurnedPage
                        target = TurnedPage(page, best_rotation)
                    else:
                        target = page
                    best_data, outlines = _read_vector_outlines(target, best_data, dpi, image=oriented,
                                                                deadline=deadline)
                    if outlines and turned:
                        outlines['rotation'] = best_rotation
                    if outlines and (outlines['words_changed'] or outlines['words_dropped'] or outlines['words_added']
                                     or outlines['lines_read']):
                        text, confidence = _text_and_confidence_from_tesseract(best_data)
                except Exception:
                    logger.warning('Vector outline reading unavailable; retaining the OCR reading', exc_info=True)
        finally:
            if oriented is not image:
                oriented.close()
    finally:
        image.close()
    refinements = []
    if inkless:
        refinements.append(dict(field='ocr_inkless_words', decision='dropped', threshold=INKLESS_WORD_THRESHOLD,
                                words=inkless))
    layer = []
    if outlines:
        best_data, layer = _withhold_layer(best_data, outlines.pop(LAYER_ROWS, []))
        refinements.append(outlines)
    before_rereads = best_data
    try:
        from app.pipeline.financial_bbva_ocr import reread_bbva_fields
        refined_data, comparisons = reread_bbva_fields(page, best_data,
            rotation=best_rotation, image_width=pixmap.width, image_height=pixmap.height,
            reader=_load_table_reader(), deadline=deadline, language=settings.tesseract_lang)
        if comparisons:
            text, confidence = _text_and_confidence_from_tesseract(refined_data)
            best_data = refined_data
            refinements.extend(comparisons)
    except Exception:
        logger.warning('Optional BBVA field OCR unavailable; retaining the page reading', exc_info=True)
    try:
        from app.pipeline.financial_date_ocr import reread_financial_dates
        refined_data, comparisons = reread_financial_dates(page, best_data,
            rotation=best_rotation, image_width=pixmap.width, image_height=pixmap.height,
            reader=_load_table_reader(), deadline=deadline, language=settings.tesseract_lang)
        if comparisons:
            new_text, new_confidence = _text_and_confidence_from_tesseract(refined_data)
            best_data = refined_data
            refinements.extend(comparisons)
            text, confidence = new_text, new_confidence
    except Exception:
        logger.warning('Optional date-region OCR unavailable; retaining the page reading', exc_info=True)
    try:
        from app.pipeline.financial_transaction_date_ocr import reread_financial_transaction_dates
        refined_data, comparisons = reread_financial_transaction_dates(page, best_data,
            rotation=best_rotation,image_width=pixmap.width,image_height=pixmap.height,
            reader=_load_table_reader(),deadline=deadline,language=settings.tesseract_lang)
        if comparisons:
            text, confidence = _text_and_confidence_from_tesseract(refined_data)
            best_data = refined_data
            refinements.extend(comparisons)
    except Exception:
        logger.warning('Optional transaction-date OCR unavailable; retaining the page reading', exc_info=True)
    try:
        from app.pipeline.financial_amount_ocr import reread_financial_amounts
        refined_data, comparisons = reread_financial_amounts(page, best_data,
            rotation=best_rotation, image_width=pixmap.width, image_height=pixmap.height,
            reader=_load_table_reader(), deadline=deadline, language=settings.tesseract_lang)
        if comparisons:
            new_text, new_confidence = _text_and_confidence_from_tesseract(refined_data)
            best_data = refined_data
            refinements.extend(comparisons)
            text, confidence = new_text, new_confidence
    except Exception:
        logger.warning('Optional money-region OCR unavailable; retaining the page reading', exc_info=True)
    try:
        from app.pipeline.financial_santander_ocr import reread_santander_closing
        refined_data, comparisons = reread_santander_closing(page, best_data,
            rotation=best_rotation, image_width=pixmap.width, image_height=pixmap.height,
            reader=_load_table_reader(), deadline=deadline, language=settings.tesseract_lang)
        if comparisons:
            text, confidence = _text_and_confidence_from_tesseract(refined_data)
            best_data = refined_data
            refinements.extend(comparisons)
    except Exception:
        logger.warning('Optional Santander closing OCR unavailable; retaining the page reading', exc_info=True)
    if layer:
        best_data, left_out = _restore_layer(best_data, layer, before_rereads)
        if left_out:
            # Recorded in page points x1000 like every other rect of the record; a line left out is
            # not part of the reading, so it leaves lines_read.
            to_page = 72.0 / dpi * 1000
            outlines['lines_left_to_rereads'] = [dict(line, rect=[round(v * to_page) for v in line['rect']])
                                                 for line in left_out]
            left_texts = [line['text'] for line in left_out]
            kept = []
            for line in outlines['lines_read']:
                if line['text'] in left_texts:
                    left_texts.remove(line['text'])
                else:
                    kept.append(line)
            outlines['lines_read'] = kept
        text, confidence = _text_and_confidence_from_tesseract(best_data)
    if best_rotation:
        # Later crops of this page's cells must be turned the same way.
        refinements.append(dict(field='page_orientation', rotation=best_rotation))
    from app.pipeline.ocr_geometry import project_ocr_words
    try:
        words = project_ocr_words(best_data, rotation=best_rotation,
            image_width=pixmap.width, image_height=pixmap.height,
            page_width=page.rect.width, page_height=page.rect.height)
    except ValueError:
        logger.warning("OCR word geometry unavailable; retaining recovered text only")
        words = None
    return text, confidence, dpi, words, refinements


def _page_span(page_result: _PageResult, start_char: int) -> dict:
    span = {
        "page": page_result.page_number,
        "start_char": start_char,
        "end_char": start_char + len(page_result.text),
        "extraction_method": page_result.extraction_method,
        "text_origin": page_result.text_origin,
        "detection_reason": page_result.detection_reason,
    }
    if page_result.ocr_refinements:
        span['ocr_refinements'] = page_result.ocr_refinements
    if page_result.ocr_status is not None:
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
                "ocr_geometry_status": page_result.ocr_geometry_status,
                "ocr_refinements": page_result.ocr_refinements,
            }
        )
    return span


def _restore_page_tables(values):
    """Rebuild only the known table/locator types from a native-page checkpoint."""
    if not values:
        return []
    reader = _load_table_reader()
    if reader is None:
        raise PdfOcrError('The table reader is unavailable while resuming saved PDF pages')
    from services.financial.locators import Locator
    from services.financial.table_geometry import LocatedCell, LocatedTable
    result = []
    for entry in values:
        value = entry['metadata']
        geometry = value.get('table')
        located = None
        if geometry is not None:
            located = LocatedTable(page_number=geometry['page'], locator=Locator.from_json(geometry['table']),
                cells=tuple(LocatedCell(row=c['row'],column=c['column'],text=c['text'],locator=Locator.from_json(c['locator']))
                            for c in geometry['values']), unlocated_values=geometry['unlocated_values'])
        result.append(reader.ExtractedTable(chunk=entry['chunk'],table_source=reader.TableSource(value['table_source']),
            geometry=located,geometry_source=reader.GeometrySource(value['geometry_source']),
            degraded_reason=value.get('degraded_reason')))
    return result


def _words_run_vertically(words):
    """Whether most recognised words stand on end on the displayed page (text printed sideways).

    A recorded page orientation alone does not say this: Tesseract's own layout
    analysis can turn the image back, and a landscape page with upright text is
    then recorded as read at 90 degrees while its words lie flat on the page.
    Only words of three or more characters count; a word is on end when its box
    is at least 1.5 times taller than wide.
    """
    tall = wide = 0
    for x0, y0, x1, y1, text in words or []:
        if len(text.strip()) < 3:
            continue
        width, height = x1 - x0, y1 - y0
        if height > 1.5 * width:
            tall += 1
        elif width > 1.5 * height:
            wide += 1
    return tall > wide


def _read_ocr_page(document, page_index, page_result, prepared, page_cache, native_alternatives,
                   table_chunks, extracted_tables):
    """Read one page selected for OCR into ``page_result`` and the table lists.

    ``prepared`` (``scan_preprocessing``) is the image the page reading, its
    rereads and the money-cell crop check measure, when the scan needed
    preparing; the original page otherwise. Returns ``True`` when the image
    reading failed and the page's embedded reading was kept for review.
    """
    page = document[page_index]
    reading_page = prepared.page if prepared is not None else page
    try:
        checkpoint = page_cache / f'ocr-{page_index}.json' if page_cache else None
        if checkpoint and checkpoint.exists():
            text, confidence, dpi, words, refinements = json.loads(checkpoint.read_text())
        else:
            text, confidence, dpi, words, refinements = (_ocr_page(reading_page, drop_inkless_words=True)
                if prepared is not None else _ocr_page(reading_page, vector_text=True)
                if page_result.detection_reason == 'vector_text' else _ocr_page(reading_page))
            if prepared is not None:
                refinements = [prepared.record, *refinements]
            if checkpoint:
                from app.services.ingestion_checkpoints import atomic_json
                atomic_json(checkpoint, [text, confidence, dpi, words, refinements])
        page_result.ocr_refinements = refinements
    except Exception as exc:
        if original := native_alternatives.get(page_index):
            if prepared is not None:
                page_result.ocr_refinements.append(dict(prepared.record))
            crop_page = _crop_page_for_original_geometry(page, prepared, page_result.ocr_refinements)
            chunks, verified, verification = _verify_recognised_money(crop_page,
                original['tables'], original['chunks'], text_origin=original['origin'],
                extraction_method='native')
            page_result.ocr_refinements.extend(verification)
            original = {**original, 'tables': verified, 'chunks': chunks}
            _retain_native_statement(page_result, original, table_chunks, extracted_tables,
                'Image reread unavailable; unresolved embedded readings remain for review.')
            return True
        if isinstance(exc, RuntimeError) and _is_tesseract_timeout_error(exc):
            # One slow page must not discard every other page of the file.
            # The page is kept unread and marked; the financial reader holds
            # any statement that could include it until the file is read again.
            logger.warning("PDF OCR timed out page=%d; page kept unread", page_result.page_number)
            page_result.text = ''
            page_result.text_origin = 'unread'
            page_result.ocr_status = OCR_TIMEOUT_STATUS
            page_result.ocr_confidence = None
            page_result.ocr_language = settings.tesseract_lang
            page_result.ocr_geometry_status = 'unavailable'
            return False
        logger.error(
            "PDF OCR failed page=%d reason=%s",
            page_result.page_number,
            exc,
        )
        message = 'Tesseract executable was not found' if isinstance(exc, pytesseract.TesseractNotFoundError) else str(exc)
        raise PdfOcrError(
            f"OCR failed on PDF page {page_result.page_number}: {message}"
        ) from exc

    page_result.text = text
    page_result.text_origin = "recognised_glyphs"
    page_result.ocr_status = "success" if text else "no_text"
    page_result.ocr_confidence = confidence
    page_result.ocr_dpi = dpi
    page_result.ocr_language = settings.tesseract_lang
    page_result.ocr_geometry_status = "unavailable"
    reader = _load_table_reader()
    ocr_tables = []
    if words is not None and reader is not None:
        try:
            rotation = _page_rotation(page_result.ocr_refinements)
            if rotation in (90, 270) and hasattr(reader, 'upright_ocr_words') and _words_run_vertically(words):
                # A page OCR read turned: group its rows and columns in the frame the text reads
                # upright in, then store every rectangle in displayed page space as always.
                upright, (width, height) = reader.upright_ocr_words(words, rotation=rotation,
                    page_width=page.rect.width, page_height=page.rect.height)
                ocr_tables = reader.displayed_tables(reader.read_positioned_ocr_words(upright,
                    page_number=page_result.page_number, page_width=width, page_height=height), rotation=rotation)
                page_result.ocr_refinements.append(dict(field='table_frame', frame='upright', rotation=rotation))
            else:
                ocr_tables = reader.read_positioned_ocr_words(words,
                    page_number=page_result.page_number,
                    page_width=page.rect.width,
                    page_height=page.rect.height)
            if any(table.geometry_source.value == "cell_rectangles" for table in ocr_tables):
                page_result.ocr_geometry_status = "available"
        except Exception:
            logger.warning("OCR source geometry unavailable on page %s", page_result.page_number, exc_info=True)

    original = native_alternatives.get(page_index)
    quality = _statement_reading_quality(ocr_tables) if original else None
    preferred = bool(original) and _prefer_statement_image(original['quality'], quality)
    recovered = None
    if original and not preferred and original.get('unread_lines'):
        # The embedded layer left printed lines unread: the image reading may
        # replace it only by adding exactly those lines (``recovers_unread_lines``).
        try:
            recovered = _recovered_unread_lines(original, ocr_tables)
        except Exception:
            logger.warning('Unread line recovery unavailable; embedded reading kept', exc_info=True)
    if original and not preferred and not recovered:
        # A whole-page image reading can omit a row. Keep that page's
        # original geometry and try only demonstrably unreadable statement
        # money cells; crop disagreement never replaces a value.
        crop_page = _crop_page_for_original_geometry(page, prepared, page_result.ocr_refinements)
        try:
            from app.pipeline.financial_amount_ocr import refine_statement_native_cells
            refined, refinements = refine_statement_native_cells(crop_page, original['tables'],
                deadline=time.monotonic() + 60, language=settings.tesseract_lang)
            if refinements:
                page_result.ocr_refinements.extend(refinements)
                original = {**original, 'tables': refined, 'chunks': reader.chunks_of(refined)}
        except Exception:
            logger.debug('Native statement cell reread unavailable', exc_info=True)
        chunks, verified, verification = _verify_recognised_money(crop_page,
            original['tables'], original['chunks'], text_origin=original['origin'],
            extraction_method='native')
        page_result.ocr_refinements.extend(verification)
        original = {**original, 'tables': verified, 'chunks': chunks}
        _retain_native_statement(page_result, original, table_chunks, extracted_tables,
            'Image reread did not safely improve the same account, period and payment rows.')
    else:
        ocr_chunks = reader.chunks_of(ocr_tables) if reader is not None else []
        ocr_chunks, ocr_tables, verification = _verify_recognised_money(reading_page,
            ocr_tables, ocr_chunks, text_origin='recognised_glyphs', extraction_method='tesseract_ocr',
            rotation=_page_rotation(page_result.ocr_refinements), refinements=page_result.ocr_refinements)
        page_result.ocr_refinements.extend(verification)
        table_chunks.extend(ocr_chunks)
        extracted_tables.extend(ocr_tables)
        if original:
            page_result.ocr_refinements.append(dict(field='statement_page_reading', decision='image_selected',
                original_quality=original['quality'], image_quality=quality,
                original_text_sha256=hashlib.sha256(original['text'].encode()).hexdigest(),
                **(dict(reason='recovered_unread_lines', unread_lines=[list(b) for b in original['unread_lines']],
                        added_rows=recovered['added']) if recovered else {})))
    return False


def _extract_pdf_sync(
    file_path: str,
    report_progress: Callable[[PdfExtractionProgress], None] | None = None,
    *,
    reading_mode: str = "automatic",
    checkpoint_directory: str | None = None,
) -> PdfExtractionResult:
    if reading_mode not in ("automatic", "page_images"):
        raise ValueError("Unknown PDF reading method")
    started = time.perf_counter()
    table_chunks: list[str] = []
    # Positionally aligned with table_chunks: the reader returns both from one
    # pass precisely so that alignment is a property of the data rather than
    # something these two lists have to be trusted to maintain.
    extracted_tables: list[Any] = []
    page_cache = None
    if checkpoint_directory:
        configuration = {name: getattr(settings, name) for name in _PDF_WORKER_SETTINGS}
        configuration.update(reading_mode=reading_mode, reading_revision=PDF_READING_REVISION)
        stamp = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
        page_cache = Path(checkpoint_directory) / stamp

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
        native_alternatives = {}
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            checkpoint = page_cache / f'native-{page_index}.json' if page_cache else None
            if checkpoint and checkpoint.exists():
                cached = json.loads(checkpoint.read_text())
                page_result = _PageResult(page_number=page_number, text=cached['text'],
                    text_origin=cached['text_origin'], ocr_refinements=cached.get('refinements', []))
                pages.append(page_result)
                table_chunks.extend(cached['chunks'])
                extracted_tables.extend(_restore_page_tables(cached['tables']))
                if report_progress:
                    report_progress(PdfExtractionProgress(f'Resumed PDF page {page_number} of {document.page_count}',
                        page_number, document.page_count, page_number))
                continue
            native_text = page.get_text()
            detection_reason = ("requested_page_images" if reading_mode == "page_images"
                else _ocr_detection_reason(page, native_text))
            if detection_reason is None:
                page_result = _PageResult(
                    page_number=page_number, text=native_text,
                    text_origin=_embedded_text_origin(page),
                )
                page_chunks, page_tables = _extract_native_tables(page, page_number)
                quality = _statement_reading_quality(page_tables)
                unread = []
                if quality and not quality['unreadable'] and page_result.text_origin == 'recognised_glyphs':
                    try:
                        unread = _unread_printed_lines(page)
                    except Exception:
                        logger.debug('Unread printed line check unavailable', exc_info=True)
                if quality and (quality['unreadable'] or unread):
                    native_alternatives[page_index] = dict(text=native_text, origin=page_result.text_origin,
                        chunks=page_chunks, tables=page_tables, quality=quality, unread_lines=unread)
                    page_result.extraction_method = 'tesseract_ocr'
                    page_result.detection_reason = ('unreadable_statement_fields' if quality['unreadable']
                                                    else 'unread_printed_lines')
                    ocr_indexes.append(page_index)
                else:
                    from app.pipeline.statement_money_verification import page_needs_verification
                    prepared = (_prepare_scan(page) if page_tables
                                and page_needs_verification(page_result.text_origin, 'native') else None)
                    try:
                        crop_page = page
                        if prepared is not None and prepared.same_frame:
                            page_result.ocr_refinements.append(dict(prepared.record, used_for='crop_rereads'))
                            crop_page = prepared.page
                        page_chunks, page_tables, verification = _verify_recognised_money(crop_page, page_tables,
                            page_chunks, text_origin=page_result.text_origin, extraction_method='native')
                    finally:
                        if prepared is not None:
                            prepared.close()
                    page_result.ocr_refinements.extend(verification)
                    table_chunks.extend(page_chunks)
                    extracted_tables.extend(page_tables)
                if checkpoint and page_index not in native_alternatives:
                    from app.services.ingestion_checkpoints import atomic_json
                    atomic_json(checkpoint, dict(text=native_text, text_origin=page_result.text_origin,
                        chunks=page_chunks, tables=[dict(chunk=t.chunk, metadata=t.to_json()) for t in page_tables],
                        refinements=page_result.ocr_refinements))
            else:
                page_result = _PageResult(
                    page_number=page_number,
                    text=native_text,
                    extraction_method="tesseract_ocr",
                    detection_reason=detection_reason,
                )
                ocr_indexes.append(page_index)
            pages.append(page_result)
            if report_progress:
                report_progress(PdfExtractionProgress(f"Read PDF page {page_number} of {document.page_count}",
                    page_number, document.page_count, page_number))

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
            prepared = _prepare_scan(document[page_index])
            try:
                kept_after_failure = _read_ocr_page(document, page_index, pages[page_index], prepared,
                    page_cache, native_alternatives, table_chunks, extracted_tables)
            finally:
                if prepared is not None:
                    prepared.close()
            if kept_after_failure:
                if report_progress:
                    report_progress(PdfExtractionProgress('Kept original statement reading for review',
                        completed, ocr_count, pages[page_index].page_number))
                continue
            if report_progress:
                report_progress(
                    PdfExtractionProgress(
                        message=(
                            f"OCR page {completed} of {ocr_count} "
                            f"(PDF page {pages[page_index].page_number})"
                        ),
                        completed=completed,
                        total=ocr_count,
                        pdf_page=pages[page_index].page_number,
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
        used_ocr_count = sum(page.extraction_method == 'tesseract_ocr' for page in pages)
        if not used_ocr_count:
            extraction_mode = "native"
        elif used_ocr_count == len(pages):
            extraction_mode = "ocr"
        else:
            extraction_mode = "hybrid"

        from app.pipeline.pdf_processing_manifest import capture_pdf_processing_manifest
        metadata = {
            "file_type": "pdf",
            "processing_manifest": capture_pdf_processing_manifest(settings=settings, ocr_used=bool(ocr_count), reading_mode=reading_mode),
            "pdf_reading_mode": reading_mode,
            "page_count": len(pages),
            "is_scanned": ocr_count > 0,
            "extraction_mode": extraction_mode,
            "ocr_page_count": used_ocr_count,
            "ocr_attempted_page_count": ocr_count,
            "native_page_count": len(pages) - used_ocr_count,
            "low_confidence_page_count": low_confidence_count,
            "ocr_timed_out_pages": [page.page_number for page in pages if page.ocr_status == OCR_TIMEOUT_STATUS],
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
            len(pages) - used_ocr_count,
            used_ocr_count,
            low_confidence_count,
            ocr_elapsed,
            time.perf_counter() - started,
        )
        return PdfExtractionResult(text=text, metadata=metadata, tables=table_chunks)
    finally:
        document.close()


_PDF_WORKER_SETTINGS = (
    'pdf_ocr_dpi', 'pdf_ocr_max_pixels', 'pdf_ocr_page_timeout_seconds',
    'pdf_ocr_max_concurrency', 'tesseract_lang', 'max_pdf_pages', 'pdf_scan_preprocessing',
)


def _pdf_worker(connection, file_path, reading_mode, configuration, checkpoint_directory=None):
    """Own every MuPDF object in a fresh process, including table-reader state."""
    try:
        if os.name == 'posix':
            # Keep Tesseract subprocesses in this job's process group so a
            # cancelled reading does not leave OCR running after its slot opens.
            os.setsid()
        for name in _PDF_WORKER_SETTINGS:
            setattr(settings, name, configuration[name])
        result = _extract_pdf_sync(file_path,
            lambda progress: connection.send(('progress', progress)), reading_mode=reading_mode,
            **({'checkpoint_directory': checkpoint_directory} if checkpoint_directory else {}))
        connection.send(('result', result))
    except Exception as exc:
        connection.send(('error', str(exc)))
    finally:
        connection.close()


def _receive_pdf_message(connection, worker):
    while not connection.poll(0.25):
        if not worker.is_alive():
            raise PdfOcrError('The PDF reader stopped before completing this file. Retry reading the PDF.')
    try:
        return connection.recv()
    except EOFError as exc:
        raise PdfOcrError('The PDF reader closed before completing this file. Retry reading the PDF.') from exc


def _close_pdf_worker(worker, completed):
    if not completed and worker.is_alive():
        try:
            if os.name == 'posix' and os.getpgid(worker.pid) == worker.pid:
                os.killpg(worker.pid, signal.SIGTERM)
            else:
                worker.terminate()
        except ProcessLookupError:
            pass
    worker.join(timeout=1)
    if worker.is_alive():
        try:
            if os.name == 'posix' and os.getpgid(worker.pid) == worker.pid:
                os.killpg(worker.pid, signal.SIGKILL)
            else:
                worker.kill()
        except ProcessLookupError:
            pass
        worker.join()


async def _extract_pdf_in_process(file_path, progress_callback=None, *, reading_mode='automatic'):
    # PyMuPDF explicitly does not support concurrent threads, even when each
    # thread opens a separate file. Spawn avoids inheriting its global state.
    # https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html
    context = multiprocessing.get_context('spawn')
    from app.services.ingestion_checkpoints import page_checkpoint_root
    checkpoint_directory = await asyncio.to_thread(page_checkpoint_root, file_path)
    incoming, outgoing = context.Pipe(duplex=False)
    worker = context.Process(target=_pdf_worker, args=(outgoing, file_path, reading_mode,
        {name: getattr(settings, name) for name in _PDF_WORKER_SETTINGS}, checkpoint_directory), daemon=True)
    reader = None
    completed = False
    try:
        worker.start()
        outgoing.close()
        while True:
            reader = asyncio.create_task(asyncio.to_thread(_receive_pdf_message, incoming, worker))
            kind, value = await asyncio.shield(reader)
            reader = None
            if kind == 'progress':
                if progress_callback is not None:
                    await progress_callback(value)
            elif kind == 'result':
                completed = True
                return value
            else:
                raise PdfOcrError(value)
    finally:
        # Keep the concurrency slot until the child actually exits, including
        # cancellation and failed progress updates. Drain any in-flight reader
        # before closing its pipe so no background thread outlives the job.
        if worker.pid is not None:
            await asyncio.to_thread(_close_pdf_worker, worker, completed)
        if reader is not None:
            await asyncio.gather(reader, return_exceptions=True)
        incoming.close()
        outgoing.close()
        worker.close()


async def extract_pdf(
    file_path: str,
    progress_callback: PdfProgressCallback | None = None,
    *,
    reading_mode: str = "automatic",
) -> PdfExtractionResult:
    semaphore = _get_pdf_extraction_semaphore()
    async with semaphore:
        return await _extract_pdf_in_process(file_path, progress_callback, reading_mode=reading_mode)
