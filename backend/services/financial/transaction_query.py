"""Reading the ledger: the other half of the "both stores" rule.

``services.financial.transactions.record_transactions`` has written admitted
rows into the relational ledger since it was built, and the graph mirror of
the same facts has been readable through ``/api/financial`` for just as
long. Nothing let a caller read the relational ledger itself back out --
every fact ingestion wrote there was reachable only by opening a database
client by hand. ``list_transactions`` is that read: case-scoped, defaulting
to the rows that count toward a total, and ordered the way the ledger orders
itself, by ``ordering_date`` then ``row_index``.

The default status is not a convenience. ``admitted`` is the population every
other total in this ledger is filtered to; a read endpoint that defaulted to
every row regardless of status would show quarantined and superseded rows
beside real ones with nothing distinguishing them, which is the exact
confusion ``ledger_status`` exists to prevent. A caller that wants a
different population says so explicitly.

``TransactionView`` is the read side of the provenance/locator asymmetry
documented in ``services.financial.transactions``: the writer nests a row's
locator under ``provenance[LOCATOR_PROVENANCE_KEY]`` because provenance is an
open bag and the locator is one specific, structured fact living inside it.
A reader does not want to reach into that bag for the one fact it always
wants, so ``to_view`` lifts it back out to a top-level field -- the same
place a Neo4j-backed transaction already carries it once
``attach_transaction_locators`` has run.

Every closed-vocabulary column (``direction``, ``ledger_status``,
``proof_class``, ``ordering_date_source``, ``extraction_layer``) is read
straight off the row with no ``.value`` unwrapping: the writer stores the
plain string or int, never an enum instance, so there is nothing here to
convert -- only to trust.

Nothing here mutates a row. This module answers "what is in the ledger", not
"what should be in it"; admitting, correcting, or quarantining a row stays
with the ingestion and adjudication services that act with a run and an
actor behind them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.enums import LedgerStatus
from postgres.models.financial import FinancialTransaction
from services.financial.transactions import LOCATOR_PROVENANCE_KEY


class LedgerQueryError(ValueError):
    """A ledger read was asked for something it cannot honestly answer."""


def list_transactions(
    session: Session,
    case_id: UUID,
    *,
    account_id: Optional[UUID] = None,
    ledger_status: Optional[LedgerStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> list[FinancialTransaction]:
    """Rows for one case, defaulting to the population that counts toward totals.

    ``ledger_status`` left unset means :attr:`LedgerStatus.admitted`, not
    every row regardless of status. ``start_date``/``end_date`` bound
    ``ordering_date``, the column the ledger itself orders and reconciles by,
    not any one of the four printed dates a row may also carry.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise LedgerQueryError(
            f"start_date {start_date.isoformat()} is after end_date "
            f"{end_date.isoformat()}"
        )

    status = ledger_status if ledger_status is not None else LedgerStatus.admitted

    stmt = select(FinancialTransaction).where(
        FinancialTransaction.case_id == case_id,
        FinancialTransaction.ledger_status == status.value,
    )
    if account_id is not None:
        stmt = stmt.where(FinancialTransaction.account_id == account_id)
    if start_date is not None:
        stmt = stmt.where(FinancialTransaction.ordering_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(FinancialTransaction.ordering_date <= end_date)
    stmt = stmt.order_by(
        FinancialTransaction.ordering_date.asc(),
        FinancialTransaction.row_index.asc(),
    )
    return list(session.scalars(stmt).all())


@dataclass(frozen=True)
class TransactionView:
    """One ledger row, shaped for a reader rather than for storage.

    Every field is either a stored column unwrapped to a JSON-safe type, or
    ``locator``, the one field this shape adds: lifted out of ``provenance``
    so a caller never has to know the ledger keeps it there.
    """

    key: str
    case_id: str
    account_id: str
    source_document_id: str
    ingestion_run_id: str
    statement_period_id: Optional[str]
    ref_id: str
    row_index: int
    amount_minor: int
    currency: str
    direction: str
    running_balance_minor: Optional[int]
    transaction_date: Optional[str]
    posted_date: Optional[str]
    value_date: Optional[str]
    effective_date: Optional[str]
    ordering_date: str
    ordering_date_source: str
    description: Optional[str]
    counterparty_raw: Optional[str]
    transaction_type: Optional[str]
    bank_reference: Optional[str]
    proof_class: str
    extraction_layer: int
    ledger_status: str
    quarantine_reason: Optional[str]
    superseded_by_id: Optional[str]
    locator: Optional[Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "case_id": self.case_id,
            "account_id": self.account_id,
            "source_document_id": self.source_document_id,
            "ingestion_run_id": self.ingestion_run_id,
            "statement_period_id": self.statement_period_id,
            "ref_id": self.ref_id,
            "row_index": self.row_index,
            "amount_minor": str(self.amount_minor),
            "currency": self.currency,
            "direction": self.direction,
            "running_balance_minor": (str(self.running_balance_minor) if self.running_balance_minor is not None else None),
            "transaction_date": self.transaction_date,
            "posted_date": self.posted_date,
            "value_date": self.value_date,
            "effective_date": self.effective_date,
            "ordering_date": self.ordering_date,
            "ordering_date_source": self.ordering_date_source,
            "description": self.description,
            "counterparty_raw": self.counterparty_raw,
            "transaction_type": self.transaction_type,
            "bank_reference": self.bank_reference,
            "proof_class": self.proof_class,
            "extraction_layer": self.extraction_layer,
            "ledger_status": self.ledger_status,
            "quarantine_reason": self.quarantine_reason,
            "superseded_by_id": self.superseded_by_id,
            "locator": self.locator,
        }


def _isoformat(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def to_view(row: FinancialTransaction) -> TransactionView:
    """Convert one stored row into its read shape.

    Reads every closed-vocabulary column as the plain string or int
    :func:`services.financial.transactions.record_transactions` put there --
    always a ``.value``, never an enum instance -- so there is nothing to
    unwrap here.
    """
    return TransactionView(
        key=str(row.id),
        case_id=str(row.case_id),
        account_id=str(row.account_id),
        source_document_id=str(row.source_document_id),
        ingestion_run_id=str(row.ingestion_run_id),
        statement_period_id=(
            str(row.statement_period_id)
            if row.statement_period_id is not None
            else None
        ),
        ref_id=row.ref_id,
        row_index=row.row_index,
        amount_minor=row.amount_minor,
        currency=row.currency,
        direction=row.direction,
        running_balance_minor=row.running_balance_minor,
        transaction_date=_isoformat(row.transaction_date),
        posted_date=_isoformat(row.posted_date),
        value_date=_isoformat(row.value_date),
        effective_date=_isoformat(row.effective_date),
        ordering_date=_isoformat(row.ordering_date),
        ordering_date_source=row.ordering_date_source,
        description=row.description,
        counterparty_raw=row.counterparty_raw,
        transaction_type=row.transaction_type,
        bank_reference=row.bank_reference,
        proof_class=row.proof_class,
        extraction_layer=row.extraction_layer,
        ledger_status=row.ledger_status,
        quarantine_reason=row.quarantine_reason,
        superseded_by_id=(
            str(row.superseded_by_id) if row.superseded_by_id is not None else None
        ),
        locator=(row.provenance or {}).get(LOCATOR_PROVENANCE_KEY),
    )
