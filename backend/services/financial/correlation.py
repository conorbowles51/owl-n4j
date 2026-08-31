"""Matching what people said about money against what the records show.

A subject says "I paid Halloran two hundred thousand in March".  The ledger,
built from admitted statements whose arithmetic closes, shows one payment to
Halloran in March for forty thousand.  That gap is the finding, and no product
on the market surfaces it.

This module is the surface that does.  It takes P4 claims -- financial
assertions extracted from interviews, messages, emails and notes -- and matches
them against the verified ledger, returning one of three outcomes:
*corroborated*, *contradicted*, or *unresolved*.

The rule that makes it safe
---------------------------

**Correlation never promotes.**  A corroborated P4 claim is still
P4.  It gains a link to a P0-P2 transaction and the transaction gains a link
back, and neither changes class.  There is no code path here that assigns a
proof class, and there is no argument -- however many transactions corroborate
a claim, however exactly they agree -- that moves an assertion into the ledger.
The ledger is never contaminated by an assertion, and the constructors refuse
in both directions: a claim that is not P4 is not a claim this module will read
(:class:`ClaimError`), and a ledger entry that is P4 is not evidence
(:class:`LedgerClassError`), because an assertion cannot corroborate an
assertion.

The rule that makes it honest
-----------------------------

**A contradiction is a claim about the records, not about the speaker.**  Every
contradiction here means one thing only: *no transaction answering this claim
exists in the accounts we hold, over a period those accounts cover without a
gap and without an unreconciled statement.*  It does not mean the speaker lied,
and the vocabulary is built so that it cannot be made to say so.  Whether a
person was untruthful is for the trier of fact; AICPA SSFS No. 1 forbids the
opinion and :mod:`services.financial.tracing` says the same thing about fraud.

Distinguishing "contradicted" from "we do not have the records" is one of the
few places in this system where carelessness would do real harm.  So the
gate on contradiction is deliberately hard to pass:

* the claim's whole date window must be covered by an account in scope, with no
  gap seam and no break seam inside it (:mod:`services.financial.continuity`
  supplies both);
* no period overlapping the window may be unreconciled -- a statement whose
  arithmetic does not close may be missing rows, and absence from a record that
  is known to be incomplete is not absence;
* the claim must be *testable*: it must carry a currency, an amount range, and
  either a named party or a direction that can be anchored to an account holder;
* and no candidate transaction may be left inconclusive.  A single row that
  might be the payment, and which the evidence does not let us rule in or out,
  is enough to make the answer *unresolved*.  A maybe is not an absence.

Where any of those fails the outcome is unresolved, and the reason is named.
The bias is deliberate and it runs one way: a false *unresolved* costs an
investigator an afternoon, and a false *contradicted* is put to a witness.

Vagueness is preserved, not resolved
------------------------------------

"About twenty grand" is an amount *range*; "in March" is a date *range*.  A
claim carries :class:`AmountRange` and :class:`DateRange` rather than an amount
and a date, and there is no constructor here that turns a hedge into a figure.
Converting speech into those ranges is the assertion processor's work, upstream
of this module, and it is the processor that must not invent precision: a range
of a single day and a single cent asserts that the witness was exact.

Materiality sits on top of the range, not inside it
---------------------------------------------------

A claim of exactly $20,000 that the ledger answers with $20,000.02 is not a
finding, and a range comparison alone would make it one.  So the stated range
is widened by a :class:`Materiality` tolerance before the comparison, and the
tolerance actually applied is recorded on the result so it can be shown and
argued rather than assumed.  It defaults to ten per cent of the claim's
midpoint, floored at one major unit -- generous, because the harm from a
manufactured contradiction is not symmetric with the harm from a generous
corroboration.

Names are compared as strings
-----------------------------

Party matching uses :func:`~services.financial.linkage.name_similarity` over
:func:`~services.financial.linkage.normalise_name`, which is deliberately
shallow.  Deciding that "Halloran Group" and "HG Holdings LLC" are one entity
is entity resolution and belongs upstream; callers should pass
resolved names.  Because a name this module sets aside might be the very
transaction the claim describes, every correlation reports the candidates it
excluded on a name alone, so a contradiction can be read together with what it
declined to look at.

Nothing here confirms anything
------------------------------

Correlation is a *proposal* surface.  :func:`correlate` produces a
proposal with its reasoning visible; a person confirms or rejects it; the
decision is appended as a :class:`CorrelationDecision`, in the same manner as
an entity merge, and :func:`apply_decisions` shows the machine's proposal and
the human's answer side by side without overwriting either.  There is no
confidence score above which this module decides for itself, because the value
of the feature is entirely in the investigator's confidence in it, and a
surface that is right nine times and quietly wrong the tenth has none.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Mapping, Optional, Sequence

from postgres.models.enums import ProofClass, TransactionDirection
from services.financial.continuity import (
    AccountContinuity,
    SeamAgreement,
    SeamKind,
)
from services.financial.linkage import name_similarity, normalise_name
from services.financial.money import CurrencyMismatchError, Money
from services.financial.proof_class import LEDGER_CLASSES


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CorrelationError(Exception):
    """Base class for every refusal in this module."""


class ClaimError(CorrelationError):
    """A P4 claim was malformed, or was not P4 at all.

    Raised rather than repaired.  A claim with an inverted range or an empty
    quote is a defect in the assertion processor, and correlating it anyway
    would put the defect into a report instead of into a stack trace.
    """


class LedgerClassError(CorrelationError):
    """A ledger entry carried a class that cannot be evidence of anything.

    P4 is the only class this catches, and it catches it on purpose: an
    assertion corroborating an assertion is two people saying the same thing,
    which is not a record and must never be presented as one.
    """


class CoverageError(CorrelationError):
    """A coverage statement contradicted itself."""


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


class Outcome(str, Enum):
    """The three answers, and the only three."""

    #: A verified transaction answers the claim on every testable dimension.
    corroborated = "corroborated"
    #: No such transaction exists, over records complete enough to say so.
    contradicted = "contradicted"
    #: The records, the claim, or a candidate will not let us say either.
    unresolved = "unresolved"


class ContradictionKind(str, Enum):
    """Which of the two kinds of contradiction was found."""

    #: Nothing in the covered period answers the claim at all.
    no_transaction = "no_transaction"
    #: A transaction answers it on parties, direction and date -- and differs
    #: materially on amount.  The $200,000-against-$40,000 case.
    amount_differs = "amount_differs"


class UnresolvedReason(str, Enum):
    """Why no finding was made.  Named, because "unresolved" alone is useless.

    An investigator reading a list of unresolved claims needs to know which of
    them a subpoena would settle (:attr:`records_incomplete`), which want a
    better interview (:attr:`claim_not_testable`), and which are already sitting
    on a row that a person could adjudicate in a minute
    (:attr:`candidate_inconclusive`).  Those are three different afternoons.
    """

    #: A gap, a break, or an unreconciled period inside the claim's window.
    records_incomplete = "records_incomplete"
    #: No account in scope covers the claim's window at all.
    outside_coverage = "outside_coverage"
    #: The claim does not carry enough to search on.
    claim_not_testable = "claim_not_testable"
    #: A candidate could be the payment, and the evidence will not say.
    candidate_inconclusive = "candidate_inconclusive"


class Agreement(str, Enum):
    """How one dimension of a claim compared with one ledger row.

    ``unknown`` is a third answer and not a weak ``differs``.  A missing
    counterparty string is a gap in the extraction, not evidence that the
    parties disagree, and collapsing the two is exactly how a system arrives at
    a confident wrong contradiction.
    """

    agrees = "agrees"
    differs = "differs"
    unknown = "unknown"


class CandidateVerdict(str, Enum):
    """What one ledger row is to one claim."""

    #: Everything testable agrees.  Corroboration.
    matches = "matches"
    #: Parties, direction, date and currency agree; the amount does not.
    differs_on_amount = "differs_on_amount"
    #: Nothing disagrees, but something is unknown.  Blocks contradiction.
    inconclusive = "inconclusive"
    #: Something other than the amount disagrees.  Not this payment.
    excluded = "excluded"


class DecisionKind(str, Enum):
    """A human's answer to a proposal.  Appended, never applied in place."""

    confirmed = "confirmed"
    rejected = "rejected"


#: The component names, used as keys and printed in narratives.
COMPONENT_CURRENCY = "currency"
COMPONENT_AMOUNT = "amount"
COMPONENT_DATE = "date"
COMPONENT_HOLDER = "holder_role"
COMPONENT_DIRECTION = "direction"
COMPONENT_COUNTERPARTY = "counterparty"

#: Order the components are reported in: the cheap, certain tests first.
COMPONENT_ORDER: tuple[str, ...] = (
    COMPONENT_CURRENCY,
    COMPONENT_AMOUNT,
    COMPONENT_DATE,
    COMPONENT_HOLDER,
    COMPONENT_DIRECTION,
    COMPONENT_COUNTERPARTY,
)

#: Components on which a disagreement is a name disagreement.  A contradiction
#: reached by setting these aside is reported together with what it set aside.
NAME_COMPONENTS: frozenset[str] = frozenset({COMPONENT_HOLDER, COMPONENT_COUNTERPARTY})


#: At or above this, two normalised names are the same party.  Shared with
#: :mod:`services.financial.linkage`, which uses the same figure for tier 2.
NAME_AGREEMENT_THRESHOLD = 0.85

#: At or below this, two normalised names are different parties.  Between the
#: two the answer is :attr:`Agreement.unknown`, and the band exists because the
#: cost of the two errors is not the same: calling a spelling variant a
#: disagreement discards the transaction that answers the claim, and then
#: reports its own discarding as a contradiction.
NAME_DISAGREEMENT_THRESHOLD = 0.50


NOTE_SEVERAL_MATCHES = "several transactions answer this claim"
NOTE_COVERAGE_GAP = "a statement is missing from the claimed period"
NOTE_COVERAGE_BREAK = "balances disagree across a seam in the claimed period"
NOTE_COVERAGE_OVERLAP = "two statements claim the same days in the period"
NOTE_COVERAGE_UNVERIFIED = "a statement covering the period does not reconcile"
NOTE_NO_ACCOUNTS = "no account is in scope"
NOTE_SCOPE_IS_PARTIAL = "the finding is limited to the accounts held"
NOTE_AMOUNT_OUTSIDE_STATED_RANGE = "the amount agrees only once materiality is allowed"
NOTE_DIRECTION_UNANCHORED = "no account holder was named, so direction is untested"
NOTE_COUNTERPARTY_UNTESTED = "the matched rows name no counterparty"
NOTE_SET_ASIDE_ON_NAME = "transactions were set aside on a name alone"
NOTE_MATCHED_ONLY_UNVERIFIED = "corroborated only by rows whose statement does not reconcile"


# ---------------------------------------------------------------------------
# Ranges: the shape vagueness is kept in
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AmountRange:
    """What was said about an amount, including how loosely it was said.

    A witness who says "about twenty grand" has told us something real and has
    not told us a number.  Storing 20000.00 would be an invention; storing the
    range is the record.  An exact figure is expressed as a range whose ends
    are equal, so the type is the same either way and nothing downstream has to
    ask which kind it got.
    """

    low: Money
    high: Money

    def __post_init__(self) -> None:
        if self.low.currency != self.high.currency:
            raise CurrencyMismatchError(
                f"an amount range cannot span {self.low.currency} and "
                f"{self.high.currency}; a conversion is an analytical act"
            )
        if self.low.is_negative or self.high.is_negative:
            raise ClaimError(
                "an amount range is a magnitude and cannot be negative; "
                "which way the money went is the claim's direction"
            )
        if self.low > self.high:
            raise ClaimError(
                f"amount range is inverted: {self.low.format()} > {self.high.format()}"
            )

    @property
    def currency(self) -> str:
        return self.low.currency

    @property
    def is_exact(self) -> bool:
        """Whether the speaker was recorded as giving a figure, not a hedge."""
        return self.low == self.high

    @property
    def midpoint(self) -> Money:
        """The middle of the range, floored.  Only ever used for materiality."""
        return Money(
            (self.low.minor_units + self.high.minor_units) // 2, self.currency
        )

    def contains(self, amount: Money) -> bool:
        if amount.currency != self.currency:
            raise CurrencyMismatchError(
                f"cannot test a {amount.currency} amount against a "
                f"{self.currency} range"
            )
        return self.low <= amount <= self.high

    def widened(self, tolerance: Money) -> "AmountRange":
        """The range with ``tolerance`` allowed on each side.

        The low end is floored at zero rather than allowed negative, because a
        negative lower bound is not a looser claim, it is a meaningless one.
        """
        if tolerance.currency != self.currency:
            raise CurrencyMismatchError(
                f"cannot widen a {self.currency} range by {tolerance.currency}"
            )
        if tolerance.is_negative:
            raise ClaimError("materiality tolerance cannot be negative")
        low = self.low - tolerance
        if low.is_negative:
            low = Money.zero(self.currency)
        return AmountRange(low=low, high=self.high + tolerance)

    def format(self) -> str:
        if self.is_exact:
            return self.low.format()
        return f"{self.low.format(with_currency=False)}-{self.high.format()}"


@dataclass(frozen=True)
class DateRange:
    """When it was said to have happened, including how loosely.

    "In March" is a month; "on the fifth" is a day; "some time last year" is a
    year.  All three are this type, and none of them is a date.
    """

    earliest: date
    latest: date

    def __post_init__(self) -> None:
        if self.earliest > self.latest:
            raise ClaimError(
                f"date range is inverted: {self.earliest} > {self.latest}"
            )

    @property
    def is_exact(self) -> bool:
        return self.earliest == self.latest

    @property
    def days(self) -> int:
        """How many calendar days the range spans, inclusive."""
        return (self.latest - self.earliest).days + 1

    def contains(self, when: date) -> bool:
        return self.earliest <= when <= self.latest

    def format(self) -> str:
        if self.is_exact:
            return self.earliest.isoformat()
        return f"{self.earliest.isoformat()} to {self.latest.isoformat()}"


# ---------------------------------------------------------------------------
# Materiality
# ---------------------------------------------------------------------------


#: Ten per cent, in basis points.  Deliberately generous: see the module
#: docstring on why the two errors do not cost the same.
DEFAULT_MATERIALITY_BASIS_POINTS = 1000

#: One major unit, so a claim small enough that ten per cent of it is a rounding
#: artefact still gets a usable tolerance.
DEFAULT_MATERIALITY_FLOOR_MAJOR_UNITS = 1

_BASIS_POINT_DENOMINATOR = 10_000


@dataclass(frozen=True)
class Materiality:
    """How far a ledger figure may sit outside a claim and still answer it.

    Both terms are integers and the arithmetic is integer throughout, because
    a tolerance computed in floating point would be a different tolerance on
    different machines, and this number goes into a report.
    """

    basis_points: int = DEFAULT_MATERIALITY_BASIS_POINTS
    floor_major_units: int = DEFAULT_MATERIALITY_FLOOR_MAJOR_UNITS

    def __post_init__(self) -> None:
        for name in ("basis_points", "floor_major_units"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ClaimError(f"{name} must be an int, not {type(value).__name__}")
            if value < 0:
                raise ClaimError(f"{name} cannot be negative")

    def tolerance_for(self, amounts: AmountRange) -> Money:
        """The tolerance this policy allows around ``amounts``."""
        currency = amounts.currency
        exponent = amounts.low.currency_info.exponent
        relative = (
            abs(amounts.midpoint.minor_units) * self.basis_points
        ) // _BASIS_POINT_DENOMINATOR
        floor = self.floor_major_units * (10 ** exponent)
        return Money(max(relative, floor), currency)

    def describe(self) -> str:
        percent = self.basis_points / 100
        return (
            f"{percent:g}% of the claimed midpoint, "
            f"floored at {self.floor_major_units} major unit"
            f"{'' if self.floor_major_units == 1 else 's'}"
        )


DEFAULT_MATERIALITY = Materiality()


# ---------------------------------------------------------------------------
# The claim
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """A financial assertion made in unstructured material.  Always P4.

    ``quote`` is required and is the words that were actually used.  A claim
    without them cannot be checked by the person who has to stand behind the
    report, and a paraphrase of a paraphrase is how "about twenty" becomes
    "$20,000.00" three systems downstream.

    ``payer`` and ``payee`` are the parties as named by the speaker, resolved
    upstream if they are going to be resolved at all -- this module compares
    the strings it is handed.
    """

    claim_id: uuid.UUID
    amounts: AmountRange
    dates: DateRange
    quote: str
    source_document_id: uuid.UUID
    payer: Optional[str] = None
    payee: Optional[str] = None
    speaker: Optional[str] = None
    proof_class: ProofClass = ProofClass.p4
    locator: Optional[str] = None

    def __post_init__(self) -> None:
        if self.proof_class is not ProofClass.p4:
            raise ClaimError(
                f"a claim is P4 by definition; got {self.proof_class.value}.  "
                "A structured record is a ledger entry, not a claim, and "
                "reading one as a claim would let it be corroborated by itself"
            )
        if not isinstance(self.amounts, AmountRange):
            raise ClaimError("amounts must be an AmountRange")
        if not isinstance(self.dates, DateRange):
            raise ClaimError("dates must be a DateRange")
        if not self.quote or not self.quote.strip():
            raise ClaimError(
                "a claim must carry the verbatim words it was extracted from; "
                "without them nobody downstream can check what was actually said"
            )

    @property
    def currency(self) -> str:
        return self.amounts.currency

    @property
    def named_parties(self) -> tuple[str, ...]:
        return tuple(n for n in (self.payer, self.payee) if normalise_name(n))

    def describe(self) -> str:
        payer = self.payer or "an unnamed party"
        payee = self.payee or "an unnamed party"
        return (
            f"{self.amounts.format()} from {payer} to {payee}, "
            f"{self.dates.format()}"
        )


# ---------------------------------------------------------------------------
# The verified side
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerEntry:
    """One admitted transaction, reduced to what a correlation may use.

    ``holder`` is the name of the party whose account this row sits in, and it
    is what lets a direction be tested at all: the same payment is a debit in
    the payer's statement and a credit in the payee's, so "was this a payment
    out" has no answer until we know whose account we are reading.

    ``reconciled`` records whether the period this row came from closed its
    arithmetic.  It does not exclude the row -- a p3 row is still a row -- but
    absence from an unreconciled period is not absence, so it gates
    contradiction.
    """

    transaction_id: uuid.UUID
    account_id: uuid.UUID
    ordering_date: date
    amount: Money
    direction: TransactionDirection
    proof_class: ProofClass
    holder: Optional[str] = None
    counterparty: Optional[str] = None
    description: Optional[str] = None
    reconciled: bool = True

    def __post_init__(self) -> None:
        if self.proof_class not in LEDGER_CLASSES:
            raise LedgerClassError(
                f"{self.proof_class.value} cannot appear in the ledger; an "
                "assertion cannot corroborate an assertion, and a correlation "
                "between two P4 objects is two people saying the same thing"
            )
        if self.amount.is_negative:
            raise LedgerClassError(
                "a ledger amount is a positive magnitude with the sign carried "
                f"in direction; got {self.amount.format()}"
            )


# ---------------------------------------------------------------------------
# Coverage: what makes an absence mean anything
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountCoverage:
    """What one account's records actually establish about a span of time.

    Three separate things can stop an absence from meaning anything, and they
    are kept apart because they call for different work.  ``gaps`` wants a
    subpoena for the missing statement.  ``breaks`` wants somebody to look at
    two balances that do not meet.  ``unverified`` wants the extraction fixed,
    or the document adjudicated.
    """

    account_id: uuid.UUID
    covered_from: Optional[date] = None
    covered_to: Optional[date] = None
    holder: Optional[str] = None
    gaps: Sequence[tuple[date, date]] = field(default_factory=tuple)
    breaks: Sequence[tuple[date, date]] = field(default_factory=tuple)
    overlaps: Sequence[tuple[date, date]] = field(default_factory=tuple)
    unverified: Sequence[tuple[date, date]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (self.covered_from is None) != (self.covered_to is None):
            raise CoverageError(
                "coverage must state both ends or neither; a run with a start "
                "and no end covers nothing anyone can test against"
            )
        if (
            self.covered_from is not None
            and self.covered_to is not None
            and self.covered_from > self.covered_to
        ):
            raise CoverageError(
                f"coverage is inverted: {self.covered_from} > {self.covered_to}"
            )
        for label in ("gaps", "breaks", "overlaps", "unverified"):
            for start, end in getattr(self, label):
                if start > end:
                    raise CoverageError(
                        f"{label} span is inverted: {start} > {end}"
                    )

    def spans(self, window: DateRange) -> bool:
        """Whether this account's run encloses the whole window."""
        if self.covered_from is None or self.covered_to is None:
            return False
        return self.covered_from <= window.earliest and window.latest <= self.covered_to

    #: The three conditions under which an absence over the window means
    #: nothing, and the note each raises.  Order is fixed so a report reads the
    #: same twice.
    _BLOCKING = (
        ("gaps", NOTE_COVERAGE_GAP),
        ("breaks", NOTE_COVERAGE_BREAK),
        ("unverified", NOTE_COVERAGE_UNVERIFIED),
    )

    def _touching(self, label: str, window: DateRange) -> bool:
        return any(
            start <= window.latest and window.earliest <= end
            for start, end in getattr(self, label)
        )

    def blocking_defects_in(self, window: DateRange) -> tuple[str, ...]:
        """The conditions that stop an absence over ``window`` meaning anything.

        A gap means the statement that would show the payment was never
        produced.  A break means two balances that ought to meet do not, so
        rows are unaccounted for on one side of the seam.  An unverified period
        is one whose arithmetic did not close, and a period that does not foot
        may be missing rows -- that is frequently *why* it does not foot.

        Overlaps are deliberately absent.  Two statements claiming the same
        days is a duplicate-resolution problem: the days are covered twice, and
        a row counted twice is still not a row that is missing.  It is reported
        (:meth:`defects_in`) and it does not block.
        """
        return tuple(
            note for label, note in self._BLOCKING if self._touching(label, window)
        )

    def defects_in(self, window: DateRange) -> tuple[str, ...]:
        """Everything worth reporting about the window, blocking or not."""
        found = list(self.blocking_defects_in(window))
        if self._touching("overlaps", window):
            found.append(NOTE_COVERAGE_OVERLAP)
        return tuple(found)


@dataclass(frozen=True)
class Coverage:
    """Every account in scope, and what each one covers.

    An empty scope is not an error and is not a licence to contradict: it is
    the state of a case before any statement has been admitted, and every claim
    against it is unresolved.
    """

    accounts: Sequence[AccountCoverage] = field(default_factory=tuple)

    @property
    def account_ids(self) -> tuple[uuid.UUID, ...]:
        return tuple(a.account_id for a in self.accounts)

    def supporting(self, window: DateRange) -> tuple[AccountCoverage, ...]:
        """The accounts that enclose the window with none of the three defects.

        These, and only these, are the accounts an absence can be asserted
        against.  Every contradiction names them.  An overlap does not
        disqualify an account -- see
        :meth:`AccountCoverage.blocking_defects_in`.
        """
        return tuple(
            a
            for a in self.accounts
            if a.spans(window) and not a.blocking_defects_in(window)
        )

    def defects(self, window: DateRange) -> tuple[str, ...]:
        """The distinct defect notes raised by accounts that reach the window."""
        found: list[str] = []
        for account in self.accounts:
            if account.covered_from is None or account.covered_to is None:
                continue
            if account.covered_to < window.earliest or window.latest < account.covered_from:
                continue
            for note in account.defects_in(window):
                if note not in found:
                    found.append(note)
        return tuple(found)


def coverage_from_continuity(
    continuity: AccountContinuity,
    *,
    holder: Optional[str] = None,
    unverified: Sequence[tuple[date, date]] = (),
) -> AccountCoverage:
    """Read a continuity assessment into the coverage a correlation needs.

    The two modules answer different questions and this is the join between
    them.  :mod:`services.financial.continuity` asks whether one account's
    statements form an unbroken run; correlation asks whether a *particular
    window* is safe to assert an absence over.  Gaps and breaks transfer
    directly.  Overlaps transfer too, but only as a note: two statements
    claiming the same days is a duplicate-resolution failure rather than
    evidence that a row is missing.

    ``unverified`` cannot be derived from continuity -- whether a period's
    arithmetic closed is :mod:`services.financial.reconcile`'s answer, not this
    one's -- so it is a parameter, and a caller who does not pass it is
    asserting that every period in the run reconciled.
    """
    if continuity.account_id is None:
        raise CoverageError(
            "a continuity reading with no account cannot support a coverage "
            "statement; there is nothing for an absence to be absent from"
        )

    def _span(seam) -> tuple[date, date]:
        # The days between two periods, or the days they both claim.  Both are
        # derived from the printed bounds, which is the only thing build_run
        # admits.
        earlier_end = seam.earlier.end
        later_start = seam.later.start
        if seam.kind is SeamKind.gap:
            return (earlier_end + timedelta(days=1), later_start - timedelta(days=1))
        return (later_start, earlier_end)

    gaps = tuple(_span(s) for s in continuity.gaps)
    breaks = tuple(
        (s.earlier.end, s.later.start)
        for s in continuity.seams
        if s.kind is SeamKind.contiguous and s.agreement is SeamAgreement.disagrees
    )
    overlaps = tuple(_span(s) for s in continuity.overlaps)
    return AccountCoverage(
        account_id=continuity.account_id,
        covered_from=continuity.covered_from,
        covered_to=continuity.covered_to,
        holder=holder,
        gaps=gaps,
        breaks=breaks,
        overlaps=overlaps,
        unverified=tuple(unverified),
    )


# ---------------------------------------------------------------------------
# Comparing one claim to one row
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Component:
    """One dimension compared, with the values that produced the answer.

    ``detail`` is written to be read aloud.  The whole point of a proposal
    surface is that its reasoning is visible, and a component that reports
    ``differs`` without saying what differed from what is a score with extra
    steps.
    """

    name: str
    agreement: Agreement
    detail: str

    @property
    def agrees(self) -> bool:
        return self.agreement is Agreement.agrees

    @property
    def differs(self) -> bool:
        return self.agreement is Agreement.differs


class HolderRole(str, Enum):
    """Which end of the claimed payment the account holder is."""

    payer = "payer"
    payee = "payee"
    unknown = "unknown"


def _name_agreement(left: Optional[str], right: Optional[str]) -> Agreement:
    """Three-band comparison.  The middle band is the point of it."""
    score = name_similarity(left, right)
    if score is None:
        return Agreement.unknown
    if score >= NAME_AGREEMENT_THRESHOLD:
        return Agreement.agrees
    if score <= NAME_DISAGREEMENT_THRESHOLD:
        return Agreement.differs
    return Agreement.unknown


def _resolve_role(claim: Claim, entry: LedgerEntry) -> tuple[HolderRole, Component]:
    """Decide which end of the claim the account holder is, and say why.

    Tried against the holder first, because that is direct evidence.  Where the
    holder is not named the counterparty is used to infer the role from the
    other end -- a row whose counterparty is the claimed payee is presumably in
    the payer's account -- and the detail records that the answer was inferred,
    because an inference and an observation should not read the same in a
    report.
    """
    against_payer = _name_agreement(entry.holder, claim.payer)
    against_payee = _name_agreement(entry.holder, claim.payee)

    if against_payer is Agreement.agrees and against_payee is not Agreement.agrees:
        return HolderRole.payer, Component(
            COMPONENT_HOLDER,
            Agreement.agrees,
            f"the account is held by {entry.holder!r}, the claimed payer",
        )
    if against_payee is Agreement.agrees and against_payer is not Agreement.agrees:
        return HolderRole.payee, Component(
            COMPONENT_HOLDER,
            Agreement.agrees,
            f"the account is held by {entry.holder!r}, the claimed payee",
        )
    if against_payer is Agreement.agrees and against_payee is Agreement.agrees:
        # Both ends of the claim name the same party, or two names close enough
        # that this module cannot separate them.  Anchoring the direction on
        # either would be a coin toss dressed as a finding.
        return HolderRole.unknown, Component(
            COMPONENT_HOLDER,
            Agreement.unknown,
            f"the holder {entry.holder!r} matches both claimed parties",
        )
    if against_payer is Agreement.differs and against_payee is Agreement.differs:
        return HolderRole.unknown, Component(
            COMPONENT_HOLDER,
            Agreement.differs,
            f"the account is held by {entry.holder!r}, who is neither claimed party",
        )

    # The holder settles nothing.  Try to infer from the other end.
    counterparty_is_payee = _name_agreement(entry.counterparty, claim.payee)
    counterparty_is_payer = _name_agreement(entry.counterparty, claim.payer)
    if counterparty_is_payee is Agreement.agrees and counterparty_is_payer is not Agreement.agrees:
        return HolderRole.payer, Component(
            COMPONENT_HOLDER,
            Agreement.unknown,
            f"no holder was named; inferred to be the payer because the "
            f"counterparty {entry.counterparty!r} is the claimed payee",
        )
    if counterparty_is_payer is Agreement.agrees and counterparty_is_payee is not Agreement.agrees:
        return HolderRole.payee, Component(
            COMPONENT_HOLDER,
            Agreement.unknown,
            f"no holder was named; inferred to be the payee because the "
            f"counterparty {entry.counterparty!r} is the claimed payer",
        )
    return HolderRole.unknown, Component(
        COMPONENT_HOLDER,
        Agreement.unknown,
        "neither end identifies which side of the claim this account is",
    )


def _direction_component(
    role: HolderRole, entry: LedgerEntry
) -> Component:
    """Whether the money moved the way the claim says, from this account's side."""
    if role is HolderRole.unknown:
        return Component(
            COMPONENT_DIRECTION,
            Agreement.unknown,
            "direction cannot be tested without knowing whose account this is",
        )
    expected = (
        TransactionDirection.debit
        if role is HolderRole.payer
        else TransactionDirection.credit
    )
    if entry.direction is expected:
        return Component(
            COMPONENT_DIRECTION,
            Agreement.agrees,
            f"a {entry.direction.value} in the {role.value}'s account, as claimed",
        )
    return Component(
        COMPONENT_DIRECTION,
        Agreement.differs,
        f"a {entry.direction.value} in the {role.value}'s account, where the "
        f"claim requires a {expected.value}",
    )


def _counterparty_component(
    claim: Claim, entry: LedgerEntry, role: HolderRole
) -> Component:
    """Compare the row's counterparty with whichever party it should be."""
    if role is HolderRole.payer:
        expected, label = claim.payee, "payee"
    elif role is HolderRole.payee:
        expected, label = claim.payer, "payer"
    else:
        # Role unsettled: the counterparty may legitimately be either end.
        against_payer = _name_agreement(entry.counterparty, claim.payer)
        against_payee = _name_agreement(entry.counterparty, claim.payee)
        if Agreement.agrees in (against_payer, against_payee):
            which = "payer" if against_payer is Agreement.agrees else "payee"
            return Component(
                COMPONENT_COUNTERPARTY,
                Agreement.agrees,
                f"the counterparty {entry.counterparty!r} is the claimed {which}",
            )
        if against_payer is Agreement.differs and against_payee is Agreement.differs:
            return Component(
                COMPONENT_COUNTERPARTY,
                Agreement.differs,
                f"the counterparty {entry.counterparty!r} is neither claimed party",
            )
        return Component(
            COMPONENT_COUNTERPARTY,
            Agreement.unknown,
            "the counterparty does not settle either party",
        )

    agreement = _name_agreement(entry.counterparty, expected)
    if agreement is Agreement.agrees:
        detail = f"the counterparty {entry.counterparty!r} is the claimed {label}"
    elif agreement is Agreement.differs:
        detail = (
            f"the counterparty {entry.counterparty!r} is not the claimed "
            f"{label} {expected!r}"
        )
    elif not normalise_name(entry.counterparty):
        detail = "the row names no counterparty"
    elif not normalise_name(expected):
        detail = f"the claim names no {label}"
    else:
        detail = (
            f"the counterparty {entry.counterparty!r} neither matches nor "
            f"clearly differs from the claimed {label} {expected!r}"
        )
    return Component(COMPONENT_COUNTERPARTY, agreement, detail)


@dataclass(frozen=True)
class MatchCandidate:
    """One ledger row weighed against one claim, with the workings kept.

    Named ``MatchCandidate`` rather than the bare word because
    :mod:`services.financial.quarantine` already has a ``Candidate``, and it is
    a different thing entirely -- a document awaiting admission, not a row
    awaiting comparison.  Two classes sharing a name at the package surface is
    the sort of small ambiguity that later gets somebody's import wrong.
    """

    entry: LedgerEntry
    verdict: CandidateVerdict
    components: Mapping[str, Component]
    role: HolderRole

    def component(self, name: str) -> Component:
        return self.components[name]

    @property
    def disagreements(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in COMPONENT_ORDER
            if name in self.components and self.components[name].differs
        )

    @property
    def unknowns(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in COMPONENT_ORDER
            if name in self.components
            and self.components[name].agreement is Agreement.unknown
        )

    @property
    def excluded_on_name_only(self) -> bool:
        """Set aside solely because a name did not match.

        Reported with every contradiction.  This module compares names as
        strings, so the row it declined to look at may be exactly the payment
        the claim describes, and a finding of absence that hides its own
        exclusions is not a finding anybody should sign.
        """
        disagreements = set(self.disagreements)
        return bool(disagreements) and disagreements <= set(NAME_COMPONENTS)

    def explain(self) -> str:
        lines = [
            f"  transaction {self.entry.transaction_id} "
            f"({self.entry.proof_class.value}, {self.verdict.value}):"
        ]
        for name in COMPONENT_ORDER:
            component = self.components.get(name)
            if component is None:
                continue
            lines.append(f"    {name:14s} {component.agreement.value:8s} {component.detail}")
        return "\n".join(lines)


def _weigh(
    claim: Claim, entry: LedgerEntry, *, materiality: Materiality
) -> MatchCandidate:
    """Compare one row with one claim on every dimension the two share."""
    components: dict[str, Component] = {}

    if entry.amount.currency != claim.currency:
        components[COMPONENT_CURRENCY] = Component(
            COMPONENT_CURRENCY,
            Agreement.differs,
            f"the row is in {entry.amount.currency}, the claim in {claim.currency}",
        )
        # Nothing further can be compared: an amount in another currency cannot
        # be tested against this range without a conversion, and a conversion
        # is an analytical act that has to be recorded rather than implied.
        return MatchCandidate(
            entry=entry,
            verdict=CandidateVerdict.excluded,
            components=components,
            role=HolderRole.unknown,
        )

    components[COMPONENT_CURRENCY] = Component(
        COMPONENT_CURRENCY, Agreement.agrees, f"both in {claim.currency}"
    )

    tolerance = materiality.tolerance_for(claim.amounts)
    widened = claim.amounts.widened(tolerance)
    if widened.contains(entry.amount):
        if claim.amounts.contains(entry.amount):
            detail = f"{entry.amount.format()} is within the claimed {claim.amounts.format()}"
        else:
            detail = (
                f"{entry.amount.format()} is outside the claimed "
                f"{claim.amounts.format()} but within {tolerance.format()} of it"
            )
        components[COMPONENT_AMOUNT] = Component(
            COMPONENT_AMOUNT, Agreement.agrees, detail
        )
    else:
        components[COMPONENT_AMOUNT] = Component(
            COMPONENT_AMOUNT,
            Agreement.differs,
            f"{entry.amount.format()} is outside the claimed "
            f"{claim.amounts.format()} by more than {tolerance.format()}",
        )

    if claim.dates.contains(entry.ordering_date):
        components[COMPONENT_DATE] = Component(
            COMPONENT_DATE,
            Agreement.agrees,
            f"{entry.ordering_date.isoformat()} falls in {claim.dates.format()}",
        )
    else:
        components[COMPONENT_DATE] = Component(
            COMPONENT_DATE,
            Agreement.differs,
            f"{entry.ordering_date.isoformat()} is outside {claim.dates.format()}",
        )

    role, holder_component = _resolve_role(claim, entry)
    components[COMPONENT_HOLDER] = holder_component
    components[COMPONENT_DIRECTION] = _direction_component(role, entry)
    components[COMPONENT_COUNTERPARTY] = _counterparty_component(claim, entry, role)

    return MatchCandidate(
        entry=entry,
        verdict=_verdict(components),
        components=components,
        role=role,
    )


def _verdict(components: Mapping[str, Component]) -> CandidateVerdict:
    """Reduce the components to one of the four verdicts.

    The order of the tests is the whole rule.  Anything disagreeing other than
    the amount means this is not the payment described, so it is set aside
    before the amount is considered at all -- otherwise a payment to the wrong
    person for the wrong sum would be reported as evidence that the claimed sum
    was wrong.
    """
    differing = {name for name, c in components.items() if c.differs}
    if differing - {COMPONENT_AMOUNT}:
        return CandidateVerdict.excluded

    party_agrees = any(
        components[name].agrees
        for name in NAME_COMPONENTS
        if name in components
    )
    if not party_agrees:
        # Nothing ties this row to either named party.  It may still be the
        # payment, so it is not excluded; it simply cannot be relied on.
        return CandidateVerdict.inconclusive

    if COMPONENT_AMOUNT in differing:
        return CandidateVerdict.differs_on_amount

    direction = components.get(COMPONENT_DIRECTION)
    if direction is not None and direction.agreement is Agreement.unknown:
        # The row's direction could not be tested -- we do not know whose
        # account this is -- so a credit that would refute the claim is
        # indistinguishable from the debit that would support it.
        return CandidateVerdict.inconclusive

    return CandidateVerdict.matches


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Correlation:
    """A proposal about one claim, with everything it rests on attached.

    It is a proposal and never a determination.  :attr:`outcome` is what the
    rules produce from the evidence supplied; whether it is accepted is a human
    act, recorded separately as a :class:`CorrelationDecision`.
    """

    claim: Claim
    outcome: Outcome
    candidates: Sequence[MatchCandidate] = field(default_factory=tuple)
    contradiction: Optional[ContradictionKind] = None
    unresolved_reason: Optional[UnresolvedReason] = None
    accounts_relied_on: Sequence[uuid.UUID] = field(default_factory=tuple)
    materiality: Materiality = DEFAULT_MATERIALITY
    tolerance: Optional[Money] = None
    notes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.outcome is Outcome.contradicted and self.contradiction is None:
            raise CorrelationError(
                "a contradiction must say which kind it is; an unlabelled one "
                "cannot be read against the record it is a claim about"
            )
        if self.outcome is Outcome.unresolved and self.unresolved_reason is None:
            raise CorrelationError(
                "an unresolved correlation must name its reason, because the "
                "reason is what tells an investigator what would settle it"
            )
        if self.outcome is not Outcome.contradicted and self.contradiction is not None:
            raise CorrelationError("only a contradiction carries a contradiction kind")
        if self.outcome is not Outcome.unresolved and self.unresolved_reason is not None:
            raise CorrelationError("only an unresolved correlation carries a reason")

    # -- the classes never move -------------------------------------------

    @property
    def claim_proof_class(self) -> ProofClass:
        """Always P4, corroborated or not: correlation never promotes.

        Present as a property so that a caller reading the result cannot find
        anywhere else to look for a class, and so that the invariant has a name
        a test can assert on.
        """
        return self.claim.proof_class

    def by_verdict(self, verdict: CandidateVerdict) -> tuple[MatchCandidate, ...]:
        return tuple(c for c in self.candidates if c.verdict is verdict)

    @property
    def matches(self) -> tuple[MatchCandidate, ...]:
        return self.by_verdict(CandidateVerdict.matches)

    @property
    def amount_differences(self) -> tuple[MatchCandidate, ...]:
        return self.by_verdict(CandidateVerdict.differs_on_amount)

    @property
    def inconclusive(self) -> tuple[MatchCandidate, ...]:
        return self.by_verdict(CandidateVerdict.inconclusive)

    @property
    def excluded(self) -> tuple[MatchCandidate, ...]:
        return self.by_verdict(CandidateVerdict.excluded)

    @property
    def set_aside_on_name(self) -> tuple[MatchCandidate, ...]:
        """Rows excluded for a name and nothing else.

        A contradiction should always be read next to this list.
        """
        return tuple(c for c in self.excluded if c.excluded_on_name_only)

    @property
    def is_finding(self) -> bool:
        """Whether this is something to put in front of an investigator."""
        return self.outcome in (Outcome.corroborated, Outcome.contradicted)

    def narrative(self) -> str:
        """The proposal in prose, with its limits stated rather than implied."""
        lines: list[str] = []
        speaker = self.claim.speaker or "an unattributed source"
        lines.append(
            f"Claim ({self.claim.claim_id}): {self.claim.describe()}, "
            f"asserted by {speaker}."
        )
        lines.append(f'  Quoted: "{self.claim.quote.strip()}"')

        if self.outcome is Outcome.corroborated:
            count = len(self.matches)
            lines.append(
                f"  Corroborated by {count} verified "
                f"transaction{'' if count == 1 else 's'}.  The claim remains "
                f"{self.claim_proof_class.value}: corroboration links, it does "
                "not promote."
            )
        elif self.outcome is Outcome.contradicted:
            named = ", ".join(str(a) for a in self.accounts_relied_on) or "no account"
            if self.contradiction is ContradictionKind.amount_differs:
                lines.append(
                    "  Contradicted on amount.  A transaction answers this "
                    "claim on parties, direction and date, and differs from "
                    "the stated amount by more than the allowed materiality."
                )
            else:
                lines.append(
                    "  Contradicted: no transaction answering this claim "
                    "appears in the records held."
                )
            lines.append(
                f"  This is a statement about the records, not about {speaker}.  "
                f"It is limited to account(s) {named}, which cover "
                f"{self.claim.dates.format()} without gap, break or "
                "unreconciled period."
            )
            aside = self.set_aside_on_name
            if aside:
                lines.append(
                    f"  {len(aside)} transaction(s) were set aside on a name "
                    "alone and should be read alongside this finding."
                )
        else:
            reason = self.unresolved_reason
            lines.append(f"  Unresolved ({reason.value if reason else 'unstated'}).")
            if reason is UnresolvedReason.candidate_inconclusive:
                lines.append(
                    "  At least one transaction could answer this claim and the "
                    "evidence does not settle it either way."
                )
            elif reason in (
                UnresolvedReason.records_incomplete,
                UnresolvedReason.outside_coverage,
            ):
                lines.append(
                    "  No absence can be asserted over these dates: the records "
                    "do not cover them completely."
                )
            elif reason is UnresolvedReason.claim_not_testable:
                lines.append(
                    "  The claim does not carry enough to search on."
                )

        if self.tolerance is not None:
            lines.append(
                f"  Materiality allowed: {self.tolerance.format()} "
                f"({self.materiality.describe()})."
            )
        for note in sorted(self.notes):
            lines.append(f"  Note: {note}.")
        for candidate in self.candidates:
            if candidate.verdict is not CandidateVerdict.excluded:
                lines.append(candidate.explain())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Correlating
# ---------------------------------------------------------------------------


def _is_testable(claim: Claim, entries: Sequence[LedgerEntry]) -> bool:
    """Whether the claim carries enough for an absence to mean anything.

    A named party is enough on its own.  Failing that, the claim must at least
    be anchorable to an account whose holder we know, so that "no payment of
    this size left this account" is a sentence with a subject.  A claim naming
    nobody, against rows naming nobody, supports no finding at all -- it would
    assert that no payment of roughly this size happened anywhere, which is not
    what anybody said.

    This is one gate of four and it promises nothing on its own.  In particular
    a claim naming nobody clears it whenever some row names a holder, and then
    almost always fails the *next* gate instead: no name component can agree
    against a claim with no names, so every row that is not excluded outright
    comes back inconclusive and leaves the question open.  The two gates are
    not redundant -- they refuse for different reasons, and the reason is what
    the reader is told.
    """
    if claim.named_parties:
        return True
    return any(normalise_name(entry.holder) for entry in entries)


def correlate(
    claim: Claim,
    entries: Sequence[LedgerEntry],
    *,
    coverage: Coverage,
    materiality: Materiality = DEFAULT_MATERIALITY,
) -> Correlation:
    """Weigh one P4 claim against the verified ledger.

    ``entries`` should be the rows from the accounts in ``coverage``; passing
    rows from an account the coverage does not describe would let a corroboration
    rest on a record whose completeness was never assessed.  That is not
    refused, because a corroboration does not depend on completeness the way an
    absence does -- but a contradiction names the accounts it relied on, and
    those come from the coverage, never from the rows.
    """
    if not isinstance(claim, Claim):
        raise ClaimError(f"expected a Claim, got {type(claim).__name__}")
    if not isinstance(coverage, Coverage):
        raise CoverageError(f"expected a Coverage, got {type(coverage).__name__}")

    tolerance = materiality.tolerance_for(claim.amounts)
    candidates = tuple(
        _weigh(claim, entry, materiality=materiality) for entry in entries
    )
    notes: set[str] = set()

    matches = tuple(c for c in candidates if c.verdict is CandidateVerdict.matches)
    inconclusive = tuple(
        c for c in candidates if c.verdict is CandidateVerdict.inconclusive
    )
    amount_differences = tuple(
        c for c in candidates if c.verdict is CandidateVerdict.differs_on_amount
    )
    set_aside = tuple(
        c
        for c in candidates
        if c.verdict is CandidateVerdict.excluded and c.excluded_on_name_only
    )
    if set_aside:
        notes.add(NOTE_SET_ASIDE_ON_NAME)
    if entries and not any(e.holder for e in entries):
        # Direction is meaningless until we know whose account we are reading,
        # and nothing here names a holder.  Every direction component in this
        # run was decided by inference from the counterparty or not at all, and
        # a reader is entitled to know that before relying on the answer.
        notes.add(NOTE_DIRECTION_UNANCHORED)

    def _build(
        outcome: Outcome,
        *,
        contradiction: Optional[ContradictionKind] = None,
        reason: Optional[UnresolvedReason] = None,
        accounts: Sequence[uuid.UUID] = (),
    ) -> Correlation:
        return Correlation(
            claim=claim,
            outcome=outcome,
            candidates=candidates,
            contradiction=contradiction,
            unresolved_reason=reason,
            accounts_relied_on=tuple(accounts),
            materiality=materiality,
            tolerance=tolerance,
            notes=frozenset(notes),
        )

    # -- corroboration first.  A match settles the claim, and does so without
    #    any reference to coverage: a payment that is in the records is in them
    #    whether or not the surrounding months are complete.
    if matches:
        if len(matches) > 1:
            notes.add(NOTE_SEVERAL_MATCHES)
        if any(not claim.amounts.contains(m.entry.amount) for m in matches):
            # The row agrees only because the stated range was widened.  That
            # is a legitimate corroboration and it is not the same as the
            # witness naming the figure, so the report has to distinguish them.
            notes.add(NOTE_AMOUNT_OUTSIDE_STATED_RANGE)
        if all(
            m.components[COMPONENT_COUNTERPARTY].agreement is Agreement.unknown
            for m in matches
        ):
            # A holder-anchored row with no parsed counterparty still matches --
            # requiring one would discard most bank CSVs and with them the
            # feature -- but what was not tested must not read as tested.
            notes.add(NOTE_COUNTERPARTY_UNTESTED)
        if all(not m.entry.reconciled for m in matches):
            notes.add(NOTE_MATCHED_ONLY_UNVERIFIED)
        return _build(Outcome.corroborated)

    # -- a maybe is not an absence.
    if inconclusive:
        return _build(
            Outcome.unresolved, reason=UnresolvedReason.candidate_inconclusive
        )

    # -- everything below asserts an absence, so the record has to earn it.
    if not coverage.accounts:
        notes.add(NOTE_NO_ACCOUNTS)
        return _build(Outcome.unresolved, reason=UnresolvedReason.outside_coverage)

    supporting = coverage.supporting(claim.dates)
    if not supporting:
        defects = coverage.defects(claim.dates)
        notes.update(defects)
        reason = (
            UnresolvedReason.records_incomplete
            if defects
            else UnresolvedReason.outside_coverage
        )
        return _build(Outcome.unresolved, reason=reason)

    if not _is_testable(claim, entries):
        return _build(Outcome.unresolved, reason=UnresolvedReason.claim_not_testable)

    # Deliberately no defect notes here.  Every account this finding rests on
    # spans the window without gap, break or unreconciled period -- that is what
    # `supporting` means -- so a note raised by some *other* account would read
    # as a qualification of the finding when it qualifies nothing.  The limit
    # that does apply is that the scope is only the accounts we hold, and the
    # narrative names them.
    notes.add(NOTE_SCOPE_IS_PARTIAL)
    accounts = tuple(a.account_id for a in supporting)

    if amount_differences:
        return _build(
            Outcome.contradicted,
            contradiction=ContradictionKind.amount_differs,
            accounts=accounts,
        )
    return _build(
        Outcome.contradicted,
        contradiction=ContradictionKind.no_transaction,
        accounts=accounts,
    )


def correlate_all(
    claims: Sequence[Claim],
    entries: Sequence[LedgerEntry],
    *,
    coverage: Coverage,
    materiality: Materiality = DEFAULT_MATERIALITY,
) -> tuple[Correlation, ...]:
    """Correlate every claim, in the order given.

    Claims are weighed independently.  One claim corroborated by a transaction
    does not consume it: two people describing the same payment should both be
    corroborated by it, and a scheme that spent the row on whoever was
    processed first would make the answer depend on the order of an interview
    schedule.
    """
    return tuple(
        correlate(claim, entries, coverage=coverage, materiality=materiality)
        for claim in claims
    )


# ---------------------------------------------------------------------------
# The human's answer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorrelationDecision:
    """A person's verdict on a proposal, recorded as an event.

    Appended in the manner of an entity merge: the proposal is not
    edited and the decision does not replace it.  Both survive, so a report can
    show what the system proposed, what a person decided, and who they were.
    """

    claim_id: uuid.UUID
    decision: DecisionKind
    decided_by: str
    decided_at: datetime
    transaction_id: Optional[uuid.UUID] = None
    note: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.decided_by or not self.decided_by.strip():
            raise CorrelationError(
                "a decision must record who made it; an anonymous confirmation "
                "is indistinguishable from the system confirming itself"
            )


@dataclass(frozen=True)
class AdjudicatedCorrelation:
    """A proposal and the decisions taken on it, side by side.

    Neither is derived from the other and neither overwrites the other.  A
    caller that wants to know what a person concluded reads
    :attr:`decisions`; a caller that wants to know what the evidence supported
    reads :attr:`proposal`.  They are allowed to differ, and when they do that
    is itself the record.
    """

    proposal: Correlation
    decisions: Sequence[CorrelationDecision] = field(default_factory=tuple)

    @property
    def is_decided(self) -> bool:
        return bool(self.decisions)

    @property
    def confirmed(self) -> tuple[CorrelationDecision, ...]:
        return tuple(
            d for d in self.decisions if d.decision is DecisionKind.confirmed
        )

    @property
    def rejected(self) -> tuple[CorrelationDecision, ...]:
        return tuple(d for d in self.decisions if d.decision is DecisionKind.rejected)

    @property
    def stands(self) -> bool:
        """Whether the proposal survives the decisions taken on it.

        An undecided proposal does not stand.  It has not been looked at, and
        a surface whose unreviewed proposals counted as accepted would be the
        auto-confirmation this module exists to resist, arrived at by leaving
        the queue alone.
        """
        return bool(self.confirmed) and not self.rejected


def apply_decisions(
    proposal: Correlation,
    decisions: Sequence[CorrelationDecision],
) -> AdjudicatedCorrelation:
    """Attach the decisions belonging to this proposal, refusing the rest.

    A decision carrying another claim's id is a routing bug, and silently
    dropping it would attach a person's name to a conclusion they did not
    reach on a claim they may never have seen.
    """
    for decision in decisions:
        if decision.claim_id != proposal.claim.claim_id:
            raise CorrelationError(
                f"decision names claim {decision.claim_id}, proposal is for "
                f"{proposal.claim.claim_id}"
            )
        if decision.transaction_id is not None and decision.transaction_id not in {
            c.entry.transaction_id for c in proposal.candidates
        }:
            raise CorrelationError(
                f"decision names transaction {decision.transaction_id}, which "
                "was not among the candidates weighed for this claim"
            )
    return AdjudicatedCorrelation(proposal=proposal, decisions=tuple(decisions))
