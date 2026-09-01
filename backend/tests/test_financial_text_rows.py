"""Tests for recovering a page's rows from where its words sit.

No case material appears here.  Every page is a stub offering ``get_text``,
because that is the only thing the module under test reads and it is duck-typed
against that shape precisely so it can be exercised without a PDF.

Two of these tests carry more weight than the rest.
:meth:`AcceptanceTests.test_the_recovered_table_is_one_locate_table_accepts`
runs the real geometry check over the real output, because everything else here
proves only that the module does what it was written to do -- not that what it
produces is usable by the code that has to consume it, which is the question
that actually failed on real documents.  And :class:`RealPageTests` runs against
PyMuPDF itself, because every stub in this file was written from the same
assumption as the code and so cannot test that assumption.
"""
import unittest

try:  # pragma: no cover - exercised by whether RealPageTests below skips
    import pymupdf

    _PYMUPDF = True
except Exception:  # pragma: no cover
    _PYMUPDF = False

from postgres.models.enums import CoordinateSpace
from services.financial.table_geometry import locate_table
from services.financial.text_rows import (
    BAND_SEPARATION,
    MIN_COLUMN_GAP,
    MIN_ROWS,
    TextRowTable,
    Word,
    deduplicate,
    group_lines,
    line_bands,
    read_text_rows,
    split_cells,
)

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0

# Two lines of two columns.  The words inside a column sit 2pt apart and the
# gutter between columns is 100pt, so the split threshold -- a multiple of the
# page's *median* gap -- lands between the two with room on each side.  A stub
# whose cells were single words would report one enormous median and never
# split, which is a property of real pages too.
WORDS = [
    (100.0, 100.0, 125.0, 108.0, "Trans", 0, 0, 0),
    (127.0, 100.0, 150.0, 108.0, "Date", 0, 0, 1),
    (250.0, 100.0, 300.0, 108.0, "Merchant", 0, 0, 2),
    (302.0, 100.0, 330.0, 108.0, "Name", 0, 0, 3),
    (100.0, 140.0, 112.0, 148.0, "01", 0, 1, 0),
    (114.0, 140.0, 140.0, 148.0, "Feb", 0, 1, 1),
    (250.0, 140.0, 300.0, 148.0, "COFFEE", 0, 1, 2),
    (302.0, 140.0, 340.0, 148.0, "SHOP", 0, 1, 3),
]


class StubPage:
    def __init__(self, words=WORDS):
        self._words = words

    def get_text(self, kind):
        assert kind == "words", f"unexpected get_text({kind!r})"
        return self._words


def word(x0, y0, x1, y1, text):
    return Word(x0=x0, y0=y0, x1=x1, y1=y1, text=text)


class ReadingTests(unittest.TestCase):
    def test_a_two_column_page_yields_two_columns(self):
        table = read_text_rows(StubPage())
        self.assertEqual(
            table.extract(),
            [["Trans Date", "Merchant Name"], ["01 Feb", "COFFEE SHOP"]],
        )

    def test_the_bbox_encloses_every_cell(self):
        table = read_text_rows(StubPage())
        self.assertEqual(table.bbox, (100.0, 100.0, 340.0, 148.0))

    def test_a_page_with_no_words_yields_nothing(self):
        self.assertIsNone(read_text_rows(StubPage([])))

    def test_one_line_is_not_a_table(self):
        # A single line of text is not a table, and calling it one would put a
        # spurious table on every page of running prose in a document.
        self.assertIsNone(read_text_rows(StubPage(WORDS[:4])))

    def test_the_row_floor_is_the_documented_one(self):
        self.assertEqual(MIN_ROWS, 2)

    def test_rows_come_down_the_page_in_order(self):
        # The words are handed over bottom line first, so an implementation
        # that trusted input order rather than position would invert them.
        table = read_text_rows(StubPage(WORDS[4:] + WORDS[:4]))
        self.assertEqual(table.extract()[0], ["Trans Date", "Merchant Name"])

    def test_cells_come_across_the_page_in_order(self):
        table = read_text_rows(StubPage(list(reversed(WORDS))))
        self.assertEqual(table.extract()[0], ["Trans Date", "Merchant Name"])


class MalformedInputTests(unittest.TestCase):
    """A reader's output is not this module's to trust."""

    def test_a_tuple_too_short_to_be_a_word_is_skipped(self):
        self.assertIsNone(read_text_rows(StubPage([(1.0, 2.0, 3.0)])))

    def test_a_word_whose_text_is_not_text_is_skipped(self):
        words = list(WORDS) + [(400.0, 100.0, 420.0, 108.0, None, 0, 0, 9)]
        self.assertEqual(len(read_text_rows(StubPage(words)).rows), 2)

    def test_whitespace_is_not_a_word(self):
        words = list(WORDS) + [(400.0, 100.0, 420.0, 108.0, "   ", 0, 0, 9)]
        table = read_text_rows(StubPage(words))
        self.assertEqual(table.extract()[0], ["Trans Date", "Merchant Name"])

    def test_surrounding_whitespace_is_stripped_from_a_word(self):
        words = [
            (100.0, 100.0, 125.0, 108.0, " Trans ", 0, 0, 0),
            (127.0, 100.0, 150.0, 108.0, "Date\n", 0, 0, 1),
        ] + WORDS[4:6]
        self.assertEqual(read_text_rows(StubPage(words)).extract()[0], ["Trans Date"])

    def test_a_word_with_no_area_does_not_divide_by_zero(self):
        # A degenerate box is compared for overlap against every other copy of
        # the same text, and the comparison divides by the smaller area.  It
        # gets a line of its own here -- a zero-height box has a centre nowhere
        # near the line it was drawn on -- which is the right outcome: the real
        # rows come through untouched rather than absorbing it.
        words = list(WORDS) + [(400.0, 100.0, 400.0, 100.0, "Trans", 0, 0, 9)]
        table = read_text_rows(StubPage(words))
        self.assertIn(["Trans Date", "Merchant Name"], table.extract())
        self.assertIn(["01 Feb", "COFFEE SHOP"], table.extract())


class DeduplicationTests(unittest.TestCase):
    """The quietest corruption in this path: every figure read twice.

    A scanned PDF can carry more than one OCR text layer, each a complete
    reading of the page.  Left in, a sum doubles and nothing reports an error.
    """

    def test_a_word_written_over_itself_is_read_once(self):
        first = word(100.0, 100.0, 130.0, 108.0, "2500.00")
        second = word(100.4, 100.3, 130.4, 108.3, "2500.00")
        self.assertEqual(deduplicate([first, second]), [first])

    def test_which_copy_survives_does_not_depend_on_the_reader_s_order(self):
        # The survivor is chosen by position -- topmost, then leftmost -- and
        # not by which copy the reader happened to hand over first.  Two OCR
        # layers can be emitted in either order on either page, so an
        # order-dependent rule would make the stored rectangle differ between
        # two runs over the same document with nothing to show for it.
        upper = word(100.0, 100.0, 130.0, 108.0, "2500.00")
        lower = word(100.4, 100.3, 130.4, 108.3, "2500.00")
        self.assertEqual(deduplicate([upper, lower]), [upper])
        self.assertEqual(deduplicate([lower, upper]), [upper])

    def test_two_different_values_side_by_side_both_survive(self):
        # The comparison can reject a duplicate but must never invent one, so
        # only identical text is ever considered.
        left = word(100.0, 100.0, 130.0, 108.0, "2500.00")
        right = word(100.0, 100.0, 130.0, 108.0, "2500.01")
        self.assertEqual(len(deduplicate([left, right])), 2)

    def test_the_same_value_in_two_places_both_survive(self):
        # A statement that debits 25.00 twice in a month has two transactions,
        # not one written twice, and the difference is where they sit.
        top = word(100.0, 100.0, 130.0, 108.0, "25.00")
        bottom = word(100.0, 300.0, 130.0, 308.0, "25.00")
        self.assertEqual(len(deduplicate([top, bottom])), 2)

    def test_a_short_word_hiding_inside_a_long_one_is_dropped(self):
        # Judged by how much of the *smaller* word is covered; using the larger
        # as the denominator would let this duplicate through.
        long_word = word(100.0, 100.0, 200.0, 108.0, "x")
        short = word(150.0, 100.0, 160.0, 108.0, "x")
        self.assertEqual(deduplicate([long_word, short]), [long_word])

    def test_a_doubled_layer_does_not_double_the_page(self):
        offset = [
            (x0 + 0.4, y0 + 0.3, x1 + 0.4, y1 + 0.3, text, b, l, w)
            for x0, y0, x1, y1, text, b, l, w in WORDS
        ]
        table = read_text_rows(StubPage(list(WORDS) + offset))
        self.assertEqual(
            table.extract(),
            [["Trans Date", "Merchant Name"], ["01 Feb", "COFFEE SHOP"]],
        )


class LineGroupingTests(unittest.TestCase):
    def test_words_on_the_same_line_group_together(self):
        line = [word(100.0, 100.0, 120.0, 108.0, "a"), word(130.0, 100.2, 150.0, 108.2, "b")]
        self.assertEqual(len(group_lines(line, 3.6)), 1)

    def test_words_on_different_lines_do_not(self):
        pair = [word(100.0, 100.0, 120.0, 108.0, "a"), word(100.0, 140.0, 120.0, 148.0, "b")]
        self.assertEqual(len(group_lines(pair, 3.6)), 2)

    def test_a_line_does_not_drift_down_the_page(self):
        # Each word is within tolerance of the one before it but the last is
        # well outside the line's own centre.  Grouping against the previous
        # word rather than the running centre would swallow the lot.
        drifting = [
            word(100.0 + 30 * i, 100.0 + 3.0 * i, 120.0 + 30 * i, 108.0 + 3.0 * i, "w")
            for i in range(6)
        ]
        self.assertGreater(len(group_lines(drifting, 3.6)), 1)

    def test_no_words_group_into_no_lines(self):
        self.assertEqual(group_lines([], 3.6), [])


class CellSplittingTests(unittest.TestCase):
    def test_a_wide_gap_ends_a_cell(self):
        line = [word(100.0, 100.0, 120.0, 108.0, "a"), word(250.0, 100.0, 270.0, 108.0, "b")]
        self.assertEqual([c.text for c in split_cells(line, 6.0)], ["a", "b"])

    def test_a_narrow_gap_does_not(self):
        line = [word(100.0, 100.0, 120.0, 108.0, "a"), word(122.0, 100.0, 140.0, 108.0, "b")]
        self.assertEqual([c.text for c in split_cells(line, 6.0)], ["a b"])

    def test_the_cell_rectangle_encloses_the_words_it_was_read_from(self):
        line = [word(100.0, 100.0, 120.0, 108.0, "a"), word(122.0, 99.0, 140.0, 109.0, "b")]
        self.assertEqual(split_cells(line, 6.0)[0].rect, (100.0, 99.0, 140.0, 109.0))

    def test_an_empty_line_yields_no_cells(self):
        self.assertEqual(split_cells([], 6.0), [])

    def test_the_gap_threshold_has_a_floor(self):
        # A page whose words happen to sit unusually close together would
        # otherwise produce a threshold small enough to split ordinary prose
        # into columns, one word per cell.
        tight = []
        for line_index in range(2):
            y = 100.0 + 40 * line_index
            x = 100.0
            for _ in range(6):
                tight.append((x, y, x + 20.0, y + 8.0, "word", 0, line_index, 0))
                x += 20.0 + 0.2
        table = read_text_rows(StubPage(tight))
        self.assertEqual([len(r.values) for r in table.rows], [1, 1])
        self.assertEqual(MIN_COLUMN_GAP, 6.0)

    def test_a_wide_early_word_is_pulled_back_out_of_its_neighbour(self):
        # Cells are cut at wide gaps, so the last word of a run ends before the
        # next run starts -- but an earlier word can be the widest and reach
        # past it, producing the same unclickable overlap stacked rows do.
        line = [
            word(100.0, 100.0, 260.0, 108.0, "wide"),
            word(110.0, 100.0, 120.0, 108.0, "short"),
            word(250.0, 100.0, 270.0, 108.0, "next"),
        ]
        cells = split_cells(line, 6.0)
        self.assertEqual(len(cells), 2)
        self.assertLess(cells[0].rect[2], cells[1].rect[0])


class BandingTests(unittest.TestCase):
    """Two rows a click cannot choose between are two rows worth refusing."""

    def test_a_tall_word_does_not_reach_into_the_line_below(self):
        # A line carrying a logo, a heading or an accented capital reports a
        # box taller than its glyphs.  Measured before this existed: only 2 of
        # 56 pages of a scanned statement survived the overlap check.
        lines = [
            [word(100.0, 100.0, 120.0, 145.0, "tall")],
            [word(100.0, 140.0, 120.0, 148.0, "next")],
        ]
        top, bottom = line_bands(lines)
        self.assertLess(top[1], bottom[0])

    def test_the_bands_leave_clear_space_rather_than_meeting(self):
        # capture() stores millipoints and rounds outward, so two rectangles
        # meeting exactly on a boundary both claim the millipoint it falls in.
        # Both lines here reach past the midpoint between them, so both are
        # clipped to it and the gap left is the separation twice over -- the
        # case the constant exists for.
        lines = [
            [word(100.0, 100.0, 120.0, 145.0, "tall")],
            [word(100.0, 138.0, 120.0, 180.0, "also tall")],
        ]
        top, bottom = line_bands(lines)
        self.assertAlmostEqual(bottom[0] - top[1], 2 * BAND_SEPARATION)

    def test_clipping_never_pushes_a_box_off_its_own_words(self):
        # Clipping only ever narrows a highlight.  Expanding one would put the
        # box somewhere the value is not.
        lines = [
            [word(100.0, 100.0, 120.0, 108.0, "a")],
            [word(100.0, 140.0, 120.0, 148.0, "b")],
        ]
        self.assertEqual(line_bands(lines), [(100.0, 108.0), (140.0, 148.0)])

    def test_no_lines_yield_no_bands(self):
        self.assertEqual(line_bands([]), [])


class ShapeTests(unittest.TestCase):
    """The recovered table has to be the shape ``pdf_tables`` already reads.

    ``bbox``, ``extract()`` and ``rows[].cells`` are not this module's names to
    choose.  Matching them is what lets a recovered table travel through the
    existing chunking and locating code rather than through a parallel path
    that would have to be kept in step with it.
    """

    def setUp(self):
        self.table = read_text_rows(StubPage())

    def test_it_is_a_text_row_table(self):
        self.assertIsInstance(self.table, TextRowTable)

    def test_every_row_carries_a_rectangle_per_value(self):
        for row in self.table.rows:
            self.assertEqual(len(row.values), len(row.cells))

    def test_the_counts_agree_with_the_rows(self):
        self.assertEqual(self.table.row_count, 2)
        self.assertEqual(self.table.cell_count, 4)

    def test_it_is_immutable(self):
        with self.assertRaises(Exception):
            self.table.bbox = (0.0, 0.0, 1.0, 1.0)


class AcceptanceTests(unittest.TestCase):
    def test_the_recovered_table_is_one_locate_table_accepts(self):
        # The point of the whole module.  Rows that cannot be located are rows
        # an analyst cannot click through to, and a reader that produced them
        # would have moved the failure rather than fixed it.
        table = read_text_rows(StubPage())
        located = locate_table(
            page_number=1,
            table_rect=table.bbox,
            cell_text=[list(row.values) for row in table.rows],
            cell_rects=[list(row.cells) for row in table.rows],
            space=CoordinateSpace.pdf_unrotated,
            rotation=0,
            page_width=PAGE_WIDTH,
            page_height=PAGE_HEIGHT,
        )
        self.assertEqual(located.located_values, 4)
        self.assertEqual(located.unlocated_values, 0)


@unittest.skipUnless(_PYMUPDF, "PyMuPDF not installed; the duck-typing is unverified")
class RealPageTests(unittest.TestCase):
    """Whether ``get_text("words")`` is what this module assumes it is.

    Everything above runs against a stub written from the same assumption as
    the code, so together they show only that the two agree with each other.
    This builds a real page with real inserted text and asks the library.
    """

    def build(self, rotation=0):
        document = pymupdf.open()
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        for index, row in enumerate(
            [("Trans Date", "Merchant Name"), ("01 Feb", "COFFEE SHOP")]
        ):
            y = 100.0 + 40 * index
            page.insert_text((100.0, y), row[0], fontsize=9)
            page.insert_text((250.0, y), row[1], fontsize=9)
        if rotation:
            page.set_rotation(rotation)
        return document, page

    def test_the_tuple_shape_is_the_one_assumed(self):
        document, page = self.build()
        try:
            words = page.get_text("words")
            self.assertTrue(words)
            first = words[0]
            self.assertGreaterEqual(len(first), 5)
            self.assertIsInstance(first[4], str)
            for value in first[:4]:
                self.assertIsInstance(value, float)
        finally:
            document.close()

    def test_a_page_with_no_drawn_geometry_still_yields_its_rows(self):
        # The failure this module exists to prevent, reproduced in miniature:
        # no vector drawings anywhere, transactions plainly present.
        document, page = self.build()
        try:
            self.assertEqual(page.get_drawings(), [])
            self.assertEqual(len(page.find_tables().tables), 0)
            table = read_text_rows(page)
            self.assertEqual(
                table.extract(),
                [["Trans Date", "Merchant Name"], ["01 Feb", "COFFEE SHOP"]],
            )
        finally:
            document.close()

    def test_the_words_are_reported_in_the_unrotated_space(self):
        # The measurement behind TEXT_COORDINATE_SPACE.  If get_text followed
        # the same convention find_tables does, these would differ.
        upright, upright_page = self.build()
        turned, turned_page = self.build(rotation=180)
        try:
            self.assertEqual(
                [w[:4] for w in upright_page.get_text("words")],
                [w[:4] for w in turned_page.get_text("words")],
            )
        finally:
            upright.close()
            turned.close()

    def test_a_real_page_locates_every_value_where_it_was_written(self):
        document, page = self.build()
        try:
            table = read_text_rows(page)
            located = locate_table(
                page_number=1,
                table_rect=table.bbox,
                cell_text=[list(row.values) for row in table.rows],
                cell_rects=[list(row.cells) for row in table.rows],
                space=CoordinateSpace.pdf_unrotated,
                rotation=page.rotation,
                page_width=page.rect.width,
                page_height=page.rect.height,
            )
            self.assertEqual(located.located_values, 4)
            self.assertEqual(located.unlocated_values, 0)
            date = next(
                cell for cell in located.cells if cell.text == "Trans Date"
            )
            rectangle = date.locator.rectangle
            # Written at (100, 100) as a 9pt baseline, so the box sits just
            # above and to the right of that point.
            self.assertLess(abs(rectangle.x0 / 1000.0 - 100.0), 2.0)
            self.assertLess(abs(rectangle.y1 / 1000.0 - 100.0), 3.0)
        finally:
            document.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
