"""Who did what, from where: an append-only record of sign-ins, uploads and Financial entries.

No foreign keys: deleting a case, user or file must not erase the record of what
was done to it. The database refuses UPDATE, DELETE and TRUNCATE on the table
(migration ``20261028_activity_events``); rows are kept indefinitely.
"""
import uuid
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class ActivityEvent(Base):
    __tablename__ = 'activity_events'
    __table_args__ = (
        Index('ix_activity_events_case_at', 'case_id', 'at'),
        Index('ix_activity_events_user_at', 'user_id', 'at'),
        Index('ix_activity_events_action_at', 'action', 'at'),
    )
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), 'sqlite'), primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # The person, as they were named at the time; "System" for automatic steps.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Network address of the browser (from the local proxy's X-Real-IP), or "system".
    source_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # First 16 hex of sha256(sign-in token): ties actions to one sign-in without storing the token.
    session_ref: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Which screen sent it (X-Loupe-Origin), or "automatic".
    origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), 'sqlite'), nullable=False, default=dict)
