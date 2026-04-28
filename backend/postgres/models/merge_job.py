"""MergeJob — tracks entity merge jobs dispatched to the evidence engine."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class MergeJob(Base, TimestampMixin):
    """Tracks an entity merge job sent to the evidence engine."""

    __tablename__ = "merge_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    engine_job_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, unique=True, index=True,
    )
    source_entity_keys: Mapped[list] = mapped_column(
        JSONB, nullable=False,
    )
    recycled_source_keys: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
    )
    merged_entity_key: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
    )
    created_by: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    case = relationship("Case", foreign_keys=[case_id])
