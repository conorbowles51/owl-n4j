"""Money flow from a chosen point of view.

This is the quantitative money-flow surface: select a *perspective set* of
entities, and every transaction touching any of
them is classified as **inflow** (external money arriving), **outflow** (money
leaving for an external party) or **internal** (payment inside the set).  The
divergent counterparty chart that falls out of it answers "who is this party
net-funding, and by how much", which is a different -- often better -- question
than "what is connected to what", and one that little else on the market asks.

The model is V1's.  Its implementation there
(``MoneyFlowSection.jsx``, 440 lines) was one of the genuinely good things the
old interface had and one of the things Loupe lost entirely.  The analytical
core is carried over intact:

* scope is an **OR across both sides** -- a row is in scope if *either* party
  is selected -- which is what makes it different in kind from the From/To
  cross-filter, an AND across two orthogonal dimensions;
* internal payment is **counted once and kept out of the counterparty chart**,
  because an intra-set transfer is the same money seen twice and adding it to
  both sides would inflate the set's apparent volume and leave the net figure
  meaning nothing;
* counterparties are merged **bidirectionally**, so a party that both sends and
  receives is one bar with two halves rather than two unrelated rows;
* and outflow is carried as a negative quantity against a zero reference line,
  which is the whole point of a divergent chart and is analytical content
  rather than styling, so it belongs here and not in the renderer.

What is not carried over
------------------------

V1 computed all of this in floating point, off ``parseFloat(t.amount) || 0``,
and rounded at the end.  Where that ended up is worth stating exactly:
``toFloat()`` on a
malformed amount yields NaN, ``sum(abs(NaN))`` is NaN, NaN renders as $0.00 and
``CASE WHEN NaN >= 0`` is false so the outflow branch silently skipped the row.
The live symptom was **Total Volume $0.00 alongside Outflows of $284M on the
same screen**.  Every figure here is :class:`~services.financial.money.Money`
over integer minor units, and a row this module cannot read is refused or
reported, never coerced to zero and counted as a real transaction that happened
to be worth nothing.

V1 also identified entities as ``key || name`` -- falling back to the display
string when no key was present.  Two distinct parties who share a name merge
into one, and one party whose name is spelled two ways splits into two, and
neither shows up as anything but a wrong number.  Here identity is a
:class:`Party` key and the name is a label that is never load-bearing.  Deciding
that two names are one party is entity resolution and happens
upstream; :func:`attribute` is the boundary, and the type makes it impossible to
build a flow row without having decided.

The same payment, twice
-----------------------

This is what changes when the model is pointed at a reconciled ledger rather
than at V1's flat transaction list, and it is the reason this module is a port
and not a copy.

V1's data had one row per payment.  A ledger built from bank statements has one
row per *statement line*, so when both sides of a relationship are in evidence
the same payment appears **twice** -- a debit in the payer's account and a
credit in the payee's.  Both rows derive the same payer and the same payee, so
both land in the same bucket, and the perspective set's outflow is exactly
double.  Silently.  The better the case's document coverage, the wronger the
number gets, which is the worst possible failure direction.

So mirrored rows are collapsed to one **payment** before anything is counted.
The rule is deliberately narrow: two rows pair only if they resolve to the same
payer and the same payee, carry the same amount in the same currency, sit in
*different* accounts, and are held one by the payer and one by the payee -- one
row from each side of the payment.  Two rows in the *same* account are not a
mirror pair, they are a duplicate, and :mod:`services.financial.duplicates` is
where that lives.

Two genuine payments of equal size between the same parties on the same day are
a real thing and must not be collapsed into one.  They are not, because pairing
is a matching and not a lookup: two payments produce two debits and two credits,
which pair into two payments.  Where a debit could pair with more than one
credit the choice is made deterministically -- nearest date, then lowest
transaction id -- and the choice is safe to make because every candidate in the
group is interchangeable by construction: it changes which id is recorded as
collapsed, never the count and never the total.

A collapsed pair is also the strongest confirmation this system can produce for
a payment, since both parties' banks recorded it independently, so it is
reported rather than quietly applied, and the surviving payment takes the
stronger of the two proof classes.

Everything set aside says so
----------------------------

A total has to state which proof classes it covers, so every
figure here carries its :class:`ClassComposition` and no figure is a bare
number.  Rows in scope that fall outside the counted classes are reported as
set aside with the reason, because "Net +$40,000" over a set whose volume is
half unadjudicated is a lie by omission even though every digit in it is right.

The counterparty chart has the same problem in a different place, and V1 had it:
a row whose external side has no name counts toward the Inflow card but adds no
bar, so the bars sum to less than the card and nobody is told.  Here that
residue is named -- :attr:`MoneyFlow.unattributed_inflow` and
:attr:`~MoneyFlow.unattributed_outflow` -- and the identity *chart + residue ==
card* is checked on the way out.  If it ever fails this module raises rather
than returning a screen that disagrees with itself.

Nothing here is a finding
-------------------------

This is a descriptive surface.  Unlike :mod:`services.financial.correlation`,
which gates hard because it asserts an absence, flow describes what is present
and so it computes over an incomplete record rather than refusing to.  But an
incomplete record makes a *net* figure mean less than it looks like it means, so
unreconciled rows, uncovered periods and set-aside classes are all disclosed in
:attr:`MoneyFlow.notes`.  The number is offered with its qualifications
attached, which is the only form in which it is worth having.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence

from postgres.models.enums import ProofClass, TransactionDirection
from services.financial.correlation import LedgerEntry
from services.financial.linkage import normalise_name
from services.financial.money import Money, get_currency
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES, LEDGER_CLASSES


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FlowError(Exception):
    """Base class for every refusal in this module."""


class PerspectiveError(FlowError):
    """The point of view is unusable."""


class FlowCurrencyError(FlowError):
    """Rows in more than one currency, or in one the caller did not state."""


class DuplicateRowError(FlowError):
    """The same transaction id was handed in twice."""


class PartyAttributionError(FlowError):
    """A row was attributed to parties it cannot carry."""


class FlowInvariantError(FlowError):
    """A total and its own breakdown disagree.  Never expected; never hidden."""


# ---------------------------------------------------------------------------
# Proof class strength
# ---------------------------------------------------------------------------


#: Strongest first.  Written out rather than derived from the enum's string
#: values, so that renaming a member cannot silently reorder it, and so that
#: "stronger" has one definition in this module that can be pointed at.
_CLASS_ORDER: tuple[ProofClass, ...] = (
    ProofClass.p0,
    ProofClass.p1,
    ProofClass.p2,
    ProofClass.p3,
    ProofClass.p4,
)

_CLASS_RANK: Mapping[ProofClass, int] = {
    cls: index for index, cls in enumerate(_CLASS_ORDER)
}


def _stronger(left: ProofClass, right: ProofClass) -> ProofClass:
    """The better-evidenced of two classes."""
    return left if _CLASS_RANK[left] <= _CLASS_RANK[right] else right


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Party:
    """One side of a payment, identified by key and labelled by name.

    The split is the whole point.  ``key`` is what equality, grouping and the
    perspective set are computed on; ``name`` is what a person reads and is
    never load-bearing.  V1 conflated them and got both of the errors that
    follow from it -- two parties sharing a display name silently merged, one
    party spelled two ways silently split -- and neither is visible in the
    output as anything except a number that is wrong.
    """

    key: str
    name: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise PartyAttributionError(
                "a party needs a stable key; a display name is a label and "
                "using it as an identity merges everyone who shares it"
            )

    @property
    def label(self) -> str:
        """What to show.  Falls back to the key, and says so by doing nothing."""
        return self.name if self.name else self.key


def _party_label(party: Optional[Party]) -> str:
    return party.label if party is not None else "an unnamed party"


# ---------------------------------------------------------------------------
# Rows, once their parties are known
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlowRow:
    """One ledger row with both of its parties resolved.

    Built through :func:`attribute` from a
    :class:`~services.financial.correlation.LedgerEntry`, which is the
    subsystem's single reduced ledger row.  The extra thing this type carries is
    identity: the entry holds *names*, because correlation compares the strings
    it is handed, and this module cannot, because it groups by party and a group
    keyed on a string is the V1 bug.

    ``holder`` is the party whose account the row sits in, and it is what makes
    direction meaningful: the same payment is a debit in the payer's statement
    and a credit in the payee's, so which way the money went has no answer until
    you know whose account you are reading.  Either side may be ``None``.  A row
    with no holder is not useless -- if the counterparty is known, the direction
    still says which way the money moved relative to them -- but a row with
    neither is unplaceable, and is reported as such rather than dropped.
    """

    transaction_id: uuid.UUID
    account_id: uuid.UUID
    ordering_date: date
    amount: Money
    direction: TransactionDirection
    proof_class: ProofClass
    holder: Optional[Party] = None
    counterparty: Optional[Party] = None
    reconciled: bool = True
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if self.proof_class not in LEDGER_CLASSES:
            raise PartyAttributionError(
                f"{self.proof_class.value} cannot appear in the ledger, so it "
                "cannot appear in a flow figure; an assertion about a payment "
                "is not a payment"
            )
        if self.amount.is_negative:
            raise PartyAttributionError(
                "a ledger amount is a positive magnitude with the sign carried "
                f"in direction; got {self.amount.format()}"
            )
        if (
            self.holder is not None
            and self.counterparty is not None
            and self.holder.key == self.counterparty.key
        ):
            raise PartyAttributionError(
                f"a row cannot be its own counterparty ({self.holder.key}); a "
                "payment from a party to itself is a bookkeeping entry, and "
                "counting it as flow would move money that never moved"
            )

    # -- Derived sides ------------------------------------------------------
    #
    # Everything downstream reasons in payer/payee, because that is the shape
    # V1's model is expressed in and the shape a person thinks in.  The ledger
    # stores holder + direction, which is the shape a bank statement is in.
    # This is the whole of the translation between them.

    @property
    def payer(self) -> Optional[Party]:
        """Whose money left.  ``None`` where that side is unresolved."""
        if self.direction is TransactionDirection.debit:
            return self.holder
        return self.counterparty

    @property
    def payee(self) -> Optional[Party]:
        """Whose money arrived.  ``None`` where that side is unresolved."""
        if self.direction is TransactionDirection.debit:
            return self.counterparty
        return self.holder

    @property
    def is_placeable(self) -> bool:
        """Whether either side is known well enough to test against a set."""
        return self.holder is not None or self.counterparty is not None

    def describe(self) -> str:
        return (
            f"{self.amount.format()} from {_party_label(self.payer)} to "
            f"{_party_label(self.payee)} on {self.ordering_date.isoformat()}"
        )


def attribute(
    entry: LedgerEntry,
    *,
    holder: Optional[Party] = None,
    counterparty: Optional[Party] = None,
) -> FlowRow:
    """Resolve a ledger entry's two sides into identities.

    This function is the entity-resolution boundary made explicit.  Resolution
    belongs upstream of analysis, and the alternative to a boundary is
    what V1 did: resolve implicitly, per row, by falling back to the display
    name whenever a key was missing.  Requiring the caller to say who these
    parties *are* is a small cost paid once, against a class of error that is
    invisible in the output.

    Passing ``None`` for a side is a legitimate answer and means the side was
    not resolved -- which is different from, and must not be written as, a party
    named after whatever string happened to be in the extraction.
    """
    if not isinstance(entry, LedgerEntry):
        raise PartyAttributionError("attribute() takes a LedgerEntry")
    return FlowRow(
        transaction_id=entry.transaction_id,
        account_id=entry.account_id,
        ordering_date=entry.ordering_date,
        amount=entry.amount,
        direction=entry.direction,
        proof_class=entry.proof_class,
        holder=holder,
        counterparty=counterparty,
        reconciled=entry.reconciled,
        description=entry.description,
    )


# ---------------------------------------------------------------------------
# The point of view
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Perspective:
    """The entities the question is being asked from.

    A row is in scope if *any* member appears on *either* side of it.  That OR
    is the model: it is what lets a set of related companies be looked at as one
    economic unit, with transfers between them recognised as internal rather
    than counted as real flow.  The From/To cross-filter that sits beside this
    in the interface is an AND across two orthogonal dimensions and answers a
    different question; V1's source drew the contrast explicitly and it is worth
    keeping drawn.
    """

    keys: frozenset[str]

    def __post_init__(self) -> None:
        if not self.keys:
            raise PerspectiveError(
                "a perspective needs at least one entity; a flow computed from "
                "nowhere would report zeros, and a zero that means 'nobody "
                "asked' looks exactly like a zero that means 'no money moved'"
            )
        for key in self.keys:
            if not key or not key.strip():
                raise PerspectiveError("a perspective key cannot be blank")

    @classmethod
    def of(cls, *keys: str) -> "Perspective":
        return cls(frozenset(keys))

    def holds(self, party: Optional[Party]) -> bool:
        return party is not None and party.key in self.keys

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.keys)


class Placement(str, Enum):
    """Where a payment sits relative to the perspective set."""

    #: External party -> selected.  Money arriving from outside the set.
    inflow = "inflow"
    #: Selected -> external party.  Money leaving the set.
    outflow = "outflow"
    #: Selected -> selected.  Counted once, and kept out of the chart.
    internal = "internal"
    #: Neither side is in the set.  Not an error; just not this question.
    out_of_scope = "out_of_scope"
    #: Neither side resolved to a party at all, so it cannot be tested.
    unplaceable = "unplaceable"


class SetAsideReason(str, Enum):
    """Why an in-scope payment did not reach a figure."""

    #: Its proof class is outside the counted set.
    class_not_counted = "class_not_counted"
    #: Neither party resolved, so the perspective cannot be applied to it.
    unplaceable = "unplaceable"


# ---------------------------------------------------------------------------
# Figures that state what they are made of
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassComposition:
    """The proof classes behind a figure, with counts and subtotals.

    A total has to state its class composition, and the reason it
    has to be carried on the figure rather than computed beside it is that the
    two get separated: a number travels into an exhibit, a caption does not
    always travel with it.
    """

    counts: Mapping[ProofClass, int]
    amounts: Mapping[ProofClass, Money]

    @property
    def classes(self) -> tuple[ProofClass, ...]:
        """The classes present, strongest first."""
        return tuple(c for c in _CLASS_ORDER if self.counts.get(c))

    @property
    def weakest(self) -> Optional[ProofClass]:
        """The weakest class in the figure, which is what qualifies it."""
        present = self.classes
        return present[-1] if present else None

    @property
    def is_uniform(self) -> bool:
        return len(self.classes) <= 1

    def describe(self) -> str:
        present = self.classes
        if not present:
            return "no rows"
        return "; ".join(
            f"{c.value} {self.counts[c]} "
            f"row{'' if self.counts[c] == 1 else 's'} "
            f"{self.amounts[c].format()}"
            for c in present
        )


@dataclass(frozen=True)
class Figure:
    """A money total that carries its own provenance.

    There is no constructor here that produces a total without a composition,
    which is the point: the discipline is only worth anything if it cannot be
    skipped by a caller in a hurry.
    """

    amount: Money
    count: int
    composition: ClassComposition

    @property
    def is_zero(self) -> bool:
        return self.count == 0

    def describe(self) -> str:
        return f"{self.amount.format()} over {self.count} " + (
            "payment" if self.count == 1 else "payments"
        )


class _Accumulator:
    """Mutable builder for a :class:`Figure`.  Never escapes this module."""

    __slots__ = ("currency", "total", "count", "_counts", "_amounts")

    def __init__(self, currency: str) -> None:
        self.currency = currency
        self.total = Money.zero(currency)
        self.count = 0
        self._counts: dict[ProofClass, int] = defaultdict(int)
        self._amounts: dict[ProofClass, Money] = {}

    def add(self, amount: Money, proof_class: ProofClass) -> None:
        self.total = self.total + amount
        self.count += 1
        self._counts[proof_class] += 1
        running = self._amounts.get(proof_class)
        self._amounts[proof_class] = amount if running is None else running + amount

    def freeze(self) -> Figure:
        return Figure(
            amount=self.total,
            count=self.count,
            composition=ClassComposition(
                counts=dict(self._counts),
                amounts=dict(self._amounts),
            ),
        )


# ---------------------------------------------------------------------------
# Payments: one economic event, however many rows recorded it
# ---------------------------------------------------------------------------


#: How far apart the two sides of one payment may be dated and still be the
#: same payment.  A wire posts to both accounts the same day; ACH takes one to
#: three business days; a cheque can take longer.  Three days covers the common
#: instruments without reaching far enough to swallow a second, genuinely
#: separate payment of the identical amount to the identical party.
#:
#: The parameter is exposed on every entry point because the right value is a
#: property of the instruments in the case, not of this module, and because a
#: reader who disagrees with the number should be able to change it and see what
#: moves rather than argue with a constant.
DEFAULT_SETTLEMENT_DAYS = 3


@dataclass(frozen=True)
class Payment:
    """One payment of money, after mirrored rows have been reconciled to it.

    The distinction between this and :class:`FlowRow` is the whole reason this
    module is a port of V1's model rather than a copy of it.  V1 read a table
    with one row per payment.  A ledger assembled from bank statements has one
    row per *statement line*, so a payment between two parties whose statements
    are both in evidence appears twice -- as a debit in the payer's account and
    a credit in the payee's.  Both rows resolve to the same payer and the same
    payee, so both land in the same bucket, and the figure comes out at exactly
    twice the money that moved.

    Silently, and worse the better the case is documented: the more complete the
    collection, the larger the error.  That is the wrong direction for an error
    to run in a system whose output is meant to be put in front of a court.
    """

    payer: Optional[Party]
    payee: Optional[Party]
    amount: Money
    ordering_date: date
    proof_class: ProofClass
    #: Every contributing transaction id.  Debit first where there are two, so
    #: the tuple reads in the direction the money went.
    rows: tuple[uuid.UUID, ...]
    accounts: frozenset[uuid.UUID]
    reconciled: bool
    description: Optional[str] = None

    @property
    def bilateral(self) -> bool:
        """True where both parties' own records evidence this payment.

        This is the strongest confirmation the system can produce without
        leaving the ledger: two institutions recorded the same transfer
        independently and the records agree on party, amount and currency.  It
        is reported rather than merely used, because a reader is entitled to
        know which figures rest on one bank's word and which on two.
        """
        return len(self.rows) > 1

    def describe(self) -> str:
        return (
            f"{self.amount.format()} from {_party_label(self.payer)} to "
            f"{_party_label(self.payee)} on {self.ordering_date.isoformat()}"
            + (" (both sides in evidence)" if self.bilateral else "")
        )


def _payment_from_row(row: FlowRow) -> Payment:
    """The one-sided case: a single statement line, taken at its own word."""
    return Payment(
        payer=row.payer,
        payee=row.payee,
        amount=row.amount,
        ordering_date=row.ordering_date,
        proof_class=row.proof_class,
        rows=(row.transaction_id,),
        accounts=frozenset({row.account_id}),
        reconciled=row.reconciled,
        description=row.description,
    )


def _payment_from_pair(debit: FlowRow, credit: FlowRow) -> Payment:
    """Collapse a mirrored debit and credit into the single payment they are.

    Three of the fields are choices rather than reads, and each is made the
    conservative way:

    *Parties.*  Both rows name both sides, but not necessarily identically: a
    payer's statement labels the payee however that payer's bank chose to, and
    the payee's own statement labels itself.  The key is the same either way --
    that is what made them a pair -- so only the label is in question, and the
    label taken is the one each party's own bank gave it.

    *Date.*  The earlier of the two, which is when the money left.  The later
    date is when it landed, and the gap between them is settlement, recorded on
    the :class:`MirrorPair` so it stays visible.

    *Proof class.*  The stronger of the two.  Not an averaging and not the
    weaker: the class describes how well the payment is evidenced, and a
    payment evidenced by a reconciling statement *and* a second record is not
    made worse by the second record existing.
    """
    payer = debit.holder
    payee = credit.holder
    assert payer is not None and payee is not None  # guaranteed by the pairing
    return Payment(
        payer=payer,
        payee=payee,
        amount=debit.amount,
        ordering_date=min(debit.ordering_date, credit.ordering_date),
        proof_class=_stronger(debit.proof_class, credit.proof_class),
        rows=(debit.transaction_id, credit.transaction_id),
        accounts=frozenset({debit.account_id, credit.account_id}),
        reconciled=debit.reconciled and credit.reconciled,
        description=debit.description or credit.description,
    )


@dataclass(frozen=True)
class MirrorPair:
    """A record that two rows were treated as one payment, and on what grounds.

    Collapsing is reported, never merely applied.  A figure that is half what a
    naive count would give needs to be able to say why, row by row, and a reader
    who disagrees with a particular pairing needs to be able to find it.
    """

    debit_id: uuid.UUID
    credit_id: uuid.UUID
    debit_account: uuid.UUID
    credit_account: uuid.UUID
    payer: Party
    payee: Party
    amount: Money
    debit_date: date
    credit_date: date
    proof_class: ProofClass
    #: True where the debit could have been paired with more than one credit.
    #: The choice made is deterministic and does not change the count or the
    #: total -- every candidate in the group carries the same parties, amount
    #: and currency, so any of them yields the same arithmetic -- but it does
    #: change which transaction ids are recorded against each other, and a
    #: reader tracing one payment is entitled to know the identification was a
    #: selection rather than a deduction.
    ambiguous: bool = False

    @property
    def settlement_days(self) -> int:
        """Days between the money leaving and the money landing."""
        return (self.credit_date - self.debit_date).days

    def describe(self) -> str:
        gap = self.settlement_days
        settled = "same day" if gap == 0 else f"settled in {gap} day{'' if abs(gap) == 1 else 's'}"
        return (
            f"{self.amount.format()} {self.payer.label} -> {self.payee.label} "
            f"on {self.debit_date.isoformat()} ({settled})"
            + (" [pairing was ambiguous]" if self.ambiguous else "")
        )


def _row_sort_key(row: FlowRow) -> tuple:
    return (row.ordering_date, str(row.transaction_id))


def _payment_sort_key(payment: Payment) -> tuple:
    return (payment.ordering_date, str(payment.rows[0]))


def collapse_mirrors(
    rows: Iterable[FlowRow],
    *,
    settlement_days: int = DEFAULT_SETTLEMENT_DAYS,
) -> tuple[tuple[Payment, ...], tuple[MirrorPair, ...]]:
    """Reduce statement lines to the payments they record.

    Two rows are the same payment only when all of the following hold:

    * the same payer key and the same payee key;
    * the same amount, to the minor unit, in the same currency;
    * one row is a debit and the other a credit -- that is, one sits in the
      payer's account and one in the payee's;
    * they sit in *different* accounts;
    * their dates are within ``settlement_days`` of each other.

    Each condition is doing work.  Dropping the different-account requirement
    would let this collapse a genuine in-matter duplicate, which is a different
    defect with a different remedy and belongs to ``duplicates.py``.  Dropping
    the date window would let a January payment and a June payment of the same
    round amount to the same supplier collapse into one, understating the total
    -- and an understatement is no better than the overstatement this function
    exists to prevent, only quieter.

    *Why this is a matching and not a lookup.*  Two genuine payments of the same
    amount between the same parties on the same day produce two debits and two
    credits, and must yield two payments, not one.  Pairing them off as a
    bipartite matching gives that for free; a dictionary keyed on the tuple
    would not.  Where a credit can be answered by more than one debit the choice
    is made deterministically -- earliest unpaired debit still inside the window,
    ties by transaction id -- and the pair is flagged ``ambiguous``.  The choice
    is safe because every candidate carries identical parties, amount and
    currency by construction, so it moves which ids are recorded against each
    other and never the number of payments or the total.

    The sweep processes credits in date order and takes the earliest still-live
    debit, which is the exchange-optimal greedy for this shape of problem and so
    leaves no pair unmade that could have been made -- provided the two sides of
    a payment really are in different accounts, which they are whenever account
    ownership is well formed, since an account has one holder.

    :returns: the payments, and the pairs that were collapsed to make them.
    :raises DuplicateRowError: if a transaction id appears twice.
    :raises FlowError: if ``settlement_days`` is negative.
    """
    if settlement_days < 0:
        raise FlowError(
            f"settlement_days must not be negative; got {settlement_days}"
        )
    window = timedelta(days=settlement_days)

    materialised = list(rows)
    seen: set[uuid.UUID] = set()
    for row in materialised:
        if row.transaction_id in seen:
            raise DuplicateRowError(
                f"transaction {row.transaction_id} was supplied twice; a row "
                "counted twice is money that did not move, and this module "
                "cannot tell an accidental repeat from a genuine second row"
            )
        seen.add(row.transaction_id)

    # Currency is part of the grouping key rather than a precondition, so that
    # cross-currency pairing is impossible by construction.  A caller totalling
    # a mixed-currency ledger is stopped later, in analyse(), where a total is
    # actually being formed; collapsing is a per-payment operation and has no
    # reason to refuse the mixture.
    groups: dict[tuple, tuple[list[FlowRow], list[FlowRow]]] = {}
    for row in materialised:
        if row.holder is None or row.counterparty is None:
            continue
        payer, payee = row.payer, row.payee
        if payer is None or payee is None:  # pragma: no cover - defensive
            continue
        key = (payer.key, payee.key, row.amount.currency, row.amount.minor_units)
        bucket = groups.get(key)
        if bucket is None:
            bucket = ([], [])
            groups[key] = bucket
        if row.direction is TransactionDirection.debit:
            bucket[0].append(row)
        else:
            bucket[1].append(row)

    pairs: list[MirrorPair] = []
    consumed: set[uuid.UUID] = set()

    for key in sorted(groups):
        debits, credits = groups[key]
        if not debits or not credits:
            continue
        debits.sort(key=_row_sort_key)
        credits.sort(key=_row_sort_key)
        used = [False] * len(debits)
        start = 0
        for credit in credits:
            lower = credit.ordering_date - window
            upper = credit.ordering_date + window
            # Debits older than the window can never be reached by this credit
            # or by any later one, because credits arrive in date order and the
            # lower bound only rises.  Retiring them keeps the inner scan short.
            while start < len(debits) and (
                used[start] or debits[start].ordering_date < lower
            ):
                start += 1
            chosen: Optional[int] = None
            eligible = 0
            for index in range(start, len(debits)):
                if used[index]:
                    continue
                candidate = debits[index]
                if candidate.ordering_date > upper:
                    break
                if candidate.account_id == credit.account_id:
                    # Same account: this is a repeated row, not the other side
                    # of a payment.  Leave it for duplicate detection.
                    continue
                eligible += 1
                if chosen is None:
                    chosen = index
                else:
                    break  # one more is all "ambiguous" needs to know
            if chosen is None:
                continue
            used[chosen] = True
            debit = debits[chosen]
            consumed.add(debit.transaction_id)
            consumed.add(credit.transaction_id)
            assert debit.holder is not None and credit.holder is not None
            pairs.append(
                MirrorPair(
                    debit_id=debit.transaction_id,
                    credit_id=credit.transaction_id,
                    debit_account=debit.account_id,
                    credit_account=credit.account_id,
                    payer=debit.holder,
                    payee=credit.holder,
                    amount=debit.amount,
                    debit_date=debit.ordering_date,
                    credit_date=credit.ordering_date,
                    proof_class=_stronger(debit.proof_class, credit.proof_class),
                    ambiguous=eligible > 1,
                )
            )

    by_id = {row.transaction_id: row for row in materialised}
    payments = [
        _payment_from_pair(by_id[pair.debit_id], by_id[pair.credit_id])
        for pair in pairs
    ]
    payments.extend(
        _payment_from_row(row)
        for row in materialised
        if row.transaction_id not in consumed
    )
    payments.sort(key=_payment_sort_key)
    pairs.sort(key=lambda p: (p.debit_date, str(p.debit_id)))
    return tuple(payments), tuple(pairs)


def _payments_only(rows: Iterable[FlowRow]) -> tuple[Payment, ...]:
    """Every row as its own payment.  The ``collapse=False`` path."""
    materialised = list(rows)
    seen: set[uuid.UUID] = set()
    for row in materialised:
        if row.transaction_id in seen:
            raise DuplicateRowError(
                f"transaction {row.transaction_id} was supplied twice"
            )
        seen.add(row.transaction_id)
    payments = [_payment_from_row(row) for row in materialised]
    payments.sort(key=_payment_sort_key)
    return tuple(payments)


# ---------------------------------------------------------------------------
# Placing a payment against the perspective
# ---------------------------------------------------------------------------


def place(payment: Payment, perspective: Perspective) -> Placement:
    """Where a payment sits relative to the selected entities.

    The order of the tests is the model.  Both sides in the set is *internal*
    and is tested first, because a transfer between two selected companies is
    not money entering or leaving the group and counting it as either would
    inflate the picture in whichever direction the test happened to reach first.
    V1 had this ordering and it is worth saying why rather than merely copying
    it.

    A payment with one side in the set and the other unresolved is placed on
    the side that is known.  That is the only available answer, and it is not a
    safe one: money that left a selected account for a party nobody has
    identified may have gone to another selected account, in which case it was
    internal and the outflow figure is overstated.  Nothing here can tell.  The
    result carries a note saying so whenever it applies.
    """
    payer_in = perspective.holds(payment.payer)
    payee_in = perspective.holds(payment.payee)
    if payer_in and payee_in:
        return Placement.internal
    if payer_in:
        return Placement.outflow
    if payee_in:
        return Placement.inflow
    if payment.payer is None and payment.payee is None:
        return Placement.unplaceable
    return Placement.out_of_scope


# ---------------------------------------------------------------------------
# Counterparties
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CounterpartyFlow:
    """One external party, with both directions of its relationship to the set.

    Merged bidirectionally: a party that both pays and is paid is one entry with
    two halves, not two entries.  That is the point of the view -- a supplier
    who is also a customer, or a party moving money back and forth, is a single
    relationship and reads as one, with the shape of the relationship visible in
    the balance between the halves.
    """

    party: Party
    inflow: Figure
    outflow: Figure

    @property
    def total(self) -> Money:
        """Gross traffic in both directions.  The sort key, and the bar length."""
        return self.inflow.amount + self.outflow.amount

    @property
    def net(self) -> Money:
        """Positive where the set received more than it sent."""
        return self.inflow.amount - self.outflow.amount

    @property
    def count(self) -> int:
        return self.inflow.count + self.outflow.count

    @property
    def is_bidirectional(self) -> bool:
        return self.inflow.count > 0 and self.outflow.count > 0

    def describe(self) -> str:
        return (
            f"{self.party.label}: in {self.inflow.amount.format()}, "
            f"out {self.outflow.amount.format()}, net {self.net.format()}"
        )


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


NOTE_MIRRORS_COLLAPSED = "rows recording both sides of one payment were counted once"
NOTE_MIRRORS_AMBIGUOUS = "a mirrored pairing had more than one candidate"
NOTE_MIRRORS_NOT_COLLAPSED = "mirrored rows were not collapsed, so a payment held on both sides is counted twice"
NOTE_UNATTRIBUTED_OUTFLOW = "money left the set for parties that were not identified, so some of it may have stayed inside"
NOTE_UNATTRIBUTED_INFLOW = "money arrived from parties that were not identified"
NOTE_UNPLACEABLE = "payments with neither side identified could not be placed"
NOTE_SET_ASIDE_ON_CLASS = "payments in scope were set aside as their proof class is not counted"
NOTE_UNRECONCILED = "some counted payments come from statements that do not reconcile"
NOTE_MIXED_COMPOSITION = "figures rest on more than one proof class"
NOTE_NAMES_COLLIDE = "distinct parties carry the same display name"
NOTE_SETTLEMENT_LAG = "the two sides of a payment were dated differently"
NOTE_NOT_BILATERAL = "no payment is evidenced by both parties' own records"


def _combine_figures(figures: Iterable[Figure], currency: str) -> Figure:
    """Add figures together, carrying the composition through the sum.

    Used for the aggregate bars.  Written as a fold over compositions rather
    than a re-scan of the underlying payments so that an aggregate cannot end
    up describing a different population from the bars it replaced.
    """
    total = Money.zero(currency)
    count = 0
    counts: dict[ProofClass, int] = defaultdict(int)
    amounts: dict[ProofClass, Money] = {}
    for figure in figures:
        total = total + figure.amount
        count += figure.count
        for proof_class, number in figure.composition.counts.items():
            counts[proof_class] += number
        for proof_class, amount in figure.composition.amounts.items():
            running = amounts.get(proof_class)
            amounts[proof_class] = amount if running is None else running + amount
    return Figure(
        amount=total,
        count=count,
        composition=ClassComposition(counts=dict(counts), amounts=dict(amounts)),
    )


# ---------------------------------------------------------------------------
# The divergent counterparty chart
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChartBar:
    """One row of the divergent chart: a counterparty, or an aggregate of them."""

    #: ``None`` on an aggregate bar, which stands for several parties or none.
    key: Optional[str]
    label: str
    inflow: Figure
    #: Held as a positive magnitude.  :attr:`plotted_outflow` is what the chart
    #: draws; keeping both means the sign convention is stated once, here,
    #: rather than assumed by every consumer.
    outflow: Figure
    is_aggregate: bool = False

    @property
    def plotted_outflow(self) -> Money:
        """Outflow as the chart carries it: negative, against a zero baseline.

        The sign is analytical, not decorative.  A divergent bar chart says
        something a pair of stacked bars does not -- that the two directions are
        opposed, and that a party's position is the balance between them -- and
        the place to decide that is here, where the composition is known, rather
        than in a component that has only numbers.
        """
        return -self.outflow.amount

    @property
    def total(self) -> Money:
        """Bar length: gross traffic, both directions."""
        return self.inflow.amount + self.outflow.amount

    @property
    def net(self) -> Money:
        return self.inflow.amount - self.outflow.amount


@dataclass(frozen=True)
class DivergentChart:
    """The chart, with every figure in it accounted for.

    V1's chart took the top twelve counterparties and drew them, and the cards
    above it totalled every in-scope row including the ones with no named
    counterparty at all.  The two therefore disagreed, by an amount nothing on
    the screen reported, and a reader adding up the bars to check the card would
    find a shortfall and no explanation for it.  This chart closes: the bars sum
    to the cards exactly, because the parties past the limit and the payments
    with no identified counterparty each get a bar of their own.
    """

    bars: tuple[ChartBar, ...]
    limit: int
    #: The reference line the bars diverge from.  Zero, in the flow's currency.
    baseline: Money
    #: How many named counterparties exist, and how many got a bar of their own.
    named_counterparties: int
    charted_counterparties: int

    @property
    def truncated(self) -> bool:
        return self.charted_counterparties < self.named_counterparties

    @property
    def inflow_total(self) -> Money:
        return _sum_money((bar.inflow.amount for bar in self.bars), self.baseline)

    @property
    def outflow_total(self) -> Money:
        return _sum_money((bar.outflow.amount for bar in self.bars), self.baseline)

    @property
    def extent(self) -> Money:
        """The largest single-direction magnitude, for scaling the axis."""
        largest = self.baseline
        for bar in self.bars:
            for amount in (bar.inflow.amount, bar.outflow.amount):
                if amount > largest:
                    largest = amount
        return largest


def _sum_money(amounts: Iterable[Money], zero: Money) -> Money:
    total = zero
    for amount in amounts:
        total = total + amount
    return total


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


#: How many counterparties the chart draws individually before aggregating the
#: rest.  V1's number, kept: twelve bars is about as many as a divergent chart
#: reads at, and the thirteenth is aggregated rather than dropped.
DEFAULT_CHART_LIMIT = 12


@dataclass(frozen=True)
class MoneyFlow:
    """Money in, money out, and internal transfers, from a chosen point of view.

    Every figure on this object is a :class:`Figure` and so states the proof
    classes behind it.  The three cards -- inflow, outflow,
    internal -- partition the in-scope, counted payments exactly once each, and
    :meth:`divergent_chart` decomposes inflow and outflow into bars that sum
    back to them.  What did not reach a card is not discarded: it is in
    :attr:`set_aside`, :attr:`out_of_scope`, or one of the unattributed figures,
    and the arithmetic can be closed by a reader who wants to.
    """

    perspective: Perspective
    currency: str
    included_classes: frozenset[ProofClass]
    settlement_days: int
    collapsed: bool

    #: External -> selected.
    inflow: Figure
    #: Selected -> external.
    outflow: Figure
    #: Selected -> selected, counted once.  Excluded from the chart, because a
    #: transfer inside the group has no external counterparty to draw.
    internal: Figure

    #: The parts of inflow and outflow whose external side was never resolved.
    #: Contained in the figures above, not additional to them.
    unattributed_inflow: Figure
    unattributed_outflow: Figure

    #: Counted payments touching neither selected entity.  Context, not a
    #: component: it says how much of the ledger this point of view ignores.
    out_of_scope: Figure
    #: Counted payments resting on a statement that does not reconcile.  A
    #: subset of the cards, reported so a reader can discount it.
    unreconciled: Figure

    counterparties: tuple[CounterpartyFlow, ...]
    mirrors: tuple[MirrorPair, ...]
    set_aside: Mapping[SetAsideReason, Figure]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        # The counterparty breakdown is built alongside the cards rather than
        # derived from them, so the two can in principle drift.  They must not,
        # and a screen that disagrees with itself is worse than an error, so
        # this is checked on construction rather than trusted.
        zero = Money.zero(self.currency)
        charted_in = _sum_money((c.inflow.amount for c in self.counterparties), zero)
        charted_out = _sum_money((c.outflow.amount for c in self.counterparties), zero)
        if charted_in + self.unattributed_inflow.amount != self.inflow.amount:
            raise FlowInvariantError(
                "inflow does not equal its counterparty breakdown plus the "
                f"unattributed remainder: {self.inflow.amount.format()} against "
                f"{(charted_in + self.unattributed_inflow.amount).format()}"
            )
        if charted_out + self.unattributed_outflow.amount != self.outflow.amount:
            raise FlowInvariantError(
                "outflow does not equal its counterparty breakdown plus the "
                f"unattributed remainder: {self.outflow.amount.format()} against "
                f"{(charted_out + self.unattributed_outflow.amount).format()}"
            )

    # -- Headline figures ---------------------------------------------------

    @property
    def net(self) -> Money:
        """Inflow less outflow.  Negative where the set is a net payer."""
        return self.inflow.amount - self.outflow.amount

    @property
    def total_volume(self) -> Money:
        """Everything counted in scope, internal transfers included once."""
        return self.inflow.amount + self.outflow.amount + self.internal.amount

    @property
    def payment_count(self) -> int:
        return self.inflow.count + self.outflow.count + self.internal.count

    @property
    def has_internal(self) -> bool:
        return self.internal.count > 0

    @property
    def bilateral_count(self) -> int:
        """Payments evidenced by both parties' own records."""
        return len(self.mirrors)

    @property
    def composition(self) -> ClassComposition:
        """The proof classes behind the in-scope figures taken together."""
        return _combine_figures(
            (self.inflow, self.outflow, self.internal), self.currency
        ).composition

    # -- The chart ----------------------------------------------------------

    def divergent_chart(self, limit: int = DEFAULT_CHART_LIMIT) -> DivergentChart:
        """Top ``limit`` counterparties, with the remainder kept on the chart.

        :raises FlowError: if ``limit`` is not positive.
        :raises FlowInvariantError: if the bars do not sum to the cards.
        """
        if limit < 1:
            raise FlowError(
                f"a chart needs at least one bar; got limit {limit}"
            )
        zero = Money.zero(self.currency)
        drawn = self.counterparties[:limit]
        rest = self.counterparties[limit:]

        bars: list[ChartBar] = [
            ChartBar(
                key=c.party.key,
                label=c.party.label,
                inflow=c.inflow,
                outflow=c.outflow,
            )
            for c in drawn
        ]
        if rest:
            bars.append(
                ChartBar(
                    key=None,
                    label=(
                        f"{len(rest)} further counterpart"
                        f"{'y' if len(rest) == 1 else 'ies'}"
                    ),
                    inflow=_combine_figures((c.inflow for c in rest), self.currency),
                    outflow=_combine_figures((c.outflow for c in rest), self.currency),
                    is_aggregate=True,
                )
            )
        if self.unattributed_inflow.count or self.unattributed_outflow.count:
            bars.append(
                ChartBar(
                    key=None,
                    label="counterparty not identified",
                    inflow=self.unattributed_inflow,
                    outflow=self.unattributed_outflow,
                    is_aggregate=True,
                )
            )

        chart = DivergentChart(
            bars=tuple(bars),
            limit=limit,
            baseline=zero,
            named_counterparties=len(self.counterparties),
            charted_counterparties=len(drawn),
        )
        if chart.inflow_total != self.inflow.amount:
            raise FlowInvariantError(
                "chart inflow does not sum to the inflow card: "
                f"{chart.inflow_total.format()} against {self.inflow.amount.format()}"
            )
        if chart.outflow_total != self.outflow.amount:
            raise FlowInvariantError(
                "chart outflow does not sum to the outflow card: "
                f"{chart.outflow_total.format()} against {self.outflow.amount.format()}"
            )
        return chart

    # -- Reading ------------------------------------------------------------

    def describe(self) -> str:
        parts = [
            f"in {self.inflow.amount.format()} ({self.inflow.count})",
            f"out {self.outflow.amount.format()} ({self.outflow.count})",
            f"net {self.net.format()}",
        ]
        if self.has_internal:
            parts.append(
                f"internal {self.internal.amount.format()} ({self.internal.count})"
            )
        parts.append(f"classes {self.composition.describe()}")
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# Preconditions shared by the entry points
# ---------------------------------------------------------------------------


def _check_currency(currency: str) -> str:
    try:
        get_currency(currency)
    except Exception as exc:  # UnknownCurrencyError, and anything it grows into
        raise FlowCurrencyError(
            f"{currency!r} is not a currency this system knows, so no total can "
            "be formed in it"
        ) from exc
    return currency


def _check_included(included: frozenset[ProofClass]) -> frozenset[ProofClass]:
    if not included:
        raise FlowError(
            "at least one proof class must be counted; a flow that counts "
            "nothing reports zeros, and a zero meaning 'excluded by the filter' "
            "is indistinguishable on the screen from a zero meaning 'no money "
            "moved'"
        )
    return frozenset(included)


def _require_single_currency(rows: Sequence[FlowRow], currency: str) -> None:
    """Refuse a mixed-currency population rather than filtering it down.

    Dropping the rows in other currencies would produce a figure that looks
    complete and is not, and there is no exchange rate this module is entitled
    to apply.  A caller with a multi-currency ledger runs this once per
    currency, which is the only honest way to present it.
    """
    others = sorted({row.amount.currency for row in rows} - {currency})
    if others:
        raise FlowCurrencyError(
            f"rows in {', '.join(others)} were supplied for a flow stated in "
            f"{currency}; money in different currencies cannot be added, and "
            "silently dropping the others would produce a total that looks "
            "complete and is not"
        )


def _to_payments(
    rows: Sequence[FlowRow],
    *,
    collapse: bool,
    settlement_days: int,
) -> tuple[tuple[Payment, ...], tuple[MirrorPair, ...]]:
    if collapse:
        return collapse_mirrors(rows, settlement_days=settlement_days)
    return _payments_only(rows), ()


def _colliding_names(payments: Iterable[Payment]) -> bool:
    """Whether two distinct party keys carry names that normalise alike.

    Not an error and not acted on -- two real companies can share a trading
    name, and this module has no standing to merge them -- but it is the visible
    surface of the failure that matters most here, which is entity resolution
    having split one party in two or being about to be asked to.
    """
    by_name: dict[str, set[str]] = defaultdict(set)
    for payment in payments:
        for party in (payment.payer, payment.payee):
            if party is None or not party.name:
                continue
            normalised = normalise_name(party.name)
            if normalised:
                by_name[normalised].add(party.key)
    return any(len(keys) > 1 for keys in by_name.values())


class _CounterpartyBuilder:
    """Accumulates one external party's two directions.  Never escapes."""

    __slots__ = ("party", "inflow", "outflow")

    def __init__(self, party: Party, currency: str) -> None:
        self.party = party
        self.inflow = _Accumulator(currency)
        self.outflow = _Accumulator(currency)

    def observe(self, party: Party) -> None:
        """Keep the best label seen for this key.

        Keys are what identity is; names are labels, and a party can appear with
        a name on one payment and without on another depending on which bank
        wrote the line.  Taking the first non-empty name, in the payments'
        deterministic order, is a display decision and nothing downstream turns
        on it.
        """
        if not self.party.name and party.name:
            self.party = party

    def freeze(self) -> CounterpartyFlow:
        return CounterpartyFlow(
            party=self.party,
            inflow=self.inflow.freeze(),
            outflow=self.outflow.freeze(),
        )


def analyse(
    rows: Iterable[FlowRow],
    perspective: Perspective,
    *,
    currency: str,
    included: frozenset[ProofClass] = DEFAULT_TOTAL_CLASSES,
    settlement_days: int = DEFAULT_SETTLEMENT_DAYS,
    collapse: bool = True,
) -> MoneyFlow:
    """Compute money flow for a set of entities over a reconciled ledger.

    The sequence matters and is not the obvious one.  Payments are *placed*
    against the perspective before the proof-class filter is applied, so that a
    p3 payment between the selected entities and an outside party is reported
    as in scope and not counted, rather than merely absent.  Doing it the other
    way round is one line shorter and loses the distinction between money the
    view excluded and money that was never there.

    ``collapse`` defaults to true because the default has to be the correct
    number.  Turning it off is supported -- a reader who wants to see the raw
    statement lines is entitled to -- and the result then carries a note saying
    the figures double-count any payment held on both sides.

    Unlike :mod:`services.financial.correlation`, which refuses to speak where
    its evidence is incomplete, this module computes over whatever is held and
    discloses what is missing.  The difference is in what is being said: a
    correlation asserts an *absence*, which is only true if the record is
    complete, whereas a flow describes a *presence*, which stays true as far as
    it goes provided it says how far that is.  That is what :attr:`MoneyFlow.notes`
    is for, and it is not decoration.

    :raises FlowCurrencyError: on an unknown or mixed currency.
    :raises DuplicateRowError: if a transaction id appears twice.
    :raises FlowError: if no proof class is counted.
    """
    currency = _check_currency(currency)
    included = _check_included(included)
    if not isinstance(perspective, Perspective):
        raise PerspectiveError("analyse() takes a Perspective")

    materialised = list(rows)
    _require_single_currency(materialised, currency)
    payments, mirrors = _to_payments(
        materialised, collapse=collapse, settlement_days=settlement_days
    )

    inflow = _Accumulator(currency)
    outflow = _Accumulator(currency)
    internal = _Accumulator(currency)
    out_of_scope = _Accumulator(currency)
    unreconciled = _Accumulator(currency)
    unattributed_in = _Accumulator(currency)
    unattributed_out = _Accumulator(currency)
    set_aside_class = _Accumulator(currency)
    set_aside_unplaceable = _Accumulator(currency)
    counterparties: dict[str, _CounterpartyBuilder] = {}

    def counterparty_for(party: Party) -> _CounterpartyBuilder:
        builder = counterparties.get(party.key)
        if builder is None:
            builder = _CounterpartyBuilder(party, currency)
            counterparties[party.key] = builder
        else:
            builder.observe(party)
        return builder

    for payment in payments:
        placement = place(payment, perspective)

        if placement is Placement.unplaceable:
            # No class filter here.  A payment whose parties are both unknown
            # is missing something the filter cannot substitute for, and
            # reporting it under a proof-class heading would suggest the class
            # was the reason it was excluded.
            set_aside_unplaceable.add(payment.amount, payment.proof_class)
            continue

        counted = payment.proof_class in included

        if placement is Placement.out_of_scope:
            if counted:
                out_of_scope.add(payment.amount, payment.proof_class)
            continue

        if not counted:
            set_aside_class.add(payment.amount, payment.proof_class)
            continue

        if placement is Placement.internal:
            internal.add(payment.amount, payment.proof_class)
        elif placement is Placement.inflow:
            inflow.add(payment.amount, payment.proof_class)
            payer = payment.payer
            if payer is None:
                unattributed_in.add(payment.amount, payment.proof_class)
            else:
                counterparty_for(payer).inflow.add(
                    payment.amount, payment.proof_class
                )
        else:  # Placement.outflow
            outflow.add(payment.amount, payment.proof_class)
            payee = payment.payee
            if payee is None:
                unattributed_out.add(payment.amount, payment.proof_class)
            else:
                counterparty_for(payee).outflow.add(
                    payment.amount, payment.proof_class
                )

        if not payment.reconciled:
            unreconciled.add(payment.amount, payment.proof_class)

    ordered = sorted(
        (builder.freeze() for builder in counterparties.values()),
        key=lambda c: (-c.total.minor_units, c.party.key),
    )

    set_aside: dict[SetAsideReason, Figure] = {
        SetAsideReason.class_not_counted: set_aside_class.freeze(),
        SetAsideReason.unplaceable: set_aside_unplaceable.freeze(),
    }

    notes: list[str] = []
    if collapse:
        if mirrors:
            notes.append(NOTE_MIRRORS_COLLAPSED)
            if any(pair.ambiguous for pair in mirrors):
                notes.append(NOTE_MIRRORS_AMBIGUOUS)
            if any(pair.settlement_days != 0 for pair in mirrors):
                notes.append(NOTE_SETTLEMENT_LAG)
        elif payments:
            notes.append(NOTE_NOT_BILATERAL)
    else:
        notes.append(NOTE_MIRRORS_NOT_COLLAPSED)
    if unattributed_out.count:
        notes.append(NOTE_UNATTRIBUTED_OUTFLOW)
    if unattributed_in.count:
        notes.append(NOTE_UNATTRIBUTED_INFLOW)
    if set_aside_unplaceable.count:
        notes.append(NOTE_UNPLACEABLE)
    if set_aside_class.count:
        notes.append(NOTE_SET_ASIDE_ON_CLASS)
    if unreconciled.count:
        notes.append(NOTE_UNRECONCILED)
    if _colliding_names(payments):
        notes.append(NOTE_NAMES_COLLIDE)

    inflow_figure = inflow.freeze()
    outflow_figure = outflow.freeze()
    internal_figure = internal.freeze()
    if not _combine_figures(
        (inflow_figure, outflow_figure, internal_figure), currency
    ).composition.is_uniform:
        notes.append(NOTE_MIXED_COMPOSITION)

    return MoneyFlow(
        perspective=perspective,
        currency=currency,
        included_classes=included,
        settlement_days=settlement_days,
        collapsed=collapse,
        inflow=inflow_figure,
        outflow=outflow_figure,
        internal=internal_figure,
        unattributed_inflow=unattributed_in.freeze(),
        unattributed_outflow=unattributed_out.freeze(),
        out_of_scope=out_of_scope.freeze(),
        unreconciled=unreconciled.freeze(),
        counterparties=tuple(ordered),
        mirrors=mirrors,
        set_aside=set_aside,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# The picker
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityOption:
    """One entity a perspective could be built from, with its traffic.

    Ported from V1's ``moneyFlowEntityOptions``, with one substantive change:
    the counts and the volume are computed over *payments*, not rows.  Under
    the old shape an entity whose own statements and its counterparties'
    statements were both held showed roughly twice the volume of an entity
    documented from one side only -- which put the best-evidenced parties at the
    top of the picker for the wrong reason and made the list a ranking of
    collection completeness rather than of money.
    """

    party: Party
    #: Payments this entity paid out on, and received on.  They cannot both
    #: count the same payment: a payment from a party to itself is refused at
    #: the row.
    as_payer_count: int
    as_payee_count: int
    volume: Money
    composition: ClassComposition

    @property
    def payment_count(self) -> int:
        return self.as_payer_count + self.as_payee_count

    def describe(self) -> str:
        return (
            f"{self.party.label}: {self.volume.format()} over "
            f"{self.payment_count} payment"
            f"{'' if self.payment_count == 1 else 's'} "
            f"({self.as_payer_count} out, {self.as_payee_count} in)"
        )


def entity_options(
    rows: Iterable[FlowRow],
    *,
    currency: str,
    included: frozenset[ProofClass] = DEFAULT_TOTAL_CLASSES,
    settlement_days: int = DEFAULT_SETTLEMENT_DAYS,
    collapse: bool = True,
    always_include: frozenset[str] = frozenset(),
) -> tuple[EntityOption, ...]:
    """Every identified party in the ledger, ranked by the money it touched.

    ``always_include`` guarantees an entry for the keys given even where nothing
    counted for them -- V1 kept the currently selected entities in the list for
    exactly this reason, so that selecting an entity with no counted traffic did
    not remove the control needed to deselect it again.  Such an entry is
    present with zeros rather than fabricated, and reads as what it is.

    :raises FlowCurrencyError: on an unknown or mixed currency.
    :raises DuplicateRowError: if a transaction id appears twice.
    """
    currency = _check_currency(currency)
    included = _check_included(included)
    materialised = list(rows)
    _require_single_currency(materialised, currency)
    payments, _ = _to_payments(
        materialised, collapse=collapse, settlement_days=settlement_days
    )

    parties: dict[str, Party] = {}
    payer_counts: dict[str, int] = defaultdict(int)
    payee_counts: dict[str, int] = defaultdict(int)
    volumes: dict[str, _Accumulator] = {}

    def note(party: Party) -> _Accumulator:
        known = parties.get(party.key)
        if known is None or (not known.name and party.name):
            parties[party.key] = party
        accumulator = volumes.get(party.key)
        if accumulator is None:
            accumulator = _Accumulator(currency)
            volumes[party.key] = accumulator
        return accumulator

    for payment in payments:
        if payment.proof_class not in included:
            continue
        if payment.payer is not None:
            note(payment.payer).add(payment.amount, payment.proof_class)
            payer_counts[payment.payer.key] += 1
        if payment.payee is not None:
            note(payment.payee).add(payment.amount, payment.proof_class)
            payee_counts[payment.payee.key] += 1

    for key in always_include:
        if key not in parties:
            parties[key] = Party(key=key)
            volumes[key] = _Accumulator(currency)

    options = []
    for key, party in parties.items():
        figure = volumes[key].freeze()
        options.append(
            EntityOption(
                party=party,
                as_payer_count=payer_counts.get(key, 0),
                as_payee_count=payee_counts.get(key, 0),
                volume=figure.amount,
                composition=figure.composition,
            )
        )
    options.sort(key=lambda o: (-o.volume.minor_units, o.party.key))
    return tuple(options)
