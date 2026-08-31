"""Tests for :mod:`services.financial.linkage`.

Four things these tests exist to hold, beyond the obvious one that pairs which
should join do join.

**That ``same_side`` and ``counterparty`` stay opposite.**  This is the failure
mode with no downstream detector.  Treating a counterparty pair as redundant
deletes one leg of every transfer; treating a same-side pair as two payments
doubles a total.  In both cases every period still reconciles, because
:mod:`services.financial.reconcile` computes its identity per account and
neither error moves a single account's arithmetic.  So the relation is asserted
by name in every joining test, never inferred from the fact that a link exists.

**That the rules which look like over-caution are the load-bearing ones.**
Cliques rather than chains, mutual uniqueness rather than first-match, a scope
on every identifier, a crossed name comparison for counterparty pairs.  Each
has a test that fails if the rule is relaxed to the obvious alternative, and
each of those tests is written so that the obvious alternative *passes the
naive assertion* -- otherwise the test is not testing the rule.

**That ambiguity is reported rather than resolved.**  A debit answering to
three credits must produce three ambiguous links, not one confident one.  The
tests assert the count and the outcome, because a matcher that quietly picks
the nearest date would satisfy any test that only asked whether a link existed.

**That nothing collapses.**  A reconciled transaction retains all its
sources.  The module has no way to delete a row and these tests hold it to
that, so that a later refactor cannot borrow the supersede behaviour from
:mod:`services.financial.duplicates`, where it is correct, into here, where it
would destroy evidence.
"""

from __future__ import annotations

import dataclasses
import itertools
import random
import unittest
import uuid
from datetime import date

from postgres.models.enums import (
    DateSource,
    JoinTier,
    LinkOutcome,
    LinkRelation,
    ReferenceScope,
    TransactionDirection,
)
from services.financial import linkage
from services.financial.linkage import (
    DEFAULT_TOLERANCE_DAYS,
    MATCH_ACCOUNT,
    MATCH_ACCOUNTS_DIFFER,
    MATCH_AMOUNT,
    MATCH_COUNTERPARTY_NAME,
    MATCH_CURRENCY,
    MATCH_DATE,
    MATCH_DIRECTION,
    MATCH_IDENTIFIER,
    NAME_SIMILARITY_THRESHOLD,
    RAIL_TOLERANCE_DAYS,
    REFERENCE_BANK_REFERENCE,
    REFERENCE_CHEQUE_NUMBER,
    REFERENCE_NACHA_TRACE,
    REFERENCE_UUID,
    DateAgreement,
    Link,
    LinkConflict,
    LinkObservation,
    LinkageError,
    LinkageResult,
    ScopedReference,
    classify_relation,
    compare_dates,
    link_composite,
    link_exact_identifiers,
    link_probabilistic,
    link_transactions,
    name_agreement,
    name_similarity,
    normalise_name,
    references_from_bank_reference,
    tolerance_for_rail,
)
from services.financial.money import Money

DEBIT = TransactionDirection.debit
CREDIT = TransactionDirection.credit

#: A UUID that could plausibly be a UETR.  Written lower case; several tests
#: feed it back in other spellings to check canonicalisation.
UETR = "0197b9f2-0d1e-4c3a-8b5a-1f2e3d4c5b6a"


def ident(n: int) -> uuid.UUID:
    """A readable, ordered id.  ``ident(1) < ident(2)`` and both print small."""
    return uuid.UUID(int=n)


def observation(
    txn: int,
    *,
    account: int = 100,
    document: int = 900,
    minor: int = 50_000,
    currency: str = "USD",
    direction: TransactionDirection = DEBIT,
    day: int = 5,
    date_field: str = "value_date",
    ordering_source: DateSource = DateSource.value,
    counterparty: str | None = None,
    holder: str | None = None,
    is_reversal: bool = False,
    references: tuple[ScopedReference, ...] = (),
    **dates: date,
) -> LinkObservation:
    """A row, specified by the few fields any one test actually varies.

    ``date_field`` chooses which preferred field carries ``day``; the rest stay
    ``None``.  Tests that care about the preference order set the fields
    explicitly through ``**dates`` instead.
    """
    fields: dict[str, date | None] = {
        "transaction_date": None,
        "posted_date": None,
        "value_date": None,
        "effective_date": None,
    }
    if date_field:
        fields[date_field] = date(2024, 3, day)
    fields.update(dates)
    return LinkObservation(
        transaction_id=ident(txn),
        account_id=ident(account),
        source_document_id=ident(document),
        amount=Money.from_minor_units(minor, currency),
        direction=direction,
        ordering_date=date(2024, 3, day),
        ordering_date_source=ordering_source,
        counterparty_raw=counterparty,
        holder_name=holder,
        is_reversal=is_reversal,
        references=references,
        **fields,
    )


def uetr_reference(value: str = UETR) -> tuple[ScopedReference, ...]:
    return references_from_bank_reference(value)


def pairs(result: LinkageResult) -> set[tuple[int, int]]:
    """The links as readable integer pairs, for assertions that read."""
    return {(link.left_id.int, link.right_id.int) for link in result.links}


def only(result: LinkageResult) -> Link:
    """The single link a result was expected to hold."""
    assert len(result.links) == 1, f"expected one link, got {len(result.links)}"
    return result.links[0]


class ScopedReferenceTests(unittest.TestCase):
    """The scope is what makes "exact match" safe rather than merely confident."""

    def test_cheque_1001_in_two_accounts_is_two_references(self):
        """The case the whole class exists for.

        Cheque number 1001 exists in every chequebook ever printed.  Joining
        two accounts' cheque 1001 into one payment is a confident, mechanical,
        entirely wrong answer that no downstream check would catch, because the
        resulting "payment" has a plausible amount, a plausible date and two
        real sources.
        """
        first = ScopedReference(
            kind=REFERENCE_CHEQUE_NUMBER,
            scope=ReferenceScope.account,
            value="1001",
            scope_key="account-a",
        )
        second = ScopedReference(
            kind=REFERENCE_CHEQUE_NUMBER,
            scope=ReferenceScope.account,
            value="1001",
            scope_key="account-b",
        )
        self.assertNotEqual(first.join_key, second.join_key)

    def test_same_scope_and_value_is_one_reference(self):
        first = ScopedReference(
            kind=REFERENCE_CHEQUE_NUMBER,
            scope=ReferenceScope.account,
            value="1001",
            scope_key="account-a",
        )
        second = ScopedReference(
            kind=REFERENCE_CHEQUE_NUMBER,
            scope=ReferenceScope.account,
            value="1001",
            scope_key="account-a",
        )
        self.assertEqual(first.join_key, second.join_key)

    def test_a_scoped_reference_without_a_scope_key_is_refused(self):
        """Refused rather than silently widened to global.

        Widening is how a bare internal reference from two different banks
        becomes one payment, and it happens without any error to notice.
        """
        with self.assertRaises(LinkageError) as caught:
            ScopedReference(
                kind=REFERENCE_BANK_REFERENCE,
                scope=ReferenceScope.institution,
                value="ABC123",
            )
        self.assertIn("scope key", str(caught.exception))

    def test_a_global_reference_with_a_scope_key_is_refused(self):
        """The opposite mistake, and equally a lie about what was compared."""
        with self.assertRaises(LinkageError):
            ScopedReference(
                kind=REFERENCE_UUID,
                scope=ReferenceScope.global_,
                value=UETR,
                scope_key="bank-a",
            )

    def test_an_empty_value_or_kind_is_refused(self):
        with self.assertRaises(LinkageError):
            ScopedReference(
                kind=REFERENCE_UUID, scope=ReferenceScope.global_, value=""
            )
        with self.assertRaises(LinkageError):
            ScopedReference(
                kind="", scope=ReferenceScope.global_, value=UETR
            )

    def test_the_kind_participates_in_the_join_key(self):
        """A cheque number and a bank reference that read alike are not equal."""
        cheque = ScopedReference(
            kind=REFERENCE_CHEQUE_NUMBER,
            scope=ReferenceScope.account,
            value="1001",
            scope_key="a",
        )
        bank = ScopedReference(
            kind=REFERENCE_BANK_REFERENCE,
            scope=ReferenceScope.account,
            value="1001",
            scope_key="a",
        )
        self.assertNotEqual(cheque.join_key, bank.join_key)


class ReferencesFromBankReferenceTests(unittest.TestCase):
    """``bank_reference`` is one column holding four things; scope each honestly."""

    def test_a_uuid_is_recognised_and_scoped_globally(self):
        (reference,) = references_from_bank_reference(UETR)
        self.assertEqual(reference.kind, REFERENCE_UUID)
        self.assertIs(reference.scope, ReferenceScope.global_)
        self.assertIsNone(reference.scope_key)

    def test_the_same_uuid_in_four_spellings_yields_one_join_key(self):
        """The same UETR travels upper case in one system and lower in another.

        Comparing as written would leave a payment unjoined between two banks
        that both recorded it correctly.
        """
        spellings = [
            UETR,
            UETR.upper(),
            "{" + UETR + "}",
            "urn:uuid:" + UETR,
        ]
        keys = set()
        for spelling in spellings:
            references = references_from_bank_reference(spelling)
            self.assertEqual(len(references), 1, spelling)
            keys.add(references[0].join_key)
        self.assertEqual(len(keys), 1)

    def test_a_fifteen_digit_trace_from_a_nacha_file_carries_its_own_scope(self):
        """The leading eight digits are the ODFI routing prefix."""
        (reference,) = references_from_bank_reference(
            "021000021000001", parser_name="services.financial.nacha"
        )
        self.assertEqual(reference.kind, REFERENCE_NACHA_TRACE)
        self.assertIs(reference.scope, ReferenceScope.institution)
        self.assertEqual(reference.scope_key, "02100002")

    def test_a_trace_shaped_value_from_a_named_non_nacha_parser_is_not_a_trace(self):
        """Shape alone does not make a trace when the parser says otherwise.

        A BAI2 bank reference can be fifteen digits by coincidence.  Where the
        parser is recorded it is believed, because it is the stronger evidence.
        """
        (reference,) = references_from_bank_reference(
            "021000021000001",
            parser_name="services.financial.bai2",
            institution_key="bank-a",
        )
        self.assertEqual(reference.kind, REFERENCE_BANK_REFERENCE)

    def test_a_trace_shaped_value_with_no_parser_recorded_is_read_as_a_trace(self):
        """Shape is diagnostic when nothing better is available."""
        (reference,) = references_from_bank_reference("021000021000001")
        self.assertEqual(reference.kind, REFERENCE_NACHA_TRACE)

    def test_an_institution_reference_without_an_institution_is_dropped(self):
        """Nothing is better than an unscoped institution reference.

        Returning it unscoped would let two banks' internal counters collide
        into one payment, and the collision would look exactly like a match.
        """
        self.assertEqual(
            references_from_bank_reference(
                "ABC123", parser_name="services.financial.bai2"
            ),
            (),
        )

    def test_an_institution_reference_with_an_institution_is_kept(self):
        (reference,) = references_from_bank_reference(
            "ABC123",
            parser_name="services.financial.bai2",
            institution_key="bank-a",
        )
        self.assertEqual(reference.kind, REFERENCE_BANK_REFERENCE)
        self.assertEqual(reference.scope_key, "bank-a")

    def test_absent_and_blank_references_yield_nothing(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(
                    references_from_bank_reference(
                        value, institution_key="bank-a"
                    ),
                    (),
                )

    def test_surrounding_whitespace_does_not_make_two_references(self):
        first = references_from_bank_reference(
            " ABC123 ", institution_key="bank-a"
        )
        second = references_from_bank_reference(
            "ABC123", institution_key="bank-a"
        )
        self.assertEqual(first[0].join_key, second[0].join_key)


class LinkObservationTests(unittest.TestCase):
    def test_a_float_amount_is_refused(self):
        """Matching compares integer minor units.

        A float would make equality a matter of luck, and the luck would run
        out on the cases where two sources disagree in the last place.
        """
        with self.assertRaises(LinkageError) as caught:
            LinkObservation(
                transaction_id=ident(1),
                account_id=ident(100),
                source_document_id=ident(900),
                amount=500.0,  # type: ignore[arg-type]
                direction=DEBIT,
                ordering_date=date(2024, 3, 5),
                ordering_date_source=DateSource.value,
            )
        self.assertIn("Money", str(caught.exception))

    def test_currency_comes_from_the_amount(self):
        row = observation(1, currency="EUR")
        self.assertEqual(row.currency, "EUR")

    def test_date_for_reads_the_named_field_and_the_ordering_fallback(self):
        row = observation(1, date_field="posted_date", day=7)
        self.assertEqual(row.date_for("posted_date"), date(2024, 3, 7))
        self.assertIsNone(row.date_for("value_date"))
        self.assertEqual(row.date_for("ordering_date"), date(2024, 3, 7))

    def test_date_for_an_unknown_field_is_none_rather_than_an_error(self):
        self.assertIsNone(observation(1).date_for("settlement_date"))


class ClassifyRelationTests(unittest.TestCase):
    """The five arrangements two rows can be in, and what each one means."""

    def test_one_account_one_direction_two_documents_is_same_side(self):
        relation, reason = classify_relation(
            observation(1, account=100, document=900),
            observation(2, account=100, document=901),
        )
        self.assertIs(relation, LinkRelation.same_side)
        self.assertIsNone(reason)

    def test_two_accounts_opposite_directions_is_counterparty(self):
        relation, reason = classify_relation(
            observation(1, account=100, direction=DEBIT),
            observation(2, account=200, direction=CREDIT),
        )
        self.assertIs(relation, LinkRelation.counterparty)
        self.assertIsNone(reason)

    def test_two_rows_from_one_document_are_two_movements(self):
        """A repeated payment is indistinguishable from this.

        The document is a single reading and it states these as two movements.
        Joining them would turn a genuine second payment into a phantom
        duplicate, and there is nothing in the document to say which it was.
        """
        relation, reason = classify_relation(
            observation(1, account=100, document=900),
            observation(2, account=100, document=900),
        )
        self.assertIsNone(relation)
        self.assertIn("one document", reason)

    def test_one_account_opposite_directions_is_a_contradiction(self):
        relation, reason = classify_relation(
            observation(1, account=100, direction=DEBIT),
            observation(2, account=100, direction=CREDIT),
        )
        self.assertIsNone(relation)
        self.assertIn("opposite", reason)

    def test_a_reversal_explains_opposite_directions_in_one_account(self):
        """The one arrangement that would otherwise be reported as a conflict.

        A reversal legitimately carries the identifier of the entry it
        reverses, in the same account, in the opposite direction.  It is not a
        link and it is not a finding, so both are withheld.
        """
        relation, reason = classify_relation(
            observation(1, account=100, direction=DEBIT),
            observation(2, account=100, direction=CREDIT, is_reversal=True),
        )
        self.assertIsNone(relation)
        self.assertIsNone(reason)

    def test_two_accounts_same_direction_impugns_the_scope(self):
        relation, reason = classify_relation(
            observation(1, account=100, direction=DEBIT),
            observation(2, account=200, direction=DEBIT),
        )
        self.assertIsNone(relation)
        self.assertIn("not unique", reason)

    def test_classification_does_not_depend_on_argument_order(self):
        left = observation(1, account=100, direction=DEBIT)
        right = observation(2, account=200, direction=CREDIT)
        self.assertEqual(
            classify_relation(left, right), classify_relation(right, left)
        )


class CompareDatesTests(unittest.TestCase):
    """Like must be compared with like, or the gap is not evidence."""

    def test_value_date_is_preferred_when_both_rows_carry_it(self):
        agreement = compare_dates(
            observation(1, date_field="value_date", day=5),
            observation(2, date_field="value_date", day=8),
        )
        self.assertEqual(agreement.field, "value_date")
        self.assertEqual(agreement.gap_days, 3)
        self.assertTrue(agreement.like_for_like)

    def test_the_strongest_field_both_rows_carry_is_the_one_used(self):
        """Not the strongest either row carries.

        A row with a value date and a row with only a posted date have no
        value date in common, and comparing one against the other is comparing
        two different events.
        """
        left = observation(
            1,
            date_field="",
            value_date=date(2024, 3, 5),
            posted_date=date(2024, 3, 6),
        )
        right = observation(2, date_field="", posted_date=date(2024, 3, 7))
        agreement = compare_dates(left, right)
        self.assertEqual(agreement.field, "posted_date")
        self.assertEqual(agreement.gap_days, 1)

    def test_the_preference_order_is_value_posted_transaction_effective(self):
        both = {
            "value_date": date(2024, 3, 1),
            "posted_date": date(2024, 3, 2),
            "transaction_date": date(2024, 3, 3),
            "effective_date": date(2024, 3, 4),
        }
        expected = [
            "value_date",
            "posted_date",
            "transaction_date",
            "effective_date",
        ]
        self.assertEqual(list(linkage.DATE_FIELD_PREFERENCE), expected)
        for index, field in enumerate(expected):
            with self.subTest(field=field):
                available = dict(
                    itertools.islice(
                        ((k, both[k]) for k in expected[index:]), None
                    )
                )
                left = observation(1, date_field="", **available)
                right = observation(2, date_field="", **available)
                self.assertEqual(compare_dates(left, right).field, field)

    def test_no_shared_preferred_field_falls_back_to_ordering_date(self):
        left = observation(1, date_field="value_date", day=5)
        right = observation(2, date_field="posted_date", day=6)
        agreement = compare_dates(left, right)
        self.assertEqual(agreement.field, "ordering_date")
        self.assertEqual(agreement.gap_days, 1)

    def test_the_fallback_records_whether_the_two_orderings_meant_one_thing(self):
        """The single situation in which ``like_for_like`` is false.

        Two ordering dates drawn from different underlying fields differ partly
        by the rail's settlement lag, which is not evidence about whether these
        are one payment.
        """
        left = observation(
            1, date_field="value_date", day=5, ordering_source=DateSource.value
        )
        right = observation(
            2,
            date_field="posted_date",
            day=6,
            ordering_source=DateSource.posted,
        )
        self.assertFalse(compare_dates(left, right).like_for_like)

        matched = observation(
            2,
            date_field="posted_date",
            day=6,
            ordering_source=DateSource.value,
        )
        self.assertTrue(compare_dates(left, matched).like_for_like)

    def test_the_gap_is_unsigned(self):
        forward = compare_dates(
            observation(1, day=5), observation(2, day=9)
        )
        backward = compare_dates(
            observation(1, day=9), observation(2, day=5)
        )
        self.assertEqual(forward.gap_days, backward.gap_days)
        self.assertEqual(forward.gap_days, 4)


class NameComparisonTests(unittest.TestCase):
    def test_normalisation_folds_case_and_punctuation(self):
        self.assertEqual(
            normalise_name("Blue River, L.L.C."), "BLUE RIVER L L C"
        )
        self.assertEqual(normalise_name("  ACME   HOLDINGS  "), "ACME HOLDINGS")

    def test_normalisation_does_not_strip_corporate_suffixes(self):
        """"ACME LTD" and "ACME INC" are two companies.

        A normaliser that made them equal would hand tier 2 a confident wrong
        answer in the one place a reviewer is meant to be able to trust the
        shortlist.
        """
        self.assertNotEqual(
            normalise_name("ACME LTD"), normalise_name("ACME INC")
        )

    def test_a_missing_name_scores_none_rather_than_zero(self):
        """Absence and disagreement call for different handling.

        Scoring a missing name zero would reject a pair for a reason that is
        not about the pair.
        """
        self.assertIsNone(name_similarity(None, "ACME"))
        self.assertIsNone(name_similarity("ACME", ""))
        self.assertIsNone(name_similarity("!!!", "ACME"))

    def test_spelling_variants_of_one_name_clear_the_threshold(self):
        score = name_similarity("ACME HOLDINGS LTD", "ACME HOLDINGS LIMITED")
        self.assertGreaterEqual(score, NAME_SIMILARITY_THRESHOLD)

    def test_different_names_do_not_clear_the_threshold(self):
        for left, right in (
            ("ACME", "APEX"),
            ("BLUE RIVER LLC", "RED MOUNTAIN LLC"),
            ("JOHN SMITH", "JANE SMITH"),
        ):
            with self.subTest(left=left, right=right):
                self.assertLess(
                    name_similarity(left, right), NAME_SIMILARITY_THRESHOLD
                )


class CrossedNameTests(unittest.TestCase):
    """A counterparty name means the opposite thing on each side of a pair.

    These tests are the reason :func:`name_agreement` exists rather than a
    bare call to :func:`name_similarity`.
    """

    def _pair(self):
        payer = observation(
            1,
            account=100,
            direction=DEBIT,
            counterparty="ACME HOLDINGS LIMITED",
            holder="BLUE RIVER LLC",
        )
        payee = observation(
            2,
            account=200,
            direction=CREDIT,
            counterparty="BLUE RIVER L.L.C.",
            holder="ACME HOLDINGS LTD",
        )
        return payer, payee

    def test_the_naive_comparison_rejects_a_genuine_counterparty_pair(self):
        """The bug this module is written to avoid, demonstrated.

        Comparing the two ``counterparty_raw`` strings directly compares a
        payee's name with a payer's name.  For a *genuine* pair these are two
        different companies, so the naive rule scores near zero and rejects
        exactly the pairs it exists to find.
        """
        payer, payee = self._pair()
        naive = name_similarity(payer.counterparty_raw, payee.counterparty_raw)
        self.assertLess(naive, NAME_SIMILARITY_THRESHOLD)

    def test_the_crossed_comparison_accepts_it(self):
        payer, payee = self._pair()
        crossed = name_agreement(payer, payee, LinkRelation.counterparty)
        self.assertGreaterEqual(crossed, NAME_SIMILARITY_THRESHOLD)

    def test_same_side_uses_the_direct_comparison(self):
        """Both rows are one movement in one account, so both name the same
        other party and comparing them to each other is right."""
        first = observation(1, document=900, counterparty="ACME HOLDINGS LTD")
        second = observation(
            2, document=901, counterparty="ACME HOLDINGS LIMITED"
        )
        self.assertGreaterEqual(
            name_agreement(first, second, LinkRelation.same_side),
            NAME_SIMILARITY_THRESHOLD,
        )

    def test_the_weaker_half_of_a_crossed_comparison_is_what_counts(self):
        """One side agreeing while the other disagrees is not corroboration.

        It is one agreement and one disagreement, and a rule that took the
        better of the two would let a single matching name carry a pair whose
        other name says it is somebody else.
        """
        payer = observation(
            1,
            account=100,
            direction=DEBIT,
            counterparty="ACME HOLDINGS LIMITED",
            holder="BLUE RIVER LLC",
        )
        payee = observation(
            2,
            account=200,
            direction=CREDIT,
            counterparty="ZENITH TRADING SA",
            holder="ACME HOLDINGS LTD",
        )
        score = name_agreement(payer, payee, LinkRelation.counterparty)
        self.assertLess(score, NAME_SIMILARITY_THRESHOLD)

    def test_one_usable_crossed_comparison_is_enough_to_score(self):
        """Half the names present is weak evidence, not absent evidence."""
        payer = observation(
            1,
            account=100,
            direction=DEBIT,
            counterparty="ACME HOLDINGS LIMITED",
            holder=None,
        )
        payee = observation(
            2,
            account=200,
            direction=CREDIT,
            counterparty=None,
            holder="ACME HOLDINGS LTD",
        )
        score = name_agreement(payer, payee, LinkRelation.counterparty)
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, NAME_SIMILARITY_THRESHOLD)

    def test_no_usable_comparison_scores_none(self):
        payer = observation(1, account=100, direction=DEBIT)
        payee = observation(2, account=200, direction=CREDIT)
        self.assertIsNone(
            name_agreement(payer, payee, LinkRelation.counterparty)
        )


class LinkInvariantTests(unittest.TestCase):
    def test_a_row_cannot_be_linked_to_itself(self):
        """A self-link would make every row its own corroboration."""
        with self.assertRaises(LinkageError):
            Link(
                left_id=ident(1),
                right_id=ident(1),
                relation=LinkRelation.same_side,
                tier=JoinTier.exact_identifier,
                outcome=LinkOutcome.resolved,
                components=(),
            )

    def test_endpoints_must_be_stored_in_sorted_order(self):
        """So that one pair yields one link object however it was encountered."""
        with self.assertRaises(LinkageError):
            Link(
                left_id=ident(2),
                right_id=ident(1),
                relation=LinkRelation.same_side,
                tier=JoinTier.exact_identifier,
                outcome=LinkOutcome.resolved,
                components=(),
            )

    def test_an_ambiguous_link_is_not_asserted_at_any_tier(self):
        """The condition that gets forgotten.

        Tier 0 is the strongest evidence the corpus can offer, and an
        ambiguous tier-0 match is still a shortlist rather than an answer.
        """
        for tier in JoinTier:
            with self.subTest(tier=tier):
                link = Link(
                    left_id=ident(1),
                    right_id=ident(2),
                    relation=LinkRelation.counterparty,
                    tier=tier,
                    outcome=LinkOutcome.ambiguous,
                    components=(),
                )
                self.assertFalse(link.is_asserted)

    def test_a_resolved_probabilistic_link_is_not_asserted(self):
        """Tier 2 is a proposal by construction, however clean the match."""
        link = Link(
            left_id=ident(1),
            right_id=ident(2),
            relation=LinkRelation.counterparty,
            tier=JoinTier.probabilistic,
            outcome=LinkOutcome.resolved,
            components=(),
        )
        self.assertFalse(link.is_asserted)

    def test_resolved_links_below_tier_two_are_asserted(self):
        for tier in (JoinTier.exact_identifier, JoinTier.deterministic_composite):
            with self.subTest(tier=tier):
                link = Link(
                    left_id=ident(1),
                    right_id=ident(2),
                    relation=LinkRelation.same_side,
                    tier=tier,
                    outcome=LinkOutcome.resolved,
                    components=(),
                )
                self.assertTrue(link.is_asserted)


class RailToleranceTests(unittest.TestCase):
    def test_every_rail_has_a_window(self):
        for rail, days in RAIL_TOLERANCE_DAYS.items():
            with self.subTest(rail=rail):
                self.assertGreaterEqual(days, 0)
                self.assertEqual(tolerance_for_rail(rail), days)

    def test_an_unknown_rail_falls_back_to_the_narrow_default(self):
        """The safe reading of a rail nobody has heard of is that nothing is
        known about its settlement timing, which is what the default encodes."""
        self.assertEqual(tolerance_for_rail("carrier-pigeon"), DEFAULT_TOLERANCE_DAYS)
        self.assertEqual(tolerance_for_rail(None), DEFAULT_TOLERANCE_DAYS)

    def test_ach_is_wider_than_wire_and_cheque_wider_than_both(self):
        """The ordering is the part that carries meaning.

        Fedwire settles same day; ACH settles in up to two banking days, which
        across a weekend is four calendar days; cheques clear over a longer and
        much less predictable interval.
        """
        self.assertLess(
            RAIL_TOLERANCE_DAYS[linkage.RAIL_WIRE],
            RAIL_TOLERANCE_DAYS[linkage.RAIL_ACH],
        )
        self.assertLess(
            RAIL_TOLERANCE_DAYS[linkage.RAIL_ACH],
            RAIL_TOLERANCE_DAYS[linkage.RAIL_CHEQUE],
        )


class ExactIdentifierGroupingTests(unittest.TestCase):
    """Tier 0: what a shared scoped identifier does and does not settle."""

    def test_two_readings_of_one_movement_are_same_side(self):
        rows = [
            observation(1, document=900, references=uetr_reference()),
            observation(2, document=901, references=uetr_reference()),
        ]
        link = only(link_exact_identifiers(rows))
        self.assertIs(link.relation, LinkRelation.same_side)
        self.assertIs(link.tier, JoinTier.exact_identifier)
        self.assertIs(link.outcome, LinkOutcome.resolved)
        self.assertTrue(link.is_asserted)

    def test_the_two_ends_of_a_payment_are_counterparty(self):
        """The distinction this module exists for, in its simplest form.

        Both rows are real and both belong in their own account's totals.  The
        same two rows read as ``same_side`` would count one payment twice, and
        no downstream identity check would notice: each account's arithmetic
        closes either way.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, references=uetr_reference()),
        ]
        link = only(link_exact_identifiers(rows))
        self.assertIs(link.relation, LinkRelation.counterparty)
        self.assertIn(MATCH_ACCOUNTS_DIFFER, link.components)
        self.assertNotIn(MATCH_ACCOUNT, link.components)

    def test_three_rows_sharing_one_identifier_give_all_three_pairs(self):
        """Equality is transitive, so tier 0 groups rather than pairs.

        Pairing would leave the third row attached to only whichever of the
        first two it happened to be compared against.
        """
        rows = [
            observation(n, document=900 + n, references=uetr_reference())
            for n in (1, 2, 3)
        ]
        self.assertEqual(
            pairs(link_exact_identifiers(rows)), {(1, 2), (1, 3), (2, 3)}
        )

    def test_a_correspondent_chain_is_not_ambiguous(self):
        """The tier-0 rule that is the reverse of the tier-1 rule.

        A UETR is *designed* to travel unchanged through intermediaries, so one
        identifier spanning a payer, a correspondent and a payee is the format
        working.  Reporting several partners as ambiguity here would flag the
        exact case the standard was built to make unambiguous -- which is why
        this cannot simply reuse tier 1's mutual-uniqueness rule.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, references=uetr_reference()),
            observation(3, account=300, direction=CREDIT, references=uetr_reference()),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(pairs(result), {(1, 2), (1, 3)})
        for link in result.links:
            with self.subTest(pair=(link.left_id.int, link.right_id.int)):
                self.assertIs(link.outcome, LinkOutcome.resolved)
                self.assertTrue(link.is_asserted)

    def test_two_rows_from_one_document_are_two_movements(self):
        """A repeated payment is indistinguishable from this.

        The document is a single reading and it states two movements; treating
        them as one reading seen twice would delete a real payment.  So: not a
        link.  But not silence either -- one reference against two movements in
        one statement is an issuer reusing a reference, which is a finding in
        its own right and is reported as a conflict.  The two halves are worth
        asserting together, because dropping the link without recording why is
        how a real identifier defect leaves no trace.
        """
        rows = [
            observation(1, document=900, references=uetr_reference()),
            observation(2, document=900, references=uetr_reference()),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(len(result.conflicts), 1)
        self.assertIn("one document", result.conflicts[0].reason)

    def test_a_row_carrying_one_reference_twice_is_not_a_pair(self):
        """A self-link would make a row its own corroboration."""
        doubled = uetr_reference() + uetr_reference()
        result = link_exact_identifiers([observation(1, references=doubled)])
        self.assertEqual(result.links, ())
        self.assertEqual(result.conflicts, ())

    def test_amounts_may_differ_under_one_identifier(self):
        """A payment can arrive net of a correspondent's fee.

        Requiring equality here would reject the pair the identifier exists to
        settle, so the components record what agreed instead of gating on it.
        """
        rows = [
            observation(
                1, account=100, direction=DEBIT, minor=50_000,
                references=uetr_reference(),
            ),
            observation(
                2, account=200, direction=CREDIT, minor=49_750,
                references=uetr_reference(),
            ),
        ]
        link = only(link_exact_identifiers(rows))
        self.assertIn(MATCH_CURRENCY, link.components)
        self.assertNotIn(MATCH_AMOUNT, link.components)

    def test_a_currency_mismatch_records_neither_currency_nor_amount(self):
        rows = [
            observation(
                1, account=100, direction=DEBIT, currency="USD",
                references=uetr_reference(),
            ),
            observation(
                2, account=200, direction=CREDIT, currency="EUR",
                references=uetr_reference(),
            ),
        ]
        link = only(link_exact_identifiers(rows))
        self.assertNotIn(MATCH_CURRENCY, link.components)
        self.assertNotIn(MATCH_AMOUNT, link.components)

    def test_dates_are_irrelevant_to_a_tier_zero_match(self):
        """An identifier settles the pair; the gap is recorded, not required."""
        rows = [
            observation(1, day=1, document=900, references=uetr_reference()),
            observation(2, day=28, document=901, references=uetr_reference()),
        ]
        link = only(link_exact_identifiers(rows))
        self.assertIs(link.outcome, LinkOutcome.resolved)
        self.assertEqual(link.date_agreement.gap_days, 27)


class ScopeSeparationTests(unittest.TestCase):
    """The part that stops cheque 1001 joining cheque 1001."""

    @staticmethod
    def _cheque(number: str, account: str) -> tuple[ScopedReference, ...]:
        return (
            ScopedReference(
                kind=REFERENCE_CHEQUE_NUMBER,
                scope=ReferenceScope.account,
                value=number,
                scope_key=account,
            ),
        )

    def test_one_cheque_number_in_two_accounts_does_not_join(self):
        """Every chequebook contains a cheque 1001."""
        rows = [
            observation(1, account=100, references=self._cheque("1001", "acct-a")),
            observation(2, account=200, references=self._cheque("1001", "acct-b")),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(result.conflicts, ())

    def test_one_cheque_number_within_one_account_does_join(self):
        rows = [
            observation(
                1, document=900, references=self._cheque("1001", "acct-a")
            ),
            observation(
                2, document=901, references=self._cheque("1001", "acct-a")
            ),
        ]
        link = only(link_exact_identifiers(rows))
        self.assertIs(link.relation, LinkRelation.same_side)
        self.assertEqual(link.reference.value, "1001")

    def test_the_same_value_under_two_kinds_does_not_join(self):
        """Kind is part of the join key, so a trace and a cheque never meet."""
        rows = [
            observation(
                1,
                document=900,
                references=(
                    ScopedReference(
                        kind=REFERENCE_CHEQUE_NUMBER,
                        scope=ReferenceScope.account,
                        value="1001",
                        scope_key="acct-a",
                    ),
                ),
            ),
            observation(
                2,
                document=901,
                references=(
                    ScopedReference(
                        kind=REFERENCE_BANK_REFERENCE,
                        scope=ReferenceScope.account,
                        value="1001",
                        scope_key="acct-a",
                    ),
                ),
            ),
        ]
        self.assertEqual(link_exact_identifiers(rows).links, ())


class ConflictTests(unittest.TestCase):
    """What tier 0 says when a shared identifier cannot mean a shared payment."""

    def test_one_identifier_paying_out_of_two_accounts_is_a_conflict(self):
        """The declared scope is wider than the value's real uniqueness."""
        rows = [
            observation(1, account=100, direction=DEBIT, references=uetr_reference()),
            observation(2, account=200, direction=DEBIT, references=uetr_reference()),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(len(result.conflicts), 1)
        self.assertIn("not unique", result.conflicts[0].reason)

    def test_one_account_moving_both_ways_is_a_conflict(self):
        rows = [
            observation(1, direction=DEBIT, references=uetr_reference()),
            observation(2, direction=CREDIT, references=uetr_reference()),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(len(result.conflicts), 1)
        self.assertIn("opposite", result.conflicts[0].reason)

    def test_a_reversal_explains_it_and_is_neither_link_nor_conflict(self):
        """The one arrangement that would otherwise read as an identifier clash.

        A reversal legitimately carries the reversed entry's identifier, in the
        same account, in the opposite direction.  It is not a link either: the
        two rows are two movements, and joining them would net a real payment
        against a real correction.
        """
        rows = [
            observation(1, direction=DEBIT, references=uetr_reference()),
            observation(
                2, direction=CREDIT, is_reversal=True, references=uetr_reference()
            ),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(result.conflicts, ())

    def test_a_conflict_carries_the_reference_that_caused_it(self):
        """So a finding can be shown, not merely counted."""
        rows = [
            observation(1, account=100, direction=DEBIT, references=uetr_reference()),
            observation(2, account=200, direction=DEBIT, references=uetr_reference()),
        ]
        conflict = link_exact_identifiers(rows).conflicts[0]
        self.assertEqual(conflict.reference.value, UETR)
        self.assertEqual(conflict.reference.kind, REFERENCE_UUID)

    def test_a_conflicting_pair_still_conflicts_with_a_third_row(self):
        """Every pair in the group is judged, not just the first."""
        rows = [
            observation(n, account=100 * n, direction=DEBIT, references=uetr_reference())
            for n in (1, 2, 3)
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(
            {(c.left_id.int, c.right_id.int) for c in result.conflicts},
            {(1, 2), (1, 3), (2, 3)},
        )


class CompositeTierTests(unittest.TestCase):
    """Tier 1: amount, currency, direction and a date within tolerance."""

    def test_a_pair_inside_tolerance_is_asserted(self):
        rows = [
            observation(1, document=900, day=5),
            observation(2, document=901, day=6),
        ]
        link = only(link_composite(rows, tolerance_days=2))
        self.assertIs(link.tier, JoinTier.deterministic_composite)
        self.assertIs(link.outcome, LinkOutcome.resolved)
        self.assertTrue(link.is_asserted)
        self.assertEqual(link.date_agreement.gap_days, 1)

    def test_the_tolerance_boundary_is_inclusive(self):
        """A window of two days means two days, not one.

        Asserted from both sides so that an off-by-one in either direction
        fails: a rule that admitted three would pass a test that only checked
        two.
        """
        inside = [observation(1, document=900, day=5), observation(2, document=901, day=7)]
        outside = [observation(1, document=900, day=5), observation(2, document=901, day=8)]
        self.assertEqual(len(link_composite(inside, tolerance_days=2).links), 1)
        self.assertEqual(link_composite(outside, tolerance_days=2).links, ())

    def test_amounts_must_be_equal_to_the_minor_unit(self):
        """No amount tolerance, deliberately.

        Two payments differing by a fee are two payments; matching across the
        fee would merge them and no later check would notice.  Where a fee
        genuinely splits one payment, the identifier that survives it joins it
        at tier 0.
        """
        rows = [
            observation(1, document=900, minor=50_000),
            observation(2, document=901, minor=49_999),
        ]
        self.assertEqual(link_composite(rows).links, ())

    def test_currencies_do_not_cross(self):
        """50,000 minor units of USD is not 50,000 minor units of EUR.

        Blocking is on ``(currency, minor_units)`` together, so this separates
        no pair that could have matched -- every tier below tier 0 requires
        both anyway.
        """
        rows = [
            observation(1, document=900, currency="USD"),
            observation(2, document=901, currency="EUR"),
        ]
        self.assertEqual(link_composite(rows).links, ())

    def test_an_unlike_date_comparison_is_refused(self):
        """Where the two rows share no preferred field, the fallback is unlike.

        The gap between a booking date and a value date is partly the rail's
        settlement lag rather than a discrepancy, and tier 1 is asserted
        without a person, so it declines.  The pair is still reachable at
        tier 2, where somebody looks at it.
        """
        rows = [
            observation(
                1, document=900, date_field="posted_date", day=5,
                ordering_source=DateSource.posted,
            ),
            observation(
                2, document=901, date_field="value_date", day=5,
                ordering_source=DateSource.value,
            ),
        ]
        agreement = compare_dates(*rows)
        self.assertFalse(agreement.like_for_like)
        self.assertEqual(agreement.gap_days, 0)  # would match on the number alone
        self.assertEqual(link_composite(rows).links, ())

    def test_rows_in_one_document_do_not_join_at_tier_one_either(self):
        """The relation rules are the same at every tier."""
        rows = [observation(1, document=900), observation(2, document=900)]
        self.assertEqual(link_composite(rows).links, ())

    def test_tier_one_produces_no_conflicts(self):
        """A conflict contradicts an assertion, and tier 1 asserted nothing.

        A pair that fails here simply did not match.
        """
        rows = [
            observation(1, account=100, direction=DEBIT),
            observation(2, account=200, direction=DEBIT),
        ]
        result = link_composite(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(result.conflicts, ())

    def test_components_name_the_fields_that_actually_participated(self):
        """A full composite key wants both account identifiers; the ledger
        has one.

        Recording what was checked rather than claiming the full key is what
        keeps a link made today distinguishable from one made after
        counterparty account identifiers land.
        """
        rows = [
            observation(1, account=100, direction=DEBIT),
            observation(2, account=200, direction=CREDIT),
        ]
        link = only(link_composite(rows))
        self.assertEqual(
            link.components,
            (MATCH_CURRENCY, MATCH_AMOUNT, MATCH_ACCOUNTS_DIFFER, MATCH_DIRECTION, MATCH_DATE),
        )
        self.assertIsNone(link.reference)


class MutualUniquenessTests(unittest.TestCase):
    """One payment has two ends, so a third candidate is a question."""

    def test_two_candidate_partners_make_both_links_ambiguous(self):
        """The useful output is that there are two, not a guess between them.

        Both are returned so a reviewer sees the shortlist; neither is
        asserted, because asserting either would be a coin toss recorded as a
        finding.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, day=5),
            observation(2, account=200, direction=CREDIT, day=5),
            observation(3, account=300, direction=CREDIT, day=5),
        ]
        result = link_composite(rows)
        self.assertEqual(pairs(result), {(1, 2), (1, 3)})
        for link in result.links:
            with self.subTest(pair=(link.left_id.int, link.right_id.int)):
                self.assertIs(link.outcome, LinkOutcome.ambiguous)
                self.assertFalse(link.is_asserted)

    def test_an_unambiguous_pair_beside_an_ambiguous_one_is_still_resolved(self):
        """Ambiguity is per payment, not per corpus.

        A run containing one contested payment must not downgrade every other
        match in it.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, minor=50_000),
            observation(2, account=200, direction=CREDIT, minor=50_000),
            observation(3, account=300, direction=CREDIT, minor=50_000),
            observation(4, account=100, direction=DEBIT, minor=77_700),
            observation(5, account=200, direction=CREDIT, minor=77_700),
        ]
        by_pair = {
            (link.left_id.int, link.right_id.int): link.outcome
            for link in link_composite(rows).links
        }
        self.assertIs(by_pair[(4, 5)], LinkOutcome.resolved)
        self.assertIs(by_pair[(1, 2)], LinkOutcome.ambiguous)
        self.assertIs(by_pair[(1, 3)], LinkOutcome.ambiguous)


class CliqueTests(unittest.TestCase):
    """Tolerance does not compose, so a same-side group must be a clique."""

    def test_a_chain_of_tolerances_is_not_a_group(self):
        """A is two days from B and B two days from C; A is four days from C.

        Admitting the chain would silently widen the window to the length of
        the chain, which is the failure this rule exists to stop.  The three
        rows are still reported -- as an ambiguous group, which is what they
        are -- rather than dropped.
        """
        rows = [
            observation(1, document=901, day=1),
            observation(2, document=902, day=3),
            observation(3, document=903, day=5),
        ]
        result = link_composite(rows, tolerance_days=2)
        self.assertEqual(pairs(result), {(1, 2), (2, 3)})
        for link in result.links:
            with self.subTest(pair=(link.left_id.int, link.right_id.int)):
                self.assertIs(link.outcome, LinkOutcome.ambiguous)

    def test_a_group_where_every_pair_agrees_is_resolved(self):
        """The same three rows inside one window, to show the rule is not
        simply refusing all groups of three."""
        rows = [
            observation(1, document=901, day=4),
            observation(2, document=902, day=5),
            observation(3, document=903, day=6),
        ]
        result = link_composite(rows, tolerance_days=2)
        self.assertEqual(pairs(result), {(1, 2), (1, 3), (2, 3)})
        for link in result.links:
            with self.subTest(pair=(link.left_id.int, link.right_id.int)):
                self.assertIs(link.outcome, LinkOutcome.resolved)


class ProbabilisticTierTests(unittest.TestCase):
    """Tier 2: proposals, never assertions."""

    @staticmethod
    def _pair(day_left: int = 5, day_right: int = 9) -> list[LinkObservation]:
        return [
            observation(
                1, account=100, direction=DEBIT, day=day_left,
                counterparty="ACME HOLDINGS LIMITED", holder="BLUE RIVER LLC",
            ),
            observation(
                2, account=200, direction=CREDIT, day=day_right,
                counterparty="BLUE RIVER L.L.C.", holder="ACME HOLDINGS LTD",
            ),
        ]

    def test_a_clean_tier_two_match_is_still_only_a_proposal(self):
        link = only(link_probabilistic(self._pair()))
        self.assertIs(link.tier, JoinTier.probabilistic)
        self.assertIs(link.outcome, LinkOutcome.resolved)
        self.assertFalse(link.is_asserted)

    def test_the_similarity_is_recorded_on_the_link(self):
        """A reviewer choosing within a shortlist needs the score."""
        link = only(link_probabilistic(self._pair()))
        self.assertGreaterEqual(link.name_similarity, NAME_SIMILARITY_THRESHOLD)
        self.assertIn(MATCH_COUNTERPARTY_NAME, link.components)

    def test_names_below_the_threshold_are_not_proposed(self):
        rows = self._pair()
        rows[1] = observation(
            2, account=200, direction=CREDIT, day=9,
            counterparty="ENTIRELY DIFFERENT PARTY", holder="SOMETHING ELSE",
        )
        self.assertEqual(link_probabilistic(rows).links, ())

    def test_missing_names_are_not_proposed(self):
        """Absence is not similarity.

        Without the name this tier is amount and a fortnight, which in a corpus
        of round-numbered rent pairs everything with everything; and a proposal
        a reviewer cannot evaluate is worse than no proposal.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, day=5),
            observation(2, account=200, direction=CREDIT, day=9),
        ]
        self.assertEqual(link_probabilistic(rows).links, ())

    def test_an_unlike_date_comparison_is_admitted_and_recorded(self):
        """The refusal tier 1 makes, relaxed here because a person sees it.

        A booking date against a value date is weak evidence rather than none,
        and weak evidence in front of somebody is what this tier is for.
        """
        rows = [
            observation(
                1, account=100, direction=DEBIT, day=5,
                date_field="posted_date", ordering_source=DateSource.posted,
                counterparty="ACME HOLDINGS LIMITED", holder="BLUE RIVER LLC",
            ),
            observation(
                2, account=200, direction=CREDIT, day=9,
                date_field="value_date", ordering_source=DateSource.value,
                counterparty="BLUE RIVER L.L.C.", holder="ACME HOLDINGS LTD",
            ),
        ]
        link = only(link_probabilistic(rows))
        self.assertFalse(link.date_agreement.like_for_like)

    def test_the_wider_window_is_what_makes_this_tier_reachable(self):
        """Outside tier 1's window, inside tier 2's."""
        rows = self._pair(day_left=1, day_right=12)
        self.assertEqual(link_composite(rows).links, ())
        self.assertEqual(len(link_probabilistic(rows).links), 1)

    def test_beyond_the_wider_window_nothing_is_proposed(self):
        rows = self._pair(day_left=5, day_right=9)
        self.assertEqual(link_probabilistic(rows, tolerance_days=3).links, ())


class CascadeTests(unittest.TestCase):
    """The three tiers run together: what carries between them, and what must not."""

    def test_each_tier_is_reachable_in_one_pass(self):
        """A corpus arranged so that exactly one pair lands at each tier."""
        rows = [
            observation(1, account=100, direction=DEBIT, minor=10_000,
                        references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, minor=10_000,
                        references=uetr_reference()),
            observation(3, account=100, direction=DEBIT, minor=20_000, day=5),
            observation(4, account=200, direction=CREDIT, minor=20_000, day=6),
            observation(5, account=100, direction=DEBIT, minor=30_000, day=1,
                        counterparty="ACME HOLDINGS LIMITED", holder="BLUE RIVER LLC"),
            observation(6, account=200, direction=CREDIT, minor=30_000, day=12,
                        counterparty="BLUE RIVER L.L.C.", holder="ACME HOLDINGS LTD"),
        ]
        by_pair = {
            (link.left_id.int, link.right_id.int): link.tier
            for link in link_transactions(rows).links
        }
        self.assertEqual(by_pair[(1, 2)], JoinTier.exact_identifier)
        self.assertEqual(by_pair[(3, 4)], JoinTier.deterministic_composite)
        self.assertEqual(by_pair[(5, 6)], JoinTier.probabilistic)

    def test_a_pair_claimed_by_a_stronger_tier_is_claimed_once(self):
        """Otherwise every tier-0 pair would reappear as a tier-1 duplicate."""
        rows = [
            observation(1, account=100, direction=DEBIT, references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, references=uetr_reference()),
        ]
        result = link_transactions(rows)
        self.assertEqual(len(result.links), 1)
        self.assertIs(result.links[0].tier, JoinTier.exact_identifier)

    def test_the_suppression_is_of_the_pair_not_the_row(self):
        """A third sighting with no identifier still joins the group.

        A and B share a UETR; C is the same account, the same amount, one day
        later, and carries nothing.  Suppressing *rows* seen at tier 0 would
        make C unreachable; suppressing pairs leaves it reachable, which is the
        whole reason the exclusion is written the way it is.
        """
        rows = [
            observation(1, document=901, day=5, references=uetr_reference()),
            observation(2, document=902, day=5, references=uetr_reference()),
            observation(3, document=903, day=6),
        ]
        result = link_transactions(rows, tolerance_days=2)
        self.assertEqual(pairs(result), {(1, 2), (1, 3), (2, 3)})

    def test_a_tier_zero_equality_satisfies_the_clique_test_below_it(self):
        """The half of the rule above that only shows up in the outcome.

        The links exist either way; what the equality changes is whether the
        group is *resolved*.  Tier 1 cannot see the A-B edge -- it was claimed
        and excluded -- so a clique test built from tier 1's candidates alone
        finds a triangle missing a side and reports ambiguity that is not
        there.  Asserted against the counterfactual immediately below, because
        the resolved outcome alone would also pass if the rule were simply
        dropped.
        """
        rows = [
            observation(1, document=901, day=5, references=uetr_reference()),
            observation(2, document=902, day=5, references=uetr_reference()),
            observation(3, document=903, day=6),
        ]
        for link in link_transactions(rows, tolerance_days=2).links:
            with self.subTest(pair=(link.left_id.int, link.right_id.int)):
                self.assertIs(link.outcome, LinkOutcome.resolved)

    def test_without_the_equality_the_same_group_reads_as_ambiguous(self):
        """The counterfactual: tier 1 alone, with the tier-0 pair excluded.

        This is what the cascade did before the equalities were threaded
        through, and it is what the test above would silently permit if the
        threading were removed.
        """
        rows = [
            observation(1, document=901, day=5, references=uetr_reference()),
            observation(2, document=902, day=5, references=uetr_reference()),
            observation(3, document=903, day=6),
        ]
        claimed = frozenset(link.pair for link in link_exact_identifiers(rows).links)
        bare = link_composite(rows, tolerance_days=2, exclude_pairs=claimed)
        self.assertEqual(pairs(bare), {(1, 3), (2, 3)})
        for link in bare.links:
            with self.subTest(pair=(link.left_id.int, link.right_id.int)):
                self.assertIs(link.outcome, LinkOutcome.ambiguous)

    def test_a_tier_one_edge_is_never_promoted_to_an_equality(self):
        """Two tolerances in a chain is exactly what the clique rule forbids.

        Rows 1 and 3 are two days apart and resolve at tier 1.  Row 2 is five
        days from row 3 and seven from row 1, so it reaches neither at tier 1
        but reaches both inside tier 2's wider window.  Tier 2 therefore sees a
        three-row component with the 1-3 side missing, because tier 1 claimed
        it.

        If tier-1 edges were passed down as established, that side would be
        filled in, the component would look like a clique and the group would
        resolve -- resting on a two-day tolerance chained to a five-day one,
        which is the composition the rule exists to refuse.  Only tier 0's
        equalities may fill such a gap.
        """
        rows = [
            observation(1, document=901, day=1, counterparty="ACME HOLDINGS LIMITED"),
            observation(3, document=903, day=3, counterparty="ACME HOLDINGS LIMITED"),
            observation(2, document=902, day=8, counterparty="ACME HOLDINGS LIMITED"),
        ]
        result = link_transactions(
            rows, tolerance_days=2, probabilistic_tolerance_days=7
        )
        by_pair = {
            (link.left_id.int, link.right_id.int): link for link in result.links
        }
        self.assertEqual(set(by_pair), {(1, 3), (1, 2), (2, 3)})
        self.assertIs(by_pair[(1, 3)].tier, JoinTier.deterministic_composite)
        self.assertIs(by_pair[(1, 3)].outcome, LinkOutcome.resolved)
        for pair_ in ((1, 2), (2, 3)):
            with self.subTest(pair=pair_):
                self.assertIs(by_pair[pair_].tier, JoinTier.probabilistic)
                self.assertIs(by_pair[pair_].outcome, LinkOutcome.ambiguous)

    def test_a_pair_a_stronger_tier_rejected_may_still_be_proposed(self):
        """Rejection at tier 1 is not a verdict, it is that tier declining.

        A gap outside the settlement window is not evidence of two payments;
        it is evidence that nothing can be asserted without somebody looking.
        Tier 2 exists to put it in front of somebody -- as a proposal, never
        asserted.
        """
        rows = [
            observation(1, document=901, day=1, counterparty="ACME HOLDINGS LIMITED"),
            observation(2, document=902, day=5, counterparty="ACME HOLDINGS LIMITED"),
        ]
        self.assertEqual(link_composite(rows, tolerance_days=2).links, ())
        link = only(link_transactions(rows, tolerance_days=2))
        self.assertIs(link.tier, JoinTier.probabilistic)
        self.assertFalse(link.is_asserted)

    def test_a_counterparty_resolved_at_tier_zero_is_not_re_partnered(self):
        """One-to-one is a property of the payment, not of the tier.

        Row 1's partner is settled by identifier.  Row 3 matches row 1 on
        amount and date and would resolve cleanly at tier 1 in isolation; the
        cascade must see that row 1 is already spoken for.  Without this the
        run asserts two contradictory routes for one payment while satisfying
        uniqueness inside each tier.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, day=5,
                        references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, day=5,
                        references=uetr_reference()),
            observation(3, account=300, direction=CREDIT, day=5),
        ]
        by_pair = {
            (link.left_id.int, link.right_id.int): link
            for link in link_transactions(rows).links
        }
        self.assertIs(by_pair[(1, 2)].outcome, LinkOutcome.resolved)
        self.assertIs(by_pair[(1, 3)].outcome, LinkOutcome.ambiguous)
        self.assertFalse(by_pair[(1, 3)].is_asserted)

    def test_tier_zero_conflicts_survive_into_the_combined_result(self):
        """A finding is not discarded because two weaker tiers ran afterwards."""
        rows = [
            observation(1, account=100, direction=DEBIT, references=uetr_reference()),
            observation(2, account=200, direction=DEBIT, references=uetr_reference()),
        ]
        result = link_transactions(rows)
        self.assertEqual(len(result.conflicts), 1)

    def test_a_conflicting_pair_is_not_rescued_by_a_weaker_tier(self):
        """No explicit suppression is needed, and this is why.

        A conflict arises precisely where :func:`classify_relation` returns no
        relation, and every tier calls that same function first -- so the pair
        cannot reach a candidate list anywhere.  Stated as a test because the
        alternative reading is that tier 0 forgot to exclude them, and a future
        edit acting on that reading would be caught here.
        """
        rows = [
            observation(1, account=100, direction=DEBIT, day=5,
                        counterparty="ACME HOLDINGS LIMITED",
                        holder="ACME HOLDINGS LIMITED",
                        references=uetr_reference()),
            observation(2, account=200, direction=DEBIT, day=5,
                        counterparty="ACME HOLDINGS LTD",
                        holder="ACME HOLDINGS LTD",
                        references=uetr_reference()),
        ]
        result = link_transactions(rows)
        self.assertEqual(result.links, ())
        self.assertEqual(len(result.conflicts), 1)

    def test_the_probabilistic_tier_can_be_turned_off(self):
        rows = [
            observation(1, account=100, direction=DEBIT, day=1,
                        counterparty="ACME HOLDINGS LIMITED", holder="BLUE RIVER LLC"),
            observation(2, account=200, direction=CREDIT, day=12,
                        counterparty="BLUE RIVER L.L.C.", holder="ACME HOLDINGS LTD"),
        ]
        self.assertEqual(len(link_transactions(rows).links), 1)
        self.assertEqual(
            link_transactions(rows, include_probabilistic=False).links, ()
        )

    def test_asserted_and_proposals_partition_the_links(self):
        rows = [
            observation(1, account=100, direction=DEBIT, minor=10_000,
                        references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, minor=10_000,
                        references=uetr_reference()),
            observation(3, account=100, direction=DEBIT, minor=30_000, day=1,
                        counterparty="ACME HOLDINGS LIMITED", holder="BLUE RIVER LLC"),
            observation(4, account=200, direction=CREDIT, minor=30_000, day=12,
                        counterparty="BLUE RIVER L.L.C.", holder="ACME HOLDINGS LTD"),
        ]
        result = link_transactions(rows)
        self.assertEqual(
            len(result.asserted) + len(result.proposals), len(result.links)
        )
        self.assertEqual(set(result.asserted) & set(result.proposals), set())


class DeterminismTests(unittest.TestCase):
    """A join set that reshuffled between runs could not be cited."""

    @staticmethod
    def _corpus() -> list[LinkObservation]:
        return [
            observation(1, account=100, direction=DEBIT, minor=10_000,
                        references=uetr_reference()),
            observation(2, account=200, direction=CREDIT, minor=10_000,
                        references=uetr_reference()),
            observation(3, account=100, direction=DEBIT, minor=20_000, day=5),
            observation(4, account=200, direction=CREDIT, minor=20_000, day=6),
            observation(5, account=300, direction=CREDIT, minor=20_000, day=6),
            observation(6, account=100, direction=DEBIT, minor=30_000, day=1,
                        counterparty="ACME HOLDINGS LIMITED", holder="BLUE RIVER LLC"),
            observation(7, account=200, direction=CREDIT, minor=30_000, day=12,
                        counterparty="BLUE RIVER L.L.C.", holder="ACME HOLDINGS LTD"),
        ]

    def test_the_result_does_not_depend_on_input_order(self):
        """Shuffled twenty ways; the links and their outcomes must not move."""
        expected = link_transactions(self._corpus()).links
        rng = random.Random(20240301)
        for attempt in range(20):
            rows = self._corpus()
            rng.shuffle(rows)
            with self.subTest(attempt=attempt):
                self.assertEqual(link_transactions(rows).links, expected)

    def test_conflicts_are_ordered_too(self):
        rows = [
            observation(n, account=100 * n, direction=DEBIT, references=uetr_reference())
            for n in (1, 2, 3)
        ]
        expected = link_exact_identifiers(rows).conflicts
        for permutation in itertools.permutations(rows):
            with self.subTest(order=[o.transaction_id.int for o in permutation]):
                self.assertEqual(
                    link_exact_identifiers(list(permutation)).conflicts, expected
                )

    def test_an_empty_corpus_produces_an_empty_result(self):
        result = link_transactions([])
        self.assertEqual(result.links, ())
        self.assertEqual(result.conflicts, ())

    def test_a_single_row_produces_nothing(self):
        result = link_transactions([observation(1, references=uetr_reference())])
        self.assertEqual(result.links, ())
        self.assertEqual(result.conflicts, ())


class NothingCollapsesTests(unittest.TestCase):
    """A reconciled transaction retains all its sources.

    The deliberate contrast with ``duplicates``, which does supersede.  Stated
    as tests because the temptation to return one row per payment is
    permanent, and yielding to it would destroy the thing an exhibit rests on:
    that each source document still says what it said.
    """

    def test_linking_returns_links_and_never_merged_rows(self):
        rows = [
            observation(1, document=901, references=uetr_reference()),
            observation(2, document=902, references=uetr_reference()),
        ]
        result = link_transactions(rows)
        self.assertEqual(len(result.links), 1)
        self.assertEqual(
            {row.transaction_id for row in rows},
            {result.links[0].left_id, result.links[0].right_id},
        )

    def test_both_source_documents_remain_distinguishable(self):
        """The link names two transactions; the rows keep their own documents.

        Nothing in the result offers a "winning" document, because there isn't
        one to offer.
        """
        rows = [
            observation(1, document=901, references=uetr_reference()),
            observation(2, document=902, references=uetr_reference()),
        ]
        link_transactions(rows)
        self.assertNotEqual(rows[0].source_document_id, rows[1].source_document_id)

    def test_an_input_row_is_not_mutated_by_linking(self):
        rows = [
            observation(1, document=901, references=uetr_reference()),
            observation(2, document=902, references=uetr_reference()),
        ]
        before = [dataclasses.astuple(row) for row in rows]
        link_transactions(rows)
        self.assertEqual([dataclasses.astuple(row) for row in rows], before)


class CarryForwardTests(unittest.TestCase):
    """What one tier is allowed to tell the next, and on whose authority.

    Two things travel down the cascade -- settled counterparty pairings, and
    settled same-side pairs offered as equalities -- and each is filtered twice
    on the way: by relation and by outcome.  All four filters are load-bearing
    and none of them is visible in an end-to-end result that merely joins.

    The two helpers are exercised directly as well as through the cascade.
    That is deliberate.  Tier 0 records every link it makes as resolved, so
    today no caller can hand either helper an *ambiguous* link, and the two
    outcome filters would answer identically if they were deleted.  They are
    contracts rather than dead code: the moment a tier that can report
    ambiguity is asked to vouch for something -- which is what would happen if
    tier 1's output were ever passed where tier 0's is passed now -- the filter
    is the only thing standing between an unsettled pair and an assertion made
    on its authority.  A test that can only reach a guard through a caller
    tests the caller.
    """

    @staticmethod
    def _link(left, right, relation, outcome):
        return Link(
            left_id=ident(left),
            right_id=ident(right),
            relation=relation,
            tier=JoinTier.exact_identifier,
            outcome=outcome,
            components=(MATCH_AMOUNT,),
            date_agreement=DateAgreement(
                field="value_date",
                left=date(2024, 3, 5),
                right=date(2024, 3, 5),
                gap_days=0,
                like_for_like=True,
            ),
        )

    def _mixed(self):
        """One link of each relation crossed with each outcome."""
        return [
            self._link(1, 2, LinkRelation.same_side, LinkOutcome.resolved),
            self._link(3, 4, LinkRelation.same_side, LinkOutcome.ambiguous),
            self._link(5, 6, LinkRelation.counterparty, LinkOutcome.resolved),
            self._link(7, 8, LinkRelation.counterparty, LinkOutcome.ambiguous),
        ]

    def test_only_resolved_same_side_pairs_become_equalities(self):
        """An equality is a claim that two rows are one movement.

        A counterparty pair is the opposite claim and must never be offered as
        one; an ambiguous pair settled nothing, so it can vouch for nothing.
        Asserted as an exact set, because a filter that lets one extra pair
        through is the whole failure.
        """
        equalities = linkage._same_side_equalities(self._mixed())
        self.assertEqual(
            {(left.int, right.int) for left, right in equalities}, {(1, 2)}
        )

    def test_only_resolved_counterparty_pairs_become_partners(self):
        """A partner claim says a payment already has its other end.

        A same-side pair is two readings of *one* end and says nothing about
        the other, so admitting it here would spend a row's one pairing on its
        own duplicate.  An ambiguous pair, again, settled nothing.
        """
        partners = linkage._counterparty_partners(self._mixed())
        self.assertEqual(
            {node.int: sorted(v.int for v in values) for node, values in partners.items()},
            {5: [6], 6: [5]},
        )

    def test_a_same_side_group_does_not_spend_its_members_as_counterparties(self):
        """Rows 1 and 2 are one movement, so neither is the other's far end.

        Rows 1 and 2 share a UETR and differ in amount, which tier 0 permits
        and which puts them in different blocking buckets, so row 2 is not a
        tier-1 candidate for row 3 and cannot compete for it honestly.  If the
        same-side pair were carried down as a partner claim anyway, row 1 would
        arrive at tier 1 already spoken for and the genuine pairing with row 3
        would be reported ambiguous -- an ambiguity manufactured entirely by
        the carry-forward.
        """
        rows = [
            observation(1, account=100, document=901, minor=50_000,
                        direction=DEBIT, references=uetr_reference()),
            observation(2, account=100, document=902, minor=99_999,
                        direction=DEBIT, references=uetr_reference()),
            observation(3, account=200, document=903, minor=50_000,
                        direction=CREDIT, day=6),
        ]
        by_pair = {
            (link.left_id.int, link.right_id.int): link
            for link in link_transactions(
                rows, tolerance_days=3, include_probabilistic=False
            ).links
        }
        self.assertEqual(set(by_pair), {(1, 2), (1, 3)})
        self.assertIs(by_pair[(1, 2)].relation, LinkRelation.same_side)
        self.assertIs(by_pair[(1, 3)].relation, LinkRelation.counterparty)
        self.assertIs(by_pair[(1, 3)].outcome, LinkOutcome.resolved)

    def test_an_ambiguous_pairing_does_not_spend_either_of_its_ends(self):
        """Row 11 answers to two credits at tier 1, which settles nothing.

        Both pairings are recorded ambiguous and both are claimed, so neither
        comes back at tier 2.  What must also not happen is row 11 arriving at
        tier 2 holding two partner claims it never earned: row 14 agrees with
        it on the crossed names and falls inside the wider window, and that
        pairing is unique on both sides.  If ambiguity counted as a claim it
        would read as a third competitor and the one pair the cascade could
        settle would be reported ambiguous instead.
        """
        rows = [
            observation(11, account=100, document=910, minor=44_400, day=5,
                        direction=DEBIT, counterparty="ACME HOLDINGS LIMITED",
                        holder="BLUE RIVER LLC"),
            observation(12, account=200, document=911, minor=44_400, day=5,
                        direction=CREDIT),
            observation(13, account=300, document=912, minor=44_400, day=5,
                        direction=CREDIT),
            observation(14, account=400, document=913, minor=44_400, day=12,
                        direction=CREDIT, counterparty="BLUE RIVER L.L.C.",
                        holder="ACME HOLDINGS LTD"),
        ]
        by_pair = {
            (link.left_id.int, link.right_id.int): link
            for link in link_transactions(rows, tolerance_days=3).links
        }
        self.assertEqual(set(by_pair), {(11, 12), (11, 13), (11, 14)})
        for pair_ in ((11, 12), (11, 13)):
            self.assertIs(by_pair[pair_].tier, JoinTier.deterministic_composite)
            self.assertIs(by_pair[pair_].outcome, LinkOutcome.ambiguous)
        self.assertIs(by_pair[(11, 14)].tier, JoinTier.probabilistic)
        self.assertIs(by_pair[(11, 14)].outcome, LinkOutcome.resolved)


class ReferenceOrderTests(unittest.TestCase):
    """Two rows can share more than one identifier, and then order is a choice.

    Each shared reference produces its own link, and the links are otherwise
    identical -- same endpoints, same tier, same relation -- so the sort that
    orders the result cannot separate them and leaves them in the order they
    were generated.  That order is therefore decided by how tier 0 walks its
    reference groups, and walking a dictionary would hand it to whichever row
    happened to be read first.

    Nothing downstream *needs* one order over another.  It matters because an
    exhibit is a document with a fixed order of rows, and two runs over the
    same evidence that disagree about it are two documents.
    """

    @staticmethod
    def _cheque(number: str) -> ScopedReference:
        return ScopedReference(
            kind=REFERENCE_CHEQUE_NUMBER,
            scope=ReferenceScope.account,
            value=number,
            scope_key="acct-a",
        )

    def test_two_references_on_one_pair_come_back_in_join_key_order(self):
        """Carried in descending order, returned in ascending order."""
        refs = (self._cheque("zzz9"), self._cheque("aaa1"))
        rows = [
            observation(1, document=901, references=refs),
            observation(2, document=902, references=refs),
        ]
        result = link_exact_identifiers(rows)
        self.assertEqual(
            [link.reference.value for link in result.links], ["aaa1", "zzz9"]
        )

    def test_the_order_does_not_depend_on_which_row_was_read_first(self):
        refs = (self._cheque("zzz9"), self._cheque("aaa1"))
        rows = [
            observation(1, document=901, references=refs),
            observation(2, document=902, references=tuple(reversed(refs))),
        ]
        forward = link_exact_identifiers(rows)
        backward = link_exact_identifiers(list(reversed(rows)))
        self.assertEqual(
            [link.reference.value for link in forward.links], ["aaa1", "zzz9"]
        )
        self.assertEqual(forward.links, backward.links)

    def test_an_equality_vouches_for_a_pair_without_deciding_who_is_in_a_group(self):
        """The narrow reading of what a prior equality is for.

        Rows 1 and 2 share a UETR, which tier 0 accepts without looking at
        dates, so they are one movement.  Nine days separate them, and each
        has a near neighbour of its own: row 3 a day after row 1, row 4 a day
        after row 2.  Within a two-day tolerance that is two groups, and each
        is a clique on its own terms.

        If the tier-0 equality were fed to the component search rather than
        only to the clique test, it would join the two groups into one, and
        the merged group -- whose members are up to ten days apart -- would
        fail the clique test and report two sound pairings as ambiguous.  An
        equality may say that a pair inside a group is settled.  It may not
        say who is in the group, because the group is this tier's finding.
        """
        rows = [
            observation(1, document=901, day=1, references=uetr_reference()),
            observation(2, document=902, day=10, references=uetr_reference()),
            observation(3, document=903, day=2),
            observation(4, document=904, day=11),
        ]
        by_pair = {
            (link.left_id.int, link.right_id.int): link
            for link in link_transactions(
                rows, tolerance_days=2, include_probabilistic=False
            ).links
        }
        self.assertEqual(set(by_pair), {(1, 2), (1, 3), (2, 4)})
        for pair_ in ((1, 3), (2, 4)):
            with self.subTest(pair=pair_):
                self.assertIs(by_pair[pair_].tier, JoinTier.deterministic_composite)
                self.assertIs(by_pair[pair_].outcome, LinkOutcome.resolved)
