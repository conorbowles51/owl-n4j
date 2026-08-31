"""Tracing value through a commingled account, by a named doctrine.

When $50,000 of traceable funds enters an account already holding $200,000 and
$60,000 leaves, nothing about the world determines what left.  Money is
fungible; the question has no factual answer.  Courts do not find one, they
apply a rule -- and which rule applies depends on the jurisdiction and the
cause of action.

So a tracing result is not a fact.  It is a fact plus a rule.  A system that
reports "$50,000 flowed from A to C" without naming the rule has made a legal
choice on the investigator's behalf and made it invisibly, which is
indefensible under cross-examination in about one question.  This module
therefore has no default doctrine.  :func:`trace` requires one by name, and
:func:`compare_doctrines` runs all of them so the choice can be shown to have
been made knowingly and its consequence quantified -- which is the
reliable-application showing FRE 702(d) demands.

Showing the alternatives is not a hedge.  It is the most defensible thing the
system can do.

What this module will not do
----------------------------

It will not say that funds were stolen, misappropriated, or fraudulently
obtained.  AICPA SSFS No. 1 prohibits a member from opining on whether fraud
occurred, and the vocabulary here is built to make that opinion inexpressible:
a deposit is *attributed* to a *claim* on a stated *basis*, and the basis is
recorded rather than evaluated.  Who is entitled to what is for the trier of
fact.

It will not guess at an order it was not given.  FIFO and LIFO answers turn on
the order of movements within a day, and where the evidence does not fix that
order the result says so rather than quietly adopting whichever order the rows
arrived in.

It will not trace into an overdraft.  Once a balance goes negative the money
paid out is the bank's, not the claimant's, and the traceable fund is
exhausted; *Bishopsgate Investment Management Ltd v Homan* [1995] Ch 211
refuses the step.  Later deposits do not revive what an overdraft consumed
unless someone intended them to, and intention is not a thing this module can
see.

The doctrines
-------------

**Lowest intermediate balance rule.**  Traceable funds are presumed to remain,
but only up to the lowest balance the account reached after the deposit.  Two
rules compose to make it: a withdrawal is presumed to spend the account
holder's own money first (*Re Hallett's Estate* (1880) 13 Ch D 696), and once
the balance has fallen below the traceable sum, later deposits do not replenish
it (*Roscoe (James) (Bolton) Ltd v Winder* [1915] 1 Ch 62).  The most commonly
applied rule in US and Commonwealth restitution and trust cases; *Easy Loan
Corp v Wiseman*, 2017 ABCA 58, is a useful modern statement.

**First in, first out.**  *Devaynes v Noble* (1816) 35 ER 781, the rule in
*Clayton's Case*.  Mechanically simple, frequently criticised as arbitrary,
still applied in some jurisdictions and contexts.

**Last in, first out.**  Used by the US government in some cryptocurrency
forfeiture contexts.

**Pro rata.**  Each withdrawal draws rateably from everything then in the
account, so every claimant shares proportionately in what remains and in what
was spent.  Restatement (Third) of Restitution and Unjust Enrichment §§55-61
addresses tracing into commingled funds and the proportionate approach.  This
is the rolling charge: the proportions are recomputed at each withdrawal rather
than struck once at the end, because striking them once would let a deposit
made after a withdrawal bear part of that withdrawal.

**Direct tracing.**  Where the records permit an actual one-to-one match -- a
sum in on Tuesday, the same sum out on Wednesday, nothing else moving -- no
presumption is needed.  Implemented as a matcher that refuses ambiguity rather
than resolving it: where two candidate deposits could equally answer to a
withdrawal, this doctrine declines to say and reports the withdrawal as
unmatched.  A direct trace that guessed would be the presumptions with the
labelling removed.

Sub-rules the doctrines do not settle
-------------------------------------

With more than one claim in the account, LIBR fixes how much survives but not
whose.  Allocating a shortfall among competing claimants is a further question
courts have answered differently, and this module answers it rateably and
*says so*: any result whose numbers depended on that sub-rule carries
:data:`NOTE_SHORTFALL_SHARED` in its notes.  A caveat that only appears when it
bit is worth more than one printed always.

Everything is exact
-------------------

Amounts are :class:`~services.financial.money.Money`, which is an integer count
of minor units.  Pro rata shares are allocated with
:meth:`~services.financial.money.Money.allocate`, which distributes by largest
remainder and therefore loses nothing: the parts sum back to the whole.  A
split that drops a penny is a split that will not reconcile, and a trace that
does not reconcile is not evidence of anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Mapping, Optional, Sequence

from postgres.models.enums import ProofClass, TransactionDirection
from services.financial.money import Money, CurrencyMismatchError
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TracingError(Exception):
    """Base class for every refusal in this module."""


class DoctrineError(TracingError):
    """The doctrine asked for is not one this module implements.

    Deliberately an error rather than a fallback.  A tracing engine that
    quietly substituted a doctrine for the one it was asked for would produce
    exactly the invisible legal choice this module exists to prevent.
    """


class AttributionError(TracingError):
    """An attribution does not describe a deposit this account received."""


# There is deliberately no ordering error.  Where the records do not fix the
# order of movements within a day, the trace still runs and reports
# :data:`NOTE_ORDER_UNEVIDENCED`.  The alternatives have to be *shown*, and
# refusing outright would suppress the very comparison that tells
# the reader the answer is order-dependent.  LIBR and pro rata are unaffected
# by intraday order in any case, so a refusal would also withhold two results
# that are not in doubt.


# ---------------------------------------------------------------------------
# Doctrines
# ---------------------------------------------------------------------------


class Doctrine(str, Enum):
    """The rule applied to decide what left a commingled account.

    A parameter, never a default.  The member values are stable strings
    because they are written into exhibits and must mean the same thing in
    next year's report as in this one.
    """

    #: Traceable funds survive only to the lowest balance reached after their
    #: deposit; the holder's own money is spent first and later deposits do
    #: not replenish what was lost.
    lowest_intermediate_balance = "lowest_intermediate_balance"
    #: The rule in *Clayton's Case*: first money in is first money out.
    first_in_first_out = "first_in_first_out"
    #: Last money in is first money out.
    last_in_first_out = "last_in_first_out"
    #: Every withdrawal draws rateably from everything then in the account.
    pro_rata = "pro_rata"
    #: One-to-one matching where the records permit it, and silence where they
    #: do not.
    direct = "direct"


#: Every doctrine, in the order a report should present them.  LIBR and pro
#: rata lead because they are the most commonly applied; direct
#: tracing is last because it is not a presumption at all and usually answers
#: for only part of the account.
DOCTRINE_ORDER: tuple[Doctrine, ...] = (
    Doctrine.lowest_intermediate_balance,
    Doctrine.pro_rata,
    Doctrine.first_in_first_out,
    Doctrine.last_in_first_out,
    Doctrine.direct,
)

#: The authority each doctrine rests on, for the exhibit that has to cite it.
#: A trace whose doctrine cannot be named is not a trace anyone can use.
DOCTRINE_AUTHORITY: Mapping[Doctrine, str] = {
    Doctrine.lowest_intermediate_balance: (
        "Re Hallett's Estate (1880) 13 Ch D 696; Roscoe (James) (Bolton) Ltd v "
        "Winder [1915] 1 Ch 62; Easy Loan Corp v Wiseman, 2017 ABCA 58"
    ),
    Doctrine.first_in_first_out: "Devaynes v Noble (1816) 35 ER 781 (Clayton's Case)",
    Doctrine.last_in_first_out: (
        "No general common-law authority; used by the US government in some "
        "cryptocurrency forfeiture contexts"
    ),
    Doctrine.pro_rata: (
        "Restatement (Third) of Restitution and Unjust Enrichment §§55-61"
    ),
    Doctrine.direct: (
        "No presumption applied; specific identification on the records"
    ),
}


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

#: Emitted when a shortfall had to be divided between competing claims.  The
#: doctrine fixes how much survives; it does not fix whose, and this module
#: divides rateably.  Stated because a reader is entitled to know that a
#: further choice was made underneath the one they asked for.
NOTE_SHORTFALL_SHARED = "shortfall_shared_rateably_between_claims"

#: Emitted when the balance went negative.  Nothing is traceable through an
#: overdraft: the money paid out was the bank's.
NOTE_OVERDRAWN = "balance_went_negative_traceable_fund_exhausted"

#: Emitted when two movements on one day could not be ordered on the evidence,
#: and the order was settled by an arbitrary tiebreak.  FIFO and LIFO can turn
#: on exactly this, so a result carrying it is a result whose doctrine may be
#: answering a question the records do not decide.
NOTE_ORDER_UNEVIDENCED = "intraday_order_not_evidenced"

#: Emitted when a withdrawal drew on funds present before the first attributed
#: deposit.  Those funds are outside every claim, so the amount is reported as
#: drawn from the opening balance rather than assigned to anyone.
NOTE_DREW_ON_OPENING = "withdrawal_drew_on_opening_balance"

#: Emitted by :attr:`Doctrine.direct` when a withdrawal had more than one
#: candidate deposit and the doctrine therefore declined to match it.
NOTE_AMBIGUOUS_MATCH = "direct_match_ambiguous_and_refused"

#: Emitted by :attr:`Doctrine.direct` when some withdrawal was left unallocated
#: -- no single deposit of that amount was available to identify it against.
#: Without this note a direct trace reads as a positive finding that a claim's
#: money did not move, when what happened is that the doctrine made no finding
#: at all.  Those are very different things to put in front of a tribunal, and
#: the surviving figure alone cannot tell them apart.
NOTE_UNIDENTIFIED_WITHDRAWAL = "direct_withdrawal_not_identified"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Movement:
    """One admitted ledger row, reduced to what tracing reads.

    A narrow object rather than the ORM row, for the same reason
    :class:`services.financial.linkage.LinkObservation` is narrow: the rules
    are the part worth auditing, and they are easier to audit when the thing
    they run over fits in four lines of a test.  It also stops the tracer
    quietly depending on a column nobody meant it to read.

    ``amount`` is a positive magnitude and ``direction`` carries the sign, which
    is the ledger's convention throughout.  ``row_index`` is the row's position
    in the statement it was read from, and it is what puts two movements on one
    day into the order the bank recorded them in.
    """

    transaction_id: uuid.UUID
    ordering_date: date
    row_index: int
    amount: Money
    direction: TransactionDirection
    proof_class: ProofClass
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Money):
            raise TracingError(
                f"movement {self.transaction_id}: amount must be Money, got "
                f"{type(self.amount).__name__}"
            )
        if self.amount.is_negative:
            raise TracingError(
                f"movement {self.transaction_id}: amount is a magnitude and must "
                "not be negative; the sign belongs in `direction`"
            )
        # A zero amount is permitted, and that is a decision rather than an
        # oversight.  Real statements carry zero-value rows -- waived fees,
        # reversal pairs, memo entries -- and refusing them would mean a whole
        # trace could not run because of a line that moves no money and changes
        # no figure.  An attribution against one is separately impossible, since
        # :class:`Attribution` requires a positive amount and no attribution may
        # exceed its deposit, so a zero row cannot carry a claim either.


    @property
    def is_deposit(self) -> bool:
        return self.direction == TransactionDirection.credit

    @property
    def is_withdrawal(self) -> bool:
        return self.direction == TransactionDirection.debit


@dataclass(frozen=True)
class Attribution:
    """An analyst's claim that part of a deposit is traceable to a claimant.

    This is the one input to tracing that is not a ledger fact, and it is a
    separate object for that reason: the deposit is what the bank recorded, the
    attribution is what someone says about it.  Keeping them apart is what lets
    an exhibit show the trace resting on an assertion and name whose assertion
    it is.

    ``basis`` is recorded and never evaluated.  This module does not rank the
    strength of an attribution, and it certainly does not decide whether the
    money was taken wrongfully -- AICPA SSFS No. 1 puts that outside what may
    be opined on at all.

    ``amount`` may be less than the deposit: a $100,000 credit of which
    $30,000 is said to be traceable is an ordinary situation, and the other
    $70,000 is untainted money in the same account.
    """

    transaction_id: uuid.UUID
    claim_id: str
    amount: Money
    basis: str

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise AttributionError("an attribution must name a claim")
        if not isinstance(self.amount, Money):
            raise AttributionError(
                f"attribution to {self.claim_id}: amount must be Money"
            )
        if not self.amount.is_positive:
            raise AttributionError(
                f"attribution to {self.claim_id}: amount must be positive; a "
                "zero attribution asserts nothing and a negative one is not a "
                "thing a deposit can be"
            )
        if not self.basis:
            raise AttributionError(
                f"attribution to {self.claim_id}: a basis must be stated, "
                "because the trace rests on it and a reader is entitled to see "
                "what it rests on"
            )


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Draw:
    """What one withdrawal took, and from whom, under the doctrine applied.

    ``by_claim`` covers only attributed money.  ``from_untainted`` is money
    deposited without an attribution, and ``from_opening`` is money that was
    in the account before the window opened; both are outside every claim and
    are kept apart from each other because they are different evidential
    situations -- untainted deposits are movements this trace saw, an opening
    balance is a figure it was handed.

    ``unfunded`` and ``unidentified`` are both residues, and they are separate
    because they record opposite situations.  ``unfunded`` means the money was
    not there: the withdrawal ran past everything the account held, which is
    the *Bishopsgate v Homan* position.  ``unidentified`` means the money was
    there and the doctrine declined to say whose it was -- only direct tracing
    ever produces it, because only direct tracing applies no presumption and so
    can leave a withdrawal unallocated.  Folding the second into the first
    would report an account as overdrawn when it was solvent throughout, which
    in an exhibit is not an approximation but a false statement.

    The five parts sum to the withdrawal exactly, always.
    """

    transaction_id: uuid.UUID
    ordering_date: date
    amount: Money
    by_claim: Mapping[str, Money]
    from_untainted: Money
    from_opening: Money
    unfunded: Money
    unidentified: Money

    def total_traced(self) -> Money:
        """The part of this withdrawal that any claim answers for."""
        total = Money.zero(self.amount.currency)
        for share in self.by_claim.values():
            total = total + share
        return total

    def parts_total(self) -> Money:
        """The five parts summed.  Equal to :attr:`amount` by construction."""
        return (
            self.total_traced()
            + self.from_untainted
            + self.from_opening
            + self.unfunded
            + self.unidentified
        )


@dataclass(frozen=True)
class ClaimOutcome:
    """Where one claim's money ended up under the doctrine applied.

    ``deposited`` is what was attributed.  ``surviving`` is what is still in
    the account at the close of the window; ``withdrawn`` is what left it and
    can be followed onward to the next account.  These three are the whole of
    the claim: ``deposited == surviving + withdrawn``.

    There is no separate "dissipated" figure, and its absence is deliberate.
    Whether money that left was dissipated or merely moved is not something
    this account's statement can answer -- it is answered by tracing the next
    account, or by failing to find one.  Reporting a dissipation here would be
    asserting the negative of something never looked for.
    """

    claim_id: str
    deposited: Money
    surviving: Money
    withdrawn: Money


@dataclass(frozen=True)
class TraceResult:
    """One account's movements resolved under one named doctrine.

    Carries the doctrine, its authority, the per-claim outcome, the per
    withdrawal detail, and the notes recording every further choice that had to
    be made to reach the numbers.  A result is meant to be readable on its own:
    someone handed only this object should be able to say what rule was
    applied, what it produced, and what it assumed.
    """

    doctrine: Doctrine
    authority: str
    currency: str
    opening_balance: Money
    closing_balance: Money
    #: The account's minimum balance across the traced period, opening balance
    #: included.  Deliberately *not* named for the lowest intermediate balance
    #: rule, which it is not: the rule's operative figure is per claim and is
    #: measured from that claim's own deposit onwards, whereas this is one
    #: number for the whole account measured from the start.  On an account
    #: opening at zero the two differ immediately -- this reads 0.00 while a
    #: claim deposited later may be capped at any figure above it.  The naming
    #: matters because the per-claim cap is already carried, correctly, in
    #: :attr:`outcomes`, and a reader who took this for the cap would quote a
    #: number the trace never found.
    lowest_balance: Money
    outcomes: Mapping[str, ClaimOutcome]
    draws: tuple[Draw, ...]
    notes: tuple[str, ...]
    proof_classes_included: frozenset[ProofClass]
    movements_considered: int
    movements_excluded_by_proof_class: int

    def surviving(self, claim_id: str) -> Money:
        """What of ``claim_id`` is still in the account."""
        outcome = self.outcomes.get(claim_id)
        if outcome is None:
            raise TracingError(f"no claim {claim_id!r} in this trace")
        return outcome.surviving

    def withdrawn(self, claim_id: str) -> Money:
        """What of ``claim_id`` left the account, and so may be followed on."""
        outcome = self.outcomes.get(claim_id)
        if outcome is None:
            raise TracingError(f"no claim {claim_id!r} in this trace")
        return outcome.withdrawn

    def total_surviving(self) -> Money:
        total = Money.zero(self.currency)
        for outcome in self.outcomes.values():
            total = total + outcome.surviving
        return total

    def total_unidentified(self) -> Money:
        """Withdrawals this doctrine declined to allocate to anyone.

        Zero under every doctrine but :attr:`Doctrine.direct`, because every
        other doctrine applies a presumption and a presumption always reaches
        an answer.  Where this is non-zero the surviving figures are silent
        about that much money rather than positively finding it stayed put,
        and a report that quotes the one without the other misrepresents the
        trace.
        """
        total = Money.zero(self.currency)
        for draw in self.draws:
            total = total + draw.unidentified
        return total


@dataclass(frozen=True)
class DoctrineComparison:
    """The same account under every doctrine, and where they disagree.

    The point of the object.  ``divergence`` gives, per claim, the spread
    between the highest and lowest surviving figure across the doctrines, which
    is the number that says whether the choice of rule mattered here at all.
    Where it is zero the doctrines agree and the choice is academic; where it
    is large the choice is the case.

    A doctrine that declined to allocate a withdrawal is excluded from that
    spread, and this is the subtle part.  Direct tracing reports whatever it
    could not identify as still surviving, because it did not find that the
    money left -- but neither did it find that the money stayed.  Counting that
    silence as a surviving figure manufactures a disagreement between the
    doctrines out of the absence of a finding by one of them, and produces the
    worst possible sentence to have to defend: "the answer is between 600 and
    1,000 depending which rule the tribunal prefers", when in truth every rule
    that reaches an answer reaches 600 and one method simply did not speak.
    :meth:`surviving_by_doctrine` and :meth:`narrative` still report every
    doctrine, silence included; only the arithmetic of the spread excludes it.
    """

    results: Mapping[Doctrine, TraceResult]
    claim_ids: tuple[str, ...]

    def surviving_by_doctrine(self, claim_id: str) -> Mapping[Doctrine, Money]:
        return {
            doctrine: result.surviving(claim_id)
            for doctrine, result in self.results.items()
        }

    def made_a_finding(self, doctrine: Doctrine) -> bool:
        """True where this doctrine allocated every withdrawal it was given.

        False only where a withdrawal was left unidentified, which in practice
        means direct tracing on facts that did not permit a one-to-one match.
        The test is trace-wide rather than per claim on purpose: an
        unallocated withdrawal could have been anyone's, so it leaves every
        claim's surviving figure in the same trace overstated by an unknown
        share, not just the claims it might obviously have touched.
        """
        result = self.results.get(doctrine)
        if result is None:
            raise TracingError(f"doctrine {doctrine!r} is not in this comparison")
        return not result.total_unidentified().is_positive

    def doctrines_making_findings(self) -> tuple[Doctrine, ...]:
        """The doctrines whose figures are findings, in :data:`DOCTRINE_ORDER`."""
        return tuple(
            doctrine
            for doctrine in DOCTRINE_ORDER
            if doctrine in self.results and self.made_a_finding(doctrine)
        )

    def divergence(self, claim_id: str) -> Money:
        """Highest surviving figure minus lowest, over doctrines that found.

        Zero where fewer than two doctrines reached an answer: one answer
        cannot disagree with itself, and no answers cannot disagree either.
        Callers that need to know which case they are in ask
        :meth:`doctrines_making_findings` rather than reading it off a spread.
        """
        surviving = self.surviving_by_doctrine(claim_id)
        found = self.doctrines_making_findings()
        currency = next(iter(self.results.values())).currency
        if len(found) < 2:
            return Money.zero(currency)
        amounts = [surviving[doctrine].minor_units for doctrine in found]
        return Money(max(amounts) - min(amounts), currency)

    def doctrines_agree(self, claim_id: str) -> bool:
        """True where every doctrine that reached an answer reached the same one.

        Says nothing about doctrines that made no finding; a comparison in
        which four doctrines agree and direct tracing declined is an agreement,
        because there is nothing for the declination to disagree with.
        """
        return self.divergence(claim_id).is_zero

    def narrative(self, claim_id: str) -> str:
        """One line per doctrine, in :data:`DOCTRINE_ORDER`, for an exhibit.

        Deliberately plain.  This is the sentence a report puts under the
        number, and it should read the same whichever doctrine was chosen, so
        that choosing one does not look like advocacy for it.
        """
        lines = []
        for doctrine in DOCTRINE_ORDER:
            result = self.results.get(doctrine)
            if result is None:
                continue
            line = (
                f"{_DOCTRINE_LABEL[doctrine]}: "
                f"{result.surviving(claim_id).format()} remaining, "
                f"{result.withdrawn(claim_id).format()} traced out"
            )
            # Without this clause the line reads as a positive finding that the
            # money stayed put, when the doctrine in fact declined to say.
            unidentified = result.total_unidentified()
            if unidentified.is_positive:
                line += (
                    f" ({unidentified.format()} of withdrawals could not be "
                    "identified against any deposit, so this doctrine makes no "
                    "finding about that amount)"
                )
            lines.append(line)
        spread = self.divergence(claim_id)
        found = self.doctrines_making_findings()
        # Said only where it is true.  "The doctrines agree" over a set in which
        # one of them declined to speak would be a claim of unanimity drawn
        # partly from silence, and the qualifier is what keeps the summary line
        # consistent with the per-doctrine lines above it.
        silent = len(found) < len(
            [d for d in DOCTRINE_ORDER if d in self.results]
        )
        qualifier = (
            " among those that reached an answer" if silent else ""
        )
        if len(found) < 2:
            lines.append(
                "Fewer than two doctrines reached an answer on this claim, so "
                "there is no comparison to draw between them."
            )
        elif spread.is_zero:
            lines.append(
                f"The doctrines agree{qualifier}; the choice between them does "
                "not affect this claim."
            )
        else:
            lines.append(
                f"The doctrines differ{qualifier} by {spread.format()} on what "
                "remains, so the choice between them is material and is a "
                "question of law."
            )
        return "\n".join(lines)


#: How each doctrine is named in prose.  Separate from the enum because the
#: enum value is a stable key and this is a label a reader sees.
_DOCTRINE_LABEL: Mapping[Doctrine, str] = {
    Doctrine.lowest_intermediate_balance: "Lowest intermediate balance rule",
    Doctrine.first_in_first_out: "First in, first out (Clayton's Case)",
    Doctrine.last_in_first_out: "Last in, first out",
    Doctrine.pro_rata: "Pro rata",
    Doctrine.direct: "Direct tracing",
}


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def _ordered(movements: Sequence[Movement]) -> tuple[list[Movement], bool]:
    """Put movements in the order the account saw them.

    Sorted by date, then by the row's position in its statement, then by
    transaction id.  The last of those is arbitrary -- it is there so the
    result is deterministic, not because it means anything -- so reaching for
    it is reported: the returned flag is true when two movements on one day
    shared a row index and the tiebreak had to decide between them.

    That matters because FIFO and LIFO can turn on it.  A deposit and a
    withdrawal on the same day, in an order the records do not fix, is an
    ambiguity in the evidence, and a tracing engine that resolved it silently
    would be inventing the fact its answer depends on.
    """
    ordered = sorted(
        movements,
        key=lambda m: (m.ordering_date, m.row_index, str(m.transaction_id)),
    )
    unevidenced = False
    for earlier, later in zip(ordered, ordered[1:]):
        if (
            earlier.ordering_date == later.ordering_date
            and earlier.row_index == later.row_index
            and earlier.direction != later.direction
        ):
            unevidenced = True
            break
    return ordered, unevidenced


# ---------------------------------------------------------------------------
# The pool
# ---------------------------------------------------------------------------


@dataclass
class _Parcel:
    """A quantity of money in the account, and whose it is said to be.

    ``claim_id`` is ``None`` for money nobody has claimed: either an
    unattributed deposit or the opening balance, told apart by ``is_opening``.
    Parcels are consumed by withdrawals according to the doctrine, and what is
    left at the end is what survives.
    """

    claim_id: Optional[str]
    remaining: Money
    is_opening: bool = False
    sequence: int = 0


def _empty_draw(movement: Movement, currency: str) -> dict:
    zero = Money.zero(currency)
    return {
        "transaction_id": movement.transaction_id,
        "ordering_date": movement.ordering_date,
        "amount": movement.amount,
        "by_claim": {},
        "from_untainted": zero,
        "from_opening": zero,
        "unfunded": zero,
        "unidentified": zero,
    }


def _record(parts: dict, parcel: _Parcel, taken: Money) -> None:
    """Add ``taken`` to the right bucket of a draw under construction."""
    if taken.is_zero:
        return
    if parcel.claim_id is None:
        key = "from_opening" if parcel.is_opening else "from_untainted"
        parts[key] = parts[key] + taken
    else:
        current = parts["by_claim"].get(parcel.claim_id)
        parts["by_claim"][parcel.claim_id] = (
            taken if current is None else current + taken
        )


def _consume_in_order(
    parcels: list[_Parcel], parts: dict, wanted: Money, order: Sequence[int]
) -> Money:
    """Take ``wanted`` from ``parcels`` following ``order``, and report the rest.

    Shared by every ordered doctrine: FIFO walks the parcels oldest first, LIFO
    newest first, and LIBR walks unclaimed money first and claims afterwards.
    The three differ only in the order they hand in, which is the whole reason
    they are one function -- writing the take-and-record loop three times is
    how the three come to disagree about something nobody meant them to
    disagree about.
    """
    outstanding = wanted
    for index in order:
        if not outstanding.is_positive:
            break
        parcel = parcels[index]
        if not parcel.remaining.is_positive:
            continue
        taken = Money(
            min(parcel.remaining.minor_units, outstanding.minor_units),
            outstanding.currency,
        )
        parcel.remaining = parcel.remaining - taken
        outstanding = outstanding - taken
        _record(parts, parcel, taken)
    return outstanding


def _consume_rateably(parcels: list[_Parcel], parts: dict, wanted: Money) -> Money:
    """Take ``wanted`` proportionately from every parcel holding anything.

    Uses :meth:`Money.allocate`, so the shares sum back to ``wanted`` exactly
    and nothing is lost to rounding.

    No share can exceed the parcel meant to bear it, and that is stated here as
    a proof rather than a hope because two lines below depend on it.  The
    rateable branch is reached only where ``available > wanted`` strictly, and
    the weights are the parcels' own balances, so ``allocate`` floors each
    share at ``wanted * w / available``, which is below ``w``, and then hands
    out at most one further minor unit apiece -- leaving every share at or
    under ``w``.  A parcel holding nothing is excluded from ``live`` before any
    of that, so it cannot be handed a rounding unit it has no money to pay.

    The ``min`` on each take and the sweep that follows are therefore both
    provably dead, and are kept deliberately.  Each of the three facts the
    proof rests on -- the strict inequality above, the weights being the
    balances, the exclusion of empty parcels -- is one edit away from being
    untrue, and if any of them stops holding the failure is a withdrawal that
    silently comes out smaller than it was.  These two lines are what would
    surface that rather than let it through.
    """
    live = [i for i, p in enumerate(parcels) if p.remaining.is_positive]
    if not live:
        return wanted
    available = sum(parcels[i].remaining.minor_units for i in live)
    if available <= wanted.minor_units:
        # Everything goes; no proportions to strike.
        return _consume_in_order(parcels, parts, wanted, live)

    weights = [parcels[i].remaining.minor_units for i in live]
    shares = wanted.allocate(weights)
    for index, share in zip(live, shares):
        parcel = parcels[index]
        taken = Money(
            min(parcel.remaining.minor_units, share.minor_units), wanted.currency
        )
        parcel.remaining = parcel.remaining - taken
        _record(parts, parcel, taken)
    taken_total = sum(
        (weights[n] - parcels[i].remaining.minor_units) for n, i in enumerate(live)
    )
    return Money(wanted.minor_units - taken_total, wanted.currency)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def trace(
    movements: Sequence[Movement],
    attributions: Sequence[Attribution],
    *,
    doctrine: Doctrine,
    opening_balance: Money,
    proof_classes: frozenset[ProofClass] = DEFAULT_TOTAL_CLASSES,
) -> TraceResult:
    """Resolve one account's movements under one doctrine.

    ``doctrine`` is keyword-only and has no default, which is the point: there
    is no rule this module is entitled to pick on a caller's behalf.

    ``proof_classes`` defaults to :data:`DEFAULT_TOTAL_CLASSES` -- P0 to P2, the
    classes that reach the ledger without a human act -- and the result records
    both the filter and how many rows it excluded, so a trace can never quietly
    be running over material a reader would not have admitted.
    """
    if not isinstance(doctrine, Doctrine):
        raise DoctrineError(
            f"{doctrine!r} is not a Doctrine; a trace must name its rule and "
            "this module will not choose one"
        )
    if not isinstance(opening_balance, Money):
        raise TracingError("opening_balance must be Money")
    currency = opening_balance.currency
    if opening_balance.is_negative:
        raise TracingError(
            "opening_balance is negative: the account was already overdrawn, so "
            "there is no fund to trace into and no doctrine repairs that"
        )

    # Checked over the whole input rather than the admitted subset, and checked
    # before anything else reads the rows.  ``transaction_id`` is the key
    # attributions are indexed on, so two rows sharing one would attach a single
    # attribution to both and charge the claim twice -- silently, and in a
    # direction that flatters whoever the attribution names.  Refusing on the
    # unfiltered set also means a later change to the proof-class filter cannot
    # expose a duplicate that was previously hidden behind an exclusion.
    _refuse_duplicate_rows(movements)

    considered, excluded = _filter_by_proof_class(movements, proof_classes, currency)
    ordered, unevidenced = _ordered(considered)
    by_deposit = _index_attributions(ordered, attributions, currency)

    parcels: list[_Parcel] = []
    if opening_balance.is_positive:
        parcels.append(
            _Parcel(claim_id=None, remaining=opening_balance, is_opening=True)
        )

    deposited: dict[str, Money] = {}
    for attribution in attributions:
        current = deposited.get(attribution.claim_id)
        deposited[attribution.claim_id] = (
            attribution.amount if current is None else current + attribution.amount
        )

    notes: set[str] = set()
    if unevidenced and doctrine in (
        Doctrine.first_in_first_out,
        Doctrine.last_in_first_out,
    ):
        notes.add(NOTE_ORDER_UNEVIDENCED)

    if doctrine == Doctrine.direct:
        return _trace_direct(
            ordered, by_deposit, deposited, currency, opening_balance,
            proof_classes, len(considered), excluded, notes,
        )

    draws: list[Draw] = []
    balance = opening_balance
    lowest = opening_balance
    sequence = 0

    for movement in ordered:
        if movement.is_deposit:
            balance = balance + movement.amount
            attributed = by_deposit.get(movement.transaction_id, [])
            claimed_total = Money.zero(currency)
            for attribution in attributed:
                sequence += 1
                parcels.append(
                    _Parcel(
                        claim_id=attribution.claim_id,
                        remaining=attribution.amount,
                        sequence=sequence,
                    )
                )
                claimed_total = claimed_total + attribution.amount
            remainder = movement.amount - claimed_total
            if remainder.is_positive:
                sequence += 1
                parcels.append(
                    _Parcel(claim_id=None, remaining=remainder, sequence=sequence)
                )
            continue

        parts = _empty_draw(movement, currency)
        order = _draw_order(parcels, doctrine)
        if doctrine == Doctrine.pro_rata:
            outstanding = _consume_rateably(parcels, parts, movement.amount)
        else:
            outstanding = _consume_in_order(parcels, parts, movement.amount, order)

        if outstanding.is_positive:
            parts["unfunded"] = outstanding
            notes.add(NOTE_OVERDRAWN)
        if parts["from_opening"].is_positive:
            notes.add(NOTE_DREW_ON_OPENING)
        if len(parts["by_claim"]) > 1 and doctrine == (
            Doctrine.lowest_intermediate_balance
        ):
            notes.add(NOTE_SHORTFALL_SHARED)

        draws.append(Draw(**parts))
        balance = balance - movement.amount
        if balance.minor_units < lowest.minor_units:
            lowest = balance
        if balance.is_negative:
            notes.add(NOTE_OVERDRAWN)
            balance = Money.zero(currency)

    outcomes = _outcomes(deposited, parcels, draws, currency)
    return TraceResult(
        doctrine=doctrine,
        authority=DOCTRINE_AUTHORITY[doctrine],
        currency=currency,
        opening_balance=opening_balance,
        closing_balance=balance,
        lowest_balance=lowest,
        outcomes=outcomes,
        draws=tuple(draws),
        notes=tuple(sorted(notes)),
        proof_classes_included=frozenset(proof_classes),
        movements_considered=len(considered),
        movements_excluded_by_proof_class=excluded,
    )


def _draw_order(parcels: Sequence[_Parcel], doctrine: Doctrine) -> list[int]:
    """The order this doctrine takes money out of the account in.

    LIBR is the interesting one.  Unclaimed money goes first -- the opening
    balance and then unattributed deposits, oldest first -- because *Re
    Hallett's Estate* presumes a person spends their own money before money
    they hold for someone else.  Only when that is exhausted does a withdrawal
    reach the claims, and it then takes from them oldest first.

    Nothing here ever puts money *back*.  A parcel reduced to nothing stays at
    nothing however much is deposited afterwards, which is *Roscoe v Winder*
    and is the whole substance of the lowest intermediate balance: the floor is
    a floor because the fund does not refill.
    """
    indices = list(range(len(parcels)))
    if doctrine == Doctrine.first_in_first_out:
        return sorted(indices, key=lambda i: (parcels[i].sequence, i))
    if doctrine == Doctrine.last_in_first_out:
        return sorted(indices, key=lambda i: (-parcels[i].sequence, i))
    if doctrine == Doctrine.lowest_intermediate_balance:
        return sorted(
            indices,
            key=lambda i: (
                parcels[i].claim_id is not None,
                parcels[i].sequence,
                i,
            ),
        )
    return indices


def _outcomes(
    deposited: Mapping[str, Money],
    parcels: Sequence[_Parcel],
    draws: Sequence[Draw],
    currency: str,
) -> dict[str, ClaimOutcome]:
    """What survived and what left, per claim.

    Computed from two independent places -- what is still sitting in the
    parcels, and what the draws recorded taking -- and the two must add back to
    what was deposited.  They are not checked against each other here because
    the tests do that; the arrangement exists so that they *can* be.
    """
    surviving: dict[str, Money] = {}
    for parcel in parcels:
        if parcel.claim_id is None:
            continue
        current = surviving.get(parcel.claim_id)
        surviving[parcel.claim_id] = (
            parcel.remaining if current is None else current + parcel.remaining
        )

    withdrawn: dict[str, Money] = {}
    for draw in draws:
        for claim_id, share in draw.by_claim.items():
            current = withdrawn.get(claim_id)
            withdrawn[claim_id] = share if current is None else current + share

    zero = Money.zero(currency)
    return {
        claim_id: ClaimOutcome(
            claim_id=claim_id,
            deposited=total,
            surviving=surviving.get(claim_id, zero),
            withdrawn=withdrawn.get(claim_id, zero),
        )
        for claim_id, total in sorted(deposited.items())
    }


def _refuse_duplicate_rows(movements: Sequence[Movement]) -> None:
    """Refuse a ledger that carries the same transaction identity twice.

    A duplicate is not merely double-counted; it corrupts attribution.  The
    index built by :func:`_index_attributions` is keyed on ``transaction_id``,
    so one attribution against a duplicated id is applied to both copies, and
    the claim is credited with a deposit that happened once.  Nothing
    downstream can detect that: both traces balance, both foot, and the
    inflated figure carries the same authority as an honest one.

    Deduplicating instead of refusing would be worse.  Two rows with one id are
    either the same row read twice or two different rows that lost their
    identity, and this module cannot tell which -- keeping one copy would be a
    guess about the ledger presented as a fact about it.
    """
    seen: dict[uuid.UUID, int] = {}
    for position, movement in enumerate(movements):
        first = seen.get(movement.transaction_id)
        if first is not None:
            raise TracingError(
                f"movement {movement.transaction_id} appears twice, at "
                f"positions {first} and {position}; a transaction id is the "
                "key attributions are matched on, so the same id on two rows "
                "would charge one claim for a deposit that happened once"
            )
        seen[movement.transaction_id] = position


def _filter_by_proof_class(
    movements: Sequence[Movement],
    proof_classes: frozenset[ProofClass],
    currency: str,
) -> tuple[list[Movement], int]:
    """Drop rows outside the admitted classes, and count what was dropped.

    Counted rather than silently discarded: a trace that ran over half the
    account because the other half was P3 is a different trace, and the reader
    has to be able to see that it was.
    """
    if not proof_classes:
        raise TracingError(
            "proof_classes is empty, so no movement could be considered; pass "
            "the classes to include rather than none"
        )
    kept: list[Movement] = []
    excluded = 0
    for movement in movements:
        if movement.amount.currency != currency:
            raise CurrencyMismatchError(
                f"movement {movement.transaction_id} is in "
                f"{movement.amount.currency} but the account is in {currency}; "
                "converting is an analytical act and must be recorded, not implied"
            )
        if movement.proof_class in proof_classes:
            kept.append(movement)
        else:
            excluded += 1
    return kept, excluded


def _index_attributions(
    movements: Sequence[Movement],
    attributions: Sequence[Attribution],
    currency: str,
) -> dict[uuid.UUID, list[Attribution]]:
    """Group attributions by deposit, refusing every way they can be wrong.

    An attribution to a row that is not here, to a withdrawal, in the wrong
    currency, or exceeding the deposit it names is a mistake that would
    otherwise show up as a quiet arithmetic error several hundred lines later.
    """
    deposits = {m.transaction_id: m for m in movements if m.is_deposit}
    withdrawals = {m.transaction_id for m in movements if m.is_withdrawal}

    grouped: dict[uuid.UUID, list[Attribution]] = {}
    for attribution in attributions:
        if attribution.amount.currency != currency:
            raise CurrencyMismatchError(
                f"attribution to {attribution.claim_id} is in "
                f"{attribution.amount.currency} but the account is in {currency}"
            )
        if attribution.transaction_id in withdrawals:
            raise AttributionError(
                f"attribution to {attribution.claim_id} names "
                f"{attribution.transaction_id}, which is a withdrawal; funds are "
                "traced from the deposit that brought them in, not from a payment out"
            )
        if attribution.transaction_id not in deposits:
            raise AttributionError(
                f"attribution to {attribution.claim_id} names "
                f"{attribution.transaction_id}, which is not a deposit in this "
                "account within the movements supplied"
            )
        grouped.setdefault(attribution.transaction_id, []).append(attribution)

    for transaction_id, group in grouped.items():
        total = Money.zero(currency)
        for attribution in group:
            total = total + attribution.amount
        deposit = deposits[transaction_id]
        if total.minor_units > deposit.amount.minor_units:
            raise AttributionError(
                f"deposit {transaction_id} of {deposit.amount.format()} carries "
                f"attributions totalling {total.format()}; a deposit cannot be "
                "traceable to more than it was"
            )
        group.sort(key=lambda a: (a.claim_id, a.amount.minor_units))

    return grouped


# ---------------------------------------------------------------------------
# Direct tracing
# ---------------------------------------------------------------------------


def _trace_direct(
    ordered: Sequence[Movement],
    by_deposit: Mapping[uuid.UUID, Sequence[Attribution]],
    deposited: Mapping[str, Money],
    currency: str,
    opening_balance: Money,
    proof_classes: frozenset[ProofClass],
    considered: int,
    excluded: int,
    notes: set[str],
) -> TraceResult:
    """Match withdrawals to deposits one-to-one, or say nothing.

    A withdrawal is matched only when exactly one deposit of the same amount
    precedes it and has not already been spoken for.  Two candidates means the
    records do not identify which one left, and this doctrine declines rather
    than picking -- picking would be a presumption with the label taken off,
    which is the one thing this module is built to prevent.

    *Untainted deposits compete in that identification.*  The test is a wire in
    on Tuesday, a wire out of the same amount on Wednesday, **and nothing else
    moving** -- and an unattributed deposit of the same amount is
    something else moving: the money that left could as easily have been the
    holder's own.  Considering only attributed deposits would find a unique
    match wherever the competing deposit happened to be untainted, and would
    thereby resolve a real ambiguity against the claimant -- silently, and
    under a doctrine whose whole content is that it applies no presumption.
    So an untainted deposit is carried as a candidate with no claim; matching
    one means the withdrawal came from the holder's own money and no claim
    answers for it, and matching it *against* an attributed deposit of the same
    amount means nothing is matched at all.

    Unmatched withdrawals are reported as drawn from nothing in particular.
    Under this doctrine that is the honest answer: no presumption was applied,
    so no claim answers for the payment.
    """
    # ``claim_id`` is None for the untainted remainder of a deposit.  Those
    # entries never attribute anything to anyone; they exist so that they can
    # spoil a match, which is the whole point of "nothing else moving".
    available: list[tuple[int, Optional[str], Money]] = []
    sequence = 0
    draws: list[Draw] = []
    balance = opening_balance
    lowest = opening_balance
    withdrawn: dict[str, Money] = {}

    for movement in ordered:
        if movement.is_deposit:
            balance = balance + movement.amount
            claimed = Money.zero(currency)
            for attribution in by_deposit.get(movement.transaction_id, []):
                sequence += 1
                available.append(
                    (sequence, attribution.claim_id, attribution.amount)
                )
                claimed = claimed + attribution.amount
            # Whatever of the deposit no claim spoke for is the holder's own,
            # and is just as capable of being the money that later left.
            untainted = movement.amount - claimed
            if untainted.is_positive:
                sequence += 1
                available.append((sequence, None, untainted))
            continue

        parts = _empty_draw(movement, currency)
        # The part of the withdrawal the account could not fund is settled
        # before identification is attempted, and for the same reason it is
        # under every other doctrine: *Bishopsgate v Homan* refuses tracing
        # into an overdraft, so money that was never in the account cannot be
        # identified as anyone's however well the amounts happen to line up.
        overdraft = movement.amount - balance
        if overdraft.is_positive:
            notes.add(NOTE_OVERDRAWN)
            parts["unfunded"] = overdraft
        fundable = movement.amount - parts["unfunded"]

        candidates = [
            entry for entry in available
            if entry[2].minor_units == fundable.minor_units
        ] if fundable.is_positive else []
        if len(candidates) == 1:
            _, claim_id, amount = candidates[0]
            available.remove(candidates[0])
            if claim_id is None:
                # Identified, and identified as the holder's own money.  That
                # is a result, not a failure to find one: no claim answers for
                # this payment because the records say it was not their money.
                parts["from_untainted"] = amount
            else:
                parts["by_claim"] = {claim_id: amount}
                current = withdrawn.get(claim_id)
                withdrawn[claim_id] = (
                    amount if current is None else current + amount
                )
        else:
            # Nothing identified: either no candidate at all, or several and
            # the doctrine declined between them.  The money still left the
            # account, so it is recorded as unidentified rather than dropped;
            # dropping it would break the identity between a withdrawal and
            # its parts, and an exhibit whose columns do not add up is worse
            # than useless.
            if len(candidates) > 1:
                notes.add(NOTE_AMBIGUOUS_MATCH)
            if fundable.is_positive:
                notes.add(NOTE_UNIDENTIFIED_WITHDRAWAL)
                parts["unidentified"] = fundable

        draws.append(Draw(**parts))
        balance = balance - fundable
        if balance.minor_units < lowest.minor_units:
            lowest = balance

    zero = Money.zero(currency)
    outcomes = {
        claim_id: ClaimOutcome(
            claim_id=claim_id,
            deposited=total,
            surviving=total - withdrawn.get(claim_id, zero),
            withdrawn=withdrawn.get(claim_id, zero),
        )
        for claim_id, total in sorted(deposited.items())
    }
    return TraceResult(
        doctrine=Doctrine.direct,
        authority=DOCTRINE_AUTHORITY[Doctrine.direct],
        currency=currency,
        opening_balance=opening_balance,
        closing_balance=balance,
        lowest_balance=lowest,
        outcomes=outcomes,
        draws=tuple(draws),
        notes=tuple(sorted(notes)),
        proof_classes_included=frozenset(proof_classes),
        movements_considered=considered,
        movements_excluded_by_proof_class=excluded,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_doctrines(
    movements: Sequence[Movement],
    attributions: Sequence[Attribution],
    *,
    opening_balance: Money,
    proof_classes: frozenset[ProofClass] = DEFAULT_TOTAL_CLASSES,
    doctrines: Sequence[Doctrine] = DOCTRINE_ORDER,
) -> DoctrineComparison:
    """Run every doctrine over the same facts and report the spread.

    This is what an exhibit should be built from.  Reporting one doctrine's
    number alone leaves the reader unable to tell whether the choice mattered;
    reporting all of them shows the choice was made knowingly and shows what it
    cost, which is what FRE 702(d) asks for.
    """
    results = {
        doctrine: trace(
            movements,
            attributions,
            doctrine=doctrine,
            opening_balance=opening_balance,
            proof_classes=proof_classes,
        )
        for doctrine in doctrines
    }
    claim_ids = sorted({a.claim_id for a in attributions})
    return DoctrineComparison(results=results, claim_ids=tuple(claim_ids))
