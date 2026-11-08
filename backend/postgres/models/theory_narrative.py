"""What one addition to a theory shows and finds, or how the theory's additions fit together (lx-theorybuild G, H).

Every addition (a link row of a theory, finding or note: one item or a group) carries its own narrative; a theory
also carries one for the whole (``link_id`` is null). A narrative is written by a person (``origin='person'``) or
inferred by the case model from the addition's members (``origin='agent'``, with ``model`` and ``citations``, each
naming a member it was given). An inferred narrative is a model reading: it is shown under the model's name until a
person confirms it (``confirmed_by_user_id``) and is never saved under a person's name. Rows are never rewritten:
an edit or a new reading is a new row whose ``replaces_id`` names the one before, so the original stays visible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")


class TheoryNarrative(Base):
    __tablename__ = "theory_narratives"
    __table_args__ = (
        CheckConstraint("origin IN ('person', 'agent')", name="ck_theory_narratives_origin"),
        CheckConstraint("origin = 'person' OR model IS NOT NULL", name="ck_theory_narratives_model_named"),
        Index("ix_theory_narratives_entry", "entry_id", "link_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace_entries.id", ondelete="CASCADE"), nullable=False)
    # The addition it explains; null for the theory's own "how it fits together".
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace_entry_links.id", ondelete="CASCADE"), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    # The person who wrote it, or, for a model reading, the person who asked for it (never its author).
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
                                                      nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # [{"ref": "financial_transaction:<id>", "label": "..."}] for an addition; [{"ref": "link:<id>"}] for a theory.
    citations: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    # How much it read: {"read": 120, "of": 400, "invalid_citations": 0}.
    basis: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    replaces_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theory_narratives.id", ondelete="SET NULL"), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                                                 server_default=func.now(), nullable=False)
