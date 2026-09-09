"""Canonical authored Workspace entries and their immutable history."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")

WORKSPACE_ENTRY_TYPES = ("note", "finding", "theory")
FINDING_STATES = ("draft", "active", "superseded", "withdrawn")
THEORY_STATES = (
    "proposed",
    "investigating",
    "substantiated",
    "weakened",
    "rejected",
    "converted",
)
FINDING_SIGNIFICANCE = ("high", "medium", "low")
ENTRY_REVIEW_STATES = ("accepted", "pending", "rejected")
ENTRY_LINK_RELATIONSHIPS = ("unclassified", "supports", "contradicts", "context")
ENTRY_LINK_TARGET_TYPES = (
    "evidence",
    "graph_entity",
    "dossier",
    "entry",
    "task",
    "deadline",
    "timeline_event",
    "agent_artifact",
    "witness",
)
ENTRY_EVENT_TYPES = (
    "created",
    "updated",
    "lifecycle_changed",
    "confidence_changed",
    "converted",
    "deleted",
    "restored",
    "review_changed",
    "migrated",
    "link_added",
    "link_updated",
    "link_removed",
)


class WorkspaceEntry(Base, TimestampMixin):
    __tablename__ = "workspace_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('note', 'finding', 'theory')",
            name="ck_workspace_entries_type",
        ),
        CheckConstraint(
            "entry_type = 'note' OR needs_migration_review = true OR "
            "(title IS NOT NULL AND length(trim(title)) > 0)",
            name="ck_workspace_entries_required_title",
        ),
        CheckConstraint(
            "lifecycle_state IS NULL OR lifecycle_state IN "
            "('draft', 'active', 'superseded', 'withdrawn', 'proposed', "
            "'investigating', 'substantiated', 'weakened', 'rejected', 'converted')",
            name="ck_workspace_entries_lifecycle",
        ),
        CheckConstraint(
            "significance IS NULL OR significance IN ('high', 'medium', 'low')",
            name="ck_workspace_entries_significance",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_workspace_entries_confidence",
        ),
        CheckConstraint(
            "review_state IN ('accepted', 'pending', 'rejected')",
            name="ck_workspace_entries_review_state",
        ),
        CheckConstraint(
            "(entry_type = 'note' AND lifecycle_state IS NULL AND significance IS NULL "
            "AND confidence IS NULL) OR "
            "(entry_type = 'finding' AND lifecycle_state IN "
            "('draft', 'active', 'superseded', 'withdrawn') AND confidence IS NULL "
            "AND (significance IS NOT NULL OR needs_migration_review = true)) OR "
            "(entry_type = 'theory' AND lifecycle_state IN "
            "('proposed', 'investigating', 'substantiated', 'weakened', 'rejected', "
            "'converted') AND significance IS NULL)",
            name="ck_workspace_entries_type_specific_fields",
        ),
        UniqueConstraint(
            "case_id",
            "legacy_source",
            "legacy_id",
            name="uq_workspace_entries_legacy_identity",
        ),
        Index("ix_workspace_entries_case_type_state", "case_id", "entry_type", "lifecycle_state"),
        Index("ix_workspace_entries_case_updated", "case_id", "updated_at"),
        Index("ix_workspace_entries_case_author", "case_id", "author_user_id"),
        Index(
            "ix_workspace_entries_case_significance",
            "case_id",
            "entry_type",
            "significance",
        ),
        Index(
            "ix_workspace_entries_case_confidence",
            "case_id",
            "entry_type",
            "confidence",
        ),
        Index("ix_workspace_entries_case_deleted", "case_id", "deleted_at"),
        Index("ix_workspace_entries_source_theory", "source_theory_entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, default=list, server_default="[]", nullable=False
    )
    lifecycle_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    significance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_state: Mapped[str] = mapped_column(
        String(16), default="accepted", server_default="accepted", nullable=False
    )

    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    source_theory_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_entries.id", ondelete="SET NULL"),
        nullable=True,
    )
    legacy_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    migration_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, server_default="{}", nullable=False
    )
    needs_migration_review: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    revisions: Mapped[list["WorkspaceEntryRevision"]] = relationship(
        "WorkspaceEntryRevision",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="WorkspaceEntryRevision.revision_number",
    )
    links: Mapped[list["WorkspaceEntryLink"]] = relationship(
        "WorkspaceEntryLink",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="WorkspaceEntryLink.created_at",
    )
    events: Mapped[list["WorkspaceEntryEvent"]] = relationship(
        "WorkspaceEntryEvent",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="WorkspaceEntryEvent.created_at",
    )
    source_theory: Mapped["WorkspaceEntry | None"] = relationship(
        "WorkspaceEntry", remote_side=[id], foreign_keys=[source_theory_entry_id]
    )


class WorkspaceEntryRevision(Base):
    __tablename__ = "workspace_entry_revisions"
    __table_args__ = (
        UniqueConstraint(
            "entry_id", "revision_number", name="uq_workspace_entry_revision_number"
        ),
        Index("ix_workspace_entry_revisions_case_entry", "case_id", "entry_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    lifecycle_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    significance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_state: Mapped[str] = mapped_column(String(16), nullable=False)
    editor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    editor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    editor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )

    entry: Mapped[WorkspaceEntry] = relationship(
        "WorkspaceEntry", back_populates="revisions"
    )


class WorkspaceEntryLink(Base, TimestampMixin):
    __tablename__ = "workspace_entry_links"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('unclassified', 'supports', 'contradicts', 'context')",
            name="ck_workspace_entry_links_relationship",
        ),
        CheckConstraint(
            "target_type IN ('evidence', 'graph_entity', 'dossier', 'entry', 'task', "
            "'deadline', 'timeline_event', 'agent_artifact', 'witness')",
            name="ck_workspace_entry_links_target_type",
        ),
        UniqueConstraint(
            "entry_id", "target_type", "target_id", name="uq_workspace_entry_link_target"
        ),
        Index(
            "ix_workspace_entry_links_case_target",
            "case_id",
            "target_type",
            "target_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    target_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    relationship_type: Mapped[str] = mapped_column(
        "relationship",
        String(16),
        default="unclassified",
        server_default="unclassified",
        nullable=False,
    )
    source_anchor: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, server_default="{}", nullable=False
    )
    link_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, default=dict, server_default="{}", nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    entry: Mapped[WorkspaceEntry] = relationship("WorkspaceEntry", back_populates="links")


class WorkspaceEntryEvent(Base):
    __tablename__ = "workspace_entry_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created', 'updated', 'lifecycle_changed', "
            "'confidence_changed', 'converted', 'deleted', 'restored', "
            "'review_changed', 'migrated', 'link_added', 'link_updated', 'link_removed')",
            name="ck_workspace_entry_events_type",
        ),
        Index("ix_workspace_entry_events_case_entry", "case_id", "entry_id"),
        Index("ix_workspace_entry_events_case_created", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    before_state: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, server_default="{}", nullable=False
    )
    after_state: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, server_default="{}", nullable=False
    )
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )

    entry: Mapped[WorkspaceEntry] = relationship("WorkspaceEntry", back_populates="events")


class WorkspaceLegacyMapping(Base):
    """Stable source-to-canonical identity used throughout staged migrations."""

    __tablename__ = "workspace_legacy_mappings"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "source_type",
            "source_id",
            "target_type",
            name="uq_workspace_legacy_mapping_source",
        ),
        Index(
            "ix_workspace_legacy_mapping_target",
            "case_id",
            "target_type",
            "target_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    migration_state: Mapped[str] = mapped_column(
        String(32), default="migrated", server_default="migrated", nullable=False
    )
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, default=dict, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now().astimezone()
    )
