"""Tests for the printed control block and the dialect it is written in.

This module guards a boundary, not a computation.  The arithmetic it performs
is addition; what it is actually for is refusing to guess.  So the tests are
mostly about the ways a plausible implementation would quietly start guessing:

* defaulting the convention, so that a caller who never decided which dialect
  a statement uses gets an answer anyway;
* trying each dialect until one closes, which produces a check that cannot
  fail and therefore is not a check;
* taking absolute values of the printed outflows, which makes ``signed`` a
  superset of ``magnitude`` and destroys the distinction the type exists to
  record;
* treating an absent balance as zero, which manufactures a delta the size of
  the real opening balance;
* reading a float through ``float`` rather than its decimal repr, which loses
  cents on values that were exact on the page.

Each is a test that fails loudly if the rule is relaxed.

The two dialects are not hypothetical.  Both appear in the corpus this system
was built against, and the documents written in the minority dialect are
arithmetically perfect: a check hard-coded to the majority reports them as the
two largest discrepancies in the case.  The figures asserted in
``test_signed_corpus_shapes`` are those documents' real ones.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from postgres.models.enums import ReconciliationStatus, TotalsConvention
from services.financial.money import AmbiguousAmountError, Money, UnknownCurrencyError
from services.financial.statement_totals import (
    CANDIDATE_CONVENTIONS,
    FIELD_ALIASES,
    INFLOW_ROLES,
    OUTFLOW_ROLES,
    ConventionError,
    HeaderTotals,
    StatementTotalsError,
    TotalsRole,
    UnreadableFigureError,
    check_header_identity,
    figure_to_money,
    infer_convention,
    is_figure,
    read_header_totals,
)

USD = "USD"


def usd(text: str) -> Money:
    return Money.from_decimal(Decimal(text), USD)


# A block in the majority dialect: outflows printed as positive magnitudes.
MAGNITUDE_BLOCK = {
    "beginning_balance": 16590.45,
    "deposits_credits": 8051.0,
    "withdrawals_debits": 5148.66,
    "checks": 19248.11,
    "service_fees": 0.0,
    "ending_balance": 244.68,
}

# A block in the minority dialect: outflows printed already negative.
SIGNED_BLOCK = {
    "beginning_balance": 133310.97,
    "deposits_credits": 6252.99,
    "withdrawals_debits": -115906.04,
    "checks": -23050.0,
    "service_fees": -821.83,
    "ending_balance": -213.91,
}


# ---------------------------------------------------------------------------
# The alias table
# ---------------------------------------------------------------------------


class AliasTableTests(unittest.TestCase):
    """The table is data, so its invariants are asserted rather than assumed."""

    def test_every_role_has_at_least_one_alias(self) -> None:
        for role in TotalsRole:
            self.assertIn(role, FIELD_ALIASES)
            self.assertTrue(FIELD_ALIASES[role])

    def test_no_field_name_appears_under_two_roles(self) -> None:
        """Overlap would make the reading order decide the meaning.

        If ``withdrawals`` were listed under both ``debits`` and
        ``other_withdrawals`` the same figure would be counted twice, and the
        resulting delta would be exactly one withdrawal total -- a number that
        looks like a missing transaction and is not one.
        """
        seen: dict[str, TotalsRole] = {}
        for role, names in FIELD_ALIASES.items():
            for name in names:
                self.assertNotIn(
                    name,
                    seen,
                    f"{name!r} is claimed by both {seen.get(name)} and {role}",
                )
                seen[name] = role

    def test_inflow_and_outflow_roles_are_disjoint_and_cover_the_flows(self) -> None:
        inflow = set(INFLOW_ROLES)
        outflow = set(OUTFLOW_ROLES)
        self.assertEqual(inflow & outflow, set())
        self.assertEqual(
            inflow | outflow | {TotalsRole.opening, TotalsRole.closing},
            set(TotalsRole),
        )

    def test_undetermined_is_not_a_candidate(self) -> None:
        """It is a recorded state, not a way of reading figures."""
        self.assertNotIn(TotalsConvention.undetermined, CANDIDATE_CONVENTIONS)
        self.assertEqual(
            set(CANDIDATE_CONVENTIONS),
            {TotalsConvention.magnitude, TotalsConvention.signed},
        )


# ---------------------------------------------------------------------------
# Reading one figure
# ---------------------------------------------------------------------------


class FigureReadingTests(unittest.TestCase):
    def test_float_is_read_through_its_decimal_repr(self) -> None:
        """``Decimal(0.07)`` is not seven cents; ``Decimal(repr(0.07))`` is.

        Every monetary value in the corpus arrives as a JSON float, so this is
        the conversion the whole module rests on.
        """
        self.assertEqual(figure_to_money(0.07, USD, field="fees"), usd("0.07"))
        self.assertEqual(
            figure_to_money(16590.45, USD, field="beginning_balance"),
            usd("16590.45"),
        )

    def test_negative_and_zero_are_readable(self) -> None:
        self.assertEqual(figure_to_money(-821.83, USD, field="f"), usd("-821.83"))
        self.assertEqual(figure_to_money(0.0, USD, field="f"), usd("0.00"))

    def test_string_and_int_are_readable(self) -> None:
        self.assertEqual(figure_to_money("1,234.50", USD, field="f"), usd("1234.50"))
        self.assertEqual(figure_to_money(42, USD, field="f"), usd("42.00"))

    def test_a_formatted_string_is_read_rather_than_rejected(self) -> None:
        """Text figures arrive with the page's formatting still attached.

        ``Decimal`` refuses every one of these.  Refusing a well-formed figure
        costs exactly what misreading one costs: the block loses a term, and a
        block missing a term has no identity left to check.
        """
        self.assertEqual(figure_to_money("$1,234.50", USD, field="f"), usd("1234.50"))
        self.assertEqual(figure_to_money(" 244.68 ", USD, field="f"), usd("244.68"))
        self.assertEqual(figure_to_money("-213.91", USD, field="f"), usd("-213.91"))

    def test_accounting_parentheses_are_a_negative_not_a_syntax_error(self) -> None:
        """The dialect this module exists for is often printed in parentheses."""
        self.assertEqual(figure_to_money("(213.91)", USD, field="f"), usd("-213.91"))

    def test_a_lone_three_digit_group_is_refused_not_inferred(self) -> None:
        """``1.234`` is one thousand or one-and-a-bit depending on the locale.

        Three orders of magnitude apart, with nothing in the figure to say
        which.  Read loosely the parser would infer grouping, since a
        three-place decimal is not representable in USD -- a reasonable default
        for free text and the wrong one here, because this block's only job is
        to be arithmetically checkable and a term off by 1000x either breaks an
        identity that was sound or closes one that was not.  The refusal is
        what keeps the decimal point a fact read from the document rather than
        a default supplied by us.
        """
        for value in ("1.234", "1,234", "10.005"):
            with self.subTest(value=value):
                with self.assertRaises(UnreadableFigureError) as caught:
                    figure_to_money(value, USD, field="f")
                self.assertIsInstance(
                    caught.exception.__cause__, AmbiguousAmountError
                )

    def test_an_unambiguous_separator_pair_is_still_read(self) -> None:
        """Strictness costs nothing where the document itself disambiguates.

        Both separators present fixes which is which, in either locale, so
        these are read rather than referred to a person.
        """
        self.assertEqual(figure_to_money("1,234.50", USD, field="f"), usd("1234.50"))
        self.assertEqual(figure_to_money("1.234,50", USD, field="f"), usd("1234.50"))

    def test_a_refusal_says_which_field_and_why(self) -> None:
        """The underlying diagnosis survives the wrapping."""
        with self.assertRaises(UnreadableFigureError) as caught:
            figure_to_money("not a number", USD, field="beginning_balance")
        self.assertIn("beginning_balance", str(caught.exception))

    def test_bool_is_refused(self) -> None:
        """``True`` is an ``int`` in Python and would silently read as $0.01."""
        with self.assertRaises(UnreadableFigureError):
            figure_to_money(True, USD, field="ok")

    def test_non_finite_is_refused(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(UnreadableFigureError):
                figure_to_money(value, USD, field="f")

    def test_excess_precision_is_refused(self) -> None:
        """A third decimal place in a USD figure is a misread, not a rounding.

        Rounding it would put a one-cent delta into the identity, which is
        indistinguishable from a real one-cent error and much harder to
        explain.  Asserted on the forms whose decimal point is unambiguous, so
        that what is being tested is the precision rule and not the separator
        inference tested below.
        """
        for value in (Decimal("10.005"), 10.005, "1,234.567"):
            with self.subTest(value=value):
                with self.assertRaises(UnreadableFigureError):
                    figure_to_money(value, USD, field="f")

    def test_is_figure_rejects_none_and_containers(self) -> None:
        self.assertTrue(is_figure(0.0))
        self.assertTrue(is_figure(-1))
        self.assertTrue(is_figure("1.00"))
        self.assertFalse(is_figure(None))
        self.assertFalse(is_figure(True))
        self.assertFalse(is_figure([1.0]))
        self.assertFalse(is_figure({"a": 1.0}))


# ---------------------------------------------------------------------------
# Normalising a block
# ---------------------------------------------------------------------------


class ReadHeaderTotalsTests(unittest.TestCase):
    def test_convention_is_required(self) -> None:
        """No default, because a default is a guess with a nice name."""
        with self.assertRaises(TypeError):
            read_header_totals(MAGNITUDE_BLOCK, currency=USD)  # type: ignore[call-arg]

    def test_undetermined_is_refused_as_a_reading_instruction(self) -> None:
        with self.assertRaises(ConventionError):
            read_header_totals(
                MAGNITUDE_BLOCK,
                currency=USD,
                convention=TotalsConvention.undetermined,
            )

    def test_roles_are_resolved_and_source_field_is_kept(self) -> None:
        totals = read_header_totals(
            MAGNITUDE_BLOCK, currency=USD, convention=TotalsConvention.magnitude
        )
        self.assertEqual(totals.opening, usd("16590.45"))
        self.assertEqual(totals.closing, usd("244.68"))
        self.assertEqual(totals.figure(TotalsRole.checks), usd("19248.11"))
        sources = {r.role: r.source_field for r in totals.inflows + totals.outflows}
        self.assertEqual(sources[TotalsRole.credits], "deposits_credits")
        self.assertEqual(sources[TotalsRole.debits], "withdrawals_debits")

    def test_unrecognised_keys_are_reported_not_dropped(self) -> None:
        """A field nobody mapped is the shape of a new institution's dialect."""
        totals = read_header_totals(
            {**MAGNITUDE_BLOCK, "average_ledger_balance": 4165.04, "notes": "hi"},
            currency=USD,
            convention=TotalsConvention.magnitude,
        )
        self.assertIn("average_ledger_balance", totals.unmapped)
        self.assertIn("notes", totals.unmapped)

    def test_a_null_alias_falls_through_to_the_next(self) -> None:
        totals = read_header_totals(
            {"beginning_balance": None, "opening": 10.0, "deposits": 1.0,
             "ending_balance": 11.0},
            currency=USD,
            convention=TotalsConvention.magnitude,
        )
        self.assertEqual(totals.opening, usd("10.00"))

    def test_block_with_balances_but_no_flows_is_not_testable(self) -> None:
        totals = read_header_totals(
            {"beginning_balance": 5.0, "ending_balance": 5.0},
            currency=USD,
            convention=TotalsConvention.magnitude,
        )
        self.assertTrue(totals.has_balances)
        self.assertFalse(totals.has_flows)
        self.assertFalse(totals.is_testable)


# ---------------------------------------------------------------------------
# The dialects, and the fact that they differ
# ---------------------------------------------------------------------------


class ConventionArithmeticTests(unittest.TestCase):
    def test_magnitude_block_closes_as_magnitude(self) -> None:
        totals = read_header_totals(
            MAGNITUDE_BLOCK, currency=USD, convention=TotalsConvention.magnitude
        )
        outcome = check_header_identity(totals)
        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.delta, usd("0.00"))
        self.assertTrue(outcome.signs_coherent)

    def test_magnitude_block_does_not_close_as_signed(self) -> None:
        """The dialects must actually disagree, or declaring one says nothing.

        Read as ``signed``, the outflows are added instead of subtracted, so
        the result misses by twice their total.  If this test ever passes as
        balanced, the two conventions have collapsed into one.
        """
        totals = read_header_totals(
            MAGNITUDE_BLOCK, currency=USD, convention=TotalsConvention.signed
        )
        outcome = check_header_identity(totals)
        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(outcome.delta, usd("48793.54"))  # 2 x 24396.77
        self.assertFalse(outcome.signs_coherent)

    def test_signed_block_closes_as_signed(self) -> None:
        totals = read_header_totals(
            SIGNED_BLOCK, currency=USD, convention=TotalsConvention.signed
        )
        outcome = check_header_identity(totals)
        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.delta, usd("0.00"))
        self.assertTrue(outcome.signs_coherent)

    def test_signed_block_read_as_magnitude_is_the_worst_answer(self) -> None:
        """The failure mode this module exists to prevent, with its real size."""
        totals = read_header_totals(
            SIGNED_BLOCK, currency=USD, convention=TotalsConvention.magnitude
        )
        outcome = check_header_identity(totals)
        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(outcome.delta, usd("279555.74"))
        self.assertFalse(outcome.signs_coherent)

    def test_outflow_is_normalised_to_a_positive_magnitude(self) -> None:
        signed = read_header_totals(
            SIGNED_BLOCK, currency=USD, convention=TotalsConvention.signed
        )
        self.assertEqual(signed.total_outflow, usd("139777.87"))
        self.assertTrue(signed.total_outflow.is_positive)

    def test_a_reversal_inside_a_signed_block_offsets_rather_than_adds(self) -> None:
        """Negating the sum, not each term.

        A fee reversed within the period is printed positive inside an
        otherwise negative block.  Summing absolute values would turn that
        credit into a second charge and break an identity that was correct.
        """
        block = {
            "beginning_balance": 1000.0,
            "deposits_credits": 0.0,
            "withdrawals_debits": -100.0,
            "service_fees": 10.0,  # a reversal
            "ending_balance": 910.0,
        }
        totals = read_header_totals(
            block, currency=USD, convention=TotalsConvention.signed
        )
        self.assertEqual(totals.total_outflow, usd("90.00"))
        self.assertIs(
            check_header_identity(totals).status, ReconciliationStatus.balanced
        )
        self.assertFalse(totals.outflow_signs_coherent)


# ---------------------------------------------------------------------------
# Declining to compute
# ---------------------------------------------------------------------------


class UnavailableTests(unittest.TestCase):
    def test_missing_opening_is_unavailable_not_zero(self) -> None:
        block = dict(MAGNITUDE_BLOCK)
        del block["beginning_balance"]
        totals = read_header_totals(
            block, currency=USD, convention=TotalsConvention.magnitude
        )
        outcome = check_header_identity(totals)
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertIsNone(outcome.delta)
        self.assertIsNone(outcome.computed_closing)
        self.assertIn("opening", outcome.unavailable_reason or "")

    def test_missing_both_balances_names_both(self) -> None:
        block = {"deposits_credits": 1.0, "withdrawals_debits": 1.0}
        outcome = check_header_identity(
            read_header_totals(
                block, currency=USD, convention=TotalsConvention.magnitude
            )
        )
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertIn("opening and closing", outcome.unavailable_reason or "")

    def test_balances_without_flows_is_unavailable(self) -> None:
        outcome = check_header_identity(
            read_header_totals(
                {"beginning_balance": 5.0, "ending_balance": 5.0},
                currency=USD,
                convention=TotalsConvention.magnitude,
            )
        )
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertIsNone(outcome.delta)


# ---------------------------------------------------------------------------
# Inference proposes; it does not decide
# ---------------------------------------------------------------------------


class InferenceTests(unittest.TestCase):
    def test_inference_returns_evidence_for_a_magnitude_block(self) -> None:
        inf = infer_convention(MAGNITUDE_BLOCK, currency=USD)
        self.assertTrue(inf.testable)
        self.assertTrue(inf.is_evidenced)
        self.assertIs(inf.proposed, TotalsConvention.magnitude)
        self.assertEqual(inf.balancing, frozenset({TotalsConvention.magnitude}))
        self.assertEqual(inf.deltas[TotalsConvention.magnitude], usd("0.00"))

    def test_inference_returns_evidence_for_a_signed_block(self) -> None:
        inf = infer_convention(SIGNED_BLOCK, currency=USD)
        self.assertTrue(inf.is_evidenced)
        self.assertIs(inf.proposed, TotalsConvention.signed)
        self.assertEqual(inf.deltas[TotalsConvention.magnitude], usd("279555.74"))

    def test_all_zero_outflows_is_ambiguous_and_proposes_undetermined(self) -> None:
        """The honest state: the document's own figures do not distinguish.

        Both dialects close, so neither is evidenced.  This is a real shape --
        one corpus document has exactly it -- and the answer is to record
        ``undetermined`` rather than to pick the commoner dialect.
        """
        block = {
            "beginning_balance": 0.0,
            "deposits": 1039.07,
            "checks": 0.0,
            "withdrawals": 0.0,
            "ending_balance": 1039.07,
        }
        inf = infer_convention(block, currency=USD)
        self.assertTrue(inf.testable)
        self.assertTrue(inf.is_ambiguous)
        self.assertFalse(inf.is_evidenced)
        self.assertIs(inf.proposed, TotalsConvention.undetermined)
        self.assertEqual(len(inf.balancing), 2)

    def test_a_block_no_dialect_explains_is_unexplained(self) -> None:
        block = dict(MAGNITUDE_BLOCK, ending_balance=250.0)
        inf = infer_convention(block, currency=USD)
        self.assertTrue(inf.testable)
        self.assertTrue(inf.is_unexplained)
        self.assertFalse(inf.is_evidenced)
        self.assertIs(inf.proposed, TotalsConvention.undetermined)
        self.assertEqual(inf.balancing, frozenset())

    def test_untestable_block_proposes_nothing(self) -> None:
        inf = infer_convention({"notes": "56 txns, pdfplumber extraction"}, currency=USD)
        self.assertFalse(inf.testable)
        self.assertIs(inf.proposed, TotalsConvention.undetermined)
        self.assertFalse(inf.is_unexplained)

    def test_inference_does_not_normalise(self) -> None:
        """It reports; it never rewrites the block or picks for the caller.

        A routine that tried each dialect until one balanced would report every
        document as balanced, including those with genuinely missing rows.
        """
        block = dict(MAGNITUDE_BLOCK)
        before = dict(block)
        infer_convention(block, currency=USD)
        self.assertEqual(block, before)


# ---------------------------------------------------------------------------
# Shapes taken from the corpus
# ---------------------------------------------------------------------------


class CorpusShapeTests(unittest.TestCase):
    """Real dialects, asserted by arithmetic rather than by quoting the case.

    The figures below are control totals only -- no party, account or
    narrative -- and they are here because they are the shapes that broke a
    fixed-formula check.
    """

    def test_signed_corpus_shapes(self) -> None:
        # Second signed document: three separate withdrawal buckets, and a
        # deposits field under an alias no other document in the corpus uses.
        block = {
            "beginning_balance": 431124.32,
            "deposits_additions": 90963.75,
            "atm_debit_withdrawals": -13781.09,
            "electronic_withdrawals": -125863.39,
            "other_withdrawals": -500.0,
            "service_charges": 0.0,
            "ending_balance": 381943.59,
        }
        inf = infer_convention(block, currency=USD)
        self.assertIs(inf.proposed, TotalsConvention.signed)
        self.assertEqual(inf.deltas[TotalsConvention.signed], usd("0.00"))
        self.assertEqual(inf.deltas[TotalsConvention.magnitude], usd("280288.96"))

    def test_multiple_outflow_buckets_sum_without_double_counting(self) -> None:
        block = {
            "beginning_balance": 100.0,
            "deposits": 50.0,
            "atm_debit_withdrawals": 10.0,
            "electronic_withdrawals": 20.0,
            "other_withdrawals": 5.0,
            "checks": 1.0,
            "service_fees": 2.0,
            "ending_balance": 112.0,
        }
        totals = read_header_totals(
            block, currency=USD, convention=TotalsConvention.magnitude
        )
        self.assertEqual(totals.total_outflow, usd("38.00"))
        self.assertIs(
            check_header_identity(totals).status, ReconciliationStatus.balanced
        )

    def test_the_shape_that_lost_its_check(self) -> None:
        """What a silently truncated re-extraction leaves behind.

        Six documents in the corpus were read a second time by a different
        extractor, which dropped rows and replaced the control block with a
        note.  The first reading balanced exactly; the second cannot be
        checked at all.  ``not testable`` is the correct verdict, and it is
        emphatically not the same as ``balanced``.
        """
        inf = infer_convention(
            {"notes": "56 txns, pdfplumber extraction"}, currency=USD
        )
        self.assertFalse(inf.testable)
        self.assertFalse(inf.is_evidenced)
        self.assertFalse(inf.is_unexplained)


class MoneyDisciplineTests(unittest.TestCase):
    def test_no_float_survives_into_the_result(self) -> None:
        totals = read_header_totals(
            MAGNITUDE_BLOCK, currency=USD, convention=TotalsConvention.magnitude
        )
        for reading in totals.inflows + totals.outflows:
            self.assertIsInstance(reading.amount, Money)
        for value in (totals.opening, totals.closing, totals.total_outflow):
            self.assertIsInstance(value, Money)

    def test_currency_is_carried_through(self) -> None:
        totals = read_header_totals(
            MAGNITUDE_BLOCK, currency="usd", convention=TotalsConvention.magnitude
        )
        self.assertEqual(totals.currency, "USD")
        self.assertEqual(totals.total_outflow.currency, "USD")

    def test_unknown_currency_is_refused(self) -> None:
        """And refused as a currency error, not as an unreadable document.

        The currency is an argument from the caller, not a figure read off the
        page, so an unrecognised code is a fault in the calling code and is
        reported as one.  Rewrapping it as a
        :class:`StatementTotalsError` would file it alongside the documents
        that genuinely could not be read, which is where a reviewer looks for
        problems with the evidence rather than problems with the pipeline.
        """
        with self.assertRaises(UnknownCurrencyError):
            read_header_totals(
                MAGNITUDE_BLOCK,
                currency="ZZZ",
                convention=TotalsConvention.magnitude,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
