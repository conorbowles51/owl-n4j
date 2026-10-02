"""Check every recognised money cell against the page image before it can count.

Why this exists
---------------
A scanned statement carries text that some recogniser produced from an image.
A misread digit that still forms a valid amount (``25.11`` read as ``28.11``)
parses, so nothing marks it unreadable and no reread is triggered. When two
such misreads cancel, every printed control still reconciles and arithmetic
cannot see the fault. An equation may detect a problem; it cannot establish
that a valid-looking value is the printed one.

What this does
--------------
For a page whose characters were recognised from an image (an embedded OCR
layer, a full-page OCR reading, or a page whose origin cannot be measured),
every table cell whose whole text is a money amount is reread from the original
page image at two resolutions and three ink thresholds. The crops are stacked
into one image per profile so a page costs six Tesseract calls, not six per
cell.

* **Confirmed**: at least four of the six crop readings, spanning both
  resolutions, give the same amount as the page reading. The cell is unchanged.
* **Contradicted**: at least four readings, spanning both resolutions, agree on
  a different amount. Two readings of the same printed figure disagree.
* **Unconfirmed**: anything else (crop readings disagree among themselves, are
  incomplete, or the time budget ran out).

A contradicted or unconfirmed cell is never resolved here. The crop reading is
not substituted: repeated agreement from one engine is supporting evidence, not
independent proof, and the embedded reading is itself a complete competing
value. The cell keeps the page's characters, but each character the two
readings dispute becomes ``?`` (or ``?`` is appended when the readings cannot be
aligned), so the statement reader cannot parse it and the period is held for a
person with the page reading, every crop reading and the crop location
retained in the page's refinement record. Pages with a digital text layer are
never touched and cost nothing.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
import os
import re
import time

import fitz
import pytesseract
from PIL import Image, ImageOps

METHOD = 'tesseract_money_cell_verification'
PROFILES = tuple((dpi, threshold) for dpi in (300, 450) for threshold in (150, 190, 220))
MIN_AGREEING = 4
WHITELIST = '0123456789.,-+$()'
MAX_STRIPS_PER_IMAGE = 40
# Recognised-image pages; digital text is exact by construction and skipped.
VERIFIED_ORIGINS = frozenset({'recognised_glyphs', 'unknown'})

_MONEY = re.compile(
    r'(?P<open>\()?\s*(?P<lead>[+\-−])?\s*\$?\s*(?P<sign2>[+\-−])?\s*'
    r'(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)\s*\.\s*\d{2})\s*(?P<trail>-)?\s*(?P<close>\))?')


def money_value(text):
    """``(negative, digits)`` for a complete money string, else ``None``.

    Grouping commas, spaces and a currency symbol do not change the amount;
    a sign does, wherever the statement prints it.
    """
    match = _MONEY.fullmatch((text or '').strip())
    if not match or bool(match['open']) != bool(match['close']):
        return None
    signs = [s for s in (match['lead'], match['sign2'], match['trail']) if s]
    if len(signs) > 1:
        return None
    negative = bool(match['open']) or (bool(signs) and signs[0] in '-−')
    return negative, re.sub(r'\D', '', match['number'])


def page_needs_verification(text_origin, extraction_method):
    return extraction_method == 'tesseract_ocr' or text_origin in VERIFIED_ORIGINS


def _cell_rect(cell, page):
    """The cell's measured rectangle in page points, or ``None``."""
    try:
        locator = cell.locator.to_json()
    except AttributeError:
        return None
    rect, size = locator.get('rect') or [], locator.get('page_size') or []
    if (locator.get('kind') != 'page_rectangle' or locator.get('page') != page.number + 1
            or len(rect) != 4 or len(size) != 2 or not all(type(v) is int for v in rect + size)
            or not 0 <= rect[0] < rect[2] <= size[0] or not 0 <= rect[1] < rect[3] <= size[1]
            or abs(size[0] - page.rect.width * 1000) > 2 or abs(size[1] - page.rect.height * 1000) > 2):
        return None
    # A money cell is one short printed line; anything larger is not a crop
    # this check can read as that one value.
    if rect[2] - rect[0] > size[0] * .4 or rect[3] - rect[1] > size[1] * .05:
        return None
    return rect


def _strip(page, rect, dpi, rotation):
    clip = (fitz.Rect([v / 1000 for v in rect]) + (-3, -1, 3, 1)) & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip,
        colorspace=fitz.csGRAY, alpha=False, annots=True)
    image = Image.frombytes('L', (pix.width, pix.height), pix.samples)
    if rotation:
        oriented = image.rotate(-rotation, expand=True, fillcolor=255)
        image.close()
        image = oriented
    return image


@contextmanager
def _single_threaded_tesseract():
    """Run these small reads with one OpenMP thread.

    Measured on the benchmark host under load (1-minute load 25 on 6 CPUs): a
    stacked strip read took 15-24 s with Tesseract's default OpenMP threads and
    about 1 s with ``OMP_THREAD_LIMIT=1``, the same text either way. pytesseract
    passes the process environment to its subprocess, so the limit is set only
    for the duration of these calls and then restored.
    """
    previous = os.environ.get('OMP_THREAD_LIMIT')
    os.environ['OMP_THREAD_LIMIT'] = '1'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('OMP_THREAD_LIMIT', None)
        else:
            os.environ['OMP_THREAD_LIMIT'] = previous


def stacked_readings(page, rects, *, rotation, deadline, language):
    with _single_threaded_tesseract():
        return _stacked_readings(page, rects, rotation=rotation, deadline=deadline, language=language)


def _stacked_readings(page, rects, *, rotation, deadline, language):
    """Read every rectangle under each profile; ``{profile index: [(text, confidence)]}``.

    Each crop is a separate horizontal strip with a wide white gap, so a
    recognised word belongs to exactly one strip by its vertical centre. A word
    centred in a gap belongs to none and is discarded rather than guessed.
    """
    results = {}
    for dpi in sorted({dpi for dpi, _ in PROFILES}):
        if deadline - time.monotonic() < 1:
            break
        greys = [_strip(page, rect, dpi, rotation) for rect in rects]
        try:
            for index, (profile_dpi, threshold) in enumerate(PROFILES):
                if profile_dpi != dpi:
                    continue
                readings = []
                for start in range(0, len(greys), MAX_STRIPS_PER_IMAGE):
                    remaining = deadline - time.monotonic()
                    if remaining < 1:
                        readings = None
                        break
                    readings.extend(_read_stack(greys[start:start + MAX_STRIPS_PER_IMAGE], dpi,
                        threshold, language, min(10, remaining)))
                if readings is None:
                    break
                results[index] = readings
        finally:
            for image in greys:
                image.close()
    return results


def _read_stack(images, dpi, threshold, language, timeout):
    gap = max(20, int(dpi / 72 * 8))
    pad = 30
    width = max(image.width for image in images) + 2 * pad
    height = sum(image.height for image in images) + gap * (len(images) + 1)
    spans = []
    with Image.new('L', (width, height), 255) as canvas:
        y = gap
        for image in images:
            with image.point(lambda value: 255 if value >= threshold else 0) as ink:
                canvas.paste(ink, (pad, y))
            spans.append((y, y + image.height))
            y += image.height + gap
        data = pytesseract.image_to_data(canvas, lang=language, output_type=pytesseract.Output.DICT,
            config=f'--oem 1 --psm 6 --dpi {dpi} -c tessedit_char_whitelist={WHITELIST}', timeout=timeout)
    words = [[] for _ in images]
    for i, raw in enumerate(data.get('text') or []):
        word = str(raw or '').strip()
        if not word:
            continue
        centre = data['top'][i] + data['height'][i] / 2
        owner = [k for k, (top, bottom) in enumerate(spans) if top - gap / 2 < centre < bottom + gap / 2]
        if len(owner) == 1:
            try:
                confidence = float(data['conf'][i])
            except (TypeError, ValueError, IndexError, KeyError):
                confidence = -1.0
            words[owner[0]].append((data['left'][i], word, confidence))
    readings = []
    for found in words:
        found.sort()
        confidences = [c for _, _, c in found if c >= 0]
        readings.append((' '.join(w for _, w, _ in found),
            round(min(confidences), 1) if confidences else None))
    return readings


def _dispute_marked(original, reading):
    """The page's characters with each disputed one replaced by ``?``.

    Positions align only when both strings have the same non-space length;
    otherwise the dispute cannot be localised and ``?`` is appended. Either
    way the result is not a parseable amount, so it cannot be admitted.
    """
    if reading is not None:
        positions = [i for i, character in enumerate(original) if not character.isspace()]
        compact = re.sub(r'\s+', '', reading)
        if len(positions) == len(compact):
            marked = list(original)
            for index, character in zip(positions, compact):
                if original[index] != character:
                    marked[index] = '?'
            if '?' in marked:
                return ''.join(marked)
    return original.rstrip() + '?'


def classify(original, observations):
    """``(status, contradicting reading)`` for one cell's crop observations."""
    expected = money_value(original)
    agreeing = [o for o in observations if money_value(o['text']) == expected]
    if len(agreeing) >= MIN_AGREEING and {o['dpi'] for o in agreeing} == {dpi for dpi, _ in PROFILES}:
        return 'confirmed', None
    others = Counter(money_value(o['text']) for o in observations
                     if money_value(o['text']) not in (None, expected))
    for value, count in others.most_common(1):
        supporters = [o for o in observations if money_value(o['text']) == value]
        if count >= MIN_AGREEING and {o['dpi'] for o in supporters} == {dpi for dpi, _ in PROFILES}:
            return 'contradicted', supporters[0]['text']
    return 'unconfirmed', None


def verify_money_cells(page, tables, *, rotation=0, deadline, language, chunk=None, measure=True):
    """Return ``(tables, records)`` with every unconfirmed money cell marked.

    ``chunk`` rebuilds a table's text from its grid (default: the financial
    reader's own chunk format). Tables without measured cells are left as they
    are: they carry no money cell to reread.
    """
    if chunk is None:
        from services.financial.pdf_tables import _chunk as chunk
    started = time.monotonic()
    # Cell rectangles are not mapped through a PDF page rotation here, and a
    # caller whose verification failed passes ``measure=False``. Either way
    # the money cells stay unverified and are held rather than admitted.
    rects_available = measure and not page.rotation
    targets = []
    for table_index, table in enumerate(tables):
        geometry = getattr(table, 'geometry', None)
        for cell in getattr(geometry, 'cells', None) or ():
            if money_value(cell.text) is not None:
                targets.append((table_index, cell, _cell_rect(cell, page) if rects_available else None))
    if not targets:
        return tables, []
    measured = [t for t in targets if t[2] is not None]
    readings = {}
    error = None
    if measured:
        try:
            readings = stacked_readings(page, [rect for _, _, rect in measured], rotation=rotation,
                deadline=deadline, language=language)
        except (RuntimeError, pytesseract.TesseractError) as exc:
            error = str(exc)[:200]
            readings = {}
    observations_by_cell = {}
    for position, (table_index, cell, _) in enumerate(measured):
        observations_by_cell[(table_index, cell.row, cell.column)] = [
            dict(dpi=PROFILES[i][0], threshold=PROFILES[i][1], text=readings[i][position][0],
                 confidence=readings[i][position][1])
            for i in sorted(readings) if position < len(readings[i])]
    replacements, cells_record = {}, []
    for table_index, cell, rect in targets:
        key = (table_index, cell.row, cell.column)
        observations = observations_by_cell.get(key, [])
        status, contradiction = classify(cell.text, observations) if rect else ('unconfirmed', None)
        entry = dict(table_index=table_index, row_index=cell.row, column_index=cell.column,
            original_text=cell.text, status=status, rect=rect, observations=observations)
        if status != 'confirmed':
            entry['marked_text'] = replacements[key] = _dispute_marked(cell.text, contradiction)
            entry['reason'] = ('crop_readings_contradict_page_reading' if status == 'contradicted'
                else 'cell_not_measured' if rect is None else 'crop_readings_do_not_confirm_page_reading')
        cells_record.append(entry)
    record = dict(method=METHOD, page=page.number + 1,
        decision='held' if replacements else 'all_confirmed',
        confirmed=sum(c['status'] == 'confirmed' for c in cells_record),
        contradicted=sum(c['status'] == 'contradicted' for c in cells_record),
        unconfirmed=sum(c['status'] == 'unconfirmed' for c in cells_record),
        profiles=[dict(dpi=d, threshold=t) for d, t in PROFILES], segmentation_mode=6,
        character_set=WHITELIST, rotation=rotation, minimum_agreeing=MIN_AGREEING,
        seconds=round(time.monotonic() - started, 3), cells=cells_record)
    if error:
        record['error'] = error
    if not replacements:
        return tables, [record]
    refined = []
    for table_index, table in enumerate(tables):
        geometry = getattr(table, 'geometry', None)
        if geometry is None or not any(k[0] == table_index for k in replacements):
            refined.append(table)
            continue
        cells = tuple(replace(c, text=replacements.get((table_index, c.row, c.column), c.text))
                      for c in geometry.cells)
        text = table.chunk
        if chunk is not None:
            rows = {}
            for c in cells:
                rows.setdefault(c.row, {})[c.column] = c.text
            grid = [[row.get(column, '') for column in range(max(row) + 1)] for _, row in sorted(rows.items())]
            text = chunk(grid, page.number + 1) or table.chunk
        refined.append(replace(table, geometry=replace(geometry, cells=cells), chunk=text))
    return refined, [record]
