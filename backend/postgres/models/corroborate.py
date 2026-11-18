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
    __table_args__ = (
        Index("ix_corroborate_watches_case", "case_id", "active"),
        Index("ix_corroborate_watches_case_state", "case_id", "state"),
        CheckConstraint("origin IN ('found_by_loupe', 'asked', 'agent')", name="ck_corroborate_watches_origin"),
        CheckConstraint("state IN ('new', 'looking', 'in_theory', 'not_relevant')", name="ck_corroborate_watches_state"),
    )

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
    # A lead (lx-leads A, migration 20261120_leads): the same row, grown up. See services/leads/store.py.
    origin: Mapped[str] = mapped_column(String(16), nullable=False, default="asked")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="new")
    state_history: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    people: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    period: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    kinds: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    record_refs: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    raises: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    lowers: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    searched: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    detail: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    corrections: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    read_by: Mapped[str] = mapped_column(String(120), nullable=False, default="Corroborate")
    finder_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class LeadFinderRun(Base):
    """One run of the lead finder over a case (lx-leads D): when, how long, what it saved. See migration
    20261120_leads."""
    __tablename__ = "lead_finder_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="ck_lead_finder_runs_status"),
        Index("ix_lead_finder_runs_case", "case_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="button")
    counts: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    material: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # stamped every minute while the run's thread is alive; a running row with an old beat died with its server
    beat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
