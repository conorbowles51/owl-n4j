from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class CaseContext(Base, TimestampMixin):
    """Universal, investigator-authored orientation for one case."""

    __tablename__ = "case_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    case_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    investigation_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_template_key: Mapped[str] = mapped_column(String(64), nullable=False, default="generic")
    active_mandate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_mandate_versions.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    values = relationship("CaseContextValue", back_populates="context", cascade="all, delete-orphan")
    active_mandate_version = relationship("CaseMandateVersion", foreign_keys=[active_mandate_version_id])


class CaseContextTemplate(Base, TimestampMixin):
    __tablename__ = "case_context_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fields = relationship(
        "CaseContextTemplateField", back_populates="template", cascade="all, delete-orphan", order_by="CaseContextTemplateField.position"
    )


class CaseContextTemplateField(Base, TimestampMixin):
    __tablename__ = "case_context_template_fields"
    __table_args__ = (UniqueConstraint("template_id", "field_key", name="uq_case_context_template_field"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_context_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    field_type: Mapped[str] = mapped_column(String(32), nullable=False)
    choices: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template = relationship("CaseContextTemplate", back_populates="fields")


class CaseContextValue(Base, TimestampMixin):
    __tablename__ = "case_context_values"
    __table_args__ = (
        UniqueConstraint("context_id", "template_field_id", name="uq_case_context_value_field"),
        Index("ix_case_context_values_case_context", "case_id", "context_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    context_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_contexts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_context_template_fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[object] = mapped_column(JSON_DOCUMENT, nullable=False)

    context = relationship("CaseContext", back_populates="values")
    field = relationship("CaseContextTemplateField")


class CaseMandateVersion(Base):
    """Immutable instructions used to frame case AI work."""

    __tablename__ = "case_mandate_versions"
    __table_args__ = (UniqueConstraint("case_id", "version_number", name="uq_case_mandate_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_questions: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    in_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    out_of_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    perspective: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    author = relationship("User", foreign_keys=[author_user_id])


class CaseContextLegacyMapping(Base):
    __tablename__ = "case_context_legacy_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    workspace_context_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace_contexts.id", ondelete="SET NULL"), nullable=True
    )
    migrated_payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    warnings: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    migrated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
