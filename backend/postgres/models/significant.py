from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class SignificantEntity(Base, TimestampMixin):
    """A durable case-level reference to a significant Neo4j entity.

    The entity's descriptive data deliberately remains in Neo4j.  This row is
    only the shared curation manifest and audit metadata, so edits to the
    canonical entity are reflected in every Significant projection immediately.
    """

    __tablename__ = "significant_entities"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "entity_key",
            name="uq_significant_entities_case_entity",
        ),
        Index(
            "ix_significant_entities_case_active",
            "case_id",
            "removed_at",
        ),
        Index(
            "ix_significant_entities_added_by",
            "added_by_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_key: Mapped[str] = mapped_column(String(512), nullable=False)
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    addition_source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="manual",
        server_default="manual",
    )
    context: Mapped[dict] = mapped_column(
        JSON_DOCUMENT,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    # Rows are retained when membership is removed.  This gives merge/delete
    # lifecycle handlers enough information to restore membership safely and
    # preserves an auditable history without copying any graph data.
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    removed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    removal_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    added_by = relationship("User", foreign_keys=[added_by_user_id])
    removed_by = relationship("User", foreign_keys=[removed_by_user_id])
