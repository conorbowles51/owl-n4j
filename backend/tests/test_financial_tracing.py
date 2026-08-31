"""Tests for :mod:`services.financial.tracing`.

Five things these tests exist to hold, beyond the obvious one that the
arithmetic adds up.

**That the doctrines actually disagree.**  This is the failure mode with no
downstream detector, and it is the one a tracing engine falls into by default.
Five code paths that all return the same numbers are one doctrine wearing five
labels, and nothing else in the system would notice: every total still foots,
every claim still balances, the report still names a doctrine and cites a case.
The output would simply be a presumption applied under whichever name the
analyst picked, which is precisely the invisible legal choice `12` §4.5 says is
"indefensible under cross-examination in about one question".  So the divergence
is asserted directly, on the fact patterns the authorities were decided on, and
:class:`DoctrinesMustDisagree` exists to fail loudly if any two doctrines ever
collapse into each other.

**That the safe direction is downward.**  Classifying a source one proof class
too low costs an adjudication; one too high puts an unchecked row inside a
total.  Tracing has the same asymmetry with a sharper edge: a doctrine that
over-attributes says a claimant's money paid for something when it may not
have.  Every ambiguity here therefore resolves toward saying less -- direct
tracing declines a contested match rather than picking, an unfunded withdrawal
is reported rather than absorbed, and no doctrine traces into an overdraft.

**That declining to find is not the same as finding nothing.**  Direct tracing
reaches no conclusion far more often than the presumptive doctrines do, and a
surviving figure alone cannot distinguish "this money demonstrably stayed" from
"nobody can say where this money went".  The second dressed as the first is a
false statement in an exhibit, so the unidentified residue is carried in the
:class:`~services.financial.tracing.Draw`, surfaced in ``total_unidentified``
and written into the narrative, and all three are tested.

**That the analyst's act stays separate from the ledger's fact.**  A
:class:`~services.financial.tracing.Movement` is what the bank recorded; an
:class:`~services.financial.tracing.Attribution` is a person saying that a
deposit answers to a claim, on a stated basis.  Merging them would make the
opinion unfalsifiable, so attributions are validated against the movements they
name and every mismatch raises rather than being absorbed.

**That the module cannot be made to opine.**  AICPA SSFS No. 1 forbids opining
on whether fraud occurred.  The vocabulary is built so that the opinion is
inexpressible -- there is no "dissipated", no "misappropriated", no boolean
anywhere that means "this was stolen" -- and :class:`TheModuleDoesNotOpine`
holds that shape in place against future additions.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import date

from postgres.models.enums import ProofClass, TransactionDirection
from services.financial import tracing
from services.financial.money import CurrencyMismatchError, Money
from services.financial.tracing import (
    Attribution,
    AttributionError,
    ClaimOutcome,
    Doctrine,
    DoctrineError,
    Draw,
    Movement,
    NOTE_AMBIGUOUS_MATCH,
    NOTE_DREW_ON_OPENING,
    NOTE_ORDER_UNEVIDENCED,
    NOTE_OVERDRAWN,
    NOTE_SHORTFALL_SHARED,
    NOTE_UNIDENTIFIED_WITHDRAWAL,
    DOCTRINE_AUTHORITY,
    DOCTRINE_ORDER,
    TracingError,
    compare_doctrines,
    trace,
)

CR = TransactionDirection.credit
DR = TransactionDirection.debit

PRESUMPTIVE = tuple(d for d in DOCTRINE_ORDER if d is not Doctrine.direct)


def usd(major: str) -> Money:
    """A USD amount from a major-unit string.  Never a float."""
    from decimal import Decimal

    return Money.from_decimal(Decimal(major), "USD")


def mv(
    day: int,
    idx: int,
    amount: str,
    direction: TransactionDirection,
    *,
    proof_class: ProofClass = ProofClass.p1,
    currency: str = "USD",
    row_index: int | None = None,
) -> Movement:
    from decimal import Decimal

    return Movement(
        transaction_id=uuid.UUID(int=idx),
        ordering_date=date(2024, 1, day),
        row_index=idx if row_index is None else row_index,
        amount=Money.from_decimal(Decimal(amount), currency),
        direction=direction,
        proof_class=proof_class,
    )


def attr(idx: int, claim: str, amount: str, currency: str = "USD") -> Attribution:
    from decimal import Decimal

    return Attribution(
        transaction_id=uuid.UUID(int=idx),
        claim_id=claim,
        amount=Money.from_decimal(Decimal(amount), currency),
        basis="wire reference names the claimant",
    )


def dec(money: Money) -> str:
    return str(money.as_decimal())


class DoctrinesMustDisagree(unittest.TestCase):
    """The doctrines are different rules, and the tests must be able to tell.

    If these fail, the module has collapsed into a single doctrine and every
    other test in this file is passing vacuously.
    """

    def setUp(self):
        # Claim money in first, the holder's own money in second, then a single
        # withdrawal that consumes exactly one deposit's worth.  This is the
        # minimal pattern that separates Hallett from Clayton's Case: Hallett
        # spends the holder's own money first, Clayton's Case spends whatever
        # went in first, and here those are different pots.
        self.movements = [
            mv(1, 1, "5000.00", CR),
            mv(2, 2, "5000.00", CR),
            mv(3, 3, "5000.00", DR),
        ]
        self.attributions = [attr(1, "A", "5000.00")]

    def _surviving(self):
        comparison = compare_doctrines(
            self.movements, self.attributions, opening_balance=usd("0.00")
        )
        return {
            doctrine: dec(result.outcomes["A"].surviving)
            for doctrine, result in comparison.results.items()
        }

    def test_hallett_spends_the_holders_own_money_first(self):
        """*Re Hallett's Estate* (1880) 13 Ch D 696.

        The claimant is left whole because the withdrawal is presumed to have
        taken the holder's own money, even though it went in later.
        """
        self.assertEqual(
            "5000.00", self._surviving()[Doctrine.lowest_intermediate_balance]
        )

    def test_claytons_case_spends_whatever_went_in_first(self):
        """*Devaynes v Noble* (1816) 35 ER 781.

        The opposite result on the same facts: the claimant went in first, so
        the claimant goes out first and nothing survives.
        """
        self.assertEqual("0.00", self._surviving()[Doctrine.first_in_first_out])

    def test_lifo_spends_the_later_deposit(self):
        self.assertEqual("5000.00", self._surviving()[Doctrine.last_in_first_out])

    def test_pro_rata_splits_rateably(self):
        """Restatement (Third) of Restitution §§55-61.

        Half the account was the claimant's, so the claimant bears half the
        withdrawal -- a third answer, distinct from both presumptions above.
        """
        self.assertEqual("2500.00", self._surviving()[Doctrine.pro_rata])

    def test_direct_declines_because_two_deposits_match_the_amount(self):
        """`12` §5.1 requires "nothing else moving" for a one-to-one match.

        Both deposits are 5,000, so either could be the money that left.  The
        doctrine makes no finding rather than choosing, and the choice it
        declines to make would otherwise have gone against the claimant purely
        because the competing deposit happened to be unattributed.
        """
        result = trace(
            self.movements,
            self.attributions,
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertIn(NOTE_AMBIGUOUS_MATCH, result.notes)
        self.assertEqual("5000.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("5000.00", dec(result.total_unidentified()))

    def test_at_least_three_distinct_answers_on_one_fact_pattern(self):
        """The guard against five names for one rule.

        Asserting the individual figures above would still pass if the module
        were rewritten to return a constant per doctrine.  This asserts the
        thing that actually matters: the doctrines partition into genuinely
        different answers on facts chosen to separate them.
        """
        self.assertGreaterEqual(len(set(self._surviving().values())), 3)

    def test_the_comparison_reports_the_spread_as_material(self):
        comparison = compare_doctrines(
            self.movements, self.attributions, opening_balance=usd("0.00")
        )
        self.assertFalse(comparison.doctrines_agree("A"))
        self.assertEqual("5000.00", dec(comparison.divergence("A")))
        self.assertIn("question of law", comparison.narrative("A"))

    def test_doctrines_agree_where_the_facts_do_not_separate_them(self):
        """Divergence is a property of the facts, not a constant.

        A single attributed deposit and a partial withdrawal gives every
        doctrine that reaches an answer the same pot to draw on, so they must
        agree -- and the narrative must say the choice is immaterial rather
        than claiming a spread that is not there.

        Direct tracing declines here: a 400.00 withdrawal has no 400.00 deposit
        to identify it against.  Its surviving figure of 1000.00 is silence,
        not a finding, and it is excluded from the spread for that reason.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "400.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        self.assertTrue(comparison.doctrines_agree("A"))
        self.assertTrue(comparison.divergence("A").is_zero)
        self.assertIn("does not affect this claim", comparison.narrative("A"))
        self.assertEqual(PRESUMPTIVE, comparison.doctrines_making_findings())
        self.assertFalse(comparison.made_a_finding(Doctrine.direct))

    def test_a_declining_doctrine_does_not_manufacture_a_spread(self):
        """The defect this guards against, stated directly.

        Counting direct tracing's silence as a surviving figure would report a
        divergence of 400.00 on these facts and put "the answer is between
        600.00 and 1,000.00 depending on the rule" in front of a tribunal,
        when every rule that answers answers 600.00.  The declination is still
        reported -- it is in ``surviving_by_doctrine`` and it has its own line
        in the narrative -- it is only kept out of the arithmetic of the
        spread.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "400.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        surviving = comparison.surviving_by_doctrine("A")
        self.assertEqual("1000.00", dec(surviving[Doctrine.direct]))
        for doctrine in PRESUMPTIVE:
            self.assertEqual("600.00", dec(surviving[doctrine]))
        self.assertEqual("0.00", dec(comparison.divergence("A")))
        narrative = comparison.narrative("A")
        self.assertIn("makes no finding about that amount", narrative)
        self.assertIn("among those that reached an answer", narrative)

    def test_agreement_is_unqualified_when_every_doctrine_answered(self):
        """The qualifier appears only where a doctrine actually stayed silent.

        A one-to-one match leaves direct tracing with a finding of its own, so
        the summary line is entitled to speak for all five without hedging.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "1000.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        self.assertEqual(DOCTRINE_ORDER, comparison.doctrines_making_findings())
        self.assertTrue(comparison.doctrines_agree("A"))
        self.assertNotIn(
            "among those that reached an answer", comparison.narrative("A")
        )


class TheLowestIntermediateBalanceRule(unittest.TestCase):
    """LIBR is two rules composed, and both limbs are tested separately."""

    def test_a_later_deposit_does_not_replenish(self):
        """*Roscoe (James) (Bolton) Ltd v Winder* [1915] 1 Ch 62.

        Ten thousand in, nine thousand out, eight thousand back in.  The
        claimant traces one thousand, not nine: the money that left is gone and
        the holder's later deposit is the holder's, not restitution.
        """
        result = trace(
            [
                mv(1, 1, "10000.00", CR),
                mv(2, 2, "9000.00", DR),
                mv(3, 3, "8000.00", CR),
            ],
            [attr(1, "A", "10000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("1000.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("9000.00", dec(result.outcomes["A"].withdrawn))
        self.assertEqual("9000.00", dec(result.closing_balance))
        # The account minimum is 0.00, because the account opened at zero and
        # the trace measures from there.  A's cap is 1000.00, because the rule
        # measures from A's own deposit.  These are different numbers and the
        # field is named so they cannot be confused; asserting both here is
        # what stops the distinction being quietly collapsed later.
        self.assertEqual("0.00", dec(result.lowest_balance))

    def test_no_presumptive_doctrine_replenishes(self):
        """The Roscoe limb is structural, not special-cased into LIBR.

        Parcels are drawn down and never refilled, so a later deposit cannot
        restore an earlier claim under *any* presumption.  Testing this across
        all four presumptive doctrines catches a refill bug that a LIBR-only
        test would miss.
        """
        comparison = compare_doctrines(
            [
                mv(1, 1, "10000.00", CR),
                mv(2, 2, "9000.00", DR),
                mv(3, 3, "8000.00", CR),
            ],
            [attr(1, "A", "10000.00")],
            opening_balance=usd("0.00"),
        )
        for doctrine in PRESUMPTIVE:
            with self.subTest(doctrine=doctrine.value):
                self.assertEqual(
                    "1000.00",
                    dec(comparison.results[doctrine].outcomes["A"].surviving),
                )

    def test_the_holders_own_money_is_spent_before_the_claimants(self):
        """The Hallett limb, isolated from ordering.

        The untainted deposit arrives *after* the claim, so a doctrine that
        merely spent in arrival order would spend the claim first.  LIBR must
        reach past it.
        """
        result = trace(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "1000.00", CR),
                mv(3, 3, "1000.00", DR),
            ],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("1000.00", dec(result.draws[0].from_untainted))
        self.assertEqual({}, dict(result.draws[0].by_claim))

    def test_the_opening_balance_is_spent_before_the_claimants_money(self):
        """An opening balance is the holder's own money for Hallett purposes.

        It is reported separately from an untainted deposit because the two are
        different evidential situations -- one is a movement this trace saw,
        the other a figure it was handed -- but both are outside every claim.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "800.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("2000.00"),
        )
        self.assertEqual("800.00", dec(result.draws[0].from_opening))
        self.assertEqual("0.00", dec(result.draws[0].from_untainted))
        self.assertEqual("1000.00", dec(result.outcomes["A"].surviving))
        self.assertIn(NOTE_DREW_ON_OPENING, result.notes)

    def test_the_opening_balance_note_is_absent_when_it_was_not_touched(self):
        """Notes fire only when the situation they describe actually arose.

        A note that is always present carries no information, and a reader who
        learns to ignore it will ignore it on the case where it mattered.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "800.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertNotIn(NOTE_DREW_ON_OPENING, result.notes)

    def test_sharing_a_shortfall_between_claims_is_disclosed(self):
        """LIBR fixes how much survives, never whose.

        With two claims and a withdrawal larger than either, the rule runs out
        before the answer does: *Hallett* says the holder's own money goes
        first, and says nothing about which of two claimants bears what is
        left.  This module divides rateably, which is one defensible answer
        among several, and :data:`NOTE_SHORTFALL_SHARED` is how the reader
        learns a second choice was made underneath the one they asked for.
        Without it the exhibit presents a contestable allocation with the
        authority of a settled rule.
        """
        result = trace(
            [
                mv(1, 1, "300.00", CR),
                mv(2, 2, "700.00", CR),
                mv(3, 3, "1000.00", DR),
            ],
            [attr(1, "A", "300.00"), attr(2, "B", "700.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertIn(NOTE_SHORTFALL_SHARED, result.notes)
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("0.00", dec(result.outcomes["B"].surviving))

    def test_a_single_claim_shortfall_is_not_disclosed_as_sharing(self):
        """One claimant cannot share with anyone, so no sub-rule was applied."""
        result = trace(
            [mv(1, 1, "300.00", CR), mv(2, 2, "300.00", DR)],
            [attr(1, "A", "300.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertNotIn(NOTE_SHORTFALL_SHARED, result.notes)


class ProRataIsARollingCharge(unittest.TestCase):
    """Proportions are struck at each withdrawal, not once at the end."""

    def test_a_deposit_after_a_withdrawal_does_not_bear_that_withdrawal(self):
        """The whole content of "rolling".

        A claims 1,000 and is alone in the account when 500 leaves, so A bears
        all of it.  B arrives afterwards.  Striking the proportions once at the
        end would make B bear part of a withdrawal that predates B's money --
        an arithmetic convenience that would put a claimant's money into a
        payment it demonstrably could not have funded.
        """
        result = trace(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "500.00", DR),
                mv(3, 3, "1000.00", CR),
            ],
            [attr(1, "A", "1000.00"), attr(3, "B", "1000.00")],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("500.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("1000.00", dec(result.outcomes["B"].surviving))
        self.assertEqual("0.00", dec(result.outcomes["B"].withdrawn))

    def test_a_later_withdrawal_is_shared_between_both_claims(self):
        result = trace(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "1000.00", CR),
                mv(3, 3, "1000.00", DR),
            ],
            [attr(1, "A", "1000.00"), attr(2, "B", "1000.00")],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("500.00", dec(result.draws[0].by_claim["A"]))
        self.assertEqual("500.00", dec(result.draws[0].by_claim["B"]))

    def test_an_indivisible_penny_is_allocated_and_not_lost(self):
        """``Money.allocate`` uses largest-remainder for exactly this case.

        One cent cannot be split three ways.  The shares must still sum to the
        withdrawal exactly, because a trace that loses a penny is a trace that
        will not reconcile against the statement it came from.
        """
        result = trace(
            [
                mv(1, 1, "0.01", CR),
                mv(2, 2, "0.01", CR),
                mv(3, 3, "0.01", CR),
                mv(4, 4, "0.01", DR),
            ],
            [
                attr(1, "A", "0.01"),
                attr(2, "B", "0.01"),
                attr(3, "C", "0.01"),
            ],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        draw = result.draws[0]
        self.assertEqual(draw.amount, draw.parts_total())
        self.assertEqual("0.01", dec(draw.total_traced()))

    def test_a_shortfall_is_shared_rateably_without_a_caveat(self):
        """More leaves than any single claim can fund.

        Pro rata carries no :data:`NOTE_SHORTFALL_SHARED`, and the absence is
        deliberate rather than a gap.  The note exists to disclose a sub-rule
        the reader did not ask for -- under LIBR, which fixes how much survives
        but not whose, rateable division is an extra choice made underneath the
        doctrine.  Under pro rata it *is* the doctrine.  Printing the caveat
        here would train a reader to skip it, which is precisely how a caveat
        stops doing its job in the one place it matters.
        """
        result = trace(
            [
                mv(1, 1, "300.00", CR),
                mv(2, 2, "700.00", CR),
                mv(3, 3, "1000.00", DR),
            ],
            [attr(1, "A", "300.00"), attr(2, "B", "700.00")],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertNotIn(NOTE_SHORTFALL_SHARED, result.notes)
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("0.00", dec(result.outcomes["B"].surviving))


class DirectTracingRefusesRatherThanResolves(unittest.TestCase):
    """The doctrine that applies no presumption must be allowed to say nothing."""

    def test_a_clean_one_to_one_match_is_made(self):
        """`12` §5.1: a wire in, a wire out of the same amount, nothing else."""
        result = trace(
            [mv(1, 1, "2500.00", CR), mv(2, 2, "2500.00", DR)],
            [attr(1, "A", "2500.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("2500.00", dec(result.draws[0].by_claim["A"]))
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))
        self.assertNotIn(NOTE_AMBIGUOUS_MATCH, result.notes)
        self.assertNotIn(NOTE_UNIDENTIFIED_WITHDRAWAL, result.notes)

    def test_an_untainted_deposit_of_the_same_amount_spoils_the_match(self):
        """The defect this class was written to catch.

        Considering only attributed deposits as candidates would find a unique
        match here and charge it to the claimant.  But the holder's own 2,500
        could equally have been the money that left, and resolving that against
        the claimant is a presumption applied under the name of the one
        doctrine that applies none.
        """
        result = trace(
            [
                mv(1, 1, "2500.00", CR),
                mv(2, 2, "2500.00", CR),
                mv(3, 3, "2500.00", DR),
            ],
            [attr(1, "A", "2500.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertIn(NOTE_AMBIGUOUS_MATCH, result.notes)
        self.assertEqual({}, dict(result.draws[0].by_claim))
        self.assertEqual("2500.00", dec(result.draws[0].unidentified))

    def test_a_match_against_untainted_money_charges_no_claim(self):
        """Identified, and identified as *not* the claimant's.

        This is a finding, not a failure to make one, so it belongs in
        ``from_untainted`` rather than ``unidentified`` -- the records say
        whose money left, and it was the holder's.
        """
        result = trace(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "2500.00", CR),
                mv(3, 3, "2500.00", DR),
            ],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("2500.00", dec(result.draws[0].from_untainted))
        self.assertEqual("0.00", dec(result.draws[0].unidentified))
        self.assertEqual("1000.00", dec(result.outcomes["A"].surviving))
        self.assertNotIn(NOTE_UNIDENTIFIED_WITHDRAWAL, result.notes)

    def test_two_attributed_deposits_of_one_amount_are_ambiguous(self):
        result = trace(
            [
                mv(1, 1, "400.00", CR),
                mv(2, 2, "400.00", CR),
                mv(3, 3, "400.00", DR),
            ],
            [attr(1, "A", "400.00"), attr(2, "B", "400.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertIn(NOTE_AMBIGUOUS_MATCH, result.notes)
        self.assertEqual("400.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("400.00", dec(result.outcomes["B"].surviving))

    def test_an_unmatched_withdrawal_is_unidentified_not_silently_dropped(self):
        """No deposit of 900 exists, so the doctrine makes no finding.

        The money still left, so it must appear in the draw.  A draw whose
        parts do not sum to the withdrawal is an exhibit column that does not
        add up.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "900.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        draw = result.draws[0]
        self.assertEqual("900.00", dec(draw.unidentified))
        self.assertEqual(draw.amount, draw.parts_total())
        self.assertIn(NOTE_UNIDENTIFIED_WITHDRAWAL, result.notes)

    def test_a_deposit_is_matched_at_most_once(self):
        """Two identical withdrawals, one deposit that could answer for either.

        The first consumes the candidate; the second then has none.  Without
        the consumption the same 500 would be traced out twice, and the claim
        would be shown as having funded a thousand pounds of payments out of a
        five hundred pound deposit.
        """
        result = trace(
            [
                mv(1, 1, "500.00", CR),
                mv(2, 2, "500.00", DR),
                mv(3, 3, "500.00", CR),
                mv(4, 4, "500.00", DR),
            ],
            [attr(1, "A", "500.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("500.00", dec(result.outcomes["A"].withdrawn))
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))

    def test_the_narrative_says_when_no_finding_was_made(self):
        """A surviving figure alone cannot distinguish silence from a finding.

        "1,000.00 remaining, 0.00 traced out" reads as proof the money stayed.
        Where the doctrine simply declined, the sentence must say so.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "900.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        narrative = comparison.narrative("A")
        self.assertIn("could not be identified", narrative)
        self.assertIn("makes no finding", narrative)

    def test_the_narrative_is_silent_where_every_withdrawal_was_identified(self):
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "1000.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        self.assertNotIn("could not be identified", comparison.narrative("A"))

    def test_only_direct_tracing_ever_leaves_money_unidentified(self):
        """Every other doctrine applies a presumption, and a presumption answers."""
        comparison = compare_doctrines(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "333.00", DR),
                mv(3, 3, "222.00", DR),
            ],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        for doctrine in PRESUMPTIVE:
            with self.subTest(doctrine=doctrine.value):
                self.assertTrue(
                    comparison.results[doctrine].total_unidentified().is_zero
                )
        self.assertTrue(
            comparison.results[Doctrine.direct].total_unidentified().is_positive
        )

    def test_a_matched_deposit_is_spent_and_cannot_answer_again(self):
        """One deposit answers for one withdrawal, not for every equal one.

        The identification here is that this money is that money.  Leaving a
        matched deposit in the candidate pool would let a single 1,000.00
        credited to A be identified as the source of two separate 1,000.00
        payments, and the second finding would look exactly like the first --
        same amount, same claimant, same stated basis.  The claim's withdrawn
        figure would then exceed everything it ever deposited, which is not a
        rounding problem but a statement that money left twice.
        """
        result = trace(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "1000.00", DR),
                mv(3, 3, "1000.00", DR),
            ],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("1000.00"),
        )
        self.assertEqual("1000.00", dec(result.outcomes["A"].withdrawn))
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))
        self.assertEqual({"A"}, set(result.draws[0].by_claim))
        self.assertEqual({}, dict(result.draws[1].by_claim))
        self.assertEqual("1000.00", dec(result.draws[1].unidentified))
        self.assertIn(NOTE_UNIDENTIFIED_WITHDRAWAL, result.notes)

    def test_the_unfundable_part_is_not_debited_from_the_balance(self):
        """*Bishopsgate* again, on the direct path's running balance.

        Only the fundable part of the payment came out of this account; the
        rest came from the bank.  Debiting the whole amount would drive the
        recorded balance below zero and carry that fiction into every later
        row and into the account minimum -- while the draw itself still foots,
        because the unfunded part is recorded there correctly.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "4000.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("3000.00", dec(result.draws[0].unfunded))
        self.assertEqual("0.00", dec(result.closing_balance))
        self.assertEqual("0.00", dec(result.lowest_balance))
        self.assertFalse(result.closing_balance.is_negative)


class NoTracingIntoAnOverdraft(unittest.TestCase):
    """*Bishopsgate Investment Management Ltd v Homan* [1995] Ch 211."""

    def test_the_unfunded_excess_is_reported_under_every_doctrine(self):
        """Money paid out of an overdrawn account is the bank's.

        Absorbing the excess silently would let a trace attribute money that
        was never in the account, which is the one arithmetic a statement
        cannot corroborate.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "4000.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        for doctrine, result in comparison.results.items():
            with self.subTest(doctrine=doctrine.value):
                self.assertIn(NOTE_OVERDRAWN, result.notes)
                self.assertEqual("3000.00", dec(result.draws[-1].unfunded))

    def test_an_overdraft_does_not_become_an_unidentified_residue(self):
        """The two residues mean opposite things and must not be conflated.

        ``unfunded`` says the money was not there; ``unidentified`` says it was
        there and nobody can say whose.  Reporting an overdraft as the second
        would describe a solvent account, and reporting the second as the first
        would describe an overdraft that never happened.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "4000.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.direct,
            opening_balance=usd("0.00"),
        )
        draw = result.draws[-1]
        self.assertEqual("3000.00", dec(draw.unfunded))
        self.assertEqual("1000.00", dec(draw.by_claim.get("A", usd("0.00"))))
        self.assertEqual("0.00", dec(draw.unidentified))

    def test_the_overdraft_note_is_absent_on_a_solvent_account(self):
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "1000.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertNotIn(NOTE_OVERDRAWN, result.notes)

    def test_a_later_deposit_does_not_revive_a_claim_across_an_overdraft(self):
        comparison = compare_doctrines(
            [
                mv(1, 1, "1000.00", CR),
                mv(2, 2, "4000.00", DR),
                mv(3, 3, "5000.00", CR),
            ],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        for doctrine in PRESUMPTIVE:
            with self.subTest(doctrine=doctrine.value):
                self.assertEqual(
                    "0.00",
                    dec(comparison.results[doctrine].outcomes["A"].surviving),
                )


class OrderIsEvidenceNotAnAssumption(unittest.TestCase):
    """Where the records do not fix the order, the result says so."""

    def test_unevidenced_intraday_order_is_flagged(self):
        """FIFO and LIFO turn entirely on order.

        Two movements on the same day with the same row index and opposite
        directions are not ordered by the records.  Adopting whichever order
        the rows happened to arrive in would make the answer a property of the
        database, not of the evidence.
        """
        result = trace(
            [
                mv(1, 1, "1000.00", CR, row_index=7),
                mv(1, 2, "400.00", DR, row_index=7),
            ],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.first_in_first_out,
            opening_balance=usd("0.00"),
        )
        self.assertIn(NOTE_ORDER_UNEVIDENCED, result.notes)

    def test_a_distinct_row_index_is_evidence_of_order(self):
        result = trace(
            [
                mv(1, 1, "1000.00", CR, row_index=1),
                mv(1, 2, "400.00", DR, row_index=2),
            ],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.first_in_first_out,
            opening_balance=usd("0.00"),
        )
        self.assertNotIn(NOTE_ORDER_UNEVIDENCED, result.notes)

    def test_the_result_does_not_depend_on_input_order(self):
        """Determinism.

        The same movements handed over in a different sequence must produce the
        same trace, or two analysts running the same query get different
        exhibits from the same ledger.
        """
        movements = [
            mv(1, 1, "1000.00", CR),
            mv(2, 2, "600.00", DR),
            mv(3, 3, "500.00", CR),
            mv(4, 4, "700.00", DR),
        ]
        attributions = [attr(1, "A", "1000.00"), attr(3, "B", "500.00")]
        forward = trace(
            movements,
            attributions,
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        backward = trace(
            list(reversed(movements)),
            list(reversed(attributions)),
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual(
            [dec(o.surviving) for o in forward.outcomes.values()],
            [dec(o.surviving) for o in backward.outcomes.values()],
        )
        self.assertEqual(forward.notes, backward.notes)

    def test_ordering_ambiguity_does_not_refuse_the_trace(self):
        """`13` §8.2 requires alternatives be shown, so the trace still runs.

        Refusing outright would suppress the comparison that tells the reader
        the answer is order-dependent, and would withhold LIBR and pro rata,
        which do not turn on intraday order at all.
        """
        comparison = compare_doctrines(
            [
                mv(1, 1, "1000.00", CR, row_index=7),
                mv(1, 2, "400.00", DR, row_index=7),
            ],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        self.assertEqual(len(DOCTRINE_ORDER), len(comparison.results))
        self.assertIn("600.00", comparison.narrative("A"))

    def test_the_date_outranks_the_row_index(self):
        """Row indexes restart on every statement; dates do not.

        A ledger assembled from more than one statement carries row 1 several
        times over, and ordering on the row first would interleave January and
        February into a sequence the account never saw.  The failure is quiet
        in exactly the way this module is built to prevent: here the deposit
        that funds the withdrawal would be sorted *after* it, so the trace
        would report an overdraft the bank never granted and hand the claimant
        back money the account had already paid out.
        """
        movements = [
            mv(5, 1, "1000.00", CR, row_index=9),   # last row of January
            mv(20, 2, "1000.00", DR, row_index=1),  # first row of February
        ]
        result = trace(
            movements,
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("1000.00", dec(result.outcomes["A"].withdrawn))
        self.assertNotIn(NOTE_OVERDRAWN, result.notes)

    def test_the_row_index_orders_movements_within_a_day(self):
        """Within one day the statement's own sequence is the evidence.

        Drop it and the remaining tiebreak is the transaction id, which is a
        database identifier and means nothing about when anything happened.
        The rows here are built so the two disagree: the deposit sits first on
        the statement but carries the later id.  Ordering on the id would put
        the withdrawal first, against a record that plainly says otherwise.
        """
        movements = [
            mv(1, 2, "1000.00", CR, row_index=1),
            mv(1, 1, "1000.00", DR, row_index=2),
        ]
        result = trace(
            movements,
            [attr(2, "A", "1000.00")],
            doctrine=Doctrine.first_in_first_out,
            opening_balance=usd("0.00"),
        )
        self.assertNotIn(NOTE_ORDER_UNEVIDENCED, result.notes)
        self.assertNotIn(NOTE_OVERDRAWN, result.notes)
        self.assertEqual("0.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("1000.00", dec(result.outcomes["A"].withdrawn))


class AttributionsAreCheckedAgainstTheLedger(unittest.TestCase):
    """The analyst's opinion is validated against the bank's record."""

    def setUp(self):
        self.movements = [mv(1, 1, "1000.00", CR), mv(2, 2, "400.00", DR)]

    def _trace(self, attributions):
        return trace(
            self.movements,
            attributions,
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )

    def test_a_withdrawal_cannot_be_attributed(self):
        """A claim is a claim to money that came in, not money that went out.

        The message is asserted, not just the type.  A withdrawal is also
        absent from the deposit index, so removing this check entirely still
        raises ``AttributionError`` -- from the *next* guard, saying the row is
        not a deposit in this account.  That is a different and misleading
        thing to tell an analyst who attributed a row that is plainly present
        on the statement, and asserting only the type would let the two
        refusals be silently collapsed into one.
        """
        with self.assertRaises(AttributionError) as caught:
            self._trace([attr(2, "A", "400.00")])
        self.assertIn("which is a withdrawal", str(caught.exception))

    def test_an_unknown_transaction_cannot_be_attributed(self):
        """Silently ignoring it would drop the claim from the trace entirely."""
        with self.assertRaises(AttributionError) as caught:
            self._trace([attr(99, "A", "100.00")])
        self.assertIn("not a deposit in this", str(caught.exception))

    def test_an_attribution_cannot_exceed_its_deposit(self):
        with self.assertRaises(AttributionError):
            self._trace([attr(1, "A", "1500.00")])

    def test_attributions_sharing_a_deposit_cannot_exceed_it_together(self):
        """Each is individually plausible; together they claim money that
        never arrived.  Checking them one at a time would let this through."""
        with self.assertRaises(AttributionError):
            self._trace([attr(1, "A", "600.00"), attr(1, "B", "600.00")])

    def test_two_claims_may_share_one_deposit_within_it(self):
        result = self._trace([attr(1, "A", "600.00"), attr(1, "B", "400.00")])
        self.assertEqual("600.00", dec(result.outcomes["A"].deposited))
        self.assertEqual("400.00", dec(result.outcomes["B"].deposited))

    def test_a_currency_mismatch_is_refused(self):
        """Raised as the shared money-domain error, not a tracing-local one.

        ``CurrencyMismatchError`` is what ``money`` raises and what
        ``services.financial`` exports, so a caller already catching it around
        arithmetic catches it here too.  Asserting the specific type rather
        than ``Exception`` is the point: it pins the fact that this refusal is
        reachable by a caller who does not know ``tracing`` exists.

        The message is asserted too, and for a sharper reason.  Delete the
        check and ``Money`` raises the same class a few lines later, out of the
        arithmetic that totals a deposit's attributions -- so the type alone
        cannot tell a refusal that names the claim from an incidental failure
        to add two numbers.  Only the first is any use to whoever has to fix
        the input.
        """
        with self.assertRaises(CurrencyMismatchError) as caught:
            self._trace([attr(1, "A", "100.00", currency="EUR")])
        self.assertIn("attribution to A", str(caught.exception))

    def test_mixed_currency_movements_are_refused(self):
        """A trace over two currencies is not a trace, it is two traces.

        Adding them would produce a number in no currency at all.  As with the
        attribution case above, the message is asserted because the arithmetic
        downstream would raise the same class without ever saying which row was
        the odd one out.
        """
        with self.assertRaises(CurrencyMismatchError) as caught:
            trace(
                [mv(1, 1, "100.00", CR), mv(2, 2, "50.00", DR, currency="EUR")],
                [attr(1, "A", "100.00")],
                doctrine=Doctrine.pro_rata,
                opening_balance=usd("0.00"),
            )
        self.assertIn("converting is an analytical act", str(caught.exception))

    def test_an_attribution_must_state_a_basis(self):
        """The basis is what makes the attribution reviewable.

        Without it the trace records that someone thought a deposit answered to
        a claim, but not why, and nobody downstream can weigh it.
        """
        with self.assertRaises(AttributionError):
            Attribution(
                transaction_id=uuid.UUID(int=1),
                claim_id="A",
                amount=usd("100.00"),
                basis="",
            )

    def test_a_non_positive_attribution_is_refused(self):
        with self.assertRaises(AttributionError):
            Attribution(
                transaction_id=uuid.UUID(int=1),
                claim_id="A",
                amount=usd("0.00"),
                basis="stated",
            )

    def test_an_attribution_must_name_a_claim(self):
        """An unnamed claim is not a claim, and nothing downstream would say so.

        The claim id is the key every outcome is reported under.  An empty one
        would produce a ``ClaimOutcome`` keyed on the empty string, sitting in
        an exhibit next to the named claims and answering for real money with
        no claimant behind it.  Nothing in the arithmetic notices.
        """
        with self.assertRaises(AttributionError):
            Attribution(
                transaction_id=uuid.UUID(int=1),
                claim_id="",
                amount=usd("100.00"),
                basis="stated",
            )


class ProofClassGovernsWhatIsTraced(unittest.TestCase):
    """`13` §8.3: the default runs over P0-P2 and says so."""

    def setUp(self):
        self.movements = [
            mv(1, 1, "1000.00", CR, proof_class=ProofClass.p1),
            mv(2, 2, "500.00", CR, proof_class=ProofClass.p3),
            mv(3, 3, "600.00", DR, proof_class=ProofClass.p1),
        ]
        self.attributions = [attr(1, "A", "1000.00")]

    def test_unadjudicated_rows_are_excluded_by_default(self):
        """A p3 row needs a recorded human verdict before it counts.

        Including it by default would put an unchecked row inside a total,
        which `13` §2.2 calls the exact failure the system exists to prevent.
        """
        result = trace(
            self.movements,
            self.attributions,
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual(2, result.movements_considered)
        self.assertEqual(1, result.movements_excluded_by_proof_class)
        self.assertEqual("400.00", dec(result.closing_balance))

    def test_the_included_classes_are_recorded_on_the_result(self):
        """A total must state which classes it covers, not imply them."""
        result = trace(
            self.movements,
            self.attributions,
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual(
            frozenset({ProofClass.p0, ProofClass.p1, ProofClass.p2}),
            result.proof_classes_included,
        )

    def test_widening_the_classes_changes_the_trace_and_is_recorded(self):
        """Admitting p3 is a decision, and the result carries evidence of it."""
        result = trace(
            self.movements,
            self.attributions,
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
            proof_classes=frozenset(
                {ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3}
            ),
        )
        self.assertEqual(3, result.movements_considered)
        self.assertEqual(0, result.movements_excluded_by_proof_class)
        self.assertEqual("900.00", dec(result.closing_balance))
        self.assertIn(ProofClass.p3, result.proof_classes_included)

    def test_an_empty_class_set_is_refused_rather_than_traced(self):
        """Admitting nothing is not a narrow trace, it is not a trace.

        Left to run it produces a perfectly well-formed result: zero movements
        considered, a closing balance equal to the opening one, and every claim
        reported as fully surviving -- because nothing was ever admitted that
        could take money out.  That is the most dangerous shape of output this
        module can produce, since it says every claimant's money is still there
        and it says it with all the usual apparatus around it.
        """
        with self.assertRaises(TracingError) as caught:
            trace(
                self.movements,
                self.attributions,
                doctrine=Doctrine.pro_rata,
                opening_balance=usd("0.00"),
                proof_classes=frozenset(),
            )
        self.assertIn("no movement could be considered", str(caught.exception))

    def test_an_excluded_deposit_cannot_be_attributed(self):
        """Filtering happens before attribution, so the claim has nothing to
        attach to and the mismatch is reported rather than silently dropped."""
        with self.assertRaises(AttributionError):
            trace(
                self.movements,
                [attr(2, "B", "500.00")],
                doctrine=Doctrine.pro_rata,
                opening_balance=usd("0.00"),
            )

    def test_a_p4_movement_is_never_traced(self):
        """p4 is assertional: a claim in a chat message, not a ledger row."""
        result = trace(
            [
                mv(1, 1, "1000.00", CR, proof_class=ProofClass.p1),
                mv(2, 2, "9999.00", CR, proof_class=ProofClass.p4),
            ],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("1000.00", dec(result.closing_balance))


class EveryTraceBalances(unittest.TestCase):
    """Invariants that must hold on every doctrine and every input."""

    def setUp(self):
        self.movements = [
            mv(1, 1, "3000.00", CR),
            mv(2, 2, "4000.00", CR),
            mv(3, 3, "2500.00", DR),
            mv(4, 4, "1000.00", CR),
            mv(5, 5, "5000.00", DR),
            mv(6, 6, "250.00", DR),
        ]
        self.attributions = [
            attr(1, "A", "3000.00"),
            attr(2, "B", "4000.00"),
            attr(4, "C", "1000.00"),
        ]
        self.comparison = compare_doctrines(
            self.movements, self.attributions, opening_balance=usd("2000.00")
        )

    def test_deposited_equals_surviving_plus_withdrawn(self):
        """The identity that makes a claim's row in an exhibit add up."""
        for doctrine, result in self.comparison.results.items():
            for claim_id, outcome in result.outcomes.items():
                with self.subTest(doctrine=doctrine.value, claim=claim_id):
                    self.assertEqual(
                        outcome.deposited, outcome.surviving + outcome.withdrawn
                    )

    def test_the_parts_of_a_draw_sum_to_the_withdrawal(self):
        for doctrine, result in self.comparison.results.items():
            for draw in result.draws:
                with self.subTest(doctrine=doctrine.value, tx=str(draw.transaction_id)):
                    self.assertEqual(draw.amount, draw.parts_total())

    def test_no_claim_survives_more_than_it_deposited(self):
        for doctrine, result in self.comparison.results.items():
            for claim_id, outcome in result.outcomes.items():
                with self.subTest(doctrine=doctrine.value, claim=claim_id):
                    self.assertLessEqual(outcome.surviving, outcome.deposited)

    def test_no_figure_is_ever_negative(self):
        """A negative surviving figure would mean more of a claim left than
        arrived, which is not a small error but a broken model."""
        for doctrine, result in self.comparison.results.items():
            for outcome in result.outcomes.values():
                with self.subTest(doctrine=doctrine.value):
                    self.assertFalse(outcome.surviving.is_negative)
                    self.assertFalse(outcome.withdrawn.is_negative)
            for draw in result.draws:
                for share in draw.by_claim.values():
                    self.assertFalse(share.is_negative)

    def test_the_closing_balance_is_the_same_under_every_doctrine(self):
        """The doctrines divide the money differently; they do not change how
        much there is.  A doctrine that moved the closing balance would be
        altering the bank's record rather than interpreting it."""
        balances = {
            dec(result.closing_balance)
            for result in self.comparison.results.values()
        }
        self.assertEqual(1, len(balances))

    def test_total_surviving_never_exceeds_the_closing_balance(self):
        """Claims survive only in money that is still there."""
        for doctrine in PRESUMPTIVE:
            result = self.comparison.results[doctrine]
            with self.subTest(doctrine=doctrine.value):
                self.assertLessEqual(result.total_surviving(), result.closing_balance)

    def test_a_trace_with_no_movements_is_empty_not_an_error(self):
        result = trace(
            [], [], doctrine=Doctrine.pro_rata, opening_balance=usd("0.00")
        )
        self.assertEqual({}, dict(result.outcomes))
        self.assertEqual((), result.draws)
        self.assertEqual("0.00", dec(result.closing_balance))

    def test_a_trace_with_deposits_but_no_withdrawals_leaves_everything(self):
        result = trace(
            [mv(1, 1, "1000.00", CR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.pro_rata,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("1000.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("0.00", dec(result.outcomes["A"].withdrawn))

    def test_the_parts_of_an_overdrawn_draw_include_what_was_unfunded(self):
        """The identity has to hold on the row where it is easiest to lose.

        Every other test of this identity runs on a funded ledger, where the
        unfunded column is zero and dropping it from the sum changes nothing.
        An overdraft is the one case where that column carries money, and it
        is also the case where a reader is least likely to check: the traced,
        untainted and opening figures already look like a complete account of
        the payment, and the shortfall the bank covered is the part that goes
        missing without anything appearing to be wrong.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "4000.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        for doctrine, result in comparison.results.items():
            with self.subTest(doctrine=doctrine.value):
                draw = result.draws[0]
                self.assertEqual("3000.00", dec(draw.unfunded))
                self.assertEqual(draw.amount, draw.parts_total())

    def test_the_account_minimum_follows_the_balance_below_the_opening(self):
        """`lowest_balance` is a fact about the account, not about the claims.

        It has to track the running balance, because the whole of Roscoe turns
        on how far the account fell.  Left at the opening figure it still
        looks entirely plausible -- a real number, in the right currency, of
        roughly the right size -- while quietly overstating the floor that
        every restriction on tracing is measured against.
        """
        comparison = compare_doctrines(
            [mv(1, 1, "4000.00", DR), mv(2, 2, "10000.00", CR)],
            [attr(2, "A", "10000.00")],
            opening_balance=usd("5000.00"),
        )
        for doctrine, result in comparison.results.items():
            with self.subTest(doctrine=doctrine.value):
                self.assertEqual("5000.00", dec(result.opening_balance))
                self.assertEqual("11000.00", dec(result.closing_balance))
                self.assertEqual("1000.00", dec(result.lowest_balance))

    def test_a_claim_survives_across_every_deposit_it_was_attributed_to(self):
        """One claimant, two payments in, one figure out.

        A claim is rarely a single deposit.  Counting only the last parcel
        would report a claimant's survival as whatever their most recent
        payment happened to be, and on this ledger that is 2,000.00 out of
        3,000.00 -- a plausible-looking number that would simply lose a
        payment, and lose it in the claimant's disfavour.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "2000.00", CR)],
            [attr(1, "A", "1000.00"), attr(2, "A", "2000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        outcome = result.outcomes["A"]
        self.assertEqual("3000.00", dec(outcome.deposited))
        self.assertEqual("3000.00", dec(outcome.surviving))
        self.assertEqual("0.00", dec(outcome.withdrawn))

    def test_only_the_attributed_part_of_a_deposit_belongs_to_the_claim(self):
        """A partial attribution claims a part, and the rest is the holder's.

        Deposits are frequently mixed -- a single credit carrying both a
        claimant's money and the holder's own.  Taking the whole credit into
        the claim's parcel would inflate the pool above the money actually in
        the account, and under Hallett it would additionally destroy the
        distinction the doctrine rests on, since the untainted remainder that
        is supposed to be spent first would no longer exist separately.
        """
        result = trace(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "600.00", DR)],
            [attr(1, "A", "400.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        outcome = result.outcomes["A"]
        self.assertEqual("400.00", dec(outcome.deposited))
        self.assertEqual("400.00", dec(outcome.surviving))
        self.assertEqual("0.00", dec(outcome.withdrawn))
        self.assertEqual("600.00", dec(result.draws[0].from_untainted))
        self.assertEqual("400.00", dec(result.closing_balance))


class EveryTraceNamesItsDoctrine(unittest.TestCase):
    """`12` §4.5: a result without its rule has made the choice invisibly."""

    def test_trace_requires_a_doctrine_and_has_no_default(self):
        """The single most important line in the module.

        A default doctrine would mean every caller who did not think about it
        got a legal presumption chosen by whoever wrote the signature.
        """
        with self.assertRaises(TypeError):
            trace(
                [mv(1, 1, "100.00", CR)],
                [],
                opening_balance=usd("0.00"),
            )

    def test_the_doctrine_must_be_passed_by_keyword(self):
        with self.assertRaises(TypeError):
            trace(
                [mv(1, 1, "100.00", CR)],
                [],
                Doctrine.pro_rata,
                opening_balance=usd("0.00"),
            )

    def test_an_unknown_doctrine_is_refused_not_substituted(self):
        """Quietly substituting would be the invisible choice, automated."""
        with self.assertRaises((DoctrineError, TracingError)):
            trace(
                [mv(1, 1, "100.00", CR)],
                [],
                doctrine="whatever_is_convenient",
                opening_balance=usd("0.00"),
            )

    def test_the_result_carries_the_doctrine_and_its_authority(self):
        for doctrine in DOCTRINE_ORDER:
            with self.subTest(doctrine=doctrine.value):
                result = trace(
                    [mv(1, 1, "100.00", CR)],
                    [attr(1, "A", "100.00")],
                    doctrine=doctrine,
                    opening_balance=usd("0.00"),
                )
                self.assertEqual(doctrine, result.doctrine)
                self.assertEqual(DOCTRINE_AUTHORITY[doctrine], result.authority)
                self.assertTrue(result.authority)

    def test_every_doctrine_has_an_authority_recorded(self):
        for doctrine in Doctrine:
            with self.subTest(doctrine=doctrine.value):
                self.assertIn(doctrine, DOCTRINE_AUTHORITY)
                self.assertTrue(DOCTRINE_AUTHORITY[doctrine].strip())

    def test_lifo_authority_does_not_claim_a_common_law_case(self):
        """There is no general common-law authority for LIFO.

        Citing one would be worse than citing none: an opponent who checks it
        finds it does not say what the report says it says.
        """
        authority = DOCTRINE_AUTHORITY[Doctrine.last_in_first_out].lower()
        self.assertNotIn("v ", authority)

    def test_the_doctrine_order_covers_every_doctrine_exactly_once(self):
        self.assertEqual(sorted(DOCTRINE_ORDER, key=str), sorted(Doctrine, key=str))
        self.assertEqual(len(set(DOCTRINE_ORDER)), len(DOCTRINE_ORDER))

    def test_libr_and_pro_rata_lead_the_order(self):
        """`13` §8.1 makes them the priority, being the most commonly applied,
        and the narrative prints in this order."""
        self.assertEqual(Doctrine.lowest_intermediate_balance, DOCTRINE_ORDER[0])
        self.assertEqual(Doctrine.pro_rata, DOCTRINE_ORDER[1])

    def test_the_narrative_names_every_doctrine_it_ran(self):
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "400.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
        )
        narrative = comparison.narrative("A")
        self.assertIn("Lowest intermediate balance rule", narrative)
        self.assertIn("Clayton's Case", narrative)
        self.assertIn("Pro rata", narrative)
        self.assertIn("Direct tracing", narrative)

    def test_a_subset_of_doctrines_can_be_compared(self):
        comparison = compare_doctrines(
            [mv(1, 1, "1000.00", CR), mv(2, 2, "400.00", DR)],
            [attr(1, "A", "1000.00")],
            opening_balance=usd("0.00"),
            doctrines=(Doctrine.pro_rata, Doctrine.first_in_first_out),
        )
        self.assertEqual(2, len(comparison.results))
        self.assertNotIn(Doctrine.direct, comparison.results)


class TheModuleDoesNotOpine(unittest.TestCase):
    """AICPA SSFS No. 1 forbids opining on whether fraud occurred.

    These tests hold the *shape* of the vocabulary rather than any behaviour,
    because the risk is that someone later adds a convenient field and the
    module starts answering a question it is not permitted to answer.
    """

    def test_no_output_field_names_a_conclusion_about_wrongdoing(self):
        forbidden = {
            "fraud",
            "fraudulent",
            "stolen",
            "theft",
            "misappropriated",
            "dissipated",
            "laundered",
            "suspicious",
            "guilty",
            "culpable",
        }
        for cls in (Draw, ClaimOutcome, Movement, Attribution):
            for name in getattr(cls, "__annotations__", {}):
                with self.subTest(cls=cls.__name__, field=name):
                    self.assertNotIn(name.lower(), forbidden)

    def test_an_attribution_records_a_basis_rather_than_a_verdict(self):
        """The basis is recorded, never evaluated.

        The module has no notion of a good or bad basis, because grading one
        would be the opinion it is not allowed to give.
        """
        self.assertIn("basis", Attribution.__annotations__)
        self.assertNotIn("credible", Attribution.__annotations__)
        self.assertNotIn("verified", Attribution.__annotations__)

    def test_a_claim_outcome_has_no_dissipated_figure(self):
        """Withdrawn money may have been spent, moved on, or repaid.

        Calling it dissipated would assert which, and the ledger does not say.
        """
        self.assertNotIn("dissipated", ClaimOutcome.__annotations__)
        self.assertIn("withdrawn", ClaimOutcome.__annotations__)

    def test_the_notes_describe_situations_not_judgements(self):
        notes = {
            NOTE_SHORTFALL_SHARED,
            NOTE_OVERDRAWN,
            NOTE_ORDER_UNEVIDENCED,
            NOTE_DREW_ON_OPENING,
            NOTE_AMBIGUOUS_MATCH,
            NOTE_UNIDENTIFIED_WITHDRAWAL,
        }
        self.assertEqual(6, len(notes))
        for note in notes:
            with self.subTest(note=note):
                self.assertNotIn("fraud", note)
                self.assertNotIn("suspicious", note)
                self.assertEqual(note, note.lower())

    def test_no_doctrine_is_marked_correct_or_preferred(self):
        """`13` §8.2 requires alternatives be shown, not ranked.

        Which doctrine applies is a question of law for the instructing
        lawyer.  A "recommended" flag would be this module answering it.
        """
        for text in DOCTRINE_AUTHORITY.values():
            lowered = text.lower()
            with self.subTest(text=text):
                self.assertNotIn("recommended", lowered)
                self.assertNotIn("preferred", lowered)
                self.assertNotIn("correct", lowered)


class MovementsAreValidated(unittest.TestCase):
    """A malformed movement is refused at construction, not carried inward."""

    def test_a_negative_amount_is_refused(self):
        """The ledger stores magnitude plus direction.

        A negative amount alongside a direction is two statements of sign that
        can contradict each other, and the trace would silently believe one.
        """
        with self.assertRaises(Exception):
            Movement(
                transaction_id=uuid.UUID(int=1),
                ordering_date=date(2024, 1, 1),
                row_index=1,
                amount=usd("-5.00"),
                direction=CR,
                proof_class=ProofClass.p1,
            )

    def test_a_zero_amount_is_permitted_and_moves_nothing(self):
        """Real statements carry zero-value rows; refusing them refuses the case.

        Waived fees, reversal pairs and memo entries all appear as zero-amount
        lines in production bank data.  A tracer that rejected them would fail
        on the statement rather than on the analysis, so the row is admitted
        and simply changes no figure.  It cannot smuggle anything in either:
        an attribution must be positive and may not exceed its deposit, so a
        zero row can never carry a claim.
        """
        zero_row = Movement(
            transaction_id=uuid.UUID(int=9),
            ordering_date=date(2024, 1, 1),
            row_index=9,
            amount=usd("0.00"),
            direction=CR,
            proof_class=ProofClass.p1,
        )
        result = trace(
            [mv(1, 1, "1000.00", CR), zero_row, mv(2, 2, "400.00", DR)],
            [attr(1, "A", "1000.00")],
            doctrine=Doctrine.lowest_intermediate_balance,
            opening_balance=usd("0.00"),
        )
        self.assertEqual("600.00", dec(result.outcomes["A"].surviving))
        self.assertEqual("600.00", dec(result.closing_balance))

    def test_an_attribution_against_a_zero_row_is_impossible(self):
        """The two rules that make the allowance above safe, stated together."""
        with self.assertRaises(AttributionError):
            attr(9, "A", "0.00")

    def test_is_deposit_follows_the_direction(self):
        self.assertTrue(mv(1, 1, "1.00", CR).is_deposit)
        self.assertFalse(mv(1, 1, "1.00", DR).is_deposit)

    def test_a_negative_opening_balance_is_refused(self):
        """An account already overdrawn has nothing to trace into.

        *Bishopsgate* again, applied at the window's start rather than inside
        it: money paid out of an overdrawn account is the bank's.
        """
        with self.assertRaises(TracingError):
            trace(
                [mv(1, 1, "100.00", CR)],
                [],
                doctrine=Doctrine.pro_rata,
                opening_balance=usd("-1.00"),
            )

    def test_duplicate_transaction_ids_are_refused(self):
        """The same row twice would double a deposit or a withdrawal, and the
        trace has no way to know which reading was meant."""
        with self.assertRaises(TracingError):
            trace(
                [mv(1, 1, "100.00", CR), mv(2, 1, "200.00", CR)],
                [],
                doctrine=Doctrine.pro_rata,
                opening_balance=usd("0.00"),
            )

    def test_a_duplicate_is_refused_before_it_can_double_a_claim(self):
        """The harm the refusal exists to prevent, stated as a test.

        Attributions are indexed on ``transaction_id``.  Were the duplicate
        admitted, one attribution of 100.00 would attach to both copies and
        the claimant would be credited with 200.00 deposited from a single
        100.00 credit -- and the result would still balance, still foot, and
        still name its authority.  There is no downstream check that catches
        it, which is why the refusal has to sit at the front.
        """
        with self.assertRaises(TracingError) as caught:
            trace(
                [mv(1, 1, "100.00", CR), mv(2, 1, "100.00", CR)],
                [attr(1, "A", "100.00")],
                doctrine=Doctrine.lowest_intermediate_balance,
                opening_balance=usd("0.00"),
            )
        self.assertIn("appears twice", str(caught.exception))

    def test_a_duplicate_is_refused_even_when_the_filter_would_hide_it(self):
        """Checked over the input, not the admitted subset.

        The second copy here is P4 and would be dropped by the proof-class
        filter, so a check placed after filtering would pass.  It is placed
        before, so that widening the filter later cannot resurrect a
        double-count that was only ever masked by an exclusion.
        """
        with self.assertRaises(TracingError):
            trace(
                [
                    mv(1, 1, "100.00", CR),
                    mv(2, 1, "100.00", CR, proof_class=ProofClass.p4),
                ],
                [attr(1, "A", "100.00")],
                doctrine=Doctrine.lowest_intermediate_balance,
                opening_balance=usd("0.00"),
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
