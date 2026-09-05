"""Run the balance identity over a case's stored periods, and read the result.

:mod:`services.financial.reconcile` holds the arithmetic and knows how to
record it on one period.  Nothing in the running system called it.  Its only
production caller is :mod:`services.financial.duplicates`, which has no
production caller of its own, so every ``FinancialStatementPeriod`` was created
at ``not_attempted`` by ``periods.persist_period`` and stayed there for the
life of the case.  The check that says a document was read completely had
never run against a stored row.

This module is what runs it, and what reads the answer back.

**Why the parse-time verdict is not the same claim.**  Ingestion already moves
a document's proof class on a reconciliation result: ``native_ingest`` passes
``reading.reconciliation_status`` to ``documents.reclassify_after_reconciliation``.
That verdict is computed by the format parser over the file as parsed --
camt.053, BAI2, MT940 and NACHA each carry control totals and each compute one.
It is a statement about the document.  The identity here is a statement about
the *ledger*: it sums the rows that are actually stored and actually admitted.
The two can disagree, and after row-level adjudication landed they can be made
to disagree deliberately, because quarantining a row changes what the ledger
holds and cannot change what a file said when it was read months earlier.  A
period that parsed clean and has since had two rows set aside is no longer a
period whose rows add up, and only this path can say so.

**What this module does not do.**  It does not touch proof class.  Moving a
document between p2 and p3 on the strength of an identity is
``assign_proof_class`` and ``record_admission``, which are a later unit, and
doing it here would mean two code paths writing the same column on two
different definitions of the same word.  The result is computed, recorded on
the period, and exposed.  What is done about it is decided elsewhere.

**A refusal leaves the stored verdict alone.**  A period whose stored balances
cannot be reconstructed, or which holds an admitted row in another currency,
is reported ``refused`` and its ``reconciliation_status`` column is left
exactly as it was.  That column may then hold a real finding from an earlier
run, and overwriting it with ``not_attempted`` would destroy evidence on the
strength of a read error rather than a re-reading.  The refusal is reported,
with its reason, in the sweep result.  What would reverse this: a decision
that a stored status must never outlive the ability to re-derive it, in which
case the refusal branch would clear the result columns and set
``not_attempted`` instead.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from postgres.models.enums import BalanceSource, ReconciliationStatus
from postgres.models.financial import FinancialStatementPeriod
from services.financial.money import MoneyError
from services.financial.periods import PeriodError
from services.financial.reconcile import (
    IdentityOutcome,
    ReconciliationError,
    reconcile_period,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ReconciliationQueryError(ValueError):
    """A read was asked for on terms it cannot be asked on."""


#: The failures that make one period unanswerable without making the sweep
#: unsafe.  Each of them is a fact about that period's stored data -- a
#: carried-forward balance whose source period was deleted, an admitted row in
#: a currency the period is not denominated in, a stored currency code that is
#: not ISO 4217, a total too large for a signed 64-bit column.  None of them
#: is a database fault, so none of them is a reason to abandon the periods
#: that follow.
_REFUSABLE = (ReconciliationError, PeriodError, MoneyError)


class PeriodOutcome(str, Enum):
    """What happened to one period in a sweep.

    The first three members carry the same spellings as
    :class:`ReconciliationStatus` deliberately: they are the values written to
    ``reconciliation_status``, and a reader comparing an API response against
    the column should not have to translate.  ``not_attempted`` has no member
    here because it is a description of a period nobody has run yet, and this
    enum only ever describes a period that was just run.
    """

    balanced = "balanced"
    unbalanced = "unbalanced"
    unavailable = "unavailable"
    #: The identity could not be computed from what is stored.  Nothing was
    #: written and the previous stored verdict, if any, survives.
    refused = "refused"

    @property
    def recorded(self) -> bool:
        """Whether this outcome was written to the period."""
        return self is not PeriodOutcome.refused


class CaseOutcome(str, Enum):
    """What happened to the sweep as a whole."""

    #: Every period was visited and the transaction was committed.  Individual
    #: periods may still have refused; ``refused_count`` says how many.
    completed = "completed"
    #: The case holds no statement periods.  Reported separately from a
    #: completed sweep over nothing so that a caller reading ``outcome`` alone
    #: is not told work was done when there was none to do.
    no_periods = "no_periods"
    #: The database refused the write.  Rolled back; nothing was recorded.
    write_failed = "write_failed"


@dataclass(frozen=True)
class PeriodReconciliation:
    """One period's result, with enough of the finding to render it.

    ``stored_status`` is what the column holds after the sweep.  For every
    outcome but ``refused`` it equals ``outcome``.  On a refusal it is whatever
    survived, which is the one case where the two differ and the only reason
    the field is carried at all.
    """

    period_id: uuid.UUID
    account_id: uuid.UUID
    currency: str
    period_start: Optional[date]
    period_end: Optional[date]
    outcome: PeriodOutcome
    stored_status: str
    identity: Optional[IdentityOutcome]
    reason: Optional[str]

    @property
    def recorded(self) -> bool:
        return self.outcome.recorded

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "period_id": str(self.period_id),
            "account_id": str(self.account_id),
            "currency": self.currency,
            "period_start": _isoformat(self.period_start),
            "period_end": _isoformat(self.period_end),
            "outcome": self.outcome.value,
            "recorded": self.recorded,
            "stored_status": self.stored_status,
            "reason": self.reason,
        }
        payload.update(_identity_fields(self.identity))
        return payload


@dataclass(frozen=True)
class CaseReconciliation:
    """The result of running the identity across one case."""

    case_id: uuid.UUID
    outcome: CaseOutcome
    periods: tuple[PeriodReconciliation, ...]
    reason: Optional[str]

    @property
    def applied(self) -> bool:
        """Whether anything was written.

        An interface reads this rather than the outcome word, for the reason
        the row adjudications do: the vocabulary can grow, and a caller that
        switched on the word would silently mis-handle a member added later.
        """
        return self.outcome is CaseOutcome.completed and any(
            period.recorded for period in self.periods
        )

    def counts(self) -> dict[str, int]:
        """How many periods landed on each outcome, every member present.

        Every member is keyed even at zero.  A caller rendering "3 unbalanced"
        should not have to distinguish a missing key from a real zero, and a
        summary that omits the outcomes nobody hit is a summary that hides the
        good news as readily as the bad.
        """
        tally = {member.value: 0 for member in PeriodOutcome}
        for period in self.periods:
            tally[period.outcome.value] += 1
        return tally

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "outcome": self.outcome.value,
            "applied": self.applied,
            "reason": self.reason,
            "total": len(self.periods),
            "counts": self.counts(),
            "periods": [period.as_dict() for period in self.periods],
        }


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------


def reconcile_case(
    session: "Session",
    case_id: uuid.UUID,
    *,
    account_id: Optional[uuid.UUID] = None,
    now: Optional[datetime] = None,
) -> CaseReconciliation:
    """Run the balance identity over every stored period of one case.

    Periods are visited oldest first so that the result reads in the order the
    statements cover, and a period with no printed start date sorts last rather
    than at an arbitrary position.

    One period cannot abandon the rest.  Each is attempted inside its own
    guard, and a period whose stored data will not support the arithmetic is
    recorded ``refused`` and stepped over.  This matters more than it looks:
    the periods most likely to refuse are the ones holding damaged data, and a
    sweep that stopped at the first of them would leave the rest of the case
    unchecked precisely when checking it is most useful.

    The whole sweep commits once, at the end.  A partial commit would leave the
    case in a state no single run produced, and ``reconciled_at`` would then
    disagree across periods that were in fact examined together.
    """
    stamp = now or datetime.now(timezone.utc)

    query = select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.case_id == case_id
    )
    if account_id is not None:
        query = query.where(FinancialStatementPeriod.account_id == account_id)
    query = query.order_by(
        FinancialStatementPeriod.period_start.asc().nullslast(),
        FinancialStatementPeriod.id.asc(),
    )

    try:
        periods = list(session.execute(query).scalars().all())
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Failed to read statement periods for case %s", case_id)
        return CaseReconciliation(
            case_id=case_id,
            outcome=CaseOutcome.write_failed,
            periods=(),
            reason=str(exc),
        )

    if not periods:
        return CaseReconciliation(
            case_id=case_id,
            outcome=CaseOutcome.no_periods,
            periods=(),
            reason=None,
        )

    results: list[PeriodReconciliation] = []
    for period in periods:
        try:
            identity = reconcile_period(session, period, now=stamp)
        except _REFUSABLE as exc:
            # ``reconcile_period`` assigns the status before the range guard on
            # the totals can raise, so a refusal can leave the object half
            # mutated.  Expiring it discards those pending values without a
            # flush; a refresh would flush them first, and the next period's
            # SELECT would flush them too.  Neither the column nor the loop can
            # be left holding a value the arithmetic never stood behind.
            session.expire(period)
            results.append(
                PeriodReconciliation(
                    period_id=period.id,
                    account_id=period.account_id,
                    currency=period.currency,
                    period_start=period.period_start,
                    period_end=period.period_end,
                    outcome=PeriodOutcome.refused,
                    stored_status=period.reconciliation_status,
                    identity=None,
                    reason=str(exc),
                )
            )
            continue
        except SQLAlchemyError as exc:
            session.rollback()
            logger.exception(
                "Database error reconciling period %s of case %s",
                period.id,
                case_id,
            )
            return CaseReconciliation(
                case_id=case_id,
                outcome=CaseOutcome.write_failed,
                periods=(),
                reason=str(exc),
            )

        results.append(
            PeriodReconciliation(
                period_id=period.id,
                account_id=period.account_id,
                currency=period.currency,
                period_start=period.period_start,
                period_end=period.period_end,
                outcome=PeriodOutcome(identity.status.value),
                stored_status=period.reconciliation_status,
                identity=identity,
                reason=None,
            )
        )

    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Failed to commit reconciliation for case %s", case_id)
        return CaseReconciliation(
            case_id=case_id,
            outcome=CaseOutcome.write_failed,
            periods=(),
            reason=str(exc),
        )

    return CaseReconciliation(
        case_id=case_id,
        outcome=CaseOutcome.completed,
        periods=tuple(results),
        reason=None,
    )


# ---------------------------------------------------------------------------
# Reading the recorded result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodReconciliationView:
    """A stored period's recorded reconciliation, read and never recomputed.

    Recomputing on a read would make a ``GET`` write, and would mean the figure
    an analyst is looking at could differ from the one recorded against the run
    that produced it.  This reports the column.  Re-running is a ``POST``.
    """

    period_id: uuid.UUID
    case_id: uuid.UUID
    account_id: uuid.UUID
    source_document_id: uuid.UUID
    ingestion_run_id: uuid.UUID
    currency: str
    period_start: Optional[date]
    period_end: Optional[date]
    reconciliation_status: str
    opening_balance_minor: Optional[int]
    opening_balance_source: str
    closing_balance_minor: Optional[int]
    closing_balance_source: str
    computed_closing_minor: Optional[int]
    delta_minor: Optional[int]
    credit_total_minor: Optional[int]
    debit_total_minor: Optional[int]
    transaction_count: Optional[int]
    reconciled_at: Optional[datetime]

    @property
    def is_independent(self) -> bool:
        """Both balances printed on the statement rather than carried forward.

        Read from the stored sources rather than from a stored flag, because
        there is no stored flag: independence is a property of where the two
        balances came from, and those are columns.
        """
        printed = BalanceSource.printed.value
        return (
            self.opening_balance_source == printed
            and self.closing_balance_source == printed
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "period_id": str(self.period_id),
            "case_id": str(self.case_id),
            "account_id": str(self.account_id),
            "source_document_id": str(self.source_document_id),
            "ingestion_run_id": str(self.ingestion_run_id),
            "currency": self.currency,
            "period_start": _isoformat(self.period_start),
            "period_end": _isoformat(self.period_end),
            "reconciliation_status": self.reconciliation_status,
            "opening_balance_minor": self.opening_balance_minor,
            "opening_balance_source": self.opening_balance_source,
            "closing_balance_minor": self.closing_balance_minor,
            "closing_balance_source": self.closing_balance_source,
            "computed_closing_minor": self.computed_closing_minor,
            "delta_minor": self.delta_minor,
            "credit_total_minor": self.credit_total_minor,
            "debit_total_minor": self.debit_total_minor,
            "transaction_count": self.transaction_count,
            "reconciled_at": _isoformat(self.reconciled_at),
            "independent": self.is_independent,
        }


def list_period_reconciliations(
    session: "Session",
    case_id: uuid.UUID,
    *,
    account_id: Optional[uuid.UUID] = None,
    reconciliation_status: Optional[ReconciliationStatus] = None,
    limit: Optional[int] = None,
) -> Sequence[FinancialStatementPeriod]:
    """Stored periods for one case, oldest first, every status by default.

    Defaulting to every status is the same decision the run listing made and
    for the same reason.  A period sitting at ``not_attempted`` is the single
    most important thing this endpoint can report -- it means the arithmetic
    that would have caught a dropped transaction has not been run -- and a
    default that hid it behind a query parameter would let an unchecked ledger
    look like a checked one to anyone who did not already suspect otherwise.

    Ordering carries a secondary key on ``id`` so the sequence is total.
    ``period_start`` is nullable and not unique, so ordering on it alone leaves
    ties resolved by whatever the database felt like, and a paginated caller
    would see rows move between pages.
    """
    if limit is not None and limit <= 0:
        raise ReconciliationQueryError(
            f"limit must be a positive integer, got {limit}"
        )

    query = select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.case_id == case_id
    )
    if account_id is not None:
        query = query.where(FinancialStatementPeriod.account_id == account_id)
    if reconciliation_status is not None:
        query = query.where(
            FinancialStatementPeriod.reconciliation_status
            == reconciliation_status.value
        )

    query = query.order_by(
        FinancialStatementPeriod.period_start.asc().nullslast(),
        FinancialStatementPeriod.id.asc(),
    )
    if limit is not None:
        query = query.limit(limit)

    return session.execute(query).scalars().all()


def to_reconciliation_view(
    row: FinancialStatementPeriod,
) -> PeriodReconciliationView:
    """Project a stored period onto the read model.  No recomputation."""
    return PeriodReconciliationView(
        period_id=row.id,
        case_id=row.case_id,
        account_id=row.account_id,
        source_document_id=row.source_document_id,
        ingestion_run_id=row.ingestion_run_id,
        currency=row.currency,
        period_start=row.period_start,
        period_end=row.period_end,
        reconciliation_status=row.reconciliation_status,
        opening_balance_minor=row.opening_balance_minor,
        opening_balance_source=row.opening_balance_source,
        closing_balance_minor=row.closing_balance_minor,
        closing_balance_source=row.closing_balance_source,
        computed_closing_minor=row.computed_closing_minor,
        delta_minor=row.delta_minor,
        credit_total_minor=row.credit_total_minor,
        debit_total_minor=row.debit_total_minor,
        transaction_count=row.transaction_count,
        reconciled_at=row.reconciled_at,
    )


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _isoformat(value: Optional[Any]) -> Optional[str]:
    """ISO 8601 or ``None``, never the string ``'None'``."""
    return None if value is None else value.isoformat()


def _identity_fields(identity: Optional[IdentityOutcome]) -> dict[str, Any]:
    """Flatten an identity onto the wire, or null every field of it.

    The keys are present whether or not the identity ran, so a client renders
    one shape.  A refused period reports nulls rather than omitting the block,
    because an absent key and a null read the same in most clients and only one
    of them is what happened.
    """
    if identity is None:
        return {
            "opening_minor": None,
            "printed_closing_minor": None,
            "computed_closing_minor": None,
            "delta_minor": None,
            "credit_total_minor": None,
            "debit_total_minor": None,
            "transaction_count": None,
            "excluded_counts": {},
            "excluded_count": None,
            "independent": None,
            "proves_completeness": None,
            "unavailable_reason": None,
        }

    totals = identity.totals
    return {
        "opening_minor": _minor(identity.opening),
        "printed_closing_minor": _minor(identity.printed_closing),
        "computed_closing_minor": _minor(identity.computed_closing),
        "delta_minor": _minor(identity.delta),
        "credit_total_minor": totals.credits.minor_units,
        "debit_total_minor": totals.debits.minor_units,
        "transaction_count": totals.counted,
        "excluded_counts": dict(totals.excluded),
        "excluded_count": totals.excluded_count,
        "independent": identity.independent,
        "proves_completeness": identity.proves_completeness,
        "unavailable_reason": identity.unavailable_reason,
    }


def _minor(amount: Optional[Any]) -> Optional[int]:
    return None if amount is None else amount.minor_units
