"""The balance identity: the check a language model cannot talk its way out of.

For one statement period the arithmetic is not negotiable::

    opening + (credits - debits) = closing

Every quantity is an integer count of minor units, so the comparison is exact
and the result is a yes or a no rather than a score.  This matters because the
failure this subsystem exists to catch produces no other signal.  A dropped
transaction does not arrive flagged as low confidence; it does not arrive at
all, and an extractor that silently returns forty rows where the page held
forty-two is indistinguishable, from the inside, from one that got it right.
Confidence cannot detect an absence.  Arithmetic can, because the absent row
is still present in the printed closing balance.

Three rules give the check its teeth.

**It declines rather than assumes.**  If either balance was not printed, the
identity does not run and the period is recorded ``unavailable``.  Substituting
zero for a missing opening balance would produce a delta exactly equal to the
real opening — a number that looks like a large unexplained discrepancy, and
which sends whoever reads it hunting for fraud in a period where the only
thing wrong is that nobody could read the top of the page.  ``unavailable`` is
a worse-looking answer and a far more useful one.

**It counts only admitted rows.**  ``ledger_status`` decides what is evidence.
Quarantined, superseded and rejected rows are excluded from the totals, and
the count of what was excluded travels with the result, so a period that
balances only because six rows were set aside cannot present itself as clean.

**It says whether it proved anything.**  An identity computed over a
carried-forward opening balance is arithmetic against the neighbouring
period's closing figure rather than against this statement.  It is worth
computing and it is not independent evidence, and ``IdentityOutcome.independent``
is the difference.  Only a period whose opening and closing were both printed
supports the claim that these rows, on their own, are complete.

What this module does not do: it does not decide what to do about a failure.
Localising a delta to the rows that could explain it, and quarantining on that
basis, is the next stage.  Here the job is to produce the number honestly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Mapping, Optional

from sqlalchemy import func, select

from postgres.models.enums import (
    LedgerStatus,
    ReconciliationStatus,
    TransactionDirection,
)
from postgres.models.financial import (
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial.money import Money, get_currency
from services.financial.periods import (
    BalanceObservation,
    read_closing,
    read_opening,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


class ReconciliationError(Exception):
    """Base for failures that make the identity meaningless rather than false."""


class MixedCurrencyError(ReconciliationError):
    """An admitted transaction is denominated differently from its period."""


class LedgerOverflowError(ReconciliationError):
    """A total is too large for the column that would hold it."""


# The ledger's integer columns are signed 64-bit.  Python integers are not,
# so a total can be computed that cannot be stored; catching that here names
# the column and the value instead of surfacing a driver-level error at some
# later commit.
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _fits(value: int, column: str) -> int:
    if not _INT64_MIN <= value <= _INT64_MAX:
        raise LedgerOverflowError(
            f"{column} would be {value}, outside the range of a signed 64-bit "
            "column; this is a corrupt amount rather than a real total"
        )
    return value


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransactionTotals:
    """What the rows of one period sum to, and what was left out.

    ``excluded`` maps ledger status to a count of rows carrying it.  It exists
    so that a balanced period which reached that state by setting rows aside
    cannot be read as a clean one: the identity holding over the admitted rows
    is a different claim from the statement having been read completely.
    """

    currency: str
    credits: Money
    debits: Money
    counted: int
    excluded: Mapping[str, int]

    @property
    def net(self) -> Money:
        """Signed movement across the period: credits in, debits out."""
        return self.credits - self.debits

    @property
    def excluded_count(self) -> int:
        return sum(self.excluded.values())

    @property
    def is_complete(self) -> bool:
        """True when every row in the period counted toward the total."""
        return self.excluded_count == 0


def empty_totals(currency: str) -> TransactionTotals:
    """Totals for a period holding no rows at all.

    A dormant month is a real thing, and it is also what a total extraction
    failure looks like.  The two are separated by the identity rather than
    here: no rows and equal balances is a genuine balance, no rows and
    differing balances is a delta equal to the whole month's movement.
    """
    code = get_currency(currency).code
    return TransactionTotals(
        currency=code,
        credits=Money.zero(code),
        debits=Money.zero(code),
        counted=0,
        excluded={},
    )


def total_transactions(
    session: "Session",
    *,
    period_id: uuid.UUID,
    currency: str,
) -> TransactionTotals:
    """Sum the admitted rows of one period, grouped in the database.

    The sum is done by the database rather than by loading rows, because the
    number of rows in a period is unbounded and the totals are all that the
    identity needs.  Grouping by status as well as direction means the
    excluded counts come back from the same single query.
    """
    code = get_currency(currency).code

    rows = session.execute(
        select(
            FinancialTransaction.ledger_status,
            FinancialTransaction.direction,
            FinancialTransaction.currency,
            func.sum(FinancialTransaction.amount_minor),
            func.count(),
        )
        .where(FinancialTransaction.statement_period_id == period_id)
        .group_by(
            FinancialTransaction.ledger_status,
            FinancialTransaction.direction,
            FinancialTransaction.currency,
        )
    ).all()

    credits = 0
    debits = 0
    counted = 0
    excluded: dict[str, int] = {}

    for status, direction, row_currency, amount, count in rows:
        if status != LedgerStatus.admitted.value:
            # A row that does not count toward the total cannot corrupt it, so
            # a quarantined row in another currency is recorded and not
            # refused.  Only the admitted set has to be coherent.
            excluded[status] = excluded.get(status, 0) + int(count)
            continue

        if row_currency != code:
            raise MixedCurrencyError(
                f"period is denominated in {code} but holds {count} admitted "
                f"{direction} row(s) in {row_currency}; summing across "
                "currencies would produce a number that means nothing"
            )

        total = int(amount or 0)
        if direction == TransactionDirection.credit.value:
            credits += total
        elif direction == TransactionDirection.debit.value:
            debits += total
        else:  # pragma: no cover - the column has a check constraint
            raise ReconciliationError(
                f"row carries direction {direction!r}, which is neither "
                "credit nor debit"
            )
        counted += int(count)

    return TransactionTotals(
        currency=code,
        credits=Money(credits, code),
        debits=Money(debits, code),
        counted=counted,
        excluded=dict(excluded),
    )


# ---------------------------------------------------------------------------
# The identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityOutcome:
    """The result of the identity, including the case where it could not run.

    ``delta`` is ``computed_closing - printed_closing``.  A positive delta
    means the rows on hand produce more money than the statement says ended
    the period, which is what missing debits or spurious credits look like; a
    negative delta is the mirror image.  The sign is part of the finding, and
    the next stage localises the gap on the strength of it.
    """

    status: ReconciliationStatus
    totals: TransactionTotals
    opening: Optional[Money]
    printed_closing: Optional[Money]
    computed_closing: Optional[Money]
    delta: Optional[Money]
    independent: bool
    unavailable_reason: Optional[str]

    @property
    def is_balanced(self) -> bool:
        return self.status is ReconciliationStatus.balanced

    @property
    def was_attempted(self) -> bool:
        return self.status is not ReconciliationStatus.not_attempted

    @property
    def proves_completeness(self) -> bool:
        """The only combination that argues these rows are the whole period.

        Balanced is not enough on its own.  A balance struck against a
        carried-forward opening restates the neighbouring period, and a
        balance reached after rows were quarantined is a balance over a subset.
        """
        return self.is_balanced and self.independent and self.totals.is_complete


def evaluate_identity(
    *,
    opening: BalanceObservation,
    closing: BalanceObservation,
    totals: TransactionTotals,
    currency: str,
) -> IdentityOutcome:
    """Apply the identity to observations already made.  Pure: no database.

    Kept separate from the reading and the writing so that the arithmetic can
    be exercised directly, and so that anyone auditing the rule has one short
    function to read rather than a query and a session lifecycle.
    """
    code = get_currency(currency).code

    for label, observation in (("opening", opening), ("closing", closing)):
        if not isinstance(observation, BalanceObservation):
            raise ReconciliationError(
                f"{label} must be a BalanceObservation, got "
                f"{type(observation).__name__}"
            )
        amount = observation.amount
        if amount is not None and amount.currency != code:
            raise MixedCurrencyError(
                f"{label} balance is {amount.currency} but the period is "
                f"{code}; a period holding two currencies has no identity"
            )

    if totals.currency != code:
        raise MixedCurrencyError(
            f"totals are {totals.currency} but the period is {code}"
        )

    # Independence is a property of the sources, not of the outcome, so it is
    # reported whether or not the identity could be computed.
    independent = opening.is_independent and closing.is_independent

    missing = [
        label
        for label, observation in (("opening", opening), ("closing", closing))
        if observation.is_absent
    ]
    if missing:
        reason = (
            f"the {' and '.join(missing)} balance"
            f"{'s were' if len(missing) > 1 else ' was'} not printed on the "
            "statement, and substituting zero would manufacture a delta equal "
            "to the real figure"
        )
        return IdentityOutcome(
            status=ReconciliationStatus.unavailable,
            totals=totals,
            opening=opening.amount,
            printed_closing=closing.amount,
            computed_closing=None,
            delta=None,
            independent=independent,
            unavailable_reason=reason,
        )

    # Both present: mypy aside, the absence check above guarantees these.
    opening_amount = opening.amount
    printed_closing = closing.amount
    assert opening_amount is not None and printed_closing is not None

    computed_closing = opening_amount + totals.net
    delta = computed_closing - printed_closing

    return IdentityOutcome(
        status=(
            ReconciliationStatus.balanced
            if delta.minor_units == 0
            else ReconciliationStatus.unbalanced
        ),
        totals=totals,
        opening=opening_amount,
        printed_closing=printed_closing,
        computed_closing=computed_closing,
        delta=delta,
        independent=independent,
        unavailable_reason=None,
    )


def reconcile_period(
    session: "Session",
    period: FinancialStatementPeriod,
    *,
    now: Optional[datetime] = None,
) -> IdentityOutcome:
    """Compute the identity for a stored period and record the result on it.

    The totals and the row count are written even when the identity could not
    run.  They were genuinely computed, they are useful to whoever has to
    supply the missing balance, and recording them costs nothing.  What stays
    null in that case is the computed closing balance and the delta, because
    those are the two values that would be inventions.

    ``reconciled_at`` records the attempt rather than the success, matching
    what ``unavailable`` means: tried, and the statement did not carry what
    the check needs.
    """
    opening = read_opening(period)
    closing = read_closing(period)
    totals = total_transactions(
        session, period_id=period.id, currency=period.currency
    )
    outcome = evaluate_identity(
        opening=opening,
        closing=closing,
        totals=totals,
        currency=period.currency,
    )

    period.reconciliation_status = outcome.status.value
    period.credit_total_minor = _fits(
        totals.credits.minor_units, "credit_total_minor"
    )
    period.debit_total_minor = _fits(
        totals.debits.minor_units, "debit_total_minor"
    )
    period.transaction_count = totals.counted
    period.computed_closing_minor = (
        None
        if outcome.computed_closing is None
        else _fits(outcome.computed_closing.minor_units, "computed_closing_minor")
    )
    period.delta_minor = (
        None if outcome.delta is None else _fits(outcome.delta.minor_units, "delta_minor")
    )
    period.reconciled_at = now or datetime.now(timezone.utc)

    # Flush here so that a bad write is raised against the period that caused
    # it rather than at some later commit covering many periods.
    session.flush()
    return outcome
