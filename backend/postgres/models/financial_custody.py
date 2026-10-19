"""Append-only reported custody, independent of deletable evidence rows."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, String, func, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class FinancialCustodyEvent(Base):
    __tablename__ = 'financial_custody_events'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    evidence_sha256: Mapped[str | None] = mapped_column(String(64))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    actor: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    report: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
