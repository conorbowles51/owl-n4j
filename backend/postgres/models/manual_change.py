"""Manual changes: every time a person changes, confirms or sets aside something the system produced.

One row per decision, written in the same transaction as the save it describes (a save rolled back leaves no row).
Rows are only added. They feed the lessons inbox (``services.manual_changes``): repeats of one pattern (kind, field,
the reader or rule that produced the value, the layout or bank) become one lesson item for a lesson job.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

CHANGE_TYPES = ('change', 'confirm', 'set_aside')


def _json():
    return JSONB().with_variant(JSON(), 'sqlite')


class ManualChange(Base):
    __tablename__ = 'manual_changes'
    __table_args__ = (
        CheckConstraint(f"change_type IN {CHANGE_TYPES}", name='ck_manual_changes_type'),
        Index('ix_manual_changes_case', 'case_id', 'created_at'),
        Index('ix_manual_changes_pattern', 'pattern_key'),
        Index('uq_manual_changes_source_ref', 'source_ref', unique=True),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False, default='')
    subject_id: Mapped[str] = mapped_column(String(200), nullable=False, default='')
    field: Mapped[str] = mapped_column(String(300), nullable=False, default='')
    producer: Mapped[str] = mapped_column(String(300), nullable=False, default='')
    layout: Mapped[str] = mapped_column(String(300), nullable=False, default='')
    pattern_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    before: Mapped[object | None] = mapped_column(_json(), nullable=True)
    after: Mapped[object | None] = mapped_column(_json(), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default='')
    link: Mapped[str] = mapped_column(Text, nullable=False, default='')
    actor_name: Mapped[str] = mapped_column(String(300), nullable=False, default='')
    actor_email: Mapped[str] = mapped_column(String(300), nullable=False, default='')
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    historic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 'app' (a route), 'phone' (a phone review screen), 'backfill' (a change saved before this table existed).
    source: Mapped[str] = mapped_column(String(20), nullable=False, default='app')
    # The record the change came from when it is recorded from another table (backfill): one row per source record.
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # A record this one corrects (a historic save compared later): the original stays visible, this one counts.
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
