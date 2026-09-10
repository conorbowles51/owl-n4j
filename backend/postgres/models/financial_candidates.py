"""Immutable extraction originals, deliberately outside the money ledger.

Review will be recorded separately; these tables never acquire a mutable amount
or admission state. Case/file deletion still cascades. PostgreSQL migration
triggers reject UPDATE; the ORM guard also protects SQLite service tests.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event, func, inspect
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


class FinancialCandidateReview(Base):
    __tablename__ = "financial_candidate_reviews"
    __table_args__ = (
        UniqueConstraint("candidate_id", "sequence", name="uq_candidate_review_sequence"),
        CheckConstraint("sequence > 0", name="ck_candidate_review_sequence"),
        CheckConstraint("status IN ('pending', 'resolved', 'rejected')", name="ck_candidate_review_status"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_candidate_review_reason"),
        CheckConstraint("(status = 'resolved' AND reading IS NOT NULL) OR (status <> 'resolved' AND reading IS NULL)", name="ck_candidate_review_reading"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_extraction_candidates.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reading: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite"), nullable=True)
    actor: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    original_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinancialCandidateFinalization(Base):
    """One immutable, whole-file candidate materialization receipt."""
    __tablename__ = "financial_candidate_finalizations"
    __table_args__ = (
        UniqueConstraint("case_id", "evidence_file_id", name="uq_candidate_finalization_file"),
        UniqueConstraint("source_document_id", name="uq_candidate_finalization_document"),
        CheckConstraint("length(source_sha256) = 64 AND length(snapshot_sha256) = 64", name="ck_candidate_finalization_digests"),
        CheckConstraint("transaction_count > 0 AND transaction_count <= 1000", name="ck_candidate_finalization_count"),
        CheckConstraint("length(trim(reason)) > 0", name="ck_candidate_finalization_reason"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_source_documents.id", ondelete="CASCADE"), nullable=False)
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_ingestion_runs.id", ondelete="CASCADE"), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    actor: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinancialCandidateTransaction(Base):
    """Retain the original ledger row even after that row is corrected."""
    __tablename__ = "financial_candidate_transactions"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_candidate_transaction_candidate"),
        UniqueConstraint("transaction_id", name="uq_candidate_transaction_row"),
        UniqueConstraint("finalization_id", "source_claim_sha256", name="uq_candidate_transaction_source"),
        CheckConstraint("length(source_claim_sha256) = 64 AND length(review_revision) = 64 AND length(original_sha256) = 64", name="ck_candidate_transaction_digests"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finalization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_candidate_finalizations.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_extraction_candidates.id", ondelete="CASCADE"), nullable=False)
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_candidate_reviews.id", ondelete="CASCADE"), nullable=False)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("financial_transactions.id", ondelete="CASCADE"), nullable=False)
    source_claim_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    review_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    original_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


@event.listens_for(FinancialCandidateFinalization, "before_update")
@event.listens_for(FinancialCandidateTransaction, "before_update")
@event.listens_for(FinancialCandidateReview, "before_update")
@event.listens_for(FinancialCandidateMapping, "before_update")
@event.listens_for(FinancialExtractionCandidate, "before_update")
def _immutable_original(mapper, connection, target):
    if any(attribute.history.has_changes() for attribute in inspect(target).attrs):
        raise ValueError("Extraction originals are immutable; record a separate review or mapping revision.")


class FinancialStatementReviewDraft(Base):
    """Replaceable working controls, separate from immutable finalized receipts."""
    __tablename__ = 'financial_statement_review_drafts'
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('evidence_files.id', ondelete='CASCADE'), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_scopes: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=False)
    editor_draft: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=True)
    actor: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint('version > 0', name='ck_statement_review_draft_version'),)
