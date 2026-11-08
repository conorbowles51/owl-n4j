"""A kept copy of analyst work a person removed, so the removal can be undone (followups m11032229063349).

Hard deletes of dossier assessments, interviews (with their working notes), media, links and saved snapshots used
to leave nothing behind. Each now writes one row here, in the same transaction as the delete, holding every removed
row as it was. Restoring puts the rows back unchanged and stamps the copy restored; the copy itself is never edited.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

KINDS = ('dossier_assessment', 'dossier_interview', 'dossier_media', 'dossier_link', 'dossier_evidence_link',
         'snapshot',
         # Deleted items (lx-deletebin, 2026-11-08): the folder rows of a deleted evidence folder (its files wait in
         # evidence_files with deleted_at), and hard deletes that used to leave nothing to restore.
         'evidence_folder', 'entry_link', 'evidence_pin', 'case_deadline', 'chat')


class RemovedRecord(Base):
    __tablename__ = "removed_records"
    __table_args__ = (
        CheckConstraint("kind IN ('" + "', '".join(KINDS) + "')", name="ck_removed_records_kind"),
        Index("ix_removed_records_case_removed", "case_id", "removed_at"),
        Index("ix_removed_records_subject", "kind", "subject_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"),
                                                      nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # {"rows": [{"table": <table name>, "values": {column: value}}, ...]}, parent rows first.
    data: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    removed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    removed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restored_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
