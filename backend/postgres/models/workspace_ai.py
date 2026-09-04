"""Durable, reviewable AI assistance for Workspace casework."""

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


class WorkspaceAIOutput(Base, TimestampMixin):
    """One durable generation attempt and its immutable reviewable result.

    Regeneration creates a new version rather than mutating a completed output.
    ``content`` and ``citations`` are structured JSON so citation validation can
    be repeated at acceptance time without trusting rendered prose.
    """

    __tablename__ = "workspace_ai_outputs"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('dossier', 'theory')",
            name="ck_workspace_ai_outputs_target_type",
        ),
        CheckConstraint(
            "output_type IN ('statement_summary', 'statement_comparison', 'theory_analysis')",
            name="ck_workspace_ai_outputs_output_type",
        ),
        CheckConstraint(
            "job_status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_workspace_ai_outputs_job_status",
        ),
        CheckConstraint(
            "review_status IN ('pending_review', 'accepted', 'rejected')",
            name="ck_workspace_ai_outputs_review_status",
        ),
        CheckConstraint(
            "citation_status IN ('pending', 'valid', 'invalid')",
            name="ck_workspace_ai_outputs_citation_status",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_workspace_ai_outputs_progress",
        ),
        UniqueConstraint(
            "case_id",
            "target_type",
            "target_id",
            "output_type",
            "version",
            name="uq_workspace_ai_output_version",
        ),
        Index(
            "ix_workspace_ai_outputs_case_target",
            "case_id",
            "target_type",
            "target_id",
            "created_at",
        ),
        Index(
            "ix_workspace_ai_outputs_case_status",
            "case_id",
            "job_status",
            "review_status",
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
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    output_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_output_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_ai_outputs.id", ondelete="SET NULL"),
        nullable=True,
    )

    job_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued", server_default="queued"
    )
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_review", server_default="pending_review"
    )
    citation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", server_default="pending"
    )
    progress: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    content: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list, server_default="[]"
    )
    source_set: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list, server_default="[]"
    )
    generation_input: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )
    proposed_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list, server_default="[]"
    )
    accepted_targets: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=list, server_default="[]"
    )
    model_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    mandate_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_mandate_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent_output = relationship("WorkspaceAIOutput", remote_side=[id])
    requester = relationship("User", foreign_keys=[requested_by_user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by_user_id])
    mandate_version = relationship("CaseMandateVersion", foreign_keys=[mandate_version_id])
