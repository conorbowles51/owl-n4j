"""Read a page whose text is printed as vector outlines from the outlines themselves.

Why this exists
---------------
Some statements carry no text layer at all: every character is drawn as a
filled outline (a "vector text" page). The page is read by OCR from a render,
and a narrow sans-serif digit set is read unreliably even though the render
is perfectly sharp: a ``5`` read as ``9`` at 300 dpi, again at 600 and 800 dpi,
and a different misread at 400 dpi (measured on one cell of a real page; more
resolution does not help). Tesseract also reports words over blank paper
(``—-`` between two printed date columns), which breaks the line apart.

What the outlines give
----------------------
Every instance of one character in one font and size is drawn with the same
outline. Grouping the page's filled contours into characters and comparing
their shapes (translated to the character's own corner, equal within
``SHAPE_TOLERANCE`` points) gives each printed character a shape identity, and
the page uses a few hundred distinct shapes for thousands of characters.

What this does
--------------
* ``page_glyphs``: the page's printed characters, each with its rectangle and
  shape identity.
* ``shape_labels``: the character each shape prints, decided by the page's
  own OCR. Every recognised word whose characters align one to one with the
  outlines under it votes for its characters; a shape takes a label only with
  at least ``MIN_LABEL_VOTES`` votes from ``MIN_LABEL_WORDS`` words and
  ``MIN_LABEL_SHARE`` of them agreeing
  (measured: OCR read the page's zero shape as the letter ``O`` in 29 of 147
  words). A shape OCR reads inconsistently has no label.
* ``read_words``: each recognised word is re-read from the outlines under it.
  When its characters align one to one with the outlines under it, a
  character changes only where the outline's label is a figure or money mark
  (``FIGURE_CHARACTERS``): letters keep their OCR reading, so a font drawing
  two letters with one shape cannot rewrite a word. When they do not align
  (OCR added or lost a character), the word is rebuilt from the labels only
  if every character under it has one. A word with a space-wide gap inside
  keeps its reading; a word over no ink at all (no outline, image or other
  drawing) was not printed and is dropped.
* ``read_rect``: the outline reading of one cell, used by the money check to
  confirm a cell (``statement_money_verification``).

No value comes from anywhere but the print: the shape identity is the
document's own drawing and the label is what OCR reads that shape as across
the page. A shape misread systematically would misread every amount carrying
it, and the statement then cannot reconcile and is held.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import re

METHOD = 'vector_outline_glyph_reading'
QUANTUM = 0.05
SHAPE_TOLERANCE = 0.25
MIN_LABEL_VOTES = 3
MIN_LABEL_WORDS = 2
MIN_LABEL_SHARE = 0.6
# ... and at least this many times the votes of any other character.
MIN_LABEL_MARGIN = 2
# An outline reading may drop at most this many OCR characters inside a word.
MAX_DROPPED = 2
# Characters OCR lost inside a word are restored from fully labelled outlines (``_reconciled``). Off: an
# outline reading longer than the OCR word is never taken, as before.
LOST_CHARACTERS = True
# A word's box widened by this much (points) touching no ink at all was not printed.
INKLESS_PADDING = 1.0
# Characters an outline reading may put in place of the OCR's character in an aligned word.
FIGURE_CHARACTERS = frozenset('0123456789.,-+/$()%')
# A filled contour larger than this (points) is a box, a rule or shading, not a character.
MAX_GLYPH_SIZE = 40.0
# A character's outlines stacked together are at most this many times its tallest outline.
MAX_STACK = 1.5
# A page counts as vector text from this many outline segments (paths' line and curve items).
MIN_VECTOR_SEGMENTS = 3000
# A gap between two characters at least this share of the line's height is a space.
SPACE_GAP_SHARE = 0.3


@dataclass(frozen=True)
class Glyph:
    x0: float
    y0: float
    x1: float
    y1: float
    shape: str

    @property
    def centre(self):
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2


def _points(item):
    if item[0] == 're':
        rect = item[1]
        return [(rect.x0, rect.y0), (rect.x1, rect.y1)]
    if item[0] == 'qu':
        quad = item[1]
        return [(p.x, p.y) for p in (quad.ul, quad.ur, quad.lr, quad.ll)]
    return [(p.x, p.y) for p in item[1:] if hasattr(p, 'x')]


def _contours(drawings):
    """Closed outlines of the filled paths: a new contour starts wherever a path jumps."""
    contours = []
    for path in drawings:
        if path.get('fill') is None or path.get('type') not in ('f', 'fs'):
            continue
        current, last = [], None
        for item in path.get('items') or ():
            points = _points(item)
            if not points:
                continue
            if item[0] in ('re', 'qu'):
                if current:
                    contours.append(current)
                contours.append([(item[0], points)])
                current, last = [], None
                continue
            if last is not None and abs(points[0][0] - last[0]) + abs(points[0][1] - last[1]) > 1e-3:
                contours.append(current)
                current = []
            current.append((item[0], points))
            last = points[-1]
        if current:
            contours.append(current)
    return contours


def _bounds(contour):
    xs = [x for _, points in contour for x, _ in points]
    ys = [y for _, points in contour for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _same_character(group, b, tallest):
    """An outline belongs to a character: it overlaps it horizontally, nearly touches it vertically, and
    together they are no taller than ``MAX_STACK`` times the character's tallest single outline (a dot over a
    stem, an accent; never two lines). A colon's dots stay two marks: a word holding one never aligns, and
    its outline reading is not the OCR text with noise removed, so it keeps its OCR reading."""
    overlap = min(group[2], b[2]) - max(group[0], b[0])
    if overlap <= 0 or overlap < 0.5 * min(group[2] - group[0], b[2] - b[0]):
        return False
    tallest = max(tallest, b[3] - b[1])
    gap = max(group[1], b[1]) - min(group[3], b[3])
    return gap <= max(0.6, 0.35 * tallest) and max(group[3], b[3]) - min(group[1], b[1]) <= MAX_STACK * tallest


def _shapes(groups):
    """A shape identity per character: equal outline structure, every point within ``SHAPE_TOLERANCE``.

    Characters are compared in the corner-relative frame, contours in drawing
    order. A producer that snaps outline points to its device grid draws two
    instances of one character apart (measured: 0.12 pt on a 600 dpi grid; up to
    0.24 pt in the worst case, a rounding error on each point and on the corner
    of each instance), so identity is a tolerance, not an exact key. Measured on
    real pages, 0.25 and 0.3 pt only reunite split instances of one character;
    at 0.4 pt distinct letters merge. Each character is compared with the first
    instance of every shape of the same structure.
    """
    first = defaultdict(list)
    shapes = []
    for bounds, contours, _ in groups:
        structure = tuple(tuple(kind for kind, _ in contour) for _, contour in sorted(contours))
        points = [(x - bounds[0], y - bounds[1])
                  for _, contour in sorted(contours) for _, segment in contour for x, y in segment]
        for representative, identity in first[structure]:
            if all(abs(a - c) <= SHAPE_TOLERANCE and abs(b - d) <= SHAPE_TOLERANCE
                   for (a, b), (c, d) in zip(representative, points)):
                shapes.append(identity)
                break
        else:
            key = (structure, [(round(x / QUANTUM), round(y / QUANTUM)) for x, y in points])
            identity = hashlib.sha1(repr(key).encode()).hexdigest()[:16]
            first[structure].append((points, identity))
            shapes.append(identity)
    return shapes


def vector_segments(drawings):
    return sum(len(path.get('items') or ()) for path in drawings)


# A page whose characters are drawn left to right reads upright. Its
# character outlines are drawn in reading order, so consecutive outlines
# step to the right along each printed line. Characters made of several
# outlines (i, j, colons) add as many up as down steps; text drawn
# sideways or upside down steps mostly up, down or left instead.
UPRIGHT_MIN_STEPS = 50
UPRIGHT_VERTICAL_RATIO = 2
UPRIGHT_REVERSE_RATIO = 10


def drawing_directions(drawings):
    """{0: right, 90: down, 180: left, 270: up}: steps between consecutive character outlines."""
    boxes = [b for b in map(_bounds, _contours(drawings))
             if b[2] - b[0] <= MAX_GLYPH_SIZE and b[3] - b[1] <= MAX_GLYPH_SIZE]
    votes = {0: 0, 90: 0, 180: 0, 270: 0}
    for a, b in zip(boxes, boxes[1:]):
        size = max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1], 0.5)
        dx = (b[0] + b[2] - a[0] - a[2]) / 2
        dy = (b[1] + b[3] - a[1] - a[3]) / 2
        if abs(dx) + abs(dy) > 3 * size or abs(dx) + abs(dy) < 0.05 * size:
            continue  # a new line or a repeated outline, not the next character
        if abs(dx) > 3 * abs(dy):
            votes[0 if dx > 0 else 180] += 1
        elif abs(dy) > 3 * abs(dx):
            votes[90 if dy > 0 else 270] += 1
    return votes


def drawn_upright(drawings):
    """True when the page's character outlines clearly run left to right (no rotation needed)."""
    votes = drawing_directions(drawings)
    return (votes[0] >= UPRIGHT_MIN_STEPS
            and votes[0] >= UPRIGHT_VERTICAL_RATIO * max(votes[90], votes[270])
            and votes[0] >= UPRIGHT_REVERSE_RATIO * votes[180])


# A page whose outlines are drawn sideways (a landscape statement printed on a portrait page) is read
# turned upright, as its OCR is: the outlines are turned the same way first (``TurnedPage``), so every
# character, word box and shape label lives in the one frame the OCR words are measured in. Measured on
# real sideways outline pages (one producer, 2022-2025 statements): read without their outlines, OCR
# invented words ('Saldo ae inicial'), split an amount from its line and skipped printed amounts, so their
# periods did not reconcile. Off: a page OCR reads turned keeps its OCR reading, as before.
TURNED_PAGES = True


def turn_point(x, y, rotation, width, height):
    """(x, y) on a ``width`` x ``height`` page, in the frame of the page turned clockwise by ``rotation``."""
    if rotation == 90:
        return height - y, x
    if rotation == 180:
        return width - x, height - y
    if rotation == 270:
        return y, width - x
    return x, y


def turn_rect(rect, rotation, width, height):
    """``rect`` (x0, y0, x1, y1) in the turned frame (see ``turn_point``)."""
    (ax, ay), (bx, by) = (turn_point(rect[0], rect[1], rotation, width, height),
                          turn_point(rect[2], rect[3], rotation, width, height))
    return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)


class TurnedPage:
    """The parts of a page the outline reading uses, turned clockwise by ``rotation`` (90, 180 or 270).

    Points, rectangles and quads of every drawing and the boxes of every image are moved into the frame of
    the turned page; nothing else changes, so a turned character keeps its outline and its shape identity.
    """

    def __init__(self, page, rotation):
        import fitz
        if rotation not in (90, 180, 270):
            raise ValueError(f'unsupported rotation {rotation}')
        self._fitz, self._page, self.rotation_turned = fitz, page, rotation
        self._width, self._height = page.rect.width, page.rect.height
        turned_width, turned_height = ((self._height, self._width) if rotation in (90, 270)
                                       else (self._width, self._height))
        self.rect = fitz.Rect(0, 0, turned_width, turned_height)
        self.rotation = 0
        self._drawings = None

    def _point(self, point):
        return self._fitz.Point(*turn_point(point.x, point.y, self.rotation_turned, self._width, self._height))

    def _rect(self, rect):
        return self._fitz.Rect(*turn_rect((rect.x0, rect.y0, rect.x1, rect.y1), self.rotation_turned,
                                          self._width, self._height))

    def _item(self, item):
        kind = item[0]
        if kind == 're':
            return (kind, self._rect(item[1])) + tuple(item[2:])
        if kind == 'qu':
            quad = item[1]
            return (kind, self._fitz.Quad(*(self._point(p) for p in (quad.ul, quad.ur, quad.ll, quad.lr))))
        return (kind,) + tuple(self._point(p) if hasattr(p, 'x') else p for p in item[1:])

    def get_drawings(self):
        if self._drawings is None:
            turned = []
            for path in self._page.get_drawings():
                path = dict(path)
                path['items'] = [self._item(item) for item in path.get('items') or ()]
                if path.get('rect') is not None:
                    path['rect'] = self._rect(path['rect'])
                turned.append(path)
            self._drawings = turned
        return self._drawings

    def get_image_info(self):
        infos = []
        for info in self._page.get_image_info():
            try:
                infos.append(dict(info, bbox=turn_rect(tuple(info['bbox']), self.rotation_turned,
                                                      self._width, self._height)))
            except (KeyError, TypeError, ValueError):
                continue
        return infos


def page_glyphs(page, drawings=None):
    """The page's printed characters drawn as filled outlines, left to right."""
    if drawings is None:
        drawings = page.get_drawings()
    measured = []
    for order, contour in enumerate(_contours(drawings)):
        bounds = _bounds(contour)
        if bounds[2] - bounds[0] > MAX_GLYPH_SIZE or bounds[3] - bounds[1] > MAX_GLYPH_SIZE:
            continue
        measured.append((bounds, (order, contour)))
    measured.sort(key=lambda item: item[0][0])
    groups, open_groups = [], []
    for bounds, contour in measured:
        open_groups = [g for g in open_groups if g[0][2] >= bounds[0]]
        for group in open_groups:
            if _same_character(group[0], bounds, group[2]):
                b = group[0]
                group[0] = (min(b[0], bounds[0]), min(b[1], bounds[1]), max(b[2], bounds[2]), max(b[3], bounds[3]))
                group[1].append(contour)
                group[2] = max(group[2], bounds[3] - bounds[1])
                break
        else:
            group = [bounds, [contour], bounds[3] - bounds[1]]
            groups.append(group)
            open_groups.append(group)
    return [Glyph(*group[0], shape=shape) for group, shape in zip(groups, _shapes(groups))]


class _Index:
    """Characters by position, for finding the ones under a word's box."""

    def __init__(self, glyphs, cell=20.0):
        self.cell = cell
        self.buckets = defaultdict(list)
        for glyph in glyphs:
            x, y = glyph.centre
            self.buckets[(int(x // cell), int(y // cell))].append(glyph)

    def within(self, x0, y0, x1, y1):
        found = []
        for bx in range(int(x0 // self.cell), int(x1 // self.cell) + 1):
            for by in range(int(y0 // self.cell), int(y1 // self.cell) + 1):
                for glyph in self.buckets.get((bx, by), ()):
                    x, y = glyph.centre
                    if x0 <= x <= x1 and y0 <= y <= y1:
                        found.append(glyph)
        return sorted(found, key=lambda g: g.x0)


def _has_space(glyphs):
    height = max(g.y1 - g.y0 for g in glyphs)
    return any(b.x0 - a.x1 > SPACE_GAP_SHARE * height for a, b in zip(glyphs, glyphs[1:]))


def _amount_gaps(glyphs):
    """Every gap between the characters is narrow enough to lie inside one amount (``AMOUNT_JOIN_GAP``)."""
    height = max(g.y1 - g.y0 for g in glyphs)
    return all(b.x0 - a.x1 <= AMOUNT_JOIN_GAP * height for a, b in zip(glyphs, glyphs[1:]))


def _without_added_marks(text, under):
    """``text`` without the marks at its ends OCR read where no character is printed (a column rule
    read as ``)`` or ``|``), when that leaves exactly one character per outline; else ``text``."""
    if len(text) <= len(under):
        return text
    trimmed = re.sub(r'^[^0-9A-Za-z$]+|[^0-9A-Za-z.]+$', '', text)
    return trimmed if len(trimmed) == len(under) else text


def shape_labels(glyphs, words):
    """``{shape: (label, votes, total)}`` for every shape the page's OCR reads consistently.

    ``words`` are ``(text, (x0, y0, x1, y1))`` in page points.
    """
    index = _Index(glyphs)
    votes, voters = defaultdict(Counter), defaultdict(set)
    for number, (text, box) in enumerate(words):
        text = (text or '').strip()
        if not text or any(c.isspace() for c in text):
            continue
        under = index.within(*box)
        if not under:
            continue
        text = _without_added_marks(text, under)
        if len(under) != len(text) or (_has_space(under) and not (_AMOUNT.fullmatch(text) and _amount_gaps(under))):
            continue
        for glyph, character in zip(under, text):
            votes[glyph.shape][character] += 1
            voters[glyph.shape].add(number)
    labels = {}
    for shape, counter in votes.items():
        (label, count), *others = counter.most_common(2)
        total = sum(counter.values())
        if (count >= MIN_LABEL_VOTES and count >= MIN_LABEL_SHARE * total and len(voters[shape]) >= MIN_LABEL_WORDS
                and all(count >= MIN_LABEL_MARGIN * other for _, other in others)):
            labels[shape] = (label, count, total)
    return labels


def read_glyphs(glyphs, labels):
    """The labelled text of ``glyphs`` (left to right), or ``None`` when any of them has no label."""
    if not glyphs or any(g.shape not in labels for g in glyphs):
        return None
    return ''.join(labels[g.shape][0] for g in glyphs)


def _reconciled(text, reading):
    """``reading`` (outlines) matches the OCR ``text`` up to what OCR can add or lose.

    Every character of the reading stands for one OCR character in order: the
    same character, or a figure or money mark (``FIGURE_CHARACTERS``) in place
    of whatever OCR read there. OCR characters with no outline are dropped: at
    most ``MAX_DROPPED``, and at the word's ends only marks that are neither
    letters nor figures, because a missing end character is more likely a
    printed letter the OCR box cut off than one OCR invented. A character of
    the reading OCR lost (``14NAR`` over the outlines of ``14/MAR``: a slash and
    a letter read as one) is kept only inside the word, between characters OCR
    read on both sides of it, so it lies within the box OCR drew over the word;
    outlines past either end of the OCR word are never added. Dropped and lost
    characters together are at most ``MAX_DROPPED``. A reading longer than the
    OCR word replaces only OCR letters (an ``O`` on a zero's outline, an ``N`` on
    a slash's): every figure and mark OCR read must be the reading's own, so
    the reading cannot slide along an amount by one character.
    """
    from functools import lru_cache
    n, m = len(text), len(reading)

    @lru_cache(maxsize=None)
    def best(i, j):
        # Fewest drops to match text[i:] to reading[j:]; None when impossible.
        if j == m:
            return 0 if all(not c.isalnum() for c in text[i:]) else None
        if i == n:
            return None
        options = []
        if text[i] == reading[j] or reading[j] in FIGURE_CHARACTERS and (m <= n or text[i].isalpha()):
            after = best(i + 1, j + 1)
            if after is not None:
                options.append(after)
        if j > 0 or not text[i].isalnum():
            after = best(i + 1, j)
            if after is not None:
                options.append(after + 1)
        if LOST_CHARACTERS and 0 < i and 0 < j < m - 1:
            # A character OCR lost inside the word: the reading's next character is matched after it.
            after = best(i, j + 1)
            if after is not None:
                options.append(after + 1)
        return min(options) if options else None

    if not m or (m > n and not LOST_CHARACTERS) or m > n + MAX_DROPPED:
        return False
    dropped = best(0, 0)
    return dropped is not None and dropped <= MAX_DROPPED


def _aligned_reading(text, under, labels):
    """``text`` read one character per outline: a character changes only where its outline's label is a
    figure or money mark (``FIGURE_CHARACTERS``)."""
    characters = []
    for glyph, character in zip(under, text):
        label = labels.get(glyph.shape, (None,))[0]
        characters.append(label if label is not None and label in FIGURE_CHARACTERS else character)
    return ''.join(characters)


def _word_reading(text, under, labels):
    if _has_space(under):
        # A narrow figure's side bearing can be as wide as a space: one amount
        # stays one word when every gap is within the amount limit.
        reading = read_glyphs(under, labels) if _amount_gaps(under) else None
        if reading is not None and _AMOUNT.fullmatch(reading) and _reconciled(text, reading):
            return reading
        # The same holds for any token of figures OCR read as one word: a date
        # whose two 1s stand a space-wide side bearing apart ('11/05/2021', OCR
        # '41/05/2021'). One character per outline (a mark OCR added at an end
        # dropped), each changed only where its outline's label is a figure.
        trimmed = text if len(text) <= len(under) else re.sub(r'^[^0-9A-Za-z$]+|[^0-9A-Za-z$]+$', '', text)
        if _amount_gaps(under) and len(under) == len(trimmed) and all(c in FIGURE_CHARACTERS for c in trimmed):
            return _aligned_reading(trimmed, under, labels)
        return None
    if len(under) == len(text):
        return _aligned_reading(text, under, labels)
    if len(under) > len(text) and any(b.x0 < a.x1 for a, b in zip(under, under[1:])):
        # More outlines than OCR characters, two of them stacked over each other (a colon's two dots): they
        # may be one printed character, so OCR's reading is kept.
        return None
    reading = read_glyphs(under, labels)
    return reading if reading is not None and _reconciled(text, reading) else None


def other_ink(page, drawings):
    """Rectangles of everything printed on the page that is not a character outline (images, rules, boxes)."""
    rects = []
    for info in page.get_image_info():
        try:
            rects.append(tuple(info['bbox']))
        except (KeyError, TypeError):
            continue
    for path in drawings:
        rect = path.get('rect')
        if rect is not None and (path.get('fill') is None or rect.width > MAX_GLYPH_SIZE or rect.height > MAX_GLYPH_SIZE):
            rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
    return rects


def _touches(box, rects):
    x0, y0, x1, y1 = box
    return any(r[0] <= x1 and x0 <= r[2] and r[1] <= y1 and y0 <= r[3] for r in rects)


def inkless(glyphs, ink, box):
    """The word box, widened by ``INKLESS_PADDING``, touches no character outline and no other ink."""
    x0, y0, x1, y1 = box
    padded = (x0 - INKLESS_PADDING, y0 - INKLESS_PADDING, x1 + INKLESS_PADDING, y1 + INKLESS_PADDING)
    return not _touches(padded, [(g.x0, g.y0, g.x1, g.y1) for g in glyphs]) and not _touches(padded, ink)


_AMOUNT = re.compile(r'-?\d{1,3}(?:,\d{3})*\.\d{2}-?')
# Measured on real outline pages: gaps inside a word reach 0.49 of its height ("1" before "."), gaps
# between words go down to 0.31; two pieces of one amount are rejoined across at most this much.
AMOUNT_JOIN_GAP = 0.5


# A day of the month (one or two figures) OCR skipped as the first word of a printed line carrying an amount
# (a movement line) is added from its outlines too (``unread_words``). Measured: a day printed against the
# table's left rule on a statement's first page, read nowhere, left its movement undated and the period held.
# Off: only amounts are added, as before.
LINE_START_DAYS = True
_DAY = re.compile(r'(?:0?[1-9]|[12]\d|3[01])')


def _line_carries_amount(run, texts, words, top, bottom):
    """A grouped amount with two decimals stands to the right of ``run`` on its printed line: an OCR word
    centred within the line's band, or an amount this reading adds on the same line."""
    right = max(g.x1 for g in run)
    return (any(text is not None and _AMOUNT.fullmatch(text) for text in texts)
            or any(_AMOUNT.fullmatch((text or '').strip()) and box[0] > right and top <= (box[1] + box[3]) / 2 <= bottom
                   for text, box in words))


def unread_words(glyphs, labels, words):
    """``[(text, box)]``: printed amounts no OCR word covers, read from their outlines.

    OCR can skip a printed amount altogether. Characters whose centre lies in
    no OCR word's box are joined into words along their printed line, split at
    space-wide gaps (``SPACE_GAP_SHARE``). A narrow figure's side bearing can
    be as wide as a space, so two neighbouring pieces are rejoined (gap at most
    ``AMOUNT_JOIN_GAP`` of the height) only when neither is an amount alone and
    together they are one (``9,981`` and ``.80``). A word is returned only when
    no character of it is under an OCR word, every character has a label, and
    it is a grouped amount with two decimals (``_AMOUNT``). The one other word
    added is a day of the month (``LINE_START_DAYS``): the line's first run of
    characters, one or two figures reading 1 to 31, every one labelled and none
    under an OCR word, on a line where an amount stands to its right. Nothing
    else is added: not letters, other dates or references.
    """
    covered = set()
    index = _Index(glyphs)
    for text, box in words:
        if (text or '').strip():
            covered.update(id(g) for g in index.within(*box))
    lines = []
    for glyph in sorted(glyphs, key=lambda g: (g.y1, g.x0)):
        for line in lines:
            # Any overlap: in bottom-edge order a line's digits come before its commas, which hang below them.
            if min(line['y1'], glyph.y1) - max(line['y0'], glyph.y0) > 0:
                line['glyphs'].append(glyph)
                line['y0'], line['y1'] = min(line['y0'], glyph.y0), max(line['y1'], glyph.y1)
                break
        else:
            lines.append(dict(y0=glyph.y0, y1=glyph.y1, glyphs=[glyph]))
    found = []
    for line in lines:
        ordered = sorted(line['glyphs'], key=lambda g: g.x0)
        height = max(g.y1 - g.y0 for g in ordered)
        runs, current = [], [ordered[0]]
        for previous, glyph in zip(ordered, ordered[1:]):
            if glyph.x0 - previous.x1 > SPACE_GAP_SHARE * height:
                runs.append(current)
                current = []
            current.append(glyph)
        runs.append(current)
        texts = [read_glyphs(run, labels) for run in runs]
        joined, k = [], 0
        while k < len(runs):
            run, text = runs[k], texts[k]
            if (k + 1 < len(runs) and text is not None and texts[k + 1] is not None
                    and runs[k + 1][0].x0 - run[-1].x1 <= AMOUNT_JOIN_GAP * height
                    and not _AMOUNT.fullmatch(text) and not _AMOUNT.fullmatch(texts[k + 1])
                    and _AMOUNT.fullmatch(text + texts[k + 1])):
                run, text = run + runs[k + 1], text + texts[k + 1]
                k += 1
            joined.append((run, text))
            k += 1
        for position, (run, text) in enumerate(joined):
            if text is None or any(id(g) in covered for g in run):
                continue
            if not _AMOUNT.fullmatch(text) and not (
                    LINE_START_DAYS and position == 0 and _DAY.fullmatch(text) and _whole_day(run, ordered, height)
                    and _line_carries_amount(run, [t for _, t in joined[1:]], words, line['y0'], line['y1'])):
                continue
            found.append((text, (min(g.x0 for g in run), min(g.y0 for g in run),
                                 max(g.x1 for g in run), max(g.y1 for g in run))))
    return found


def _whole_day(run, ordered, height):
    """``run`` is a whole day entry of its own column: at most two characters, every gap inside it narrower
    than one inside an amount (``AMOUNT_JOIN_GAP``), and no other character of the line (read or not) within
    a column gap (``UNREAD_LINE_COLUMN_GAP`` heights) after it. Measured: OCR read the second figure of a
    printed '10' into the word beside it, leaving the '1' alone; that '1' is not the day."""
    if len(run) > 2 or not _amount_gaps(run):
        return False
    after = [g for g in ordered if g.x0 >= run[-1].x1 and g not in run]
    return not after or min(g.x0 for g in after) - run[-1].x1 >= UNREAD_LINE_COLUMN_GAP * height


_GROUP_HEAD = re.compile(r'-?\d{1,3}(?:,\d{3})*')
_GROUP_TAIL = re.compile(r'\d{3}(?:,\d{3})*\.\d{2}-?')
# Two OCR words of one printed amount split where OCR skipped its thousands comma are read as one amount
# (``split_amounts``). Off: the two pieces stay apart, as before.
SPLIT_AMOUNTS_JOIN = True
MAX_UNCOVERED_JOIN = 3


def split_amounts(glyphs, labels, words):
    """``[(i, j, text)]``: words ``i`` and ``j`` are two pieces of one printed amount OCR split at a thousands
    comma it skipped ('47,382' and '615.29' with the comma's outline under neither word).

    The first piece is a grouped whole number, the second three figures (more groups) with two decimals.
    Between their outlines stand at most ``MAX_UNCOVERED_JOIN`` outlines no word covers: the comma, and any
    figure the first word's box cut off ('385' read over the outlines of '38', the '5' and the comma past its
    edge). Every gap is narrow enough to lie inside one amount (``AMOUNT_JOIN_GAP``); the outlines up to the
    second piece read exactly as the first OCR word and a comma, and the whole run reads exactly as the two
    OCR pieces joined by that comma, a grouped amount with two decimals (``_AMOUNT``). Nothing else is joined.
    """
    if not SPLIT_AMOUNTS_JOIN:
        return []
    index = _Index(glyphs)
    unders, owner = [], {}
    for number, (text, box) in enumerate(words):
        text = (text or '').strip()
        under = index.within(*box) if text and not any(c.isspace() for c in text) else []
        unders.append(under)
        for glyph in under:
            owner.setdefault(id(glyph), number)
    found = []
    for i, (text, _) in enumerate(words):
        text = (text or '').strip()
        under = unders[i]
        if not under or not _GROUP_HEAD.fullmatch(text):
            continue
        height = max(g.y1 - g.y0 for g in under)
        top, bottom = min(g.y0 for g in under), max(g.y1 for g in under)
        run, between, last = list(under), [], under[-1]
        while True:
            reach = AMOUNT_JOIN_GAP * height
            near = [g for g in index.within(last.x1, top - height, last.x1 + reach + height, bottom + height)
                    if g.x0 > last.x0 and g.y0 < bottom and g.y1 > top and 0 <= g.x0 - last.x1 <= reach]
            if not near:
                break
            following = min(near, key=lambda g: g.x0)
            if id(following) in owner:
                j = owner[id(following)]
                tail = (words[j][0] or '').strip()
                if (between and j != i and unders[j] and unders[j][0] is following and _GROUP_TAIL.fullmatch(tail)
                        and _amount_gaps(run + unders[j]) and read_glyphs(run, labels) == text + ','):
                    reading = read_glyphs(run + unders[j], labels)
                    if reading == text + ',' + tail and _AMOUNT.fullmatch(reading):
                        found.append((i, j, reading))
                break
            if len(between) >= MAX_UNCOVERED_JOIN:
                break
            between.append(following)
            run.append(following)
            last = following
    return found


# A printed line OCR skipped is read again only when it has at least this many characters (a lone
# outline is a rule piece or a mark), and its words split into column runs at gaps this many line heights wide.
MIN_UNREAD_LINE_CHARACTERS = 3
UNREAD_LINE_COLUMN_GAP = 1.5
# Characters of one printed line have centres within this share of the line's height.
LINE_CENTRE_SHARE = 0.35
# A mark (comma, period, quote) is shorter than this share of the page's median character height. Its
# centre sits near the line's baseline or cap height, outside the centre band, so it joins the nearest
# line whose centre lies within ``MARK_LINE_SHARE`` of that line's height.
MARK_HEIGHT_SHARE = 0.5
MARK_LINE_SHARE = 0.75


def _printed_lines(glyphs):
    """Characters grouped into printed lines: ``[{'centre', 'height', 'glyphs'}]``.

    Characters of ordinary height are grouped by their centres (``LINE_CENTRE_SHARE``).
    A mark's centre lies outside that band (measured: the thousands comma of
    '$12,345.67' sits 3.5 pt below the centre of a 9.5 pt line), so marks join the
    nearest such line afterwards; a mark near no line is grouped with other marks.
    """
    heights = sorted(g.y1 - g.y0 for g in glyphs)
    median = heights[len(heights) // 2] if heights else 0.0
    marks = [g for g in glyphs if g.y1 - g.y0 < MARK_HEIGHT_SHARE * median]
    mark_ids = {id(g) for g in marks}

    def group(members, lines):
        for glyph in sorted(members, key=lambda g: (g.centre[1], g.x0)):
            height = glyph.y1 - glyph.y0
            for line in lines:
                if abs(line['centre'] - glyph.centre[1]) <= LINE_CENTRE_SHARE * max(line['height'], height):
                    line['glyphs'].append(glyph)
                    line['height'] = max(line['height'], height)
                    break
            else:
                lines.append(dict(centre=glyph.centre[1], height=height, glyphs=[glyph]))
        return lines

    lines = group([g for g in glyphs if id(g) not in mark_ids], [])
    loose = []
    for mark in marks:
        near = [line for line in lines if abs(line['centre'] - mark.centre[1]) <= MARK_LINE_SHARE * line['height']]
        if near:
            min(near, key=lambda line: abs(line['centre'] - mark.centre[1]))['glyphs'].append(mark)
        else:
            loose.append(mark)
    return lines + group(loose, [])


def unread_lines(glyphs, words):
    """``[(box, glyphs)]``: runs of printed characters along one line, none of them under any OCR word.

    Page OCR can skip a whole printed line (measured: an addressee's first name
    line and two summary lines between a shaded box and a mailing block). The
    outlines show where it is printed. Characters are grouped into lines
    (``_printed_lines``) and split into column runs at gaps wider than
    ``UNREAD_LINE_COLUMN_GAP`` line heights; a run is returned when it has at
    least ``MIN_UNREAD_LINE_CHARACTERS`` characters and no character of it lies
    under an OCR word, so a line OCR read even in part is never returned.
    Nothing is read here: the caller reads each run's own image.
    """
    covered = set()
    index = _Index(glyphs)
    for text, box in words:
        if (text or '').strip():
            covered.update(id(g) for g in index.within(*box))
    lines = _printed_lines(glyphs)
    found = []
    for line in lines:
        ordered = sorted(line['glyphs'], key=lambda g: g.x0)
        runs, current = [], [ordered[0]]
        for previous, glyph in zip(ordered, ordered[1:]):
            if glyph.x0 - previous.x1 > UNREAD_LINE_COLUMN_GAP * line['height']:
                runs.append(current)
                current = []
            current.append(glyph)
        runs.append(current)
        for run in runs:
            if len(run) >= MIN_UNREAD_LINE_CHARACTERS and not any(id(g) in covered for g in run):
                found.append(((min(g.x0 for g in run), min(g.y0 for g in run),
                               max(g.x1 for g in run), max(g.y1 for g in run)), run))
    return sorted(found, key=lambda item: (item[0][1], item[0][0]))


def _box_cut(index, under, box):
    """An outline character of the same printed line lies just past either end of the characters under the
    word's box, nearer than a space (``SPACE_GAP_SHARE`` of the height): the box cut a printed character off."""
    height = max(g.y1 - g.y0 for g in under)
    top, bottom = min(g.y0 for g in under), max(g.y1 for g in under)
    first, last = under[0], under[-1]
    reach = SPACE_GAP_SHARE * height
    near = index.within(box[0] - reach - height, top, box[2] + reach + height, bottom)
    inside = {id(g) for g in under}
    return any(id(g) not in inside and min(g.y1, bottom) - max(g.y0, top) > 0
               and (0 <= g.x0 - last.x1 < reach or 0 <= first.x0 - g.x1 < reach) for g in near)


# A word with more OCR characters than outlines under its box keeps its OCR reading when the box cut off a
# printed character beside it (``_box_cut``): OCR read 385 where the box held only the outlines of 38 and
# the 5 stood just past its edge. Off: such a word may be rebuilt from the outlines it covers, as before.
CUT_BOX_KEEPS_OCR = True


def read_words(glyphs, labels, words):
    """Each word ``(text, box)`` re-read from the outlines under it, or ``None`` where it keeps its reading."""
    index = _Index(glyphs)
    results = []
    for text, box in words:
        text = (text or '').strip()
        under = index.within(*box) if text and not any(c.isspace() for c in text) else []
        if under and CUT_BOX_KEEPS_OCR and len(under) < len(text) and _box_cut(index, under, box):
            results.append(None)
            continue
        results.append(_word_reading(text, under, labels) if under else None)
    return results


def read_rect(glyphs, labels, rect):
    """The outline reading of the characters centred in ``rect`` (page points), spaces where printed gaps are.

    ``None`` when the rectangle covers no character or any character in it has no label.
    """
    under = _Index(glyphs).within(*rect)
    if not under:
        return None
    # One printed line: every character overlaps the band of the others (a comma hangs below the digits).
    top, bottom = min(g.y1 for g in under), max(g.y0 for g in under)
    if bottom >= top:
        return None
    line = under
    height = max(g.y1 - g.y0 for g in line)
    text = []
    for previous, glyph in zip([None] + line[:-1], line):
        if glyph.shape not in labels:
            return None
        if previous is not None and glyph.x0 - previous.x1 > SPACE_GAP_SHARE * height:
            text.append(' ')
        text.append(labels[glyph.shape][0])
    return ''.join(text)
