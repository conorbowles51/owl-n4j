"""Durable preparation and confirmation of groups of financial statements."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, JSON, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base
from postgres.models.mixins import TimestampMixin


def json_type():
    return JSONB().with_variant(JSON(), 'sqlite')


class FinancialImportBatch(Base, TimestampMixin):
    __tablename__ = 'financial_import_batches'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'))
    status: Mapped[str] = mapped_column(String(24), default='preparing', nullable=False)
    files: Mapped[list] = mapped_column(json_type(), default=list, nullable=False)
    actor: Mapped[dict] = mapped_column(json_type(), nullable=False)
    worker_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FinancialImportBatchItem(Base, TimestampMixin):
    __tablename__ = 'financial_import_batch_items'
    __table_args__ = (UniqueConstraint('batch_id','file_id','statement_key',name='uq_financial_batch_period'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('financial_import_batches.id', ondelete='CASCADE'), index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_files.id', ondelete='CASCADE'))
    statement_key: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    summary: Mapped[dict] = mapped_column(json_type(), nullable=False)
    review_request: Mapped[dict | None] = mapped_column(json_type(), nullable=True)


class FinancialImportOperation(Base, TimestampMixin):
    __tablename__ = 'financial_import_operations'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('financial_import_batches.id', ondelete='CASCADE'), index=True)
    expected_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[dict] = mapped_column(json_type(), nullable=False)
    outcomes: Mapped[list] = mapped_column(json_type(), nullable=False)
