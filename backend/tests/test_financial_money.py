"""Tests for the exact money value type.

The properties that matter here are not "does it usually work". They are:
nothing rounds silently, nothing returns zero on failure, no float appears on
any path, allocation never loses a unit, and anything with two valid readings
raises rather than picks one.
"""

from __future__ import annotations

import random
import unittest
from decimal import Decimal

from services.financial.money import (
    AmbiguousAmountError,
    Currency,
    CurrencyMismatchError,
    Money,
    MoneyError,
    MoneyParseError,
    PrecisionError,
    UnknownCurrencyError,
    get_currency,
    parse_amount,
    parse_money,
    sum_money,
)


class CurrencyTests(unittest.TestCase):
    def test_exponents_follow_iso_4217(self):
        self.assertEqual(get_currency("USD").exponent, 2)
        self.assertEqual(get_currency("EUR").exponent, 2)
        self.assertEqual(get_currency("GBP").exponent, 2)
        self.assertEqual(get_currency("JPY").exponent, 0)
        self.assertEqual(get_currency("KRW").exponent, 0)
        self.assertEqual(get_currency("ISK").exponent, 0)
        self.assertEqual(get_currency("KWD").exponent, 3)
        self.assertEqual(get_currency("BHD").exponent, 3)
        self.assertEqual(get_currency("TND").exponent, 3)
        self.assertEqual(get_currency("CLF").exponent, 4)

    def test_code_is_normalised(self):
        self.assertEqual(get_currency("  usd ").code, "USD")

    def test_historical_codes_are_accepted_and_flagged(self):
        deutschmark = get_currency("DEM")
        self.assertTrue(deutschmark.is_historical)
        self.assertEqual(deutschmark.exponent, 2)

        lira = get_currency("ITL")
        self.assertTrue(lira.is_historical)
        self.assertEqual(lira.exponent, 0)

        self.assertFalse(get_currency("USD").is_historical)

    def test_unknown_currency_raises_rather_than_defaulting(self):
        for bad in ("XYZ", "US", "USDD", "", "12A", None, 4):
            with self.assertRaises(UnknownCurrencyError):
                get_currency(bad)

    def test_minor_units_per_major(self):
        self.assertEqual(get_currency("USD").minor_units_per_major, 100)
        self.assertEqual(get_currency("JPY").minor_units_per_major, 1)
        self.assertEqual(get_currency("KWD").minor_units_per_major, 1000)


class MoneyConstructionTests(unittest.TestCase):
    def test_float_is_refused_at_construction(self):
        with self.assertRaises(MoneyError):
            Money(12.34, "USD")
        with self.assertRaises(MoneyError):
            Money(1234.0, "USD")

    def test_bool_is_not_an_int_here(self):
        with self.assertRaises(MoneyError):
            Money(True, "USD")

    def test_from_decimal_is_exact(self):
        self.assertEqual(
            Money.from_decimal(Decimal("12.34"), "USD"),
            Money(1234, "USD"),
        )
        self.assertEqual(
            Money.from_decimal(Decimal("1234"), "JPY"),
            Money(1234, "JPY"),
        )
        self.assertEqual(
            Money.from_decimal(Decimal("1.234"), "KWD"),
            Money(1234, "KWD"),
        )

    def test_from_decimal_refuses_to_round(self):
        with self.assertRaises(PrecisionError):
            Money.from_decimal(Decimal("10.555"), "USD")
        with self.assertRaises(PrecisionError):
            Money.from_decimal(Decimal("10.5"), "JPY")

    def test_from_decimal_rejects_non_finite_and_non_decimal(self):
        with self.assertRaises(MoneyError):
            Money.from_decimal(Decimal("NaN"), "USD")
        with self.assertRaises(MoneyError):
            Money.from_decimal(Decimal("Infinity"), "USD")
        with self.assertRaises(MoneyError):
            Money.from_decimal(12.34, "USD")

    def test_as_decimal_round_trips(self):
        for minor in (-123456, -1, 0, 1, 5, 99, 100, 123456789):
            money = Money(minor, "USD")
            self.assertEqual(Money.from_decimal(money.as_decimal(), "USD"), money)

    def test_zero_and_predicates(self):
        self.assertTrue(Money.zero("USD").is_zero)
        self.assertTrue(Money(-1, "USD").is_negative)
        self.assertTrue(Money(1, "USD").is_positive)
        self.assertFalse(Money(0, "USD").is_positive)


class FormatTests(unittest.TestCase):
    def test_formatting_is_deterministic_and_locale_free(self):
        self.assertEqual(Money(123456, "USD").format(), "1,234.56 USD")
        self.assertEqual(Money(-123456, "USD").format(), "-1,234.56 USD")
        self.assertEqual(Money(5, "USD").format(), "0.05 USD")
        self.assertEqual(Money(0, "USD").format(), "0.00 USD")
        self.assertEqual(Money(1234, "JPY").format(), "1,234 JPY")
        self.assertEqual(Money(1234, "KWD").format(), "1.234 KWD")
        self.assertEqual(
            Money(123456, "USD").format(with_currency=False), "1,234.56"
        )
        self.assertEqual(
            Money(123456, "USD").format(grouping=False), "1234.56 USD"
        )

    def test_format_parse_round_trip(self):
        # format() always writes '.' as the decimal point, so the property
        # under test is that our own rendering survives a read-back when the
        # reader is told the convention it was written in. Without that hint a
        # three-digit currency is genuinely ambiguous ("56.572" in KWD is both
        # a grouped thousand and a three-place decimal) and the parser is
        # right to refuse it.
        rng = random.Random(20260830)
        for code in ("USD", "EUR", "JPY", "KWD", "GBP", "CLF"):
            for _ in range(200):
                minor = rng.randint(-10**9, 10**9)
                money = Money(minor, code)
                self.assertEqual(
                    parse_money(money.format(), code, decimal_separator="."),
                    money,
                )


class ArithmeticTests(unittest.TestCase):
    def test_addition_and_subtraction(self):
        self.assertEqual(
            Money(1000, "USD") + Money(234, "USD"), Money(1234, "USD")
        )
        self.assertEqual(
            Money(1000, "USD") - Money(1234, "USD"), Money(-234, "USD")
        )

    def test_currency_mismatch_is_refused(self):
        with self.assertRaises(CurrencyMismatchError):
            Money(100, "USD") + Money(100, "EUR")
        with self.assertRaises(CurrencyMismatchError):
            Money(100, "USD") - Money(100, "EUR")
        with self.assertRaises(CurrencyMismatchError):
            Money(100, "USD") < Money(100, "EUR")

    def test_cannot_combine_with_non_money(self):
        with self.assertRaises(MoneyError):
            Money(100, "USD") + 100

    def test_multiplication_only_by_int(self):
        self.assertEqual(Money(100, "USD") * 3, Money(300, "USD"))
        self.assertEqual(3 * Money(100, "USD"), Money(300, "USD"))
        with self.assertRaises(MoneyError):
            Money(100, "USD") * 1.5
        with self.assertRaises(MoneyError):
            Money(100, "USD") * Decimal("1.5")

    def test_negation_and_absolute(self):
        self.assertEqual(-Money(100, "USD"), Money(-100, "USD"))
        self.assertEqual(abs(Money(-100, "USD")), Money(100, "USD"))

    def test_ordering(self):
        amounts = [Money(3, "USD"), Money(-1, "USD"), Money(2, "USD")]
        self.assertEqual(
            sorted(amounts),
            [Money(-1, "USD"), Money(2, "USD"), Money(3, "USD")],
        )

    def test_equality_is_currency_aware(self):
        self.assertNotEqual(Money(100, "USD"), Money(100, "EUR"))
        self.assertEqual(Money(100, "USD"), Money(100, "USD"))
        self.assertEqual(len({Money(100, "USD"), Money(100, "USD")}), 1)

    def test_sum_money(self):
        self.assertEqual(
            sum_money([Money(100, "USD"), Money(23, "USD")], "USD"),
            Money(123, "USD"),
        )
        self.assertEqual(sum_money([], "USD"), Money(0, "USD"))
        with self.assertRaises(CurrencyMismatchError):
            sum_money([Money(100, "EUR")], "USD")
        with self.assertRaises(MoneyError):
            sum_money([100], "USD")


class AllocateTests(unittest.TestCase):
    def test_allocation_conserves_the_total(self):
        parts = Money(100, "USD").allocate([1, 1, 1])
        self.assertEqual([p.minor_units for p in parts], [34, 33, 33])
        self.assertEqual(sum_money(parts, "USD"), Money(100, "USD"))

    def test_allocation_is_weighted(self):
        parts = Money(1000, "USD").allocate([1, 4])
        self.assertEqual([p.minor_units for p in parts], [200, 800])

    def test_allocation_of_a_negative_amount(self):
        parts = Money(-100, "USD").allocate([1, 1, 1])
        self.assertEqual([p.minor_units for p in parts], [-34, -33, -33])
        self.assertEqual(sum_money(parts, "USD"), Money(-100, "USD"))

    def test_zero_weight_receives_nothing(self):
        parts = Money(100, "USD").allocate([0, 1])
        self.assertEqual([p.minor_units for p in parts], [0, 100])

    def test_allocation_is_deterministic(self):
        first = Money(100, "USD").allocate([1, 1, 1])
        for _ in range(10):
            self.assertEqual(Money(100, "USD").allocate([1, 1, 1]), first)

    def test_allocation_never_loses_a_unit(self):
        rng = random.Random(97531)
        for _ in range(500):
            total = Money(rng.randint(-10**7, 10**7), "USD")
            weights = [rng.randint(0, 50) for _ in range(rng.randint(1, 9))]
            if sum(weights) == 0:
                weights[0] = 1
            parts = total.allocate(weights)
            self.assertEqual(sum_money(parts, "USD"), total)
            self.assertEqual(len(parts), len(weights))

    def test_invalid_weights(self):
        with self.assertRaises(MoneyError):
            Money(100, "USD").allocate([])
        with self.assertRaises(MoneyError):
            Money(100, "USD").allocate([0, 0])
        with self.assertRaises(MoneyError):
            Money(100, "USD").allocate([-1, 2])
        with self.assertRaises(MoneyError):
            Money(100, "USD").allocate([1.5, 2])


class ParseTests(unittest.TestCase):
    def test_plain_and_decorated_amounts(self):
        cases = [
            ("1234.56", "USD", 123456),
            ("1,234.56", "USD", 123456),
            ("$1,234.56", "USD", 123456),
            ("USD 1,234.56", "USD", 123456),
            ("1,234.56 USD", "USD", 123456),
            ("  1,234.56  ", "USD", 123456),
            ("0.05", "USD", 5),
            (".05", "USD", 5),
            ("12.5", "USD", 1250),
            ("12", "USD", 1200),
            ("1,234,567.89", "USD", 123456789),
            ("+1,234.56", "USD", 123456),
        ]
        for text, code, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    parse_money(text, code), Money(expected, code)
                )

    def test_european_and_spaced_conventions(self):
        cases = [
            ("1.234,56", "EUR", 123456),
            ("€1.234,56", "EUR", 123456),
            ("1 234,56", "EUR", 123456),
            ("1\u00a0234,56", "EUR", 123456),
            ("1\u202f234,56", "EUR", 123456),
            ("1 234 567,89", "EUR", 123456789),
            # Swiss statements group with an apostrophe, straight or curly.
            ("1'234.56", "CHF", 123456),
            ("1\u2019234\u2019567.89", "CHF", 123456789),
            ("CHF 1'234'567.89", "CHF", 123456789),
        ]
        for text, code, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    parse_money(text, code), Money(expected, code)
                )

    def test_a_space_that_is_not_a_group_separator_is_residue(self):
        # The space after the symbol is not between digits, so it is dropped
        # rather than validated as grouping.
        self.assertEqual(parse_money("$ 1234.56", "USD"), Money(123456, "USD"))
        self.assertEqual(parse_money("1234.56 USD", "USD"), Money(123456, "USD"))

    def test_spaced_groups_must_be_groups(self):
        for text in ("12 3456,78", "1 2345,67", "1 234 56,78"):
            with self.subTest(text=text):
                with self.assertRaises(MoneyParseError):
                    parse_money(text, "EUR")

    def test_space_grouping_is_recognised_in_the_indian_pattern_too(self):
        # "1 23 456" is a valid Indian grouping whichever character does the
        # grouping, so refusing it would be inventing a rule the notation does
        # not have. What matters is that the pattern is checked at all.
        result = parse_amount("1 23 456,78", "EUR")
        self.assertEqual(result.money, Money(12345678, "EUR"))
        self.assertEqual(result.grouping_style, "indian")
        self.assertEqual(result.grouping_separator, " ")

    def test_mixed_group_separators_are_refused(self):
        with self.assertRaises(MoneyParseError):
            parse_money("1'234 567.89", "CHF")

    def test_spaced_grouping_still_honours_currency_precision(self):
        with self.assertRaises(PrecisionError):
            parse_money("1 234.567", "CHF")

    def test_indian_grouping(self):
        self.assertEqual(
            parse_money("1,23,456.78", "INR"), Money(12345678, "INR")
        )
        self.assertEqual(
            parse_money("12,34,567.89", "INR"), Money(123456789, "INR")
        )

    def test_zero_decimal_and_three_decimal_currencies(self):
        self.assertEqual(parse_money("1,234", "JPY"), Money(1234, "JPY"))
        self.assertEqual(parse_money("1234", "JPY"), Money(1234, "JPY"))
        self.assertEqual(
            parse_money("1,234.567", "KWD"), Money(1234567, "KWD")
        )

    def test_accounting_negatives(self):
        self.assertEqual(parse_money("(1,234.56)", "USD"), Money(-123456, "USD"))
        self.assertEqual(parse_money("[1,234.56]", "USD"), Money(-123456, "USD"))
        self.assertEqual(parse_money("-1,234.56", "USD"), Money(-123456, "USD"))
        self.assertEqual(parse_money("1,234.56-", "USD"), Money(-123456, "USD"))
        self.assertEqual(parse_money("\u22121,234.56", "USD"), Money(-123456, "USD"))
        self.assertEqual(parse_money("($1,234.56)", "USD"), Money(-123456, "USD"))

    def test_double_negation_is_refused(self):
        for text in ("(-1,234.56)", "--1234.56", "-1234.56-"):
            with self.subTest(text=text):
                with self.assertRaises(MoneyParseError):
                    parse_money(text, "USD")

    def test_single_separator_with_three_digits_infers_grouping(self):
        result = parse_amount("1,234", "USD")
        self.assertEqual(result.money, Money(123400, "USD"))
        self.assertEqual(result.grouping_separator, ",")
        self.assertIsNone(result.decimal_separator)

        # The same inference under the European convention.
        result = parse_amount("1.234", "EUR")
        self.assertEqual(result.money, Money(123400, "EUR"))
        self.assertEqual(result.grouping_separator, ".")

    def test_strict_refuses_the_inferred_case(self):
        with self.assertRaises(AmbiguousAmountError):
            parse_money("1,234", "USD", strict=True)
        with self.assertRaises(AmbiguousAmountError):
            parse_money("10.555", "USD", strict=True)
        # Unambiguous input is unaffected by strict.
        self.assertEqual(
            parse_money("1,234.56", "USD", strict=True), Money(123456, "USD")
        )
        self.assertEqual(
            parse_money("1,234,567", "USD", strict=True), Money(123456700, "USD")
        )

    def test_three_digit_currency_is_always_ambiguous_here(self):
        for text in ("1,234", "1.234"):
            with self.subTest(text=text):
                with self.assertRaises(AmbiguousAmountError):
                    parse_money(text, "KWD")

    def test_decimal_separator_hint_resolves_ambiguity(self):
        self.assertEqual(
            parse_money("1,234", "KWD", decimal_separator=","),
            Money(1234, "KWD"),
        )
        self.assertEqual(
            parse_money("1,234", "KWD", decimal_separator="."),
            Money(1234000, "KWD"),
        )
        self.assertEqual(
            parse_money("1,234", "USD", decimal_separator="."),
            Money(123400, "USD"),
        )

    def test_hint_still_refuses_to_round(self):
        with self.assertRaises(PrecisionError):
            parse_money("1,234", "USD", decimal_separator=",")

    def test_precision_beyond_the_currency_is_refused(self):
        for text, code in (
            ("1234.567", "USD"),
            ("1.5", "JPY"),
            ("1,234.5678", "USD"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(PrecisionError):
                    parse_money(text, code)

    def test_malformed_input_raises_and_never_returns_zero(self):
        cases = [
            "",
            "   ",
            "abc",
            "1,234.56.78",
            "12,34,56.78",  # not a valid western or Indian grouping
            "1,23,4.56",
            "1234.",
            "1234,",
            ".",
            ",",
            "1 2 3 4 . 5 6 7",
            "(1,234.56",
            "1,234.56)",
            "USD",
            "$",
            "1234 units",
            "1e5",
            "0x10",
        ]
        for text in cases:
            with self.subTest(text=text):
                with self.assertRaises(MoneyParseError):
                    parse_money(text, "USD")

    def test_non_string_input_raises(self):
        for value in (None, 1234, 12.34, Decimal("12.34"), b"12.34", ["12"]):
            with self.subTest(value=value):
                with self.assertRaises(MoneyParseError):
                    parse_money(value, "USD")

    def test_conflicting_currency_code_in_text_is_refused(self):
        with self.assertRaises(CurrencyMismatchError):
            parse_money("EUR 1,234.56", "USD")
        with self.assertRaises(CurrencyMismatchError):
            parse_money("1,234.56 CAD", "USD")


class MarkerTests(unittest.TestCase):
    def test_marker_is_reported_but_not_applied_by_default(self):
        result = parse_amount("1,234.56 CR", "USD")
        self.assertEqual(result.marker, "CR")
        self.assertEqual(result.money, Money(123456, "USD"))

        result = parse_amount("1,234.56 DR", "USD")
        self.assertEqual(result.marker, "DR")
        self.assertEqual(result.money, Money(123456, "USD"))

    def test_marker_can_be_applied_explicitly(self):
        self.assertEqual(
            parse_amount("1,234.56 DR", "USD", apply_marker=True).money,
            Money(-123456, "USD"),
        )
        self.assertEqual(
            parse_amount("1,234.56 CR", "USD", apply_marker=True).money,
            Money(123456, "USD"),
        )

    def test_single_letter_markers(self):
        self.assertEqual(parse_amount("100.00 D", "USD").marker, "DR")
        self.assertEqual(parse_amount("100.00 C", "USD").marker, "CR")

    def test_currency_code_is_not_mistaken_for_a_marker(self):
        result = parse_amount("1,234.56 DKK", "DKK")
        self.assertIsNone(result.marker)
        self.assertEqual(result.stripped_code, "DKK")


class ProvenanceTests(unittest.TestCase):
    def test_parsed_amount_records_how_it_was_read(self):
        result = parse_amount("(€1.234,56)", "EUR")
        self.assertEqual(result.money, Money(-123456, "EUR"))
        self.assertEqual(result.decimal_separator, ",")
        self.assertEqual(result.grouping_separator, ".")
        self.assertEqual(result.grouping_style, "western")
        self.assertEqual(result.negative_style, "parentheses")
        self.assertEqual(result.stripped_symbol, "€")
        self.assertIsNone(result.stripped_code)
        self.assertEqual(result.raw, "(€1.234,56)")

    def test_indian_grouping_is_recorded_as_such(self):
        self.assertEqual(
            parse_amount("1,23,456.78", "INR").grouping_style, "indian"
        )

    def test_trailing_minus_is_distinguished_from_parentheses(self):
        self.assertEqual(
            parse_amount("1234.56-", "USD").negative_style, "trailing_minus"
        )
        self.assertEqual(
            parse_amount("-1234.56", "USD").negative_style, "leading_minus"
        )
        self.assertIsNone(parse_amount("1234.56", "USD").negative_style)


class NoFloatAnywhereTests(unittest.TestCase):
    """A float on any path is a defect, not a style preference."""

    def test_module_source_contains_no_float_conversion(self):
        import inspect

        from services.financial import money as money_module

        source = inspect.getsource(money_module)
        for banned in ("float(", "round(", "%f", "math.fsum"):
            self.assertNotIn(
                banned,
                source,
                f"{banned!r} appears in money.py; monetary values must never "
                "pass through binary floating point",
            )

    def test_large_amounts_stay_exact(self):
        # Beyond 2**53, where float64 stops being able to count.
        big = Money(9_007_199_254_740_993, "USD")
        self.assertEqual((big + Money(1, "USD")).minor_units, 9_007_199_254_740_994)
        self.assertEqual(
            parse_money(big.format(), "USD").minor_units, 9_007_199_254_740_993
        )

    def test_repeated_addition_matches_multiplication(self):
        total = Money(0, "USD")
        for _ in range(1000):
            total = total + Money(7, "USD")
        self.assertEqual(total, Money(7000, "USD"))


if __name__ == "__main__":
    unittest.main()
