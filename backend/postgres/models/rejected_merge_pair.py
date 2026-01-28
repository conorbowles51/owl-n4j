from __future__ import annotations

import uuid
from sqlalchemy import ForeignKey, String, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from postgres.base import Base
from postgres.models.mixins import TimestampMixin


class RejectedMergePair(Base, TimestampMixin):
    """
    Stores pairs of entities that a user has rejected as false positives
    during duplicate entity detection. These pairs will be filtered out
    from future similar-entities scans.

    Keys are stored in sorted order (entity_key_1 < entity_key_2) to prevent
    duplicate entries like (A, B) and (B, A).
    """
    __tablename__ = "rejected_merge_pairs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Entity keys stored in sorted order (key1 < key2 alphabetically)
    entity_key_1: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_key_2: Mapped[str] = mapped_column(String(255), nullable=False)

    rejected_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    case = relationship("Case", foreign_keys=[case_id])
    rejected_by = relationship("User", foreign_keys=[rejected_by_user_id])

    __table_args__ = (
        # Ensure no duplicate pair rejections for the same case
        UniqueConstraint("case_id", "entity_key_1", "entity_key_2", name="uq_rejected_pair"),
        # Index for efficient lookups when filtering similar entities
        Index("ix_rejected_pairs_case_keys", "case_id", "entity_key_1", "entity_key_2"),
    )

    @staticmethod
    def normalize_keys(key1: str, key2: str) -> tuple[str, str]:
        """
        Return keys in sorted order to ensure consistent storage.
        This prevents storing both (A, B) and (B, A) as separate entries.
        """
        if key1 <= key2:
            return key1, key2
        return key2, key1
