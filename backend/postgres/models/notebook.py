"""Case notebook models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class NotebookNote(Base, TimestampMixin):
    """A public investigative note within a case."""

    __tablename__ = "notebook_notes"
    __table_args__ = (
        Index("ix_notebook_notes_case_updated", "case_id", "updated_at"),
        Index("ix_notebook_notes_author_case", "author_user_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, server_default="[]", nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), default="case", server_default="case", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    links: Mapped[list["NotebookNoteLink"]] = relationship(
        "NotebookNoteLink",
        back_populates="note",
        cascade="all, delete-orphan",
        order_by="NotebookNoteLink.created_at",
    )


class NotebookNoteLink(Base, TimestampMixin):
    """A link from a note to an investigative object."""

    __tablename__ = "notebook_note_links"
    __table_args__ = (
        UniqueConstraint("note_id", "target_type", "target_id", name="uq_notebook_note_target"),
        Index("ix_notebook_links_case_target", "case_id", "target_type", "target_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notebook_notes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    target_label: Mapped[str | None] = mapped_column(String(512), nullable=True)
    link_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON_DOCUMENT,
        default=dict,
        server_default="{}",
        nullable=False,
    )

    note: Mapped[NotebookNote] = relationship("NotebookNote", back_populates="links")
