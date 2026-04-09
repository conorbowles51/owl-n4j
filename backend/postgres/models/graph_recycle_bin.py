from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class GraphRecycleBinItem(Base, TimestampMixin):
    """Recoverable snapshot of a graph entity removed from the active Neo4j graph."""

    __tablename__ = "graph_recycle_bin_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_delete', 'active', 'restoring', 'restored', 'purged')",
            name="ck_graph_recycle_bin_items_status",
        ),
        CheckConstraint(
            "item_type IN ('entity_delete', 'merge_undo')",
            name="ck_graph_recycle_bin_items_item_type",
        ),
        UniqueConstraint("recycle_key", name="uq_graph_recycle_bin_items_recycle_key"),
        Index("ix_graph_recycle_bin_items_case_status_deleted", "case_id", "status", "deleted_at"),
        Index("ix_graph_recycle_bin_items_case_type_status_deleted", "case_id", "item_type", "status", "deleted_at"),
        Index("ix_graph_recycle_bin_items_original_key", "case_id", "original_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )

    recycle_key: Mapped[str] = mapped_column(String(512), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False, default="entity_delete")
    original_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_type: Mapped[str | None] = mapped_column(String(255), nullable=True)

    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    deleted_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_delete")
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    case = relationship("Case", foreign_keys=[case_id])
