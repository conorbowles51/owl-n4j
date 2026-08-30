"""Pair each extracted table value with the rectangle it was read from.

A table extractor hands back two things that have to be kept in step: the text
of each cell, and the rectangle each cell occupies.  Everything here exists to
make the pairing between them either correct or absent, and never confidently
wrong -- a click-through that highlights the neighbouring figure is worse than
one that highlights nothing, because the reader has no way to tell it is being
misled.  That asymmetry is the same one ``proof_class`` is built on.

This module deliberately knows nothing about PyMuPDF.  It takes plain numbers
and strings so it can be tested exhaustively without a PDF, and so the reader
that produces them can be replaced without rewriting the part that has rules
in it.  The caller does the attribute reads; the judgement lives here.

What was measured, on PyMuPDF 1.28.2, before any of this was written:

* ``find_tables()`` reports **displayed** coordinates -- at rotation 90 the
  page is 792x612 and the table box lands inside it -- whereas
  ``get_text("words")`` reports unrotated ones.  Nothing in either tuple says
  which, so the space is a required argument and has no default.
* ``len(table.rows)`` equals ``len(table.extract())``, and each row's cell
  count equals its text count, including on irregular grids.  Positional
  pairing is therefore sound -- but it is checked here anyway, because if a
  future reader breaks that correspondence the failure is silent misalignment
  of every value on the page.
* A merged cell yields its rectangle once and ``None`` in the cells it
  subsumes, and the text at those positions is ``None`` too.  Missing geometry
  and missing value coincide, so no value is orphaned by a merge, and no two
  cells share a rectangle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from postgres.models.enums import CoordinateSpace, LocatorKind

from services.financial.locators import (
    Locator,
    LocatorError,
    SourceRectangle,
    capture,
)

# A cell is expected to sit inside the table that contains it.  The tolerance
# is one typographic point, which covers a border stroke drawn on the boundary
# and the outward rounding this module's rectangles use; anything beyond it is
# a cell that does not belong to this table, which means the pairing is wrong
# rather than imprecise.
CELL_OVERFLOW_TOLERANCE_MILLIPOINTS = 1_000


class TableGeometryError(LocatorError):
    """Raised when cell geometry cannot be trusted to describe this table.

    Deliberately a single family.  The caller's response to every one of these
    is the same -- fall back to keeping the table's own rectangle and marking
    the values inside it unlocated -- so making callers enumerate causes would
    invite them to handle some and drop others.
    """


@dataclass(frozen=True, slots=True)
class LocatedCell:
    """One extracted value and where it was read from.

    ``row`` and ``column`` are the value's position in the extracted grid, not
    a claim about the table's headers.  They are kept because they are what
    lets a later stage say which column a figure came from without re-reading
    the PDF.
    """

    row: int
    column: int
    text: str
    locator: Locator

    def to_json(self) -> dict[str, Any]:
        """Fixed key order, for the same reason :meth:`Locator.to_json` has one."""
        return {
            "row": self.row,
            "column": self.column,
            "text": self.text,
            "locator": self.locator.to_json(),
        }


@dataclass(frozen=True, slots=True)
class LocatedTable:
    """A table's own rectangle, and the values found inside it.

    ``unlocated_values`` is not an error count to be swallowed.  It is the
    measure of how much of this table can be clicked through to, and it is
    carried alongside the successes so that a run which quietly stops
    producing geometry shows up as a number rather than as an absence.
    """

    page_number: int
    locator: Locator
    cells: tuple[LocatedCell, ...]
    unlocated_values: int

    @property
    def located_values(self) -> int:
        return sum(1 for cell in self.cells if cell.locator.is_clickable)

    @property
    def value_count(self) -> int:
        return len(self.cells)

    def to_json(self) -> dict[str, Any]:
        return {
            "page": self.page_number,
            "table": self.locator.to_json(),
            "values": [cell.to_json() for cell in self.cells],
            "unlocated_values": self.unlocated_values,
        }


def _text_of(cell: Any) -> str:
    """The value in a cell, or the empty string if there is none.

    Mirrors what the extraction path already does to build the text chunk.  If
    the two ever disagreed about which cells hold values, the geometry would
    describe a different set of cells than the text does, so this is written
    once and shared rather than being restated at the call site.
    """
    if cell is None:
        return ""
    return str(cell).strip()


def _require_grid(
    cell_text: Sequence[Sequence[Any]],
    cell_rects: Optional[Sequence[Sequence[Any]]],
) -> None:
    if cell_rects is None:
        return
    if len(cell_rects) != len(cell_text):
        raise TableGeometryError(
            f"{len(cell_rects)} rows of geometry for {len(cell_text)} rows of "
            "text; the two do not describe the same table"
        )
    for index, (texts, rects) in enumerate(zip(cell_text, cell_rects)):
        if len(rects) != len(texts):
            raise TableGeometryError(
                f"row {index} has {len(rects)} cell rectangles for "
                f"{len(texts)} cell values; positions cannot be paired"
            )


def _within_table(cell: SourceRectangle, table: SourceRectangle) -> bool:
    slack = CELL_OVERFLOW_TOLERANCE_MILLIPOINTS
    return (
        cell.x0 >= table.x0 - slack
        and cell.y0 >= table.y0 - slack
        and cell.x1 <= table.x1 + slack
        and cell.y1 <= table.y1 + slack
    )


def _first_overlap(
    placed: Sequence[tuple[int, int, SourceRectangle]],
) -> Optional[tuple[tuple[int, int], tuple[int, int]]]:
    """The first pair of cells that share area, or ``None`` if none do.

    Touching is not overlapping: adjacent cells in a grid share an edge, so
    the comparison is on strict interior intersection.  Sorting by the top
    edge lets the scan stop as soon as a candidate begins below the current
    cell ends, which keeps a page of several hundred cells from becoming a
    quadratic scan over all of them.
    """
    ordered = sorted(placed, key=lambda item: (item[2].y0, item[2].x0))
    for index, (row, column, rect) in enumerate(ordered):
        for other_row, other_column, other in ordered[index + 1 :]:
            if other.y0 >= rect.y1:
                break
            if min(rect.x1, other.x1) > max(rect.x0, other.x0) and min(
                rect.y1, other.y1
            ) > max(rect.y0, other.y0):
                return (row, column), (other_row, other_column)
    return None


def locate_table(
    *,
    page_number: int,
    table_rect: Iterable[float],
    cell_text: Sequence[Sequence[Any]],
    cell_rects: Optional[Sequence[Sequence[Any]]],
    space: CoordinateSpace,
    rotation: int,
    page_width: float,
    page_height: float,
) -> LocatedTable:
    """Pair every value in an extracted table with the rectangle it came from.

    ``cell_rects`` may be ``None``, meaning the reader offered no cell
    geometry.  That is not an error: the table's own rectangle still says
    which table on which page a figure came from, and each value is marked
    unlocated so the loss is counted rather than inferred from silence.  A
    caller that catches :class:`TableGeometryError` should retry with ``None``
    for exactly that reason -- untrustworthy geometry and absent geometry
    should end in the same honest place.

    Raises :class:`TableGeometryError` if the geometry offered cannot be
    trusted to describe this table.  Every check that raises is one where the
    alternative is a highlight drawn over the wrong figure.
    """
    for row_index, texts in enumerate(cell_text):
        if isinstance(texts, (str, bytes)):
            raise TableGeometryError(
                f"row {row_index} is a {type(texts).__name__}, not a row of cells"
            )

    _require_grid(cell_text, cell_rects)

    try:
        table = capture(
            page_number=page_number,
            rect=table_rect,
            space=space,
            rotation=rotation,
            page_width=page_width,
            page_height=page_height,
        )
    except LocatorError as exc:
        raise TableGeometryError(f"the table's own rectangle is unusable: {exc}") from exc

    table_locator = Locator(kind=LocatorKind.page_rectangle, rectangle=table)

    placed: list[tuple[int, int, SourceRectangle]] = []
    values: list[tuple[int, int, str, Optional[SourceRectangle]]] = []

    for row_index, texts in enumerate(cell_text):
        rects = cell_rects[row_index] if cell_rects is not None else None
        for column_index, raw in enumerate(texts):
            text = _text_of(raw)
            if not text:
                # No value here, so nothing to locate.  A merged cell's
                # subsumed positions arrive this way, with neither text nor
                # rectangle, and contribute nothing in either direction.
                continue

            raw_rect = rects[column_index] if rects is not None else None
            if raw_rect is None:
                values.append((row_index, column_index, text, None))
                continue

            try:
                rectangle = capture(
                    page_number=page_number,
                    rect=raw_rect,
                    space=space,
                    rotation=rotation,
                    page_width=page_width,
                    page_height=page_height,
                )
            except LocatorError as exc:
                raise TableGeometryError(
                    f"cell ({row_index}, {column_index}) has an unusable "
                    f"rectangle: {exc}"
                ) from exc

            if not _within_table(rectangle, table):
                raise TableGeometryError(
                    f"cell ({row_index}, {column_index}) at "
                    f"({rectangle.x0}, {rectangle.y0}, {rectangle.x1}, "
                    f"{rectangle.y1}) falls outside the table it belongs to; "
                    "the geometry does not describe this table"
                )

            placed.append((row_index, column_index, rectangle))
            values.append((row_index, column_index, text, rectangle))

    collision = _first_overlap(placed)
    if collision is not None:
        first, second = collision
        raise TableGeometryError(
            f"cells {first} and {second} share page area; a click in the "
            "overlap would resolve to either value"
        )

    cells: list[LocatedCell] = []
    unlocated = 0
    for row_index, column_index, text, rectangle in values:
        if rectangle is None:
            unlocated += 1
            locator = Locator(kind=LocatorKind.unlocated, page_number=page_number)
        else:
            locator = Locator(kind=LocatorKind.page_rectangle, rectangle=rectangle)
        cells.append(
            LocatedCell(
                row=row_index,
                column=column_index,
                text=text,
                locator=locator,
            )
        )

    return LocatedTable(
        page_number=page_number,
        locator=table_locator,
        cells=tuple(cells),
        unlocated_values=unlocated,
    )
