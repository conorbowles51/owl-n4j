"""Explicit additions to the case chronology, retaining the as-added evidence."""
import uuid
from sqlalchemy import ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class TimelineEntry(Base, TimestampMixin):
    __tablename__ = "timeline_entries"
    __table_args__ = (UniqueConstraint("case_id", "source_kind", "source_id", name="uq_timeline_entry_source"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(24))
    # Deliberately retained if a source is removed. The saved snapshot says what
    # the investigator added; resolving it never borrows a different case's row.
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    event_snapshot: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
