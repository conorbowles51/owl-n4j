from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class DossierRole(Base, TimestampMixin):
    __tablename__ = "dossier_roles"
    __table_args__ = (UniqueConstraint("dossier_id", "normalized_name", name="uq_dossier_role_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    template_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    dossier = relationship("CaseProfile", foreign_keys=[dossier_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class DossierLink(Base, TimestampMixin):
    __tablename__ = "dossier_links"
    __table_args__ = (
        UniqueConstraint("dossier_id", "target_type", "target_id", name="uq_dossier_link_target"),
        Index("ix_dossier_links_case_target", "case_id", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    relationship_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_anchor: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    dossier = relationship("CaseProfile", foreign_keys=[dossier_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class DossierAssessment(Base, TimestampMixin):
    __tablename__ = "dossier_assessments"
    __table_args__ = (Index("ix_dossier_assessments_case_dossier", "case_id", "dossier_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    legacy_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provenance_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="investigator", server_default="investigator"
    )
    generated_output_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_ai_outputs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    dossier = relationship("CaseProfile", foreign_keys=[dossier_id])
    author = relationship("User", foreign_keys=[author_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])


class DossierAssessmentLink(Base, TimestampMixin):
    __tablename__ = "dossier_assessment_links"
    __table_args__ = (UniqueConstraint("assessment_id", "target_type", "target_id", name="uq_dossier_assessment_link"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dossier_assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_anchor: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)

    assessment = relationship("DossierAssessment", foreign_keys=[assessment_id])


class DossierMedia(Base, TimestampMixin):
    __tablename__ = "dossier_media"
    __table_args__ = (
        UniqueConstraint("dossier_id", "evidence_file_id", name="uq_dossier_media_evidence"),
        Index("ix_dossier_media_dossier_order", "dossier_id", "ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_cover: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    focal_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    focal_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    crop_metadata: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    source_anchor: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    dossier = relationship("CaseProfile", foreign_keys=[dossier_id])
    evidence_file = relationship("EvidenceFile", foreign_keys=[evidence_file_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class DossierInterview(Base, TimestampMixin):
    __tablename__ = "dossier_interviews"
    __table_args__ = (Index("ix_dossier_interviews_dossier_date", "dossier_id", "interview_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    interview_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    interviewer_user_ids: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="planned")
    working_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    dossier = relationship("CaseProfile", foreign_keys=[dossier_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])


class DossierInterviewEvidenceLink(Base, TimestampMixin):
    __tablename__ = "dossier_interview_evidence_links"
    __table_args__ = (UniqueConstraint("interview_id", "evidence_file_id", name="uq_dossier_interview_evidence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dossier_interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_anchor: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)

    interview = relationship("DossierInterview", foreign_keys=[interview_id])
    evidence_file = relationship("EvidenceFile", foreign_keys=[evidence_file_id])


class DossierGeneratedOutput(Base, TimestampMixin):
    __tablename__ = "dossier_generated_outputs"
    __table_args__ = (UniqueConstraint("dossier_id", "output_type", "version", name="uq_dossier_output_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    output_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_review")
    generated_by_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mandate_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("case_mandate_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DossierLegacyMapping(Base, TimestampMixin):
    __tablename__ = "dossier_legacy_mappings"
    __table_args__ = (UniqueConstraint("case_id", "source_type", "source_id", name="uq_dossier_legacy_mapping"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    dossier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    migration_metadata: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
