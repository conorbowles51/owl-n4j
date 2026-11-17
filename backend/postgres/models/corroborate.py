"""Corroborate's case facts and kept watches (lx-corroengine H). See migration 20261117_corroborate_facts."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class CorroborateFact(Base):
    """What a person tells Loupe about the case ("Doe and Roe live together"), with who said it and when. A fact is
    never rewritten: withdrawing it keeps it, marked withdrawn, with who withdrew it and when."""
    __tablename__ = "corroborate_case_facts"
    __table_args__ = (
        CheckConstraint("kind IN ('live_together', 'work_group', 'routine_phrase', 'routine_place', 'same_person', "
                        "'not_same_person', 'other')", name="ck_corroborate_case_facts_kind"),
        CheckConstraint("state IN ('active', 'withdrawn')", name="ck_corroborate_case_facts_state"),
        Index("ix_corroborate_case_facts_case", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    people: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    phrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    withdrawn_by_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CorroborateWatch(Base):
    """A saved Corroborate result that re-checks itself when the case's material changes, and keeps every level
    change with its reason (``history``). Alerts show in Loupe only."""
    __tablename__ = "corroborate_watches"
    __table_args__ = (Index("ix_corroborate_watches_case", "case_id", "active"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    selection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_selections.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    level: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    material: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    history: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    unseen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CorroborateClaim(Base):
    """A free-text claim ("I was home all evening on the 3rd") and what Loupe read from it (lx-corrostatement).
    ``read`` is Loupe's reading, kept as it was made ("Read by Loupe · not confirmed"). ``confirmed`` holds the chips
    a named person confirmed or edited; it is empty until then, and only a confirmed claim is weighed."""
    __tablename__ = "corroborate_claims"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed')", name="ck_corroborate_claims_status"),
        Index("ix_corroborate_claims_case", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    statement_date: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    read: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    confirmed: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    edited: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_by_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_by_name: Mapped[str | None] = mapped_column(String(300))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
