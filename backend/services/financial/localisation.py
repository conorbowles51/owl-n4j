"""Reading a stored period into the form localisation and rescue checks need.

:mod:`~services.financial.quarantine` is pure by design.  ``localise`` takes a
residual and a sequence of :class:`~services.financial.quarantine.RowObservation`,
``would_rescue`` takes an :class:`~services.financial.reconcile.IdentityOutcome`
and the rows about to be removed, and neither has ever seen a database.  That
purity is why the arithmetic is testable, and it is also why both functions sat
in the package with no production caller at all: something has to turn stored
rows into observations and a stored period into a live outcome, and nothing did.
This module is that something.  It reads; it does not decide and it does not
write.

Which rows the chain is walked over
-----------------------------------

Admitted rows only, ordered by ``row_index``.

The alternative -- walking every row the document printed, including ones
already set aside -- is tempting because the printed running-balance column is a
property of the document rather than of the ledger.  It is wrong here, and the
reason is the definition of ``proved``.  ``localise`` calls a set of breaks
proved when their discrepancies account for **the whole residual**, and the
residual comes from :func:`~services.financial.reconcile.total_transactions`,
which sums admitted rows and nothing else.  Walking a different population
against that residual would compare two numbers that are not measurements of the
same thing, and ``proved`` is the one verdict in this subsystem that must never
rest on such a comparison: it is the only verdict that is grounds.

The cost is real and worth stating.  A row quarantined earlier has left the
totals but is still present in the statement's printed chain, so the chain as
walked here will show a discontinuity where that row used to be.  That
discontinuity is a true fact about the admitted set, and in the ordinary case it
will not account for the residual, so the localisation comes back ``partial``,
which is not grounds.  What would reverse this choice is a different question
being asked: "was this document read completely" is a document-level check
against the printed chain, and it deserves its own function rather than a flag
on this one.

Why the identity is recomputed rather than read off the period
--------------------------------------------------------------

:func:`~services.financial.reconcile.reconcile_period` writes its result onto
the period, so a delta is usually sitting there already.  It is not used.
``would_rescue`` asks whether removing a row would close the gap **as the gap
stands at the moment of the write**, and a stored delta is as old as the last
reconciliation: any admission, correction or quarantine since then has moved the
real figure and left the column behind.  Recomputing costs one grouped query,
which is what :func:`~services.financial.reconcile.total_transactions` already
does for the same period in the same session.

That recomputation also carries a guarantee this module relies on rather than
re-checks.  ``total_transactions`` raises
:class:`~services.financial.reconcile.MixedCurrencyError` when a period holds an
admitted row in another currency, so by the time an outcome exists, every
admitted row in the period is denominated in the period's currency.  The rows
read here are therefore known to satisfy ``localise`` and ``would_rescue``
without a currency filter, and a period that would have broken them raises
before any row is loaded.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from postgres.models.enums import LedgerStatus, TransactionDirection
from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
from services.financial.money import Money
from services.financial.periods import read_closing, read_opening
from services.financial.quarantine import (
    Localisation,
    RescueWarning,
    RowObservation,
    localise,
    would_rescue,
)
from services.financial.reconcile import (
    IdentityOutcome,
    evaluate_identity,
    total_transactions,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


def _page_of(transaction: FinancialTransaction) -> Optional[int]:
    """The page a row was read from, where provenance happens to record one.

    ``provenance`` is a document rather than a column set, and no key in it is
    settled yet for transactions.  ``RowObservation.page`` is carried for
    citation and is never read by the arithmetic, so a missing or oddly typed
    page is an absence rather than a fault: the alternative, raising, would
    make localisation fail on rows it can localise perfectly well.
    """
    provenance = getattr(transaction, "provenance", None)
    if not isinstance(provenance, dict):
        return None
    page = provenance.get("page")
    # ``bool`` is an ``int``; a True here would become page 1 silently.
    if isinstance(page, bool) or not isinstance(page, int):
        return None
    return page


def observe_transaction(transaction: FinancialTransaction) -> RowObservation:
    """One stored row reduced to what the arithmetic reads.

    The direction is passed through the enum rather than as the stored string,
    because ``RowObservation`` refuses anything that is not
    :class:`~postgres.models.enums.TransactionDirection` and a row whose stored
    direction is neither word should fail here, loudly, rather than be summed
    as if it were a debit.
    """
    currency = transaction.currency
    balance = transaction.running_balance_minor
    return RowObservation(
        ref_id=transaction.ref_id,
        row_index=transaction.row_index,
        amount=Money.from_minor_units(transaction.amount_minor, currency),
        direction=TransactionDirection(transaction.direction),
        running_balance=(
            None
            if balance is None
            else Money.from_minor_units(balance, currency)
        ),
        page=_page_of(transaction),
    )


def observe_period_rows(
    session: "Session", *, period_id: uuid.UUID
) -> tuple[RowObservation, ...]:
    """The admitted rows of one period, in the statement's own order.

    ``row_index`` is position within the source document, so ordering by it
    reproduces the order the balances were printed in.  Ordering by date would
    not: several rows commonly share a date, and the running-balance chain is
    meaningless in any order but the printed one.
    """
    rows = (
        session.execute(
            select(FinancialTransaction)
            .where(
                FinancialTransaction.statement_period_id == period_id,
                FinancialTransaction.ledger_status == LedgerStatus.admitted.value,
            )
            .order_by(FinancialTransaction.row_index)
        )
        .scalars()
        .all()
    )
    return tuple(observe_transaction(row) for row in rows)


def current_identity(
    session: "Session", period: FinancialStatementPeriod
) -> IdentityOutcome:
    """The balance identity for a period as it stands now, without writing.

    The same three steps :func:`~services.financial.reconcile.reconcile_period`
    takes, minus the assignment to the period and the flush.  Kept here rather
    than added there as a flag, because a function whose writing can be turned
    off is a function two callers read differently.
    """
    totals = total_transactions(
        session, period_id=period.id, currency=period.currency
    )
    return evaluate_identity(
        opening=read_opening(period),
        closing=read_closing(period),
        totals=totals,
        currency=period.currency,
    )


def localise_period(
    session: "Session", period: FinancialStatementPeriod
) -> Optional[Localisation]:
    """Account for a period's residual, or report that there is none to account for.

    ``None`` means the question does not arise: the period balances, or the
    statement did not print the balances the identity needs.  That is different
    from :attr:`~services.financial.quarantine.LocalisationStrength.none`, which
    means the question arose and the arithmetic offered nothing, and the
    difference matters to whoever reads the result: the first is a period with
    no problem, the second is a period with a problem nobody can place.
    """
    outcome = current_identity(session, period)
    if outcome.delta is None or outcome.delta.minor_units == 0:
        return None
    return localise(
        residual=outcome.delta,
        rows=observe_period_rows(session, period_id=period.id),
        opening=outcome.opening,
    )


def rescue_if_removed(
    session: "Session", transaction: FinancialTransaction
) -> Optional[RescueWarning]:
    """Whether setting this row aside would make its period balance.

    Answered before the write, so the fact can be recorded alongside the
    decision rather than inferred afterwards from two states of the ledger.

    ``None`` covers every case where the question is not meaningful: a row
    belonging to no statement period, and so to no identity; a period that has
    gone from under the row; a row that is not admitted and has therefore
    already left the totals, so removing it again would change nothing; and a
    period that balances or cannot be tested, handled by ``would_rescue``
    itself.  A caller cannot distinguish these from each other and does not need
    to, because in all of them there is nothing to warn about.
    """
    period_id = transaction.statement_period_id
    if period_id is None:
        return None
    if transaction.ledger_status != LedgerStatus.admitted.value:
        return None
    period = session.get(FinancialStatementPeriod, period_id)
    if period is None:
        return None
    return would_rescue(
        outcome=current_identity(session, period),
        rows=[observe_transaction(transaction)],
    )
