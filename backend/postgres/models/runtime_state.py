from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


def _jsonb_column():
    return JSONB().with_variant(JSON(), "sqlite")


class BackgroundTask(Base, TimestampMixin):
    """Runtime background task state persisted in Postgres."""

    __tablename__ = "background_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_background_tasks_status",
        ),
        Index("ix_background_tasks_owner_created", "owner", "created_at"),
        Index("ix_background_tasks_case_created", "case_id", "created_at"),
        Index("ix_background_tasks_status", "status"),
        Index("ix_background_tasks_task_type", "task_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    progress: Mapped[dict] = mapped_column(_jsonb_column(), server_default="{}", nullable=False)
    files: Mapped[list] = mapped_column(_jsonb_column(), server_default="[]", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", _jsonb_column(), server_default="{}", nullable=False)


class WiretapProcessedFolder(Base, TimestampMixin):
    """Tracks folders successfully processed as wiretaps."""

    __tablename__ = "wiretap_processed_folders"
    __table_args__ = (
        UniqueConstraint("case_id", "folder_path", name="uq_wiretap_processed_case_folder"),
        Index("ix_wiretap_processed_case_processed", "case_id", "processed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    folder_path: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PresenceSession(Base, TimestampMixin):
    """Active workspace presence session."""

    __tablename__ = "presence_sessions"
    __table_args__ = (
        Index("ix_presence_sessions_case_active", "case_id", "last_active"),
        Index("ix_presence_sessions_user", "user_id"),
    )

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
