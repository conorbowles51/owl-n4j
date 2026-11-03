from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class Case(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'on_hold', 'closed')",
            name="ck_cases_status",
        ),
        CheckConstraint(
            "address_lookup_mode IS NULL OR address_lookup_mode IN ('auto', 'flag')",
            name="ck_cases_address_lookup_mode",
        ),
        Index("ix_cases_deleted", "id", postgresql_where=text("deleted_at IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", nullable=False
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    # Region for phone numbers written without + (docs/cellebrite/02 section 8.3); null means the US default.
    phone_default_region: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # 'auto' or 'flag' (services.address_lookup); null means the system default.
    address_lookup_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Deleted items (postgres/soft_delete.py): set while the case waits 30 days to be purged; every read hides it.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_by = relationship("User", foreign_keys=[created_by_user_id])
    owner = relationship("User", foreign_keys=[owner_user_id])
