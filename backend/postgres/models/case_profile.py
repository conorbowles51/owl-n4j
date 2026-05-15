from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


CASE_PROFILE_TYPES = (
    "person",
    "address",
    "event",
    "device",
    "organisation",
    "vehicle",
    "other",
)

CASE_PROFILE_ATTRIBUTE_KINDS = (
    "alias",
    "tag",
    "phone",
    "email",
    "address",
    "identifier",
    "device",
    "vehicle",
    "organisation",
    "date",
    "custom",
)


class CaseProfile(Base, TimestampMixin):
    """Investigator-curated case profile stored canonically in Postgres."""

    __tablename__ = "case_profiles"
    __table_args__ = (
        CheckConstraint(
            "profile_type IN ('person', 'address', 'event', 'device', 'organisation', 'vehicle', 'other')",
            name="ck_case_profiles_type",
        ),
        Index("ix_case_profiles_case_type_name", "case_id", "profile_type", "display_name"),
        Index("ix_case_profiles_case_archived", "case_id", "archived_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    profile_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    importance: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    case = relationship("Case", foreign_keys=[case_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    updated_by = relationship("User", foreign_keys=[updated_by_user_id])
    archived_by = relationship("User", foreign_keys=[archived_by_user_id])
    attributes = relationship(
        "CaseProfileAttribute",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CaseProfileAttribute.ordinal",
    )
    graph_node_links = relationship(
        "CaseProfileGraphNodeLink",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CaseProfileGraphNodeLink.created_at",
    )
    evidence_links = relationship(
        "CaseProfileEvidenceLink",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CaseProfileEvidenceLink.created_at",
    )
    note_links = relationship(
        "CaseProfileNoteLink",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CaseProfileNoteLink.created_at",
    )
    finding_links = relationship(
        "CaseProfileFindingLink",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="CaseProfileFindingLink.created_at",
    )


class CaseProfileAttribute(Base, TimestampMixin):
    __tablename__ = "case_profile_attributes"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('alias', 'tag', 'phone', 'email', 'address', 'identifier', 'device', 'vehicle', 'organisation', 'date', 'custom')",
            name="ck_case_profile_attributes_kind",
        ),
        Index("ix_case_profile_attributes_case_kind_value", "case_id", "kind", "value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    profile = relationship("CaseProfile", back_populates="attributes")
    case = relationship("Case", foreign_keys=[case_id])


class CaseProfileGraphNodeLink(Base, TimestampMixin):
    __tablename__ = "case_profile_graph_node_links"
    __table_args__ = (
        UniqueConstraint("profile_id", "node_key", name="uq_case_profile_graph_node"),
        Index("ix_case_profile_graph_case_node", "case_id", "node_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_key: Mapped[str] = mapped_column(String(512), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    node_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    relationship_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    profile = relationship("CaseProfile", back_populates="graph_node_links")
    case = relationship("Case", foreign_keys=[case_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class CaseProfileEvidenceLink(Base, TimestampMixin):
    __tablename__ = "case_profile_evidence_links"
    __table_args__ = (
        UniqueConstraint("profile_id", "evidence_file_id", name="uq_case_profile_evidence_file"),
        Index("ix_case_profile_evidence_case_file", "case_id", "evidence_file_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    profile = relationship("CaseProfile", back_populates="evidence_links")
    case = relationship("Case", foreign_keys=[case_id])
    evidence_file = relationship("EvidenceFile", foreign_keys=[evidence_file_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class CaseProfileNoteLink(Base, TimestampMixin):
    __tablename__ = "case_profile_note_links"
    __table_args__ = (
        UniqueConstraint("profile_id", "note_id", name="uq_case_profile_note"),
        Index("ix_case_profile_notes_case_note", "case_id", "note_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note_id: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    profile = relationship("CaseProfile", back_populates="note_links")
    case = relationship("Case", foreign_keys=[case_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class CaseProfileFindingLink(Base, TimestampMixin):
    __tablename__ = "case_profile_finding_links"
    __table_args__ = (
        UniqueConstraint("profile_id", "finding_id", name="uq_case_profile_finding"),
        Index("ix_case_profile_findings_case_finding", "case_id", "finding_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("case_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[str] = mapped_column(String(128), nullable=False)
    relationship_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    profile = relationship("CaseProfile", back_populates="finding_links")
    case = relationship("Case", foreign_keys=[case_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
