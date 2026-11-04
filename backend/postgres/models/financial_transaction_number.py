"""Each ledger payment's printable number: short, stable per case, never reused.

``financial_transaction_numbers`` holds one row per transaction; ``financial_transaction_number_counters`` holds the
last number handed out in each case. A database trigger on ``financial_transactions`` numbers every new row, whatever
path inserted it, so no import path can forget. The rule a printed number depends on:

* a new payment gets the next number of its case; numbers are never handed out twice, even after a row is deleted;
* a corrected version of a payment (a row whose ``provenance.correction.previous_transaction_id`` names the row it
  replaces) keeps the number of the row it replaces, so a number written on a printout still finds the payment after
  a correction; the superseded original keeps it too, shown as the earlier version;
* nothing renumbers existing rows: a new import only adds numbers after the last one.

The numbers live beside the ledger rather than in it, so the audited ledger rows are unchanged.
"""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class FinancialTransactionNumber(Base):
    __tablename__ = 'financial_transaction_numbers'
    __table_args__ = (
        CheckConstraint('number >= 1', name='ck_financial_transaction_numbers_positive'),
        Index('ix_financial_transaction_numbers_case_number', 'case_id', 'number'),
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('financial_transactions.id', ondelete='CASCADE'), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinancialTransactionNumberCounter(Base):
    __tablename__ = 'financial_transaction_number_counters'
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)
