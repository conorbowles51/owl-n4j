"""Saved timeline view models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class TimelineView(Base, TimestampMixin):
    """A fixed, case-wide curated chronology."""

    __tablename__ = "timeline_views"
    __table_args__ = (
        Index("ix_timeline_views_case_updated", "case_id", "updated_at"),
        Index("ix_timeline_views_owner_case", "owner_user_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), default="case", server_default="case", nullable=False)
    filter_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    export_defaults: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    events: Mapped[list["TimelineViewEvent"]] = relationship(
        "TimelineViewEvent",
        back_populates="view",
        cascade="all, delete-orphan",
        order_by="TimelineViewEvent.sort_date, TimelineViewEvent.sort_time, TimelineViewEvent.position",
    )


class TimelineViewEvent(Base, TimestampMixin):
    """Fixed membership of a Neo4j timeline event in a saved view."""

    __tablename__ = "timeline_view_events"
    __table_args__ = (
        UniqueConstraint("view_id", "event_key", name="uq_timeline_view_event"),
        Index("ix_timeline_view_events_case_key", "case_id", "event_key"),
        Index("ix_timeline_view_events_view_sort", "view_id", "sort_date", "sort_time", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    view_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("timeline_views.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_key: Mapped[str] = mapped_column(String(512), nullable=False)
    event_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT,
        default=dict,
        server_default="{}",
        nullable=False,
    )
    sort_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sort_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    view: Mapped[TimelineView] = relationship("TimelineView", back_populates="events")
