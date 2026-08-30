"""Tests for pairing extracted table values with their rectangles.

No case material appears here.  Every table is synthetic, and the coordinates
are chosen to make the arithmetic checkable by hand.

One test, :meth:`RotationTests.test_unrotated_cells_match_measured_pymupdf`,
carries numbers that were measured rather than derived: they are what PyMuPDF
1.28.2 actually returned for the same table on a page at rotation 90.  It is
the only check here that the rotation arithmetic agrees with the library whose
output it exists to interpret.
"""
import json
import unittest

from postgres.models.enums import CoordinateSpace, LocatorKind
from services.financial.table_geometry import (
    CELL_OVERFLOW_TOLERANCE_MILLIPOINTS,
    LocatedTable,
    TableGeometryError,
    locate_table,
)

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0

# A 3x2 grid at x in {100, 250, 400} and y in {100, 140, 180, 220}.
GRID_TEXT = [["r0c0", "r0c1"], ["r1c0", "r1c1"], ["r2c0", "r2c1"]]
GRID_RECTS = [
    [(100.0, 100.0, 250.0, 140.0), (250.0, 100.0, 400.0, 140.0)],
    [(100.0, 140.0, 250.0, 180.0), (250.0, 140.0, 400.0, 180.0)],
    [(100.0, 180.0, 250.0, 220.0), (250.0, 180.0, 400.0, 220.0)],
]
GRID_BBOX = (100.0, 100.0, 400.0, 220.0)


def _locate(**overrides):
    kwargs = {
        "page_number": 1,
        "table_rect": GRID_BBOX,
        "cell_text": GRID_TEXT,
        "cell_rects": GRID_RECTS,
        "space": CoordinateSpace.pdf_displayed,
        "rotation": 0,
        "page_width": PAGE_WIDTH,
        "page_height": PAGE_HEIGHT,
    }
    kwargs.update(overrides)
    return locate_table(**kwargs)


class PairingTests(unittest.TestCase):
    def test_every_value_gets_its_own_rectangle(self):
        table = _locate()
        self.assertEqual(table.value_count, 6)
        self.assertEqual(table.located_values, 6)
        self.assertEqual(table.unlocated_values, 0)
        self.assertTrue(table.locator.is_clickable)

    def test_each_value_is_paired_with_the_rectangle_beside_it(self):
        """The pairing itself, not just the counts.

        Every other test here would pass if the rectangles were handed out in
        the wrong order, because the number of them would still be right.
        This one asserts that ``r1c0`` carries the rectangle that sits in row
        one, column zero, which is the only thing the feature is actually for.
        """
        table = _locate()
        by_text = {cell.text: cell for cell in table.cells}
        self.assertEqual(
            [by_text["r1c0"].row, by_text["r1c0"].column], [1, 0]
        )
        self.assertEqual(
            by_text["r1c0"].locator.to_json()["rect"],
            [100_000, 140_000, 250_000, 180_000],
        )
        self.assertEqual(
            by_text["r2c1"].locator.to_json()["rect"],
            [250_000, 180_000, 400_000, 220_000],
        )

    def test_cells_come_back_in_reading_order(self):
        table = _locate()
        self.assertEqual(
            [(cell.row, cell.column) for cell in table.cells],
            [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)],
        )

    def test_the_page_number_reaches_every_cell(self):
        """Captured on page 9, because everything else here uses page 1.

        A pairing that hardcoded the page would satisfy the rest of this file
        while sending every click-through in a long statement to its first
        page.
        """
        table = _locate(page_number=9)
        self.assertEqual(table.page_number, 9)
        self.assertEqual(table.locator.page, 9)
        self.assertEqual({cell.locator.page for cell in table.cells}, {9})

    def test_an_empty_table_locates_nothing_and_does_not_fail(self):
        table = _locate(cell_text=[[], []], cell_rects=[[], []])
        self.assertEqual(table.cells, ())
        self.assertEqual(table.unlocated_values, 0)
        self.assertTrue(table.locator.is_clickable)


class AbsentGeometryTests(unittest.TestCase):
    def test_a_merged_cell_orphans_no_value(self):
        """A merge yields the rectangle once and ``None`` in the cells it
        subsumes -- and ``None`` text at those same positions, as measured.
        So the subsumed positions hold no value and contribute nothing, rather
        than becoming values with no home."""
        table = _locate(
            cell_text=[["MERGED", None], ["r1c0", "r1c1"], ["r2c0", "r2c1"]],
            cell_rects=[
                [(100.0, 100.0, 400.0, 140.0), None],
                GRID_RECTS[1],
                GRID_RECTS[2],
            ],
        )
        self.assertEqual(table.value_count, 5)
        self.assertEqual(table.unlocated_values, 0)
        self.assertEqual(
            table.cells[0].locator.to_json()["rect"],
            [100_000, 100_000, 400_000, 140_000],
        )

    def test_a_value_with_no_rectangle_is_counted_not_dropped(self):
        """The value survives; only its position is lost.

        Dropping it would make the table look complete and quietly shrink the
        evidence.  Marking it ``unlocated`` keeps the figure and makes the
        loss countable, which is what turns a reader that stops producing
        geometry into a number somebody can see.
        """
        table = _locate(
            cell_rects=[
                [GRID_RECTS[0][0], None],
                GRID_RECTS[1],
                GRID_RECTS[2],
            ],
        )
        self.assertEqual(table.value_count, 6)
        self.assertEqual(table.located_values, 5)
        self.assertEqual(table.unlocated_values, 1)
        orphan = table.cells[1]
        self.assertEqual(orphan.text, "r0c1")
        self.assertIs(orphan.locator.kind, LocatorKind.unlocated)
        self.assertEqual(orphan.locator.page, 1)
        self.assertFalse(orphan.locator.is_clickable)

    def test_no_cell_geometry_at_all_keeps_the_table_rectangle(self):
        """The degrade a caller falls back to when geometry cannot be trusted.

        Untrustworthy geometry and absent geometry have to end in the same
        place, or a caller would be tempted to keep the suspect rectangles
        rather than lose the table entirely.
        """
        table = _locate(cell_rects=None)
        self.assertEqual(table.value_count, 6)
        self.assertEqual(table.located_values, 0)
        self.assertEqual(table.unlocated_values, 6)
        self.assertTrue(table.locator.is_clickable)
        self.assertEqual(
            {cell.locator.kind for cell in table.cells}, {LocatorKind.unlocated}
        )

    def test_a_blank_value_is_not_a_value(self):
        for blank in ("", "   ", "\n\t "):
            with self.subTest(blank=repr(blank)):
                table = _locate(
                    cell_text=[[blank, "kept"], ["a", "b"], ["c", "d"]],
                )
                self.assertEqual(table.value_count, 5)
                self.assertNotIn("", [cell.text for cell in table.cells])

    def test_a_value_is_stored_stripped(self):
        table = _locate(cell_text=[["  1,234.00  ", "b"], ["c", "d"], ["e", "f"]])
        self.assertEqual(table.cells[0].text, "1,234.00")

    def test_a_non_string_value_is_coerced_not_refused(self):
        table = _locate(cell_text=[[1234, 0], ["c", "d"], ["e", "f"]])
        self.assertEqual([c.text for c in table.cells[:2]], ["1234", "0"])


class MisalignmentTests(unittest.TestCase):
    """The checks that exist because a wrong highlight beats no highlight only
    in the sense that it is worse."""

    def test_a_different_number_of_rows_is_refused(self):
        with self.assertRaisesRegex(TableGeometryError, "same table"):
            _locate(cell_rects=GRID_RECTS[:2])

    def test_a_different_number_of_cells_in_a_row_is_refused(self):
        with self.assertRaisesRegex(TableGeometryError, "cannot be paired"):
            _locate(
                cell_rects=[GRID_RECTS[0], [GRID_RECTS[1][0]], GRID_RECTS[2]],
            )

    def test_a_row_given_as_a_string_is_refused(self):
        """Otherwise a string row iterates character by character and every
        letter becomes a value with a plausible-looking rectangle."""
        with self.assertRaisesRegex(TableGeometryError, "not a row of cells"):
            _locate(cell_text=["r0c0", ["a", "b"], ["c", "d"]], cell_rects=None)

    def test_a_cell_outside_its_table_is_refused(self):
        with self.assertRaisesRegex(TableGeometryError, "outside the table"):
            _locate(
                cell_rects=[
                    [(100.0, 100.0, 250.0, 140.0), (450.0, 300.0, 500.0, 340.0)],
                    GRID_RECTS[1],
                    GRID_RECTS[2],
                ],
            )

    def test_a_cell_outside_the_table_is_refused_in_every_direction(self):
        """All four bounds, separately.

        The test above puts a cell down and to the right of the table, which
        exercises only the two upper bounds; the lower ones stayed unchecked
        until mutation testing deleted them and nothing failed.  One cell in a
        one-cell table isolates containment from the overlap rule, so each
        direction fails for the reason it is named for.
        """
        table_rect = (100.0, 100.0, 250.0, 140.0)
        for direction, rect in (
            ("left of it", (90.0, 100.0, 95.0, 140.0)),
            ("above it", (100.0, 90.0, 250.0, 95.0)),
            ("right of it", (405.0, 100.0, 500.0, 140.0)),
            ("below it", (100.0, 225.0, 250.0, 300.0)),
        ):
            with self.subTest(direction=direction):
                with self.assertRaisesRegex(TableGeometryError, "outside the table"):
                    _locate(
                        table_rect=table_rect,
                        cell_text=[["a"]],
                        cell_rects=[[rect]],
                    )

    def test_a_cell_a_hair_over_the_edge_is_kept(self):
        """A border stroke on the boundary, plus outward rounding, puts real
        cells a fraction outside the box that contains them.  Refusing those
        would discard the geometry of ordinary tables."""
        slack = CELL_OVERFLOW_TOLERANCE_MILLIPOINTS / 1000.0
        table = _locate(
            cell_rects=[
                [
                    (100.0 - slack, 100.0 - slack, 250.0, 140.0),
                    GRID_RECTS[0][1],
                ],
                GRID_RECTS[1],
                GRID_RECTS[2],
            ],
        )
        self.assertEqual(table.located_values, 6)

    def test_a_cell_well_over_the_edge_is_refused(self):
        """Past the table's own right edge, not merely into a neighbour.

        The first draft of this test widened a cell towards the cell beside
        it, which is an overlap rather than an overflow and tripped a
        different rule; the table bound is only exceeded by leaving the table.
        """
        slack = CELL_OVERFLOW_TOLERANCE_MILLIPOINTS / 1000.0
        with self.assertRaisesRegex(TableGeometryError, "outside the table"):
            _locate(
                cell_rects=[
                    [
                        GRID_RECTS[0][0],
                        (250.0, 100.0, 400.0 + slack * 5, 140.0),
                    ],
                    GRID_RECTS[1],
                    GRID_RECTS[2],
                ],
            )

    def test_overlapping_cells_are_refused(self):
        with self.assertRaisesRegex(TableGeometryError, "share page area"):
            _locate(
                cell_rects=[
                    [(100.0, 100.0, 300.0, 140.0), (250.0, 100.0, 400.0, 140.0)],
                    GRID_RECTS[1],
                    GRID_RECTS[2],
                ],
            )

    def test_cells_that_only_touch_are_kept(self):
        """Adjacent cells in any real grid share an edge.  Treating a shared
        edge as an overlap would refuse every table there is, so the check is
        on interior area and this test is what holds it there."""
        table = _locate()
        self.assertEqual(table.located_values, 6)

    def test_cells_overlapping_across_rows_are_refused(self):
        """The scan sorts by top edge and stops early; a collision between
        rows rather than within one is the case that ordering could hide."""
        with self.assertRaisesRegex(TableGeometryError, "share page area"):
            _locate(
                cell_rects=[
                    [(100.0, 100.0, 250.0, 160.0), GRID_RECTS[0][1]],
                    GRID_RECTS[1],
                    GRID_RECTS[2],
                ],
            )

    def test_an_unusable_table_rectangle_raises_this_modules_error(self):
        """Callers catch one family.  A rectangle error escaping as itself
        would slip past the fallback and lose the table."""
        with self.assertRaisesRegex(TableGeometryError, "table's own rectangle"):
            _locate(table_rect=(0.0, 0.0, 0.0, 0.0))

    def test_an_unusable_cell_rectangle_raises_this_modules_error(self):
        with self.assertRaisesRegex(TableGeometryError, r"cell \(0, 0\)"):
            _locate(
                cell_rects=[
                    [(250.0, 140.0, 100.0, 100.0), GRID_RECTS[0][1]],
                    GRID_RECTS[1],
                    GRID_RECTS[2],
                ],
            )


class RotationTests(unittest.TestCase):
    def test_displayed_coordinates_are_taken_as_given(self):
        table = _locate(space=CoordinateSpace.pdf_displayed, rotation=90)
        self.assertEqual(
            table.locator.to_json()["rect"], [100_000, 100_000, 400_000, 220_000]
        )

    def test_unrotated_cells_match_measured_pymupdf(self):
        """Measured, not derived.

        PyMuPDF 1.28.2 was given this table on a page set to rotation 90 and
        reported the table at (572, 100, 692, 400) and the cell holding
        ``r0c0`` at (652, 100, 692, 250).  Those are the numbers below.  The
        rotation arithmetic in ``locators`` is a reimplementation of the
        library's rotation matrix, and this is the only place that says the
        reimplementation agrees with the thing it reimplements.

        The displayed page is 792x612 -- a quarter turn swaps the axes -- so
        the page extents passed here are the displayed ones, which is what a
        caller reading ``page.rect`` has.
        """
        table = _locate(
            space=CoordinateSpace.pdf_unrotated,
            rotation=90,
            page_width=792.0,
            page_height=612.0,
        )
        self.assertEqual(
            table.locator.to_json()["rect"],
            [572_000, 100_000, 692_000, 400_000],
        )
        by_text = {cell.text: cell for cell in table.cells}
        self.assertEqual(
            by_text["r0c0"].locator.to_json()["rect"],
            [652_000, 100_000, 692_000, 250_000],
        )

    def test_the_space_is_not_assumed(self):
        """The same table read in the two spaces lands in different places, so
        a caller that guessed would be wrong half the time without any error
        to show for it."""
        as_displayed = _locate(space=CoordinateSpace.pdf_displayed, rotation=90)
        as_unrotated = _locate(
            space=CoordinateSpace.pdf_unrotated,
            rotation=90,
            page_width=792.0,
            page_height=612.0,
        )
        self.assertNotEqual(
            as_displayed.locator.to_json()["rect"],
            as_unrotated.locator.to_json()["rect"],
        )


class SerialisationTests(unittest.TestCase):
    def test_the_payload_is_byte_stable(self):
        """The literal is the point, for the reason the locator suite pins its
        own: a round-trip compared against itself accepts any key order."""
        table = _locate(
            page_number=2,
            cell_text=[["a", "b"]],
            cell_rects=[[(100.0, 100.0, 250.0, 140.0), None]],
            table_rect=(100.0, 100.0, 400.0, 140.0),
        )
        self.assertEqual(
            json.dumps(table.to_json()),
            '{"page": 2, "table": {"kind": "page_rectangle", "page": 2, '
            '"rect": [100000, 100000, 400000, 140000], '
            '"page_size": [612000, 792000], "units": "millipoints", '
            '"space": "pdf_displayed"}, '
            '"values": [{"row": 0, "column": 0, "text": "a", '
            '"locator": {"kind": "page_rectangle", "page": 2, '
            '"rect": [100000, 100000, 250000, 140000], '
            '"page_size": [612000, 792000], "units": "millipoints", '
            '"space": "pdf_displayed"}}, '
            '{"row": 0, "column": 1, "text": "b", '
            '"locator": {"kind": "unlocated", "page": 2}}], '
            '"unlocated_values": 1}',
        )

    def test_the_same_table_serialises_identically_every_time(self):
        self.assertEqual(
            json.dumps(_locate().to_json()), json.dumps(_locate().to_json())
        )


class ImmutabilityTests(unittest.TestCase):
    def test_a_located_table_cannot_be_edited_after_the_fact(self):
        table = _locate()
        with self.assertRaises(Exception):
            table.unlocated_values = 99
        with self.assertRaises(Exception):
            table.cells[0].text = "edited"

    def test_cells_are_a_tuple_so_none_can_be_appended(self):
        self.assertIsInstance(_locate().cells, tuple)
        self.assertIsInstance(_locate(), LocatedTable)


if __name__ == "__main__":
    unittest.main()
