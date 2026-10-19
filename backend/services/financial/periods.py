"""Statement periods: what a document covered, and where every value came from.

A statement period is one account's coverage by one document.  It carries four
values the rest of the subsystem depends on — a start date, an end date, an
opening balance and a closing balance — and for each of them this module
insists that the value travel with a record of where it came from.

The reason is the same in all four cases: an absence and a measurement are
otherwise indistinguishable, and the two support completely different claims.

A missing opening balance is not a zero opening balance.  Treat it as zero and
the balance identity in the next stage silently produces a delta equal to the
real opening, which then looks like fraud or like missing rows.  Treat it as
absent and the identity declines to run, which is the honest answer.

A period end printed on the statement and a period end taken from the last
transaction on the page look identical in a date column and mean quite
different things.  The printed one is an assertion by the bank about what the
statement covers, and a gap between it and the next statement's printed start
is evidence that a statement is missing.  The derived one is a restatement of
the rows already held: it shrinks to fit whatever was extracted, so it invents
a gap whenever a month ended quietly and closes a real one whenever the final
rows were dropped.  Using a derived bound for continuity would therefore be
worse than not checking, because it produces confident answers in both
directions.  ``PeriodBounds.supports_continuity`` is what the continuity check
consults, and it is false unless both bounds were printed.

An opening balance carried forward from the neighbouring period is a fourth
case.  It is a real number, but the balance identity computed over it is no
longer an independent check of these rows — it is partly a restatement of the
period next door.  So a carried-forward balance must name the period it came
from.  Without that, ``carried_forward`` is an unfalsifiable claim, and nobody
reading the ledger can see which periods were checked against themselves.

Nothing here computes the balance identity or compares neighbouring periods.
This module's whole responsibility is that the inputs to those stages are
recorded exactly as observed, and that no combination which misrepresents an
observation can be written down.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional

from postgres.models.enums import (
    BalanceSource,
    PeriodBoundsSource,
    ReconciliationStatus,
)
from postgres.models.financial import (
    FinancialAccount,
    FinancialSourceDocument,
    FinancialStatementPeriod,
)
from services.financial.money import Money, get_currency
from services.financial.runs import RunScopeError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

    from services.financial.runs import IngestionRunHandle


class PeriodError(Exception):
    """A statement period could not be recorded as described."""


class BalanceCoherenceError(PeriodError):
    """A balance and its stated source contradict each other."""


class PeriodBoundsError(PeriodError):
    """Period dates and their stated sources contradict each other."""


class PeriodCurrencyError(PeriodError):
    """A balance is denominated differently from the period that holds it."""


@dataclass(frozen=True)
class BalanceObservation:
    """A balance and where it came from, kept together so neither travels alone.

    Construct through :meth:`printed`, :meth:`carried_forward` or
    :meth:`absent` rather than by hand; the constructors are what make the
    three cases distinguishable at the call site, where the caller still knows
    which one it is looking at.

    ``absent()`` is not zero.  A statement that prints no opening balance and a
    statement that prints an opening balance of zero are different documents,
    and the difference decides whether the arithmetic in the next stage can
    run at all.
    """

    source: BalanceSource
    amount: Optional[Money] = None
    carried_from_period_id: Optional[uuid.UUID] = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, BalanceSource):
            raise BalanceCoherenceError(
                f"source must be a BalanceSource, got {type(self.source).__name__}"
            )
        if self.amount is not None and not isinstance(self.amount, Money):
            raise BalanceCoherenceError(
                "amount must be a Money, got "
                f"{type(self.amount).__name__}; a bare number would not carry "
                "the currency the balance is meaningless without"
            )

        if self.source is BalanceSource.absent:
            if self.amount is not None:
                raise BalanceCoherenceError(
                    "a balance recorded as absent may not carry an amount; if "
                    f"{self.amount} was observed, say where it came from"
                )
        elif self.amount is None:
            raise BalanceCoherenceError(
                f"a balance recorded as {self.source.value} must carry an "
                "amount; if none was observed the source is 'absent'"
            )

        if self.source is BalanceSource.carried_forward:
            if self.carried_from_period_id is None:
                raise BalanceCoherenceError(
                    "a carried-forward balance must name the statement period "
                    "it was carried from, otherwise the claim cannot be "
                    "checked and the reader cannot see that this period's "
                    "arithmetic is not independent of its neighbour's"
                )
        elif self.carried_from_period_id is not None:
            raise BalanceCoherenceError(
                f"a balance recorded as {self.source.value} may not name a "
                "period it was carried from; only 'carried_forward' was"
            )

    # -- constructors ------------------------------------------------------

    @classmethod
    def printed(cls, amount: Money) -> "BalanceObservation":
        """A balance stated on the face of the statement."""
        return cls(source=BalanceSource.printed, amount=amount)

    @classmethod
    def carried_forward(
        cls, amount: Money, *, from_period_id: uuid.UUID
    ) -> "BalanceObservation":
        """A balance taken from a neighbouring period because none was printed."""
        return cls(
            source=BalanceSource.carried_forward,
            amount=amount,
            carried_from_period_id=from_period_id,
        )

    @classmethod
    def absent(cls) -> "BalanceObservation":
        """No balance was available.  This is not a balance of zero."""
        return cls(source=BalanceSource.absent)

    # -- accessors ---------------------------------------------------------

    @property
    def is_absent(self) -> bool:
        return self.source is BalanceSource.absent

    @property
    def is_independent(self) -> bool:
        """Whether arithmetic over this balance checks these rows alone.

        A printed balance is an assertion by the source about this period.  A
        carried-forward one is this system's own earlier conclusion about the
        period next door, so an identity that closes over it has confirmed
        consistency rather than correctness.
        """
        return self.source is BalanceSource.printed

    @property
    def minor_units(self) -> Optional[int]:
        return None if self.amount is None else self.amount.minor_units

    @property
    def currency(self) -> Optional[str]:
        return None if self.amount is None else self.amount.currency


@dataclass(frozen=True)
class PeriodBounds:
    """The span a statement covers, with each end's origin recorded separately.

    Start and end are separate because statements exist that print only a
    closing date, and a period whose end was printed and whose start was
    inferred is a real and common thing that a single source column would have
    to misdescribe.
    """

    start: Optional[date] = None
    end: Optional[date] = None
    start_source: PeriodBoundsSource = PeriodBoundsSource.absent
    end_source: PeriodBoundsSource = PeriodBoundsSource.absent

    def __post_init__(self) -> None:
        for label, value, source in (
            ("start", self.start, self.start_source),
            ("end", self.end, self.end_source),
        ):
            if not isinstance(source, PeriodBoundsSource):
                raise PeriodBoundsError(
                    f"period_{label}_source must be a PeriodBoundsSource, got "
                    f"{type(source).__name__}"
                )
            # datetime is a date subclass and would silently carry a time
            # component into a Date column, so it is refused by name.
            if value is not None and type(value) is not date:
                raise PeriodBoundsError(
                    f"period_{label} must be a date, got "
                    f"{type(value).__name__}"
                )
            if source is PeriodBoundsSource.absent and value is not None:
                raise PeriodBoundsError(
                    f"period_{label} is recorded as absent but carries {value}; "
                    "if a date was observed, say where it came from"
                )
            if source is not PeriodBoundsSource.absent and value is None:
                raise PeriodBoundsError(
                    f"period_{label} is recorded as {source.value} but carries "
                    "no date; if none was observed the source is 'absent'"
                )

        if self.start is not None and self.end is not None:
            if self.start > self.end:
                raise PeriodBoundsError(
                    f"period runs backwards: {self.start} to {self.end}"
                )

    # -- constructors ------------------------------------------------------

    @classmethod
    def printed(cls, start: date, end: date) -> "PeriodBounds":
        """Both dates stated on the face of the statement."""
        return cls(
            start=start,
            end=end,
            start_source=PeriodBoundsSource.printed,
            end_source=PeriodBoundsSource.printed,
        )

    @classmethod
    def derived(cls, start: date, end: date) -> "PeriodBounds":
        """Both dates inferred from the transactions found on the page."""
        return cls(
            start=start,
            end=end,
            start_source=PeriodBoundsSource.derived,
            end_source=PeriodBoundsSource.derived,
        )

    @classmethod
    def absent(cls) -> "PeriodBounds":
        """Neither date could be established."""
        return cls()

    # -- accessors ---------------------------------------------------------

    @property
    def supports_continuity(self) -> bool:
        """Whether a gap against a neighbouring period would mean anything.

        Both bounds must be printed.  A derived bound is computed from the
        rows already extracted, so comparing it with a neighbour's asks
        whether the extraction agrees with itself, which it always does.
        """
        return (
            self.start_source is PeriodBoundsSource.printed
            and self.end_source is PeriodBoundsSource.printed
        )


@dataclass(frozen=True)
class StatementPeriodDraft:
    """One account's coverage by one document, as read, before it is stored."""

    account_id: uuid.UUID
    source_document_id: uuid.UUID
    currency: str
    bounds: PeriodBounds = PeriodBounds()
    opening: BalanceObservation = BalanceObservation(source=BalanceSource.absent)
    closing: BalanceObservation = BalanceObservation(source=BalanceSource.absent)

    def __post_init__(self) -> None:
        # Normalises the code and rejects an unknown one, so a period cannot be
        # stored against a currency the money type would later refuse.
        resolved = get_currency(self.currency)
        if resolved.code != self.currency:
            object.__setattr__(self, "currency", resolved.code)

        for label, balance in (("opening", self.opening), ("closing", self.closing)):
            if not isinstance(balance, BalanceObservation):
                raise BalanceCoherenceError(
                    f"{label} must be a BalanceObservation, got "
                    f"{type(balance).__name__}"
                )
            if balance.currency is not None and balance.currency != resolved.code:
                raise PeriodCurrencyError(
                    f"{label} balance is in {balance.currency} but the period "
                    f"is denominated in {resolved.code}; a period holding two "
                    "currencies has no balance identity"
                )

        if not isinstance(self.bounds, PeriodBounds):
            raise PeriodBoundsError(
                f"bounds must be a PeriodBounds, got {type(self.bounds).__name__}"
            )

    @property
    def is_independently_checkable(self) -> bool:
        """Whether the balance identity over this period would check the rows.

        True only where both balances were printed.  Where either was carried
        forward the identity still runs and is still worth running, but what
        it establishes is consistency with a neighbour rather than agreement
        with the source.
        """
        return self.opening.is_independent and self.closing.is_independent


def record_statement_period(
    session: "Session",
    run: "IngestionRunHandle",
    draft: StatementPeriodDraft,
) -> FinancialStatementPeriod:
    """Write a statement period, attributed to ``run``, exactly as observed.

    The referenced account and document are checked to belong to the run's
    case before anything is written.  The foreign keys cannot do this — they
    guarantee the rows exist, not that they concern the same investigation —
    and a period joining one case's document to another case's account would
    put a stranger's money in this case's totals.

    Reconciliation fields are left at their defaults.  This function records
    what was observed; deciding whether the observations close is a separate
    stage, and doing both here would let a reader mistake a computed closing
    balance for a printed one.

    Duplicate periods are left to the database.  A read-then-write check here
    would be a race rather than a protection, and the unique constraints —
    including the partial index covering the undated case — are what actually
    hold.
    """
    account = session.get(FinancialAccount, draft.account_id)
    if account is None:
        raise RunScopeError(
            f"account {draft.account_id} does not exist; a statement period "
            "cannot be recorded against an account that was never created"
        )
    if account.case_id != run.case_id:
        raise RunScopeError(
            f"account {draft.account_id} belongs to case {account.case_id}, "
            f"but this run is ingesting case {run.case_id}"
        )

    document = session.get(FinancialSourceDocument, draft.source_document_id)
    if document is None:
        raise RunScopeError(
            f"source document {draft.source_document_id} does not exist; a "
            "statement period cannot be recorded against a document that was "
            "never admitted"
        )
    if document.case_id != run.case_id:
        raise RunScopeError(
            f"source document {draft.source_document_id} belongs to case "
            f"{document.case_id}, but this run is ingesting case {run.case_id}"
        )

    period = FinancialStatementPeriod(
        account_id=draft.account_id,
        source_document_id=draft.source_document_id,
        currency=draft.currency,
        period_start=draft.bounds.start,
        period_end=draft.bounds.end,
        period_start_source=draft.bounds.start_source.value,
        period_end_source=draft.bounds.end_source.value,
        opening_balance_minor=draft.opening.minor_units,
        opening_balance_source=draft.opening.source.value,
        opening_carried_from_period_id=draft.opening.carried_from_period_id,
        closing_balance_minor=draft.closing.minor_units,
        closing_balance_source=draft.closing.source.value,
        closing_carried_from_period_id=draft.closing.carried_from_period_id,
        reconciliation_status=ReconciliationStatus.not_attempted.value,
    )

    run.stamp(period)
    session.add(period)
    # Flushed so that a constraint violation is raised here, where the draft
    # that caused it is still in hand, rather than at some later commit.
    session.flush()
    return period


def read_bounds(period: FinancialStatementPeriod) -> PeriodBounds:
    """Recover the bounds value object from a stored row."""
    return PeriodBounds(
        start=period.period_start,
        end=period.period_end,
        start_source=PeriodBoundsSource(period.period_start_source),
        end_source=PeriodBoundsSource(period.period_end_source),
    )


def read_opening(period: FinancialStatementPeriod) -> BalanceObservation:
    """Recover the opening balance value object from a stored row."""
    return _read_balance(
        source=period.opening_balance_source,
        minor_units=period.opening_balance_minor,
        currency=period.currency,
        carried_from=period.opening_carried_from_period_id,
    )


def read_closing(period: FinancialStatementPeriod) -> BalanceObservation:
    """Recover the closing balance value object from a stored row."""
    return _read_balance(
        source=period.closing_balance_source,
        minor_units=period.closing_balance_minor,
        currency=period.currency,
        carried_from=period.closing_carried_from_period_id,
    )


def _read_balance(
    *,
    source: str,
    minor_units: Optional[int],
    currency: str,
    carried_from: Optional[uuid.UUID],
) -> BalanceObservation:
    resolved = BalanceSource(source)
    amount = (
        None if minor_units is None else Money(minor_units=minor_units, currency=currency)
    )
    if resolved is BalanceSource.carried_forward and carried_from is None:
        # The row says carried forward but the period it named is gone, which
        # the SET NULL on that foreign key permits.  Reconstructing it as a
        # carried-forward observation would fail validation, and reconstructing
        # it as printed would upgrade weak evidence on the way out of the
        # database.  Neither is acceptable, so the caller is told plainly.
        raise BalanceCoherenceError(
            "stored balance claims to be carried forward but no longer names a "
            "period; the period it referenced has been deleted, and this row's "
            "provenance cannot be reconstructed"
        )
    return BalanceObservation(
        source=resolved, amount=amount, carried_from_period_id=carried_from
    )
