"""Production numbers (Bates numbers): sets a case numbers its files from, and numbers files arrived with.

Assigned numbers come from a set and are never reissued: ``next_number`` only moves up, an issue is one row that is
never deleted, and a removal or withdrawal leaves the row and its range in place. A purged file leaves its name and
hash on the row (``evidence_file_id`` becomes NULL), so the range stays accounted for.

Received numbers are what a disclosure called the file. A row here is a person's act: typed, imported or a confirmed
suggestion. A suggestion read from a file name is not stored at all; it is worked out from the name each time and
shown as suggested (services/production_numbers.py), so nothing a machine read can pass for a person's value.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


def _user_fk():
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ProductionSet(Base, TimestampMixin):
    """One numbered production of a case. Prefix, start and padding are fixed once a set exists."""

    __tablename__ = "production_sets"
    __table_args__ = (
        UniqueConstraint("case_id", "prefix_key", name="uq_production_sets_case_prefix"),
        CheckConstraint("start_number >= 0", name="ck_production_sets_start"),
        CheckConstraint("padding BETWEEN 1 AND 12", name="ck_production_sets_padding"),
        CheckConstraint("next_number >= start_number", name="ck_production_sets_next"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    prefix_key: Mapped[str] = mapped_column(String(32), nullable=False)
    start_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    padding: Mapped[int] = mapped_column(Integer, nullable=False)
    next_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()


class ProductionAssignment(Base, TimestampMixin):
    """A range issued to one file: one number per page, or one number for a file with no pages to number."""

    __tablename__ = "production_assignments"
    __table_args__ = (
        UniqueConstraint("set_id", "first_number", name="uq_production_assignments_set_first"),
        CheckConstraint("last_number >= first_number", name="ck_production_assignments_range"),
        CheckConstraint("level IN ('page', 'file')", name="ck_production_assignments_level"),
        Index("ix_production_assignments_case", "case_id", "first_number"),
        Index("ix_production_assignments_file", "evidence_file_id"),
        Index("uq_production_assignments_live_file", "set_id", "evidence_file_id", unique=True,
              postgresql_where=text("withdrawn_at IS NULL"), sqlite_where=text("withdrawn_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_sets.id", ondelete="CASCADE"), nullable=False)
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="SET NULL"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    assigned_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    withdrawn_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReceivedNumber(Base, TimestampMixin):
    """A range a disclosure gave a file, as a person entered, imported or confirmed it. Rows are never overwritten:
    a correction withdraws the old row, which stays visible, and adds a new one."""

    __tablename__ = "received_numbers"
    __table_args__ = (
        CheckConstraint("last_number >= first_number", name="ck_received_numbers_range"),
        CheckConstraint("source IN ('person', 'import', 'file_name')", name="ck_received_numbers_source"),
        CheckConstraint("status IN ('confirmed', 'rejected', 'withdrawn')", name="ck_received_numbers_status"),
        Index("ix_received_numbers_case", "case_id", "first_number"),
        Index("ix_received_numbers_file", "evidence_file_id"),
        Index("uq_received_numbers_live", "evidence_file_id", "first_text", "last_text", unique=True,
              postgresql_where=text("status <> 'withdrawn'"), sqlite_where=text("status <> 'withdrawn'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False)
    prefix_key: Mapped[str] = mapped_column(String(32), nullable=False)
    first_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_text: Mapped[str] = mapped_column(String(64), nullable=False)
    last_text: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    decided_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProductionStampedCopy(Base, TimestampMixin):
    """A PDF copy with the numbers printed on its pages. A derived file with its own hash, kept outside the evidence
    folders; ``source_sha256`` is the original's hash, measured from the original before and after stamping."""

    __tablename__ = "production_stamped_copies"
    __table_args__ = (Index("ix_production_stamped_copies_assignment", "assignment_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("production_assignments.id", ondelete="CASCADE"), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk()
