from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


def _jsonb_column():
    return JSONB().with_variant(JSON(), "sqlite")


class TriageCase(Base, TimestampMixin):
    """Postgres-backed orchestration state for an independent triage case."""

    __tablename__ = "triage_cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'scanning', 'scan_complete', 'classifying', "
            "'classified', 'profiling', 'profiled', 'processing', 'failed')",
            name="ck_triage_cases_status",
        ),
        Index("ix_triage_cases_created_by_created", "created_by", "created_at"),
        Index("ix_triage_cases_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    scan_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    scan_stats: Mapped[dict] = mapped_column(_jsonb_column(), server_default="{}", nullable=False)
    profile: Mapped[dict | None] = mapped_column(_jsonb_column(), nullable=True)

    stages = relationship(
        "TriageStage",
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="TriageStage.stage_order",
    )


class TriageStage(Base, TimestampMixin):
    """Execution state for one triage stage."""

    __tablename__ = "triage_stages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_triage_stages_status",
        ),
        UniqueConstraint("triage_case_id", "order", name="uq_triage_stages_case_order"),
        Index("ix_triage_stages_case_id", "triage_case_id"),
        Index("ix_triage_stages_case_type", "triage_case_id", "type"),
        Index("ix_triage_stages_case_status", "triage_case_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    triage_case_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("triage_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_order: Mapped[int] = mapped_column("order", Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    config: Mapped[dict] = mapped_column(_jsonb_column(), server_default="{}", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    files_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    case = relationship("TriageCase", back_populates="stages")


class TriageTemplate(Base, TimestampMixin):
    """Reusable triage workflow template stored in Postgres."""

    __tablename__ = "triage_templates"
    __table_args__ = (
        Index("ix_triage_templates_created_by_created", "created_by", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    stages: Mapped[list] = mapped_column(_jsonb_column(), server_default="[]", nullable=False)


class TriageHashSet(Base, TimestampMixin):
    """Investigator-provided hash sets used during triage classification."""

    __tablename__ = "triage_hash_sets"
    __table_args__ = (
        UniqueConstraint("name", name="uq_triage_hash_sets_name"),
        Index("ix_triage_hash_sets_created_by", "created_by"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    hashes: Mapped[list] = mapped_column(_jsonb_column(), server_default="[]", nullable=False)
    hash_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
