"""Mentions Loupe read out of phone texts, and the per-phone runs that read them (lx-mentions). See migration
20261125_phone_mentions.

A mention's ``reading`` is what Loupe read and is never rewritten. A person's correction goes to ``corrected`` with who
made it and when, and only the corrected values are checked; rejecting a mention keeps it, marked rejected. The
outcome is computed by rules from the case's records (``services.mentions.checks``) and stored with the time it was
computed, so counts can be read without re-checking every mention.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class PhoneMention(Base):
    __tablename__ = "phone_mentions"
    __table_args__ = (
        UniqueConstraint("case_id", "record_uid", "start", "reader", name="uq_phone_mentions_record_span"),
        CheckConstraint("state IN ('read', 'corrected', 'confirmed', 'rejected')", name="ck_phone_mentions_state"),
        CheckConstraint("kind IN ('travel', 'meeting', 'at_place', 'home_away', 'plan', 'money', 'sent', 'deleted')",
                        name="ck_phone_mentions_kind"),
        Index("ix_phone_mentions_case_kind", "case_id", "kind", "outcome"),
        Index("ix_phone_mentions_case_record", "case_id", "record_uid"),
        Index("ix_phone_mentions_case_at", "case_id", "at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_uid: Mapped[str] = mapped_column(String(64), nullable=False)
    record_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="message")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    copy_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    start: Mapped[int] = mapped_column(Integer, nullable=False)
    end: Mapped[int] = mapped_column(Integer, nullable=False)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    reading: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    reader: Mapped[str] = mapped_column(String(40), nullable=False, default="rules")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="read")
    corrected: Mapped[dict | None] = mapped_column(JSON_DOCUMENT, nullable=True)
    corrected_fields: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    result: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PhoneMentionRun(Base):
    """One reading of one phone's texts. ``cursor_at``/``cursor_uid`` is the last text finished, so a run stopped by a
    release carries on from there; ``beat_at`` older than 15 minutes on a running row means it stopped."""
    __tablename__ = "phone_mention_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed', 'stopped')", name="ck_phone_mention_runs_status"),
        Index("ix_phone_mention_runs_case", "case_id", "extraction_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reader: Mapped[str] = mapped_column(String(40), nullable=False, default="rules")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    phase: Mapped[str] = mapped_column(String(16), nullable=False, default="messages")
    cursor_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    texts_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    texts_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mentions_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    beat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
