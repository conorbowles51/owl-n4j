"""Tests for the layer that refuses to sum what nobody has confirmed.

The properties that matter here are the module's two promises taken together:
no doubtful string ever comes back as a bare figure, and no unparseable string
is ever dropped.  Concretely: a reading is certain or it carries its doubt,
never both and never neither; every figure that reaches a sum went through
:func:`require_certain`, which raises on doubt rather than guessing; the same
string is certain from a digital text layer and suspect off a scan, because
what a recogniser loses is exactly the mark that decides the magnitude; and a
page whose provenance cannot be measured is treated as fallible, so failure
costs caution rather than confidence.
"""

from __future__ import annotations

import dataclasses
import unittest

from services.financial.money import (
    Money,
    MoneyError,
    UnknownCurrencyError,
)
from services.financial.suspect_amounts import (
    FALLIBLE_ORIGINS,
    FULL_PAGE_IMAGE_COVERAGE,
    AmountReading,
    Proposal,
    Suspicion,
    SuspectAmountError,
    TextOrigin,
    page_text_origin,
    read_amount,
    require_certain,
)


class TextOriginTests(unittest.TestCase):
    def test_fallible_origins_are_the_two_that_can_lose_a_mark(self):
        self.assertIn(TextOrigin.recognised_glyphs, FALLIBLE_ORIGINS)
        self.assertIn(TextOrigin.unknown, FALLIBLE_ORIGINS)
        self.assertNotIn(TextOrigin.digital_text_layer, FALLIBLE_ORIGINS)

    def test_enum_values_are_their_names(self):
        """Stored payloads carry these strings; they must not drift."""
        for member in TextOrigin:
            self.assertEqual(member.value, member.name)
        for member in Suspicion:
            self.assertEqual(member.value, member.name)

    def test_origin_must_be_a_text_origin_not_a_string(self):
        """A caller that cannot say where the characters came from must say
        so explicitly; a string that happens to spell a member is a caller
        that never made the decision."""
        for bad in ("digital_text_layer", "recognised_glyphs", None, 0):
            with self.subTest(origin=bad):
                with self.assertRaises(MoneyError):
                    read_amount("12.34", "USD", bad)

    def test_unknown_currency_raises_rather_than_defaulting(self):
        with self.assertRaises(UnknownCurrencyError):
            read_amount("12.34", "XYZ", TextOrigin.digital_text_layer)


class AmountReadingInvariantTests(unittest.TestCase):
    def _certain_reading(self) -> AmountReading:
        return AmountReading(
            raw="12.34",
            currency="USD",
            origin=TextOrigin.digital_text_layer,
            suspicion=Suspicion.none,
            certain=Money(1234, "USD"),
            proposals=(),
            explanation="read exactly",
        )

    def test_a_certain_reading_must_carry_its_figure(self):
        with self.assertRaises(MoneyError):
            AmountReading(
                raw="12.34",
                currency="USD",
                origin=TextOrigin.digital_text_layer,
                suspicion=Suspicion.none,
                certain=None,
                proposals=(),
                explanation="",
            )

    def test_a_suspect_reading_must_not_carry_a_figure(self):
        """This is the invariant the whole module exists for: there is no
        state in which a figure is reachable without its doubt beside it."""
        with self.assertRaises(MoneyError):
            AmountReading(
                raw="1234",
                currency="USD",
                origin=TextOrigin.recognised_glyphs,
                suspicion=Suspicion.decimal_point_absent,
                certain=Money(123400, "USD"),
                proposals=(),
                explanation="",
            )

    def test_a_certain_reading_has_nothing_left_to_propose(self):
        with self.assertRaises(MoneyError):
            AmountReading(
                raw="12.34",
                currency="USD",
                origin=TextOrigin.digital_text_layer,
                suspicion=Suspicion.none,
                certain=Money(1234, "USD"),
                proposals=(Proposal(Money(1234, "USD"), "redundant"),),
                explanation="",
            )

    def test_is_certain_follows_suspicion(self):
        self.assertTrue(self._certain_reading().is_certain)
        doubtful = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        self.assertFalse(doubtful.is_certain)

    def test_readings_are_immutable(self):
        reading = self._certain_reading()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reading.certain = Money(1, "USD")

    def test_proposals_are_a_tuple(self):
        doubtful = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        self.assertIsInstance(doubtful.proposals, tuple)


class RequireCertainTests(unittest.TestCase):
    def test_a_certain_reading_yields_its_figure(self):
        reading = read_amount("12.34", "USD", TextOrigin.digital_text_layer)
        self.assertEqual(require_certain(reading), Money(1234, "USD"))

    def test_a_suspect_reading_raises_rather_than_guessing(self):
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        with self.assertRaises(SuspectAmountError):
            require_certain(reading)

    def test_the_refusal_names_the_string_and_the_doubt(self):
        """The traceback has to say which figure stopped the sum, not merely
        that one did."""
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        try:
            require_certain(reading)
        except SuspectAmountError as exc:
            message = str(exc)
        else:  # pragma: no cover - the assertion above would have failed
            self.fail("require_certain did not raise")
        self.assertIn("'1234'", message)
        self.assertIn("not settled", message)
        self.assertIn(Suspicion.decimal_point_absent.value, message)

    def test_suspect_amount_error_is_a_money_error(self):
        """A caller guarding the whole subsystem with MoneyError catches
        this refusal too."""
        self.assertTrue(issubclass(SuspectAmountError, MoneyError))


class CertainReadingTests(unittest.TestCase):
    def test_digital_text_is_exact_by_construction(self):
        """The generator wrote '1234', so the amount is 1234: the missing
        point cannot have been lost because it was never there."""
        reading = read_amount("1234", "USD", TextOrigin.digital_text_layer)
        self.assertIs(reading.suspicion, Suspicion.none)
        self.assertEqual(reading.certain, Money(123400, "USD"))
        self.assertEqual(reading.proposals, ())

    def test_a_grouped_thousand_from_digital_text_is_certain_in_usd(self):
        """'1,234' has only one reading a two-decimal currency can hold, and
        a digital origin leaves nothing else to doubt."""
        reading = read_amount("1,234", "USD", TextOrigin.digital_text_layer)
        self.assertIs(reading.suspicion, Suspicion.none)
        self.assertEqual(reading.certain, Money(123400, "USD"))

    def test_a_full_fraction_is_certain_even_off_a_scan(self):
        """A separator that was read fixes the magnitude, and a complete
        fraction leaves no digit unaccounted for."""
        reading = read_amount("1,234.56", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.none)
        self.assertEqual(reading.certain, Money(123456, "USD"))

    def test_a_zero_exponent_currency_has_no_mark_to_lose(self):
        for text, expected in (("1234", 1234), ("1,234", 1234)):
            with self.subTest(text=text):
                reading = read_amount(
                    text, "JPY", TextOrigin.recognised_glyphs
                )
                self.assertIs(reading.suspicion, Suspicion.none)
                self.assertEqual(reading.certain, Money(expected, "JPY"))

    def test_accounting_parentheses_stay_certain(self):
        reading = read_amount(
            "(1,234.56)", "USD", TextOrigin.recognised_glyphs
        )
        self.assertIs(reading.suspicion, Suspicion.none)
        self.assertEqual(reading.certain, Money(-123456, "USD"))

    def test_the_currency_code_is_normalised_onto_the_reading(self):
        reading = read_amount("12.34", " usd ", TextOrigin.digital_text_layer)
        self.assertEqual(reading.currency, "USD")

    def test_the_raw_string_is_preserved_as_given(self):
        reading = read_amount("1,234.56", "USD", TextOrigin.digital_text_layer)
        self.assertEqual(reading.raw, "1,234.56")
        self.assertIs(reading.origin, TextOrigin.digital_text_layer)


class DecimalPointAbsentTests(unittest.TestCase):
    """Bare digits off a scan: the most dangerous doubt and the only
    unbounded one."""

    def test_bare_digits_off_a_scan_are_not_summable(self):
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.decimal_point_absent)
        self.assertIsNone(reading.certain)

    def test_both_readings_are_proposed_exactly(self):
        """$12.34 and $1,234.00, a hundred apart, with nothing in the string
        to say which; the division back down has no remainder by
        construction."""
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        self.assertEqual(
            [p.money.minor_units for p in reading.proposals], [1234, 123400]
        )

    def test_the_hazard_is_the_currency_exponent(self):
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        self.assertIn("factor of 100", reading.explanation)
        kwd = read_amount("1234", "KWD", TextOrigin.recognised_glyphs)
        self.assertIs(kwd.suspicion, Suspicion.decimal_point_absent)
        self.assertEqual(
            [p.money.minor_units for p in kwd.proposals], [1234, 1234000]
        )
        self.assertIn("factor of 1000", kwd.explanation)

    def test_unknown_provenance_gets_the_cautious_treatment(self):
        """Doubting a sound figure costs a glance at the page; trusting an
        unsound one puts a hundredfold error inside a total."""
        reading = read_amount("1234", "USD", TextOrigin.unknown)
        self.assertIs(reading.suspicion, Suspicion.decimal_point_absent)

    def test_proposal_bases_state_the_operation_not_a_likelihood(self):
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        bases = [p.basis for p in reading.proposals]
        self.assertEqual(len(bases), len(set(bases)))
        for basis in bases:
            self.assertTrue(basis)


class FractionTooShortTests(unittest.TestCase):
    """Short of a full fraction, but the magnitude is pinned by a separator
    that was read, so the doubt is bounded below one major unit."""

    def test_a_short_decimal_off_a_scan_is_doubted(self):
        reading = read_amount("65.0", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.fraction_too_short)
        self.assertIsNone(reading.certain)
        self.assertEqual(
            [p.money.minor_units for p in reading.proposals], [6500]
        )

    def test_the_bound_is_stated_in_the_explanation(self):
        reading = read_amount("65.0", "USD", TextOrigin.recognised_glyphs)
        self.assertIn("65.00 USD", reading.explanation)
        self.assertIn("65.09 USD", reading.explanation)

    def test_a_grouped_thousand_off_a_scan_is_bounded_not_shifted(self):
        """A group of three sits where it does only for the printed
        magnitude, so '2,753' can only be missing its minor digits."""
        reading = read_amount("2,753", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.fraction_too_short)
        self.assertEqual(
            [p.money.minor_units for p in reading.proposals], [275300]
        )
        self.assertIn("2,753.00 USD", reading.explanation)
        self.assertIn("2,753.99 USD", reading.explanation)

    def test_the_same_string_from_digital_text_is_certain(self):
        """The doubt belongs to the origin, not to the shape of the string."""
        reading = read_amount("65.0", "USD", TextOrigin.digital_text_layer)
        self.assertIs(reading.suspicion, Suspicion.none)
        self.assertEqual(reading.certain, Money(6500, "USD"))


class GroupingInferredTests(unittest.TestCase):
    """A separator the currency can read either way: the one doubt that does
    not depend on where the characters came from."""

    def test_a_three_decimal_currency_keeps_both_readings(self):
        reading = read_amount("1,234", "KWD", TextOrigin.digital_text_layer)
        self.assertIs(reading.suspicion, Suspicion.grouping_inferred)
        self.assertIsNone(reading.certain)
        self.assertEqual(
            [p.money.minor_units for p in reading.proposals], [1234, 1234000]
        )

    def test_the_doubt_is_independent_of_origin(self):
        """A flawless text layer is exactly as undecided: what is missing is
        a convention the document never stated, not a dropped mark."""
        digital = read_amount("1,234", "KWD", TextOrigin.digital_text_layer)
        scanned = read_amount("1,234", "KWD", TextOrigin.recognised_glyphs)
        self.assertIs(digital.suspicion, scanned.suspicion)
        self.assertEqual(
            [p.money.minor_units for p in digital.proposals],
            [p.money.minor_units for p in scanned.proposals],
        )

    def test_a_stated_convention_removes_the_inference(self):
        """When the document's decimal separator is known there is nothing
        left to infer, and the reading settles."""
        reading = read_amount(
            "1.234",
            "KWD",
            TextOrigin.digital_text_layer,
            decimal_separator=".",
        )
        self.assertIs(reading.suspicion, Suspicion.none)
        self.assertEqual(reading.certain, Money(1234, "KWD"))

    def test_without_the_convention_the_same_string_stays_open(self):
        reading = read_amount("1.234", "KWD", TextOrigin.digital_text_layer)
        self.assertIs(reading.suspicion, Suspicion.grouping_inferred)


class RepairedReadingTests(unittest.TestCase):
    """Strings the parser rejects outright but a person reads without
    hesitating.  Both shapes were counted on the documents in hand: 32
    occurrences of one, 6 of the other."""

    def test_a_repeated_separator_is_collapsed_and_doubted(self):
        reading = read_amount("28..40", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.separator_repeated)
        self.assertIsNone(reading.certain)
        self.assertEqual(
            [p.money.minor_units for p in reading.proposals], [2840]
        )
        self.assertIn("'28.40'", reading.proposals[0].basis)

    def test_a_single_convention_resolves_a_double_separator(self):
        """'1.912.05': the last separator divides, the rest group.  There is
        exactly one way to assign the roles."""
        reading = read_amount("1.912.05", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(
            reading.suspicion, Suspicion.separator_convention_unclear
        )
        self.assertEqual(
            [p.money.minor_units for p in reading.proposals], [191205]
        )

    def test_a_repaired_reading_still_refuses_to_be_summed(self):
        for text in ("28..40", "1.912.05"):
            with self.subTest(text=text):
                reading = read_amount(
                    text, "USD", TextOrigin.recognised_glyphs
                )
                with self.assertRaises(SuspectAmountError):
                    require_certain(reading)


class UnreadableTests(unittest.TestCase):
    def test_an_unreadable_string_is_carried_not_dropped(self):
        """A row dropped for being unparseable is a transaction missing from
        the ledger, which is worse than a row with a question against it."""
        reading = read_amount("12x34", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.unreadable)
        self.assertIsNone(reading.certain)
        self.assertEqual(reading.proposals, ())
        self.assertEqual(reading.raw, "12x34")

    def test_an_empty_string_is_unreadable_not_an_error(self):
        reading = read_amount("", "USD", TextOrigin.recognised_glyphs)
        self.assertIs(reading.suspicion, Suspicion.unreadable)

    def test_the_parser_failure_is_kept_in_the_explanation(self):
        reading = read_amount("12x34", "USD", TextOrigin.recognised_glyphs)
        self.assertIn("could not be read", reading.explanation)


class ToJsonTests(unittest.TestCase):
    """The payload feeds the review queue and exhibits, so its shape and key
    order are part of the contract: a stored payload must compare equal
    between runs."""

    def test_certain_payload_shape_and_order(self):
        reading = read_amount("12.34", "USD", TextOrigin.digital_text_layer)
        payload = reading.to_json()
        self.assertEqual(
            list(payload),
            ["suspicion", "origin", "raw", "currency", "minor_units",
             "explanation"],
        )
        self.assertEqual(payload["suspicion"], "none")
        self.assertEqual(payload["origin"], "digital_text_layer")
        self.assertEqual(payload["raw"], "12.34")
        self.assertEqual(payload["currency"], "USD")
        self.assertEqual(payload["minor_units"], 1234)

    def test_suspect_payload_shape_and_order(self):
        reading = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        payload = reading.to_json()
        self.assertEqual(
            list(payload),
            ["suspicion", "origin", "raw", "currency", "proposals",
             "explanation"],
        )
        self.assertNotIn("minor_units", payload)
        self.assertEqual(
            payload["proposals"],
            [
                {"minor_units": p.money.minor_units, "basis": p.basis}
                for p in reading.proposals
            ],
        )

    def test_unreadable_payload_carries_neither_figure_nor_proposals(self):
        payload = read_amount(
            "12x34", "USD", TextOrigin.recognised_glyphs
        ).to_json()
        self.assertEqual(
            list(payload),
            ["suspicion", "origin", "raw", "currency", "explanation"],
        )

    def test_proposals_are_ordered_by_magnitude_for_stable_display(self):
        """The order carries no opinion; it exists so two runs render the
        same list."""
        for text, currency in (("1234", "USD"), ("1,234", "KWD")):
            with self.subTest(text=text, currency=currency):
                reading = read_amount(
                    text, currency, TextOrigin.recognised_glyphs
                )
                units = [p.money.minor_units for p in reading.proposals]
                self.assertEqual(units, sorted(units))


class _Rect:
    def __init__(self, width, height):
        self.width = width
        self.height = height


class _FakePage:
    """The duck-typed surface page_text_origin measures: rect, get_images,
    get_image_rects, get_text.  Built so the verdict can be exercised
    without a PDF."""

    def __init__(self, width=100.0, height=100.0, image_rects=(), text="text"):
        self.rect = _Rect(width, height)
        self._image_rects = list(image_rects)
        self._text = text

    def get_images(self, full=False):
        return [(index, "meta") for index in range(len(self._image_rects))]

    def get_image_rects(self, xref):
        return [self._image_rects[xref]]

    def get_text(self, kind):
        return self._text


class _PageWithoutRects(_FakePage):
    def get_image_rects(self, xref):
        return None


class _BrokenPage(_FakePage):
    def get_images(self, full=False):
        raise RuntimeError("cannot enumerate images")


class PageTextOriginTests(unittest.TestCase):
    def test_a_page_with_no_images_is_digital(self):
        page = _FakePage(image_rects=())
        self.assertIs(page_text_origin(page), TextOrigin.digital_text_layer)

    def test_a_full_page_raster_with_text_is_recognised(self):
        """A scan with a text layer laid over it: 51 of the 56 subpoena
        pages report exactly this."""
        page = _FakePage(image_rects=[_Rect(100.0, 100.0)])
        self.assertIs(page_text_origin(page), TextOrigin.recognised_glyphs)

    def test_a_full_page_raster_with_no_text_is_unknown(self):
        for text in ("", "   ", None):
            with self.subTest(text=repr(text)):
                page = _FakePage(
                    image_rects=[_Rect(100.0, 100.0)], text=text
                )
                self.assertIs(page_text_origin(page), TextOrigin.unknown)

    def test_coverage_below_the_threshold_is_digital(self):
        """The threshold sits in a band the corpus leaves empty; either side
        of it the verdict must be stable."""
        below = _FakePage(image_rects=[_Rect(79.0, 100.0)])
        self.assertIs(page_text_origin(below), TextOrigin.digital_text_layer)
        above = _FakePage(image_rects=[_Rect(81.0, 100.0)])
        self.assertIs(page_text_origin(above), TextOrigin.recognised_glyphs)

    def test_coverage_sums_across_images(self):
        page = _FakePage(
            image_rects=[_Rect(50.0, 100.0), _Rect(50.0, 100.0)]
        )
        self.assertIs(page_text_origin(page), TextOrigin.recognised_glyphs)

    def test_an_image_with_no_placement_covers_nothing(self):
        page = _PageWithoutRects(image_rects=[_Rect(100.0, 100.0)])
        self.assertIs(page_text_origin(page), TextOrigin.digital_text_layer)

    def test_a_zero_area_page_is_unknown(self):
        page = _FakePage(width=0.0, height=100.0)
        self.assertIs(page_text_origin(page), TextOrigin.unknown)

    def test_a_page_that_cannot_be_measured_costs_caution(self):
        """Failure returns unknown, which is fallible everywhere, so a page
        this cannot read is doubted rather than trusted."""
        self.assertIs(page_text_origin(_BrokenPage()), TextOrigin.unknown)

    def test_the_threshold_is_a_fraction_of_the_page(self):
        self.assertGreater(FULL_PAGE_IMAGE_COVERAGE, 0.0)
        self.assertLess(FULL_PAGE_IMAGE_COVERAGE, 1.0)


class OriginDecidesSummabilityTests(unittest.TestCase):
    """The pair of properties the module was built around, stated once,
    end to end: the same string, two origins, two different contracts."""

    def test_the_same_string_sums_from_one_origin_and_not_the_other(self):
        digital = read_amount("1234", "USD", TextOrigin.digital_text_layer)
        self.assertEqual(require_certain(digital), Money(123400, "USD"))
        scanned = read_amount("1234", "USD", TextOrigin.recognised_glyphs)
        with self.assertRaises(SuspectAmountError):
            require_certain(scanned)

    def test_every_suspicion_member_is_reachable_through_read_amount(self):
        """Each doubt the enum names can actually be produced; a member no
        input reaches is a category the review queue will never show."""
        produced = {
            read_amount(text, currency, origin).suspicion
            for text, currency, origin in (
                ("12.34", "USD", TextOrigin.digital_text_layer),
                ("1234", "USD", TextOrigin.recognised_glyphs),
                ("65.0", "USD", TextOrigin.recognised_glyphs),
                ("1,234", "KWD", TextOrigin.digital_text_layer),
                ("28..40", "USD", TextOrigin.recognised_glyphs),
                ("1.912.05", "USD", TextOrigin.recognised_glyphs),
                ("12x34", "USD", TextOrigin.recognised_glyphs),
            )
        }
        self.assertEqual(produced, set(Suspicion))


if __name__ == "__main__":
    unittest.main()
