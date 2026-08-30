"""Tests for reading a page's tables once, with text and geometry together.

No case material appears here.  Every page is a stub shaped like a fitz
``Page`` -- ``find_tables()``, ``extract()``, ``bbox``, ``rows[].cells``,
``rect``, ``rotation`` -- because the module under test is duck-typed against
that shape precisely so it can be exercised without a PDF.

The most important test in this file is
:meth:`ChunkFidelityTests.test_chunks_match_the_pipeline_verbatim`.  It runs
the pipeline's own table-chunking code, copied verbatim below, against this
module's, over grids chosen to be awkward.  The point of the whole exercise is
to add geometry *without changing the text*, and the only way to know the text
is unchanged is to keep a copy of what it used to be and compare.
"""
import json
import unittest

try:  # pragma: no cover - exercised by whether RealPageTests below skips
    import fitz

    _PYMUPDF = True
except Exception:  # pragma: no cover
    _PYMUPDF = False

from postgres.models.enums import LocatorKind
from services.financial.pdf_tables import (
    ExtractedTable,
    GeometrySource,
    chunks_of,
    geometry_summary,
    read_tables,
)

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0

# A 2x2 grid at x in {100, 250, 400} and y in {100, 140, 180}.
GRID = [["Name", "Amount"], ["Alice", "25000"]]
RECTS = [
    [(100.0, 100.0, 250.0, 140.0), (250.0, 100.0, 400.0, 140.0)],
    [(100.0, 140.0, 250.0, 180.0), (250.0, 140.0, 400.0, 180.0)],
]
BBOX = (100.0, 100.0, 400.0, 180.0)

# A second, lower table, so that a mis-pairing between text and geometry shows
# up as a rectangle in the wrong place rather than as an error.
LOWER_GRID = [["Bob", "700"]]
LOWER_RECTS = [[(100.0, 300.0, 250.0, 340.0), (250.0, 300.0, 400.0, 340.0)]]
LOWER_BBOX = (100.0, 300.0, 400.0, 340.0)


def pipeline_chunks(extracted_tables, page_number):
    """The pipeline's table chunking as it stands today, copied verbatim.

    Taken from ``_extract_native_tables`` in
    ``evidence-engine/app/pipeline/pdf_extraction.py`` with only the fitz call
    removed, so that the comparison below is against the real rule rather than
    against a restatement of it that could drift in the same direction as the
    code it is meant to check.
    """
    table_chunks = []
    for extracted in extracted_tables:
        rows = []
        for row in extracted:
            cells = [str(cell).strip() if cell is not None else "" for cell in row]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            table_chunks.append(f"[Page: {page_number}]\n" + "\n".join(rows))
    return table_chunks


class StubRow:
    def __init__(self, cells):
        self.cells = cells


class StubTable:
    """A table shaped like PyMuPDF's, with each part independently removable.

    ``rows`` is only built when rectangles are supplied, because a reader that
    locates tables but not cells is a case the module has to handle and the
    stub has to be able to express.
    """

    def __init__(self, grid, rects=None, bbox=BBOX, has_rows=None):
        self._grid = grid
        self.bbox = bbox
        if has_rows is None:
            has_rows = rects is not None
        if has_rows:
            self.rows = [StubRow(row) for row in (rects or [])]

    def extract(self):
        return self._grid


class StubTables:
    def __init__(self, tables):
        self.tables = tables


class StubRect:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class StubPage:
    def __init__(self, tables, width=PAGE_WIDTH, height=PAGE_HEIGHT, rotation=0):
        self._tables = tables
        self.rect = StubRect(width, height)
        self.rotation = rotation

    def find_tables(self):
        return StubTables(self._tables)


def only(page, page_number=1):
    tables = read_tables(page, page_number)
    assert len(tables) == 1, f"expected one table, got {len(tables)}"
    return tables[0]


class ChunkFidelityTests(unittest.TestCase):
    """The text must be byte-identical to what the pipeline emits today."""

    GRIDS = [
        GRID,
        # A None cell, which the pipeline renders as an empty column.
        [["Alice", None], ["Bob", "700"]],
        # A wholly empty row between two full ones: dropped, not blanked.
        [["Alice", "25000"], ["", ""], ["Bob", "700"]],
        # Whitespace is not a value.
        [["  ", "\t"], ["Bob", "700"]],
        # Non-string cells are stringified.
        [[1, 2.5], [True, None]],
        # A row of a single empty cell.
        [[""], ["x"]],
        # Leading and trailing whitespace is stripped inside a kept row.
        [["  Alice  ", " 25000 "]],
    ]

    def test_chunks_match_the_pipeline_verbatim(self):
        for index, grid in enumerate(self.GRIDS):
            with self.subTest(grid=index):
                page = StubPage([StubTable(grid, RECTS if grid is GRID else None)])
                self.assertEqual(
                    chunks_of(read_tables(page, 4)),
                    pipeline_chunks([grid], 4),
                )

    def test_the_documented_contract_string_is_reproduced(self):
        # The exact assertion evidence-engine's own test makes, so that a
        # change to the format fails here before it fails there.
        page = StubPage([StubTable(GRID, RECTS)])
        self.assertEqual(
            chunks_of(read_tables(page, 1)),
            ["[Page: 1]\nName | Amount\nAlice | 25000"],
        )

    def test_a_table_with_no_values_contributes_nothing(self):
        page = StubPage([StubTable([["", ""], [None, "  "]], RECTS)])
        self.assertEqual(read_tables(page, 1), ())

    def test_an_empty_table_does_not_shift_the_pairing(self):
        # The desync this module exists to prevent: if the valueless table in
        # the middle produced geometry, the lower table's text would be paired
        # with the middle table's rectangle and every figure would highlight
        # the wrong thing.
        page = StubPage(
            [
                StubTable(GRID, RECTS),
                StubTable([["", ""]], RECTS),
                StubTable(LOWER_GRID, LOWER_RECTS, bbox=LOWER_BBOX),
            ]
        )
        tables = read_tables(page, 1)
        self.assertEqual(len(tables), 2)
        self.assertIn("Alice", tables[0].chunk)
        self.assertIn("Bob", tables[1].chunk)
        self.assertEqual(
            tables[1].geometry.locator.rectangle.y0,
            300_000,
        )

    def test_chunks_of_preserves_order(self):
        page = StubPage(
            [
                StubTable(LOWER_GRID, LOWER_RECTS, bbox=LOWER_BBOX),
                StubTable(GRID, RECTS),
            ]
        )
        chunks = chunks_of(read_tables(page, 2))
        self.assertEqual(len(chunks), 2)
        self.assertIn("Bob", chunks[0])
        self.assertIn("Alice", chunks[1])


class FullGeometryTests(unittest.TestCase):
    def test_every_value_keeps_its_rectangle(self):
        table = only(StubPage([StubTable(GRID, RECTS)]))
        self.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
        self.assertIsNone(table.degraded_reason)
        self.assertEqual(table.geometry.value_count, 4)
        self.assertEqual(table.geometry.located_values, 4)
        self.assertEqual(table.geometry.unlocated_values, 0)

    def test_the_rectangle_is_the_cell_the_value_was_read_from(self):
        table = only(StubPage([StubTable(GRID, RECTS)]))
        by_position = {(c.row, c.column): c for c in table.geometry.cells}
        alice = by_position[(1, 0)]
        self.assertEqual(alice.text, "Alice")
        self.assertEqual(alice.locator.rectangle.x0, 100_000)
        self.assertEqual(alice.locator.rectangle.y0, 140_000)
        self.assertEqual(alice.locator.rectangle.x1, 250_000)
        self.assertEqual(alice.locator.rectangle.y1, 180_000)

    def test_a_merged_cell_orphans_no_value(self):
        # A merged cell yields its rectangle once and None in the positions it
        # subsumes, where the text is None too.
        grid = [["Name", "Amount"], ["Alice", None]]
        rects = [
            [(100.0, 100.0, 250.0, 140.0), (250.0, 100.0, 400.0, 140.0)],
            [(100.0, 140.0, 250.0, 180.0), None],
        ]
        table = only(StubPage([StubTable(grid, rects)]))
        self.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
        self.assertEqual(table.geometry.value_count, 3)
        self.assertEqual(table.geometry.unlocated_values, 0)

    def test_a_rotated_page_reports_its_displayed_extent(self):
        # find_tables() reports displayed coordinates, so at rotation 90 the
        # extent stored with the rectangle is the rotated one -- 792 wide, not
        # 612.  Rotation itself is not stored: capture consumes it, and in
        # displayed space it has nothing to convert.
        page = StubPage(
            [StubTable(GRID, RECTS)], width=PAGE_HEIGHT, height=PAGE_WIDTH, rotation=90
        )
        table = only(page)
        self.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
        self.assertEqual(table.geometry.locator.rectangle.page_width, 792_000)
        self.assertEqual(table.geometry.locator.rectangle.page_height, 612_000)

    def test_a_rotated_table_is_read_as_already_displayed(self):
        """The coordinate space this module chooses, pinned by a case that can tell.

        At rotation 0 the displayed and unrotated spaces coincide, so every
        other test here passes under either choice -- which was found by
        mutation, not by reading.  A quarter turn is exactly where the two
        diverge, and PyMuPDF was measured reporting displayed coordinates, so
        the rectangle must arrive unchanged rather than being turned a second
        time.
        """
        page = StubPage(
            [StubTable(GRID, RECTS)], width=PAGE_HEIGHT, height=PAGE_WIDTH, rotation=90
        )
        table = only(page)
        self.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
        self.assertEqual(
            (
                table.geometry.locator.rectangle.x0,
                table.geometry.locator.rectangle.y0,
                table.geometry.locator.rectangle.x1,
                table.geometry.locator.rectangle.y1,
            ),
            (100_000, 100_000, 400_000, 180_000),
        )
        alice = {(c.row, c.column): c for c in table.geometry.cells}[(1, 0)]
        self.assertEqual(alice.text, "Alice")
        self.assertEqual(
            (
                alice.locator.rectangle.x0,
                alice.locator.rectangle.y0,
                alice.locator.rectangle.x1,
                alice.locator.rectangle.y1,
            ),
            (100_000, 140_000, 250_000, 180_000),
        )

    def test_an_illegal_rotation_degrades_rather_than_raising(self):
        # A reader reporting a rotation no PDF can have is a reader that
        # cannot be trusted about coordinates either, but it is not a reason
        # to lose the text.
        page = StubPage([StubTable(GRID, RECTS)], rotation=45)
        table = only(page)
        self.assertEqual(table.geometry_source, GeometrySource.unavailable)
        self.assertIn("rotation 45", table.degraded_reason)
        self.assertEqual(table.chunk, "[Page: 1]\nName | Amount\nAlice | 25000")

    def test_the_page_number_reaches_the_locator(self):
        table = only(StubPage([StubTable(GRID, RECTS)]), page_number=7)
        self.assertEqual(table.geometry.page_number, 7)
        self.assertEqual(table.geometry.locator.rectangle.page_number, 7)
        self.assertIn("[Page: 7]", table.chunk)


class DegradationTests(unittest.TestCase):
    def test_a_reader_without_cell_rectangles_keeps_the_table_rectangle(self):
        table = only(StubPage([StubTable(GRID)]))
        self.assertEqual(table.geometry_source, GeometrySource.table_rectangle_only)
        self.assertEqual(table.degraded_reason, "the reader offered no cell rectangles")
        self.assertEqual(table.geometry.value_count, 4)
        self.assertEqual(table.geometry.located_values, 0)
        self.assertEqual(table.geometry.unlocated_values, 4)
        self.assertEqual(table.geometry.locator.rectangle.x0, 100_000)

    def test_untrustworthy_cell_rectangles_degrade_with_their_reason(self):
        # One cell sits outside the table it claims to belong to.  Keeping it
        # would draw a highlight over something else on the page.
        rects = [
            [(100.0, 100.0, 250.0, 140.0), (250.0, 100.0, 400.0, 140.0)],
            [(100.0, 140.0, 250.0, 180.0), (500.0, 600.0, 560.0, 640.0)],
        ]
        table = only(StubPage([StubTable(GRID, rects)]))
        self.assertEqual(table.geometry_source, GeometrySource.table_rectangle_only)
        self.assertIn("falls outside the table", table.degraded_reason)
        self.assertEqual(table.geometry.unlocated_values, 4)

    def test_overlapping_cells_degrade_rather_than_resolve_ambiguously(self):
        rects = [
            [(100.0, 100.0, 250.0, 140.0), (200.0, 100.0, 400.0, 140.0)],
            [(100.0, 140.0, 250.0, 180.0), (250.0, 140.0, 400.0, 180.0)],
        ]
        table = only(StubPage([StubTable(GRID, rects)]))
        self.assertEqual(table.geometry_source, GeometrySource.table_rectangle_only)
        self.assertIn("share page area", table.degraded_reason)

    def test_a_mismatched_grid_degrades_with_its_reason(self):
        rects = [[(100.0, 100.0, 250.0, 140.0)], [(100.0, 140.0, 250.0, 180.0)]]
        table = only(StubPage([StubTable(GRID, rects)]))
        self.assertEqual(table.geometry_source, GeometrySource.table_rectangle_only)
        self.assertIn("cannot be paired", table.degraded_reason)

    def test_rows_without_readable_cells_are_reported_not_swallowed(self):
        class Broken:
            @property
            def cells(self):
                raise AttributeError("no cells here")

        table_stub = StubTable(GRID)
        table_stub.rows = [Broken(), Broken()]
        table = only(StubPage([table_stub]))
        self.assertEqual(table.geometry_source, GeometrySource.table_rectangle_only)
        self.assertIn("no readable cell rectangles", table.degraded_reason)

    def test_a_table_without_a_rectangle_still_yields_its_text(self):
        table = only(StubPage([StubTable(GRID, RECTS, bbox=None)]))
        self.assertEqual(table.geometry_source, GeometrySource.unavailable)
        self.assertIsNone(table.geometry)
        self.assertEqual(table.chunk, "[Page: 1]\nName | Amount\nAlice | 25000")
        self.assertIn("no rectangle of its own", table.degraded_reason)

    def test_a_table_rectangle_off_the_page_yields_text_and_both_reasons(self):
        # The cell rectangles fail first, then the table rectangle fails too.
        # Both causes are kept: either alone would misdescribe the run.
        bad = (5_000.0, 6_000.0, 5_100.0, 6_100.0)
        table = only(StubPage([StubTable(GRID, RECTS, bbox=bad)]))
        self.assertEqual(table.geometry_source, GeometrySource.unavailable)
        self.assertIsNone(table.geometry)
        self.assertIn("Alice", table.chunk)
        self.assertIn(";", table.degraded_reason)
        self.assertIn("does not meet the page", table.degraded_reason)

    def test_a_page_without_extent_yields_text_for_every_table(self):
        page = StubPage([StubTable(GRID, RECTS), StubTable(LOWER_GRID, LOWER_RECTS)])
        page.rect = StubRect(0.0, 0.0)
        tables = read_tables(page, 1)
        self.assertEqual(len(tables), 2)
        for table in tables:
            self.assertEqual(table.geometry_source, GeometrySource.unavailable)
            self.assertIsNone(table.geometry)
        self.assertEqual(chunks_of(tables), pipeline_chunks([GRID, LOWER_GRID], 1))

    def test_a_page_whose_rect_raises_yields_text_for_every_table(self):
        class NoRect(StubPage):
            @property
            def rect(self):
                raise RuntimeError("rect unavailable")

            @rect.setter
            def rect(self, value):
                pass

        page = NoRect([StubTable(GRID, RECTS)])
        table = only(page)
        self.assertEqual(table.geometry_source, GeometrySource.unavailable)
        self.assertIn("no usable extent", table.degraded_reason)
        self.assertIn("Alice", table.chunk)

    def test_an_unexpected_geometry_failure_costs_only_the_geometry(self):
        class Hostile(StubTable):
            @property
            def bbox(self):
                raise ValueError("boom")

            @bbox.setter
            def bbox(self, value):
                pass

        table = only(StubPage([Hostile(GRID, RECTS)]))
        self.assertEqual(table.geometry_source, GeometrySource.unavailable)
        self.assertIsNone(table.geometry)
        self.assertIn("ValueError", table.degraded_reason)
        self.assertIn("boom", table.degraded_reason)
        self.assertEqual(table.chunk, "[Page: 1]\nName | Amount\nAlice | 25000")

    def test_a_string_row_degrades_rather_than_pairing_characters(self):
        table = only(StubPage([StubTable([["Bob", "700"], "oops"], None)]))
        self.assertEqual(table.geometry_source, GeometrySource.unavailable)
        self.assertIn("not a row of cells", table.degraded_reason)


class PageFailureTests(unittest.TestCase):
    """Failures that cost the text are page-level, and still are."""

    def test_find_tables_failure_propagates(self):
        class NoTables(StubPage):
            def find_tables(self):
                raise RuntimeError("no tables")

        with self.assertRaises(RuntimeError):
            read_tables(NoTables([]), 1)

    def test_extract_failure_propagates(self):
        class NoExtract(StubTable):
            def extract(self):
                raise RuntimeError("no extract")

        with self.assertRaises(RuntimeError):
            read_tables(StubPage([NoExtract(GRID, RECTS)]), 1)


class SerialisationTests(unittest.TestCase):
    def test_full_geometry_serialises_with_a_fixed_key_order(self):
        table = only(StubPage([StubTable(GRID, RECTS)]))
        payload = table.to_json()
        self.assertEqual(list(payload), ["geometry_source", "table"])
        self.assertEqual(payload["geometry_source"], "cell_rectangles")
        self.assertEqual(payload["table"]["page"], 1)

    def test_a_degraded_table_records_why(self):
        payload = only(StubPage([StubTable(GRID)])).to_json()
        self.assertEqual(
            list(payload), ["geometry_source", "table", "degraded_reason"]
        )
        self.assertEqual(payload["geometry_source"], "table_rectangle_only")

    def test_an_unavailable_table_carries_no_geometry_key(self):
        payload = only(StubPage([StubTable(GRID, RECTS, bbox=None)])).to_json()
        self.assertEqual(list(payload), ["geometry_source", "degraded_reason"])

    def test_the_chunk_is_not_duplicated_into_the_payload(self):
        # It travels in the pipeline's own tables list.  A second copy could
        # drift from the first, and then neither would be authoritative.
        payload = only(StubPage([StubTable(GRID, RECTS)])).to_json()
        self.assertNotIn("chunk", json.dumps(payload))
        self.assertNotIn("Alice | 25000", json.dumps(payload))

    def test_the_payload_is_json_serialisable(self):
        page = StubPage([StubTable(GRID, RECTS), StubTable(LOWER_GRID)])
        encoded = json.dumps([t.to_json() for t in read_tables(page, 1)])
        self.assertIn("cell_rectangles", encoded)
        self.assertIn("table_rectangle_only", encoded)

    def test_unlocated_values_are_marked_as_such(self):
        table = only(StubPage([StubTable(GRID)]))
        kinds = {cell.locator.kind for cell in table.geometry.cells}
        self.assertEqual(kinds, {LocatorKind.unlocated})


class SummaryTests(unittest.TestCase):
    def test_counts_separate_located_from_unlocated(self):
        page = StubPage(
            [
                StubTable(GRID, RECTS),
                StubTable(LOWER_GRID, None, bbox=LOWER_BBOX),
                StubTable(GRID, RECTS, bbox=None),
            ]
        )
        summary = geometry_summary(read_tables(page, 1))
        self.assertEqual(summary["tables"], 3)
        self.assertEqual(summary["located_values"], 4)
        self.assertEqual(summary["unlocated_values"], 2)
        self.assertEqual(
            summary["by_source"],
            {
                "cell_rectangles": 1,
                "table_rectangle_only": 1,
                "unavailable": 1,
            },
        )

    def test_every_source_appears_even_at_zero(self):
        # A source that vanishes from the payload when it stops occurring is
        # the shape a silent regression takes: nothing to compare against.
        summary = geometry_summary(read_tables(StubPage([StubTable(GRID, RECTS)]), 1))
        self.assertEqual(
            set(summary["by_source"]), {s.value for s in GeometrySource}
        )

    def test_a_page_with_no_tables_summarises_to_zero(self):
        summary = geometry_summary(read_tables(StubPage([]), 1))
        self.assertEqual(summary["tables"], 0)
        self.assertEqual(summary["located_values"], 0)
        self.assertEqual(summary["unlocated_values"], 0)


class TypeTests(unittest.TestCase):
    def test_extracted_tables_are_immutable(self):
        table = only(StubPage([StubTable(GRID, RECTS)]))
        with self.assertRaises(Exception):
            table.chunk = "something else"

    def test_read_tables_returns_a_tuple(self):
        self.assertIsInstance(read_tables(StubPage([StubTable(GRID, RECTS)]), 1), tuple)

    def test_the_result_is_an_extracted_table(self):
        self.assertIsInstance(only(StubPage([StubTable(GRID, RECTS)])), ExtractedTable)


@unittest.skipUnless(_PYMUPDF, "PyMuPDF not installed; the duck-typing is unverified")
class RealPageTests(unittest.TestCase):
    """The one thing every other test in this file is incapable of showing.

    Everything above runs against a stub, so together they prove only that this
    module is self-consistent with an idea of what a fitz ``Page`` looks like.
    Whether that idea is correct -- whether ``find_tables()``, ``.tables``,
    ``.extract()``, ``.bbox``, ``.rows[].cells``, ``page.rect`` and
    ``page.rotation`` are the attributes PyMuPDF actually offers, in the units
    and the coordinate space assumed -- is not a question a stub can answer,
    because the stub was written from the same assumption as the code.

    So this builds a real ruled table with real drawn lines and real inserted
    text, and reads it with the real library.  The coordinates below are not
    aspirations; they were measured from PyMuPDF 1.28.2 and are asserted exactly
    so that a library change that moves them fails here rather than silently
    relocating every figure a reader is asked to trust.
    """

    # The drawn grid: three verticals, four horizontals, six cells of text.
    XS = [100.0, 250.0, 400.0]
    YS = [100.0, 140.0, 180.0, 220.0]
    LABELS = [["Name", "Amount"], ["Alice", "25000"], ["Bob", "700"]]

    def build(self, rotation):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        for x in self.XS:
            page.draw_line((x, self.YS[0]), (x, self.YS[-1]))
        for y in self.YS:
            page.draw_line((self.XS[0], y), (self.XS[-1], y))
        for r in range(3):
            for c in range(2):
                page.insert_text(
                    (self.XS[c] + 6, self.YS[r] + 26), self.LABELS[r][c], fontsize=11
                )
        if rotation:
            page.set_rotation(rotation)
        return doc, page

    def test_an_upright_page_locates_every_value_where_it_was_drawn(self):
        doc, page = self.build(0)
        try:
            tables = read_tables(page, 1)
            self.assertEqual(len(tables), 1)
            table = tables[0]
            self.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
            self.assertIsNone(table.degraded_reason)
            self.assertEqual(
                table.chunk, "[Page: 1]\nName | Amount\nAlice | 25000\nBob | 700"
            )
            self.assertEqual(table.geometry.located_values, 6)
            self.assertEqual(table.geometry.unlocated_values, 0)

            rect = table.geometry.locator.rectangle
            self.assertEqual(
                (rect.x0, rect.y0, rect.x1, rect.y1),
                (100_000, 100_000, 400_000, 220_000),
            )
            self.assertEqual((rect.page_width, rect.page_height), (612_000, 792_000))

            # Every cell lands on the grid that was drawn, which is the claim
            # the whole feature rests on: a rectangle a reader can be pointed at.
            by_position = {(c.row, c.column): c for c in table.geometry.cells}
            bob = by_position[(2, 0)]
            self.assertEqual(bob.text, "Bob")
            r = bob.locator.rectangle
            self.assertEqual(
                (r.x0, r.y0, r.x1, r.y1), (100_000, 180_000, 250_000, 220_000)
            )
        finally:
            doc.close()

    def test_a_rotated_page_is_read_in_the_space_it_is_displayed_in(self):
        """The measurement behind ``TABLE_COORDINATE_SPACE``, taken from the library.

        PyMuPDF reports table and cell rectangles already turned -- the table
        below sits at x 572..692 on a page that is 792 wide, coordinates that
        exist only after the quarter turn.  Converting them again as though they
        were unrotated would put every figure somewhere the reader is not
        looking, which is why the module declares the displayed space and why
        that declaration is asserted here against the library rather than
        against a stub built from the same belief.
        """
        doc, page = self.build(90)
        try:
            tables = read_tables(page, 1)
            self.assertEqual(len(tables), 1)
            table = tables[0]
            self.assertEqual(table.geometry_source, GeometrySource.cell_rectangles)
            self.assertIsNone(table.degraded_reason)

            rect = table.geometry.locator.rectangle
            self.assertEqual((rect.page_width, rect.page_height), (792_000, 612_000))
            self.assertEqual(
                (rect.x0, rect.y0, rect.x1, rect.y1),
                (572_000, 100_000, 692_000, 400_000),
            )
            # Turned coordinates on a turned page still fall on the page.
            self.assertLessEqual(rect.x1, rect.page_width)
            self.assertLessEqual(rect.y1, rect.page_height)

            # The grid is transposed by the rotation -- and the point is that
            # the text is transposed the same way, so a value and its rectangle
            # are still the same cell.  That agreement, not the layout, is what
            # reading text and geometry in one pass buys.
            self.assertEqual(
                table.chunk, "[Page: 1]\nBob | Alice | Name\n700 | 25000 | Amount"
            )
            by_position = {(c.row, c.column): c for c in table.geometry.cells}
            bob = by_position[(0, 0)]
            self.assertEqual(bob.text, "Bob")
            r = bob.locator.rectangle
            self.assertEqual(
                (r.x0, r.y0, r.x1, r.y1), (572_000, 100_000, 612_000, 250_000)
            )
        finally:
            doc.close()

    def test_a_real_page_without_tables_costs_nothing(self):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((100.0, 100.0), "Prose, with no ruled table on the page.")
        try:
            tables = read_tables(page, 1)
            self.assertEqual(tables, ())
            self.assertEqual(chunks_of(tables), [])
            self.assertEqual(geometry_summary(tables)["tables"], 0)
        finally:
            doc.close()


if __name__ == "__main__":
    unittest.main()
