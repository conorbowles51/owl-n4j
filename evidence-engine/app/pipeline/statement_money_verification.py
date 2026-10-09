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

One sign exception is made inside the check. Small crops drop, read or double
a printed minus from one profile to the next. A minus amount whose figures at
least four crop readings at both resolutions agree on, once their minus marks
are set aside (``_minus_figures_agreed``), is confirmed when the page image
shows exactly one minus-shaped mark beside the figures on the side the page
reading prints it (``measured_minus``). The crops confirm the figures and the
measured mark confirms the sign; a page reading of a minus the print does not
show has no such mark and stays held.

One exception is made afterwards, by ``repair_pinned_cells``: on a generic
running-balance statement, a contradicted cell that every crop profile reads
the same way is accepted when a printed control equation fixes it from cells
the page and the crops both read identically. That is a second, independent
line of evidence (the agreed printed balances) that the page reading
contradicts and the crop reading satisfies. Compensating misreads that only
fix a sum of disputed cells stay held.

On an Andrews page, ``repair_pinned_readings`` applies the same test to every
reading of a held cell that a recogniser produced from the print: the page
reading (when crops at both resolutions also give it), the crop reading, or,
for a cell whose sign glyph no reader could name, its agreed digits with
either sign. A reading is accepted only when a printed control equation whose
other cells were confirmed fixes it and no other candidate. Majority does not
decide: on a 100 dpi corpus scan four of six crops dropped a minus and misread
a digit, while the page reading was the printed value.

A cell whose page reading is an unsigned amount behind one glyph that is not a
sign (``“61.27``) is reread like any money cell, but is never confirmed.
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


# Glyphs a recogniser has been measured to put where a statement prints a
# minus sign (corpus: ``“61.27`` for ``-61.27`` on 150 dpi scans; real
# text-layer scans: ``·13.01`` for ``-13.01``).
_SIGN_LOOKALIKES = '“”„"‘’\'`´~—–‒―‐‑_=·•'


def sign_garbled_money(text):
    """The digits of an unsigned amount preceded by one glyph that is not a sign, else ``None``.

    Such a cell is not a readable amount: its sign position holds a mark the
    recogniser could not read as a sign. It is still a money cell, so it is
    reread like one, but its page reading can never be confirmed.
    """
    stripped = (text or '').strip()
    if len(stripped) < 2 or stripped[0] not in _SIGN_LOOKALIKES:
        return None
    rest = stripped[1:].strip()
    value = money_value(rest)
    if value is None or value[0] or rest[:1] in '+-−(':
        return None
    return value[1]


_CROP_MONEY = re.compile(
    r'(?P<open>\()?(?P<lead>[+\-−])?\$?(?P<sign2>[+\-−])?'
    r'(?P<whole>\d{1,3}(?:,\d{3})+|\d+)[.,](?P<cents>\d{2})[.,]?(?P<trail>-)?(?P<close>\))?')


def crop_money_value(text):
    """``(negative, digits)`` for an image reading of one money amount, else ``None``.

    As ``money_value``, except that the decimal point may have been read as a
    comma and one stray point or comma after the cents is ignored. Measured on
    real text-layer scans: Tesseract reads the small printed point of these
    cells as ``,`` at most crop profiles (``-13,01`` for ``-13.01``) and a
    speck after the cents as ``.`` or ``,``. A two-digit decimal part has one
    reading whichever mark separates it, because a grouping comma is always
    followed by three digits; ``1,234`` and ``12,345`` are therefore not
    amounts here. Digits and sign are never changed. Spaces are ignored.
    """
    match = _CROP_MONEY.fullmatch(re.sub(r'\s+', '', text or ''))
    if not match or bool(match['open']) != bool(match['close']):
        return None
    signs = [s for s in (match['lead'], match['sign2'], match['trail']) if s]
    if len(signs) > 1:
        return None
    negative = bool(match['open']) or (bool(signs) and signs[0] in '-−')
    return negative, re.sub(r'\D', '', match['whole']) + match['cents']


def separator_garbled_money(text):
    """``(negative, digits)`` for a page reading whose only fault is its decimal mark, else ``None``.

    ``-13,01`` or ``56.78,``: the digits and sign read completely, the point
    as a comma or with a stray mark after the cents. Such a cell is not a
    readable amount and is never confirmed, but it is reread like one.
    """
    if money_value(text) is not None or sign_garbled_money(text) is not None:
        return None
    return crop_money_value(text)


def dollar_garbled_money(text):
    """``(negative, digits)`` for a page reading whose only fault is an ``S`` where the dollar sign prints, else ``None``.

    ``S0.00`` or ``S1,234.56-``: measured on a real card statement's
    recognised text layer, which reads the summary's dollar sign as ``S``.
    Such a cell is not a readable amount; it is reread like one and confirmed
    only when the crops read the dollar sign itself (``_normalised_reading``),
    so an ``S`` that stands for a digit 5 is never taken for a dollar sign.
    """
    match = re.fullmatch(r'([+\-−]?\s*)S(\s*\d[\d,]*\.\d{2}\s*-?)', (text or '').strip())
    return money_value(match[1] + '$' + match[2]) if match else None


# Letters an embedded OCR layer was measured to put for printed digits in
# Andrews money cells (``-B7.65`` for ``-87.65``, ``o.oo``, ``-S6.OD``,
# ``l.234.56``), by the digit each stands for.
_DIGIT_LOOKALIKES = {'O': '0', 'o': '0', 'D': '0', 'Q': '0', 'B': '8', 'S': '5', 'l': '1', 'I': '1', 'i': '1',
                     '|': '1', 'Z': '2'}


def lookalike_money(text, kind='single'):
    """The amount(s) a page reading states once letters measured to stand for digits are read as those digits.

    ``None`` unless the text holds at least one such letter and then reads as
    an amount (``kind='pair'``: two). The result is an interpretation of the
    page's glyphs, never accepted on its own: only the agreed controls may pin it.
    """
    if not any(ch in _DIGIT_LOOKALIKES for ch in text or ''):
        return None
    mapped = ''.join(_DIGIT_LOOKALIKES.get(ch, ch) for ch in text)
    return crop_money_pair(mapped) if kind == 'pair' else crop_money_value(mapped)


def _split_pair(text, parse):
    """The two amounts of a cell printing an amount and a running balance side by side, else ``None``.

    The text must split at exactly one run of spaces into two parts that
    ``parse`` reads as amounts; a text that splits in two ways is not read.
    """
    stripped = (text or '').strip()
    found = []
    for gap in re.finditer(r'\s+', stripped):
        left, right = parse(stripped[:gap.start()]), parse(stripped[gap.end():])
        if left is not None and right is not None:
            found.append((left, right))
    return found[0] if len(found) == 1 else None


def money_pair(text):
    """The two amounts of a joined amount and balance cell, each a complete page amount, else ``None``."""
    return _split_pair(text, money_value)


def crop_money_pair(text):
    """The two amounts of an image reading of a joined amount and balance cell, else ``None``.

    The crop of such a cell is usually read as one word (``-56.781234.56``):
    each amount ends two digits after its decimal mark, so the reading is
    split wherever both sides read as amounts, and accepted only when exactly
    one split gives two amounts.
    """
    compact = re.sub(r'\s+', '', text or '')
    found = {(left, right) for i in range(1, len(compact))
             if re.search(r'[.,]\d{2}$', compact[:i])
             and (left := crop_money_value(compact[:i])) is not None
             and (right := crop_money_value(compact[i:])) is not None}
    return found.pop() if len(found) == 1 else None


def money_text(value):
    """Canonical text of one amount or of a joined pair: ``-13.01`` or ``-13.01 1234.56``."""
    if value and isinstance(value[0], tuple):
        return ' '.join(money_text(part) for part in value)
    negative, digits = value
    return ('-' if negative else '') + (digits[:-2].lstrip('0') or '0') + '.' + digits[-2:]


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


def stacked_readings(page, rects, *, rotation, deadline, language, whitelist=WHITELIST):
    with _single_threaded_tesseract():
        return _stacked_readings(page, rects, rotation=rotation, deadline=deadline, language=language,
            whitelist=whitelist)


def _stacked_readings(page, rects, *, rotation, deadline, language, whitelist=WHITELIST):
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
                        threshold, language, min(10, remaining), whitelist))
                if readings is None:
                    break
                results[index] = readings
        finally:
            for image in greys:
                image.close()
    return results


def _read_stack(images, dpi, threshold, language, timeout, whitelist=WHITELIST):
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
            config=f'--oem 1 --psm 6 --dpi {dpi} -c tessedit_char_whitelist={whitelist}', timeout=timeout)
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


SIGN_DPI = 450
SIGN_INK = 160


def _ink_boxes(image, threshold=SIGN_INK):
    """``[(x0, y0, x1, y1)]``: the bounding box of every 8-connected ink component of a small grey image."""
    width, height = image.size
    pixels = image.load()
    seen, boxes = set(), []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] >= threshold or (x, y) in seen:
                continue
            seen.add((x, y))
            stack, x0, y0, x1, y1 = [(x, y)], x, y, x, y
            while stack:
                a, b = stack.pop()
                x0, y0, x1, y1 = min(x0, a), min(y0, b), max(x1, a), max(y1, b)
                for na in (a - 1, a, a + 1):
                    for nb in (b - 1, b, b + 1):
                        if (0 <= na < width and 0 <= nb < height and (na, nb) not in seen
                                and pixels[na, nb] < threshold):
                            seen.add((na, nb))
                            stack.append((na, nb))
            boxes.append((x0, y0, x1 + 1, y1 + 1))
    return boxes


def measured_minus(page, rect, rotation, side):
    """The one minus-shaped mark printed on ``side`` (``lead`` or ``trail``) of a money cell's figures, else ``None``.

    The cell is rendered as for the crop readings, at 450 dpi, and split into
    ink components. The figures are the components at least 60% as tall as the
    tallest one; their median height and width measure the print. On the
    named side of the figures, within their line, there must be exactly one
    other component that is not a speck, and it must have the shape and place of a printed minus:
    flat (at most a quarter of the figure height, at least twice as wide as
    tall), 30% to 120% of a figure wide, centred between 40% and 80% down the
    figures, and at most one figure width from them. A rule, an underscore, a
    bracket or a letter fails one of these. Nothing is read: the mark is
    measured, and it is used only to confirm a minus the page reading prints
    whose figures the crop readings agree on (``_minus_figures_agreed``).
    """
    image = _strip(page, rect, SIGN_DPI, rotation)
    try:
        boxes = _ink_boxes(image)
    finally:
        image.close()
    if not boxes:
        return None
    tallest = max(y1 - y0 for _, y0, _, y1 in boxes)
    figures = sorted(b for b in boxes if (b[3] - b[1]) >= .6 * tallest)
    if not figures or tallest < 8:
        return None
    heights = sorted(b[3] - b[1] for b in figures)
    widths = sorted(b[2] - b[0] for b in figures)
    height, width = heights[len(heights) // 2], widths[len(widths) // 2]
    top = sorted(b[1] for b in figures)[len(figures) // 2]
    speck = max(2, height // 10)
    if side == 'lead':
        others = [b for b in boxes if b not in figures and b[2] <= figures[0][0]]
    else:
        others = [b for b in boxes if b not in figures and b[0] >= figures[-1][2]]
    # Ink outside the figures' line (the edge of the line above or below,
    # which the crop margin can include) is not beside the figures.
    others = [b for b in others if (b[2] - b[0] > speck or b[3] - b[1] > speck)
              and b[3] > top and b[1] < top + height]
    if len(others) != 1:
        return None
    x0, y0, x1, y1 = others[0]
    mark_width, mark_height = x1 - x0, y1 - y0
    centre = ((y0 + y1) / 2 - top) / height
    gap = figures[0][0] - x1 if side == 'lead' else x0 - figures[-1][2]
    if (mark_height > height / 4 or mark_width < 2 * mark_height or not .3 * width <= mark_width <= 1.2 * width
            or not .4 <= centre <= .8 or gap > width):
        return None
    return dict(side=side, dpi=SIGN_DPI, box=[x0, y0, x1, y1], figure_height=height, figure_width=width)


def _minus_figures_agreed(original, observations):
    """``lead`` or ``trail`` when the crops agree on the figures of a minus amount but not on its sign, else ``None``.

    The page reading must be one complete negative amount printed with a
    minus before or after its figures (not in parentheses). At least four crop
    readings, at both resolutions, must state exactly its figures once every
    minus and parenthesis they show is set aside (whatever decimal and
    grouping marks they show, ``_states_page_figures``), and no crop reading may show
    a plus. Measured on a real card statement's recognised text layer: the
    crops of one printed minus amount gave it as ``12.34``, ``-12.34`` and ``-12.34-``
    at different profiles; small crops drop or double a printed minus. The
    crops then confirm every figure and do not settle the sign. Only the
    measured mark (``measured_minus``) can confirm it.
    """
    page = money_value(original)
    stripped = (original or '').strip()
    if page is None or not page[0] or stripped.startswith('(') or stripped.endswith(')'):
        return None
    side = 'lead' if stripped[0] in '-−' else 'trail' if stripped[-1] == '-' else None
    if side is None or any('+' in o['text'] for o in observations):
        return None
    agreeing = [o for o in observations if _states_page_figures(re.sub(r'[-−()]', '', o['text']), (False, page[1]))
                or ((value := crop_money_value(re.sub(r'[-−()]', '', o['text']))) is not None and value[1] == page[1])]
    if len(agreeing) < MIN_AGREEING or {o['dpi'] for o in agreeing} != {dpi for dpi, _ in PROFILES}:
        return None
    return side


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


def _spaced_money_value(text):
    """``money_value`` of a page reading once the spaces OCR put between its digits are removed."""
    return money_value(re.sub(r'\s+', '', text or ''))


def _readers(kind):
    """``(page reading parser, image reading parser)`` for a cell of this kind.

    ``spaced``: an Andrews money cell whose page reading is a complete amount
    once spaces are removed (``123. 4 5``), which the Andrews reader parses
    as such in a measured money cell.
    """
    if kind == 'pair':
        return money_pair, crop_money_pair
    return (_spaced_money_value if kind == 'spaced' else money_value), crop_money_value


_POINTLESS = re.compile(r'(?P<lead>[+\-−]?)\$?(?P<sign2>[+\-−]?)(?P<figures>\d{3,})(?P<trail>-?)')


def _states_page_figures(text, expected):
    """Whether a crop reading states exactly the page reading's figures and sign, whatever marks it shows between them.

    Measured on a real card scan: at the lightest ink threshold the crops lose
    the small printed point (``2345`` for ``23.45``) and read a grouping comma
    as a point (``$1.234.56`` for ``$1,234.56``) while every figure is read.
    Such a reading agrees with a page reading that is a complete amount: the
    page fixes where the marks are (every amount here prints two decimals).
    It is never a value of its own: it can only confirm the page reading,
    never contradict or replace it.
    """
    match = _POINTLESS.fullmatch(re.sub(r'[\s.,]+', '', text or ''))
    if not match or expected is None:
        return False
    signs = [s for s in (match['lead'], match['sign2'], match['trail']) if s]
    return len(signs) <= 1 and (bool(signs) and signs[0] in '-−', match['figures']) == expected


def classify(original, observations, kind='single'):
    """``(status, contradicting reading)`` for one cell's crop observations.

    The page reading must be a complete amount (for a ``pair`` cell, two);
    crop readings are compared by the amount they state, whatever mark they
    show for the decimal point (``crop_money_value``); a single amount's crop
    reading agrees whatever decimal and grouping marks it shows (or misses)
    when it states exactly the page reading's figures and sign
    (``_states_page_figures``).
    """
    page, image = _readers(kind)
    expected = page(original)
    # A page reading that is not an amount (an unreadable sign glyph) is never confirmed.
    agreeing = [o for o in observations if expected is not None and (image(o['text']) == expected
                or (kind == 'single' and _states_page_figures(o['text'], expected)))]
    if len(agreeing) >= MIN_AGREEING and {o['dpi'] for o in agreeing} == {dpi for dpi, _ in PROFILES}:
        return 'confirmed', None
    others = Counter(image(o['text']) for o in observations if image(o['text']) not in (None, expected))
    for value, count in others.most_common(1):
        supporters = [o for o in observations if image(o['text']) == value]
        if count >= MIN_AGREEING and {o['dpi'] for o in supporters} == {dpi for dpi, _ in PROFILES}:
            return 'contradicted', supporters[0]['text']
    return 'unconfirmed', None


PAIR_PARTS = ('amount', 'balance')


def _page_pair(original):
    """The two amounts a joined cell's page reading states, its decimal marks read as points, else ``None``."""
    return money_pair(original) or crop_money_pair(original)


def confirmed_parts(original, observations):
    """``['amount' and/or 'balance']``: the parts of a joined cell the crops confirm on their own.

    A joined cell states two printed amounts. Each part counts as confirmed
    when at least four crop readings at both resolutions state that part as
    the page reading does, exactly as a whole cell is confirmed; the other
    part may still be disputed. Letters read for digits are never confirmed.
    """
    page = _page_pair(original)
    if page is None:
        return []
    parsed = [(o, crop_money_pair(o['text'])) for o in observations]
    found = []
    for index, name in enumerate(PAIR_PARTS):
        agreeing = [o for o, value in parsed if value is not None and value[index] == page[index]]
        if len(agreeing) >= MIN_AGREEING and _both_resolutions(agreeing):
            found.append(name)
    return found


def _normalised_reading(original, observations, kind):
    """The canonical text of a page reading whose only fault is its decimal mark, when the crops confirm it.

    ``-13,01`` with at least four crop readings at both resolutions stating
    -13.01 (whatever mark they read for the point) is the same printed amount
    a confirmed ``-13.01`` would be: the page and the image agree on every
    digit and the sign. The cell then takes ``-13.01`` (for a joined amount
    and balance cell, both amounts) and the record keeps the page reading.
    Letters standing for digits (``-B7.65``) are not confirmed here: the page
    did not state those digits, so only the agreed controls may pin them.

    The same holds for a page reading whose only fault is an ``S`` where the
    dollar sign prints (``S0.00``): the page states every digit, and the
    crops must read the dollar sign itself as well as the amount. The cell
    then takes the page's characters with ``$`` for that ``S``.
    """
    dollar = None
    if kind == 'pair':
        value = crop_money_pair(original) if money_pair(original) is None else None
    elif kind == 'single':
        value = separator_garbled_money(original)
        if value is None:
            value = dollar = dollar_garbled_money(original)
    else:
        value = None
    if value is None:
        return None
    _, image = _readers(kind)
    agreeing = [o for o in observations if image(o['text']) == value and (dollar is None or '$' in o['text'])]
    if len(agreeing) < MIN_AGREEING or not _both_resolutions(agreeing):
        return None
    return original.strip().replace('S', '$', 1) if dollar is not None else money_text(value)


def _andrews_page(tables):
    try:
        from services.financial.statement_reading_quality import andrews_page_reading
        return andrews_page_reading([table.to_json() for table in tables])
    except Exception:
        return False


def _money_column(cell, page):
    rect = _cell_rect(cell, page)
    return rect is not None and rect[0] >= page.rect.width * 1000 * .46


def _target_kind(cell, page, andrews):
    """``single``, ``pair`` or ``None``: whether and how a table cell is reread as money.

    Every cell whose text is one amount (or one amount behind an unreadable
    sign glyph) is reread. On an Andrews page, whose payment rows print an
    amount and a running balance in the right half of the page, two more
    kinds are: a money cell whose only fault is its decimal mark, and a cell
    in which the reading joined the amount and the balance (``pair``). The
    Andrews reader parses both of the joined amounts, so they are checked
    against the image like any other money it reads.
    """
    if (money_value(cell.text) is not None or sign_garbled_money(cell.text) is not None
            or dollar_garbled_money(cell.text) is not None):
        return 'single'
    if not andrews or not _money_column(cell, page):
        return None
    if _spaced_money_value(cell.text) is not None:
        return 'spaced'
    if separator_garbled_money(cell.text) is not None:
        return 'single'
    if crop_money_pair(cell.text) is not None:
        return 'pair'
    if lookalike_money(cell.text) is not None:
        return 'single'
    if lookalike_money(cell.text, 'pair') is not None:
        return 'pair'
    return None


_ROW_DATE = re.compile(r'\d{1,2}/\d{1,2}(?:/\d{2,4})?')


def _figures_cell(cell, row_cells, page):
    """Whether a cell is a row's amount whose page reading lost its decimal point (``6789`` for ``67.89``).

    Only figures (three or more digits, no mark), in the right-hand money
    columns, as the last cell of a row that starts with a printed date. Such a
    cell is reread like money but never held for it: unless the crops read a
    complete amount with exactly its figures (``verify_money_cells``), it keeps
    its text, unreadable as money, exactly as before.
    """
    if not re.fullmatch(r'\d{3,9}', (cell.text or '').strip()) or not _money_column(cell, page):
        return False
    ordered = sorted(row_cells, key=lambda c: c.column)
    return ordered[-1] is cell and len(ordered) >= 3 and bool(_ROW_DATE.fullmatch((ordered[0].text or '').strip()))


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
    andrews = _andrews_page(tables)
    targets = []
    for table_index, table in enumerate(tables):
        geometry = getattr(table, 'geometry', None)
        rows = {}
        for cell in getattr(geometry, 'cells', None) or ():
            rows.setdefault(cell.row, []).append(cell)
        for cell in getattr(geometry, 'cells', None) or ():
            kind = _target_kind(cell, page, andrews) or ('figures' if _figures_cell(cell, rows[cell.row], page) else None)
            if kind:
                targets.append((table_index, cell, _cell_rect(cell, page) if rects_available else None, kind))
    if not targets:
        return tables, []
    measured = [t for t in targets if t[2] is not None]
    readings = {}
    error = None
    if measured:
        try:
            readings = stacked_readings(page, [rect for _, _, rect, _ in measured], rotation=rotation,
                deadline=deadline, language=language)
        except (RuntimeError, pytesseract.TesseractError) as exc:
            error = str(exc)[:200]
            readings = {}
    observations_by_cell = {}
    for position, (table_index, cell, _, _) in enumerate(measured):
        observations_by_cell[(table_index, cell.row, cell.column)] = [
            dict(dpi=PROFILES[i][0], threshold=PROFILES[i][1], text=readings[i][position][0],
                 confidence=readings[i][position][1])
            for i in sorted(readings) if position < len(readings[i])]
    replacements, normalisations, cells_record = {}, {}, []
    for table_index, cell, rect, kind in targets:
        key = (table_index, cell.row, cell.column)
        observations = observations_by_cell.get(key, [])
        if kind == 'figures':
            # Figures whose decimal point the page reading lost: confirmed in
            # canonical form only when at least four crop readings at both
            # resolutions read a complete unsigned amount with exactly these
            # figures (the crops state where the point is). Otherwise the
            # cell is left as it was, not a money reading, and not recorded.
            figures = (False, cell.text.strip())
            agreeing = [o for o in observations if crop_money_value(o['text']) == figures]
            if rect and len(agreeing) >= MIN_AGREEING and _both_resolutions(agreeing):
                normalisations[key] = money_text(figures)
                cells_record.append(dict(table_index=table_index, row_index=cell.row, column_index=cell.column,
                    original_text=cell.text, status='confirmed', rect=rect, observations=observations,
                    kind='figures', page_decimal_point_missing=True, normalised_text=normalisations[key],
                    reason='page_figures_confirmed_by_crops_with_their_point'))
            continue
        status, contradiction = classify(cell.text, observations, kind) if rect else ('unconfirmed', None)
        entry = dict(table_index=table_index, row_index=cell.row, column_index=cell.column,
            original_text=cell.text, status=status, rect=rect, observations=observations)
        if kind in ('pair', 'spaced'):
            entry['kind'] = kind
            if kind == 'pair' and money_pair(cell.text) is None:
                entry['page_decimal_mark_unreadable'] = True
        elif separator_garbled_money(cell.text) is not None:
            entry['page_decimal_mark_unreadable'] = True
        elif dollar_garbled_money(cell.text) is not None:
            entry['page_dollar_sign_unreadable'] = True
        elif lookalike_money(cell.text) is not None:
            entry['page_digit_lookalikes'] = True
        elif money_value(cell.text) is None:
            entry['page_sign_unreadable'] = True
        if status != 'confirmed' and rect and kind == 'single' and (side := _minus_figures_agreed(cell.text, observations)):
            mark = measured_minus(page, rect, rotation, side)
            if mark is not None:
                status = entry['status'] = 'confirmed'
                entry.update(sign_mark=mark, reason='crop_figures_confirmed_printed_minus_measured')
        normalised = _normalised_reading(cell.text, observations, kind) if rect and status != 'confirmed' else None
        if normalised is not None:
            status = entry['status'] = 'confirmed'
            entry.update(normalised_text=normalised, reason='page_dollar_sign_confirmed_by_crops'
                         if entry.get('page_dollar_sign_unreadable') else 'page_decimal_mark_confirmed_by_crops')
            normalisations[key] = normalised
        if status != 'confirmed' and kind == 'pair' and rect:
            parts = confirmed_parts(cell.text, observations)
            if parts:
                entry['confirmed_parts'] = parts
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
    if not replacements and not normalisations:
        return tables, [record]
    return _with_cells(page, tables, {**normalisations, **replacements}, chunk), [record]


def _with_cells(page, tables, replacements, chunk):
    """``tables`` with the cell texts in ``replacements`` substituted; every cell keeps its locator."""
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
    return refined


PINNED_METHOD = 'statement_money_pinned_repair'


def _unanimously_contradicted(record):
    """``(crop text by cell, record cell by cell)`` when every held cell is a unanimous contradiction.

    The page must be held by this check alone, without error, and every cell
    it did not confirm must be contradicted by all six crop readings giving
    one identical, parseable amount. Otherwise ``None``.
    """
    if not record or record.get('method') != METHOD or record.get('decision') != 'held' or record.get('error'):
        return None
    disputed, by_key = {}, {}
    for cell in record['cells']:
        if cell['status'] == 'confirmed':
            continue
        texts = {o['text'] for o in cell['observations']}
        if (cell['status'] != 'contradicted' or len(cell['observations']) != len(PROFILES)
                or len(texts) != 1 or money_value(next(iter(texts))) is None):
            return None
        key = (cell['table_index'], cell['row_index'], cell['column_index'])
        disputed[key], by_key[key] = texts.pop(), cell
    return (disputed, by_key) if disputed else None


def repair_pinned_cells(page, tables, record, *, chunk=None):
    """Accept crop readings that the statement's own agreed controls fix.

    Only a page held solely by contradicted cells, each read identically by
    every crop profile at both resolutions, is considered. The statement
    reader then decides whether each such value is pinned by a printed control
    whose other cells the page and the crops read the same way (see
    ``pinned_running_balance_values``). It is all or nothing: one cell that is
    not pinned leaves the whole page held. Each accepted cell is recorded with
    the page reading, the held text, every crop reading and the cells that pin
    it, so the original reading stays visible beside the repair.
    """
    if chunk is None:
        from services.financial.pdf_tables import _chunk as chunk
    found = _unanimously_contradicted(record)
    if not found:
        return tables, []
    disputed, by_key = found
    from services.financial.statement_reading_quality import pinned_running_balance_values
    accepted = pinned_running_balance_values([table.to_json() for table in tables], disputed)
    if not accepted or accepted.keys() != disputed.keys():
        return tables, []
    repaired = _with_cells(page, tables, {key: value['text'] for key, value in accepted.items()}, chunk)
    return repaired, [dict(method=PINNED_METHOD, page=page.number + 1, decision='repaired',
        cells=[dict(table_index=key[0], row_index=key[1], column_index=key[2],
                    page_reading=by_key[key]['original_text'], held_text=by_key[key]['marked_text'],
                    text=value['text'], pinned_by=value['pinned_by'], observations=by_key[key]['observations'],
                    reason='crop_reading_pinned_by_agreed_controls')
               for key, value in sorted(accepted.items())])]



PINNED_READING_METHOD = 'statement_money_pinned_reading'


def _both_resolutions(observations):
    return {o['dpi'] for o in observations} == {dpi for dpi, _ in PROFILES}


def _printed_readings(cell):
    """``[(text, source)]``: the readings of one held cell that came from the print.

    Crop readings are compared by the amount they state (``crop_money_value``;
    for a joined amount and balance cell, both amounts).

    * ``page_reading``: the page's own amount, when at least one crop reading
      gives it (at either resolution: on real scans the 300 dpi crops read a
      printed minus as ``+`` while the 450 dpi crops and the page agree). The
      page reading comes from a recogniser independent of these crops, and it
      is only ever accepted when two confirmed printed balances fix exactly
      that amount;
    * ``page_reading_normalised``: the same for a page reading whose only fault
      is its decimal mark (``-13,01``), offered in its canonical form;
    * ``crop_reading``: the amount at least four crop readings at both
      resolutions agree on, when it differs from the page reading (the crop
      text itself when those readings are character for character the same
      complete amount, else its canonical form). If the page reading is an
      unreadable sign glyph followed by digits, the crops must give exactly
      those digits;
    * ``crop_digits_signed_by_controls``: for such a cell whose crops read the
      agreed digits without any sign, the same digits with a minus. The page
      shows a mark in the sign position that no reader could name, so both
      signs stay candidates and only the agreed controls may choose.

    Every observation profile must be present (no time-out), or nothing is offered.
    """
    observations = cell.get('observations') or []
    if len(observations) != len(PROFILES) or not cell.get('rect'):
        return []
    pair = cell.get('kind') == 'pair'
    page_parse, image = _readers(cell.get('kind') or 'single')
    original = cell['original_text']
    found = []
    page_value = page_parse(original)
    normalised = dollar = None
    if page_value is None:
        normalised = crop_money_pair(original) if pair else separator_garbled_money(original)
        if normalised is None and not pair:
            # An S read for the dollar sign keeps the page's characters with
            # the sign, as the card summaries print it (never S as a 5).
            normalised = dollar = dollar_garbled_money(original)
        if normalised is None:
            normalised = lookalike_money(original, 'pair' if pair else 'single')
    for value, source in ((page_value, 'page_reading'), (normalised, 'page_reading_normalised')):
        if value is not None and any(image(o['text']) == value for o in observations):
            found.append((original.strip() if source == 'page_reading'
                          else original.strip().replace('S', '$', 1) if dollar is not None else money_text(value), source))
    known = page_value if page_value is not None else normalised
    values = Counter(image(o['text']) for o in observations if image(o['text']) not in (None, known))
    for value, count in values.most_common(1):
        supporters = [o for o in observations if image(o['text']) == value]
        if count < MIN_AGREEING or not _both_resolutions(supporters):
            break
        texts = {_compact(o['text']) for o in supporters}
        exact = page_parse(supporters[0]['text'].strip())
        text = supporters[0]['text'].strip() if len(texts) == 1 and exact == value else money_text(value)
        if page_value is None and normalised is None:
            if sign_garbled_money(original) != value[1]:
                break
            found.append((text, 'crop_reading'))
            if not value[0] and text[:1] not in '+(':
                found.append(('-' + text, 'crop_digits_signed_by_controls'))
        else:
            found.append((text, 'crop_reading'))
    parts = cell.get('confirmed_parts') or []
    if pair and parts:
        # A part the crops confirmed keeps the page's value in every candidate.
        page = _page_pair(original)
        found = [(text, source) for text, source in found
                 if (value := crop_money_pair(text)) is not None
                 and all(value[PAIR_PARTS.index(name)] == page[PAIR_PARTS.index(name)] for name in parts)]
    return found


def repair_pinned_readings(page, tables, record, *, chunk=None):
    """Accept, for each held Andrews or card money cell, the one printed reading the agreed controls fix.

    Considered only on a page held by this check, without error. Each held
    cell offers the readings a recogniser produced from the print
    (``_printed_readings``): the page reading, the crop reading, or for an
    unreadable sign glyph the agreed digits with either sign. The statement
    reader then accepts a reading only when one printed control equation
    contains the cell as its only disputed cell, every other cell of that
    equation was confirmed here (the page and the crops read it the same
    way), the equation holds with that reading and with no other candidate,
    and with every held cell of its account section resolved, every control
    of that section on this page holds (``pinned_andrews_values``).
    Compensating misreads that only fix a sum of disputed cells stay held.

    All or nothing per account section. A page with any accepted cell carries
    one ``repaired`` record listing, per cell, the page reading, the held
    text, the accepted text and which reading it was, every crop reading and
    the cells that pin it, so the machine reading stays visible beside the
    accepted one, and the cells left held (``unresolved``). Otherwise a
    ``declined`` record says why and the tables are returned unchanged; a page
    no Andrews layout claims gets no record.
    """
    if chunk is None:
        from services.financial.pdf_tables import _chunk as chunk
    if not record or record.get('method') != METHOD or record.get('decision') != 'held':
        return tables, []

    def declined(reason):
        return tables, [dict(method=PINNED_READING_METHOD, page=page.number + 1, decision='declined', reason=reason)]

    candidates, by_key, confirmed, context = {}, {}, set(), {}
    for cell in record['cells']:
        key = (cell['table_index'], cell['row_index'], cell['column_index'])
        if cell['status'] == 'confirmed':
            confirmed.add(key)
            continue
        if cell.get('confirmed_parts') and _page_pair(cell['original_text']) is not None:
            confirmed.update(key + (name,) for name in cell['confirmed_parts'])
            context[key] = money_text(_page_pair(cell['original_text']))
        candidates[key], by_key[key] = dict(_printed_readings(cell)), cell
    from services.financial.statement_reading_quality import pinned_andrews_values, pinned_card_values
    offered = {} if record.get('error') else {key: list(readings) for key, readings in candidates.items()}
    result = pinned_andrews_values([table.to_json() for table in tables], offered, confirmed, context)
    if result is None:
        # A card statement complete on this page: its balance equation and
        # summary totals are the agreed controls (``pinned_card_values``).
        result = pinned_card_values([table.to_json() for table in tables], offered, confirmed)
    if result is None:
        return tables, []
    if record.get('error'):
        return declined('verification_incomplete')
    if not result:
        return declined('not_every_held_cell_is_pinned_by_agreed_controls' if all(candidates.values())
                        else 'held_cell_without_printed_reading')
    accepted = result['values']
    repaired = _with_cells(page, tables, {key: value['text'] for key, value in accepted.items()}, chunk)
    return repaired, [dict(method=PINNED_READING_METHOD, page=page.number + 1, decision='repaired',
        controls=result['controls'], unresolved=result['controls'].get('unresolved', []),
        cells=[dict(table_index=key[0], row_index=key[1], column_index=key[2], rect=by_key[key]['rect'],
                    page_reading=by_key[key]['original_text'], held_text=by_key[key].get('marked_text'),
                    text=value['text'], accepted_reading=candidates[key][value['text']],
                    pinned_by=value['pinned_by'], observations=by_key[key]['observations'],
                    reason='printed_reading_pinned_by_agreed_controls',
                    **({'kind': 'pair'} if by_key[key].get('kind') == 'pair' else {}))
               for key, value in sorted(accepted.items())])]


SECOND_READER_METHOD = 'statement_money_second_reader_repair'
# Digit-only printed text that is not money (dates, account and reference
# numbers) also supplies glyph templates once the crops confirm it.
TEMPLATE_WHITELIST = WHITELIST + '/'
_TEMPLATE_TEXT = re.compile(r'[0-9$.,/()+\-\s]+')


def _compact(text):
    return re.sub(r'\s+', '', text or '')


def _darkness(page, rect, rotation):
    from app.pipeline.statement_glyph_reader import DPI, ink
    image = _strip(page, rect, DPI, rotation)
    try:
        return ink(image)
    finally:
        image.close()


def _template_cells(page, tables, record, *, rotation, deadline, language):
    """``[(cell key, rect, text, source)]`` whose printed text two readings agree on.

    Confirmed money cells come from the verification record. Other cells whose
    text is only digits and money punctuation are reread here from crops at
    every profile and kept only when, as for money, at least four readings at
    both resolutions give exactly the page's characters.
    """
    found = [((c['table_index'], c['row_index'], c['column_index']), c['rect'], c['original_text'], 'money_cell')
             for c in record['cells'] if c['status'] == 'confirmed' and c.get('rect') and c.get('kind') not in ('pair', 'spaced')
             and 'normalised_text' not in c]
    known = {(c['table_index'], c['row_index'], c['column_index']) for c in record['cells']}
    extra = []
    for table_index, table in enumerate(tables):
        geometry = getattr(table, 'geometry', None)
        for cell in getattr(geometry, 'cells', None) or ():
            key = (table_index, cell.row, cell.column)
            compact = _compact(cell.text)
            if (key in known or len(compact) < 2 or not any(ch.isdigit() for ch in compact)
                    or not _TEMPLATE_TEXT.fullmatch(cell.text or '')):
                continue
            rect = _cell_rect(cell, page)
            if rect is not None:
                extra.append((key, rect, cell.text))
    if extra and not page.rotation:
        readings = stacked_readings(page, [rect for _, rect, _ in extra], rotation=rotation, deadline=deadline,
            language=language, whitelist=TEMPLATE_WHITELIST)
        for position, (key, rect, text) in enumerate(extra):
            agreeing = [PROFILES[i][0] for i in sorted(readings)
                        if position < len(readings[i]) and _compact(readings[i][position][0]) == _compact(text)]
            if len(agreeing) >= MIN_AGREEING and set(agreeing) == {dpi for dpi, _ in PROFILES}:
                found.append((key, rect, text, 'digit_text_cell'))
    return found


def _contradicted(record):
    """``(majority crop text by cell, record cell by cell)`` for a page held only by contradictions.

    Every held cell must carry the verification's own ``contradicted``
    verdict: at least ``MIN_AGREEING`` crop readings, spanning both
    resolutions, agree on one amount other than the page reading, those
    readings are character for character the same, and no crop reading at all
    supports the page reading. Otherwise ``None``.
    """
    if not record or record.get('method') != METHOD or record.get('decision') != 'held' or record.get('error'):
        return None
    disputed, by_key = {}, {}
    for cell in record['cells']:
        if cell['status'] == 'confirmed':
            continue
        if cell['status'] != 'contradicted':
            return None
        values = Counter(money_value(o['text']) for o in cell['observations'])
        page_value = money_value(cell['original_text'])
        value, count = next(iter(values.most_common(1)), (None, 0))
        supporters = [o for o in cell['observations'] if money_value(o['text']) == value]
        texts = {_compact(o['text']) for o in supporters}
        if (value is None or value == page_value or count < MIN_AGREEING or values.get(page_value)
                or {o['dpi'] for o in supporters} != {dpi for dpi, _ in PROFILES} or len(texts) != 1):
            return None
        key = (cell['table_index'], cell['row_index'], cell['column_index'])
        disputed[key], by_key[key] = supporters[0]['text'], cell
    return (disputed, by_key) if disputed else None


def repair_with_second_reader(page, tables, record, *, rotation=0, deadline, language, chunk=None):
    """Accept the crop reading of held cells that an independent reader also gives.

    Considered only on a page held solely by contradicted cells: for each,
    at least four crop readings at both resolutions agree on one other amount
    and none supports the page reading (``_contradicted``). Unlike
    ``repair_pinned_cells`` one dissenting crop reading is tolerated, because
    the value must also be given by a reader that is not Tesseract. The glyph reader
    (``statement_glyph_reader``) then reads every disputed cell from the page
    image using templates cut from cells on the same page that the page reading
    and the crops agree on. Every cell must satisfy all of:

    * the glyph reader reads the whole cell, every character, and gives
      exactly the crop reading;
    * the page reading and the crop reading have the same length, and at each
      position where they differ the page has templates for both characters,
      so the glyph reader actually compared the two candidates;

    and then, with every disputed cell replaced, every printed control on the
    page must reconcile (``page_controls_reconcile``): each statement's closing
    balance printed and matching, no difference anywhere, no flagged row.

    All or nothing per page. Anything short of it returns the tables unchanged
    with a ``declined`` record saying why, so the page stays held exactly as
    before. An accepted page carries one ``repaired`` record listing, per
    cell, the page reading, the held text, the accepted text, every crop
    reading and the glyph reader's per-character scores, so the original
    reading stays visible beside the repair.
    """
    if chunk is None:
        from services.financial.pdf_tables import _chunk as chunk
    def declined(reason, **extra):
        return tables, [dict(method=SECOND_READER_METHOD, page=page.number + 1, decision='declined',
                             reason=reason, **extra)]

    if not record or record.get('method') != METHOD or record.get('decision') != 'held':
        return tables, []
    found = _contradicted(record)
    if not found:
        return declined('not_every_held_cell_is_contradicted')
    if page.rotation:
        return declined('page_rotation_not_supported')
    disputed, by_key = found
    from app.pipeline import statement_glyph_reader as glyphs

    started = time.monotonic()
    try:
        sources = _template_cells(page, tables, record, rotation=rotation, deadline=deadline, language=language)
    except (RuntimeError, pytesseract.TesseractError) as exc:
        return declined('template_reread_failed', error=str(exc)[:200])
    strips = {}
    try:
        for key, rect, _, _ in sources:
            strips[key] = _darkness(page, rect, rotation)
        reader = glyphs.PageGlyphs([(key, strips[key], text) for key, _, text, _ in sources])
        summary = dict(reader.summary(), template_sources=dict(
            money_cell=sum(s[3] == 'money_cell' for s in sources),
            digit_text_cell=sum(s[3] == 'digit_text_cell' for s in sources)))
        accepted = {}
        for key, crop_text in sorted(disputed.items()):
            cell = by_key[key]
            page_text, image_text = _compact(cell['original_text']), _compact(crop_text)
            if not cell.get('rect') or len(page_text) != len(image_text):
                return declined('readings_not_aligned', reader=summary)
            needed = {a for pair in zip(page_text, image_text) if pair[0] != pair[1] for a in pair}
            if not needed <= reader.classes:
                return declined('no_templates_for_disputed_characters', reader=summary,
                                missing=sorted(needed - reader.classes))
            reading = reader.read(_darkness(page, cell['rect'], rotation), len(image_text))
            if reading['text'] != image_text:
                return declined('second_reader_does_not_confirm_crop_reading', reader=summary,
                    cell=list(key), glyph_text=reading['text'], glyph_reason=reading.get('reason'))
            accepted[key] = dict(text=crop_text, glyphs=[{k: g[k] for k in ('character', 'score', 'runner_up',
                'runner_up_score')} for g in reading['glyphs']])
    finally:
        strips.clear()
    repaired = _with_cells(page, tables, {key: value['text'] for key, value in accepted.items()}, chunk)
    from services.financial.statement_reading_quality import page_controls_reconcile
    controls = page_controls_reconcile([table.to_json() for table in repaired])
    if not controls or not controls['reconciles']:
        return declined('printed_controls_do_not_reconcile', reader=summary, controls=controls)
    return repaired, [dict(method=SECOND_READER_METHOD, page=page.number + 1, decision='repaired',
        reader=summary, controls=controls, seconds=round(time.monotonic() - started, 3),
        cells=[dict(table_index=key[0], row_index=key[1], column_index=key[2], rect=by_key[key]['rect'],
                    page_reading=by_key[key]['original_text'], held_text=by_key[key]['marked_text'],
                    text=value['text'], observations=by_key[key]['observations'],
                    second_reading=dict(method=glyphs.METHOD, text=_compact(value['text']), glyphs=value['glyphs']),
                    reason='crop_reading_confirmed_by_independent_glyph_reader')
               for key, value in sorted(accepted.items())])]
