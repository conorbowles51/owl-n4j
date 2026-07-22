from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
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


class LastGraphState(Base, TimestampMixin):
    """Cypher snapshot for restoring the most recently cleared Neo4j graph."""

    __tablename__ = "last_graph_states"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    cypher: Mapped[str] = mapped_column(Text, nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SnapshotRecord(Base, TimestampMixin):
    """Investigation snapshot persisted as structured runtime state in Postgres."""

    __tablename__ = "snapshots"
    __table_args__ = (
        Index("ix_snapshots_owner_created", "owner", "created_at"),
        Index("ix_snapshots_case_created", "case_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    case_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    case_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snapshot_timestamp: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict] = mapped_column(_jsonb_column(), server_default="{}", nullable=False)


class SystemLog(Base, TimestampMixin):
    """Runtime system log entry persisted in Postgres."""

    __tablename__ = "system_logs"
    __table_args__ = (
        Index("ix_system_logs_timestamp", "timestamp"),
        Index("ix_system_logs_type_timestamp", "log_type", "timestamp"),
        Index("ix_system_logs_origin_timestamp", "origin", "timestamp"),
        Index("ix_system_logs_user_timestamp", "user", "timestamp"),
        Index("ix_system_logs_success_timestamp", "success", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    log_type: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(_jsonb_column(), server_default="{}", nullable=False)


class AIModelPolicy(Base, TimestampMixin):
    """One durable, deployment-wide routing policy for generative AI workloads."""

    __tablename__ = "ai_model_policies"

    key: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    configuration: Mapped[dict] = mapped_column(
        _jsonb_column(), server_default="{}", nullable=False
    )
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class AIProviderCredential(Base, TimestampMixin):
    """Encrypted deployment-wide API credential for one cloud AI provider."""

    __tablename__ = "ai_provider_credentials"

    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_last_four: Mapped[str | None] = mapped_column(String(4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="connected")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="database")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
