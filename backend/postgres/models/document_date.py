"""Dates read from a document's own text (lx-docdates B). See migration 20261119_document_date_readings."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base


class DocumentDateReading(Base):
    """One date (or period) read from a file's text. ``source`` 'rule' or 'model' is a reading by Loupe, shown as
    "Read by Loupe · not confirmed" with ``words`` and ``page`` until ``confirmed_at`` is set. A person's correction
    is a new row with source 'person' and ``corrects_id`` naming the reading; the original stays and stays visible."""
    __tablename__ = "document_date_readings"
    __table_args__ = (
        CheckConstraint("kind IN ('written', 'signed', 'period', 'received')", name="ck_document_date_readings_kind"),
        CheckConstraint("source IN ('rule', 'model', 'person')", name="ck_document_date_readings_source"),
        Index("uq_document_date_readings_value", "evidence_file_id", "kind", "source", "rule", "date_from", "date_to",
              unique=True),
        Index("ix_document_date_readings_case", "case_id", "date_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    rule: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    words: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrects_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_date_readings.id", ondelete="SET NULL"), nullable=True)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
