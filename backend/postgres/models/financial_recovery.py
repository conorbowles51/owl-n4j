"""Durable, versioned recovery of existing statement readings after a release."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base
from postgres.models.mixins import TimestampMixin
from postgres.models.financial_import_batches import json_type


class FinancialRecoveryRelease(Base):
    __tablename__ = "financial_recovery_releases"
    release: Mapped[str] = mapped_column(String(64), primary_key=True)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinancialRecoveryRun(Base, TimestampMixin):
    __tablename__ = 'financial_recovery_runs'
    __table_args__ = (UniqueConstraint('case_id', 'release', name='uq_financial_recovery_release'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), index=True)
    release: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='running')


class FinancialRecoveryItem(Base, TimestampMixin):
    __tablename__ = 'financial_recovery_items'
    __table_args__ = (UniqueConstraint('run_id', 'file_id', name='uq_financial_recovery_file'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('financial_recovery_runs.id', ondelete='CASCADE'), index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_files.id', ondelete='CASCADE'))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default='pending')
    result: Mapped[dict] = mapped_column(json_type(), nullable=False, default=dict)
