"""A person's saved review of one original PDF page: what the page is, why, who said so and when.

Append-only: each save is a new row, and an undo stamps the row it reverses, so a page's history stays whole. The
page's current review is its newest row not undone. A review belongs to the file's exact bytes (``file_sha256``).
It describes a page and changes no reading, row, total or check.
"""
import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from postgres.base import Base

PAGE_DISPOSITIONS = ('supporting_correspondence', 'continuation', 'blank', 'other')


class FinancialPageReview(Base):
    __tablename__ = 'financial_page_reviews'
    __table_args__ = (
        CheckConstraint('page_number >= 1', name='ck_financial_page_reviews_page'),
        CheckConstraint("disposition IN ('supporting_correspondence', 'continuation', 'blank', 'other')",
                        name='ck_financial_page_reviews_disposition'),
        Index('ix_financial_page_reviews_file_page', 'evidence_file_id', 'page_number'),
        Index('ix_financial_page_reviews_case', 'case_id'),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='CASCADE'), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('evidence_files.id', ondelete='CASCADE'), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    saved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    saved_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    saved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Set when a model did the work for a person, so the review is never shown as the person's own reading.
    origin: Mapped[dict[str, Any] | None] = mapped_column(JSON().with_variant(JSONB(), 'postgresql'), nullable=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    undone_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
