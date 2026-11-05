"""A code word whose meaning a person confirmed, and a case's edits to the monitoring-app list (agent-evidence-rest)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

_JSON = JSON().with_variant(JSONB(), "postgresql")


class CaseGlossaryTerm(Base):
    __tablename__ = "case_glossary_terms"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed', 'withdrawn')", name="ck_case_glossary_terms_status"),
        Index("ix_case_glossary_terms_case", "case_id", "status"),
        Index("uq_case_glossary_term_confirmed", "case_id", text("lower(term)"), unique=True,
              postgresql_where=text("status = 'confirmed'"), sqlite_where=text("status = 'confirmed'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                               nullable=False)
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    model_meaning: Mapped[str | None] = mapped_column(Text)
    speaker: Mapped[str | None] = mapped_column(String(255))
    citations: Mapped[list] = mapped_column(_JSON, nullable=False, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="confirmed", server_default="confirmed")
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                                   ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    withdrawn_by_name: Mapped[str | None] = mapped_column(String(255))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_reason: Mapped[str | None] = mapped_column(Text)
    keyword_list_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    keyword_list_note: Mapped[str | None] = mapped_column(Text)
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                          ForeignKey("workspace_ai_outputs.id", ondelete="SET NULL"))
    origin: Mapped[dict | None] = mapped_column(_JSON)


class PhoneMonitoringAppEntry(Base):
    __tablename__ = "phone_monitoring_app_entries"
    __table_args__ = (
        CheckConstraint("action IN ('add', 'reviewed', 'set_aside')", name="ck_phone_monitoring_app_action"),
        Index("uq_phone_monitoring_app_entry", "case_id", text("lower(identifier)"), unique=True,
              postgresql_where=text("removed_at IS NULL"), sqlite_where=text("removed_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                               nullable=False)
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
                                                                 ForeignKey("users.id", ondelete="SET NULL"))
    created_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_by_name: Mapped[str | None] = mapped_column(String(255))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
