from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class WorkspaceAttentionState(Base, TimestampMixin):
    """Per-investigator state for personal Workspace attention items.

    Shared case-critical attention never consults this table.  The attention
    key includes the source's material version so a changed record can surface
    again without mutating or deleting a user's prior decision.
    """

    __tablename__ = "workspace_attention_states"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "user_id",
            "attention_key",
            name="uq_workspace_attention_user_item",
        ),
        Index(
            "ix_workspace_attention_case_user_snooze",
            "case_id",
            "user_id",
            "snoozed_until",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attention_key: Mapped[str] = mapped_column(String(768), nullable=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User", foreign_keys=[user_id])
