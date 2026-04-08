"""Workspace models — replaces JSON-on-disk storage for workspace data."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class WorkspaceContext(Base, TimestampMixin):
    """Case context: client profile, charges, legal exposure, etc."""

    __tablename__ = "workspace_contexts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspaceWitness(Base, TimestampMixin):
    """Witness record within a case workspace."""

    __tablename__ = "workspace_witnesses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    witness_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspaceTheory(Base, TimestampMixin):
    """Investigation theory / hypothesis."""

    __tablename__ = "workspace_theories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    theory_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspaceTask(Base, TimestampMixin):
    """Investigation task within a case."""

    __tablename__ = "workspace_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspaceNote(Base, TimestampMixin):
    """Investigative note."""

    __tablename__ = "workspace_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspaceFinding(Base, TimestampMixin):
    """Workspace finding / investigative conclusion."""

    __tablename__ = "workspace_findings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspacePinnedItem(Base, TimestampMixin):
    """Pinned evidence / entity reference."""

    __tablename__ = "workspace_pinned_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pin_id: Mapped[str] = mapped_column(String(64), nullable=False)
    item_type: Mapped[str] = mapped_column(String(64), nullable=False)
    item_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)


class WorkspaceDeadlineConfig(Base, TimestampMixin):
    """Deadline configuration for a case (trial date, court, individual deadlines)."""

    __tablename__ = "workspace_deadline_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    data: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
