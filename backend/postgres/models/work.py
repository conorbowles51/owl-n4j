from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class CaseTask(Base, TimestampMixin):
    __tablename__ = "case_tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('todo', 'in_progress', 'done')",
            name="ck_case_tasks_status",
        ),
        CheckConstraint(
            "priority IN ('low', 'standard', 'high', 'urgent')",
            name="ck_case_tasks_priority",
        ),
        CheckConstraint(
            "parent_task_id IS NULL OR parent_task_id <> id",
            name="ck_case_tasks_not_self_parent",
        ),
        UniqueConstraint("case_id", "legacy_id", name="uq_case_tasks_legacy_identity"),
        Index("ix_case_tasks_case_status_due", "case_id", "status", "due_at"),
        Index("ix_case_tasks_case_assignee_due", "case_id", "assignee_user_id", "due_at"),
        Index("ix_case_tasks_case_parent", "case_id", "parent_task_id"),
        Index("ix_case_tasks_case_deleted", "case_id", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="todo")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_tasks.id", ondelete="SET NULL"), nullable=True
    )
    deadline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_deadlines.id", ondelete="SET NULL"), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    migration_metadata: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    needs_migration_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    assignee = relationship("User", foreign_keys=[assignee_user_id])
    creator = relationship("User", foreign_keys=[created_by_user_id])
    editor = relationship("User", foreign_keys=[updated_by_user_id])
    deadline = relationship("CaseDeadline", foreign_keys=[deadline_id])
    parent = relationship("CaseTask", remote_side=[id], foreign_keys=[parent_task_id])


class CaseTaskLink(Base, TimestampMixin):
    __tablename__ = "case_task_links"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('dossier', 'entry', 'evidence')",
            name="ck_case_task_links_target_type",
        ),
        UniqueConstraint("task_id", "target_type", "target_id", name="uq_case_task_link_target"),
        Index("ix_case_task_links_case_target", "case_id", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_anchor: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    task = relationship("CaseTask", foreign_keys=[task_id])
    creator = relationship("User", foreign_keys=[created_by_user_id])


class SharedEvidencePin(Base, TimestampMixin):
    __tablename__ = "shared_evidence_pins"
    __table_args__ = (
        UniqueConstraint("case_id", "evidence_file_id", name="uq_shared_evidence_pin"),
        Index("ix_shared_evidence_pins_case_created", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pinned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    legacy_metadata: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)

    evidence_file = relationship("EvidenceFile", foreign_keys=[evidence_file_id])
    pinned_by = relationship("User", foreign_keys=[pinned_by_user_id])


class WorkLegacyMapping(Base, TimestampMixin):
    __tablename__ = "work_legacy_mappings"
    __table_args__ = (
        UniqueConstraint("case_id", "source_type", "source_id", name="uq_work_legacy_mapping"),
        Index("ix_work_legacy_mappings_canonical", "canonical_type", "canonical_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="migrated")
    migration_metadata: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
