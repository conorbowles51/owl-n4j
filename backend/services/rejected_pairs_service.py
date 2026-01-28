"""
Service for managing rejected merge pairs (false positives in duplicate detection).
"""

from typing import List, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from postgres.models.rejected_merge_pair import RejectedMergePair


class RejectedPairsService:
    """Service for managing rejected entity merge pairs."""

    def __init__(self, db: Session):
        self.db = db

    def reject_pair(
        self,
        case_id: UUID,
        key1: str,
        key2: str,
        user_id: UUID | None = None,
    ) -> RejectedMergePair:
        """
        Record a pair of entities as a false positive (rejected merge).

        Args:
            case_id: The case ID the entities belong to
            key1: First entity key
            key2: Second entity key
            user_id: ID of the user rejecting the pair

        Returns:
            The created RejectedMergePair record
        """
        # Normalize keys to ensure consistent storage order
        entity_key_1, entity_key_2 = RejectedMergePair.normalize_keys(key1, key2)

        # Check if already rejected
        existing = self.db.query(RejectedMergePair).filter(
            RejectedMergePair.case_id == case_id,
            RejectedMergePair.entity_key_1 == entity_key_1,
            RejectedMergePair.entity_key_2 == entity_key_2,
        ).first()

        if existing:
            return existing

        rejection = RejectedMergePair(
            case_id=case_id,
            entity_key_1=entity_key_1,
            entity_key_2=entity_key_2,
            rejected_by_user_id=user_id,
        )

        self.db.add(rejection)
        self.db.commit()
        self.db.refresh(rejection)

        return rejection

    def get_rejected_pairs(self, case_id: UUID) -> List[RejectedMergePair]:
        """
        Get all rejected pairs for a case.

        Args:
            case_id: The case ID to get rejections for

        Returns:
            List of RejectedMergePair records
        """
        return (
            self.db.query(RejectedMergePair)
            .filter(RejectedMergePair.case_id == case_id)
            .order_by(RejectedMergePair.created_at.desc())
            .all()
        )

    def get_rejected_pairs_set(self, case_id: UUID) -> Set[Tuple[str, str]]:
        """
        Get all rejected pairs as a set of tuples for efficient lookup.

        This is used by the similar entities scan to filter out rejected pairs.

        Args:
            case_id: The case ID to get rejections for

        Returns:
            Set of (entity_key_1, entity_key_2) tuples (already normalized/sorted)
        """
        pairs = self.db.query(
            RejectedMergePair.entity_key_1,
            RejectedMergePair.entity_key_2,
        ).filter(
            RejectedMergePair.case_id == case_id
        ).all()

        return {(p.entity_key_1, p.entity_key_2) for p in pairs}

    def is_rejected(self, case_id: UUID, key1: str, key2: str) -> bool:
        """
        Check if a pair has been rejected.

        Args:
            case_id: The case ID
            key1: First entity key
            key2: Second entity key

        Returns:
            True if the pair has been rejected, False otherwise
        """
        entity_key_1, entity_key_2 = RejectedMergePair.normalize_keys(key1, key2)

        return self.db.query(RejectedMergePair).filter(
            RejectedMergePair.case_id == case_id,
            RejectedMergePair.entity_key_1 == entity_key_1,
            RejectedMergePair.entity_key_2 == entity_key_2,
        ).first() is not None

    def undo_rejection(self, rejection_id: UUID, user_id: UUID | None = None) -> bool:
        """
        Remove a rejection record (undo a false positive marking).

        Args:
            rejection_id: The ID of the rejection record to remove
            user_id: Optional user ID for audit purposes (not currently used)

        Returns:
            True if the rejection was removed, False if not found
        """
        rejection = self.db.query(RejectedMergePair).filter(
            RejectedMergePair.id == rejection_id
        ).first()

        if not rejection:
            return False

        self.db.delete(rejection)
        self.db.commit()

        return True

    def undo_rejection_by_keys(
        self,
        case_id: UUID,
        key1: str,
        key2: str,
    ) -> bool:
        """
        Remove a rejection by entity keys.

        Args:
            case_id: The case ID
            key1: First entity key
            key2: Second entity key

        Returns:
            True if the rejection was removed, False if not found
        """
        entity_key_1, entity_key_2 = RejectedMergePair.normalize_keys(key1, key2)

        rejection = self.db.query(RejectedMergePair).filter(
            RejectedMergePair.case_id == case_id,
            RejectedMergePair.entity_key_1 == entity_key_1,
            RejectedMergePair.entity_key_2 == entity_key_2,
        ).first()

        if not rejection:
            return False

        self.db.delete(rejection)
        self.db.commit()

        return True
