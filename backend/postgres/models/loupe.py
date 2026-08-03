"""Loupe models — bonded collections of evidence.

A Loupe binds documents, passages, entities, events, transactions, calls and
locations together to explain one thing.  Following the SignificantEntity
pattern, these tables hold only the curation manifest: the descriptive data
stays in Neo4j and ``evidence_claims`` so edits to the canonical object are
reflected in every Loupe that references it immediately.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


JSON_DOCUMENT = JSONB().with_variant(JSON(), "sqlite")

#: What a member points at.  ``loupe`` is how Loupes nest.
MEMBER_TYPES = (
    "entity",
    "event",
    "claim",
    "document",
    "passage",
    "transaction",
    "call",
    "location",
    "loupe",
)

#: How one Loupe relates to another.
LINK_RELATIONS = (
    "supports",
    "contradicts",
    "refines",
    "precedes",
    "duplicates",
    "depends_on",
)


class Loupe(Base, TimestampMixin):
    """A bonded collection."""

    __tablename__ = "loupes"
    __table_args__ = (
        Index("ix_loupes_case_updated", "case_id", "updated_at"),
        Index("ix_loupes_case_active", "case_id", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Why these members belong together.  On a Loupe of kind ``theory`` this
    #: holds the hypothesis.
    significance: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: What the collection is for — it changes presentation, never mechanics.
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="finding", server_default="finding"
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default="case", server_default="case"
    )

    #: Set when the Loupe was seeded from a filtered view, so the origin of the
    #: selection survives.  Membership remains explicit either way.
    filter_snapshot: Mapped[dict] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class LoupeMember(Base, TimestampMixin):
    """One bound item.  ``member_ref`` is a Neo4j key, a claim id or a Loupe id."""

    __tablename__ = "loupe_members"
    __table_args__ = (
        UniqueConstraint(
            "loupe_id", "member_type", "member_ref", name="uq_loupe_members_ref"
        ),
        Index("ix_loupe_members_loupe_active", "loupe_id", "removed_at"),
        Index("ix_loupe_members_ref", "member_type", "member_ref"),
        CheckConstraint(
            "member_type IN ('entity','event','claim','document','passage',"
            "'transaction','call','location','loupe')",
            name="ck_loupe_members_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loupe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loupes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    member_type: Mapped[str] = mapped_column(String(32), nullable=False)
    member_ref: Mapped[str] = mapped_column(String(512), nullable=False)

    #: Order within the Loupe.  Timeline-built Loupes default to chronological.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    #: Why *this* member belongs — the within-Loupe narrative at member level.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Surface-specific context: the source device for a Cellebrite member, the
    #: agent's reason for a proposed one.
    context: Mapped[dict] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )

    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    addition_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="manual", server_default="manual"
    )

    #: Agent-proposed members are provisional until a human accepts them.
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoupeLink(Base, TimestampMixin):
    """A typed relationship between two Loupes."""

    __tablename__ = "loupe_links"
    __table_args__ = (
        UniqueConstraint(
            "from_loupe_id", "to_loupe_id", "relation", name="uq_loupe_links_edge"
        ),
        Index("ix_loupe_links_from", "from_loupe_id", "removed_at"),
        Index("ix_loupe_links_to", "to_loupe_id", "removed_at"),
        CheckConstraint("from_loupe_id <> to_loupe_id", name="ck_loupe_links_no_self"),
        CheckConstraint(
            "relation IN ('supports','contradicts','refines','precedes',"
            "'duplicates','depends_on')",
            name="ck_loupe_links_relation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_loupe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loupes.id", ondelete="CASCADE"), nullable=False
    )
    to_loupe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loupes.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)

    #: Why the relationship holds.  A contradicts link without a rationale is
    #: an assertion; with one it is a finding.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoupeRevision(Base, TimestampMixin):
    """Who changed what, and when.  A Loupe may end up in front of a court."""

    __tablename__ = "loupe_revisions"
    __table_args__ = (Index("ix_loupe_revisions_loupe_created", "loupe_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loupe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loupes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    #: The change itself — fields before/after, or the members touched.
    detail: Mapped[dict] = mapped_column(
        JSON_DOCUMENT, nullable=False, default=dict, server_default="{}"
    )
