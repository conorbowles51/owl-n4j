"""One run of the link analysis on a saved group of items (lx-overlaps). See migration 20261113_relation_queries."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class RelationRun(Base):
    __tablename__ = "relation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_relation_runs_status"),
        Index("ix_relation_runs_case", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    selection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_selections.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    progress: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    hypotheses: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
