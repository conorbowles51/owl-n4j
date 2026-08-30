"""Tests for source rectangles and what a locator is allowed to claim.

Two of these tests exist because of a measurement rather than a hunch, and
they are the ones worth reading first.

**The coordinate space cannot be recovered from the numbers.**  PyMuPDF
returns word geometry in unrotated coordinates and table geometry in displayed
coordinates, on the same page, with no marker distinguishing them.  On a page
rotated 180 degrees both readings of the same table land inside the page and
both look reasonable; only one is where the ink is.  So the space has to be
declared by whoever captured the rectangle, and
``test_the_two_spaces_disagree_on_a_rotated_page`` is the proof that getting it
wrong is not a rounding difference but a different place on the paper.

**A test that only uses an unrotated page proves nothing.**  At rotation 0 the
two spaces coincide exactly, so an implementation that ignored rotation
entirely would pass.  Every geometry test below therefore runs at all four
legal rotations, and ``test_transform_matches_pymupdf`` checks the arithmetic
against PyMuPDF's own ``rotation_matrix`` rather than against numbers this
file made up.

No case material appears here.  The pages are synthetic, the amounts are round
and invented, and the only document ever opened is one built in the test.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from postgres.models.enums import CoordinateSpace, LocatorKind
from services.financial.locators import (
    Locator,
    LocatorCoherenceError,
    RectangleError,
    SourceRectangle,
    capture,
)

try:  # pragma: no cover - exercised by whether the class below skips
    import fitz

    _PYMUPDF = True
except Exception:  # pragma: no cover
    _PYMUPDF = False


ROTATIONS = (0, 90, 180, 270)


def _rect(**overrides):
    """A valid rectangle on a US Letter page, in millipoints."""
    fields = {
        "page_number": 1,
        "x0": 80_000,
        "y0": 100_000,
        "x1": 400_000,
        "y1": 160_000,
        "page_width": 612_000,
        "page_height": 792_000,
    }
    fields.update(overrides)
    return SourceRectangle(**fields)


class SourceRectangleTests(unittest.TestCase):
    def test_a_rectangle_with_no_area_is_refused(self):
        """An empty box renders as an invisible highlight, which reads as
        "nothing found" to a viewer while the row claims it was located."""
        for label, overrides in (
            ("zero width", {"x1": 80_000}),
            ("zero height", {"y1": 100_000}),
            ("inverted x", {"x0": 400_000, "x1": 80_000}),
            ("inverted y", {"y0": 160_000, "y1": 100_000}),
        ):
            with self.subTest(label):
                with self.assertRaises(RectangleError):
                    _rect(**overrides)

    def test_a_rectangle_off_the_page_is_refused(self):
        for label, overrides in (
            ("past the right edge", {"x1": 612_001}),
            ("past the bottom", {"y1": 792_001}),
            ("negative x", {"x0": -1}),
            ("negative y", {"y0": -1}),
        ):
            with self.subTest(label):
                with self.assertRaises(RectangleError):
                    _rect(**overrides)

    def test_the_page_edge_itself_is_allowed(self):
        """Ink at the very margin is common on scans and is not an error."""
        edge = _rect(x0=0, y0=0, x1=612_000, y1=792_000)
        self.assertEqual(edge.width, 612_000)
        self.assertEqual(edge.height, 792_000)

    def test_pages_are_one_based(self):
        for page_number in (0, -1):
            with self.subTest(page_number=page_number):
                with self.assertRaises(RectangleError):
                    _rect(page_number=page_number)

    def test_a_page_with_no_extent_carries_nothing(self):
        """Matched on the message, not just the type.

        A zero-width page also puts every rectangle past its right edge, so
        asserting ``RectangleError`` alone passes even with this rule deleted —
        the out-of-bounds rule raises the same class.  The two are different
        diagnoses (a broken reader versus a broken page) and only the message
        distinguishes them, so the message is what is asserted.
        """
        for overrides in (
            {"page_width": 0},
            {"page_height": 0},
            {"page_width": -5},
        ):
            with self.subTest(**overrides):
                with self.assertRaisesRegex(RectangleError, "page with no extent"):
                    _rect(**overrides)

    def test_floats_are_refused_rather_than_rounded(self):
        """Silently accepting a float would put the platform-dependent text of
        a double into JSONB, which is the one thing a byte-identical export
        cannot survive."""
        with self.assertRaises(RectangleError):
            _rect(x0=80_000.5)

    def test_booleans_are_refused(self):
        """``bool`` is an ``int`` subclass, so every bounds check below would
        pass for ``True`` and store a rectangle one millipoint wide."""
        with self.assertRaises(RectangleError):
            _rect(x0=True)

    def test_normalised_is_exact(self):
        """Returned as Decimal so a viewer multiplying by a pixel width gets an
        exact product rather than a float that lands half a pixel out.

        The tenths are chosen deliberately.  A rectangle at a quarter and a half
        of the page would satisfy these assertions under float arithmetic too,
        and would prove nothing about the return type; a tenth is not
        representable in binary, so this passes only for Decimal.  The final
        assertion records that, so the test cannot quietly stop discriminating
        if the implementation is changed back to float.
        """
        rectangle = _rect(x0=61_200, x1=183_600, y0=79_200, y1=237_600)
        x0, y0, x1, y1 = rectangle.normalised()
        self.assertEqual(x0, Decimal("0.1"))
        self.assertEqual(x0 * 3, x1)
        self.assertEqual(y0 * 3, y1)
        self.assertNotEqual(float(x0) * 3, float(x1))


@unittest.skipUnless(_PYMUPDF, "PyMuPDF not installed; the transform is unverified")
class TransformAgreesWithPyMuPDFTests(unittest.TestCase):
    """The rotation arithmetic in locators.py, checked against the library.

    ``_to_displayed`` reimplements ``page.rotation_matrix`` so that the backend
    does not need a PDF library to interpret four numbers.  A reimplementation
    is only safe while something proves it still agrees with the original, and
    that is this class.  If it skips, the transform is asserted by nothing.
    """

    def _page(self, rotation):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((100, 200), "1,234.56", fontsize=12)
        page.set_rotation(rotation)
        return doc, page

    def test_transform_matches_pymupdf(self):
        for rotation in ROTATIONS:
            with self.subTest(rotation=rotation):
                doc, page = self._page(rotation)
                word = page.get_text("words")[0]
                expected = fitz.Rect(word[:4]) * page.rotation_matrix
                expected.normalize()

                got = capture(
                    page_number=1,
                    rect=tuple(word[:4]),
                    space=CoordinateSpace.pdf_unrotated,
                    rotation=rotation,
                    page_width=page.rect.width,
                    page_height=page.rect.height,
                )
                # Outward rounding means the stored box may exceed PyMuPDF's by
                # up to one millipoint per edge, and must never fall inside it.
                self.assertLessEqual(got.x0, _ceil(expected.x0))
                self.assertLessEqual(got.y0, _ceil(expected.y0))
                self.assertGreaterEqual(got.x1, _floor(expected.x1))
                self.assertGreaterEqual(got.y1, _floor(expected.y1))
                self.assertLess(abs(got.x0 - expected.x0 * 1000), 1.001)
                self.assertLess(abs(got.y1 - expected.y1 * 1000), 1.001)
                doc.close()

    def test_a_captured_table_box_stays_on_the_page(self):
        """``find_tables`` reports displayed coordinates, so capturing it as
        ``pdf_displayed`` must leave it inside the page at every rotation.

        Capturing it as ``pdf_unrotated`` instead rotates it a second time; at
        90 degrees that puts it past the bottom edge of a 612-high page, which
        is the failure this argument exists to prevent.
        """
        for rotation in ROTATIONS:
            with self.subTest(rotation=rotation):
                doc = fitz.open()
                page = doc.new_page(width=612, height=792)
                for y in (100, 130, 160):
                    page.draw_line(fitz.Point(80, y), fitz.Point(400, y))
                for x in (80, 240, 400):
                    page.draw_line(fitz.Point(x, 100), fitz.Point(x, 160))
                page.insert_text((90, 120), "Date", fontsize=10)
                page.set_rotation(rotation)

                table = page.find_tables().tables[0]
                got = capture(
                    page_number=1,
                    rect=tuple(table.bbox),
                    space=CoordinateSpace.pdf_displayed,
                    rotation=rotation,
                    page_width=page.rect.width,
                    page_height=page.rect.height,
                )
                self.assertLessEqual(got.x1, got.page_width)
                self.assertLessEqual(got.y1, got.page_height)
                doc.close()


def _ceil(value):
    import math

    return math.ceil(value * 1000)


def _floor(value):
    import math

    return math.floor(value * 1000)


class CaptureTests(unittest.TestCase):
    def test_the_two_spaces_disagree_on_a_rotated_page(self):
        """The whole reason ``space`` is a required argument.

        The same four numbers, captured under the two conventions, describe
        different places on the paper as soon as the page is rotated.  Nothing
        about the numbers themselves reveals which was meant, so a default
        would be silently wrong half the time.
        """
        rect = (100.0, 187.1, 139.3, 203.6)
        for rotation in (90, 180, 270):
            with self.subTest(rotation=rotation):
                width, height = (792.0, 612.0) if rotation in (90, 270) else (612.0, 792.0)
                as_displayed = capture(
                    page_number=1,
                    rect=rect,
                    space=CoordinateSpace.pdf_displayed,
                    rotation=rotation,
                    page_width=width,
                    page_height=height,
                )
                as_unrotated = capture(
                    page_number=1,
                    rect=rect,
                    space=CoordinateSpace.pdf_unrotated,
                    rotation=rotation,
                    page_width=width,
                    page_height=height,
                )
                self.assertNotEqual(as_displayed, as_unrotated)

    def test_the_page_number_survives_capture(self):
        """Asserted on a page other than the first, deliberately.

        Every other test here captures on page 1, so a capture that dropped the
        page number and hardcoded 1 would satisfy all of them while sending
        every click-through in a two-hundred-page statement to the cover sheet.
        """
        captured = capture(
            page_number=7,
            rect=(80.0, 100.0, 400.0, 160.0),
            space=CoordinateSpace.pdf_displayed,
            rotation=0,
            page_width=612.0,
            page_height=792.0,
        )
        self.assertEqual(captured.page_number, 7)
        self.assertEqual(
            Locator(kind=LocatorKind.page_rectangle, rectangle=captured).page, 7
        )

    def test_a_rectangle_that_misses_the_page_entirely_is_refused(self):
        """Matched on the message, for the same reason as the page-extent rule.

        Clamping a rectangle that lies wholly off the page leaves an inverted
        box, which ``SourceRectangle`` then refuses as having no area — the
        same exception class from a different rule and a message that describes
        the clamped remains rather than what the reader actually reported.
        Asserting the message keeps the useful diagnosis, which names the
        original rectangle, the page and the rotation, and is the only thing
        that tells an operator which reader produced it.
        """
        for label, rect in (
            ("right of the page", (700.0, 100.0, 800.0, 160.0)),
            ("left of the page", (-200.0, 100.0, -50.0, 160.0)),
            ("below the page", (80.0, 900.0, 400.0, 950.0)),
            ("above the page", (80.0, -200.0, 400.0, -50.0)),
        ):
            with self.subTest(label):
                with self.assertRaisesRegex(RectangleError, "does not meet the page"):
                    capture(
                        page_number=1,
                        rect=rect,
                        space=CoordinateSpace.pdf_displayed,
                        rotation=0,
                        page_width=612.0,
                        page_height=792.0,
                    )

    def test_ink_overlapping_one_edge_is_kept_and_clamped(self):
        """The other half of the previous rule.

        A reader reporting a box a fraction over the margin is describing ink
        at the edge of the paper, which is ordinary on a scan.  Refusing it
        would discard evidence over a rounding difference, so it is clamped;
        only a box with no overlap at all is refused.
        """
        for label, rect, expected in (
            ("over the left edge", (-2.0, 100.0, 400.0, 160.0),
             (0, 100_000, 400_000, 160_000)),
            ("over the right edge", (80.0, 100.0, 614.0, 160.0),
             (80_000, 100_000, 612_000, 160_000)),
            ("over the top edge", (80.0, -2.0, 400.0, 160.0),
             (80_000, 0, 400_000, 160_000)),
            ("over the bottom edge", (80.0, 100.0, 400.0, 794.0),
             (80_000, 100_000, 400_000, 792_000)),
        ):
            with self.subTest(label):
                captured = capture(
                    page_number=1,
                    rect=rect,
                    space=CoordinateSpace.pdf_displayed,
                    rotation=0,
                    page_width=612.0,
                    page_height=792.0,
                )
                self.assertEqual(
                    (captured.x0, captured.y0, captured.x1, captured.y1), expected
                )

    def test_a_displayed_page_with_no_extent_is_refused(self):
        """Caught before any arithmetic runs, so the message names the page
        rather than the rectangle that was measured against it."""
        with self.assertRaisesRegex(RectangleError, "nothing can be located"):
            capture(
                page_number=1,
                rect=(80.0, 100.0, 400.0, 160.0),
                space=CoordinateSpace.pdf_displayed,
                rotation=0,
                page_width=0.0,
                page_height=792.0,
            )

    def test_the_two_spaces_coincide_when_the_page_is_upright(self):
        """Stated so that the previous test cannot be misread as "always
        differs", and to record why no test here stops at rotation 0."""
        rect = (100.0, 187.0, 139.0, 203.0)
        common = dict(page_number=1, rect=rect, rotation=0, page_width=612.0, page_height=792.0)
        self.assertEqual(
            capture(space=CoordinateSpace.pdf_displayed, **common),
            capture(space=CoordinateSpace.pdf_unrotated, **common),
        )

    def test_rounding_goes_outward(self):
        """A box a hair too small can clip the leading digit off an amount."""
        got = capture(
            page_number=1,
            rect=(10.0004, 20.0004, 30.0006, 40.0006),
            space=CoordinateSpace.pdf_displayed,
            rotation=0,
            page_width=612.0,
            page_height=792.0,
        )
        self.assertEqual((got.x0, got.y0), (10_000, 20_000))
        self.assertEqual((got.x1, got.y1), (30_001, 40_001))

    def test_a_rectangle_overhanging_the_margin_is_clamped(self):
        """Readers routinely report ink a fraction of a point past the edge.
        Discarding the location over that would lose evidence to arithmetic."""
        got = capture(
            page_number=1,
            rect=(-0.4, -0.4, 612.4, 792.4),
            space=CoordinateSpace.pdf_displayed,
            rotation=0,
            page_width=612.0,
            page_height=792.0,
        )
        self.assertEqual((got.x0, got.y0), (0, 0))
        self.assertEqual((got.x1, got.y1), (612_000, 792_000))

    def test_a_rectangle_that_never_meets_the_page_is_refused(self):
        with self.assertRaises(RectangleError):
            capture(
                page_number=1,
                rect=(700.0, 900.0, 800.0, 1000.0),
                space=CoordinateSpace.pdf_displayed,
                rotation=0,
                page_width=612.0,
                page_height=792.0,
            )

    def test_an_illegal_rotation_is_refused(self):
        """PDF permits four rotations.  A 45 would silently take the ``270``
        branch of the transform if the guard were dropped."""
        for rotation in (45, -90, 360):
            with self.subTest(rotation=rotation):
                with self.assertRaises(RectangleError):
                    capture(
                        page_number=1,
                        rect=(10.0, 10.0, 20.0, 20.0),
                        space=CoordinateSpace.pdf_displayed,
                        rotation=rotation,
                        page_width=612.0,
                        page_height=792.0,
                    )

    def test_capture_is_deterministic(self):
        """Same input, same integers, every time: the precondition for an
        export that regenerates byte for byte."""
        args = dict(
            page_number=2,
            rect=(80.123456, 100.654321, 400.5, 160.5),
            space=CoordinateSpace.pdf_unrotated,
            rotation=270,
            page_width=792.0,
            page_height=612.0,
        )
        self.assertEqual(capture(**args), capture(**args))


class LocatorCoherenceTests(unittest.TestCase):
    def test_page_rectangle_without_a_rectangle_is_refused(self):
        """It would render as a working click-through that opens nothing."""
        with self.assertRaises(LocatorCoherenceError):
            Locator(kind=LocatorKind.page_rectangle)

    def test_a_rectangle_on_any_other_kind_is_refused(self):
        for kind in (
            LocatorKind.page_only,
            LocatorKind.not_positional,
            LocatorKind.unlocated,
        ):
            with self.subTest(kind=kind.value):
                with self.assertRaises(LocatorCoherenceError):
                    Locator(kind=kind, rectangle=_rect())

    def test_page_only_must_know_the_page(self):
        with self.assertRaises(LocatorCoherenceError):
            Locator(kind=LocatorKind.page_only)

    def test_not_positional_cannot_carry_a_page(self):
        """A CSV row has no page.  Accepting one would let a reader invent
        pagination for a format that has none."""
        with self.assertRaises(LocatorCoherenceError):
            Locator(kind=LocatorKind.not_positional, page_number=1)

    def test_unlocated_permits_a_page_or_no_page(self):
        """A reader can fail to find the value on a page it knows, or fail
        before it knows the page.  Both are the same defect."""
        self.assertIsNone(Locator(kind=LocatorKind.unlocated).page)
        self.assertEqual(Locator(kind=LocatorKind.unlocated, page_number=4).page, 4)

    def test_a_page_disagreeing_with_its_rectangle_is_refused(self):
        with self.assertRaises(LocatorCoherenceError):
            Locator(
                kind=LocatorKind.page_rectangle,
                page_number=2,
                rectangle=_rect(page_number=3),
            )

    def test_only_a_rectangle_is_clickable(self):
        """The property the UI branches on.  ``page_only`` is not a degraded
        rectangle; it opens the page and says so."""
        self.assertTrue(
            Locator(kind=LocatorKind.page_rectangle, rectangle=_rect()).is_clickable
        )
        for locator in (
            Locator(kind=LocatorKind.page_only, page_number=1),
            Locator(kind=LocatorKind.not_positional),
            Locator(kind=LocatorKind.unlocated),
        ):
            with self.subTest(kind=locator.kind.value):
                self.assertFalse(locator.is_clickable)

    def test_the_kind_must_come_from_the_vocabulary(self):
        with self.assertRaises(LocatorCoherenceError):
            Locator(kind="page_rectangle")


class LocatorSerialisationTests(unittest.TestCase):
    def _all_kinds(self):
        return (
            Locator(kind=LocatorKind.page_rectangle, rectangle=_rect(page_number=5)),
            Locator(kind=LocatorKind.page_only, page_number=9),
            Locator(kind=LocatorKind.not_positional),
            Locator(kind=LocatorKind.unlocated),
            Locator(kind=LocatorKind.unlocated, page_number=2),
        )

    def test_every_kind_round_trips(self):
        for locator in self._all_kinds():
            with self.subTest(kind=locator.kind.value, page=locator.page):
                self.assertEqual(Locator.from_json(locator.to_json()), locator)

    def test_serialisation_is_byte_stable(self):
        """``provenance`` is JSONB and the export has to regenerate byte for
        byte, so the key order is declared rather than incidental.

        The literal below is the point.  Comparing a round-trip against itself
        proves only that ``to_json`` is consistent with itself, which any key
        order satisfies; it would pass unchanged if the order were reshuffled
        tomorrow.  Pinning the bytes is what makes reshuffling them a failure.
        """
        rectangle = SourceRectangle(
            page_number=3,
            x0=80_000,
            y0=100_000,
            x1=400_000,
            y1=160_000,
            page_width=612_000,
            page_height=792_000,
        )
        self.assertEqual(
            json.dumps(
                Locator(
                    kind=LocatorKind.page_rectangle, rectangle=rectangle
                ).to_json()
            ),
            '{"kind": "page_rectangle", "page": 3, '
            '"rect": [80000, 100000, 400000, 160000], '
            '"page_size": [612000, 792000], '
            '"units": "millipoints", "space": "pdf_displayed"}',
        )

    def test_reading_and_rewriting_changes_nothing(self):
        """A stored row read back and written out must produce the same bytes,
        or an export regenerated after a round-trip would differ from the one
        taken before it."""
        for locator in self._all_kinds():
            with self.subTest(kind=locator.kind.value):
                once = json.dumps(locator.to_json())
                twice = json.dumps(Locator.from_json(locator.to_json()).to_json())
                self.assertEqual(once, twice)

    def test_absent_values_are_omitted_rather_than_written_as_null(self):
        """An omitted key and a null key are different bytes for the same
        fact, and only one of them can be the stored form."""
        self.assertEqual(
            Locator(kind=LocatorKind.not_positional).to_json(), {"kind": "not_positional"}
        )
        self.assertNotIn("rect", Locator(kind=LocatorKind.page_only, page_number=1).to_json())

    def test_an_unknown_key_is_refused_rather_than_dropped(self):
        """A key this version does not understand is a newer writer or a
        corrupt row.  Ignoring it would quietly demote a rectangle to a page
        reference with nothing recording that it happened."""
        payload = Locator(kind=LocatorKind.page_only, page_number=1).to_json()
        payload["confidence"] = 0.9
        with self.assertRaises(LocatorCoherenceError):
            Locator.from_json(payload)

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(LocatorCoherenceError):
            Locator.from_json({"kind": "somewhere_on_the_page"})

    def test_a_rectangle_in_unknown_units_is_refused(self):
        """Rescaling a unit the reader does not know would put the highlight
        anywhere at all."""
        payload = Locator(
            kind=LocatorKind.page_rectangle, rectangle=_rect()
        ).to_json()
        payload["units"] = "points"
        with self.assertRaises(LocatorCoherenceError):
            Locator.from_json(payload)

    def test_a_rectangle_in_unrotated_space_is_refused_on_read(self):
        """Stored rectangles are always displayed-space.  One that claims
        otherwise cannot be drawn without the page rotation, which is not
        stored, so it is refused rather than drawn wrongly."""
        payload = Locator(
            kind=LocatorKind.page_rectangle, rectangle=_rect()
        ).to_json()
        payload["space"] = CoordinateSpace.pdf_unrotated.value
        with self.assertRaises(LocatorCoherenceError):
            Locator.from_json(payload)

    def test_geometry_keys_on_a_non_rectangle_kind_are_refused(self):
        for key, value in (
            ("rect", [0, 0, 1, 1]),
            ("page_size", [612_000, 792_000]),
            ("units", "millipoints"),
            ("space", "pdf_displayed"),
        ):
            with self.subTest(key=key):
                payload = {"kind": "page_only", "page": 1, key: value}
                with self.assertRaises(LocatorCoherenceError):
                    Locator.from_json(payload)

    def test_a_malformed_rectangle_is_refused(self):
        for label, mutate in (
            ("three numbers", lambda p: p.__setitem__("rect", [0, 0, 1])),
            ("rect not a list", lambda p: p.__setitem__("rect", "0,0,1,1")),
            ("one dimension", lambda p: p.__setitem__("page_size", [612_000])),
        ):
            with self.subTest(label):
                payload = Locator(
                    kind=LocatorKind.page_rectangle, rectangle=_rect()
                ).to_json()
                mutate(payload)
                with self.assertRaises(LocatorCoherenceError):
                    Locator.from_json(payload)

    def test_a_payload_that_is_not_a_mapping_is_refused(self):
        with self.assertRaises(LocatorCoherenceError):
            Locator.from_json([("kind", "page_only")])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
