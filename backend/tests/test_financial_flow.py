"""Tests for :mod:`services.financial.flow`.

Four things these tests exist to hold, beyond the obvious one that the
arithmetic is right.

**That one payment is counted once.**  This is the defect the module was
written for and the reason it is a port of V1's model rather than a copy of it.
V1 read a table with one row per payment; a ledger assembled from bank
statements has one row per *statement line*, so a payment between two parties
whose statements are both in evidence appears twice, resolves to the same payer
and payee both times, lands in the same bucket both times, and doubles the
figure.  Silently, and worse the better the case is documented.
:class:`OnePaymentIsCountedOnce` asserts the fix on the smallest fact pattern
that shows it -- the same two rows, counted once and counted twice, differing in
nothing but ``collapse`` -- and then holds every condition that makes two rows a
pair, because each of them is load-bearing in a different direction.

**That collapsing cannot understate either.**  An overstatement and an
understatement are the same kind of error and the second is quieter.  Two
genuine payments of the same amount between the same parties must survive as
two, which is why the pairing is a matching and not a lookup; a January payment
and a June payment of the same round amount must not collapse, which is what
the settlement window is for; and two rows in the *same* account are a repeat
rather than a mirror and belong to ``duplicates.py``.
:class:`CollapsingCannotUnderstate` holds all three.

**That the chart cannot disagree with the cards.**  V1 drew the top twelve
counterparties and totalled every in-scope row above them, including rows whose
external side was never named, so the bars and the cards disagreed by an amount
nothing on the screen reported.  Here the remainder past the limit and the
unattributed residue each get a bar, the sum is asserted in
:meth:`~services.financial.flow.MoneyFlow.divergent_chart`, and the counterparty
breakdown is asserted against the cards in ``__post_init__``.
:class:`TheChartCloses` and :class:`InvariantsAreEnforced` hold both, including
the case where the invariant is deliberately broken and must raise.

**That what was excluded is distinguishable from what was never there.**
Payments are placed against the perspective *before* the proof-class filter, so
a p3 payment between a selected entity and an outsider reports as in scope and
not counted rather than merely absent; a payment with neither side identified
bypasses the class filter entirely, because reporting it under a proof-class
heading would name the wrong reason.  :class:`ScopeAndClassAreSeparate` holds
the ordering and :class:`NotesDisclose` holds the disclosures, which are not
decoration: this module computes over whatever is held and says how far that
goes, where :mod:`services.financial.correlation` refuses to speak at all.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import random
import unittest
import uuid
from datetime import date
from decimal import Decimal

from postgres.models.enums import ProofClass, TransactionDirection
from services.financial import flow
from services.financial.correlation import LedgerEntry
from services.financial.flow import (
    DEFAULT_CHART_LIMIT,
    DEFAULT_SETTLEMENT_DAYS,
    NOTE_MIRRORS_AMBIGUOUS,
    NOTE_MIRRORS_COLLAPSED,
    NOTE_MIRRORS_NOT_COLLAPSED,
    NOTE_MIXED_COMPOSITION,
    NOTE_NAMES_COLLIDE,
    NOTE_NOT_BILATERAL,
    NOTE_SETTLEMENT_LAG,
    NOTE_SET_ASIDE_ON_CLASS,
    NOTE_UNATTRIBUTED_INFLOW,
    NOTE_UNATTRIBUTED_OUTFLOW,
    NOTE_UNPLACEABLE,
    NOTE_UNRECONCILED,
    ChartBar,
    ClassComposition,
    CounterpartyFlow,
    DivergentChart,
    DuplicateRowError,
    EntityOption,
    Figure,
    FlowCurrencyError,
    FlowError,
    FlowInvariantError,
    FlowRow,
    MirrorPair,
    MoneyFlow,
    Party,
    PartyAttributionError,
    Payment,
    Perspective,
    PerspectiveError,
    Placement,
    SetAsideReason,
    analyse,
    attribute,
    collapse_mirrors,
    entity_options,
    place,
)
from services.financial.money import Money
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def usd(major: str) -> Money:
    """A USD amount from a major-unit string.  Never a float."""
    return Money.from_decimal(Decimal(major), "USD")


def eur(major: str) -> Money:
    return Money.from_decimal(Decimal(major), "EUR")


#: Deterministic ids.  Readable in a failure message, and stable across runs so
#: that a tie broken by transaction id breaks the same way every time.
def ident(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


ACCOUNT_A = ident(9001)
ACCOUNT_B = ident(9002)
ACCOUNT_C = ident(9003)

ACME = Party(key="acme", name="Acme LLC")
BETA = Party(key="beta", name="Beta Inc")
GAMMA = Party(key="gamma", name="Gamma Co")
DELTA = Party(key="delta", name="Delta Ltd")


_counter = itertools.count(1)


def a_row(
    *,
    holder=ACME,
    counterparty=BETA,
    amount: str = "100.00",
    day: int = 1,
    direction: TransactionDirection = TransactionDirection.debit,
    proof_class: ProofClass = ProofClass.p2,
    account=ACCOUNT_A,
    transaction_id=None,
    reconciled: bool = True,
    description=None,
    currency: str = "USD",
) -> FlowRow:
    """One flow row, with everything a test does not care about defaulted."""
    money = Money.from_decimal(Decimal(amount), currency)
    return FlowRow(
        transaction_id=transaction_id or ident(next(_counter)),
        account_id=account,
        ordering_date=date(2024, 3, day),
        amount=money,
        direction=direction,
        proof_class=proof_class,
        holder=holder,
        counterparty=counterparty,
        reconciled=reconciled,
        description=description,
    )


def mirrored(
    *,
    amount: str = "100.00",
    debit_day: int = 1,
    credit_day: int = 1,
    payer=ACME,
    payee=BETA,
    debit_account=ACCOUNT_A,
    credit_account=ACCOUNT_B,
    debit_class: ProofClass = ProofClass.p2,
    credit_class: ProofClass = ProofClass.p2,
    debit_reconciled: bool = True,
    credit_reconciled: bool = True,
    debit_description=None,
    credit_description=None,
) -> tuple[FlowRow, FlowRow]:
    """The two statement lines that record one payment from ``payer`` to ``payee``.

    The debit sits in the payer's account and the credit in the payee's, which
    is the shape the collapse exists to recognise.
    """
    debit = a_row(
        holder=payer,
        counterparty=payee,
        amount=amount,
        day=debit_day,
        direction=TransactionDirection.debit,
        proof_class=debit_class,
        account=debit_account,
        reconciled=debit_reconciled,
        description=debit_description,
    )
    credit = a_row(
        holder=payee,
        counterparty=payer,
        amount=amount,
        day=credit_day,
        direction=TransactionDirection.credit,
        proof_class=credit_class,
        account=credit_account,
        reconciled=credit_reconciled,
        description=credit_description,
    )
    return debit, credit


def figure(amount: str = "0.00", count: int = 0, **classes) -> Figure:
    """A figure built directly, for testing the types that consume one."""
    counts = {ProofClass[k]: v[0] for k, v in classes.items()}
    amounts = {ProofClass[k]: usd(v[1]) for k, v in classes.items()}
    return Figure(
        amount=usd(amount),
        count=count,
        composition=ClassComposition(counts=counts, amounts=amounts),
    )


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


class PartyTests(unittest.TestCase):
    """A key is identity; a name is a label.  Conflating them is the V1 bug."""

    def test_key_is_required(self):
        with self.assertRaises(PartyAttributionError):
            Party(key="")

    def test_whitespace_is_not_a_key(self):
        with self.assertRaises(PartyAttributionError):
            Party(key="   ")

    def test_refusal_says_why_a_name_will_not_do(self):
        with self.assertRaises(PartyAttributionError) as caught:
            Party(key="")
        self.assertIn("merges everyone who shares it", str(caught.exception))

    def test_label_prefers_the_name(self):
        self.assertEqual(Party(key="acme", name="Acme LLC").label, "Acme LLC")

    def test_label_falls_back_to_the_key(self):
        self.assertEqual(Party(key="acme").label, "acme")

    def test_an_empty_name_falls_back_rather_than_showing_blank(self):
        self.assertEqual(Party(key="acme", name="").label, "acme")

    def test_equality_is_on_both_fields_but_grouping_is_on_the_key(self):
        # The dataclass compares both, which is right for a value type.  What
        # matters is that nothing in the module groups on the whole object.
        self.assertNotEqual(Party(key="a", name="X"), Party(key="a", name="Y"))
        self.assertEqual(Party(key="a", name="X").key, Party(key="a", name="Y").key)

    def test_unnamed_party_label_for_none(self):
        self.assertEqual(flow._party_label(None), "an unnamed party")

    def test_party_is_hashable(self):
        self.assertEqual(len({ACME, ACME, BETA}), 2)


class ProofClassStrengthTests(unittest.TestCase):
    """`_stronger` has one definition in the module and it is this one."""

    def test_p0_beats_everything(self):
        for other in (ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3):
            self.assertIs(flow._stronger(ProofClass.p0, other), ProofClass.p0)
            self.assertIs(flow._stronger(other, ProofClass.p0), ProofClass.p0)

    def test_ordering_is_p0_through_p4(self):
        self.assertEqual(
            flow._CLASS_ORDER,
            (
                ProofClass.p0,
                ProofClass.p1,
                ProofClass.p2,
                ProofClass.p3,
                ProofClass.p4,
            ),
        )

    def test_rank_agrees_with_order(self):
        for index, cls in enumerate(flow._CLASS_ORDER):
            self.assertEqual(flow._CLASS_RANK[cls], index)

    def test_equal_classes_return_that_class(self):
        self.assertIs(flow._stronger(ProofClass.p2, ProofClass.p2), ProofClass.p2)

    def test_each_adjacent_pair(self):
        for stronger, weaker in zip(flow._CLASS_ORDER, flow._CLASS_ORDER[1:]):
            self.assertIs(flow._stronger(stronger, weaker), stronger)
            self.assertIs(flow._stronger(weaker, stronger), stronger)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


class FlowRowTests(unittest.TestCase):
    """Direction plus holder is the ledger's shape; payer/payee is the model's."""

    def test_a_debit_pays_from_the_holder(self):
        row = a_row(direction=TransactionDirection.debit)
        self.assertEqual(row.payer, ACME)
        self.assertEqual(row.payee, BETA)

    def test_a_credit_pays_to_the_holder(self):
        row = a_row(direction=TransactionDirection.credit)
        self.assertEqual(row.payer, BETA)
        self.assertEqual(row.payee, ACME)

    def test_a_debit_with_no_counterparty_has_no_payee(self):
        row = a_row(direction=TransactionDirection.debit, counterparty=None)
        self.assertEqual(row.payer, ACME)
        self.assertIsNone(row.payee)

    def test_a_credit_with_no_counterparty_has_no_payer(self):
        row = a_row(direction=TransactionDirection.credit, counterparty=None)
        self.assertIsNone(row.payer)
        self.assertEqual(row.payee, ACME)

    def test_a_debit_with_no_holder_has_no_payer(self):
        row = a_row(direction=TransactionDirection.debit, holder=None)
        self.assertIsNone(row.payer)
        self.assertEqual(row.payee, BETA)

    def test_p4_cannot_reach_a_flow_figure(self):
        with self.assertRaises(PartyAttributionError) as caught:
            a_row(proof_class=ProofClass.p4)
        self.assertIn("is not a payment", str(caught.exception))

    def test_every_ledger_class_is_accepted(self):
        for cls in (ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3):
            self.assertEqual(a_row(proof_class=cls).proof_class, cls)

    def test_a_negative_amount_is_refused(self):
        with self.assertRaises(PartyAttributionError) as caught:
            a_row(amount="-100.00")
        self.assertIn("positive magnitude", str(caught.exception))

    def test_zero_is_allowed(self):
        self.assertEqual(a_row(amount="0.00").amount, usd("0.00"))

    def test_a_row_cannot_be_its_own_counterparty(self):
        with self.assertRaises(PartyAttributionError) as caught:
            a_row(holder=ACME, counterparty=Party(key="acme", name="ACME"))
        self.assertIn("money that never moved", str(caught.exception))

    def test_self_dealing_is_tested_on_the_key_not_the_name(self):
        # Same key, different label: still the same party.
        with self.assertRaises(PartyAttributionError):
            a_row(holder=Party(key="x", name="One"), counterparty=Party(key="x"))
        # Different key, same label: two parties, and not this module's business
        # to merge them.
        row = a_row(
            holder=Party(key="x", name="Same Name"),
            counterparty=Party(key="y", name="Same Name"),
        )
        self.assertIsNotNone(row.payee)

    def test_placeable_needs_only_one_side(self):
        self.assertTrue(a_row(holder=ACME, counterparty=None).is_placeable)
        self.assertTrue(a_row(holder=None, counterparty=BETA).is_placeable)
        self.assertFalse(a_row(holder=None, counterparty=None).is_placeable)

    def test_describe_names_both_sides_and_the_date(self):
        row = a_row(day=4)
        self.assertEqual(
            row.describe(), "100.00 USD from Acme LLC to Beta Inc on 2024-03-04"
        )

    def test_describe_says_unnamed_rather_than_inventing_a_party(self):
        row = a_row(holder=None, counterparty=BETA)
        self.assertIn("from an unnamed party", row.describe())


class AttributeTests(unittest.TestCase):
    """The entity-resolution boundary, made explicit and required."""

    def entry(self, **kwargs) -> LedgerEntry:
        defaults = dict(
            transaction_id=ident(4001),
            account_id=ACCOUNT_A,
            ordering_date=date(2024, 3, 2),
            amount=usd("250.00"),
            direction=TransactionDirection.debit,
            proof_class=ProofClass.p1,
            holder="ACME LLC",
            counterparty="BETA INC",
            description="wire out",
            reconciled=False,
        )
        defaults.update(kwargs)
        return LedgerEntry(**defaults)

    def test_every_ledger_field_is_carried_across(self):
        row = attribute(self.entry(), holder=ACME, counterparty=BETA)
        self.assertEqual(row.transaction_id, ident(4001))
        self.assertEqual(row.account_id, ACCOUNT_A)
        self.assertEqual(row.ordering_date, date(2024, 3, 2))
        self.assertEqual(row.amount, usd("250.00"))
        self.assertIs(row.direction, TransactionDirection.debit)
        self.assertIs(row.proof_class, ProofClass.p1)
        self.assertEqual(row.description, "wire out")
        self.assertFalse(row.reconciled)

    def test_identities_come_from_the_caller_not_the_strings(self):
        # The entry's own holder is the string "ACME LLC"; the row's identity is
        # whatever the resolver said, and the two are deliberately unrelated.
        row = attribute(self.entry(), holder=Party(key="k-77"), counterparty=BETA)
        self.assertEqual(row.holder.key, "k-77")

    def test_an_unresolved_side_stays_unresolved(self):
        row = attribute(self.entry(), holder=ACME)
        self.assertIsNone(row.counterparty)
        self.assertIsNone(row.payee)

    def test_both_sides_may_be_unresolved(self):
        row = attribute(self.entry())
        self.assertFalse(row.is_placeable)

    def test_it_refuses_anything_that_is_not_a_ledger_entry(self):
        with self.assertRaises(PartyAttributionError):
            attribute(a_row(), holder=ACME)

    def test_it_refuses_a_bare_tuple(self):
        with self.assertRaises(PartyAttributionError):
            attribute(("acme", "beta"))


# ---------------------------------------------------------------------------
# The point of view
# ---------------------------------------------------------------------------


class PerspectiveTests(unittest.TestCase):
    def test_an_empty_perspective_is_refused(self):
        with self.assertRaises(PerspectiveError) as caught:
            Perspective(frozenset())
        self.assertIn("nobody asked", str(caught.exception))

    def test_of_with_no_arguments_is_refused(self):
        with self.assertRaises(PerspectiveError):
            Perspective.of()

    def test_a_blank_key_is_refused(self):
        with self.assertRaises(PerspectiveError):
            Perspective.of("acme", "")

    def test_a_whitespace_key_is_refused(self):
        with self.assertRaises(PerspectiveError):
            Perspective.of("acme", "  ")

    def test_of_builds_the_set(self):
        self.assertEqual(Perspective.of("a", "b").keys, frozenset({"a", "b"}))

    def test_holds_tests_the_key(self):
        p = Perspective.of("acme")
        self.assertTrue(p.holds(ACME))
        self.assertTrue(p.holds(Party(key="acme", name="Wholly Different Label")))
        self.assertFalse(p.holds(BETA))

    def test_holds_is_false_for_an_unresolved_side(self):
        self.assertFalse(Perspective.of("acme").holds(None))

    def test_length_is_the_number_of_entities(self):
        self.assertEqual(len(Perspective.of("a", "b", "c")), 3)

    def test_duplicates_collapse_because_it_is_a_set(self):
        self.assertEqual(len(Perspective.of("a", "a")), 1)


class PlacementTests(unittest.TestCase):
    """The order of the tests in `place` is the model, not an implementation."""

    def payment(self, payer, payee) -> Payment:
        return Payment(
            payer=payer,
            payee=payee,
            amount=usd("10.00"),
            ordering_date=date(2024, 3, 1),
            proof_class=ProofClass.p2,
            rows=(ident(1),),
            accounts=frozenset({ACCOUNT_A}),
            reconciled=True,
        )

    def test_both_sides_selected_is_internal(self):
        p = Perspective.of("acme", "beta")
        self.assertIs(place(self.payment(ACME, BETA), p), Placement.internal)

    def test_internal_is_tested_first(self):
        # If outflow were tested first this would come back outflow, and the
        # money would be counted as leaving a group it never left.
        p = Perspective.of("acme", "beta")
        self.assertIsNot(place(self.payment(ACME, BETA), p), Placement.outflow)

    def test_selected_payer_is_outflow(self):
        p = Perspective.of("acme")
        self.assertIs(place(self.payment(ACME, GAMMA), p), Placement.outflow)

    def test_selected_payee_is_inflow(self):
        p = Perspective.of("acme")
        self.assertIs(place(self.payment(GAMMA, ACME), p), Placement.inflow)

    def test_neither_side_selected_is_out_of_scope(self):
        p = Perspective.of("acme")
        self.assertIs(place(self.payment(GAMMA, DELTA), p), Placement.out_of_scope)

    def test_neither_side_resolved_is_unplaceable(self):
        p = Perspective.of("acme")
        self.assertIs(place(self.payment(None, None), p), Placement.unplaceable)

    def test_one_side_unresolved_is_placed_on_the_side_that_is_known(self):
        p = Perspective.of("acme")
        self.assertIs(place(self.payment(ACME, None), p), Placement.outflow)
        self.assertIs(place(self.payment(None, ACME), p), Placement.inflow)

    def test_an_unresolved_side_against_an_outsider_is_out_of_scope(self):
        # Known to be not-selected on one side, unknown on the other: this is
        # not unplaceable, because one side did resolve.
        p = Perspective.of("acme")
        self.assertIs(place(self.payment(GAMMA, None), p), Placement.out_of_scope)


# ---------------------------------------------------------------------------
# Figures that state what they are made of
# ---------------------------------------------------------------------------


class ClassCompositionTests(unittest.TestCase):
    def test_classes_come_out_strongest_first(self):
        c = ClassComposition(
            counts={ProofClass.p3: 1, ProofClass.p0: 2, ProofClass.p2: 1},
            amounts={
                ProofClass.p3: usd("1.00"),
                ProofClass.p0: usd("2.00"),
                ProofClass.p2: usd("3.00"),
            },
        )
        self.assertEqual(c.classes, (ProofClass.p0, ProofClass.p2, ProofClass.p3))

    def test_a_zero_count_is_not_present(self):
        c = ClassComposition(counts={ProofClass.p0: 0}, amounts={})
        self.assertEqual(c.classes, ())

    def test_weakest_is_what_qualifies_the_figure(self):
        c = ClassComposition(
            counts={ProofClass.p0: 1, ProofClass.p3: 1},
            amounts={ProofClass.p0: usd("1.00"), ProofClass.p3: usd("1.00")},
        )
        self.assertIs(c.weakest, ProofClass.p3)

    def test_weakest_of_nothing_is_none(self):
        self.assertIsNone(ClassComposition(counts={}, amounts={}).weakest)

    def test_uniform_when_one_class(self):
        c = ClassComposition(counts={ProofClass.p1: 4}, amounts={ProofClass.p1: usd("4.00")})
        self.assertTrue(c.is_uniform)

    def test_uniform_when_empty(self):
        self.assertTrue(ClassComposition(counts={}, amounts={}).is_uniform)

    def test_not_uniform_when_two_classes(self):
        c = ClassComposition(
            counts={ProofClass.p1: 1, ProofClass.p2: 1},
            amounts={ProofClass.p1: usd("1.00"), ProofClass.p2: usd("1.00")},
        )
        self.assertFalse(c.is_uniform)

    def test_describe_is_singular_for_one_row(self):
        c = ClassComposition(counts={ProofClass.p2: 1}, amounts={ProofClass.p2: usd("5.00")})
        self.assertEqual(c.describe(), "p2 1 row 5.00 USD")

    def test_describe_is_plural_for_two(self):
        c = ClassComposition(counts={ProofClass.p2: 2}, amounts={ProofClass.p2: usd("5.00")})
        self.assertEqual(c.describe(), "p2 2 rows 5.00 USD")

    def test_describe_joins_classes_strongest_first(self):
        c = ClassComposition(
            counts={ProofClass.p2: 1, ProofClass.p0: 1},
            amounts={ProofClass.p2: usd("2.00"), ProofClass.p0: usd("1.00")},
        )
        self.assertEqual(c.describe(), "p0 1 row 1.00 USD; p2 1 row 2.00 USD")

    def test_describe_of_nothing_says_so(self):
        self.assertEqual(ClassComposition(counts={}, amounts={}).describe(), "no rows")


class FigureTests(unittest.TestCase):
    def test_zero_is_about_the_count_not_the_amount(self):
        # A figure can total zero over real rows -- a payment of nothing is
        # still a payment -- and that is not the same as having no rows.
        self.assertTrue(figure("0.00", 0).is_zero)
        self.assertFalse(figure("0.00", 1, p2=(1, "0.00")).is_zero)

    def test_describe_is_singular_for_one(self):
        self.assertEqual(figure("5.00", 1, p2=(1, "5.00")).describe(), "5.00 USD over 1 payment")

    def test_describe_is_plural_for_none(self):
        self.assertEqual(figure("0.00", 0).describe(), "0.00 USD over 0 payments")

    def test_describe_is_plural_for_two(self):
        self.assertEqual(figure("9.00", 2, p2=(2, "9.00")).describe(), "9.00 USD over 2 payments")


class AccumulatorTests(unittest.TestCase):
    def test_it_starts_at_zero_in_the_stated_currency(self):
        acc = flow._Accumulator("EUR")
        frozen = acc.freeze()
        self.assertEqual(frozen.amount, eur("0.00"))
        self.assertEqual(frozen.count, 0)

    def test_it_sums_amounts_and_counts_separately(self):
        acc = flow._Accumulator("USD")
        acc.add(usd("10.00"), ProofClass.p1)
        acc.add(usd("5.00"), ProofClass.p1)
        frozen = acc.freeze()
        self.assertEqual(frozen.amount, usd("15.00"))
        self.assertEqual(frozen.count, 2)
        self.assertEqual(frozen.composition.counts, {ProofClass.p1: 2})
        self.assertEqual(frozen.composition.amounts, {ProofClass.p1: usd("15.00")})

    def test_it_keeps_classes_apart(self):
        acc = flow._Accumulator("USD")
        acc.add(usd("10.00"), ProofClass.p0)
        acc.add(usd("5.00"), ProofClass.p3)
        frozen = acc.freeze()
        self.assertEqual(frozen.amount, usd("15.00"))
        self.assertEqual(
            frozen.composition.amounts,
            {ProofClass.p0: usd("10.00"), ProofClass.p3: usd("5.00")},
        )

    def test_freezing_twice_gives_equal_figures(self):
        acc = flow._Accumulator("USD")
        acc.add(usd("1.00"), ProofClass.p2)
        self.assertEqual(acc.freeze(), acc.freeze())


# ---------------------------------------------------------------------------
# The collapse
# ---------------------------------------------------------------------------


class PaymentTests(unittest.TestCase):
    def make(self, rows) -> Payment:
        return Payment(
            payer=ACME,
            payee=BETA,
            amount=usd("100.00"),
            ordering_date=date(2024, 3, 1),
            proof_class=ProofClass.p2,
            rows=rows,
            accounts=frozenset({ACCOUNT_A}),
            reconciled=True,
        )

    def test_one_row_is_not_bilateral(self):
        self.assertFalse(self.make((ident(1),)).bilateral)

    def test_two_rows_are_bilateral(self):
        self.assertTrue(self.make((ident(1), ident(2))).bilateral)

    def test_describe_says_when_both_sides_are_in_evidence(self):
        self.assertIn("(both sides in evidence)", self.make((ident(1), ident(2))).describe())

    def test_describe_is_silent_when_only_one_side_is(self):
        self.assertNotIn("both sides", self.make((ident(1),)).describe())


class OnePaymentIsCountedOnce(unittest.TestCase):
    """The defect this module exists to prevent, on the smallest fact pattern."""

    def test_two_mirrored_rows_collapse_to_one_payment(self):
        payments, pairs = collapse_mirrors(mirrored())
        self.assertEqual(len(payments), 1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(payments[0].amount, usd("100.00"))

    def test_the_same_rows_uncollapsed_are_two(self):
        payments = flow._payments_only(mirrored())
        self.assertEqual(len(payments), 2)

    def test_the_figure_is_half_what_a_row_count_gives(self):
        rows = mirrored(amount="100.00")
        p = Perspective.of("acme")
        collapsed = analyse(rows, p, currency="USD")
        naive = analyse(rows, p, currency="USD", collapse=False)
        self.assertEqual(collapsed.outflow.amount, usd("100.00"))
        self.assertEqual(naive.outflow.amount, usd("200.00"))

    def test_the_error_grows_with_the_collection(self):
        # Three payments, all held on both sides.  A row-counting view reports
        # six hundred where three hundred moved: the better the documents, the
        # larger the error, which is the wrong direction for it to run.
        rows = []
        for day in (1, 2, 3):
            rows.extend(mirrored(amount="100.00", debit_day=day, credit_day=day))
        p = Perspective.of("acme")
        self.assertEqual(analyse(rows, p, currency="USD").outflow.amount, usd("300.00"))
        self.assertEqual(
            analyse(rows, p, currency="USD", collapse=False).outflow.amount,
            usd("600.00"),
        )

    def test_the_pair_records_both_ids_debit_first(self):
        debit, credit = mirrored()
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(payments[0].rows, (debit.transaction_id, credit.transaction_id))
        self.assertEqual(pairs[0].debit_id, debit.transaction_id)
        self.assertEqual(pairs[0].credit_id, credit.transaction_id)

    def test_the_payment_names_both_accounts(self):
        payments, _ = collapse_mirrors(mirrored())
        self.assertEqual(payments[0].accounts, frozenset({ACCOUNT_A, ACCOUNT_B}))

    def test_input_order_does_not_matter(self):
        debit, credit = mirrored()
        forward, _ = collapse_mirrors([debit, credit])
        backward, _ = collapse_mirrors([credit, debit])
        self.assertEqual(forward, backward)


class WhatMakesTwoRowsAPair(unittest.TestCase):
    """Each condition, denied one at a time.  Every one of them is load-bearing."""

    def test_different_payers_do_not_pair(self):
        debit = a_row(holder=GAMMA, counterparty=BETA, direction=TransactionDirection.debit)
        credit = a_row(
            holder=BETA, counterparty=ACME, direction=TransactionDirection.credit,
            account=ACCOUNT_B,
        )
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_different_amounts_do_not_pair(self):
        debit, credit = mirrored()
        other = a_row(
            holder=BETA, counterparty=ACME, amount="100.01",
            direction=TransactionDirection.credit, account=ACCOUNT_B,
        )
        payments, pairs = collapse_mirrors([debit, other])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_different_currencies_do_not_pair(self):
        debit = a_row(direction=TransactionDirection.debit, currency="USD")
        credit = a_row(
            holder=BETA, counterparty=ACME, direction=TransactionDirection.credit,
            account=ACCOUNT_B, currency="EUR",
        )
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_two_debits_do_not_pair(self):
        one = a_row(direction=TransactionDirection.debit)
        two = a_row(direction=TransactionDirection.debit, account=ACCOUNT_C)
        payments, pairs = collapse_mirrors([one, two])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_two_credits_do_not_pair(self):
        one = a_row(direction=TransactionDirection.credit)
        two = a_row(direction=TransactionDirection.credit, account=ACCOUNT_C)
        payments, pairs = collapse_mirrors([one, two])
        self.assertEqual(len(payments), 2)

    def test_the_same_account_is_a_repeat_and_not_a_mirror(self):
        # Belongs to duplicates.py, and collapsing it here would hide a defect
        # that has a different remedy.
        debit, credit = mirrored(debit_account=ACCOUNT_A, credit_account=ACCOUNT_A)
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_a_row_with_no_counterparty_cannot_be_paired(self):
        debit = a_row(direction=TransactionDirection.debit, counterparty=None)
        credit = a_row(
            holder=BETA, counterparty=ACME, direction=TransactionDirection.credit,
            account=ACCOUNT_B,
        )
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_a_row_with_no_holder_cannot_be_paired(self):
        debit = a_row(direction=TransactionDirection.debit, holder=None)
        credit = a_row(
            holder=BETA, counterparty=ACME, direction=TransactionDirection.credit,
            account=ACCOUNT_B,
        )
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(len(payments), 2)


class TheSettlementWindow(unittest.TestCase):
    """Wide enough for a cheque, narrow enough not to swallow a second payment."""

    def test_the_default_is_three_days(self):
        self.assertEqual(DEFAULT_SETTLEMENT_DAYS, 3)

    def test_same_day_pairs(self):
        _, pairs = collapse_mirrors(mirrored(debit_day=1, credit_day=1))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].settlement_days, 0)

    def test_exactly_at_the_window_pairs(self):
        _, pairs = collapse_mirrors(mirrored(debit_day=1, credit_day=4), settlement_days=3)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].settlement_days, 3)

    def test_one_day_past_the_window_does_not(self):
        payments, pairs = collapse_mirrors(
            mirrored(debit_day=1, credit_day=5), settlement_days=3
        )
        self.assertEqual(pairs, ())
        self.assertEqual(len(payments), 2)

    def test_a_january_and_a_june_payment_stay_two(self):
        # The understatement the window prevents, which is no better than the
        # overstatement the collapse prevents, only quieter.
        debit = a_row(direction=TransactionDirection.debit, day=1)
        credit = a_row(
            holder=BETA, counterparty=ACME, direction=TransactionDirection.credit,
            account=ACCOUNT_B, day=28,
        )
        payments, pairs = collapse_mirrors([debit, credit])
        self.assertEqual(len(payments), 2)
        self.assertEqual(pairs, ())

    def test_a_zero_window_still_pairs_same_day_rows(self):
        _, pairs = collapse_mirrors(mirrored(debit_day=2, credit_day=2), settlement_days=0)
        self.assertEqual(len(pairs), 1)

    def test_a_zero_window_refuses_a_one_day_lag(self):
        _, pairs = collapse_mirrors(mirrored(debit_day=2, credit_day=3), settlement_days=0)
        self.assertEqual(pairs, ())

    def test_a_credit_dated_before_its_debit_still_pairs(self):
        # Banks post out of order.  The window is absolute, not directional.
        _, pairs = collapse_mirrors(mirrored(debit_day=4, credit_day=2))
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].settlement_days, -2)

    def test_a_negative_window_is_refused(self):
        with self.assertRaises(FlowError) as caught:
            collapse_mirrors(mirrored(), settlement_days=-1)
        self.assertIn("must not be negative", str(caught.exception))

    def test_a_debit_far_past_the_window_is_refused_by_the_upper_bound(self):
        # The window has two edges and they are enforced by different code.  A
        # debit *before* the window is stepped over by the retire scan, which is
        # what `test_one_day_past_the_window_does_not` exercises.  A debit
        # *after* it is refused by the `break` in the eligibility loop, and
        # nothing above reaches that line: every other case here either pairs or
        # fails on the lower edge.  Dating the debit later than the credit is
        # the only way in.
        payments, pairs = collapse_mirrors(
            mirrored(debit_day=8, credit_day=2), settlement_days=3
        )
        self.assertEqual(pairs, ())
        self.assertEqual(len(payments), 2)


class AmbiguityIsFlaggedNotHidden(unittest.TestCase):
    """Which debit a credit is matched to can be a guess.  The count is not."""

    def two_and_two(self):
        # Two payments of the same amount between the same parties, days apart
        # but inside one window: either credit could belong to either debit.
        rows = []
        rows.extend(mirrored(amount="100.00", debit_day=1, credit_day=2))
        rows.extend(mirrored(amount="100.00", debit_day=2, credit_day=3))
        return rows

    def test_two_payments_survive_as_two(self):
        payments, pairs = collapse_mirrors(self.two_and_two())
        self.assertEqual(len(payments), 2)
        self.assertEqual(len(pairs), 2)

    def test_the_total_is_not_affected_by_the_guess(self):
        p = Perspective.of("acme")
        self.assertEqual(analyse(self.two_and_two(), p, currency="USD").outflow.amount,
                         usd("200.00"))

    def test_the_first_credit_is_ambiguous_and_the_second_is_not(self):
        # The first credit sees two eligible debits; once one is taken the
        # second credit has only one left, so only the first is a guess.
        _, pairs = collapse_mirrors(self.two_and_two())
        self.assertEqual([p.ambiguous for p in pairs], [True, False])

    def test_an_unambiguous_pair_is_not_flagged(self):
        _, pairs = collapse_mirrors(mirrored())
        self.assertFalse(pairs[0].ambiguous)

    def test_ambiguity_reaches_the_notes(self):
        result = analyse(self.two_and_two(), Perspective.of("acme"), currency="USD")
        self.assertTrue(any(NOTE_MIRRORS_AMBIGUOUS in n for n in result.notes))

    def test_a_clean_collapse_does_not_raise_the_ambiguity_note(self):
        result = analyse(mirrored(), Perspective.of("acme"), currency="USD")
        self.assertFalse(any(NOTE_MIRRORS_AMBIGUOUS in n for n in result.notes))

    def test_describe_says_which_rows_were_joined(self):
        _, pairs = collapse_mirrors(mirrored())
        text = pairs[0].describe()
        self.assertIn("100.00 USD", text)
        self.assertIn("Acme LLC", text)
        self.assertIn("Beta Inc", text)


class CollapsingCannotUnderstate(unittest.TestCase):
    """The quiet error.  Two payments must never be reported as one."""

    def test_two_genuine_same_day_payments_stay_two(self):
        rows = []
        rows.extend(mirrored(amount="100.00", debit_day=1, credit_day=1))
        rows.extend(mirrored(amount="100.00", debit_day=1, credit_day=1))
        payments, pairs = collapse_mirrors(rows)
        self.assertEqual(len(payments), 2)
        self.assertEqual(len(pairs), 2)

    def test_two_genuine_payments_total_twice_the_amount(self):
        rows = []
        rows.extend(mirrored(amount="100.00", debit_day=1, credit_day=1))
        rows.extend(mirrored(amount="100.00", debit_day=1, credit_day=1))
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("200.00"))
        self.assertEqual(result.outflow.count, 2)

    def test_a_debit_without_its_credit_is_still_a_payment(self):
        debit, _ = mirrored()
        payments, pairs = collapse_mirrors([debit])
        self.assertEqual(len(payments), 1)
        self.assertEqual(pairs, ())
        self.assertFalse(payments[0].bilateral)

    def test_three_debits_and_one_credit_give_three_payments(self):
        rows = [
            a_row(direction=TransactionDirection.debit, day=1),
            a_row(direction=TransactionDirection.debit, day=1),
            a_row(direction=TransactionDirection.debit, day=1),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_B,
                  direction=TransactionDirection.credit, day=1),
        ]
        payments, pairs = collapse_mirrors(rows)
        self.assertEqual(len(payments), 3)
        self.assertEqual(len(pairs), 1)

    def test_the_total_survives_a_partial_collapse(self):
        rows = [
            a_row(direction=TransactionDirection.debit, day=1),
            a_row(direction=TransactionDirection.debit, day=1),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_B,
                  direction=TransactionDirection.credit, day=1),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("200.00"))


class TheCollapseIsDeterministic(unittest.TestCase):
    """Same rows, any order, same answer -- an exhibit must reproduce."""

    def population(self):
        rows = []
        for day in (1, 2, 3, 4):
            rows.extend(mirrored(amount="100.00", debit_day=day, credit_day=day))
        rows.extend(mirrored(amount="250.00", debit_day=2, credit_day=3))
        rows.append(a_row(direction=TransactionDirection.debit, day=5, amount="10.00"))
        return rows

    def test_shuffling_does_not_change_the_result(self):
        rows = self.population()
        expected = collapse_mirrors(rows)
        rng = random.Random(20240301)
        for _ in range(25):
            shuffled = list(rows)
            rng.shuffle(shuffled)
            self.assertEqual(collapse_mirrors(shuffled), expected)

    def test_shuffling_does_not_change_the_figures(self):
        rows = self.population()
        p = Perspective.of("acme")
        expected = analyse(rows, p, currency="USD")
        rng = random.Random(7)
        for _ in range(25):
            shuffled = list(rows)
            rng.shuffle(shuffled)
            self.assertEqual(analyse(shuffled, p, currency="USD"), expected)

    def test_payments_come_out_in_date_order(self):
        payments, _ = collapse_mirrors(self.population())
        dates = [m.ordering_date for m in payments]
        self.assertEqual(dates, sorted(dates))

    def test_pairs_come_out_in_debit_date_order(self):
        _, pairs = collapse_mirrors(self.population())
        dates = [p.debit_date for p in pairs]
        self.assertEqual(dates, sorted(dates))

    def test_a_tie_on_date_is_broken_by_transaction_id(self):
        one = a_row(transaction_id=ident(200), day=1, amount="5.00")
        two = a_row(transaction_id=ident(100), day=1, amount="5.00")
        payments, _ = collapse_mirrors([one, two])
        self.assertEqual([m.rows[0] for m in payments], [ident(100), ident(200)])

    def test_pairs_tie_on_date_are_broken_by_the_debit_id_too(self):
        # Two relationships, both settled the same day, so `debit_date` alone
        # leaves the order to whatever the group sweep happened to build.  The
        # groups are visited in key order, which puts beta's pair first, and
        # beta's debit id sorts *after* gamma's -- so a stable sort on the date
        # alone would leave them the wrong way round.  Only the id tiebreak
        # puts them in a reproducible order.
        rows = [
            a_row(counterparty=BETA, account=ACCOUNT_A, transaction_id=ident(5000),
                  day=1, direction=TransactionDirection.debit),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_B,
                  transaction_id=ident(5001), day=1,
                  direction=TransactionDirection.credit),
            a_row(counterparty=GAMMA, account=ACCOUNT_A, transaction_id=ident(4000),
                  day=1, direction=TransactionDirection.debit),
            a_row(holder=GAMMA, counterparty=ACME, account=ACCOUNT_C,
                  transaction_id=ident(4001), day=1,
                  direction=TransactionDirection.credit),
        ]
        _, pairs = collapse_mirrors(rows)
        self.assertEqual(len(pairs), 2)
        self.assertEqual([p.debit_id for p in pairs], [ident(4000), ident(5000)])


class DuplicateRowsAreRefused(unittest.TestCase):
    """The same id twice is a caller defect, not something to average over."""

    def test_collapse_refuses_a_repeated_id(self):
        row = a_row(transaction_id=ident(55))
        with self.assertRaises(DuplicateRowError) as caught:
            collapse_mirrors([row, row])
        self.assertIn(str(ident(55)), str(caught.exception))

    def test_the_uncollapsed_path_refuses_it_too(self):
        row = a_row(transaction_id=ident(55))
        with self.assertRaises(DuplicateRowError):
            flow._payments_only([row, row])

    def test_analyse_refuses_it_on_both_paths(self):
        row = a_row(transaction_id=ident(55))
        p = Perspective.of("acme")
        with self.assertRaises(DuplicateRowError):
            analyse([row, row], p, currency="USD")
        with self.assertRaises(DuplicateRowError):
            analyse([row, row], p, currency="USD", collapse=False)

    def test_two_distinct_ids_are_fine(self):
        payments, _ = collapse_mirrors([a_row(transaction_id=ident(1)),
                                        a_row(transaction_id=ident(2))])
        self.assertEqual(len(payments), 2)


class WhatThePairBecomes(unittest.TestCase):
    """Three choices in `_payment_from_pair`, each asserted."""

    def test_the_earlier_date_is_kept(self):
        payments, _ = collapse_mirrors(mirrored(debit_day=2, credit_day=4))
        self.assertEqual(payments[0].ordering_date, date(2024, 3, 2))

    def test_the_earlier_date_is_kept_when_the_credit_leads(self):
        payments, _ = collapse_mirrors(mirrored(debit_day=4, credit_day=2))
        self.assertEqual(payments[0].ordering_date, date(2024, 3, 2))

    def test_the_stronger_class_is_kept(self):
        payments, _ = collapse_mirrors(
            mirrored(debit_class=ProofClass.p3, credit_class=ProofClass.p0)
        )
        self.assertIs(payments[0].proof_class, ProofClass.p0)

    def test_the_stronger_class_is_kept_in_either_position(self):
        payments, _ = collapse_mirrors(
            mirrored(debit_class=ProofClass.p0, credit_class=ProofClass.p3)
        )
        self.assertIs(payments[0].proof_class, ProofClass.p0)

    def test_the_pair_records_the_stronger_class_too(self):
        _, pairs = collapse_mirrors(
            mirrored(debit_class=ProofClass.p3, credit_class=ProofClass.p1)
        )
        self.assertIs(pairs[0].proof_class, ProofClass.p1)

    def test_each_side_is_named_by_its_own_bank(self):
        # The payer's statement calls the payer by one label and the payee's
        # statement calls it another; each side keeps the label its own bank
        # used for it, because that is the one with a document behind it.
        payer_as_seen_by_itself = Party(key="acme", name="Acme LLC")
        payer_as_seen_by_beta = Party(key="acme", name="ACME L.L.C.")
        debit, credit = mirrored(payer=payer_as_seen_by_itself, payee=BETA)
        credit = a_row(
            holder=BETA, counterparty=payer_as_seen_by_beta,
            direction=TransactionDirection.credit, account=ACCOUNT_B,
        )
        payments, _ = collapse_mirrors([debit, credit])
        self.assertEqual(payments[0].payer.name, "Acme LLC")
        self.assertEqual(payments[0].payee.name, "Beta Inc")

    def test_reconciled_needs_both_sides(self):
        for debit_ok, credit_ok, expected in (
            (True, True, True),
            (True, False, False),
            (False, True, False),
            (False, False, False),
        ):
            payments, _ = collapse_mirrors(
                mirrored(debit_reconciled=debit_ok, credit_reconciled=credit_ok)
            )
            self.assertIs(payments[0].reconciled, expected)

    def test_the_description_prefers_the_debit(self):
        payments, _ = collapse_mirrors(
            mirrored(debit_description="wire out", credit_description="wire in")
        )
        self.assertEqual(payments[0].description, "wire out")

    def test_the_description_falls_back_to_the_credit(self):
        payments, _ = collapse_mirrors(
            mirrored(debit_description=None, credit_description="wire in")
        )
        self.assertEqual(payments[0].description, "wire in")

    def test_no_description_on_either_side_is_none(self):
        payments, _ = collapse_mirrors(mirrored())
        self.assertIsNone(payments[0].description)

    def test_an_empty_debit_description_falls_through(self):
        payments, _ = collapse_mirrors(
            mirrored(debit_description="", credit_description="wire in")
        )
        self.assertEqual(payments[0].description, "wire in")


# ---------------------------------------------------------------------------
# The counterparty and the bar
# ---------------------------------------------------------------------------


class CounterpartyFlowTests(unittest.TestCase):
    """One relationship, two halves.  Merged bidirectionally, on purpose."""

    def flow_for(self, inflow: Figure, outflow: Figure) -> CounterpartyFlow:
        return CounterpartyFlow(party=BETA, inflow=inflow, outflow=outflow)

    def test_total_is_gross_traffic_not_net(self):
        c = self.flow_for(figure("30.00", 1, p2=(1, "30.00")),
                          figure("20.00", 1, p2=(1, "20.00")))
        self.assertEqual(c.total, usd("50.00"))

    def test_net_is_positive_when_the_set_received_more(self):
        c = self.flow_for(figure("30.00", 1, p2=(1, "30.00")),
                          figure("20.00", 1, p2=(1, "20.00")))
        self.assertEqual(c.net, usd("10.00"))

    def test_net_is_negative_when_the_set_sent_more(self):
        c = self.flow_for(figure("20.00", 1, p2=(1, "20.00")),
                          figure("30.00", 1, p2=(1, "30.00")))
        self.assertEqual(c.net, usd("-10.00"))

    def test_net_is_zero_when_the_money_came_back(self):
        # Gross fifty, net nothing: the pair of figures says something a single
        # number cannot, which is why both halves are kept.
        c = self.flow_for(figure("25.00", 1, p2=(1, "25.00")),
                          figure("25.00", 1, p2=(1, "25.00")))
        self.assertEqual(c.net, usd("0.00"))
        self.assertEqual(c.total, usd("50.00"))

    def test_count_adds_both_directions(self):
        c = self.flow_for(figure("30.00", 2, p2=(2, "30.00")),
                          figure("20.00", 3, p2=(3, "20.00")))
        self.assertEqual(c.count, 5)

    def test_bidirectional_needs_both_halves(self):
        both = self.flow_for(figure("1.00", 1, p2=(1, "1.00")),
                             figure("1.00", 1, p2=(1, "1.00")))
        self.assertTrue(both.is_bidirectional)

    def test_inflow_only_is_not_bidirectional(self):
        c = self.flow_for(figure("1.00", 1, p2=(1, "1.00")), figure("0.00", 0))
        self.assertFalse(c.is_bidirectional)

    def test_outflow_only_is_not_bidirectional(self):
        c = self.flow_for(figure("0.00", 0), figure("1.00", 1, p2=(1, "1.00")))
        self.assertFalse(c.is_bidirectional)

    def test_a_zero_amount_over_a_real_row_is_still_bidirectional(self):
        # Bidirectionality is about rows, not sums.
        c = self.flow_for(figure("0.00", 1, p2=(1, "0.00")),
                          figure("0.00", 1, p2=(1, "0.00")))
        self.assertTrue(c.is_bidirectional)

    def test_describe_names_the_party_and_both_directions(self):
        c = self.flow_for(figure("30.00", 1, p2=(1, "30.00")),
                          figure("20.00", 1, p2=(1, "20.00")))
        self.assertEqual(c.describe(), "Beta Inc: in 30.00 USD, out 20.00 USD, net 10.00 USD")

    def test_describe_uses_the_label_and_so_falls_back_to_the_key(self):
        c = CounterpartyFlow(party=Party(key="k-9"), inflow=figure(), outflow=figure())
        self.assertTrue(c.describe().startswith("k-9:"))


class CombineFiguresTests(unittest.TestCase):
    """An aggregate must describe the same population as the bars it replaced."""

    def test_combining_nothing_is_zero_in_the_stated_currency(self):
        combined = flow._combine_figures([], "EUR")
        self.assertEqual(combined.amount, eur("0.00"))
        self.assertEqual(combined.count, 0)
        self.assertEqual(combined.composition.classes, ())

    def test_amounts_and_counts_both_add(self):
        combined = flow._combine_figures(
            [figure("10.00", 1, p2=(1, "10.00")), figure("5.00", 2, p2=(2, "5.00"))],
            "USD",
        )
        self.assertEqual(combined.amount, usd("15.00"))
        self.assertEqual(combined.count, 3)
        # The class counts add the *number* each figure carries, not one per
        # figure: the second figure holds two p2 payments, not one.  Asserting
        # only `combined.count` leaves that distinction untested.
        self.assertEqual(combined.composition.counts, {ProofClass.p2: 3})

    def test_the_composition_carries_through(self):
        combined = flow._combine_figures(
            [figure("10.00", 1, p1=(1, "10.00")), figure("5.00", 1, p3=(1, "5.00"))],
            "USD",
        )
        self.assertEqual(combined.composition.counts,
                         {ProofClass.p1: 1, ProofClass.p3: 1})
        self.assertEqual(combined.composition.amounts,
                         {ProofClass.p1: usd("10.00"), ProofClass.p3: usd("5.00")})

    def test_the_same_class_from_two_figures_merges(self):
        combined = flow._combine_figures(
            [figure("10.00", 1, p2=(1, "10.00")), figure("5.00", 1, p2=(1, "5.00"))],
            "USD",
        )
        self.assertEqual(combined.composition.counts, {ProofClass.p2: 2})
        self.assertEqual(combined.composition.amounts, {ProofClass.p2: usd("15.00")})

    def test_an_aggregate_of_one_equals_that_one(self):
        only = figure("7.00", 1, p2=(1, "7.00"))
        combined = flow._combine_figures([only], "USD")
        self.assertEqual(combined.amount, only.amount)
        self.assertEqual(combined.count, only.count)
        self.assertEqual(combined.composition.counts, only.composition.counts)

    def test_the_result_is_a_plain_dict_not_a_defaultdict_view(self):
        combined = flow._combine_figures([figure("1.00", 1, p2=(1, "1.00"))], "USD")
        self.assertIs(type(combined.composition.counts), dict)


class ChartBarTests(unittest.TestCase):
    """The sign convention lives here and is stated once."""

    def bar(self, inflow="0.00", in_count=0, outflow="0.00", out_count=0, **kw):
        return ChartBar(
            key=kw.pop("key", "beta"),
            label=kw.pop("label", "Beta Inc"),
            inflow=figure(inflow, in_count, **({"p2": (in_count, inflow)} if in_count else {})),
            outflow=figure(outflow, out_count, **({"p2": (out_count, outflow)} if out_count else {})),
            **kw,
        )

    def test_outflow_is_held_positive(self):
        self.assertEqual(self.bar(outflow="20.00", out_count=1).outflow.amount, usd("20.00"))

    def test_but_plotted_negative(self):
        self.assertEqual(self.bar(outflow="20.00", out_count=1).plotted_outflow, usd("-20.00"))

    def test_a_zero_outflow_plots_at_zero(self):
        self.assertEqual(self.bar().plotted_outflow, usd("0.00"))

    def test_inflow_is_not_negated(self):
        bar = self.bar(inflow="30.00", in_count=1)
        self.assertEqual(bar.inflow.amount, usd("30.00"))

    def test_total_is_the_bar_length_in_both_directions(self):
        bar = self.bar(inflow="30.00", in_count=1, outflow="20.00", out_count=1)
        self.assertEqual(bar.total, usd("50.00"))

    def test_net_is_the_balance(self):
        bar = self.bar(inflow="30.00", in_count=1, outflow="20.00", out_count=1)
        self.assertEqual(bar.net, usd("10.00"))

    def test_a_bar_is_not_an_aggregate_by_default(self):
        self.assertFalse(self.bar().is_aggregate)

    def test_an_aggregate_bar_has_no_key(self):
        bar = self.bar(key=None, label="3 further counterparties", is_aggregate=True)
        self.assertIsNone(bar.key)
        self.assertTrue(bar.is_aggregate)


class DivergentChartTests(unittest.TestCase):
    def chart(self, bars, **kw):
        return DivergentChart(
            bars=tuple(bars),
            limit=kw.pop("limit", DEFAULT_CHART_LIMIT),
            baseline=kw.pop("baseline", usd("0.00")),
            named_counterparties=kw.pop("named_counterparties", len(bars)),
            charted_counterparties=kw.pop("charted_counterparties", len(bars)),
        )

    def a_bar(self, key, inflow, outflow):
        return ChartBar(
            key=key,
            label=key,
            inflow=figure(inflow, 1, p2=(1, inflow)),
            outflow=figure(outflow, 1, p2=(1, outflow)),
        )

    def test_the_baseline_is_zero_in_the_flows_currency(self):
        chart = self.chart([], baseline=eur("0.00"))
        self.assertEqual(chart.baseline, eur("0.00"))
        self.assertEqual(chart.inflow_total, eur("0.00"))

    def test_totals_sum_the_bars(self):
        chart = self.chart([self.a_bar("a", "10.00", "1.00"),
                            self.a_bar("b", "20.00", "2.00")])
        self.assertEqual(chart.inflow_total, usd("30.00"))
        self.assertEqual(chart.outflow_total, usd("3.00"))

    def test_an_empty_chart_totals_zero(self):
        chart = self.chart([])
        self.assertEqual(chart.inflow_total, usd("0.00"))
        self.assertEqual(chart.outflow_total, usd("0.00"))

    def test_extent_is_the_largest_single_direction(self):
        chart = self.chart([self.a_bar("a", "10.00", "40.00"),
                            self.a_bar("b", "30.00", "5.00")])
        self.assertEqual(chart.extent, usd("40.00"))

    def test_extent_is_not_the_sum_of_a_bar(self):
        # A bar with 30 in and 30 out is 60 of traffic but extends 30 either way.
        chart = self.chart([self.a_bar("a", "30.00", "30.00")])
        self.assertEqual(chart.extent, usd("30.00"))

    def test_extent_of_an_empty_chart_is_the_baseline(self):
        self.assertEqual(self.chart([]).extent, usd("0.00"))

    def test_not_truncated_when_every_party_got_a_bar(self):
        chart = self.chart([self.a_bar("a", "1.00", "0.00")],
                           named_counterparties=1, charted_counterparties=1)
        self.assertFalse(chart.truncated)

    def test_truncated_when_some_were_aggregated(self):
        chart = self.chart([self.a_bar("a", "1.00", "0.00")],
                           named_counterparties=5, charted_counterparties=1)
        self.assertTrue(chart.truncated)


# ---------------------------------------------------------------------------
# The result object, and the invariant that keeps it honest
# ---------------------------------------------------------------------------


def a_flow(**kw) -> MoneyFlow:
    """A MoneyFlow built directly, for testing the object rather than `analyse`."""
    currency = kw.pop("currency", "USD")
    zero = Figure(
        amount=Money.zero(currency),
        count=0,
        composition=ClassComposition(counts={}, amounts={}),
    )
    defaults = dict(
        perspective=Perspective.of("acme"),
        currency=currency,
        included_classes=DEFAULT_TOTAL_CLASSES,
        settlement_days=DEFAULT_SETTLEMENT_DAYS,
        collapsed=True,
        inflow=zero,
        outflow=zero,
        internal=zero,
        unattributed_inflow=zero,
        unattributed_outflow=zero,
        out_of_scope=zero,
        unreconciled=zero,
        counterparties=(),
        mirrors=(),
        set_aside={},
        notes=(),
    )
    defaults.update(kw)
    return MoneyFlow(**defaults)


def a_counterparty(party, inflow="0.00", in_count=0, outflow="0.00", out_count=0):
    return CounterpartyFlow(
        party=party,
        inflow=figure(inflow, in_count, **({"p2": (in_count, inflow)} if in_count else {})),
        outflow=figure(outflow, out_count, **({"p2": (out_count, outflow)} if out_count else {})),
    )


class InvariantsAreEnforced(unittest.TestCase):
    """A screen that disagrees with itself is worse than an error."""

    def test_a_closed_flow_constructs(self):
        flow_obj = a_flow(
            inflow=figure("10.00", 1, p2=(1, "10.00")),
            counterparties=(a_counterparty(BETA, inflow="10.00", in_count=1),),
        )
        self.assertEqual(flow_obj.inflow.amount, usd("10.00"))

    def test_inflow_short_of_its_breakdown_is_refused(self):
        with self.assertRaises(FlowInvariantError) as caught:
            a_flow(
                inflow=figure("10.00", 1, p2=(1, "10.00")),
                counterparties=(a_counterparty(BETA, inflow="7.00", in_count=1),),
            )
        self.assertIn("counterparty breakdown", str(caught.exception))

    def test_the_refusal_shows_both_figures(self):
        with self.assertRaises(FlowInvariantError) as caught:
            a_flow(
                inflow=figure("10.00", 1, p2=(1, "10.00")),
                counterparties=(a_counterparty(BETA, inflow="7.00", in_count=1),),
            )
        self.assertIn("10.00 USD", str(caught.exception))
        self.assertIn("7.00 USD", str(caught.exception))

    def test_outflow_short_of_its_breakdown_is_refused(self):
        with self.assertRaises(FlowInvariantError) as caught:
            a_flow(
                outflow=figure("10.00", 1, p2=(1, "10.00")),
                counterparties=(a_counterparty(BETA, outflow="7.00", out_count=1),),
            )
        self.assertIn("outflow", str(caught.exception))

    def test_the_unattributed_remainder_closes_the_gap(self):
        # This is exactly V1's shortfall, and the reason the residue is a figure
        # rather than a silence.
        flow_obj = a_flow(
            inflow=figure("10.00", 2, p2=(2, "10.00")),
            unattributed_inflow=figure("3.00", 1, p2=(1, "3.00")),
            counterparties=(a_counterparty(BETA, inflow="7.00", in_count=1),),
        )
        self.assertEqual(flow_obj.inflow.amount, usd("10.00"))

    def test_an_unattributed_remainder_that_overshoots_is_refused(self):
        with self.assertRaises(FlowInvariantError):
            a_flow(
                inflow=figure("10.00", 2, p2=(2, "10.00")),
                unattributed_inflow=figure("4.00", 1, p2=(1, "4.00")),
                counterparties=(a_counterparty(BETA, inflow="7.00", in_count=1),),
            )

    def test_internal_is_not_part_of_the_breakdown(self):
        # A transfer inside the set has no external counterparty, so it must not
        # be expected to appear among them.
        flow_obj = a_flow(internal=figure("50.00", 1, p2=(1, "50.00")))
        self.assertEqual(flow_obj.internal.amount, usd("50.00"))
        self.assertEqual(flow_obj.counterparties, ())

    def test_out_of_scope_is_not_part_of_the_breakdown_either(self):
        flow_obj = a_flow(out_of_scope=figure("50.00", 1, p2=(1, "50.00")))
        self.assertEqual(flow_obj.out_of_scope.amount, usd("50.00"))


class HeadlineFiguresTests(unittest.TestCase):
    def test_net_is_negative_for_a_net_payer(self):
        flow_obj = a_flow(
            outflow=figure("10.00", 1, p2=(1, "10.00")),
            counterparties=(a_counterparty(BETA, outflow="10.00", out_count=1),),
        )
        self.assertEqual(flow_obj.net, usd("-10.00"))

    def test_total_volume_counts_internal_once(self):
        flow_obj = a_flow(
            inflow=figure("10.00", 1, p2=(1, "10.00")),
            internal=figure("50.00", 1, p2=(1, "50.00")),
            counterparties=(a_counterparty(BETA, inflow="10.00", in_count=1),),
        )
        self.assertEqual(flow_obj.total_volume, usd("60.00"))

    def test_payment_count_spans_all_three_cards(self):
        flow_obj = a_flow(
            inflow=figure("1.00", 1, p2=(1, "1.00")),
            internal=figure("1.00", 2, p2=(2, "1.00")),
            counterparties=(a_counterparty(BETA, inflow="1.00", in_count=1),),
        )
        self.assertEqual(flow_obj.payment_count, 3)

    def test_has_internal_is_about_rows_not_amounts(self):
        self.assertFalse(a_flow().has_internal)
        self.assertTrue(a_flow(internal=figure("0.00", 1, p2=(1, "0.00"))).has_internal)

    def test_bilateral_count_is_the_number_of_pairs(self):
        _, pairs = collapse_mirrors(mirrored())
        self.assertEqual(a_flow(mirrors=pairs).bilateral_count, 1)
        self.assertEqual(a_flow().bilateral_count, 0)

    def test_composition_spans_the_three_cards(self):
        flow_obj = a_flow(
            inflow=figure("1.00", 1, p1=(1, "1.00")),
            internal=figure("2.00", 1, p3=(1, "2.00")),
            counterparties=(a_counterparty(BETA, inflow="1.00", in_count=1),),
        )
        self.assertEqual(flow_obj.composition.classes, (ProofClass.p1, ProofClass.p3))
        self.assertFalse(flow_obj.composition.is_uniform)

    def test_describe_omits_internal_when_there_is_none(self):
        text = a_flow(
            outflow=figure("10.00", 1, p2=(1, "10.00")),
            counterparties=(a_counterparty(BETA, outflow="10.00", out_count=1),),
        ).describe()
        self.assertNotIn("internal", text)
        self.assertIn("out 10.00 USD (1)", text)
        self.assertIn("net -10.00 USD", text)

    def test_describe_names_internal_when_there_is_some(self):
        text = a_flow(internal=figure("5.00", 1, p2=(1, "5.00"))).describe()
        self.assertIn("internal 5.00 USD (1)", text)

    def test_describe_always_states_the_classes(self):
        self.assertIn("classes no rows", a_flow().describe())


class TheChartCloses(unittest.TestCase):
    """The bars sum to the cards.  V1's did not, and nothing said so."""

    def many(self, count, *, each="10.00"):
        parties = [Party(key=f"p{i:02d}", name=f"Party {i:02d}") for i in range(count)]
        counterparties = tuple(
            a_counterparty(p, outflow=each, out_count=1) for p in parties
        )
        total = Money.from_decimal(Decimal(each) * count, "USD")
        return a_flow(
            outflow=Figure(
                amount=total,
                count=count,
                composition=ClassComposition(
                    counts={ProofClass.p2: count}, amounts={ProofClass.p2: total}
                ),
            ),
            counterparties=counterparties,
        )

    def test_the_default_limit_is_twelve(self):
        self.assertEqual(DEFAULT_CHART_LIMIT, 12)

    def test_a_chart_within_the_limit_draws_every_party(self):
        chart = self.many(3).divergent_chart()
        self.assertEqual(len(chart.bars), 3)
        self.assertFalse(chart.truncated)
        self.assertFalse(any(bar.is_aggregate for bar in chart.bars))

    def test_exactly_at_the_limit_is_not_aggregated(self):
        chart = self.many(12).divergent_chart()
        self.assertEqual(len(chart.bars), 12)
        self.assertFalse(chart.truncated)

    def test_one_past_the_limit_gets_an_aggregate_bar(self):
        chart = self.many(13).divergent_chart()
        self.assertEqual(len(chart.bars), 13)
        self.assertTrue(chart.truncated)
        self.assertTrue(chart.bars[-1].is_aggregate)

    def test_the_aggregate_bar_is_singular_for_one(self):
        chart = self.many(13).divergent_chart()
        self.assertEqual(chart.bars[-1].label, "1 further counterparty")

    def test_the_aggregate_bar_is_plural_for_two(self):
        chart = self.many(14).divergent_chart()
        self.assertEqual(chart.bars[-1].label, "2 further counterparties")

    def test_the_remainder_is_kept_not_dropped(self):
        # V1 drew twelve and lost the rest.  Here the total still closes.
        flow_obj = self.many(20)
        chart = flow_obj.divergent_chart()
        self.assertEqual(chart.outflow_total, flow_obj.outflow.amount)
        self.assertEqual(chart.outflow_total, usd("200.00"))

    def test_the_aggregate_carries_the_composition_of_what_it_replaced(self):
        chart = self.many(15).divergent_chart()
        aggregate = chart.bars[-1]
        self.assertEqual(aggregate.outflow.count, 3)
        self.assertEqual(aggregate.outflow.composition.counts, {ProofClass.p2: 3})

    def test_charted_and_named_counts_are_reported(self):
        chart = self.many(20).divergent_chart()
        self.assertEqual(chart.named_counterparties, 20)
        self.assertEqual(chart.charted_counterparties, 12)

    def test_a_smaller_limit_is_honoured(self):
        chart = self.many(20).divergent_chart(limit=3)
        self.assertEqual(chart.limit, 3)
        self.assertEqual(chart.charted_counterparties, 3)
        self.assertEqual(chart.bars[-1].label, "17 further counterparties")

    def test_a_limit_of_one_is_allowed(self):
        chart = self.many(5).divergent_chart(limit=1)
        self.assertEqual(len(chart.bars), 2)

    def test_a_limit_of_zero_is_refused(self):
        with self.assertRaises(FlowError) as caught:
            self.many(5).divergent_chart(limit=0)
        self.assertIn("at least one bar", str(caught.exception))

    def test_a_negative_limit_is_refused(self):
        with self.assertRaises(FlowError):
            self.many(5).divergent_chart(limit=-1)

    def test_the_unidentified_residue_gets_a_bar_of_its_own(self):
        flow_obj = a_flow(
            outflow=figure("30.00", 2, p2=(2, "30.00")),
            unattributed_outflow=figure("20.00", 1, p2=(1, "20.00")),
            counterparties=(a_counterparty(BETA, outflow="10.00", out_count=1),),
        )
        chart = flow_obj.divergent_chart()
        self.assertEqual(chart.bars[-1].label, "counterparty not identified")
        self.assertTrue(chart.bars[-1].is_aggregate)
        self.assertEqual(chart.outflow_total, usd("30.00"))

    def test_the_residue_bar_is_absent_when_there_is_no_residue(self):
        chart = self.many(2).divergent_chart()
        self.assertFalse(any(b.label == "counterparty not identified" for b in chart.bars))

    def test_a_residue_bar_appears_for_a_zero_amount_over_real_rows(self):
        # Zero money, one payment: the row exists and must be visible.
        flow_obj = a_flow(
            outflow=figure("0.00", 1, p2=(1, "0.00")),
            unattributed_outflow=figure("0.00", 1, p2=(1, "0.00")),
        )
        chart = flow_obj.divergent_chart()
        self.assertEqual(len(chart.bars), 1)
        self.assertEqual(chart.bars[0].label, "counterparty not identified")

    def test_both_aggregate_bars_can_appear_together(self):
        parties = [Party(key=f"p{i:02d}") for i in range(13)]
        counterparties = tuple(
            a_counterparty(p, outflow="10.00", out_count=1) for p in parties
        )
        flow_obj = a_flow(
            outflow=figure("135.00", 14, p2=(14, "135.00")),
            unattributed_outflow=figure("5.00", 1, p2=(1, "5.00")),
            counterparties=counterparties,
        )
        chart = flow_obj.divergent_chart()
        self.assertEqual(len(chart.bars), 14)
        self.assertEqual(chart.bars[-2].label, "1 further counterparty")
        self.assertEqual(chart.bars[-1].label, "counterparty not identified")
        self.assertEqual(chart.outflow_total, usd("135.00"))

    def test_an_empty_flow_charts_as_nothing(self):
        chart = a_flow().divergent_chart()
        self.assertEqual(chart.bars, ())
        self.assertEqual(chart.inflow_total, usd("0.00"))
        self.assertFalse(chart.truncated)

    def test_the_chart_is_in_the_flows_currency(self):
        chart = a_flow(currency="EUR").divergent_chart()
        self.assertEqual(chart.baseline, eur("0.00"))


# ---------------------------------------------------------------------------
# analyse: what is in scope, what is counted, and the difference
# ---------------------------------------------------------------------------


class PreconditionsTests(unittest.TestCase):
    def test_an_unknown_currency_is_refused(self):
        with self.assertRaises(FlowCurrencyError) as caught:
            analyse([], Perspective.of("acme"), currency="XYZ")
        self.assertIn("not a currency this system knows", str(caught.exception))

    def test_a_mixed_currency_population_is_refused(self):
        rows = [a_row(currency="USD"), a_row(currency="EUR", account=ACCOUNT_C)]
        with self.assertRaises(FlowCurrencyError) as caught:
            analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertIn("EUR", str(caught.exception))

    def test_the_refusal_explains_why_dropping_is_not_an_option(self):
        rows = [a_row(currency="USD"), a_row(currency="EUR", account=ACCOUNT_C)]
        with self.assertRaises(FlowCurrencyError) as caught:
            analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertIn("looks complete and is not", str(caught.exception))

    def test_counting_no_class_is_refused(self):
        with self.assertRaises(FlowError) as caught:
            analyse([], Perspective.of("acme"), currency="USD", included=frozenset())
        self.assertIn("at least one proof class", str(caught.exception))

    def test_the_refusal_says_why_a_zero_would_be_ambiguous(self):
        with self.assertRaises(FlowError) as caught:
            analyse([], Perspective.of("acme"), currency="USD", included=frozenset())
        self.assertIn("no money", str(caught.exception))

    def test_something_that_is_not_a_perspective_is_refused(self):
        with self.assertRaises(PerspectiveError) as caught:
            analyse([], frozenset({"acme"}), currency="USD")
        self.assertIn("takes a Perspective", str(caught.exception))

    def test_an_empty_population_gives_zeros_and_not_an_error(self):
        result = analyse([], Perspective.of("acme"), currency="USD")
        self.assertEqual(result.inflow.amount, usd("0.00"))
        self.assertEqual(result.payment_count, 0)
        self.assertEqual(result.counterparties, ())

    def test_a_generator_is_accepted(self):
        result = analyse(iter([a_row()]), Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.count, 1)

    def test_the_settings_are_carried_on_the_result(self):
        result = analyse([], Perspective.of("acme"), currency="EUR",
                         settlement_days=5, collapse=False)
        self.assertEqual(result.currency, "EUR")
        self.assertEqual(result.settlement_days, 5)
        self.assertFalse(result.collapsed)
        self.assertEqual(result.included_classes, DEFAULT_TOTAL_CLASSES)


class ScopeAndClassAreSeparate(unittest.TestCase):
    """Placed first, filtered second.  The order carries the distinction."""

    def test_a_p3_payment_in_scope_is_set_aside_not_absent(self):
        rows = [a_row(proof_class=ProofClass.p3)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.count, 0)
        self.assertEqual(result.set_aside[SetAsideReason.class_not_counted].count, 1)
        self.assertEqual(
            result.set_aside[SetAsideReason.class_not_counted].amount, usd("100.00")
        )

    def test_a_payment_that_was_never_there_is_not_set_aside(self):
        result = analyse([], Perspective.of("acme"), currency="USD")
        self.assertEqual(result.set_aside[SetAsideReason.class_not_counted].count, 0)

    def test_the_two_zeros_are_distinguishable(self):
        # Both report an outflow of zero.  Only one of them has a reason.
        excluded = analyse([a_row(proof_class=ProofClass.p3)],
                           Perspective.of("acme"), currency="USD")
        absent = analyse([], Perspective.of("acme"), currency="USD")
        self.assertEqual(excluded.outflow.amount, absent.outflow.amount)
        self.assertNotEqual(
            excluded.set_aside[SetAsideReason.class_not_counted].count,
            absent.set_aside[SetAsideReason.class_not_counted].count,
        )

    def test_widening_the_filter_counts_it(self):
        rows = [a_row(proof_class=ProofClass.p3)]
        result = analyse(rows, Perspective.of("acme"), currency="USD",
                         included=frozenset({ProofClass.p3}))
        self.assertEqual(result.outflow.count, 1)
        self.assertEqual(result.set_aside[SetAsideReason.class_not_counted].count, 0)

    def test_an_unplaceable_payment_bypasses_the_class_filter(self):
        # Neither side known.  Reporting it under a proof-class heading would
        # name the wrong reason, so it lands in its own bucket regardless.
        rows = [a_row(holder=None, counterparty=None, proof_class=ProofClass.p3)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.set_aside[SetAsideReason.unplaceable].count, 1)
        self.assertEqual(result.set_aside[SetAsideReason.class_not_counted].count, 0)

    def test_an_unplaceable_payment_of_a_counted_class_lands_there_too(self):
        rows = [a_row(holder=None, counterparty=None, proof_class=ProofClass.p1)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.set_aside[SetAsideReason.unplaceable].count, 1)

    def test_out_of_scope_is_counted_only_when_the_class_is(self):
        counted = analyse([a_row(holder=GAMMA, counterparty=DELTA, proof_class=ProofClass.p1)],
                          Perspective.of("acme"), currency="USD")
        self.assertEqual(counted.out_of_scope.count, 1)
        filtered = analyse([a_row(holder=GAMMA, counterparty=DELTA, proof_class=ProofClass.p3)],
                           Perspective.of("acme"), currency="USD")
        self.assertEqual(filtered.out_of_scope.count, 0)

    def test_an_out_of_scope_payment_never_reaches_a_card(self):
        result = analyse([a_row(holder=GAMMA, counterparty=DELTA)],
                         Perspective.of("acme"), currency="USD")
        self.assertEqual(result.payment_count, 0)
        self.assertEqual(result.out_of_scope.count, 1)

    def test_out_of_scope_is_not_a_component_of_the_cards(self):
        result = analyse([a_row(holder=GAMMA, counterparty=DELTA), a_row()],
                         Perspective.of("acme"), currency="USD")
        self.assertEqual(result.total_volume, usd("100.00"))
        self.assertEqual(result.out_of_scope.amount, usd("100.00"))


class ThePerspectiveDecidesTheBuckets(unittest.TestCase):
    def test_a_single_entity_sees_an_outflow(self):
        result = analyse([a_row()], Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("100.00"))
        self.assertEqual(result.inflow.count, 0)

    def test_the_other_side_sees_the_same_payment_as_an_inflow(self):
        result = analyse([a_row()], Perspective.of("beta"), currency="USD")
        self.assertEqual(result.inflow.amount, usd("100.00"))
        self.assertEqual(result.outflow.count, 0)

    def test_selecting_both_makes_it_internal(self):
        result = analyse([a_row()], Perspective.of("acme", "beta"), currency="USD")
        self.assertEqual(result.internal.amount, usd("100.00"))
        self.assertEqual(result.inflow.count, 0)
        self.assertEqual(result.outflow.count, 0)

    def test_an_internal_payment_has_no_counterparty_bar(self):
        result = analyse([a_row()], Perspective.of("acme", "beta"), currency="USD")
        self.assertEqual(result.counterparties, ())
        self.assertEqual(result.divergent_chart().bars, ())

    def test_scope_is_an_or_across_both_sides(self):
        # Acme pays Gamma; Delta pays Beta.  Selecting acme and beta takes both,
        # one on the payer side and one on the payee side.
        rows = [
            a_row(holder=ACME, counterparty=GAMMA),
            a_row(holder=BETA, counterparty=DELTA, account=ACCOUNT_B,
                  direction=TransactionDirection.credit),
        ]
        result = analyse(rows, Perspective.of("acme", "beta"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("100.00"))
        self.assertEqual(result.inflow.amount, usd("100.00"))
        self.assertEqual(result.out_of_scope.count, 0)

    def test_a_wider_perspective_can_turn_an_outflow_internal(self):
        rows = [a_row(holder=ACME, counterparty=GAMMA)]
        narrow = analyse(rows, Perspective.of("acme"), currency="USD")
        wide = analyse(rows, Perspective.of("acme", "gamma"), currency="USD")
        self.assertEqual(narrow.outflow.amount, usd("100.00"))
        self.assertEqual(wide.outflow.count, 0)
        self.assertEqual(wide.internal.amount, usd("100.00"))

    def test_the_perspective_is_carried_on_the_result(self):
        p = Perspective.of("acme", "beta")
        self.assertEqual(analyse([], p, currency="USD").perspective, p)


class CounterpartiesAreMergedBidirectionally(unittest.TestCase):
    def both_ways(self):
        return [
            a_row(holder=ACME, counterparty=GAMMA, amount="30.00",
                  direction=TransactionDirection.debit),
            a_row(holder=ACME, counterparty=GAMMA, amount="20.00",
                  direction=TransactionDirection.credit),
        ]

    def test_one_party_gives_one_entry(self):
        result = analyse(self.both_ways(), Perspective.of("acme"), currency="USD")
        self.assertEqual(len(result.counterparties), 1)

    def test_the_entry_carries_both_halves(self):
        result = analyse(self.both_ways(), Perspective.of("acme"), currency="USD")
        only = result.counterparties[0]
        self.assertEqual(only.outflow.amount, usd("30.00"))
        self.assertEqual(only.inflow.amount, usd("20.00"))
        self.assertTrue(only.is_bidirectional)

    def test_the_cards_agree_with_the_entry(self):
        result = analyse(self.both_ways(), Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("30.00"))
        self.assertEqual(result.inflow.amount, usd("20.00"))
        self.assertEqual(result.net, usd("-10.00"))

    def test_counterparties_are_sorted_by_gross_traffic(self):
        rows = [
            a_row(counterparty=GAMMA, amount="10.00"),
            a_row(counterparty=DELTA, amount="90.00"),
            a_row(counterparty=BETA, amount="50.00"),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual([c.party.key for c in result.counterparties],
                         ["delta", "beta", "gamma"])

    def test_a_tie_on_traffic_is_broken_by_key(self):
        rows = [
            a_row(counterparty=GAMMA, amount="10.00"),
            a_row(counterparty=BETA, amount="10.00"),
            a_row(counterparty=DELTA, amount="10.00"),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual([c.party.key for c in result.counterparties],
                         ["beta", "delta", "gamma"])

    def test_the_best_label_seen_is_kept(self):
        # The same key, named on one line and bare on another.
        rows = [
            a_row(counterparty=Party(key="gamma"), amount="10.00"),
            a_row(counterparty=Party(key="gamma", name="Gamma Co"), amount="10.00"),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(len(result.counterparties), 1)
        self.assertEqual(result.counterparties[0].party.name, "Gamma Co")

    def test_a_party_named_on_the_first_line_keeps_that_name(self):
        rows = [
            a_row(counterparty=Party(key="gamma", name="Gamma Co"), amount="10.00"),
            a_row(counterparty=Party(key="gamma"), amount="10.00"),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.counterparties[0].party.name, "Gamma Co")

    def test_identity_is_the_key_and_not_the_name(self):
        # Two different companies trading under the same name stay two.
        rows = [
            a_row(counterparty=Party(key="g1", name="Consolidated"), amount="10.00"),
            a_row(counterparty=Party(key="g2", name="Consolidated"), amount="10.00"),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(len(result.counterparties), 2)


# ---------------------------------------------------------------------------
# Disclosure
# ---------------------------------------------------------------------------


class TheUnattributedResidue(unittest.TestCase):
    """Money that went somewhere nobody has named."""

    def test_an_unnamed_payee_lands_in_the_residue(self):
        rows = [a_row(counterparty=None)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("100.00"))
        self.assertEqual(result.unattributed_outflow.amount, usd("100.00"))
        self.assertEqual(result.counterparties, ())

    def test_the_residue_is_contained_in_the_card_not_additional(self):
        rows = [a_row(counterparty=None), a_row(counterparty=BETA)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("200.00"))
        self.assertEqual(result.unattributed_outflow.amount, usd("100.00"))

    def test_an_unnamed_payer_lands_in_the_inflow_residue(self):
        rows = [a_row(direction=TransactionDirection.credit, counterparty=None)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.inflow.amount, usd("100.00"))
        self.assertEqual(result.unattributed_inflow.amount, usd("100.00"))

    def test_the_chart_still_closes_over_a_residue(self):
        rows = [a_row(counterparty=None), a_row(counterparty=BETA)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        chart = result.divergent_chart()
        self.assertEqual(chart.outflow_total, result.outflow.amount)
        self.assertEqual(len(chart.bars), 2)

    def test_this_is_the_v1_shortfall_reproduced(self):
        # V1 charted only the named party and the card totalled both, so a
        # reader adding the bars found 100 where the card said 200.
        rows = [a_row(counterparty=None), a_row(counterparty=BETA)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        named_only = _sum_money_for_test(
            [b.outflow.amount for b in result.divergent_chart().bars if b.key]
        )
        self.assertEqual(named_only, usd("100.00"))
        self.assertEqual(result.outflow.amount, usd("200.00"))


def _sum_money_for_test(amounts):
    total = usd("0.00")
    for amount in amounts:
        total = total + amount
    return total


class NotesDisclose(unittest.TestCase):
    """The notes are how this module says how far its figures go."""

    def notes_for(self, rows, keys=("acme",), **kw):
        return analyse(rows, Perspective.of(*keys), currency="USD", **kw).notes

    def test_a_collapse_is_disclosed(self):
        self.assertIn(NOTE_MIRRORS_COLLAPSED, self.notes_for(mirrored()))

    def test_declining_to_collapse_is_disclosed(self):
        notes = self.notes_for(mirrored(), collapse=False)
        self.assertIn(NOTE_MIRRORS_NOT_COLLAPSED, notes)
        self.assertNotIn(NOTE_MIRRORS_COLLAPSED, notes)

    def test_the_not_collapsed_note_says_what_it_costs(self):
        self.assertIn("counted twice", NOTE_MIRRORS_NOT_COLLAPSED)

    def test_a_one_sided_collection_is_disclosed(self):
        # Nothing paired, so no payment is evidenced by both parties.
        self.assertIn(NOTE_NOT_BILATERAL, self.notes_for([a_row()]))

    def test_a_bilateral_collection_does_not_carry_that_note(self):
        self.assertNotIn(NOTE_NOT_BILATERAL, self.notes_for(mirrored()))

    def test_an_empty_population_does_not_claim_to_be_one_sided(self):
        self.assertNotIn(NOTE_NOT_BILATERAL, self.notes_for([]))

    def test_a_settlement_lag_is_disclosed(self):
        self.assertIn(NOTE_SETTLEMENT_LAG,
                      self.notes_for(mirrored(debit_day=1, credit_day=3)))

    def test_a_same_day_pair_carries_no_lag_note(self):
        self.assertNotIn(NOTE_SETTLEMENT_LAG,
                         self.notes_for(mirrored(debit_day=1, credit_day=1)))

    def test_an_unattributed_outflow_is_disclosed(self):
        notes = self.notes_for([a_row(counterparty=None)])
        self.assertIn(NOTE_UNATTRIBUTED_OUTFLOW, notes)

    def test_that_note_admits_the_figure_may_be_overstated(self):
        self.assertIn("may have stayed inside", NOTE_UNATTRIBUTED_OUTFLOW)

    def test_an_unattributed_inflow_is_disclosed(self):
        notes = self.notes_for(
            [a_row(direction=TransactionDirection.credit, counterparty=None)]
        )
        self.assertIn(NOTE_UNATTRIBUTED_INFLOW, notes)

    def test_an_unplaceable_payment_is_disclosed(self):
        notes = self.notes_for([a_row(holder=None, counterparty=None)])
        self.assertIn(NOTE_UNPLACEABLE, notes)

    def test_a_class_exclusion_is_disclosed(self):
        notes = self.notes_for([a_row(proof_class=ProofClass.p3)])
        self.assertIn(NOTE_SET_ASIDE_ON_CLASS, notes)

    def test_an_unreconciled_statement_is_disclosed(self):
        notes = self.notes_for([a_row(reconciled=False)])
        self.assertIn(NOTE_UNRECONCILED, notes)

    def test_unreconciled_is_reported_as_a_subset_of_the_cards(self):
        rows = [a_row(reconciled=False), a_row(reconciled=True)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("200.00"))
        self.assertEqual(result.unreconciled.amount, usd("100.00"))

    def test_an_out_of_scope_unreconciled_row_is_not_counted_as_such(self):
        # The disclosure is about the figures reported, not the whole ledger.
        rows = [a_row(holder=GAMMA, counterparty=DELTA, reconciled=False)]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.unreconciled.count, 0)
        self.assertNotIn(NOTE_UNRECONCILED, result.notes)

    def test_a_mixed_composition_is_disclosed(self):
        rows = [a_row(proof_class=ProofClass.p0), a_row(proof_class=ProofClass.p2)]
        self.assertIn(NOTE_MIXED_COMPOSITION, self.notes_for(rows))

    def test_a_uniform_composition_is_not(self):
        rows = [a_row(proof_class=ProofClass.p2), a_row(proof_class=ProofClass.p2)]
        self.assertNotIn(NOTE_MIXED_COMPOSITION, self.notes_for(rows))

    def test_the_mixed_composition_note_reads_the_internal_card_too(self):
        # A payment between two selected entities lands on the internal card and
        # on neither of the other two.  If the note only combined inflow and
        # outflow it would call this population uniform, and the reader would be
        # told nothing about the p0 money moving inside the group.  Both rows
        # leave acme, so the difference is the card, not the direction.
        rows = [
            a_row(counterparty=GAMMA, proof_class=ProofClass.p2),
            a_row(counterparty=BETA, proof_class=ProofClass.p0, account=ACCOUNT_C),
        ]
        self.assertIn(NOTE_MIXED_COMPOSITION,
                      self.notes_for(rows, keys=("acme", "beta")))

    def test_and_a_population_uniform_across_all_three_cards_is_still_uniform(self):
        rows = [
            a_row(counterparty=GAMMA, proof_class=ProofClass.p2),
            a_row(counterparty=BETA, proof_class=ProofClass.p2, account=ACCOUNT_C),
        ]
        self.assertNotIn(NOTE_MIXED_COMPOSITION,
                         self.notes_for(rows, keys=("acme", "beta")))

    def test_colliding_names_are_disclosed(self):
        rows = [
            a_row(counterparty=Party(key="g1", name="Consolidated Holdings")),
            a_row(counterparty=Party(key="g2", name="Consolidated Holdings")),
        ]
        self.assertIn(NOTE_NAMES_COLLIDE, self.notes_for(rows))

    def test_two_spellings_of_one_name_collide(self):
        # The test above uses byte-identical names, which a comparison on the
        # raw string would also catch.  Two documents rarely agree on case,
        # spacing and punctuation, and it is exactly those near-misses that put
        # one party's money under another party's heading.  The comparison is
        # made on the normalised form for that reason.
        rows = [
            a_row(counterparty=Party(key="g1", name="Consolidated Holdings")),
            a_row(counterparty=Party(key="g2", name="CONSOLIDATED  HOLDINGS.")),
        ]
        self.assertIn(NOTE_NAMES_COLLIDE, self.notes_for(rows))

    def test_distinct_names_do_not_collide(self):
        rows = [a_row(counterparty=GAMMA), a_row(counterparty=DELTA)]
        self.assertNotIn(NOTE_NAMES_COLLIDE, self.notes_for(rows))

    def test_the_same_key_twice_is_not_a_collision(self):
        rows = [a_row(counterparty=GAMMA), a_row(counterparty=GAMMA)]
        self.assertNotIn(NOTE_NAMES_COLLIDE, self.notes_for(rows))

    def test_an_unnamed_party_cannot_collide(self):
        rows = [a_row(counterparty=Party(key="g1")), a_row(counterparty=Party(key="g2"))]
        self.assertNotIn(NOTE_NAMES_COLLIDE, self.notes_for(rows))

    def test_a_clean_population_carries_only_what_applies(self):
        notes = self.notes_for(mirrored())
        self.assertEqual(notes, (NOTE_MIRRORS_COLLAPSED,))

    def test_notes_are_a_tuple_and_so_cannot_be_appended_to(self):
        self.assertIsInstance(self.notes_for([a_row()]), tuple)


class TheHeadlineDefectEndToEnd(unittest.TestCase):
    """The whole point, asserted through the public entry point."""

    def test_both_statements_held_gives_the_right_figure(self):
        result = analyse(mirrored(amount="100.00"), Perspective.of("acme"),
                         currency="USD")
        self.assertEqual(result.outflow.amount, usd("100.00"))
        self.assertEqual(result.outflow.count, 1)
        self.assertEqual(result.bilateral_count, 1)

    def test_the_same_figure_as_when_only_one_statement_is_held(self):
        # The number must not depend on how much of the collection arrived.
        debit, _ = mirrored(amount="100.00")
        one_sided = analyse([debit], Perspective.of("acme"), currency="USD")
        both = analyse(mirrored(amount="100.00"), Perspective.of("acme"),
                       currency="USD")
        self.assertEqual(one_sided.outflow.amount, both.outflow.amount)

    def test_only_the_evidence_note_differs(self):
        debit, _ = mirrored(amount="100.00")
        one_sided = analyse([debit], Perspective.of("acme"), currency="USD")
        both = analyse(mirrored(amount="100.00"), Perspective.of("acme"),
                       currency="USD")
        self.assertIn(NOTE_NOT_BILATERAL, one_sided.notes)
        self.assertIn(NOTE_MIRRORS_COLLAPSED, both.notes)

    def test_the_counterparty_is_not_doubled_either(self):
        result = analyse(mirrored(), Perspective.of("acme"), currency="USD")
        self.assertEqual(len(result.counterparties), 1)
        self.assertEqual(result.counterparties[0].outflow.amount, usd("100.00"))

    def test_the_chart_is_not_doubled_either(self):
        chart = analyse(mirrored(), Perspective.of("acme"), currency="USD").divergent_chart()
        self.assertEqual(chart.outflow_total, usd("100.00"))

    def test_the_uncollapsed_view_is_available_and_says_so(self):
        result = analyse(mirrored(), Perspective.of("acme"), currency="USD",
                         collapse=False)
        self.assertEqual(result.outflow.amount, usd("200.00"))
        self.assertIn(NOTE_MIRRORS_NOT_COLLAPSED, result.notes)
        self.assertEqual(result.mirrors, ())


# ---------------------------------------------------------------------------
# The picker
# ---------------------------------------------------------------------------


def an_option(key="beta", name="Beta Inc", out=0, into=0, volume="0.00"):
    """An EntityOption built directly, for testing the object not the builder."""
    return EntityOption(
        party=Party(key=key, name=name),
        as_payer_count=out,
        as_payee_count=into,
        volume=usd(volume),
        composition=ClassComposition(counts={}, amounts={}),
    )


class EntityOptionTests(unittest.TestCase):
    def test_payment_count_adds_both_directions(self):
        self.assertEqual(an_option(out=2, into=3).payment_count, 5)

    def test_a_party_seen_only_as_payer_counts_only_those(self):
        self.assertEqual(an_option(out=2).payment_count, 2)

    def test_describe_is_singular_for_one_payment(self):
        text = an_option(out=1, volume="100.00").describe()
        self.assertEqual(text, "Beta Inc: 100.00 USD over 1 payment (1 out, 0 in)")

    def test_describe_is_plural_for_two(self):
        text = an_option(out=1, into=1, volume="100.00").describe()
        self.assertEqual(text, "Beta Inc: 100.00 USD over 2 payments (1 out, 1 in)")

    def test_describe_is_plural_for_none(self):
        # "0 payment" would read as a typo rather than as a fact.
        self.assertIn("0 payments", an_option().describe())

    def test_describe_falls_back_to_the_key(self):
        option = EntityOption(
            party=Party(key="k-9"),
            as_payer_count=0,
            as_payee_count=0,
            volume=usd("0.00"),
            composition=ClassComposition(counts={}, amounts={}),
        )
        self.assertTrue(option.describe().startswith("k-9:"))

    def test_describe_keeps_the_two_directions_apart(self):
        # The volume is gross, so the split is the only thing that says whether
        # this party was paying, being paid, or both.
        self.assertIn("(3 out, 1 in)", an_option(out=3, into=1).describe())


class OptionsRankByMoneyNotByEvidence(unittest.TestCase):
    """The substantive change from V1, asserted on the pattern that shows it."""

    def options_for(self, rows, **kw):
        return entity_options(rows, currency="USD", **kw)

    def by_key(self, options):
        return {o.party.key: o for o in options}

    def test_a_payment_held_on_both_sides_is_one_payment(self):
        options = self.by_key(self.options_for(mirrored(amount="100.00")))
        self.assertEqual(options["acme"].volume, usd("100.00"))
        self.assertEqual(options["acme"].payment_count, 1)

    def test_the_volume_does_not_depend_on_how_much_of_the_collection_arrived(self):
        debit, _ = mirrored(amount="100.00")
        one_sided = self.by_key(self.options_for([debit]))
        both = self.by_key(self.options_for(mirrored(amount="100.00")))
        self.assertEqual(one_sided["acme"].volume, both["acme"].volume)
        self.assertEqual(one_sided["acme"].payment_count,
                         both["acme"].payment_count)

    def test_not_collapsing_doubles_it_which_is_what_v1_did(self):
        options = self.by_key(self.options_for(mirrored(amount="100.00"),
                                               collapse=False))
        self.assertEqual(options["acme"].volume, usd("200.00"))
        self.assertEqual(options["acme"].payment_count, 2)

    def a_better_documented_smaller_relationship(self):
        # Beta is documented from both sides at 100; Gamma from one side at 150.
        rows = list(mirrored(amount="100.00"))
        rows.append(a_row(counterparty=GAMMA, amount="150.00", day=5))
        return rows

    def test_the_larger_relationship_ranks_higher(self):
        options = self.options_for(self.a_better_documented_smaller_relationship())
        self.assertEqual([o.party.key for o in options], ["acme", "gamma", "beta"])

    def test_and_the_row_count_would_have_ranked_them_the_other_way(self):
        # This is the ordering V1 produced: the best-evidenced party on top,
        # which made the picker a ranking of collection completeness.
        options = self.options_for(self.a_better_documented_smaller_relationship(),
                                   collapse=False)
        self.assertEqual([o.party.key for o in options], ["acme", "beta", "gamma"])


class OptionsCountWhatEachPartyDid(unittest.TestCase):
    def options_for(self, rows, **kw):
        return {o.party.key: o
                for o in entity_options(rows, currency="USD", **kw)}

    def test_the_payer_and_the_payee_are_counted_separately(self):
        options = self.options_for([a_row()])
        self.assertEqual((options["acme"].as_payer_count,
                          options["acme"].as_payee_count), (1, 0))
        self.assertEqual((options["beta"].as_payer_count,
                          options["beta"].as_payee_count), (0, 1))

    def test_a_party_on_both_sides_of_different_payments_counts_both(self):
        rows = [
            a_row(counterparty=BETA),
            a_row(direction=TransactionDirection.credit, counterparty=GAMMA),
        ]
        options = self.options_for(rows)
        self.assertEqual(options["acme"].as_payer_count, 1)
        self.assertEqual(options["acme"].as_payee_count, 1)
        self.assertEqual(options["acme"].payment_count, 2)

    def test_the_volume_is_gross_traffic_not_net(self):
        rows = [
            a_row(counterparty=BETA, amount="100.00"),
            a_row(direction=TransactionDirection.credit, counterparty=GAMMA,
                  amount="100.00"),
        ]
        self.assertEqual(self.options_for(rows)["acme"].volume, usd("200.00"))

    def test_an_unidentified_party_gets_no_option(self):
        options = self.options_for([a_row(counterparty=None)])
        self.assertEqual(list(options), ["acme"])

    def test_a_payment_with_neither_side_named_contributes_nothing(self):
        self.assertEqual(entity_options([a_row(holder=None, counterparty=None)],
                                        currency="USD"), ())

    def test_but_it_does_not_stop_the_others_being_reported(self):
        rows = [a_row(holder=None, counterparty=None), a_row()]
        self.assertEqual(sorted(self.options_for(rows)), ["acme", "beta"])


class OptionsFilterAndRank(unittest.TestCase):
    def options_for(self, rows, **kw):
        return entity_options(rows, currency="USD", **kw)

    def test_a_class_that_is_not_counted_contributes_nothing(self):
        rows = [a_row(proof_class=ProofClass.p2, amount="100.00"),
                a_row(proof_class=ProofClass.p3, amount="500.00", day=2)]
        options = {o.party.key: o for o in self.options_for(rows)}
        self.assertEqual(options["acme"].volume, usd("100.00"))
        self.assertEqual(options["acme"].payment_count, 1)

    def test_a_class_filter_can_remove_a_party_entirely(self):
        rows = [a_row(counterparty=GAMMA, proof_class=ProofClass.p3)]
        self.assertEqual(self.options_for(rows), ())

    def test_options_are_ranked_by_volume_descending(self):
        rows = [
            a_row(counterparty=BETA, amount="10.00", day=1),
            a_row(counterparty=GAMMA, amount="30.00", day=2),
            a_row(counterparty=DELTA, amount="20.00", day=3),
        ]
        keys = [o.party.key for o in self.options_for(rows)]
        self.assertEqual(keys, ["acme", "gamma", "delta", "beta"])

    def test_a_tie_on_volume_is_broken_by_key(self):
        rows = [
            a_row(counterparty=DELTA, amount="10.00", day=1),
            a_row(counterparty=GAMMA, amount="10.00", day=2),
        ]
        keys = [o.party.key for o in self.options_for(rows)]
        self.assertEqual(keys, ["acme", "delta", "gamma"])

    def test_and_a_tie_is_broken_by_key_against_the_order_of_appearance(self):
        # The test above meets delta before gamma, which is also the order the
        # keys sort in -- so a sort with no tiebreak at all, being stable, gives
        # the same answer and the assertion proves nothing.  Reversing the days
        # separates them: gamma is now built first and must still be ranked
        # second.  This matters beyond neatness, because the tiebreak is the
        # only thing standing between this list and a hash-ordered one --
        # `always_include` is a frozenset, and the keys it contributes enter the
        # table in whatever order that set iterates, which differs from run to
        # run.  Without the tiebreak the picker would reorder itself between
        # two views of the same ledger.
        rows = [
            a_row(counterparty=GAMMA, amount="10.00", day=1),
            a_row(counterparty=DELTA, amount="10.00", day=2),
        ]
        keys = [o.party.key for o in self.options_for(rows)]
        self.assertEqual(keys, ["acme", "delta", "gamma"])

    def test_a_tie_between_keys_that_only_always_include_supplied(self):
        # Two keys with nothing counted for them: their whole presence, and so
        # their whole order, comes from the frozenset.  Ranked correctly they
        # read alpha, zulu whichever way the set happened to iterate.
        options = self.options_for(
            [a_row(counterparty=GAMMA, amount="10.00")],
            always_include=frozenset({"zulu", "alpha"}),
        )
        self.assertEqual([o.party.key for o in options if o.volume.minor_units == 0],
                         ["alpha", "zulu"])

    def test_the_composition_is_carried(self):
        rows = [a_row(proof_class=ProofClass.p1, amount="10.00", day=1),
                a_row(proof_class=ProofClass.p2, amount="5.00", day=2)]
        acme = {o.party.key: o for o in self.options_for(rows)}["acme"]
        self.assertEqual(acme.composition.counts,
                         {ProofClass.p1: 1, ProofClass.p2: 1})
        self.assertEqual(acme.composition.amounts,
                         {ProofClass.p1: usd("10.00"), ProofClass.p2: usd("5.00")})

    def test_the_result_is_a_tuple_and_so_cannot_be_appended_to(self):
        self.assertIsInstance(self.options_for([a_row()]), tuple)


class TheBestLabelIsKept(unittest.TestCase):
    """A key is the identity; the name is whichever document supplied one."""

    def options_for(self, rows):
        return {o.party.key: o
                for o in entity_options(rows, currency="USD")}

    def test_a_name_arriving_later_fills_in_for_an_unnamed_key(self):
        rows = [a_row(counterparty=Party(key="g1"), day=1),
                a_row(counterparty=Party(key="g1", name="Gamma Ltd"), day=2)]
        self.assertEqual(self.options_for(rows)["g1"].party.name, "Gamma Ltd")

    def test_a_name_arriving_first_is_not_overwritten_by_silence(self):
        rows = [a_row(counterparty=Party(key="g1", name="Gamma Ltd"), day=1),
                a_row(counterparty=Party(key="g1"), day=2)]
        self.assertEqual(self.options_for(rows)["g1"].party.name, "Gamma Ltd")

    def test_the_key_is_the_identity_so_both_rows_are_one_option(self):
        rows = [a_row(counterparty=Party(key="g1"), amount="10.00", day=1),
                a_row(counterparty=Party(key="g1", name="Gamma Ltd"),
                      amount="10.00", day=2)]
        options = self.options_for(rows)
        self.assertEqual(options["g1"].volume, usd("20.00"))
        self.assertEqual(options["g1"].as_payee_count, 2)

    def test_a_second_spelling_does_not_displace_the_first(self):
        # The two tests above only pit a name against silence, which a rule of
        # "the last name wins" would also satisfy.  Two *different* names is
        # the case that separates them.  Neither spelling is more correct than
        # the other -- the point is that one of them is chosen and stays chosen,
        # so the same rows always produce the same label.
        rows = [a_row(counterparty=Party(key="g1", name="Gamma Ltd"), day=1),
                a_row(counterparty=Party(key="g1", name="GAMMA LIMITED"), day=2)]
        self.assertEqual(self.options_for(rows)["g1"].party.name, "Gamma Ltd")


class AlwaysIncludeKeepsTheControl(unittest.TestCase):
    """A selected entity with no counted traffic must stay in the list."""

    def options_for(self, rows, keys):
        return entity_options(rows, currency="USD",
                              always_include=frozenset(keys))

    def test_a_key_with_no_traffic_still_gets_an_entry(self):
        options = self.options_for([a_row()], ["zeta"])
        self.assertIn("zeta", [o.party.key for o in options])

    def test_that_entry_is_zeros_rather_than_fabricated(self):
        zeta = [o for o in self.options_for([a_row()], ["zeta"])
                if o.party.key == "zeta"][0]
        self.assertEqual(zeta.volume, usd("0.00"))
        self.assertEqual(zeta.payment_count, 0)
        self.assertEqual(zeta.composition.classes, ())

    def test_that_entry_reads_as_what_it_is(self):
        zeta = [o for o in self.options_for([a_row()], ["zeta"])
                if o.party.key == "zeta"][0]
        self.assertEqual(zeta.describe(),
                         "zeta: 0.00 USD over 0 payments (0 out, 0 in)")

    def test_a_key_already_present_is_not_duplicated(self):
        keys = [o.party.key for o in self.options_for([a_row()], ["acme"])]
        self.assertEqual(keys.count("acme"), 1)

    def test_and_its_figures_are_untouched(self):
        options = {o.party.key: o for o in self.options_for([a_row()], ["acme"])}
        self.assertEqual(options["acme"].volume, usd("100.00"))
        self.assertEqual(options["acme"].party.name, "Acme LLC")

    def test_a_zero_entry_sorts_below_a_real_one(self):
        keys = [o.party.key for o in self.options_for([a_row()], ["zeta"])]
        self.assertEqual(keys[-1], "zeta")

    def test_several_keys_all_appear(self):
        keys = [o.party.key for o in self.options_for([], ["zeta", "yves"])]
        self.assertEqual(keys, ["yves", "zeta"])

    def test_an_empty_always_include_changes_nothing(self):
        self.assertEqual(entity_options([a_row()], currency="USD"),
                         self.options_for([a_row()], []))


class OptionsSharePreconditions(unittest.TestCase):
    def test_an_unknown_currency_is_refused(self):
        with self.assertRaises(FlowCurrencyError):
            entity_options([], currency="XYZ")

    def test_a_mixed_currency_population_is_refused(self):
        rows = [a_row(currency="USD"), a_row(currency="EUR", account=ACCOUNT_C)]
        with self.assertRaises(FlowCurrencyError):
            entity_options(rows, currency="USD")

    def test_counting_no_class_is_refused(self):
        with self.assertRaises(FlowError):
            entity_options([], currency="USD", included=frozenset())

    def test_a_repeated_transaction_id_is_refused(self):
        row = a_row(transaction_id=ident(55))
        with self.assertRaises(DuplicateRowError):
            entity_options([row, row], currency="USD")

    def test_it_is_refused_on_the_uncollapsed_path_too(self):
        row = a_row(transaction_id=ident(55))
        with self.assertRaises(DuplicateRowError):
            entity_options([row, row], currency="USD", collapse=False)

    def test_an_empty_population_gives_no_options(self):
        self.assertEqual(entity_options([], currency="USD"), ())

    def test_always_include_still_works_on_an_empty_population(self):
        options = entity_options([], currency="USD",
                                 always_include=frozenset({"zeta"}))
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].volume, usd("0.00"))

    def test_a_generator_is_accepted(self):
        options = entity_options((r for r in [a_row()]), currency="USD")
        self.assertEqual(len(options), 2)

    def test_the_volume_is_in_the_stated_currency(self):
        options = entity_options([a_row(currency="EUR")], currency="EUR")
        self.assertEqual(options[0].volume, eur("100.00"))

    def test_the_settlement_window_reaches_this_entry_point_too(self):
        # Outside the window the two rows are two payments, so the volume is
        # double what it is inside it.  Same rows, same everything else.
        rows = mirrored(amount="100.00", debit_day=1, credit_day=8)
        inside = entity_options(rows, currency="USD", settlement_days=10)
        outside = entity_options(rows, currency="USD", settlement_days=3)
        self.assertEqual(
            {o.party.key: o.volume for o in inside}["acme"], usd("100.00"))
        self.assertEqual(
            {o.party.key: o.volume for o in outside}["acme"], usd("200.00"))


# ---------------------------------------------------------------------------
# What a pair says about itself
# ---------------------------------------------------------------------------


def a_pair(**kw) -> MirrorPair:
    """A pair built directly, so its sentence can be read without a sweep."""
    debit_day = kw.pop("debit_day", 1)
    credit_day = kw.pop("credit_day", 1)
    return MirrorPair(
        debit_id=kw.pop("debit_id", ident(701)),
        credit_id=kw.pop("credit_id", ident(702)),
        debit_account=kw.pop("debit_account", ACCOUNT_A),
        credit_account=kw.pop("credit_account", ACCOUNT_B),
        payer=kw.pop("payer", ACME),
        payee=kw.pop("payee", BETA),
        amount=kw.pop("amount", usd("100.00")),
        debit_date=date(2024, 3, debit_day),
        credit_date=date(2024, 3, credit_day),
        proof_class=kw.pop("proof_class", ProofClass.p2),
        **kw,
    )


class MirrorPairDescribeTests(unittest.TestCase):
    """The sentence a pair puts in front of a reader.

    A pair is the one place in this module where two documents are asserted to
    be one payment.  The sentence has to carry the settlement lag and the fact
    that the match may have been a guess, because those are the two things a
    reader would otherwise have to take on trust.
    """

    def test_a_same_day_pair_says_so(self):
        self.assertIn("same day", a_pair(debit_day=1, credit_day=1).describe())

    def test_and_does_not_call_that_zero_days(self):
        self.assertNotIn("0 day", a_pair(debit_day=1, credit_day=1).describe())

    def test_one_day_is_singular(self):
        self.assertIn("(settled in 1 day)",
                      a_pair(debit_day=1, credit_day=2).describe())

    def test_two_days_is_plural(self):
        self.assertIn("(settled in 2 days)",
                      a_pair(debit_day=1, credit_day=3).describe())

    def test_a_credit_posted_first_still_reads_as_one_day(self):
        # `abs` is the reason to look: the gap is -1, and -1 is still singular.
        self.assertIn("(settled in -1 day)",
                      a_pair(debit_day=2, credit_day=1).describe())

    def test_the_money_and_both_parties_are_named(self):
        described = a_pair().describe()
        self.assertIn("100.00 USD", described)
        self.assertIn("Acme LLC -> Beta Inc", described)

    def test_the_date_shown_is_the_debit_date(self):
        # The payer's date is the one a reader is asked to place in a timeline;
        # the credit date is recoverable from the lag.
        self.assertIn("2024-03-01", a_pair(debit_day=1, credit_day=3).describe())

    def test_a_confident_pair_carries_no_ambiguity_tag(self):
        self.assertNotIn("ambiguous", a_pair().describe())

    def test_a_guessed_pair_says_that_it_guessed(self):
        self.assertIn("[pairing was ambiguous]", a_pair(ambiguous=True).describe())

    def test_a_pair_is_confident_unless_told_otherwise(self):
        # The default is load-bearing.  A pair built without the flag asserts
        # the match was forced, not merely chosen from several, and every pair
        # the sweep is sure of is built without touching it.
        self.assertFalse(a_pair().ambiguous)


class EachSideIsNamedByItsOwnBank(unittest.TestCase):
    """A statement names its holder exactly and the far side loosely.

    Four spellings across two keys.  The debit's bank knows its customer as
    "Acme LLC" and writes the far side as "BETA"; the credit's bank knows its
    customer as "Beta Inc" and writes the far side as "ACME".  Both sides of a
    pair are therefore available under two names, and the one to keep is the
    one written by the bank that holds the account -- the other is a narrative
    field typed by someone describing a party they do not bank.

    Every other test in this file uses the same `Party` object on both rows, so
    a mutation that reads either side from the wrong statement would go unseen.
    """

    def rows(self):
        return [
            a_row(
                holder=Party(key="acme", name="Acme LLC"),
                counterparty=Party(key="beta", name="BETA"),
                account=ACCOUNT_A, day=1, transaction_id=ident(310),
                direction=TransactionDirection.debit,
            ),
            a_row(
                holder=Party(key="beta", name="Beta Inc"),
                counterparty=Party(key="acme", name="ACME"),
                account=ACCOUNT_B, day=1, transaction_id=ident(311),
                direction=TransactionDirection.credit,
            ),
        ]

    def test_the_rows_pair(self):
        payments, pairs = collapse_mirrors(self.rows())
        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(payments), 1)

    def test_the_pairs_payer_is_named_by_the_debit(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertEqual(pairs[0].payer.name, "Acme LLC")

    def test_the_pairs_payee_is_named_by_the_credit(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertEqual(pairs[0].payee.name, "Beta Inc")

    def test_the_payments_payer_is_named_by_the_debit(self):
        payments, _ = collapse_mirrors(self.rows())
        self.assertEqual(payments[0].payer.name, "Acme LLC")

    def test_the_payments_payee_is_named_by_the_credit(self):
        payments, _ = collapse_mirrors(self.rows())
        self.assertEqual(payments[0].payee.name, "Beta Inc")

    def test_the_accounts_are_not_swapped(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertEqual(pairs[0].debit_account, ACCOUNT_A)
        self.assertEqual(pairs[0].credit_account, ACCOUNT_B)

    def test_the_ids_are_not_swapped_either(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertEqual(pairs[0].debit_id, ident(310))
        self.assertEqual(pairs[0].credit_id, ident(311))

    def test_the_sentence_uses_the_holders_names_throughout(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertIn("Acme LLC -> Beta Inc", pairs[0].describe())


class TheGroupKeyIsTheWholeRelationship(unittest.TestCase):
    """Two rows pair only if they describe the same payment on both sides.

    The grouping key is payer, payee, currency and amount.  Dropping any one
    of them lets rows from different payments into one bucket, and once they
    are in one bucket the sweep will happily marry them.  Payer, currency and
    amount are covered elsewhere; the payee is covered here, because it takes
    a shape no other test in the file produces -- two rows that agree on the
    payer and disagree on who was paid.
    """

    def test_one_payer_and_two_payees_do_not_share_a_group(self):
        # Acme pays Beta, and Gamma is separately credited by Acme.  Read as
        # payer and payee those are acme->beta and acme->gamma: same payer,
        # same amount, same day, opposite directions, different accounts.
        # Everything a pair needs except that they are not the same payment.
        rows = [
            a_row(holder=ACME, counterparty=BETA, account=ACCOUNT_A, day=1,
                  transaction_id=ident(320),
                  direction=TransactionDirection.debit),
            a_row(holder=GAMMA, counterparty=ACME, account=ACCOUNT_B, day=1,
                  transaction_id=ident(321),
                  direction=TransactionDirection.credit),
        ]
        payments, pairs = collapse_mirrors(rows)
        self.assertEqual(pairs, ())
        self.assertEqual(len(payments), 2)

    def test_and_the_money_is_not_halved_by_a_wrong_marriage(self):
        # Both rows are Acme paying out -- one written from Acme's own statement,
        # one from Gamma's, where a credit names its counterparty as the payer --
        # so the two payments total 200.  Marrying them would report 100, which
        # is the collapse doing the very thing it exists to prevent, only in the
        # understating direction.
        rows = [
            a_row(holder=ACME, counterparty=BETA, account=ACCOUNT_A, day=1,
                  amount="100.00", transaction_id=ident(322),
                  direction=TransactionDirection.debit),
            a_row(holder=GAMMA, counterparty=ACME, account=ACCOUNT_B, day=1,
                  amount="100.00", transaction_id=ident(323),
                  direction=TransactionDirection.credit),
        ]
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("200.00"))
        self.assertEqual(result.outflow.count, 2)


class TheSweepTakesEachDebitOnce(unittest.TestCase):
    """A debit already spent is not available to a second credit.

    Reaching this is harder than it looks.  The retire scan walks `start` past
    debits that are used, so the obvious shape -- one debit and two credits --
    never offers the used debit to the second credit at all.  The only way in
    is a debit that is stepped over for a *different* reason and so is still
    sitting at `start`: here the first debit shares an account with both
    credits and is refused on that ground, which keeps `start` at zero and
    leaves the second debit reachable twice.
    """

    def rows(self):
        return [
            a_row(counterparty=BETA, account=ACCOUNT_A, day=1,
                  transaction_id=ident(601),
                  direction=TransactionDirection.debit),
            a_row(counterparty=BETA, account=ACCOUNT_C, day=1,
                  transaction_id=ident(602),
                  direction=TransactionDirection.debit),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_A, day=1,
                  transaction_id=ident(603),
                  direction=TransactionDirection.credit),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_A, day=1,
                  transaction_id=ident(604),
                  direction=TransactionDirection.credit),
        ]

    def test_only_one_pair_is_made(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertEqual(len(pairs), 1)

    def test_the_second_credit_finds_nothing_and_stays_its_own_payment(self):
        payments, pairs = collapse_mirrors(self.rows())
        self.assertEqual(len(payments), 3)

    def test_no_row_is_spent_in_two_payments(self):
        # The invariant the count above is standing in for.  Spending one debit
        # twice reports the same money leaving twice, which is the defect this
        # whole module exists to prevent, arriving by a different door.
        payments, _ = collapse_mirrors(self.rows())
        spent = [row for payment in payments for row in payment.rows]
        self.assertEqual(len(spent), len(set(spent)))


class TheSweepLeavesNoPairUnmade(unittest.TestCase):
    """Credits are taken earliest first, and the order is not arbitrary.

    Taking the earliest credit first, and giving it the earliest live debit, is
    exchange-optimal: no reordering makes more pairs.  Taking the latest first
    is not, and the cost is silent -- a pair that should have been made is
    missed, the two rows survive as separate payments, and the total for that
    relationship doubles.

    The shape below is the smallest that shows it.  Two debits and two credits
    that interleave: run forwards, both pair; run backwards, the late credit
    takes the late debit, the retire scan then walks `start` past it, and the
    early credit is left with nothing in range.
    """

    def rows(self):
        return [
            a_row(counterparty=BETA, account=ACCOUNT_A, day=1,
                  transaction_id=ident(801),
                  direction=TransactionDirection.debit),
            a_row(counterparty=BETA, account=ACCOUNT_A, day=5,
                  transaction_id=ident(802),
                  direction=TransactionDirection.debit),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_B, day=2,
                  transaction_id=ident(803),
                  direction=TransactionDirection.credit),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_B, day=6,
                  transaction_id=ident(804),
                  direction=TransactionDirection.credit),
        ]

    def test_both_pairs_are_made(self):
        payments, pairs = collapse_mirrors(self.rows(), settlement_days=3)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(len(payments), 2)

    def test_and_so_the_relationship_is_not_doubled(self):
        result = analyse(self.rows(), Perspective.of("acme"), currency="USD")
        self.assertEqual(result.outflow.amount, usd("200.00"))
        self.assertEqual(result.outflow.count, 2)

    def test_the_earliest_credit_takes_the_earliest_debit(self):
        _, pairs = collapse_mirrors(self.rows(), settlement_days=3)
        self.assertEqual(
            [(p.debit_id, p.credit_id) for p in pairs],
            [(ident(801), ident(803)), (ident(802), ident(804))],
        )


class TheRowOrderIsTotal(unittest.TestCase):
    """Rows tied on date are ordered by id, so the sweep does not depend on input.

    `TheCollapseIsDeterministic` shuffles a population and compares whole
    results, but every group there has at most one debit per date, so the
    tiebreak never decides anything.  Here two debits share a date and only one
    can be taken: without the tiebreak the answer is whichever the caller
    happened to list first, which is not an answer an exhibit can carry.
    """

    def rows(self):
        return [
            a_row(counterparty=BETA, account=ACCOUNT_A, day=1,
                  transaction_id=ident(902),
                  direction=TransactionDirection.debit),
            a_row(counterparty=BETA, account=ACCOUNT_A, day=1,
                  transaction_id=ident(901),
                  direction=TransactionDirection.debit),
            a_row(holder=BETA, counterparty=ACME, account=ACCOUNT_B, day=1,
                  transaction_id=ident(903),
                  direction=TransactionDirection.credit),
        ]

    def test_the_lower_id_is_taken_whatever_the_input_order(self):
        for order in itertools.permutations(self.rows()):
            with self.subTest(order=[str(r.transaction_id)[-4:] for r in order]):
                _, pairs = collapse_mirrors(list(order))
                self.assertEqual(len(pairs), 1)
                self.assertEqual(pairs[0].debit_id, ident(901))

    def test_the_choice_was_a_guess_and_says_so(self):
        _, pairs = collapse_mirrors(self.rows())
        self.assertTrue(pairs[0].ambiguous)


class TheUncollapsedPathIsAlsoOrdered(unittest.TestCase):
    """`collapse=False` is a different function and gets the same guarantees."""

    def test_payments_come_out_in_date_order(self):
        rows = [a_row(day=5, transaction_id=ident(1001)),
                a_row(day=1, transaction_id=ident(1002))]
        payments = flow._payments_only(rows)
        self.assertEqual([m.ordering_date for m in payments],
                         [date(2024, 3, 1), date(2024, 3, 5)])

    def test_a_tie_on_date_is_broken_by_transaction_id(self):
        rows = [a_row(day=1, transaction_id=ident(1004)),
                a_row(day=1, transaction_id=ident(1003))]
        payments = flow._payments_only(rows)
        self.assertEqual([m.rows[0] for m in payments],
                         [ident(1003), ident(1004)])

    def test_analyse_reports_the_same_order_on_that_path(self):
        rows = [a_row(day=5, transaction_id=ident(1005)),
                a_row(day=1, transaction_id=ident(1006))]
        result = analyse(rows, Perspective.of("acme"), currency="USD",
                         collapse=False)
        self.assertEqual(result.outflow.count, 2)


class TheChartClosureIsChecked(unittest.TestCase):
    """The bars must add up to the card they were drawn from.

    `__post_init__` compares *amounts* -- the counterparty breakdown plus the
    residue against the card.  `divergent_chart` decides whether to draw the
    residue bar on the *count*.  A residue holding money under a zero count
    falls between the two: admitted at construction, then left off the chart.

    That shape should not come out of `analyse`, and the point of the closure
    check is that "should not" is not the same as "cannot".  A chart whose bars
    quietly total less than the headline above them is exactly the kind of
    defect this module was written to stop, and it is worth an assertion rather
    than an assumption.
    """

    def a_residue_with_money_but_no_count(self):
        return Figure(
            amount=usd("10.00"),
            count=0,
            composition=ClassComposition(counts={}, amounts={}),
        )

    def test_such_a_flow_is_admitted_at_construction(self):
        # Stated so that the test below is understood as reaching the closure
        # check rather than tripping the constructor on the way to it.
        money = a_flow(
            inflow=figure("15.00", 1, p2=(1, "5.00")),
            unattributed_inflow=self.a_residue_with_money_but_no_count(),
            counterparties=(a_counterparty(BETA, inflow="5.00", in_count=1),),
        )
        self.assertEqual(money.inflow.amount, usd("15.00"))

    def test_an_inflow_chart_that_does_not_close_is_refused(self):
        money = a_flow(
            inflow=figure("15.00", 1, p2=(1, "5.00")),
            unattributed_inflow=self.a_residue_with_money_but_no_count(),
            counterparties=(a_counterparty(BETA, inflow="5.00", in_count=1),),
        )
        with self.assertRaises(FlowInvariantError) as caught:
            money.divergent_chart()
        self.assertIn("chart inflow", str(caught.exception))

    def test_an_outflow_chart_that_does_not_close_is_refused(self):
        money = a_flow(
            outflow=figure("15.00", 1, p2=(1, "5.00")),
            unattributed_outflow=self.a_residue_with_money_but_no_count(),
            counterparties=(a_counterparty(BETA, outflow="5.00", out_count=1),),
        )
        with self.assertRaises(FlowInvariantError) as caught:
            money.divergent_chart()
        self.assertIn("chart outflow", str(caught.exception))

    def test_a_counted_residue_gets_its_bar_and_the_chart_closes(self):
        money = a_flow(
            inflow=figure("15.00", 2, p2=(2, "15.00")),
            unattributed_inflow=figure("10.00", 1, p2=(1, "10.00")),
            counterparties=(a_counterparty(BETA, inflow="5.00", in_count=1),),
        )
        chart = money.divergent_chart()
        self.assertEqual(chart.inflow_total, usd("15.00"))


class TheCounterpartyLabelIsTheFirstOneOffered(unittest.TestCase):
    """One key, two spellings: the breakdown settles on one and stays there.

    The existing label tests pit a name against silence, which a rule of "the
    last name wins" satisfies just as well as "the first name wins".  Two
    different names is the case that separates them.  Neither spelling is more
    correct; what matters is that the same rows always produce the same label,
    because a heading that changes with the order documents were loaded is not
    something a reader can rely on.
    """

    def breakdown_for(self, rows):
        result = analyse(rows, Perspective.of("acme"), currency="USD")
        return {c.party.key: c for c in result.counterparties}

    def test_a_second_spelling_does_not_displace_the_first(self):
        rows = [
            a_row(counterparty=Party(key="beta", name="Beta Inc"), day=1,
                  transaction_id=ident(410)),
            a_row(counterparty=Party(key="beta", name="BETA INCORPORATED"),
                  day=2, transaction_id=ident(411)),
        ]
        self.assertEqual(self.breakdown_for(rows)["beta"].party.name, "Beta Inc")

    def test_and_a_name_still_fills_in_for_an_earlier_silence(self):
        rows = [
            a_row(counterparty=Party(key="beta"), day=1,
                  transaction_id=ident(412)),
            a_row(counterparty=Party(key="beta", name="Beta Inc"), day=2,
                  transaction_id=ident(413)),
        ]
        self.assertEqual(self.breakdown_for(rows)["beta"].party.name, "Beta Inc")

    def test_the_key_is_the_identity_so_both_rows_are_one_heading(self):
        rows = [
            a_row(counterparty=Party(key="beta", name="Beta Inc"), day=1,
                  amount="10.00", transaction_id=ident(414)),
            a_row(counterparty=Party(key="beta", name="BETA INCORPORATED"),
                  day=2, amount="10.00", transaction_id=ident(415)),
        ]
        breakdown = self.breakdown_for(rows)
        self.assertEqual(len(breakdown), 1)
        self.assertEqual(breakdown["beta"].outflow.amount, usd("20.00"))


# ---------------------------------------------------------------------------
# The package surface
# ---------------------------------------------------------------------------


def _public_definitions(module) -> set[str]:
    """The names a module defines at its top level, without the private ones.

    Read from the source rather than from ``vars()`` because a module's
    namespace also holds everything it imported, and a re-export is not a
    definition.  Constants carry no ``__module__`` to filter on, so there is no
    way to tell ``DEFAULT_CHART_LIMIT`` -- defined here -- from
    ``DEFAULT_TOTAL_CLASSES`` -- imported from ``proof_class`` -- except by
    looking at where the assignment is written.
    """
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {n for n in names if not n.startswith("_")}


#: Every name this module contributes to ``services.financial``.  Held here
#: rather than derived, so that dropping an export from ``__init__`` is a test
#: failure and not a silent narrowing of the public surface.
EXPORTED = (
    "DEFAULT_CHART_LIMIT",
    "DEFAULT_SETTLEMENT_DAYS",
    "NOTE_MIRRORS_AMBIGUOUS",
    "NOTE_MIRRORS_COLLAPSED",
    "NOTE_MIRRORS_NOT_COLLAPSED",
    "NOTE_MIXED_COMPOSITION",
    "NOTE_NAMES_COLLIDE",
    "NOTE_NOT_BILATERAL",
    "NOTE_SET_ASIDE_ON_CLASS",
    "NOTE_SETTLEMENT_LAG",
    "NOTE_UNATTRIBUTED_INFLOW",
    "NOTE_UNATTRIBUTED_OUTFLOW",
    "NOTE_UNPLACEABLE",
    "NOTE_UNRECONCILED",
    "ChartBar",
    "ClassComposition",
    "CounterpartyFlow",
    "DivergentChart",
    "DuplicateRowError",
    "EntityOption",
    "Figure",
    "FlowCurrencyError",
    "FlowError",
    "FlowInvariantError",
    "FlowRow",
    "MirrorPair",
    "MoneyFlow",
    "Party",
    "PartyAttributionError",
    "Payment",
    "Perspective",
    "PerspectiveError",
    "Placement",
    "SetAsideReason",
    "analyse",
    "attribute",
    "collapse_mirrors",
    "entity_options",
    "place",
)


class ThePackageExportsTheModule(unittest.TestCase):
    def setUp(self):
        import services.financial as package

        self.package = package

    def test_every_name_is_importable_from_the_package(self):
        missing = [n for n in EXPORTED if not hasattr(self.package, n)]
        self.assertEqual(missing, [])

    def test_every_name_is_the_same_object_as_the_modules(self):
        different = [
            n for n in EXPORTED
            if getattr(self.package, n) is not getattr(flow, n)
        ]
        self.assertEqual(different, [])

    def test_every_name_is_declared_in_all(self):
        undeclared = [n for n in EXPORTED if n not in self.package.__all__]
        self.assertEqual(undeclared, [])

    def test_all_has_no_duplicates(self):
        self.assertEqual(len(self.package.__all__), len(set(self.package.__all__)))

    def test_the_module_defines_no_public_name_the_package_withholds(self):
        # No module in this subsystem declares `__all__`, so the surface is
        # whatever a module defines at the top level without a leading
        # underscore.  Adding a public name to `flow.py` and forgetting to
        # export it should fail here rather than be found by a caller who
        # cannot reach it.
        self.assertEqual(sorted(_public_definitions(flow)), sorted(EXPORTED))

    def test_nothing_in_all_is_absent_from_the_package(self):
        absent = [n for n in self.package.__all__ if not hasattr(self.package, n)]
        self.assertEqual(absent, [])


class TheNamingCollisionIsResolvedNotHidden(unittest.TestCase):
    """`tracing` already uses `Movement` and `AttributionError` for its own things.

    ``tracing.Movement`` is an admitted ledger row -- what this module calls a
    :class:`FlowRow` -- and not a payment, so the two names had to differ.  If
    either module is ever renamed to close the gap these tests fail, which is
    the point: the collision should be resolved deliberately or not at all.
    """

    def setUp(self):
        from services.financial import tracing

        self.tracing = tracing

    def test_payment_is_not_tracings_movement(self):
        self.assertIsNot(Payment, self.tracing.Movement)

    def test_party_attribution_error_is_not_tracings(self):
        self.assertIsNot(PartyAttributionError, self.tracing.AttributionError)

    def test_the_package_exports_both_error_types_under_distinct_names(self):
        import services.financial as package

        self.assertIsNot(package.PartyAttributionError, package.AttributionError)

    def test_the_two_modules_define_no_public_name_in_common(self):
        # Both are re-exported flat from `services.financial`, so an overlap
        # would not be a collision the package could report -- one would simply
        # shadow the other at import time, and the loser would be whichever
        # line came second.
        overlap = _public_definitions(flow) & _public_definitions(self.tracing)
        self.assertEqual(overlap, set())
