"""Which records a `phone_selection` link holds, one row per record (07 section 6.4 item 7).

A selection is one link on a dossier, a Workspace entry or a task, with its frozen record list. This index lets the
reverse lookup answer "where is this record used" for a record collected only inside a selection. It is written when
the link is added and removed with it. `link_id` names the link in the table `container_type` points to; the lookup
joins back to that table, so a row whose link is gone is never reported.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin

CONTAINER_TYPES = ("dossier", "entry", "task")


class CollectionMembership(Base, TimestampMixin):
    __tablename__ = "collection_memberships"
    __table_args__ = (
        CheckConstraint("container_type IN ('dossier', 'entry', 'task')", name="ck_collection_memberships_container"),
        Index("ix_collection_memberships_case_record", "case_id", "record_id"),
        Index("ix_collection_memberships_link", "link_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    container_type: Mapped[str] = mapped_column(String(16), nullable=False)
    container_id: Mapped[str] = mapped_column(String(64), nullable=False)
    link_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    record_id: Mapped[str] = mapped_column(String(512), nullable=False)
