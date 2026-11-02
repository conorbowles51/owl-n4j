"""Phone identities and the record subjects of phone decisions (docs/cellebrite/02 sections 1.2, 8.5, 8.8).

Only the columns a decision needs are mapped: ``decisions.record`` checks a subject's ``id`` and ``case_id``. The
tables are created by ``20261102_phone_identities`` and ``20261102_phone_decisions``; the interpretation services
write them with SQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base


class PhoneIdentity(Base):
    __tablename__ = "phone_identities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                               nullable=False)
    identity_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    subkind: Mapped[str | None] = mapped_column(String(32))
    value_normalised: Mapped[str] = mapped_column(Text, nullable=False)
    value_display: Mapped[str] = mapped_column(Text, nullable=False)
    sighting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phone_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PhoneRecordSubject(Base):
    """A record a decision is about (1.2): ``id`` is the record's ``record_uid``; created with the first decision."""

    __tablename__ = "phone_record_subjects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                               nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("phone_extractions.id",
                                                                                      ondelete="CASCADE"), nullable=False)
    document_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
