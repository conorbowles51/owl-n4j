"""Questions asked of a case's phones and their answers (lx-phoneask; migration 20261125_phone_asks).

A row keeps the question, who asked it, the phones in scope, and the whole answer as shown, so an earlier question
reopens without asking the model again. The answer is a model's reading: it is shown as written by AI, never as a
person's finding."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class PhoneAsk(Base):
    __tablename__ = "phone_asks"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="ck_phone_asks_status"),
        Index("ix_phone_asks_case", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    phones: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    answer: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    asked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    asked_by_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
