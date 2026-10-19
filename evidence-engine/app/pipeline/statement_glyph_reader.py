"""A second reader for disputed money cells that does not use Tesseract.

Why this exists
---------------
When the recognised text of a scanned statement and Tesseract's crop
rereads disagree about a money cell, the cell is held
(``statement_money_verification``). Where two misreads compensate, every
printed control reconciles with both readings, so arithmetic cannot choose.
Tesseract agreeing with itself across crops is one engine's opinion repeated,
not independent proof. A tie needs a reader whose mistakes are not the same
as Tesseract's.

What this does
--------------
It reads a cell by comparing its printed glyphs with glyphs cut from the same
page: every money cell on the page that the recognised text and the crop
rereads already agree on is segmented into its characters, and each character
image becomes a labelled template. A disputed cell is segmented the same way
and each glyph is given the label of the template it correlates with best,
pixel for pixel. Same font, same print, same scan; a different method. There
is no language model, no learned weights and nothing shared with Tesseract
except the confirmed labels of the template cells.

It abstains (returns no reading) whenever the evidence is thin:

* a cell whose ink does not separate into exactly as many glyphs as it has
  printed characters is never used as a template and never read;
* a character class needs templates from at least two different cells, and
  every template must be recognised as its own label by the page's other
  templates, or the page's templates are not trusted at all;
* every glyph must match its best class with a correlation of at least
  ``MIN_SCORE`` and beat every other class by at least ``MIN_MARGIN``.

The thresholds come from leave-one-out reads of the 1,307 confirmed glyphs
on the synthetic benchmark corpus (corpus v3): a glyph's own class never
scored below 0.945 and never lost to another class, while the best *other*
class, with the glyph's own class withheld, never scored above 0.920. A score
of 0.935 therefore separates "this is a known character" from "this is the
nearest of the characters the page happens to offer". The smallest margin of
a correct read was 0.045. See
``backend/benchmarks/statement_automation/glyph_reader_evaluation.py``.

This module only reads. Whether a reading may replace a held cell is decided
by ``statement_money_verification.repair_with_second_reader``.
"""
from __future__ import annotations

import re

import numpy as np

METHOD = 'page_glyph_template_reader'
DPI = 300
# A pixel counts as ink when it is at least this dark (0 white, 1 black).
INK = 0.35
MIN_SCORE = 0.935
MIN_MARGIN = 0.05
MIN_CELLS_PER_CLASS = 2
MAX_SAMPLES_PER_CLASS = 12
SHIFT = 2


def ink(image):
    """Darkness of a greyscale PIL image as floats, 0 white to 1 black."""
    return 1 - np.asarray(image, dtype=np.float32) / 255


def segments(darkness):
    """Glyph boxes ``(x0, x1, y0, y1)`` from left to right.

    A glyph is a run of columns that contain ink; a column without ink
    separates two glyphs. Touching glyphs therefore become one segment, which
    makes the character count wrong and the cell unusable, never misread.
    """
    mask = darkness > INK
    columns = np.flatnonzero(mask.any(axis=0))
    if not len(columns):
        return []
    breaks = np.flatnonzero(np.diff(columns) > 1)
    starts = np.concatenate(([columns[0]], columns[breaks + 1]))
    ends = np.concatenate((columns[breaks] + 1, [columns[-1] + 1]))
    boxes = []
    for x0, x1 in zip(starts, ends):
        rows = np.flatnonzero(mask[:, x0:x1].any(axis=1))
        boxes.append((int(x0), int(x1), int(rows[0]), int(rows[-1]) + 1))
    return boxes


def _line_top(boxes):
    """The top of the cell's full-height glyphs, or ``None``."""
    heights = [y1 - y0 for _, _, y0, y1 in boxes]
    if not heights:
        return None
    tall = [y0 for (_, _, y0, y1), h in zip(boxes, heights) if h >= .6 * max(heights)]
    return int(np.median(tall))


class _Frame:
    """A fixed window, anchored at the line's top, that every glyph is placed in.

    Placing each glyph at its height on the printed line keeps ``.`` and
    ``-`` or ``,`` and ``.`` apart, which a tight crop of the ink would not.
    """

    def __init__(self, digit_height, widest):
        self.above = max(2, round(.35 * digit_height))
        self.height = self.above + round(1.6 * digit_height) + 2 * SHIFT
        self.width = widest + 2 * SHIFT + 4

    def place(self, darkness, box, top):
        x0, x1, _, _ = box
        if x1 - x0 > self.width - 2 * SHIFT - 2:
            return None
        frame = np.zeros((self.height, self.width), np.float32)
        left = (self.width - (x1 - x0)) // 2
        first = top - self.above
        for row in range(self.height):
            source = first + row
            if 0 <= source < darkness.shape[0]:
                frame[row, left:left + x1 - x0] = darkness[source, x0:x1]
        return frame


def _normalised(vectors):
    centred = vectors - vectors.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(centred, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return centred / norms


def _shifted(frame):
    return np.stack([np.roll(np.roll(frame, dy, axis=0), dx, axis=1).ravel()
                     for dy in range(-SHIFT, SHIFT + 1) for dx in range(-SHIFT, SHIFT + 1)])


def _cut(darkness, text):
    """``(boxes, top)`` when the cell's ink has one glyph per printed character, else ``None``."""
    characters = re.sub(r'\s+', '', text or '')
    boxes = segments(darkness)
    if not characters or len(boxes) != len(characters):
        return None
    top = _line_top(boxes)
    return (boxes, top) if top is not None else None


class PageGlyphs:
    """Templates cut from one page's confirmed cells, and the reader that uses them."""

    def __init__(self, cells):
        """``cells``: ``[(cell id, darkness array, confirmed text)]`` from one page."""
        cut = []
        for cell_id, darkness, text in cells:
            found = _cut(darkness, text)
            if found:
                cut.append((cell_id, darkness, re.sub(r'\s+', '', text), *found))
        self.cells_offered, self.cells_used = len(cells), len(cut)
        tall = [y1 - y0 for _, _, _, boxes, _ in cut for _, _, y0, y1 in boxes]
        self.digit_height = max(tall) if tall else 0
        widest = max((x1 - x0 for _, _, _, boxes, _ in cut for x0, x1, _, _ in boxes), default=0)
        self.frame = _Frame(self.digit_height, widest) if cut else None
        samples = {}
        for cell_id, darkness, characters, boxes, top in cut:
            for character, box in zip(characters, boxes):
                placed = self.frame.place(darkness, box, top)
                if placed is not None and len(samples.setdefault(character, [])) < MAX_SAMPLES_PER_CLASS:
                    samples[character].append((cell_id, placed))
        self.labels, self.owners, rows = [], [], []
        for character in sorted(samples):
            for cell_id, placed in samples[character]:
                self.labels.append(character)
                self.owners.append(cell_id)
                rows.append(placed.ravel())
        self.templates = _normalised(np.stack(rows)) if rows else None
        self.classes = {c for c in samples if len({o for o, _ in samples[c]}) >= MIN_CELLS_PER_CLASS}
        self.inconsistent = self._inconsistent_templates()

    def _inconsistent_templates(self):
        """Templates that the page's other templates do not recognise as their own label."""
        bad = []
        for index, (label, owner) in enumerate(zip(self.labels, self.owners)):
            if label not in self.classes:
                continue
            frame = self.templates[index].reshape(self.frame.height, self.frame.width)
            result = self._classify(frame, exclude_owner=owner)
            if result['character'] != label:
                bad.append(dict(label=label, read_as=result['character'], score=result['score']))
        return bad

    def _classify(self, frame, *, exclude_owner=None):
        # einsum, not a BLAS product: these matrices are tiny and BLAS would
        # start a thread pool on a shared host for no gain.
        scores = np.einsum('ij,kj->ik', _normalised(_shifted(frame)), self.templates, optimize=False).max(axis=0)
        best = {}
        for score, label, owner in zip(scores, self.labels, self.owners):
            if owner != exclude_owner and label in self.classes:
                best[label] = max(best.get(label, -1.0), float(score))
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
        if not ranked:
            return dict(character=None, score=None, runner_up=None, runner_up_score=None, scores={})
        return dict(character=ranked[0][0], score=round(ranked[0][1], 4),
            runner_up=ranked[1][0] if len(ranked) > 1 else None,
            runner_up_score=round(ranked[1][1], 4) if len(ranked) > 1 else None,
            scores={label: round(score, 4) for label, score in ranked})

    def read(self, darkness, expected_length):
        """``dict(text=..., glyphs=[...])``; ``text`` is ``None`` when the reader abstains.

        ``expected_length`` is the number of printed characters both competing
        readings give the cell; a cell whose ink separates differently is not
        read.
        """
        if self.templates is None:
            return dict(text=None, reason='no_templates', glyphs=[])
        if self.inconsistent:
            return dict(text=None, reason='templates_inconsistent', glyphs=[], inconsistent=self.inconsistent)
        boxes = segments(darkness)
        if len(boxes) != expected_length:
            return dict(text=None, reason='glyphs_not_separable', glyphs=[], glyph_count=len(boxes))
        top = _line_top(boxes)
        glyphs, characters, reason = [], [], None
        for box in boxes:
            frame = self.frame.place(darkness, box, top)
            if frame is None:
                return dict(text=None, reason='glyph_wider_than_any_template', glyphs=glyphs)
            result = self._classify(frame)
            glyphs.append(result)
            margin = (result['score'] - result['runner_up_score']
                      if result['score'] is not None and result['runner_up_score'] is not None else None)
            if result['character'] is None or result['score'] < MIN_SCORE or margin is None or margin < MIN_MARGIN:
                reason = reason or 'glyph_not_distinguished'
            characters.append(result['character'] or '?')
        if reason:
            return dict(text=None, reason=reason, glyphs=glyphs)
        return dict(text=''.join(characters), glyphs=glyphs)

    def summary(self):
        return dict(method=METHOD, dpi=DPI, ink_level=INK, minimum_score=MIN_SCORE, minimum_margin=MIN_MARGIN,
            template_cells_offered=self.cells_offered, template_cells_used=self.cells_used,
            classes=sorted(self.classes), templates=len(self.labels))
