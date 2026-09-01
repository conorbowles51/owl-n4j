"""Recover a page's rows from where its words sit, when no ruling lines exist.

``find_tables()`` locates a table by its drawn geometry -- the ruled lines and
cell rectangles a page uses to box its data.  That is the right first attempt
and it is why :mod:`services.financial.pdf_tables` makes it.  But a great many
bank statements are not drawn that way, and two failure shapes matter here
because both were measured on real subpoenaed material rather than imagined:

* A scanned statement has no vector geometry at all.  Every ruling line on the
  page is pixels in an image, invisible to a reader looking for drawn shapes.
  Measured on a 56-page credit-card subpoena response: **zero** drawings on the
  page carrying the transaction list, and therefore zero tables found.
* A digitally-generated statement can separate its rows with whitespace and
  section headings instead of boxes.  Measured on a 108-page card statement
  set: the detector found a table *rectangle* on 34 pages and resolved no cells
  inside any of them, so every one produced no text.

In both shapes the transactions are plainly present -- a person reading the
page sees them -- and the pipeline saw nothing.  That is the failure this
module exists to prevent, and the principle behind it is worth stating plainly
because getting it wrong is what caused the original bug: **a detector finding
nothing is not evidence that there is nothing there.**  It is evidence about
the detector.  So when drawn geometry yields no rows, the page is read again by
where its words actually sit.

What this module deliberately does not do is decide what a row *means*.  It
produces a grid of text and a rectangle for every cell, in exactly the shape
``find_tables()`` produces, and hands it back.  Whether a row is a transaction,
a running balance or a marketing footnote is a question for a parser that knows
what document it is reading, and answering it here would put that judgement in
the one place that cannot see the answer.

Like :mod:`services.financial.pdf_tables`, this module never imports PyMuPDF.
It reads ``get_text("words")``, ``rect`` and ``rotation`` off whatever it is
handed, which is the shape a fitz ``Page`` has and which a stub can have too.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

# ---------------------------------------------------------------------------
# Thresholds
#
# Every constant below is a multiple of something the page itself reports,
# because a statement rendered at a different scale would defeat any absolute
# figure. The measurements that fix the multiples are recorded beside them:
# they come from the two documents named in the module docstring, sampled
# across four pages of each.
# ---------------------------------------------------------------------------

#: Two words with the same text whose rectangles share more than this fraction
#: of area are the same word written twice.  Measured: a scanned statement
#: carrying two overlapping OCR layers produced 1,945 such pairs at a median
#: overlap of 0.93, offset from each other by less than a point; the
#: digitally-generated set produced none at all.  Anything above a half is
#: therefore a wide margin, and the check costs nothing on a clean page.
DUPLICATE_OVERLAP = 0.5

#: A word belongs to the line above it when their vertical centres are within
#: this multiple of the page's median word height.  Measured: median height
#: 8.3pt with transaction rows 7pt apart, so the tolerance has to stay well
#: below a row's pitch while still absorbing the half-point of vertical jitter
#: between two OCR layers of the same line.
LINE_TOLERANCE = 0.45

#: A horizontal gap wider than this multiple of the page's median inter-word
#: gap ends a cell.  Measured: median gap 1.9pt within words of a phrase, while
#: the narrowest real column gutter observed was 12.5pt and most were far
#: wider.  Three times the median lands between the two with room on each side.
COLUMN_GAP = 3.0

#: Floor for the same threshold, so a page whose words happen to sit unusually
#: close together cannot produce a gap threshold small enough to split ordinary
#: prose into columns.
MIN_COLUMN_GAP = 6.0

#: Points of clear space left between one row's rectangle and the next.
#:
#: Sharing an edge is not enough.  :func:`services.financial.locators.capture`
#: stores rectangles as integer millipoints and rounds *outward* -- ``x0`` and
#: ``y0`` down, ``x1`` and ``y1`` up -- so that a hairline of ink at the margin
#: is never cropped away.  Two rectangles meeting exactly on a boundary
#: therefore both claim the millipoint that boundary falls in, and
#: ``locate_table`` rejects the pair.  A separation of two millipoints survives
#: the rounding in both directions with one to spare.  It is a five-hundredth
#: of a point of highlight given up, and it is given up in the direction of
#: showing less rather than more.
BAND_SEPARATION = 0.002

#: A page must yield at least this many rows before it is offered as a table.
#: One line of text is not a table, and calling it one would put a spurious
#: single-cell "table" on every page of running prose in a document.
MIN_ROWS = 2


@dataclass(frozen=True, slots=True)
class Word:
    """One positioned word, in the coordinate space ``get_text`` reports."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def y_centre(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)


@dataclass(frozen=True, slots=True)
class _Cell:
    """A run of words that sit together, and the rectangle enclosing them."""

    text: str
    rect: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class _Row:
    """One visual line, exposing ``cells`` the way a fitz table row does."""

    values: tuple[str, ...]
    cells: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True, slots=True)
class TextRowTable:
    """A table recovered from word positions, shaped like a drawn one.

    The attribute names here are not arbitrary and are not this module's to
    choose: ``bbox``, ``extract()`` and ``rows[].cells`` are precisely what
    :mod:`services.financial.pdf_tables` reads off a table found by drawn
    geometry.  Matching them means the recovered table travels through the
    existing chunking and locating code unchanged, rather than through a
    parallel path that would have to be kept in step with it -- which is the
    same two-lists-drifting hazard that module was written to avoid.
    """

    bbox: tuple[float, float, float, float]
    rows: tuple[_Row, ...]

    def extract(self) -> list[list[str]]:
        return [list(row.values) for row in self.rows]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def cell_count(self) -> int:
        return sum(len(row.values) for row in self.rows)


def _words_of(page: Any) -> list[Word]:
    """Read the page's positioned words, tolerating a reader that offers none.

    ``get_text("words")`` yields tuples whose first five members are the
    rectangle and the text; later members carry block, line and word indices
    which this module deliberately ignores.  Those indices describe the
    reader's own segmentation of the page, and on a document carrying two OCR
    layers they place the same visual line in two different blocks -- so
    trusting them would reintroduce exactly the duplication that
    :func:`deduplicate` exists to remove.  Position is the only thing on the
    page that both layers agree about.
    """
    raw = page.get_text("words")
    words: list[Word] = []
    for item in raw:
        if len(item) < 5:
            continue
        x0, y0, x1, y1, text = item[0], item[1], item[2], item[3], item[4]
        if not isinstance(text, str) or not text.strip():
            continue
        words.append(
            Word(
                x0=float(x0),
                y0=float(y0),
                x1=float(x1),
                y1=float(y1),
                text=text.strip(),
            )
        )
    return words


def _overlap_fraction(first: Word, second: Word) -> float:
    """Shared area as a fraction of the smaller word's area.

    The smaller is the denominator so that a short word sitting inside a
    longer one is judged by how much of *itself* is covered.  Using the larger
    would let a duplicate hide inside a neighbour.
    """
    width = min(first.x1, second.x1) - max(first.x0, second.x0)
    height = min(first.y1, second.y1) - max(first.y0, second.y0)
    if width <= 0 or height <= 0:
        return 0.0
    smaller = min(first.area, second.area)
    if smaller <= 0:
        return 0.0
    return (width * height) / smaller


def deduplicate(words: Sequence[Word]) -> list[Word]:
    """Drop words that are another word written over the top of itself.

    A scanned PDF can carry more than one OCR text layer, each a complete
    reading of the page, offset from the other by a fraction of a point.  Left
    in, every figure on the page appears twice: a sum doubles, a transaction
    list doubles, and nothing anywhere reports an error.  It is the quietest
    corruption in this whole path, which is why it is removed here at the point
    the words are first read rather than guarded against downstream.

    Only words with identical text are considered, so two different values
    that happen to sit close together are never merged -- the comparison can
    reject a duplicate but it cannot invent one.
    """
    by_text: dict[str, list[Word]] = {}
    for word in words:
        by_text.setdefault(word.text, []).append(word)

    dropped: set[int] = set()
    for group in by_text.values():
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda w: (w.y0, w.x0))
        for index, word in enumerate(ordered):
            if id(word) in dropped:
                continue
            for other in ordered[index + 1 :]:
                if id(other) in dropped:
                    continue
                if _overlap_fraction(word, other) > DUPLICATE_OVERLAP:
                    dropped.add(id(other))
    return [word for word in words if id(word) not in dropped]


def _median_height(words: Sequence[Word]) -> float:
    heights = [w.y1 - w.y0 for w in words if w.y1 > w.y0]
    if not heights:
        return 0.0
    return statistics.median(heights)


def group_lines(words: Sequence[Word], tolerance: float) -> list[list[Word]]:
    """Group words into visual lines by vertical centre, left to right.

    Grouping is against the running line's own centre rather than against the
    previous word, so a line does not drift downwards across a page as each
    word extends the tolerance a little further than the last.
    """
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w.y_centre, w.x0))
    lines: list[list[Word]] = []
    current: list[Word] = [ordered[0]]
    centre = ordered[0].y_centre
    for word in ordered[1:]:
        if abs(word.y_centre - centre) <= tolerance:
            current.append(word)
            centre = sum(w.y_centre for w in current) / len(current)
        else:
            lines.append(sorted(current, key=lambda w: w.x0))
            current = [word]
            centre = word.y_centre
    lines.append(sorted(current, key=lambda w: w.x0))
    return lines


def _median_gap(lines: Sequence[Sequence[Word]]) -> float:
    gaps: list[float] = []
    for line in lines:
        for previous, word in zip(line, line[1:]):
            gap = word.x0 - previous.x1
            if gap >= 0:
                gaps.append(gap)
    if not gaps:
        return 0.0
    return statistics.median(gaps)


def line_bands(lines: Sequence[Sequence[Word]]) -> list[tuple[float, float]]:
    """The vertical strip belonging to each line, bounded by its neighbours.

    A cell's rectangle is the union of the boxes its words report, and those
    boxes are taller than the glyphs inside them: a line carrying a logo, a
    heading or an accented capital reaches into the line below.  Two rows whose
    rectangles overlap are two rows a click cannot choose between, which is why
    :func:`services.financial.table_geometry.locate_table` refuses them -- and
    refusing is right, because the alternative is a highlight drawn over a
    figure the analyst did not ask about.  Measured before this existed: on the
    scanned statement only 2 of 56 pages survived that check, and on the
    digitally-generated set 50 of 97.

    So each line is given the strip between the midpoints to the lines above
    and below it, and cells are *clipped* into that strip.  Clipping only ever
    narrows a highlight, and never past the words' own centres; expanding one
    would put the box somewhere the value is not.  Adjacent strips stop
    :data:`BAND_SEPARATION` short of the midpoint on each side, because merely
    meeting there is not enough once the rectangle is rounded for storage.
    """
    if not lines:
        return []
    extents = [
        (min(w.y0 for w in line), max(w.y1 for w in line)) for line in lines
    ]
    centres = [sum(w.y_centre for w in line) / len(line) for line in lines]
    bands: list[tuple[float, float]] = []
    for index, (top, bottom) in enumerate(extents):
        if index > 0:
            boundary = (centres[index - 1] + centres[index]) / 2.0
            top = max(top, boundary + BAND_SEPARATION)
        if index + 1 < len(extents):
            boundary = (centres[index] + centres[index + 1]) / 2.0
            bottom = min(bottom, boundary - BAND_SEPARATION)
        if not bottom > top:
            # Only reachable if two lines report the same centre, which
            # group_lines does not produce; fall back to the untrimmed extent
            # rather than emitting a rectangle of no height.
            top, bottom = extents[index]
        bands.append((top, bottom))
    return bands


def split_cells(
    line: Sequence[Word],
    gap_threshold: float,
    band: Optional[tuple[float, float]] = None,
) -> list[_Cell]:
    """Break one line into cells wherever the words stop being adjacent."""
    if not line:
        return []
    cells: list[_Cell] = []
    run: list[Word] = [line[0]]
    for previous, word in zip(line, line[1:]):
        if word.x0 - previous.x1 > gap_threshold:
            cells.append(_cell_of(run, band))
            run = [word]
        else:
            run.append(word)
    cells.append(_cell_of(run, band))
    return _separate(cells)


def _separate(cells: Sequence[_Cell]) -> list[_Cell]:
    """Pull back any cell whose box reaches into the one to its right.

    Cells are cut at wide gaps, so the *last* word of one run ends before the
    first word of the next.  An earlier word in the run can still be the widest
    one and reach past that boundary -- rare, but it produces the same
    unclickable overlap vertically stacked rows do, and for the same reason it
    is trimmed rather than tolerated.
    """
    trimmed: list[_Cell] = []
    for index, cell in enumerate(cells):
        if index + 1 < len(cells):
            limit = cells[index + 1].rect[0] - BAND_SEPARATION
            if cell.rect[2] > limit > cell.rect[0]:
                cell = _Cell(
                    text=cell.text,
                    rect=(cell.rect[0], cell.rect[1], limit, cell.rect[3]),
                )
        trimmed.append(cell)
    return trimmed


def _cell_of(
    run: Sequence[Word], band: Optional[tuple[float, float]] = None
) -> _Cell:
    top = min(w.y0 for w in run)
    bottom = max(w.y1 for w in run)
    if band is not None:
        top = max(top, band[0])
        bottom = min(bottom, band[1])
    return _Cell(
        text=" ".join(word.text for word in run),
        rect=(min(w.x0 for w in run), top, max(w.x1 for w in run), bottom),
    )


def _bbox_of(rows: Iterable[_Row]) -> Optional[tuple[float, float, float, float]]:
    rects = [rect for row in rows for rect in row.cells]
    if not rects:
        return None
    return (
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    )


def read_text_rows(page: Any) -> Optional[TextRowTable]:
    """Every row this page's word positions describe, or ``None`` if too few.

    Returns a single table covering the page rather than attempting to find
    several.  Splitting a page into separate tables needs a rule for where one
    ends and the next begins, and every rule available here -- a blank line, a
    change of column count, a heading -- is wrong on one of the two real
    statements this was measured against.  A caller that needs the transaction
    band specifically can find it in the rows; a caller that guessed wrong
    here would have silently dropped whichever rows fell outside its guess.
    """
    words = deduplicate(_words_of(page))
    if not words:
        return None

    height = _median_height(words)
    tolerance = max(1.0, LINE_TOLERANCE * height) if height else 1.0
    lines = group_lines(words, tolerance)
    if len(lines) < MIN_ROWS:
        return None

    gap_threshold = max(MIN_COLUMN_GAP, COLUMN_GAP * _median_gap(lines))
    bands = line_bands(lines)

    rows: list[_Row] = []
    for line, band in zip(lines, bands):
        cells = split_cells(line, gap_threshold, band)
        if not cells:
            continue
        rows.append(
            _Row(
                values=tuple(cell.text for cell in cells),
                cells=tuple(cell.rect for cell in cells),
            )
        )

    if len(rows) < MIN_ROWS:
        return None

    bbox = _bbox_of(rows)
    if bbox is None:
        return None
    return TextRowTable(bbox=bbox, rows=tuple(rows))
