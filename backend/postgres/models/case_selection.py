"""A group of case items added to a theory, finding, note or dossier as one link (lx-theorybuild B).

A group keeps what was chosen (every member, by type and id) and how (the surface it came from, the filter, range or
query, and a sentence in the person's words). It is never rewritten: choosing again makes a new group. Members that
were named but are not in the case are not kept; ``left_out`` says how many, so nothing is cut silently. The link
types that point here are ``postgres.link_types.GROUP_TYPES``; the phone build's own groups stay ``phone_selection``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")

# The link type a group is added as, and the surface it was chosen on.
GROUP_SURFACES: dict[str, str] = {
    "graph_selection": "graph",
    "significant_set": "significant",
    "timeline_range": "timeline",
    "financial_selection": "financial",
    "evidence_selection": "evidence",
    "map_selection": "map",
    "step_trail": "history",
}


class CaseSelection(Base):
    __tablename__ = "case_selections"
    __table_args__ = (
        CheckConstraint(
            "group_type IN ('graph_selection', 'significant_set', 'timeline_range', 'financial_selection', "
            "'evidence_selection', 'map_selection', 'step_trail')",
            name="ck_case_selections_group_type",
        ),
        CheckConstraint("member_count >= 0 AND left_out >= 0", name="ck_case_selections_counts"),
        Index("ix_case_selections_case", "case_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    group_type: Mapped[str] = mapped_column(String(32), nullable=False)
    words: Mapped[str] = mapped_column(Text, nullable=False)
    # How it was chosen: {"filter": {...}} / {"range": {"start", "end"}} / {"query": "..."} / {"snapshot": true} ...
    how: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False, default=dict)
    # Every member kept, in the order chosen: [{"type": "graph_entity", "id": "...", "label": "..."}].
    members: Mapped[list] = mapped_column(JSON_DOCUMENT, nullable=False, default=list)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    left_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
