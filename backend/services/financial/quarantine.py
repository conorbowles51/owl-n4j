"""Localising a failing balance identity, and setting evidence aside safely.

``reconcile`` produces a residual and stops, on the principle that computing a
number and deciding what it means are different jobs.  This module does the
second one, and it is shaped almost entirely by a measurement rather than by a
theory: against the twelve documents in the ET-Fraud corpus whose identity
fails for no recorded reason, the localisation techniques an accountant would
reach for first return **nothing at all nine times out of twelve**.

The measurement is worth stating in full, because everything below follows
from it.  Of the twelve failures, two have exactly one row whose amount equals
the residual; one has three such rows and five more that would explain it as a
sign flip, because the residual is $20.00 and $20.00 is a common amount; and
nine have no matching row at all.  Widening the search makes it worse rather
than better: allowing pairs and then triples leaves the same nine at zero
while the ambiguous document climbs from three candidates to twelve to twenty.
Subset search is a combinatorial noise generator, so this module deliberately
does not do it, and the docstring says so to stop it being added later as an
obvious improvement.

Three consequences.

**Unlocalised is the normal answer, so it is a result rather than an error.**
A module that raised when it could not localise a delta would raise on three
quarters of the real failures.  ``LocalisationStrength.none`` is a finding: it
says the arithmetic gives no purchase here and a human has to read the
document.  That is worth reporting precisely because it is not a bug.

**A candidate is never a cause.**  A row whose amount happens to equal the
residual is a coincidence until something else corroborates it, and the
corpus shows how ordinary that coincidence is.  So candidates are reported
with the count of rows competing for the same explanation, and a candidate can
never be the grounds for a quarantine.  This is enforced by construction:
``QuarantineBasis`` has no constructor that takes one.  The reason matters more
than it first appears.  Quarantining a row removes it from the totals, so
quarantining the row whose amount equals the residual makes the period balance
— every time, by arithmetic necessity.  A localiser permitted to act on its own
guesses would therefore turn every failing statement into a clean one, and the
document that most needed scrutiny would be the one that looked best.  For
``USA-ET-004539`` it would have had eight rows to choose from and no basis for
choosing.

**The only proof-grade signal is one this corpus does not carry.**  Where a
statement prints a running balance beside each row, the column is a chain of
small identities — previous balance plus this row equals this balance — and a
break in the chain localises the fault to one row boundary by arithmetic, not
by resemblance.  Every row in this corpus lacks it: 30,570 rows across 325
documents, not one balance column among them.  The walk is implemented anyway,
for two reasons.  The ledger has carried ``running_balance_minor`` since the
schema was written, and the native formats still to come (camt.053, BAI2,
MT940) all carry balances as a matter of course.  The nine unlocalisable
failures are, in that light, an argument for parsing those formats natively
rather than a limitation of this module.

What this module does not do: decide.  It reports strength honestly and
refuses to quarantine without grounds, but a document whose delta is
unexplained is quarantined by a person, and ``adjudication`` holds the record
of why.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from postgres.models.enums import (
    LedgerStatus,
    QuarantineReason,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.money import Money
from services.financial.reconcile import IdentityOutcome

if TYPE_CHECKING:  # pragma: no cover - typing only
    from postgres.models.financial import FinancialTransaction


class QuarantineError(Exception):
    """Base for refusals to set evidence aside, or to localise incoherently."""


class UngroundedQuarantineError(QuarantineError):
    """An attempt to quarantine on something that is not grounds."""


class LocalisationError(QuarantineError):
    """The inputs to localisation do not describe one coherent period."""


# ---------------------------------------------------------------------------
# What localisation needs to see
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowObservation:
    """One ledger row, reduced to the fields localisation actually reads.

    Deliberately not the ORM object.  Localisation is arithmetic and belongs
    under test without a database, and a narrow record also makes it plain
    that no description, counterparty or date reaches this logic — nothing
    here can be influenced by what a row *says*, only by what it *sums to*.
    """

    ref_id: str
    row_index: int
    amount: Money
    direction: TransactionDirection
    running_balance: Optional[Money] = None
    page: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Money):
            raise LocalisationError(
                f"row {self.ref_id!r} carries {type(self.amount).__name__} as "
                "an amount; localisation is exact and needs Money"
            )
        if self.amount.minor_units < 0:
            raise LocalisationError(
                f"row {self.ref_id!r} has a negative amount; magnitude lives "
                "in the amount and sign lives in the direction"
            )
        if not isinstance(self.direction, TransactionDirection):
            raise LocalisationError(
                f"row {self.ref_id!r} has direction {self.direction!r}, which "
                "is neither credit nor debit"
            )
        if self.running_balance is not None:
            if not isinstance(self.running_balance, Money):
                raise LocalisationError(
                    f"row {self.ref_id!r} carries a running balance that is "
                    "not Money"
                )
            if self.running_balance.currency != self.amount.currency:
                raise LocalisationError(
                    f"row {self.ref_id!r} is {self.amount.currency} but its "
                    f"running balance is {self.running_balance.currency}"
                )

    @property
    def signed(self) -> Money:
        """The row's effect on the balance: credits add, debits subtract."""
        if self.direction is TransactionDirection.credit:
            return self.amount
        return -self.amount

    @property
    def carries_balance(self) -> bool:
        return self.running_balance is not None


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BalanceBreak:
    """A proved discontinuity in the printed running-balance chain.

    ``expected`` is the previous printed balance plus this row; ``printed`` is
    what the statement shows beside this row.  They differ, so either the row
    is wrong or a row is missing between the two — the break localises the
    fault to that boundary without claiming which of the two it is.
    """

    after_ref: str
    row_index: int
    expected: Money
    printed: Money
    before_ref: Optional[str] = None

    @property
    def discrepancy(self) -> Money:
        """Printed minus expected: what the chain gains or loses here."""
        return self.printed - self.expected

    @property
    def at_opening(self) -> bool:
        """The chain breaks against the opening balance rather than a row."""
        return self.before_ref is None


class CandidateKind(str, Enum):
    """How a row would have to be wrong for it to explain the residual."""

    # The row is present and should not be, or an identical one is missing.
    equals_residual = "equals_residual"
    # The row's direction is flipped: reversing a credit of x moves the net
    # by twice x, so a residual of twice an amount fits a sign error.
    sign_flip = "sign_flip"


@dataclass(frozen=True, slots=True)
class Candidate:
    """A row that would explain the residual.  Not a finding; a coincidence
    that has not yet been ruled out."""

    ref_id: str
    row_index: int
    kind: CandidateKind


class Signature(str, Enum):
    """A hint about the *kind* of error, carrying no location at all."""

    # A residual divisible by nine is the classic trace of two digits
    # transposed.  It says look for a mistyped figure; it does not say where.
    transposition = "transposition"
    # The residual is exactly the opening balance, which is what applying the
    # identity without the opening figure produces.
    opening_omitted = "opening_omitted"
    # The residual is exactly twice the opening balance: the figure was
    # applied with the wrong sign.
    opening_sign_flipped = "opening_sign_flipped"


class LocalisationStrength(str, Enum):
    """How much the arithmetic actually established.

    The ordering is epistemic, not numeric.  ``proved`` means the statement's
    own printed chain contradicts specific rows and the breaks account for the
    whole residual.  ``partial`` means breaks were found that do not add up to
    it, so something else is wrong too.  ``conjectural`` means no proof and
    some rows that would fit.  ``none`` means the arithmetic offers nothing,
    which for this corpus is the common case.
    """

    proved = "proved"
    partial = "partial"
    conjectural = "conjectural"
    none = "none"


@dataclass(frozen=True, slots=True)
class Localisation:
    """Where a residual might have come from, and how firmly."""

    residual: Money
    strength: LocalisationStrength
    breaks: tuple[BalanceBreak, ...]
    candidates: tuple[Candidate, ...]
    signatures: tuple[Signature, ...]
    rows_seen: int
    rows_with_balance: int

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def is_proved(self) -> bool:
        return self.strength is LocalisationStrength.proved

    @property
    def is_actionable(self) -> bool:
        """Whether this is grounds for anything.  Only a proof is.

        Named separately from ``is_proved`` because the question a caller asks
        is not "how good is this" but "may I act on it", and the answer has to
        be one that a conjecture cannot accidentally satisfy.
        """
        return self.is_proved

    @property
    def chain_was_available(self) -> bool:
        """Whether the statement printed enough balances to walk the chain."""
        return self.rows_with_balance > 0

    def render(self) -> str:
        """A deterministic plain-text account, safe to put in a report.

        Carries reference ids and amounts only: no descriptions, no
        counterparties, nothing that would put case content in a log.
        """
        lines = [
            f"residual {self.residual}",
            f"strength {self.strength.value}",
            f"rows {self.rows_seen} ({self.rows_with_balance} with a printed "
            "balance)",
        ]
        if not self.chain_was_available:
            lines.append(
                "no running balance was printed, so the chain could not be "
                "walked and nothing here is proved"
            )
        for brk in self.breaks:
            # Name the row the break lands on, not just its predecessor: that
            # row is the one a reader has to go and look at, and ref_id is the
            # handle they will cite it by.
            after = "the opening balance" if brk.at_opening else str(brk.before_ref)
            lines.append(
                f"break at {brk.after_ref} (row {brk.row_index}), following "
                f"{after}: expected {brk.expected}, printed {brk.printed}, "
                f"off by {brk.discrepancy}"
            )
        if self.candidates:
            lines.append(
                f"{self.candidate_count} row(s) would fit the residual; a fit "
                "is not a cause"
            )
            for cand in self.candidates:
                lines.append(
                    f"  candidate {cand.ref_id} at row {cand.row_index} "
                    f"({cand.kind.value})"
                )
        for sig in self.signatures:
            lines.append(f"signature {sig.value}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Localising
# ---------------------------------------------------------------------------


def _walk_chain(
    rows: Sequence[RowObservation], opening: Optional[Money]
) -> tuple[BalanceBreak, ...]:
    """Follow the printed running balances and report every discontinuity.

    Rows without a printed balance are skipped rather than treated as breaks:
    a statement that prints a balance on some lines and not others is common,
    and the chain still holds across the gap because the intervening rows are
    added into the expectation.
    """
    breaks: list[BalanceBreak] = []
    previous_balance = opening
    previous_ref: Optional[str] = None
    pending = None

    for row in rows:
        pending = row.signed if pending is None else pending + row.signed
        if row.running_balance is None:
            continue
        if previous_balance is not None:
            expected = previous_balance + pending
            if expected != row.running_balance:
                breaks.append(
                    BalanceBreak(
                        after_ref=row.ref_id,
                        row_index=row.row_index,
                        expected=expected,
                        printed=row.running_balance,
                        before_ref=previous_ref,
                    )
                )
        previous_balance = row.running_balance
        previous_ref = row.ref_id
        pending = None

    return tuple(breaks)


def _candidates(
    rows: Sequence[RowObservation], residual: Money
) -> tuple[Candidate, ...]:
    """Rows whose amount fits the residual, singly or as a sign error.

    Single rows only.  Pairs and triples were measured against the corpus and
    add candidates without adding explanations; see the module docstring.
    """
    magnitude = abs(residual)
    if magnitude.minor_units == 0:
        return ()

    found: list[Candidate] = []
    for row in rows:
        if row.amount == magnitude:
            found.append(
                Candidate(
                    ref_id=row.ref_id,
                    row_index=row.row_index,
                    kind=CandidateKind.equals_residual,
                )
            )
        elif row.amount * 2 == magnitude:
            found.append(
                Candidate(
                    ref_id=row.ref_id,
                    row_index=row.row_index,
                    kind=CandidateKind.sign_flip,
                )
            )
    return tuple(found)


def _signatures(residual: Money, opening: Optional[Money]) -> tuple[Signature, ...]:
    found: list[Signature] = []
    units = abs(residual.minor_units)
    if units and units % 9 == 0:
        found.append(Signature.transposition)
    if opening is not None and opening.minor_units != 0:
        if abs(residual) == abs(opening):
            found.append(Signature.opening_omitted)
        elif abs(residual) == abs(opening) * 2:
            found.append(Signature.opening_sign_flipped)
    return tuple(found)


def localise(
    *,
    residual: Money,
    rows: Iterable[RowObservation],
    opening: Optional[Money] = None,
) -> Localisation:
    """Account for a residual as precisely as the arithmetic honestly allows.

    Pure, and ordered: rows are walked in the sequence given, which must be the
    statement's own order, because the running-balance chain is meaningless in
    any other.  Callers reading from the ledger should order by ``row_index``.
    """
    ordered = tuple(rows)
    if not isinstance(residual, Money):
        raise LocalisationError(
            f"residual is {type(residual).__name__}; localisation is exact "
            "and needs Money"
        )
    for row in ordered:
        if row.amount.currency != residual.currency:
            raise LocalisationError(
                f"row {row.ref_id!r} is {row.amount.currency} but the residual "
                f"is {residual.currency}; a period holding two currencies has "
                "no identity to localise"
            )
    if opening is not None and opening.currency != residual.currency:
        raise LocalisationError(
            f"opening balance is {opening.currency} but the residual is "
            f"{residual.currency}"
        )

    breaks = _walk_chain(ordered, opening)
    candidates = _candidates(ordered, residual)
    signatures = _signatures(residual, opening)
    with_balance = sum(1 for row in ordered if row.carries_balance)

    if breaks:
        accounted = breaks[0].discrepancy
        for brk in breaks[1:]:
            accounted = accounted + brk.discrepancy
        # The chain's losses have to account for the identity's residual before
        # the breaks can be said to explain it.  Magnitudes are compared
        # because the two run opposite ways by construction: a spurious credit
        # inflates the computed closing balance, giving a positive residual,
        # while the printed chain declines to include it, giving a negative
        # discrepancy of the same size.  A subset that does not sum is still
        # evidence, and it is not the whole story.
        strength = (
            LocalisationStrength.proved
            if abs(accounted) == abs(residual)
            else LocalisationStrength.partial
        )
    elif candidates:
        strength = LocalisationStrength.conjectural
    else:
        strength = LocalisationStrength.none

    return Localisation(
        residual=residual,
        strength=strength,
        breaks=breaks,
        candidates=candidates,
        signatures=signatures,
        rows_seen=len(ordered),
        rows_with_balance=with_balance,
    )


# ---------------------------------------------------------------------------
# Grounds
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QuarantineBasis:
    """Grounds for setting evidence aside.

    There is no public constructor taking a candidate, and that omission is
    the whole design.  Quarantining the row whose amount equals the residual
    makes the period balance by arithmetic necessity, so a system that could
    quarantine on resemblance would convert every failing statement into a
    clean one and would do it most confidently where the coincidence was most
    ordinary.  Grounds are therefore a proof or a person, and nothing else.
    """

    reason: QuarantineReason
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.reason, QuarantineReason):
            raise UngroundedQuarantineError(
                f"reason {self.reason!r} is not one of the recorded quarantine "
                "reasons"
            )
        if not self.detail or not self.detail.strip():
            raise UngroundedQuarantineError(
                f"a {self.reason.value} quarantine needs a detail; a status "
                "with no stated grounds cannot be reviewed later"
            )

    @classmethod
    def from_proof(cls, localisation: Localisation) -> "QuarantineBasis":
        """Grounds drawn from a proved break in the statement's own chain."""
        if not isinstance(localisation, Localisation):
            raise UngroundedQuarantineError(
                "grounds must come from a Localisation, got "
                f"{type(localisation).__name__}"
            )
        if not localisation.is_actionable:
            raise UngroundedQuarantineError(
                f"localisation is {localisation.strength.value}, which is not "
                "grounds for quarantine; quarantining a row that merely fits "
                "the residual would make the period balance and hide the "
                "very failure the identity detected"
            )
        first = localisation.breaks[0]
        return cls(
            reason=QuarantineReason.balance_break,
            detail=(
                f"printed running balance breaks at row {first.row_index}: "
                f"expected {first.expected}, statement prints {first.printed}"
            ),
        )

    @classmethod
    def from_adjudication(cls, *, actor: str, reason: str) -> "QuarantineBasis":
        """Grounds a person took responsibility for."""
        if not actor or not actor.strip():
            raise UngroundedQuarantineError(
                "an adjudicated quarantine has to name who decided it"
            )
        if not reason or not reason.strip():
            raise UngroundedQuarantineError(
                "an adjudicated quarantine has to record why"
            )
        return cls(
            reason=QuarantineReason.adjudicated,
            detail=f"{actor.strip()}: {reason.strip()}",
        )

    @classmethod
    def unreadable_row(cls, detail: str) -> "QuarantineBasis":
        """The row could not be read exactly enough to be summed."""
        return cls(reason=QuarantineReason.unreadable_row, detail=detail)

    @classmethod
    def currency_mismatch(cls, *, row_currency: str, period_currency: str) -> "QuarantineBasis":
        return cls(
            reason=QuarantineReason.currency_mismatch,
            detail=(
                f"row is {row_currency} in a {period_currency} period; summing "
                "across currencies produces a number that means nothing"
            ),
        )

    @classmethod
    def unexplained_delta(cls, outcome: IdentityOutcome) -> "QuarantineBasis":
        """Document-level grounds: the identity failed and nothing explained it."""
        if outcome.status is not ReconciliationStatus.unbalanced:
            raise UngroundedQuarantineError(
                f"identity is {outcome.status.value}, not unbalanced; only a "
                "failing identity is grounds, and an unavailable one is a "
                "fact about the statement rather than a fault in it"
            )
        return cls(
            reason=QuarantineReason.unexplained_delta,
            detail=f"balance identity fails by {outcome.delta}",
        )


# ---------------------------------------------------------------------------
# Setting aside
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RescueWarning:
    """A quarantine that would turn a failing identity into a passing one.

    Sometimes legitimate — a row proved wrong by the chain *should* come out,
    and the period may then balance correctly.  It is recorded rather than
    forbidden because the distinction between removing bad evidence and
    removing inconvenient evidence is not visible in the arithmetic, only in
    the grounds, and whoever reviews this later needs to see that the balance
    was reached by subtraction.
    """

    residual_before: Money
    removed: Money

    @property
    def would_balance(self) -> bool:
        return self.residual_before - self.removed == Money.zero(
            self.residual_before.currency
        )


def would_rescue(
    *, outcome: IdentityOutcome, rows: Sequence[RowObservation]
) -> Optional[RescueWarning]:
    """Whether removing these rows would make a failing period balance.

    Pure, and called before the write rather than after, so that the fact can
    be recorded alongside the decision instead of being reconstructed from two
    states of the ledger.
    """
    if outcome.delta is None or outcome.delta.minor_units == 0:
        return None
    removed = Money.zero(outcome.delta.currency)
    for row in rows:
        if row.amount.currency != outcome.delta.currency:
            raise LocalisationError(
                f"row {row.ref_id!r} is {row.amount.currency} but the period "
                f"is {outcome.delta.currency}"
            )
        removed = removed + row.signed
    warning = RescueWarning(residual_before=outcome.delta, removed=removed)
    return warning if warning.would_balance else None


def quarantine_transaction(
    transaction: "FinancialTransaction",
    basis: QuarantineBasis,
) -> "FinancialTransaction":
    """Set one row aside, recording the grounds on the row itself.

    Idempotent for a row already quarantined on the same grounds, and a
    refusal for one quarantined on different grounds: overwriting the first
    reason would erase the earlier decision, and this ledger appends.
    """
    if not isinstance(basis, QuarantineBasis):
        raise UngroundedQuarantineError(
            "quarantine needs a QuarantineBasis, got "
            f"{type(basis).__name__}; a bare string is not grounds"
        )
    current = transaction.ledger_status
    if current == LedgerStatus.quarantined.value:
        if transaction.quarantine_reason != basis.reason.value:
            raise UngroundedQuarantineError(
                f"row is already quarantined as "
                f"{transaction.quarantine_reason!r}; re-quarantining it as "
                f"{basis.reason.value!r} would erase the earlier decision"
            )
        return transaction
    if current != LedgerStatus.admitted.value:
        raise UngroundedQuarantineError(
            f"row is {current!r}, not admitted; quarantining it would "
            "overwrite a status that already excludes it from every total"
        )
    transaction.ledger_status = LedgerStatus.quarantined.value
    transaction.quarantine_reason = basis.reason.value
    return transaction


def release_transaction(
    transaction: "FinancialTransaction",
    *,
    actor: str,
    reason: str,
) -> "FinancialTransaction":
    """Return a quarantined row to the admitted set.

    Requires an actor and a reason for the same purpose the quarantine did:
    admitting evidence back into every downstream total is a decision, and a
    decision with nobody's name on it cannot be reviewed.
    """
    if transaction.ledger_status != LedgerStatus.quarantined.value:
        raise UngroundedQuarantineError(
            f"row is {transaction.ledger_status!r}, not quarantined; there is "
            "nothing to release"
        )
    if not actor or not actor.strip() or not reason or not reason.strip():
        raise UngroundedQuarantineError(
            "releasing a row has to record who did it and why"
        )
    transaction.ledger_status = LedgerStatus.admitted.value
    transaction.quarantine_reason = None
    return transaction


def quarantined_row_ids(
    rows: Iterable["FinancialTransaction"],
) -> tuple[uuid.UUID, ...]:
    """The ids of rows currently set aside, in a stable order."""
    return tuple(
        sorted(
            (
                row.id
                for row in rows
                if row.ledger_status == LedgerStatus.quarantined.value
            ),
            key=str,
        )
    )
