"""Tests for :mod:`services.financial.correlation`.

Five things these tests exist to hold, beyond the obvious one that the
comparisons are right.

**That "contradicted" and "we do not have the records" never merge.**  This is
the failure mode with real consequences outside the software.  A contradiction
is put to a witness; an absence caused by a missing statement, dressed as a
contradiction, is a manufactured discrepancy put to a witness.  Distinguishing
them is one of the few places in this system where carelessness would do real
harm, so the separation is asserted on fact patterns that differ
in *nothing* but the completeness of the record: the same claim, the same rows,
one coverage with a gap and one without.  :class:`AbsenceMustBeEarned` holds
every one of the gates.

**That correlation never promotes.**  A corroborated P4 claim is
still P4, and the module is built so the opposite is not expressible: no code
path assigns a proof class, :class:`~services.financial.correlation.Claim`
refuses any class but p4, and
:class:`~services.financial.correlation.LedgerEntry` refuses p4 outright,
because an assertion cannot corroborate an assertion.
:class:`CorrelationNeverPromotes` asserts the invariant everywhere it could
leak.

**That materiality sits on top of the stated range and never inside it.**  A
claim of twenty thousand answered by twenty thousand and two cents is not a
finding, and a bare range comparison would make it one.  The range the witness
gave is preserved exactly and widened only at comparison time, the widening is
recorded and reported, and the arithmetic is integral throughout: a tolerance
computed in floating point would be a different tolerance on a different
machine, and this number goes into an exhibit.

**That a maybe is not an absence.**  One row that might be the payment, which
the evidence does not let us rule in or out, is enough to make the answer
unresolved.  This costs an investigator an afternoon when it is wrong, where
the opposite error costs a witness a false accusation, and the bias is meant to
run that way in every ambiguous case: an untestable name, an unanchorable
direction, a period that did not foot.

**That the module cannot be made to opine.**  AICPA SSFS No. 1 forbids opining
on whether fraud occurred, and a contradiction here is a statement about the
records rather than about the speaker.  There is no "lied", no "false", no
boolean anywhere meaning "this person is not telling the truth", and
:class:`TheModuleDoesNotOpine` holds that shape against future additions.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import date
from decimal import Decimal

from postgres.models.enums import ProofClass, TransactionDirection
from services.financial import correlation
from services.financial.correlation import (
    COMPONENT_AMOUNT,
    COMPONENT_COUNTERPARTY,
    COMPONENT_CURRENCY,
    COMPONENT_DATE,
    COMPONENT_DIRECTION,
    COMPONENT_HOLDER,
    COMPONENT_ORDER,
    DEFAULT_MATERIALITY,
    DEFAULT_MATERIALITY_BASIS_POINTS,
    DEFAULT_MATERIALITY_FLOOR_MAJOR_UNITS,
    NAME_AGREEMENT_THRESHOLD,
    NAME_COMPONENTS,
    NAME_DISAGREEMENT_THRESHOLD,
    NOTE_AMOUNT_OUTSIDE_STATED_RANGE,
    NOTE_COUNTERPARTY_UNTESTED,
    NOTE_COVERAGE_BREAK,
    NOTE_COVERAGE_GAP,
    NOTE_COVERAGE_OVERLAP,
    NOTE_COVERAGE_UNVERIFIED,
    NOTE_DIRECTION_UNANCHORED,
    NOTE_MATCHED_ONLY_UNVERIFIED,
    NOTE_NO_ACCOUNTS,
    NOTE_SCOPE_IS_PARTIAL,
    NOTE_SET_ASIDE_ON_NAME,
    NOTE_SEVERAL_MATCHES,
    AccountCoverage,
    AdjudicatedCorrelation,
    Agreement,
    AmountRange,
    CandidateVerdict,
    Claim,
    ClaimError,
    Component,
    ContradictionKind,
    Correlation,
    CorrelationDecision,
    CorrelationError,
    Coverage,
    CoverageError,
    DateRange,
    DecisionKind,
    HolderRole,
    LedgerClassError,
    LedgerEntry,
    MatchCandidate,
    Materiality,
    Outcome,
    UnresolvedReason,
    apply_decisions,
    correlate,
    correlate_all,
    coverage_from_continuity,
)
from services.financial.money import CurrencyMismatchError, Money

CR = TransactionDirection.credit
DR = TransactionDirection.debit

ACCT = uuid.UUID(int=900)
OTHER_ACCT = uuid.UUID(int=901)


def usd(major: str) -> Money:
    """A USD amount from a major-unit string.  Never a float."""
    return Money.from_decimal(Decimal(major), "USD")


def eur(major: str) -> Money:
    return Money.from_decimal(Decimal(major), "EUR")


def amounts(low: str, high: str | None = None) -> AmountRange:
    return AmountRange(usd(low), usd(high if high is not None else low))


def window(d1: int = 1, d2: int | None = None) -> DateRange:
    return DateRange(date(2024, 3, d1), date(2024, 3, d2 if d2 is not None else d1))


def a_claim(
    low: str = "20000",
    high: str | None = None,
    *,
    payer: str | None = "Whitlock",
    payee: str | None = "Halloran",
    d1: int = 1,
    d2: int = 31,
    quote: str = "I paid them in March",
    speaker: str | None = "Whitlock",
    claim_id: uuid.UUID | None = None,
    proof_class: ProofClass = ProofClass.p4,
) -> Claim:
    return Claim(
        claim_id=claim_id or uuid.uuid4(),
        amounts=amounts(low, high),
        dates=window(d1, d2),
        quote=quote,
        source_document_id=uuid.UUID(int=1),
        payer=payer,
        payee=payee,
        speaker=speaker,
        proof_class=proof_class,
    )


def a_row(
    idx: int = 1,
    amount: str = "20000",
    day: int = 15,
    *,
    direction: TransactionDirection = DR,
    holder: str | None = "Whitlock",
    counterparty: str | None = "Halloran",
    proof_class: ProofClass = ProofClass.p2,
    reconciled: bool = True,
    account_id: uuid.UUID = ACCT,
    currency: str = "USD",
) -> LedgerEntry:
    return LedgerEntry(
        transaction_id=uuid.UUID(int=idx),
        account_id=account_id,
        ordering_date=date(2024, 3, day),
        amount=Money.from_decimal(Decimal(amount), currency),
        direction=direction,
        proof_class=proof_class,
        holder=holder,
        counterparty=counterparty,
        reconciled=reconciled,
    )


def a_coverage(
    *,
    holder: str | None = "Whitlock",
    gaps=(),
    breaks=(),
    overlaps=(),
    unverified=(),
    account_id: uuid.UUID = ACCT,
    covered_from: date | None = date(2024, 1, 1),
    covered_to: date | None = date(2024, 12, 31),
) -> Coverage:
    return Coverage([
        AccountCoverage(
            account_id=account_id,
            covered_from=covered_from,
            covered_to=covered_to,
            holder=holder,
            gaps=tuple(gaps),
            breaks=tuple(breaks),
            overlaps=tuple(overlaps),
            unverified=tuple(unverified),
        )
    ])


COMPLETE = a_coverage()


# ---------------------------------------------------------------------------


class AmountRangeTests(unittest.TestCase):
    """Vagueness is preserved, not resolved."""

    def test_an_exact_claim_is_a_degenerate_range(self):
        r = amounts("20000")
        self.assertTrue(r.is_exact)
        self.assertEqual(r.low, r.high)

    def test_a_vague_claim_is_not_exact(self):
        self.assertFalse(amounts("18000", "22000").is_exact)

    def test_contains_is_inclusive_at_both_ends(self):
        r = amounts("18000", "22000")
        self.assertTrue(r.contains(usd("18000")))
        self.assertTrue(r.contains(usd("22000")))
        self.assertFalse(r.contains(usd("17999.99")))
        self.assertFalse(r.contains(usd("22000.01")))

    def test_midpoint_of_an_exact_range_is_the_amount(self):
        self.assertEqual(amounts("20000").midpoint, usd("20000"))

    def test_midpoint_of_a_span_is_the_middle(self):
        self.assertEqual(amounts("10000", "20000").midpoint, usd("15000"))

    def test_midpoint_floors_rather_than_inventing_a_sub_unit(self):
        # 0.01 and 0.02 have no representable midpoint in cents.  Rounding up
        # would push the centre of the claim past a figure the witness gave.
        self.assertEqual(amounts("0.01", "0.02").midpoint, usd("0.01"))

    def test_an_inverted_range_is_refused(self):
        with self.assertRaises(CorrelationError):
            AmountRange(usd("22000"), usd("18000"))

    def test_a_mixed_currency_range_raises_money_s_own_error(self):
        # Not a local error: the mismatch is a fact about the two amounts, and
        # inventing a correlation-specific exception would obscure that.
        with self.assertRaises(CurrencyMismatchError):
            AmountRange(usd("1"), eur("1"))

    def test_a_negative_end_is_refused(self):
        with self.assertRaises(CorrelationError):
            AmountRange(usd("-1"), usd("10"))

    def test_currency_is_read_from_the_ends(self):
        self.assertEqual(amounts("1").currency, "USD")

    def test_widening_moves_both_ends(self):
        widened = amounts("18000", "22000").widened(usd("1000"))
        self.assertEqual(widened.low, usd("17000"))
        self.assertEqual(widened.high, usd("23000"))

    def test_widening_never_produces_a_negative_low(self):
        # A claim of five dollars widened by the one-major-unit floor must not
        # start asking whether a negative amount falls in range.
        self.assertEqual(amounts("0.50").widened(usd("1")).low, usd("0"))

    def test_widening_by_zero_is_the_identity(self):
        r = amounts("18000", "22000")
        self.assertEqual(r.widened(usd("0")), r)

    def test_a_negative_tolerance_is_refused(self):
        # Widening by a negative figure would *narrow* the claim -- it would
        # hold the witness to a tighter number than the one they gave and then
        # report the resulting mismatch as a contradiction.  Materiality can
        # only ever be generous to the claim, so this raises rather than
        # silently inverting.
        with self.assertRaises(ClaimError):
            amounts("18000", "22000").widened(usd("-1000"))

    def test_format_of_an_exact_range_names_one_figure(self):
        self.assertNotIn(" to ", amounts("20000").format())

    def test_format_of_a_span_names_both(self):
        text = amounts("18000", "22000").format()
        self.assertIn("18,000.00", text)
        self.assertIn("22,000.00", text)


class DateRangeTests(unittest.TestCase):
    def test_contains_is_inclusive(self):
        r = window(1, 31)
        self.assertTrue(r.contains(date(2024, 3, 1)))
        self.assertTrue(r.contains(date(2024, 3, 31)))
        self.assertFalse(r.contains(date(2024, 2, 29)))
        self.assertFalse(r.contains(date(2024, 4, 1)))

    def test_a_single_day_is_exact(self):
        self.assertTrue(window(15).is_exact)

    def test_a_month_is_not_exact(self):
        self.assertFalse(window(1, 31).is_exact)

    def test_days_counts_both_ends(self):
        self.assertEqual(window(1, 1).days, 1)
        self.assertEqual(window(1, 31).days, 31)

    def test_an_inverted_range_is_refused(self):
        with self.assertRaises(CorrelationError):
            DateRange(date(2024, 3, 31), date(2024, 3, 1))


class MaterialityTests(unittest.TestCase):
    """The allowance sits on top of the range and is computed in integers."""

    def test_the_default_is_ten_per_cent(self):
        self.assertEqual(DEFAULT_MATERIALITY_BASIS_POINTS, 1000)

    def test_the_default_floor_is_one_major_unit(self):
        self.assertEqual(DEFAULT_MATERIALITY_FLOOR_MAJOR_UNITS, 1)

    def test_ten_per_cent_of_twenty_thousand(self):
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(amounts("20000")),
                         usd("2000"))

    def test_the_tolerance_is_taken_from_the_midpoint_not_an_end(self):
        # A range of 10,000-20,000 has a midpoint of 15,000: 1,500, not 1,000
        # and not 2,000.  Taking an end would make the allowance depend on which
        # way the witness happened to phrase the estimate.
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(amounts("10000", "20000")),
                         usd("1500"))

    def test_the_floor_applies_to_small_claims(self):
        # 10% of 3.00 is 0.30, which would make "about three dollars" a
        # findable discrepancy at 3.31.
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(amounts("3")), usd("1"))

    def test_the_floor_does_not_apply_once_the_relative_figure_exceeds_it(self):
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(amounts("100")), usd("10"))

    def test_the_arithmetic_truncates_rather_than_rounding(self):
        # 10% of 0.05 is 0.005.  There is no half-cent, and rounding up would
        # widen the claim by a unit nobody chose.  (The floor then dominates,
        # but the relative term itself must floor.)
        m = Materiality(basis_points=1000, floor_major_units=0)
        self.assertEqual(m.tolerance_for(amounts("0.05")), usd("0.00"))

    def test_it_truncates_where_the_floor_does_not_hide_the_answer(self):
        # The case above has the floor dominating, so it cannot tell truncation
        # from rounding in the figure that actually reaches the exhibit.  This
        # one can: 10% of 10.15 is 1.015, the relative term clears the
        # one-major-unit floor, and the half-cent has to go down.  Rounding up
        # here would hand the witness a cent of slack nobody granted, and the
        # difference between 1.01 and 1.02 is the difference between a
        # transaction being inside the allowance and outside it.
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(amounts("10.15")),
                         usd("1.01"))

    def test_the_arithmetic_stays_exact_at_any_magnitude(self):
        # The reason the relative term is `//` and not `/` is that a tolerance
        # computed in floating point is a different tolerance on a different
        # machine, and this number goes into an exhibit.  Below the 53-bit
        # mantissa the two agree and the bug would never show; above it the
        # float quietly gains a unit.  Money keeps arbitrary-precision integers
        # precisely so the guarantee holds without a ceiling on it, and a
        # hyperinflated currency reaches these magnitudes in ordinary matters.
        minor = 72057594037927935
        r = AmountRange(Money(minor, "USD"), Money(minor, "USD"))
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(r),
                         Money(7205759403792793, "USD"))
        # What the float would have said, pinned so the divergence is on the
        # record rather than asserted in a comment.
        self.assertEqual(int(minor * 1000 / 10000), 7205759403792794)

    def test_a_zero_basis_point_materiality_still_honours_the_floor(self):
        self.assertEqual(Materiality(basis_points=0).tolerance_for(amounts("20000")),
                         usd("1"))

    def test_a_zero_materiality_is_expressible(self):
        m = Materiality(basis_points=0, floor_major_units=0)
        self.assertEqual(m.tolerance_for(amounts("20000")), usd("0"))

    def test_the_tolerance_carries_the_claim_s_currency(self):
        r = AmountRange(eur("100"), eur("100"))
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(r).currency, "EUR")

    def test_the_floor_respects_a_three_exponent_currency(self):
        # One major unit of a three-decimal currency is 1000 minor units, not
        # 100.  A floor computed against a hardcoded exponent would be wrong by
        # a factor of ten on every dinar.
        kwd = Money.from_decimal(Decimal("3"), "KWD")
        r = AmountRange(kwd, kwd)
        self.assertEqual(DEFAULT_MATERIALITY.tolerance_for(r).minor_units, 1000)

    def test_describe_states_both_terms(self):
        text = DEFAULT_MATERIALITY.describe()
        self.assertIn("10", text)
        self.assertIn("1", text)


class ClaimTests(unittest.TestCase):
    def test_a_claim_is_p4_by_default(self):
        self.assertIs(a_claim().proof_class, ProofClass.p4)

    def test_a_claim_of_any_other_class_is_refused(self):
        # An assertion that has somehow acquired a ledger class is either a bug
        # or an attempt to launder one into the ledger through this door.
        for pc in (ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3):
            with self.subTest(pc=pc):
                with self.assertRaises(ClaimError):
                    a_claim(proof_class=pc)

    def test_an_empty_quote_is_refused(self):
        # The quote is the evidence that the claim was made at all.
        with self.assertRaises(ClaimError):
            a_claim(quote="   ")

    def test_named_parties_reports_both(self):
        self.assertEqual(set(a_claim().named_parties), {"Whitlock", "Halloran"})

    def test_named_parties_is_empty_when_nobody_is_named(self):
        self.assertEqual(a_claim(payer=None, payee=None).named_parties, ())

    def test_named_parties_ignores_a_blank_name(self):
        self.assertEqual(a_claim(payer="  ", payee=None).named_parties, ())

    def test_currency_comes_from_the_amounts(self):
        self.assertEqual(a_claim().currency, "USD")

    def test_describe_names_both_parties_and_the_window(self):
        text = a_claim().describe()
        self.assertIn("Whitlock", text)
        self.assertIn("Halloran", text)
        self.assertIn("2024-03-01", text)

    def test_describe_does_not_invent_a_name_it_was_not_given(self):
        text = a_claim(payee=None).describe()
        self.assertIn("unnamed", text)


class LedgerEntryTests(unittest.TestCase):
    def test_a_p4_ledger_entry_is_refused(self):
        # An assertion cannot corroborate an assertion.  This is the other half
        # of the never-promotes rule and it has to be enforced on the way in.
        with self.assertRaises(LedgerClassError):
            a_row(proof_class=ProofClass.p4)

    def test_every_ledger_class_is_accepted(self):
        for pc in (ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3):
            with self.subTest(pc=pc):
                self.assertIs(a_row(proof_class=pc).proof_class, pc)

    def test_a_negative_amount_is_refused(self):
        # Direction carries the sign in this system.  A negative amount with a
        # direction is two sign conventions in one row.
        with self.assertRaises(CorrelationError):
            a_row(amount="-100")

    def test_a_zero_amount_is_allowed(self):
        self.assertTrue(a_row(amount="0").amount.is_zero)

    def test_rows_are_reconciled_unless_said_otherwise(self):
        self.assertTrue(a_row().reconciled)


class CoverageTests(unittest.TestCase):
    def test_spans_requires_enclosure_at_both_ends(self):
        c = AccountCoverage(ACCT, date(2024, 3, 1), date(2024, 3, 31))
        self.assertTrue(c.spans(window(1, 31)))
        self.assertTrue(c.spans(window(5, 10)))
        self.assertFalse(c.spans(DateRange(date(2024, 2, 28), date(2024, 3, 5))))
        self.assertFalse(c.spans(DateRange(date(2024, 3, 28), date(2024, 4, 5))))

    def test_an_account_with_no_bounds_spans_nothing(self):
        self.assertFalse(AccountCoverage(ACCT).spans(window(1, 31)))

    def test_half_stated_bounds_are_refused(self):
        with self.assertRaises(CoverageError):
            AccountCoverage(ACCT, covered_from=date(2024, 1, 1))
        with self.assertRaises(CoverageError):
            AccountCoverage(ACCT, covered_to=date(2024, 1, 1))

    def test_inverted_bounds_are_refused(self):
        with self.assertRaises(CoverageError):
            AccountCoverage(ACCT, date(2024, 12, 31), date(2024, 1, 1))

    def test_an_inverted_defect_span_is_refused(self):
        for label in ("gaps", "breaks", "overlaps", "unverified"):
            with self.subTest(label=label):
                with self.assertRaises(CoverageError):
                    AccountCoverage(
                        ACCT, date(2024, 1, 1), date(2024, 12, 31),
                        **{label: [(date(2024, 3, 31), date(2024, 3, 1))]},
                    )

    def test_a_defect_touching_the_window_is_found(self):
        c = AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=[(date(2024, 3, 10), date(2024, 3, 20))])
        self.assertEqual(c.blocking_defects_in(window(1, 31)), (NOTE_COVERAGE_GAP,))

    def test_a_defect_merely_abutting_the_window_is_found(self):
        # The gap ends on the first day of the window.  A statement missing on
        # that day is missing from the window.
        c = AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=[(date(2024, 2, 1), date(2024, 3, 1))])
        self.assertEqual(c.blocking_defects_in(window(1, 31)), (NOTE_COVERAGE_GAP,))

    def test_a_defect_outside_the_window_is_not_found(self):
        c = AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=[(date(2024, 1, 5), date(2024, 1, 20))])
        self.assertEqual(c.blocking_defects_in(window(1, 31)), ())

    def test_the_three_blocking_defects_are_reported_in_a_fixed_order(self):
        span = [(date(2024, 3, 5), date(2024, 3, 6))]
        c = AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=span, breaks=span, unverified=span)
        self.assertEqual(
            c.blocking_defects_in(window(1, 31)),
            (NOTE_COVERAGE_GAP, NOTE_COVERAGE_BREAK, NOTE_COVERAGE_UNVERIFIED),
        )

    def test_an_overlap_is_reported_but_does_not_block(self):
        # Two statements claiming the same days is a duplicate-resolution
        # problem: the days are covered twice, and a row counted twice is still
        # not a row that is missing.
        c = AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            overlaps=[(date(2024, 3, 5), date(2024, 3, 10))])
        self.assertEqual(c.blocking_defects_in(window(1, 31)), ())
        self.assertIn(NOTE_COVERAGE_OVERLAP, c.defects_in(window(1, 31)))

    def test_supporting_excludes_an_account_with_a_blocking_defect(self):
        cov = a_coverage(gaps=[(date(2024, 3, 5), date(2024, 3, 10))])
        self.assertEqual(cov.supporting(window(1, 31)), ())

    def test_supporting_keeps_an_account_whose_only_flaw_is_an_overlap(self):
        cov = a_coverage(overlaps=[(date(2024, 3, 5), date(2024, 3, 10))])
        self.assertEqual(len(cov.supporting(window(1, 31))), 1)

    def test_supporting_excludes_an_account_that_does_not_reach(self):
        cov = a_coverage(covered_from=date(2024, 3, 10), covered_to=date(2024, 3, 20))
        self.assertEqual(cov.supporting(window(1, 31)), ())

    def test_defects_ignores_an_account_that_does_not_touch_the_window(self):
        cov = Coverage([
            AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 1, 31),
                            gaps=[(date(2024, 1, 5), date(2024, 1, 10))]),
        ])
        self.assertEqual(cov.defects(window(1, 31)), ())

    def test_defects_deduplicates_across_accounts(self):
        span = [(date(2024, 3, 5), date(2024, 3, 6))]
        cov = Coverage([
            AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31), gaps=span),
            AccountCoverage(OTHER_ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=span),
        ])
        self.assertEqual(cov.defects(window(1, 31)), (NOTE_COVERAGE_GAP,))

    def test_defects_skips_an_unbounded_account(self):
        cov = Coverage([AccountCoverage(ACCT)])
        self.assertEqual(cov.defects(window(1, 31)), ())

    def test_account_ids_lists_the_scope(self):
        self.assertEqual(COMPLETE.account_ids, (ACCT,))

    def test_an_empty_scope_is_legal(self):
        self.assertEqual(Coverage([]).accounts, [])


class CoverageFromContinuityTests(unittest.TestCase):
    """The join between continuity's question and correlation's."""

    def test_a_continuity_with_no_account_is_refused(self):
        from services.financial.continuity import AccountContinuity
        with self.assertRaises(CoverageError):
            coverage_from_continuity(
                AccountContinuity(account_id=None, periods=(), seams=(), excluded=())
            )

    def test_an_unbroken_run_yields_coverage_with_no_defects(self):
        from services.financial.continuity import AccountContinuity
        cont = AccountContinuity(account_id=ACCT, periods=(), seams=(), excluded=())
        cov = coverage_from_continuity(cont, holder="Whitlock")
        self.assertEqual(cov.account_id, ACCT)
        self.assertEqual(cov.holder, "Whitlock")
        self.assertEqual(cov.gaps, ())
        self.assertEqual(cov.breaks, ())

    def test_unverified_must_be_supplied_because_continuity_cannot_know_it(self):
        # Whether a period's arithmetic closed is reconcile's answer, not
        # continuity's.  A caller who passes nothing is asserting they all
        # closed, and the parameter exists so that assertion is deliberate.
        from services.financial.continuity import AccountContinuity
        cont = AccountContinuity(account_id=ACCT, periods=(), seams=(), excluded=())
        cov = coverage_from_continuity(
            cont, unverified=[(date(2024, 3, 1), date(2024, 3, 31))]
        )
        self.assertEqual(len(cov.unverified), 1)


class NameComparisonTests(unittest.TestCase):
    """Three bands, because the two errors do not cost the same."""

    def test_the_agreement_threshold_matches_linkage(self):
        from services.financial.linkage import NAME_SIMILARITY_THRESHOLD
        self.assertEqual(NAME_AGREEMENT_THRESHOLD, NAME_SIMILARITY_THRESHOLD)

    def test_the_bands_do_not_overlap(self):
        self.assertLess(NAME_DISAGREEMENT_THRESHOLD, NAME_AGREEMENT_THRESHOLD)

    def test_an_identical_name_agrees(self):
        self.assertIs(correlation._name_agreement("Halloran", "Halloran"),
                      Agreement.agrees)

    def test_case_and_spacing_do_not_matter(self):
        self.assertIs(correlation._name_agreement("  HALLORAN  ", "halloran"),
                      Agreement.agrees)

    def test_an_unrelated_name_differs(self):
        self.assertIs(correlation._name_agreement("Halloran", "Zutendaal"),
                      Agreement.differs)

    def test_a_missing_name_is_unknown_not_a_disagreement(self):
        # Absence and disagreement call for different handling: one wants more
        # evidence, the other is evidence.
        self.assertIs(correlation._name_agreement(None, "Halloran"),
                      Agreement.unknown)
        self.assertIs(correlation._name_agreement("Halloran", None),
                      Agreement.unknown)
        self.assertIs(correlation._name_agreement("   ", "Halloran"),
                      Agreement.unknown)

    def test_differing_corporate_suffixes_land_in_the_middle_band(self):
        # "ACME LTD" and "ACME INC" are probably different companies and might
        # be one company recorded twice.  Calling that a disagreement would
        # discard a row and then report the discarding as a contradiction.
        self.assertIs(correlation._name_agreement("ACME LTD", "ACME INC"),
                      Agreement.unknown)

    # The two band edges below are pinned with pairs constructed to score
    # *exactly* on the threshold, because a band is defined by where it stops.
    # An inclusive bound that quietly became exclusive would move both bands by
    # one name and never show up on a pair that scores anywhere else.

    def test_a_score_exactly_on_the_agreement_threshold_agrees(self):
        # Twenty characters each, seventeen shared: the ratio is 2*17/40, which
        # is 0.85 on the nose.
        left, right = "ABCDEFGHIJKLMNOPQXXX", "ABCDEFGHIJKLMNOPQYYY"
        from services.financial.linkage import name_similarity
        self.assertEqual(name_similarity(left, right), NAME_AGREEMENT_THRESHOLD)
        self.assertIs(correlation._name_agreement(left, right), Agreement.agrees)

    def test_a_score_exactly_on_the_disagreement_threshold_differs(self):
        left, right = "FCABCFFCD", "ABC"
        from services.financial.linkage import name_similarity
        self.assertEqual(name_similarity(left, right), NAME_DISAGREEMENT_THRESHOLD)
        self.assertIs(correlation._name_agreement(left, right), Agreement.differs)


class HolderRoleTests(unittest.TestCase):
    """Direction has no answer until you know whose account you are reading."""

    def test_the_holder_being_the_payer_settles_the_role(self):
        role, comp = correlation._resolve_role(a_claim(), a_row())
        self.assertIs(role, HolderRole.payer)
        self.assertTrue(comp.agrees)

    def test_the_holder_being_the_payee_settles_the_role(self):
        role, comp = correlation._resolve_role(
            a_claim(), a_row(holder="Halloran", counterparty="Whitlock")
        )
        self.assertIs(role, HolderRole.payee)
        self.assertTrue(comp.agrees)

    def test_a_stranger_s_account_differs(self):
        role, comp = correlation._resolve_role(
            a_claim(), a_row(holder="Zutendaal BV", counterparty="Someone Else")
        )
        self.assertIs(role, HolderRole.unknown)
        self.assertIs(comp.agreement, Agreement.differs)

    def test_a_holder_matching_both_parties_settles_nothing(self):
        # Anchoring direction on either end would be a coin toss dressed as a
        # finding.
        role, comp = correlation._resolve_role(
            a_claim(payer="Halloran", payee="Halloran"), a_row(holder="Halloran")
        )
        self.assertIs(role, HolderRole.unknown)
        self.assertIs(comp.agreement, Agreement.unknown)
        self.assertIn("both claimed parties", comp.detail)

    def test_an_ambiguous_holder_is_not_rescued_by_the_counterparty(self):
        # The case above cannot tell the guard apart from the fall-through:
        # two identical party names leave the counterparty no more able to
        # separate them than the holder was, so both paths land on unknown.
        # This one can tell them apart.  The three names are built so the
        # holder scores 0.85 against each party while the parties score only
        # 0.70 against each other -- similarity is not transitive at the band
        # edge -- and the counterparty is the payee exactly.  Ignore the
        # ambiguity and the counterparty infers a payer role.
        #
        # It must not.  The holder is direct evidence and it is equivocal;
        # reaching past it to an inference would dress a coin toss as a finding
        # and then hang the whole direction test on the result.
        holder = "ABCDEFGHIJKLMNOPQRST"
        payer = "ABCDEFGHIJKLMNOPQXXX"
        payee = "YYYDEFGHIJKLMNOPQRST"
        role, comp = correlation._resolve_role(
            a_claim(payer=payer, payee=payee),
            a_row(holder=holder, counterparty=payee),
        )
        self.assertIs(role, HolderRole.unknown)
        self.assertIs(comp.agreement, Agreement.unknown)
        self.assertIn("both claimed parties", comp.detail)

    def test_an_unnamed_holder_is_inferred_from_the_counterparty(self):
        role, comp = correlation._resolve_role(
            a_claim(), a_row(holder=None, counterparty="Halloran")
        )
        self.assertIs(role, HolderRole.payer)
        # Inferred, not observed: the component must not read as agreement.
        self.assertIs(comp.agreement, Agreement.unknown)
        self.assertIn("inferred", comp.detail)

    def test_the_inference_runs_the_other_way_too(self):
        role, comp = correlation._resolve_role(
            a_claim(), a_row(holder=None, counterparty="Whitlock")
        )
        self.assertIs(role, HolderRole.payee)
        self.assertIn("inferred", comp.detail)

    def test_nothing_at_either_end_leaves_the_role_unknown(self):
        role, comp = correlation._resolve_role(
            a_claim(), a_row(holder=None, counterparty=None)
        )
        self.assertIs(role, HolderRole.unknown)
        self.assertIs(comp.agreement, Agreement.unknown)


class DirectionTests(unittest.TestCase):
    def test_a_debit_in_the_payer_s_account_agrees(self):
        c = correlation._direction_component(HolderRole.payer, a_row(direction=DR))
        self.assertTrue(c.agrees)

    def test_a_credit_in_the_payer_s_account_differs(self):
        c = correlation._direction_component(HolderRole.payer, a_row(direction=CR))
        self.assertIs(c.agreement, Agreement.differs)

    def test_a_credit_in_the_payee_s_account_agrees(self):
        c = correlation._direction_component(HolderRole.payee, a_row(direction=CR))
        self.assertTrue(c.agrees)

    def test_a_debit_in_the_payee_s_account_differs(self):
        c = correlation._direction_component(HolderRole.payee, a_row(direction=DR))
        self.assertIs(c.agreement, Agreement.differs)

    def test_direction_is_untestable_without_a_role(self):
        c = correlation._direction_component(HolderRole.unknown, a_row())
        self.assertIs(c.agreement, Agreement.unknown)

    def test_the_same_payment_from_both_sides(self):
        # One payment, two statements.  It must corroborate from either.
        claim = a_claim()
        payer_side = correlate(claim, [a_row(direction=DR, holder="Whitlock",
                                             counterparty="Halloran")],
                               coverage=COMPLETE)
        payee_side = correlate(claim, [a_row(direction=CR, holder="Halloran",
                                             counterparty="Whitlock")],
                               coverage=a_coverage(holder="Halloran"))
        self.assertIs(payer_side.outcome, Outcome.corroborated)
        self.assertIs(payee_side.outcome, Outcome.corroborated)


class CounterpartyTests(unittest.TestCase):
    def test_the_payer_s_counterparty_should_be_the_payee(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty="Halloran"), HolderRole.payer
        )
        self.assertTrue(c.agrees)

    def test_the_payee_s_counterparty_should_be_the_payer(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty="Whitlock"), HolderRole.payee
        )
        self.assertTrue(c.agrees)

    def test_a_stranger_as_counterparty_differs(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty="Zutendaal BV"), HolderRole.payer
        )
        self.assertIs(c.agreement, Agreement.differs)

    def test_an_unnamed_counterparty_says_so_plainly(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty=None), HolderRole.payer
        )
        self.assertIs(c.agreement, Agreement.unknown)
        self.assertIn("no counterparty", c.detail)

    def test_a_claim_naming_no_payee_says_so_plainly(self):
        c = correlation._counterparty_component(
            a_claim(payee=None), a_row(counterparty="Halloran"), HolderRole.payer
        )
        self.assertIs(c.agreement, Agreement.unknown)
        self.assertIn("no payee", c.detail)

    def test_with_the_role_unsettled_either_party_will_do(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty="Halloran"), HolderRole.unknown
        )
        self.assertTrue(c.agrees)

    def test_with_the_role_unsettled_a_stranger_still_differs(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty="Zutendaal BV"), HolderRole.unknown
        )
        self.assertIs(c.agreement, Agreement.differs)

    def test_with_the_role_unsettled_and_nobody_named_it_is_unknown(self):
        c = correlation._counterparty_component(
            a_claim(), a_row(counterparty=None), HolderRole.unknown
        )
        self.assertIs(c.agreement, Agreement.unknown)


class VerdictTests(unittest.TestCase):
    """The order of the tests is the whole rule."""

    def test_an_exact_row_matches(self):
        cand = correlation._weigh(a_claim(), a_row(), materiality=DEFAULT_MATERIALITY)
        self.assertIs(cand.verdict, CandidateVerdict.matches)

    def test_another_currency_is_excluded_without_further_comparison(self):
        # An amount in another currency cannot be tested against this range
        # without a conversion, and a conversion is an analytical act that has
        # to be recorded rather than implied.
        cand = correlation._weigh(a_claim(), a_row(currency="EUR"),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertIs(cand.verdict, CandidateVerdict.excluded)
        self.assertEqual(set(cand.components), {COMPONENT_CURRENCY})

    def test_a_wrong_date_is_excluded_not_an_amount_difference(self):
        cand = correlation._weigh(a_claim(d1=1, d2=10), a_row(day=20),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertIs(cand.verdict, CandidateVerdict.excluded)

    def test_a_wrong_party_and_a_wrong_amount_is_an_exclusion(self):
        # Otherwise a payment to the wrong person for the wrong sum would be
        # reported as evidence that the claimed sum was wrong.
        cand = correlation._weigh(
            a_claim("200000"), a_row(amount="40000", counterparty="Zutendaal BV"),
            materiality=DEFAULT_MATERIALITY,
        )
        self.assertIs(cand.verdict, CandidateVerdict.excluded)

    def test_a_right_party_and_a_wrong_amount_is_an_amount_difference(self):
        cand = correlation._weigh(a_claim("200000"), a_row(amount="40000"),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertIs(cand.verdict, CandidateVerdict.differs_on_amount)

    def test_a_row_tied_to_neither_party_is_inconclusive(self):
        cand = correlation._weigh(
            a_claim(), a_row(holder=None, counterparty=None),
            materiality=DEFAULT_MATERIALITY,
        )
        self.assertIs(cand.verdict, CandidateVerdict.inconclusive)

    def test_an_untestable_direction_is_inconclusive_not_a_match(self):
        # A credit that would refute the claim is indistinguishable from the
        # debit that would support it until the role is settled.
        claim = a_claim(payer="Halloran", payee="Halloran")
        cand = correlation._weigh(claim, a_row(holder="Halloran",
                                               counterparty="Halloran"),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertIs(cand.verdict, CandidateVerdict.inconclusive)

    def test_disagreements_are_listed_in_component_order(self):
        cand = correlation._weigh(
            a_claim(d1=1, d2=10),
            a_row(day=20, amount="999999", counterparty="Zutendaal BV"),
            materiality=DEFAULT_MATERIALITY,
        )
        order = [c for c in COMPONENT_ORDER if c in cand.disagreements]
        self.assertEqual(list(cand.disagreements), order)

    def test_excluded_on_name_only_is_true_for_a_name_alone(self):
        cand = correlation._weigh(a_claim(), a_row(counterparty="Zutendaal BV"),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertTrue(cand.excluded_on_name_only)

    def test_excluded_on_name_only_is_false_when_a_date_also_differs(self):
        cand = correlation._weigh(a_claim(d1=1, d2=10),
                                  a_row(day=20, counterparty="Zutendaal BV"),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertFalse(cand.excluded_on_name_only)

    def test_excluded_on_name_only_is_false_when_nothing_differs(self):
        cand = correlation._weigh(a_claim(), a_row(),
                                  materiality=DEFAULT_MATERIALITY)
        self.assertFalse(cand.excluded_on_name_only)

    def test_explain_names_every_component_it_compared(self):
        cand = correlation._weigh(a_claim(), a_row(),
                                  materiality=DEFAULT_MATERIALITY)
        text = cand.explain()
        for name in cand.components:
            self.assertIn(name, text)

    def test_the_name_components_are_the_two_party_dimensions(self):
        self.assertEqual(NAME_COMPONENTS, frozenset({COMPONENT_HOLDER,
                                                     COMPONENT_COUNTERPARTY}))


class CorroborationTests(unittest.TestCase):
    def test_an_exact_answer_corroborates(self):
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)
        self.assertEqual(len(res.matches), 1)

    def test_corroboration_does_not_depend_on_coverage(self):
        # A payment that is in the records is in them whether or not the
        # surrounding months were ever produced.
        res = correlate(a_claim(), [a_row()],
                        coverage=a_coverage(gaps=[(date(2024, 3, 1),
                                                   date(2024, 3, 31))]))
        self.assertIs(res.outcome, Outcome.corroborated)

    def test_corroboration_works_with_no_coverage_at_all(self):
        res = correlate(a_claim(), [a_row()], coverage=Coverage([]))
        self.assertIs(res.outcome, Outcome.corroborated)

    def test_several_matches_are_noted(self):
        res = correlate(a_claim(), [a_row(1), a_row(2, day=20)], coverage=COMPLETE)
        self.assertIn(NOTE_SEVERAL_MATCHES, res.notes)

    def test_one_match_is_not_noted_as_several(self):
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertNotIn(NOTE_SEVERAL_MATCHES, res.notes)

    def test_a_match_only_within_materiality_is_declared(self):
        res = correlate(a_claim("20000"), [a_row(amount="20000.02")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)
        self.assertIn(NOTE_AMOUNT_OUTSIDE_STATED_RANGE, res.notes)

    def test_a_match_inside_the_stated_range_is_not_so_declared(self):
        res = correlate(a_claim("18000", "22000"), [a_row(amount="20000")],
                        coverage=COMPLETE)
        self.assertNotIn(NOTE_AMOUNT_OUTSIDE_STATED_RANGE, res.notes)

    def test_the_note_is_raised_when_any_match_needed_the_allowance(self):
        res = correlate(a_claim("20000"),
                        [a_row(1, amount="20000"),
                         a_row(2, amount="20000.02", day=20)],
                        coverage=COMPLETE)
        self.assertIn(NOTE_AMOUNT_OUTSIDE_STATED_RANGE, res.notes)

    def test_corroboration_by_an_unreconciled_row_alone_is_declared(self):
        res = correlate(a_claim(), [a_row(proof_class=ProofClass.p3,
                                          reconciled=False)],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)
        self.assertIn(NOTE_MATCHED_ONLY_UNVERIFIED, res.notes)

    def test_a_reconciled_match_alongside_removes_that_qualification(self):
        res = correlate(a_claim(),
                        [a_row(1, reconciled=False, proof_class=ProofClass.p3),
                         a_row(2, day=20)],
                        coverage=COMPLETE)
        self.assertNotIn(NOTE_MATCHED_ONLY_UNVERIFIED, res.notes)

    def test_an_untested_counterparty_is_declared_but_not_fatal(self):
        # Bank CSVs frequently carry no parsed counterparty.  Requiring one
        # would make almost everything inconclusive and kill the feature; not
        # saying so would let untested read as tested.
        res = correlate(a_claim(), [a_row(counterparty=None)], coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)
        self.assertIn(NOTE_COUNTERPARTY_UNTESTED, res.notes)

    def test_a_tested_counterparty_carries_no_such_note(self):
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertNotIn(NOTE_COUNTERPARTY_UNTESTED, res.notes)

    def test_a_corroboration_carries_no_contradiction_kind(self):
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertIsNone(res.contradiction)
        self.assertIsNone(res.unresolved_reason)

    def test_a_corroboration_names_no_accounts_relied_on(self):
        # Only an absence rests on the completeness of a record.
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertEqual(res.accounts_relied_on, ())


class AbsenceMustBeEarned(unittest.TestCase):
    """Every gate between "no matching row" and "contradicted"."""

    def test_the_headline_finding(self):
        # A subject saying they paid $200,000 when the ledger shows $40,000 is
        # exactly what an investigator is looking for.
        res = correlate(a_claim("200000"), [a_row(amount="40000")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)
        self.assertIs(res.contradiction, ContradictionKind.amount_differs)

    def test_an_absence_over_complete_records_contradicts(self):
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)
        self.assertIs(res.contradiction, ContradictionKind.no_transaction)

    def test_a_gap_turns_the_same_facts_into_unresolved(self):
        res = correlate(a_claim("200000"), [a_row(amount="40000")],
                        coverage=a_coverage(gaps=[(date(2024, 3, 10),
                                                   date(2024, 3, 20))]))
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIs(res.unresolved_reason, UnresolvedReason.records_incomplete)

    def test_a_break_turns_the_same_facts_into_unresolved(self):
        res = correlate(a_claim("200000"), [a_row(amount="40000")],
                        coverage=a_coverage(breaks=[(date(2024, 3, 10),
                                                     date(2024, 3, 11))]))
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIn(NOTE_COVERAGE_BREAK, res.notes)

    def test_an_unreconciled_period_turns_them_into_unresolved(self):
        # A period that does not foot may be missing rows -- that is frequently
        # why it does not foot.
        res = correlate(a_claim("200000"), [a_row(amount="40000")],
                        coverage=a_coverage(unverified=[(date(2024, 3, 1),
                                                         date(2024, 3, 31))]))
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIn(NOTE_COVERAGE_UNVERIFIED, res.notes)

    def test_an_overlap_alone_does_not_block_the_finding(self):
        res = correlate(a_claim("200000"), [], coverage=a_coverage(
            overlaps=[(date(2024, 3, 5), date(2024, 3, 10))]))
        self.assertIs(res.outcome, Outcome.contradicted)

    def test_coverage_that_does_not_reach_the_window_blocks_it(self):
        res = correlate(a_claim("200000"), [], coverage=a_coverage(
            covered_from=date(2024, 3, 10), covered_to=date(2024, 3, 20)))
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIs(res.unresolved_reason, UnresolvedReason.outside_coverage)

    def test_an_empty_scope_blocks_it(self):
        res = correlate(a_claim("200000"), [], coverage=Coverage([]))
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIs(res.unresolved_reason, UnresolvedReason.outside_coverage)
        self.assertIn(NOTE_NO_ACCOUNTS, res.notes)

    def test_one_inconclusive_row_blocks_it(self):
        # A maybe is not an absence.
        res = correlate(
            a_claim("200000"),
            [LedgerEntry(uuid.UUID(int=7), ACCT, date(2024, 3, 15),
                         usd("200000"), DR, ProofClass.p2)],
            coverage=COMPLETE,
        )
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIs(res.unresolved_reason,
                      UnresolvedReason.candidate_inconclusive)

    def test_an_inconclusive_row_outranks_an_amount_difference(self):
        res = correlate(
            a_claim("200000"),
            [a_row(1, amount="40000"),
             LedgerEntry(uuid.UUID(int=7), ACCT, date(2024, 3, 16),
                         usd("200000"), DR, ProofClass.p2)],
            coverage=COMPLETE,
        )
        self.assertIs(res.outcome, Outcome.unresolved)

    def test_an_untestable_claim_blocks_it(self):
        # A claim naming nobody, against rows naming nobody, would assert that
        # no payment of roughly this size happened anywhere.
        res = correlate(a_claim("200000", payer=None, payee=None), [],
                        coverage=a_coverage(holder=None))
        self.assertIs(res.outcome, Outcome.unresolved)
        self.assertIs(res.unresolved_reason, UnresolvedReason.claim_not_testable)

    def test_a_claim_naming_one_party_is_testable(self):
        res = correlate(a_claim("200000", payee=None), [], coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)

    def test_an_anonymous_claim_against_a_named_account_is_testable(self):
        # "No payment of this size left this account" is a sentence with a
        # subject even when the claim named nobody, so testability is satisfied
        # -- but testability is only one of the four gates, and here every row
        # is excluded on its date, so nothing is left open and the finding
        # stands.
        stale = LedgerEntry(uuid.UUID(int=91), ACCT, date(2023, 1, 5),
                            usd("1"), DR, ProofClass.p2, holder="Whitlock")
        res = correlate(a_claim("200000", payer=None, payee=None), [stale],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)

    def test_a_live_row_leaves_an_anonymous_claim_open(self):
        # The counterpart to the above, and the more important half.  A claim
        # naming nobody gives the row nothing to be compared against: no name
        # component can agree, so the row can be neither matched nor ruled out.
        # Asserting absence while holding a row in that state would be a
        # contradiction that was never earned, so it does not happen -- for the
        # row that fits the claimed sum as much as for the row that does not.
        for label, amount in (("the wrong sum", "1"), ("the claimed sum", "200000")):
            with self.subTest(label):
                res = correlate(
                    a_claim("200000", payer=None, payee=None),
                    [a_row(amount=amount, holder="Whitlock")],
                    coverage=COMPLETE,
                )
                self.assertIs(res.outcome, Outcome.unresolved)
                self.assertIs(res.unresolved_reason,
                              UnresolvedReason.candidate_inconclusive)

    def test_an_anonymous_claim_is_never_corroborated(self):
        # Falls out of the same rule and is worth stating outright: a claim that
        # names nobody cannot be confirmed by a row either.  A payment of the
        # right size in the right month is not evidence for an assertion that
        # identified no one, and reporting it as corroboration would put weight
        # on a coincidence.
        res = correlate(a_claim("200000", payer=None, payee=None),
                        [a_row(amount="200000", holder="Whitlock")],
                        coverage=COMPLETE)
        self.assertIsNot(res.outcome, Outcome.corroborated)

    def test_a_contradiction_names_the_accounts_it_rests_on(self):
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        self.assertEqual(res.accounts_relied_on, (ACCT,))

    def test_an_amount_contradiction_names_them_too(self):
        # Both contradiction branches assert an absence -- one says no such
        # payment is in these records at all, the other says the payment that
        # is there was for a different sum -- and neither means anything
        # without the scope it was found in.  The amount branch carries the
        # headline finding and is the one most likely to be quoted, so it is
        # pinned separately rather than left to ride on the other branch's
        # coverage.
        res = correlate(a_claim("200000"), [a_row(amount="40000")],
                        coverage=COMPLETE)
        self.assertIs(res.contradiction, ContradictionKind.amount_differs)
        self.assertEqual(res.accounts_relied_on, (ACCT,))

    def test_a_contradiction_names_only_the_supporting_accounts(self):
        cov = Coverage([
            AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            holder="Whitlock"),
            AccountCoverage(OTHER_ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=[(date(2024, 3, 5), date(2024, 3, 6))]),
        ])
        res = correlate(a_claim("200000"), [], coverage=cov)
        self.assertIs(res.outcome, Outcome.contradicted)
        self.assertEqual(res.accounts_relied_on, (ACCT,))

    def test_a_contradiction_states_that_the_scope_is_partial(self):
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        self.assertIn(NOTE_SCOPE_IS_PARTIAL, res.notes)

    def test_a_contradiction_carries_no_defect_note_from_another_account(self):
        # Every account this finding rests on spans the window cleanly.  A note
        # raised by some other account would read as a qualification of the
        # finding when it qualifies nothing.
        cov = Coverage([
            AccountCoverage(ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            holder="Whitlock"),
            AccountCoverage(OTHER_ACCT, date(2024, 1, 1), date(2024, 12, 31),
                            gaps=[(date(2024, 3, 5), date(2024, 3, 6))]),
        ])
        res = correlate(a_claim("200000"), [], coverage=cov)
        self.assertNotIn(NOTE_COVERAGE_GAP, res.notes)

    def test_a_contradiction_discloses_what_it_set_aside_on_a_name(self):
        # A finding of absence that hides its own exclusions is not a finding
        # anybody should sign.
        res = correlate(a_claim("200000"),
                        [a_row(amount="200000", counterparty="Zutendaal BV")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)
        self.assertIn(NOTE_SET_ASIDE_ON_NAME, res.notes)
        self.assertEqual(len(res.set_aside_on_name), 1)

    def test_a_row_excluded_on_a_date_is_not_a_name_exclusion(self):
        res = correlate(a_claim("200000", d1=1, d2=10),
                        [a_row(amount="200000", day=20)], coverage=COMPLETE)
        self.assertNotIn(NOTE_SET_ASIDE_ON_NAME, res.notes)


class MaterialityInCorrelationTests(unittest.TestCase):
    def test_two_cents_over_an_exact_claim_is_not_a_finding(self):
        res = correlate(a_claim("20000"), [a_row(amount="20000.02")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)

    def test_just_inside_the_allowance_corroborates(self):
        res = correlate(a_claim("20000"), [a_row(amount="22000")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)

    def test_just_outside_the_allowance_contradicts(self):
        res = correlate(a_claim("20000"), [a_row(amount="22000.01")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)

    def test_the_allowance_widens_a_range_rather_than_replacing_it(self):
        # 18,000-22,000 has a midpoint of 20,000, so the allowance is 2,000 and
        # the effective band is 16,000-24,000.
        res = correlate(a_claim("18000", "22000"), [a_row(amount="16000")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)
        res = correlate(a_claim("18000", "22000"), [a_row(amount="15999.99")],
                        coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.contradicted)

    def test_a_stricter_materiality_can_be_supplied(self):
        strict = Materiality(basis_points=0, floor_major_units=0)
        res = correlate(a_claim("20000"), [a_row(amount="20000.02")],
                        coverage=COMPLETE, materiality=strict)
        self.assertIs(res.outcome, Outcome.contradicted)

    def test_the_tolerance_actually_applied_is_recorded(self):
        # It goes into a report and has to be arguable.
        res = correlate(a_claim("20000"), [a_row()], coverage=COMPLETE)
        self.assertEqual(res.tolerance, usd("2000"))

    def test_the_materiality_used_is_recorded(self):
        strict = Materiality(basis_points=100)
        res = correlate(a_claim("20000"), [a_row()], coverage=COMPLETE,
                        materiality=strict)
        self.assertEqual(res.materiality, strict)


class CorrelationNeverPromotes(unittest.TestCase):
    """The invariant, asserted everywhere it could leak."""

    def test_a_corroborated_claim_is_still_p4(self):
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertIs(res.outcome, Outcome.corroborated)
        self.assertIs(res.claim_proof_class, ProofClass.p4)
        self.assertIs(res.claim.proof_class, ProofClass.p4)

    def test_a_claim_corroborated_by_a_p0_row_is_still_p4(self):
        res = correlate(a_claim(), [a_row(proof_class=ProofClass.p0)],
                        coverage=COMPLETE)
        self.assertIs(res.claim_proof_class, ProofClass.p4)

    def test_many_corroborations_do_not_promote_either(self):
        rows = [a_row(i, day=10 + i) for i in range(1, 6)]
        res = correlate(a_claim(), rows, coverage=COMPLETE)
        self.assertEqual(len(res.matches), 5)
        self.assertIs(res.claim_proof_class, ProofClass.p4)

    def test_the_corroborating_rows_keep_their_own_classes(self):
        res = correlate(a_claim(), [a_row(proof_class=ProofClass.p1)],
                        coverage=COMPLETE)
        self.assertIs(res.matches[0].entry.proof_class, ProofClass.p1)

    def test_no_function_in_the_module_returns_a_proof_class(self):
        # The invariant is structural: there is nowhere to assign a class.
        import inspect
        for name, obj in vars(correlation).items():
            if not inspect.isfunction(obj) or obj.__module__ != correlation.__name__:
                continue
            hints = getattr(obj, "__annotations__", {})
            with self.subTest(fn=name):
                self.assertNotIn("ProofClass", str(hints.get("return", "")))

    def test_the_narrative_says_so_in_words(self):
        res = correlate(a_claim(), [a_row()], coverage=COMPLETE)
        self.assertIn("does not promote", res.narrative())


class TheModuleDoesNotOpine(unittest.TestCase):
    """A contradiction is about the records, never about the speaker."""

    FORBIDDEN = (
        "lied", "lying", "false", "fraud", "dishonest", "deceit",
        "misrepresent", "perjur", "guilty", "culpab",
    )

    def test_no_outcome_names_a_state_of_mind(self):
        for member in Outcome:
            for word in self.FORBIDDEN:
                with self.subTest(member=member, word=word):
                    self.assertNotIn(word, member.value.lower())

    def test_no_contradiction_kind_names_one_either(self):
        for member in ContradictionKind:
            for word in self.FORBIDDEN:
                self.assertNotIn(word, member.value.lower())

    def test_the_narrative_disclaims_it_explicitly(self):
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        self.assertIn("about the records, not about", res.narrative())

    def test_the_narrative_of_a_contradiction_names_its_limits(self):
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        text = res.narrative()
        self.assertIn("limited to account(s)", text)
        self.assertIn("without gap, break or unreconciled period", text)

    def test_the_speaker_is_named_without_characterisation(self):
        res = correlate(a_claim("200000", speaker="Whitlock"), [],
                        coverage=COMPLETE)
        self.assertIn("not about Whitlock", res.narrative())

    def test_an_unattributed_claim_does_not_acquire_a_speaker(self):
        res = correlate(a_claim("200000", speaker=None), [], coverage=COMPLETE)
        self.assertIn("unattributed", res.narrative())

    def test_no_note_names_a_state_of_mind(self):
        notes = [v for k, v in vars(correlation).items()
                 if k.startswith("NOTE_") and isinstance(v, str)]
        self.assertTrue(notes)
        for note in notes:
            for word in self.FORBIDDEN:
                with self.subTest(note=note, word=word):
                    self.assertNotIn(word, note.lower())


class ResultShapeTests(unittest.TestCase):
    def test_a_contradiction_must_name_its_kind(self):
        with self.assertRaises(CorrelationError):
            Correlation(claim=a_claim(), outcome=Outcome.contradicted)

    def test_an_unresolved_must_name_its_reason(self):
        with self.assertRaises(CorrelationError):
            Correlation(claim=a_claim(), outcome=Outcome.unresolved)

    def test_only_a_contradiction_carries_a_kind(self):
        with self.assertRaises(CorrelationError):
            Correlation(claim=a_claim(), outcome=Outcome.corroborated,
                        contradiction=ContradictionKind.no_transaction)

    def test_only_an_unresolved_carries_a_reason(self):
        with self.assertRaises(CorrelationError):
            Correlation(claim=a_claim(), outcome=Outcome.corroborated,
                        unresolved_reason=UnresolvedReason.outside_coverage)

    def test_a_contradiction_does_not_also_carry_a_reason(self):
        with self.assertRaises(CorrelationError):
            Correlation(claim=a_claim(), outcome=Outcome.contradicted,
                        contradiction=ContradictionKind.no_transaction,
                        unresolved_reason=UnresolvedReason.outside_coverage)

    def test_is_finding_covers_both_findings(self):
        self.assertTrue(correlate(a_claim(), [a_row()],
                                  coverage=COMPLETE).is_finding)
        self.assertTrue(correlate(a_claim("200000"), [],
                                  coverage=COMPLETE).is_finding)

    def test_is_finding_is_false_for_unresolved(self):
        self.assertFalse(correlate(a_claim("200000"), [],
                                   coverage=Coverage([])).is_finding)

    def test_by_verdict_partitions_the_candidates(self):
        res = correlate(
            a_claim("200000"),
            [a_row(1, amount="200000", counterparty="Zutendaal BV"),
             a_row(2, amount="40000", day=16),
             LedgerEntry(uuid.UUID(int=3), ACCT, date(2024, 3, 17),
                         usd("200000"), DR, ProofClass.p2)],
            coverage=COMPLETE,
        )
        total = (len(res.matches) + len(res.amount_differences)
                 + len(res.inconclusive) + len(res.excluded))
        self.assertEqual(total, len(res.candidates))

    def test_the_candidates_are_kept_in_the_order_supplied(self):
        rows = [a_row(3, day=20), a_row(1, day=10), a_row(2, day=15)]
        res = correlate(a_claim(), rows, coverage=COMPLETE)
        self.assertEqual([c.entry.transaction_id for c in res.candidates],
                         [r.transaction_id for r in rows])

    def test_the_narrative_omits_excluded_rows_from_the_workings(self):
        # An excluded row is disclosed by count and note; printing every
        # unrelated transaction in the account would bury the finding.
        res = correlate(a_claim("200000"),
                        [a_row(amount="200000", counterparty="Zutendaal BV")],
                        coverage=COMPLETE)
        self.assertNotIn("Zutendaal", res.narrative())

    def test_the_narrative_quotes_the_claim(self):
        res = correlate(a_claim(quote="I paid them two hundred grand"), [],
                        coverage=COMPLETE)
        self.assertIn("I paid them two hundred grand", res.narrative())

    def test_the_narrative_reports_notes_deterministically(self):
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        self.assertEqual(res.narrative(), res.narrative())


class CorrelateAllTests(unittest.TestCase):
    def test_every_claim_gets_an_answer(self):
        out = correlate_all([a_claim(), a_claim("200000")], [a_row()],
                            coverage=COMPLETE)
        self.assertEqual(len(out), 2)

    def test_a_transaction_is_not_consumed_by_the_first_claim(self):
        # Two people describing the same payment should both be corroborated by
        # it.  A scheme that spent the row on whoever was processed first would
        # make the answer depend on the order of an interview schedule.
        c1, c2 = a_claim(quote="I paid twenty"), a_claim(quote="he paid twenty")
        out = correlate_all([c1, c2], [a_row()], coverage=COMPLETE)
        self.assertEqual([r.outcome for r in out],
                         [Outcome.corroborated, Outcome.corroborated])

    def test_the_answers_do_not_depend_on_the_order_of_the_claims(self):
        c1, c2 = a_claim(quote="one"), a_claim("200000", quote="two")
        forward = {r.claim.quote: r.outcome
                   for r in correlate_all([c1, c2], [a_row()], coverage=COMPLETE)}
        backward = {r.claim.quote: r.outcome
                    for r in correlate_all([c2, c1], [a_row()], coverage=COMPLETE)}
        self.assertEqual(forward, backward)

    def test_the_order_of_the_results_follows_the_order_given(self):
        c1, c2 = a_claim(quote="one"), a_claim(quote="two")
        out = correlate_all([c1, c2], [], coverage=COMPLETE)
        self.assertEqual([r.claim.quote for r in out], ["one", "two"])

    def test_no_claims_yields_no_results(self):
        self.assertEqual(correlate_all([], [a_row()], coverage=COMPLETE), ())


class DecisionTests(unittest.TestCase):
    """A human confirms, and silence is not confirmation."""

    def setUp(self):
        self.claim = a_claim()
        self.res = correlate(self.claim, [a_row()], coverage=COMPLETE)

    def _decision(self, kind=DecisionKind.confirmed, by="N. Byrne", **kw):
        return CorrelationDecision(self.claim.claim_id, kind, by,
                                   date(2024, 4, 1), **kw)

    def test_an_undecided_proposal_does_not_stand(self):
        # A surface whose unreviewed proposals counted as accepted would be the
        # auto-confirmation this module exists to resist, arrived at by
        # leaving the queue alone.
        adj = apply_decisions(self.res, [])
        self.assertFalse(adj.stands)
        self.assertFalse(adj.is_decided)

    def test_a_confirmed_proposal_stands(self):
        adj = apply_decisions(self.res, [self._decision()])
        self.assertTrue(adj.stands)
        self.assertTrue(adj.is_decided)

    def test_a_rejected_proposal_does_not_stand(self):
        adj = apply_decisions(self.res, [self._decision(DecisionKind.rejected)])
        self.assertFalse(adj.stands)
        self.assertTrue(adj.is_decided)

    def test_one_rejection_defeats_a_confirmation(self):
        adj = apply_decisions(self.res, [
            self._decision(),
            self._decision(DecisionKind.rejected, by="R. Ng"),
        ])
        self.assertFalse(adj.stands)

    def test_the_order_of_the_decisions_does_not_change_that(self):
        adj = apply_decisions(self.res, [
            self._decision(DecisionKind.rejected, by="R. Ng"),
            self._decision(),
        ])
        self.assertFalse(adj.stands)

    def test_confirmed_and_rejected_are_listed_separately(self):
        adj = apply_decisions(self.res, [
            self._decision(),
            self._decision(DecisionKind.rejected, by="R. Ng"),
        ])
        self.assertEqual(len(adj.confirmed), 1)
        self.assertEqual(len(adj.rejected), 1)

    def test_an_anonymous_decision_is_refused(self):
        # An anonymous confirmation is indistinguishable from the system
        # confirming itself.
        with self.assertRaises(CorrelationError):
            CorrelationDecision(self.claim.claim_id, DecisionKind.confirmed,
                                "   ", date(2024, 4, 1))

    def test_a_decision_for_another_claim_is_refused(self):
        # Silently dropping it would attach a person's name to a conclusion
        # they did not reach on a claim they may never have seen.
        stray = CorrelationDecision(uuid.uuid4(), DecisionKind.confirmed,
                                    "N. Byrne", date(2024, 4, 1))
        with self.assertRaises(CorrelationError):
            apply_decisions(self.res, [stray])

    def test_a_decision_naming_an_unweighed_transaction_is_refused(self):
        with self.assertRaises(CorrelationError):
            apply_decisions(self.res,
                            [self._decision(transaction_id=uuid.UUID(int=999))])

    def test_a_decision_naming_a_weighed_transaction_is_accepted(self):
        adj = apply_decisions(self.res,
                              [self._decision(transaction_id=uuid.UUID(int=1))])
        self.assertTrue(adj.stands)

    def test_the_proposal_survives_adjudication_unchanged(self):
        adj = apply_decisions(self.res, [self._decision()])
        self.assertIs(adj.proposal, self.res)
        self.assertIs(adj.proposal.claim_proof_class, ProofClass.p4)

    def test_confirming_a_correlation_still_does_not_promote_the_claim(self):
        adj = apply_decisions(self.res, [self._decision()])
        self.assertTrue(adj.stands)
        self.assertIs(adj.proposal.claim.proof_class, ProofClass.p4)


class RefusalTests(unittest.TestCase):
    def test_correlate_refuses_something_that_is_not_a_claim(self):
        with self.assertRaises(ClaimError):
            correlate(object(), [], coverage=COMPLETE)

    def test_correlate_refuses_something_that_is_not_a_coverage(self):
        with self.assertRaises(CoverageError):
            correlate(a_claim(), [], coverage=object())

    def test_the_errors_share_a_base(self):
        for err in (ClaimError, LedgerClassError, CoverageError):
            with self.subTest(err=err):
                self.assertTrue(issubclass(err, CorrelationError))


class DirectionUnanchoredTests(unittest.TestCase):
    def test_rows_with_no_holder_anywhere_raise_the_note(self):
        res = correlate(
            a_claim(),
            [LedgerEntry(uuid.UUID(int=8), ACCT, date(2024, 3, 15), usd("20000"),
                         DR, ProofClass.p2, counterparty="Halloran")],
            coverage=COMPLETE,
        )
        self.assertIn(NOTE_DIRECTION_UNANCHORED, res.notes)

    def test_one_named_holder_is_enough_to_clear_it(self):
        res = correlate(
            a_claim(),
            [LedgerEntry(uuid.UUID(int=8), ACCT, date(2024, 3, 15), usd("20000"),
                         DR, ProofClass.p2, counterparty="Halloran"),
             a_row(9, day=16)],
            coverage=COMPLETE,
        )
        self.assertNotIn(NOTE_DIRECTION_UNANCHORED, res.notes)

    def test_no_rows_at_all_does_not_raise_it(self):
        # There is nothing to be unanchored about.
        res = correlate(a_claim("200000"), [], coverage=COMPLETE)
        self.assertNotIn(NOTE_DIRECTION_UNANCHORED, res.notes)


class PackageSurfaceTests(unittest.TestCase):
    def test_everything_is_exported(self):
        import services.financial as F
        for name in ("correlate", "correlate_all", "Claim", "LedgerEntry",
                     "Coverage", "AccountCoverage", "Correlation", "Outcome",
                     "ContradictionKind", "UnresolvedReason", "Materiality",
                     "MatchCandidate", "apply_decisions"):
            with self.subTest(name=name):
                self.assertIn(name, F.__all__)
                self.assertTrue(hasattr(F, name))

    def test_the_match_candidate_name_does_not_collide_with_quarantine_s(self):
        import services.financial as F
        from services.financial.quarantine import Candidate as QuarantineCandidate
        self.assertIs(F.Candidate, QuarantineCandidate)
        self.assertIs(F.MatchCandidate, MatchCandidate)
        self.assertIsNot(F.Candidate, F.MatchCandidate)


if __name__ == "__main__":
    unittest.main()
