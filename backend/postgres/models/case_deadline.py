from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class CaseDeadline(Base, TimestampMixin):
    __tablename__ = "case_deadlines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    case = relationship("Case", foreign_keys=[case_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
