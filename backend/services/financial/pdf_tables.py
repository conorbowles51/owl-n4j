"""Read a page's tables once, so its text and its geometry cannot disagree.

The extraction pipeline builds a text chunk per table.  Adding rectangles to
that is tempting to do as a second pass -- find the tables again, take their
geometry, zip the two lists.  It must not be done that way.  The two passes
agree only for as long as they agree about *everything*, and they already
disagree about one thing: a table whose every cell is empty yields a rectangle
but no chunk.  One position out, and every value on the page is paired with its
neighbour's rectangle -- a click-through that highlights the wrong figure while
looking entirely confident.  So the chunk and the geometry are produced here
from one call over one grid, carried in one object, and the caller never holds
two lists it could get out of step.

This module is deliberately free of PyMuPDF.  It reads a small set of
attributes off whatever it is handed -- ``find_tables``, ``extract``, ``bbox``,
``rows[].cells``, ``rect``, ``rotation`` -- which is the shape a fitz ``Page``
has and which a stub can have too.  That is not tidiness.  The pipeline that
owns the real ``Page`` imports ``datetime.UTC`` and so cannot start on the
Python this repository's tests run on; judgement placed there would ship
unexercised.  Placed here it is tested, and the pipeline keeps only attribute
reads, which are the part that cannot be got subtly wrong.

A page is read for drawn geometry first and, only if that yields no table with
text in it, read again by where its words sit -- see
:mod:`services.financial.text_rows` for the measurements that made the second
pass necessary.  Which pass a table came out of is recorded as
:class:`TableSource`, kept as a separate axis from the geometry grading below
because the two vary independently and because a row inferred from spacing is a
weaker claim than one read out of a ruled cell.

Geometry degrades in three steps and the step taken is recorded, because the
difference between "this table has no clickable values" and "this run stopped
producing geometry" is invisible unless it is written down:

* :attr:`GeometrySource.cell_rectangles` -- every value that had a rectangle
  kept it.
* :attr:`GeometrySource.table_rectangle_only` -- the cell rectangles were
  absent or could not be trusted, so the table's own rectangle is kept and
  every value inside it is marked unlocated.  The reader still knows which
  table on which page a figure came from.
* :attr:`GeometrySource.unavailable` -- not even the table's rectangle
  survived.  The text is still produced.

That last point is the invariant this module is built around: **a geometry
failure never costs text**.  Geometry is an improvement on what the pipeline
does today, and an improvement that can lose evidence is not one.  Every read
that exists only to serve geometry is therefore contained, and only the two
calls that produce the text itself -- ``find_tables()`` and ``extract()`` --
are allowed to fail the page, exactly as they can today.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Sequence

from postgres.models.enums import CoordinateSpace

from services.financial.table_geometry import (
    LocatedTable,
    TableGeometryError,
    cell_value,
    locate_table,
)
from services.financial.text_rows import read_text_rows

# The chunk format below is not a choice made here.  It is the format the
# pipeline already emits and that its consumers already parse, reproduced
# exactly so that adding geometry changes nothing a reader downstream can see.
COLUMN_SEPARATOR = " | "
PAGE_MARKER = "[Page: {page_number}]"

# Measured on PyMuPDF 1.28.2: at rotation 90 the page rectangle is 792x612 and
# ``find_tables()`` reports a table box that lands inside it.  The tables come
# back in displayed coordinates, which is not the space ``get_text("words")``
# uses, and nothing in either tuple says which -- so it is stated here once,
# next to the evidence for it, rather than assumed at each call.
TABLE_COORDINATE_SPACE = CoordinateSpace.pdf_displayed

# And the recovered pass is in the *other* space.  ``read_text_rows`` builds its
# rectangles out of ``get_text("words")``, which reports unrotated coordinates
# that do not change as the page is rotated -- the opposite convention to the
# one above, on the same page, from the same library.  Both real statements this
# was measured against are at rotation 0, where the two spaces coincide exactly,
# so passing the wrong one here would have tested clean and then put every
# highlight in the wrong quarter of the first rotated page in evidence.  Hence
# two named constants rather than one shared default.
TEXT_COORDINATE_SPACE = CoordinateSpace.pdf_unrotated


class TableSource(str, Enum):
    """Which reading of the page the table came out of.

    Deliberately a separate axis from :class:`GeometrySource`.  That one says
    how much geometry survived; this says how the table was *found*, and the
    two vary independently -- a table recovered from word positions still
    yields a rectangle per cell, so it is legitimately
    ``cell_rectangles``.  Collapsing them into one enum would make a recovered
    table indistinguishable from a drawn one at exactly the moment the
    difference matters.

    And it does matter, forensically.  A row read out of a ruled cell is a
    claim the document itself makes about which figures belong together.  A row
    recovered from where the words sit is a claim *this code* makes, from
    spacing, and it can be wrong in ways the drawn reading cannot: a wide gap
    inside a merchant name splits a cell, two lines of a wrapped address merge.
    An analyst asked to rely on a figure is entitled to know which of those two
    they are looking at, and a reviewer auditing a finished report doubly so.
    """

    #: Found by ``find_tables()`` from the page's own ruled geometry.
    drawn_geometry = "drawn_geometry"
    #: Recovered by :func:`services.financial.text_rows.read_text_rows` from
    #: word positions, because the drawn pass produced nothing.
    text_alignment = "text_alignment"


class GeometrySource(str, Enum):
    """How much of a table's geometry survived, as a recorded fact.

    Ordered by decreasing usefulness.  Kept distinct from
    ``LocatedTable.unlocated_values`` because the two answer different
    questions: that counts how many values in a table lack a rectangle, which
    a reader can legitimately produce in the best case; this says which of the
    three attempts the table came out of.
    """

    cell_rectangles = "cell_rectangles"
    table_rectangle_only = "table_rectangle_only"
    unavailable = "unavailable"


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    """One table's text and its geometry, from one reading of one grid.

    The two are in the same object rather than in two lists precisely so that
    nothing downstream has to keep them in step.  ``chunk`` is never empty:
    a table that produces no text produces no ``ExtractedTable`` at all, which
    is what keeps the chunk sequence identical to the one the pipeline emits
    without any of this.
    """

    chunk: str
    table_source: TableSource
    geometry: Optional[LocatedTable]
    geometry_source: GeometrySource
    degraded_reason: Optional[str]

    def to_json(self) -> dict[str, Any]:
        """Fixed key order, for the same reason :meth:`Locator.to_json` has one.

        ``table_source`` comes first because it qualifies everything after it:
        it says what was read before the rest says how well it was located.

        ``chunk`` is not included.  It travels in the pipeline's own ``tables``
        list, and writing it twice would create a second copy that could drift
        from the first.
        """
        payload: dict[str, Any] = {
            "table_source": self.table_source.value,
            "geometry_source": self.geometry_source.value,
        }
        if self.geometry is not None:
            payload["table"] = self.geometry.to_json()
        if self.degraded_reason is not None:
            payload["degraded_reason"] = self.degraded_reason
        return payload


def _chunk(grid: Sequence[Any], page_number: int) -> Optional[str]:
    """The pipeline's own text for a table, or ``None`` if it has no text.

    Reproduces the existing rule exactly: a row is kept when any of its cells
    holds a value, empty cells inside a kept row are preserved as empty
    columns, and a table with no kept rows contributes nothing.

    That last case is the one that makes a two-pass implementation unsafe, so
    it is handled by returning ``None`` and dropping the whole table --
    geometry included -- rather than by leaving a hole in one list only.
    """
    rows: list[str] = []
    for row in grid:
        cells = [cell_value(cell) for cell in row]
        if any(cells):
            rows.append(COLUMN_SEPARATOR.join(cells))
    if not rows:
        return None
    return PAGE_MARKER.format(page_number=page_number) + "\n" + "\n".join(rows)


def _cell_rects(table: Any) -> Optional[list[Any]]:
    """The per-cell rectangles this reader offers, or ``None`` if it offers none.

    A reader without a ``rows`` attribute is not broken; it simply locates
    tables and not cells, and the caller degrades to the table rectangle.  A
    reader that has ``rows`` but cannot produce ``cells`` from them *is*
    broken, and that is worth a recorded reason rather than the same silent
    degrade, because it is the shape a library change would take.
    """
    rows = getattr(table, "rows", None)
    if rows is None:
        return None
    try:
        return [row.cells for row in rows]
    except (AttributeError, TypeError) as exc:
        raise TableGeometryError(
            f"the reader offers rows but no readable cell rectangles: {exc}"
        ) from exc


def _locate(
    *,
    table: Any,
    grid: Sequence[Any],
    page_number: int,
    space: CoordinateSpace,
    rotation: int,
    page_width: float,
    page_height: float,
) -> tuple[Optional[LocatedTable], GeometrySource, Optional[str]]:
    """Walk the three steps, returning the best geometry and why it is not better."""
    bbox = getattr(table, "bbox", None)
    if bbox is None:
        return (
            None,
            GeometrySource.unavailable,
            "the reader gave the table no rectangle of its own",
        )

    def attempt(cell_rects: Optional[Sequence[Any]]) -> LocatedTable:
        return locate_table(
            page_number=page_number,
            table_rect=bbox,
            cell_text=grid,
            cell_rects=cell_rects,
            space=space,
            rotation=rotation,
            page_width=page_width,
            page_height=page_height,
        )

    reason: Optional[str] = None
    try:
        rects = _cell_rects(table)
    except TableGeometryError as exc:
        rects = None
        reason = str(exc)

    if rects is not None:
        try:
            return attempt(rects), GeometrySource.cell_rectangles, None
        except TableGeometryError as exc:
            # Untrustworthy geometry and absent geometry end in the same place,
            # which is the whole point of retrying rather than raising: a
            # rectangle that might be wrong is worth less than no rectangle.
            reason = str(exc)

    try:
        located = attempt(None)
    except TableGeometryError as exc:
        causes = [reason, str(exc)] if reason is not None else [str(exc)]
        return None, GeometrySource.unavailable, "; ".join(causes)

    if reason is None:
        reason = "the reader offered no cell rectangles"
    return located, GeometrySource.table_rectangle_only, reason


def _extent(page: Any) -> tuple[float, float, int]:
    rect = page.rect
    return float(rect.width), float(rect.height), int(page.rotation)


def _build(
    found: Sequence[Any],
    *,
    table_source: TableSource,
    space: CoordinateSpace,
    page_number: int,
    extent_failure: Optional[str],
    rotation: int,
    page_width: float,
    page_height: float,
) -> list[ExtractedTable]:
    """Turn one pass's tables into results, text first and geometry after."""
    tables: list[ExtractedTable] = []
    for table in found:
        grid = table.extract()
        chunk = _chunk(grid, page_number)
        if chunk is None:
            continue

        if extent_failure is not None:
            tables.append(
                ExtractedTable(
                    chunk=chunk,
                    table_source=table_source,
                    geometry=None,
                    geometry_source=GeometrySource.unavailable,
                    degraded_reason=extent_failure,
                )
            )
            continue

        try:
            geometry, source, reason = _locate(
                table=table,
                grid=grid,
                page_number=page_number,
                space=space,
                rotation=rotation,
                page_width=page_width,
                page_height=page_height,
            )
        except Exception as exc:  # noqa: BLE001 - see the module docstring
            # A reader can misbehave in ways no signature describes.  Whatever
            # it did, it did while being asked for geometry, and geometry is
            # the only thing allowed to be lost for it.
            geometry, source, reason = (
                None,
                GeometrySource.unavailable,
                f"reading the geometry raised {type(exc).__name__}: {exc}",
            )

        tables.append(
            ExtractedTable(
                chunk=chunk,
                table_source=table_source,
                geometry=geometry,
                geometry_source=source,
                degraded_reason=reason,
            )
        )
    return tables


def _resolved_cells(tables: Sequence[ExtractedTable]) -> bool:
    """Whether any of these tables came back with a rectangle per value.

    This is the test of whether a reading of the page is worth preferring, and
    it is deliberately not "did it produce any text at all".  A pass that
    returns text with only a table-level rectangle has found a box and failed
    to find the cells inside it: it has made no claim about which figures
    belong together, and there is nothing there to defer to.  It has also
    produced rows an analyst cannot click through to, which in this subsystem
    is the difference between a figure that can be checked against the page and
    one that has to be taken on trust.
    """
    return any(
        table.geometry_source is GeometrySource.cell_rectangles for table in tables
    )


def _recover(page: Any) -> list[Any]:
    """The page read again by word position, or nothing if that finds nothing.

    Every failure is swallowed, including ones that would be worth shouting
    about elsewhere.  This runs only after the drawn pass has already failed to
    resolve any cells, so the alternatives here are "some rows" and "no rows"
    -- never "rows" and "an exception".  A fallback that can turn a page the
    pipeline merely found empty into a page the pipeline fails on would be a
    worse bug than the one it was added to fix.
    """
    try:
        recovered = read_text_rows(page)
    except Exception:  # noqa: BLE001 - see above
        return []
    return [recovered] if recovered is not None else []


def read_tables(page: Any, page_number: int) -> tuple[ExtractedTable, ...]:
    """Every table on a page, each with its text and as much geometry as holds.

    ``page`` is anything shaped like a fitz ``Page``.  ``page_number`` is
    1-based, matching both the marker in the text chunk and what a locator
    requires.

    The page is read for drawn geometry first, because a ruled cell is the
    document's own statement about which figures belong together and no
    inference beats it.  The page is read again by where its words sit whenever
    that first reading resolved no cells anywhere on it -- because a detector
    finding nothing is not evidence that there is nothing there.

    Note the condition: *resolved no cells*, not *produced no text*.  The
    weaker rule was written first and measured wrong.  On a 108-page digital
    card-statement set, 34 pages returned a table rectangle with no cells
    inside it, which under the weaker rule counted as a successful drawn
    reading and blocked recovery -- yielding 718 rows that no analyst could
    click through to, where reading the same pages by word position yields
    1,719 rows that every analyst can, including the account-holder line the
    drawn reading dropped entirely.  A pass that finds a box and fails to find
    the cells has made no claim about which figures belong together, so there
    is nothing there for the drawn reading's precedence to protect.

    On the other side of the measurement: a 56-page scanned subpoena response
    has no vector geometry at all, and the drawn pass returned nothing on every
    transaction page of it.

    The recovered reading is marked :attr:`TableSource.text_alignment`.  It
    replaces the drawn one rather than joining it, because two readings of the
    same page in the same list is the same doubling that
    :func:`services.financial.text_rows.deduplicate` exists to prevent -- every
    figure counted twice, in a subsystem whose output is summed.  It is taken
    only when it resolves cells the drawn pass could not, or when the drawn
    pass produced nothing at all; a page where neither reading can be located
    keeps the drawn one, since with nothing to choose between them the
    document's own reading wins by default.

    Exceptions from ``extract()`` propagate, because it is the call that
    produces the text and its failure is a page-level failure the pipeline
    already handles.  A failure of ``find_tables()`` propagates too, but only
    once recovery has also come up empty: a reader that cannot look for drawn
    tables is not a reason to discard rows that are legible without it.
    Everything else is contained -- a reader that misbehaves only when asked
    for geometry costs the geometry and nothing else.
    """
    extent_failure: Optional[str] = None
    page_width = page_height = 0.0
    rotation = 0
    try:
        page_width, page_height, rotation = _extent(page)
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        extent_failure = f"the page reports no usable extent: {exc}"

    drawn_failure: Optional[BaseException] = None
    tables: list[ExtractedTable] = []
    try:
        found = list(page.find_tables().tables)
    except Exception as exc:  # noqa: BLE001 - re-raised below if nothing replaces it
        drawn_failure = exc
    else:
        tables = _build(
            found,
            table_source=TableSource.drawn_geometry,
            space=TABLE_COORDINATE_SPACE,
            page_number=page_number,
            extent_failure=extent_failure,
            rotation=rotation,
            page_width=page_width,
            page_height=page_height,
        )

    if not _resolved_cells(tables):
        recovered = _build(
            _recover(page),
            table_source=TableSource.text_alignment,
            space=TEXT_COORDINATE_SPACE,
            page_number=page_number,
            extent_failure=extent_failure,
            rotation=rotation,
            page_width=page_width,
            page_height=page_height,
        )
        if _resolved_cells(recovered) or not tables:
            tables = recovered or tables

    if not tables and drawn_failure is not None:
        raise drawn_failure

    return tuple(tables)


def chunks_of(tables: Sequence[ExtractedTable]) -> list[str]:
    """The text chunks, in order -- what the pipeline's ``tables`` list holds."""
    return [table.chunk for table in tables]


def geometry_summary(tables: Sequence[ExtractedTable]) -> dict[str, Any]:
    """The counts that make a silent loss of geometry visible.

    A run that stops producing rectangles produces no error and no missing
    field; it produces the same documents with fewer clickable figures, which
    nobody notices.  These counts are what turn that into a number that can be
    compared between runs.

    ``by_table_source`` makes the other silent drift visible: a corpus that
    starts arriving as scans rather than digital statements moves from drawn
    geometry to recovered rows without anything failing, and the reader of a
    finished report deserves to know that the rows in it were inferred from
    spacing rather than read out of ruled cells.
    """
    located = 0
    unlocated = 0
    by_source = {source.value: 0 for source in GeometrySource}
    by_table_source = {source.value: 0 for source in TableSource}
    for table in tables:
        by_source[table.geometry_source.value] += 1
        by_table_source[table.table_source.value] += 1
        if table.geometry is None:
            continue
        located += table.geometry.located_values
        unlocated += table.geometry.unlocated_values
    return {
        "tables": len(tables),
        "located_values": located,
        "unlocated_values": unlocated,
        "by_source": by_source,
        "by_table_source": by_table_source,
    }
