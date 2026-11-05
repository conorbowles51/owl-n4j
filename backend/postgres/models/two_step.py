"""Two-step sign-in and account recovery. Codes are held only as hashes; the authenticator secret only encrypted."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class UserTwoStep(Base, TimestampMixin):
    """One row per person who has started enrolling; they are enrolled once ``confirmed_at`` is set."""

    __tablename__ = "user_two_step"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The newest 30-second step a code was accepted for: a code is never accepted twice.
    last_used_step: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class UserRecoveryCode(Base, TimestampMixin):
    __tablename__ = "user_recovery_codes"
    __table_args__ = (Index("ix_user_recovery_codes_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AccountResetCode(Base, TimestampMixin):
    """A one-time code an administrator, or the box command, gave a person to set a new password."""

    __tablename__ = "account_reset_codes"
    __table_args__ = (Index("ix_account_reset_codes_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_by: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginPolicy(Base):
    """The deployment's single sign-in policy row. No row means the requirement is off."""

    __tablename__ = "login_policy"
    __table_args__ = (CheckConstraint("id = 1", name="ck_login_policy_single_row"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    require_two_step_for_admins: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
