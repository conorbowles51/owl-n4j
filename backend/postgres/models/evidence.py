from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class EvidenceFolder(Base, TimestampMixin):
    __tablename__ = "evidence_folders"
    __table_args__ = (
        UniqueConstraint("case_id", "parent_id", "name", name="uq_evidence_folders_case_parent_name"),
        Index("ix_evidence_folders_case_id", "case_id"),
        Index("ix_evidence_folders_parent_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_folders.id", ondelete="CASCADE"),
        nullable=True,
    )

    disk_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    # Folder context & profile — used for LLM extraction prompt enrichment.
    # context_instructions: free-text context injected into entity extraction prompts.
    # mandatory_instructions: ordered list of one-line extraction rules.
    # profile_overrides: structured JSONB for additive profile settings
    #   (currently only special_entity_types).
    context_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandatory_instructions: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    profile_overrides: Mapped[dict | None] = mapped_column("profile_overrides", JSONB, nullable=True)

    # Relationships
    case = relationship("Case", foreign_keys=[case_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    parent = relationship("EvidenceFolder", remote_side=[id], foreign_keys=[parent_id], back_populates="children")
    children = relationship("EvidenceFolder", foreign_keys=[parent_id], cascade="all, delete-orphan", back_populates="parent")
    files = relationship(
        "EvidenceFile",
        back_populates="folder",
        cascade="all, delete-orphan",
        foreign_keys="EvidenceFile.folder_id",
    )


class EvidenceFile(Base, TimestampMixin):
    __tablename__ = "evidence_files"
    __table_args__ = (
        CheckConstraint(
            "status IN ('unprocessed', 'processing', 'processed', 'failed')",
            name="ck_evidence_files_status",
        ),
        Index("ix_evidence_files_case_id", "case_id"),
        Index("ix_evidence_files_folder_id", "folder_id"),
        Index("ix_evidence_files_sha256", "sha256"),
        Index("ix_evidence_files_case_status", "case_id", "status"),
        Index("ix_evidence_files_legacy_id", "legacy_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_folders.id", ondelete="CASCADE"),
        nullable=True,
    )

    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unprocessed")

    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_relevant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    engine_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relationship_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_processed_profile_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_processed_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}", nullable=False)

    # Relationships
    case = relationship("Case", foreign_keys=[case_id])
    folder = relationship(
        "EvidenceFolder",
        back_populates="files",
        foreign_keys=[folder_id],
    )
    last_processed_folder = relationship("EvidenceFolder", foreign_keys=[last_processed_folder_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    duplicate_of = relationship("EvidenceFile", remote_side=[id], foreign_keys=[duplicate_of_id])


class IngestionLog(Base):
    __tablename__ = "ingestion_logs"
    __table_args__ = (
        Index("ix_ingestion_logs_case_id", "case_id"),
        Index("ix_ingestion_logs_case_created", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="SET NULL"),
        nullable=True,
    )

    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    case = relationship("Case", foreign_keys=[case_id])
    evidence_file = relationship("EvidenceFile", foreign_keys=[evidence_file_id])
