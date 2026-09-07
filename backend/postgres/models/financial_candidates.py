"""Immutable extraction originals, deliberately outside the money ledger.

Review will be recorded separately; these tables never acquire a mutable amount
or admission state. Case/file deletion still cascades. PostgreSQL migration
triggers reject UPDATE; the ORM guard also protects SQLite service tests.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, event, func, inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base


class FinancialCandidateMapping(Base):
    __tablename__ = "financial_candidate_mappings"
    __table_args__ = (
        UniqueConstraint("case_id", "evidence_file_id", "mapping_revision", name="uq_candidate_mapping_revision"),
        CheckConstraint("length(mapping_revision) = 64 AND length(snapshot_sha256) = 64", name="ck_candidate_mapping_digests"),
        CheckConstraint("candidate_count > 0 AND candidate_count <= 1000", name="ck_candidate_mapping_count"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False)
    mapping_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    actor: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinancialExtractionCandidate(Base):
    __tablename__ = "financial_extraction_candidates"
    __table_args__ = (
        UniqueConstraint("mapping_id", "row_index", name="uq_candidate_mapping_row"),
        UniqueConstraint("candidate_key", name="uq_extraction_candidate_key"),
        CheckConstraint("row_index >= 0", name="ck_extraction_candidate_row"),
        CheckConstraint("length(candidate_key) = 64 AND length(snapshot_sha256) = 64", name="ck_extraction_candidate_digests"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mapping_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_candidate_mappings.id", ondelete="CASCADE"), nullable=False)
    candidate_key: Mapped[str] = mapped_column(String(64), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)


@event.listens_for(FinancialCandidateMapping, "before_update")
@event.listens_for(FinancialExtractionCandidate, "before_update")
def _immutable_original(mapper, connection, target):
    if any(attribute.history.has_changes() for attribute in inspect(target).attrs):
        raise ValueError("Extraction originals are immutable; record a separate review or mapping revision.")
