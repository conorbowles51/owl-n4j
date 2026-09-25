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
from services.financial.account_consolidation import expand_account_ids

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

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
    account_ids=None, account_holders=None,
    ledger_status: Optional[LedgerStatus] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    source_document_id: Optional[UUID] = None,
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

    stmt = select(FinancialTransaction).options(joinedload(FinancialTransaction.account)).where(
        FinancialTransaction.case_id == case_id,
        FinancialTransaction.ledger_status == status.value,
    )
    if account_id is not None:
        stmt = stmt.where(FinancialTransaction.account_id.in_(expand_account_ids(session, case_id, [account_id])))
    if source_document_id is not None:
        stmt = stmt.where(FinancialTransaction.source_document_id == source_document_id)
    from services.financial.account_selection import apply_account_selection
    stmt = apply_account_selection(stmt, session, case_id, account_ids, account_holders)
    if start_date is not None:
        stmt = stmt.where(FinancialTransaction.ordering_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(FinancialTransaction.ordering_date <= end_date)
    stmt = stmt.order_by(
        FinancialTransaction.ordering_date.asc(),
        FinancialTransaction.row_index.asc(),
        FinancialTransaction.id.asc(),
    )
    return list(session.scalars(stmt).all())



@dataclass(frozen=True)
class TransactionView:
    """One ledger row, shaped for a reader rather than for storage.

    Stored readings remain unchanged. Description-based investigation labels
    identify their rule and origin in label_sources, including in exports.
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
    ordering_date_context: Optional[str] = None
    account_type: Optional[str] = None
    account_label: Optional[str] = None
    account_holder: str = ""
    account_institution: str = ""
    account_party_id: Optional[str] = None
    account_holder_parties: list = field(default_factory=list)
    account_relationships: list = field(default_factory=list)
    transfer_details: Optional[dict] = None
    category: str = ""
    from_name: str = ""
    to_name: str = ""
    label_version: int = 0
    account_alias_ids: list = field(default_factory=list)
    canonical_account_id: str | None = None
    canonical_account_label: str | None = None
    counterparty_link: dict | None = None
    label_sources: dict = field(default_factory=dict)
    balance_status: str = 'unavailable'

    def to_json(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "from_name": self.from_name,
            "to_name": self.to_name,
            "label_version": self.label_version,
            "label_sources": self.label_sources,
            "counterparty_link": self.counterparty_link,
            "canonical_account_id": self.canonical_account_id,
            "account_alias_ids": self.account_alias_ids,
            "canonical_account_label": self.canonical_account_label,
            "balance_status": self.balance_status,
            "key": self.key,
            "case_id": self.case_id,
            "account_id": self.account_id,
            "account_holder": self.account_holder,
            "account_institution": self.account_institution,
            "account_party_id": self.account_party_id,
            "account_holder_parties": self.account_holder_parties,
            "account_relationships": self.account_relationships,
            "transfer_details": self.transfer_details,
            **({"account_type": self.account_type} if self.account_type else {}),
            **({"account_label": self.account_label} if self.account_label else {}),
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
            **({"ordering_date_context": self.ordering_date_context} if self.ordering_date_context else {}),
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


def account_label_index(accounts):
    """Labels from the caller's already case-scoped account directory."""
    return {identifier: ' · '.join(value for value in (
        account.get('holder_as_recorded'), account.get('institution'), account.get('identifier_as_printed')) if value)
        for identifier, account in accounts.items()}


def to_view(row: FinancialTransaction, *, account=None, account_parties=None, canonical_account_labels=None) -> TransactionView:
    """Convert one stored row into its read shape.

    Reads every closed-vocabulary column as the plain string or int
    :func:`services.financial.transactions.record_transactions` put there --
    always a ``.value``, never an enum instance -- so there is nothing to
    unwrap here.
    """
    from services.financial.payment_labels import payment_label_view
    from services.financial.payment_inference import balance_reading_status
    from services.financial.spei_description import kapital_spei
    account_type = account.account_type if account is not None and account.case_id == row.case_id else None
    identity = (account_parties or {}).get(str(row.account_id), {})
    canonical_id = (account.metadata_ or {}).get('canonical_account_id') if account is not None else None
    canonical_label = None
    if canonical_id and canonical_account_labels is not None:
        # A case directory is authoritative even when the target is absent.
        # Avoid a per-payment lookup, and never resolve a foreign account label.
        canonical_label = canonical_account_labels.get(canonical_id)
    elif canonical_id:
        from sqlalchemy.orm import object_session
        from postgres.models.financial import FinancialAccount
        db = object_session(account)
        canonical = db.get(FinancialAccount, UUID(canonical_id)) if db else None
        if canonical is not None and canonical.case_id == row.case_id:
            canonical_label = ' · '.join(v for v in (canonical.holder_name, canonical.institution_name, canonical.identifier_as_printed) if v)
    return TransactionView(
        canonical_account_id=canonical_id, canonical_account_label=canonical_label, account_alias_ids=identity.get("alias_ids", []),
        **payment_label_view(row, account),
        balance_status=balance_reading_status(row),
        account_type=account_type,
        account_party_id=(identity.get('party') or {}).get('id') if 'party' in identity else identity.get('id'),
        account_holder_parties=identity.get('effective_holder_parties', identity.get('holder_parties', [])),
        account_relationships=identity.get('effective_relationships', identity.get('relationships', [])),
        transfer_details=kapital_spei(row.description),
        account_holder=(account.holder_name or "") if account is not None and account.case_id == row.case_id else "",
        account_institution=(account.institution_name or "") if account is not None and account.case_id == row.case_id else "",
        account_label=(" · ".join(v for v in [account.holder_name, account.institution_name, account.identifier_as_printed] if v) if account is not None and account.case_id == row.case_id else None),
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
        ordering_date_context=("statement_end_ordering_only" if (row.provenance or {}).get("date_basis") == "statement_end_ordering_only" else None),
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
