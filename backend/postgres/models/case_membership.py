from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.enums import CaseMembershipRole
from postgres.models.mixins import TimestampMixin


class CaseMembership(Base, TimestampMixin):
    __tablename__ = "case_memberships"

    # Composite key, one row per user per case
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    membership_role: Mapped[CaseMembershipRole] = mapped_column(
        Enum(CaseMembershipRole, name="case_membership_role"),
        nullable=False,
    )

     # JSON permissions object
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Who added/invited this person
    added_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    user = relationship("User", foreign_keys=[user_id])
    case = relationship("Case", foreign_keys=[case_id])
    added_by = relationship("User", foreign_keys=[added_by_user_id])