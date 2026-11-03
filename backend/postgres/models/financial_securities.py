"""Security rows of the ledger: trades and holdings read from brokerage statements.

A brokerage statement moves two things: cash and securities. The cash leg is a row of ``financial_transactions``
and stays there unchanged. The security leg (instrument as printed, quantity, price, trade and settlement dates) is
a row here, cited to the same printed line, carrying the same proof class, and linked to its cash leg.

Holdings are the statement's printed position at a date (one row per instrument line) and its open repurchase
agreements.

Corrections never overwrite: ``corrections`` holds each corrected field with the value as read, the corrected
value, who corrected it and why; the corrected value is the one every view and the agent use, and the value as read
stays visible beside it. A row read by a model carries the model's origin in ``provenance['reading_origin']`` until
a person confirms it (``confirmation``).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String,
                        Text, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

_JSON = JSONB().with_variant(JSON(), 'sqlite')
ROW_KINDS = ('trade', 'holding')
SIDES = ('buy', 'sell', 'repo', 'repo_start', 'repo_maturity', 'other')
HOLDING_KINDS = ('security', 'repo')
STATUSES = ('admitted', 'superseded')


def _in(values):
    return '(' + ', '.join("'%s'" % v for v in values) + ')'


class FinancialSecurityRow(Base):
    __tablename__ = 'financial_security_rows'
    __table_args__ = (
        CheckConstraint(f'row_kind IN {_in(ROW_KINDS)}', name='ck_financial_security_rows_kind'),
        CheckConstraint(f'side IS NULL OR side IN {_in(SIDES)}', name='ck_financial_security_rows_side'),
        CheckConstraint(f'holding_kind IS NULL OR holding_kind IN {_in(HOLDING_KINDS)}',
                        name='ck_financial_security_rows_holding_kind'),
        CheckConstraint(f'ledger_status IN {_in(STATUSES)}', name='ck_financial_security_rows_status'),
        CheckConstraint("proof_class IN ('p0', 'p1', 'p2', 'p3')", name='ck_financial_security_rows_proof_class'),
        CheckConstraint("trade_date_source IN ('printed', 'absent')", name='ck_financial_security_rows_trade_date_source'),
        Index('ix_financial_security_rows_case_kind', 'case_id', 'row_kind', 'ledger_status'),
        Index('ix_financial_security_rows_document', 'source_document_id'),
        Index('ix_financial_security_rows_cash', 'cash_transaction_id'),
        # One admitted row per printed line of a file.
        Index('uq_financial_security_rows_line', 'evidence_file_id', 'reading_key', unique=True,
              postgresql_where=text("ledger_status = 'admitted'"), sqlite_where=text("ledger_status = 'admitted'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'),
                                               nullable=False)
    row_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('evidence_files.id', ondelete='CASCADE'), nullable=False)
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('financial_source_documents.id', ondelete='CASCADE'), nullable=True)
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('financial_accounts.id', ondelete='SET NULL'), nullable=True)
    statement_period_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('financial_statement_periods.id', ondelete='SET NULL'), nullable=True)
    # The cash leg in the money ledger (a trade only). Never written to from here.
    cash_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey('financial_transactions.id', ondelete='SET NULL'), nullable=True)
    # Where in the file the line is printed, stable across re-reads: 'cash:<page>:<table>:<row>' or
    # 'holding:<page>:<table>:<row>'.
    reading_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reader: Mapped[str] = mapped_column(String(64), nullable=False)
    ledger_status: Mapped[str] = mapped_column(String(16), nullable=False, default='admitted')
    superseded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    operation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    side: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    holding_kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    instrument: Mapped[str] = mapped_column(String(128), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    series: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    isin: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    quantity_printed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 8), nullable=True)
    price_printed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 10), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    gross_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    commission_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    premium_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    tax_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    net_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    market_value_minor: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    trade_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    trade_date_source: Mapped[str] = mapped_column(String(16), nullable=False, default='absent')
    execution_time: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    settlement_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    as_of_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    term_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rate_printed: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    proof_class: Mapped[str] = mapped_column(String(2), nullable=False)
    extraction_layer: Mapped[int] = mapped_column(Integer, nullable=False)
    provenance: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    corrections: Mapped[dict] = mapped_column(_JSON, nullable=False, default=dict)
    confirmation: Mapped[Optional[dict]] = mapped_column(_JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
