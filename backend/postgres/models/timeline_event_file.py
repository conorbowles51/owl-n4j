"""An evidence file (a photo first) attached to a Timeline event, with who attached it and when."""
import uuid
from sqlalchemy import ForeignKey, String, UniqueConstraint, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from postgres.base import Base


class TimelineEventFile(Base):
    __tablename__ = "timeline_event_files"
    __table_args__ = (UniqueConstraint("case_id", "event_key", "evidence_file_id", name="uq_timeline_event_file"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    # The event's key as the Timeline shows it (a graph event key, "timeline-entry:..." or "photo:..."); events
    # live in the graph and in timeline_entries, so the key is held as text and not as a foreign key.
    event_key: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("evidence_files.id", ondelete="CASCADE"), index=True)
    added_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
