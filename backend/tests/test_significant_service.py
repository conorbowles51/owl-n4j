from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.runtime_state import SystemLog
from postgres.models.significant import SignificantEntity
from postgres.models.user import User
from services.significant_service import (
    add_significant_entities,
    get_significant_entity_keys,
    remove_significant_entities,
    restore_significant_entity_after_restore,
    suspend_significant_entity_for_delete,
    transfer_significant_membership_after_merge,
)


TABLES = [
    User.__table__,
    Case.__table__,
    SystemLog.__table__,
    SignificantEntity.__table__,
]


class SignificantServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()
        self.user = User(
            id=uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid4(),
            title="Reference Manifest",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine, tables=list(reversed(TABLES)))
        self.engine.dispose()

    def add(self, *keys: str):
        return add_significant_entities(
            self.db,
            case_id=self.case.id,
            current_user=self.user,
            entity_keys=keys,
            addition_source="manual",
            context={"surface": "test"},
        )

    def test_manifest_stores_only_entity_references_and_is_idempotent(self):
        first = self.add("person-mark", "event-1", "person-mark")
        second = self.add("person-mark")

        self.assertEqual(first["added_count"], 2)
        self.assertEqual(second["added_count"], 0)
        self.assertEqual(second["already_significant_count"], 1)
        self.assertEqual(
            set(get_significant_entity_keys(self.db, case_id=self.case.id)),
            {"person-mark", "event-1"},
        )

        row = self.db.query(SignificantEntity).filter_by(entity_key="person-mark").one()
        self.assertEqual(row.context, {"surface": "test"})
        self.assertFalse(hasattr(row, "name"))
        self.assertFalse(hasattr(row, "summary"))
        self.assertFalse(hasattr(row, "properties"))

    def test_manual_remove_and_readd_reuses_the_manifest_reference(self):
        self.add("person-mark")
        original_id = self.db.query(SignificantEntity).one().id

        removed = remove_significant_entities(
            self.db,
            case_id=self.case.id,
            current_user=self.user,
            entity_keys=["person-mark", "not-significant"],
        )
        self.assertEqual(removed["removed_count"], 1)
        self.assertEqual(removed["not_significant_count"], 1)
        self.assertEqual(get_significant_entity_keys(self.db, case_id=self.case.id), [])

        self.add("person-mark")
        row = self.db.query(SignificantEntity).one()
        self.assertEqual(row.id, original_id)
        self.assertIsNone(row.removed_at)
        self.assertIsNone(row.removal_reason)

    def test_merge_transfers_membership_and_leaves_unrelated_sources_unmarked(self):
        self.add("person-mark")

        changed = transfer_significant_membership_after_merge(
            self.db,
            case_id=self.case.id,
            source_entity_keys=["person-mark", "person-marc"],
            merged_entity_key="person-merged",
        )

        self.assertTrue(changed)
        self.assertEqual(
            get_significant_entity_keys(self.db, case_id=self.case.id),
            ["person-merged"],
        )
        source = self.db.query(SignificantEntity).filter_by(entity_key="person-mark").one()
        target = self.db.query(SignificantEntity).filter_by(entity_key="person-merged").one()
        self.assertEqual(source.removal_reason, "entity_merged")
        self.assertEqual(target.addition_source, "merge")
        self.assertEqual(
            target.context["source_entity_keys"],
            ["person-mark", "person-marc"],
        )

    def test_delete_suspends_membership_and_restore_reactivates_only_deleted_rows(self):
        self.add("person-mark", "event-1")
        suspended = suspend_significant_entity_for_delete(
            self.db,
            case_id=self.case.id,
            entity_key="person-mark",
            current_user=self.user,
        )
        remove_significant_entities(
            self.db,
            case_id=self.case.id,
            current_user=self.user,
            entity_keys=["event-1"],
        )

        self.assertTrue(suspended)
        self.assertTrue(
            restore_significant_entity_after_restore(
                self.db,
                case_id=self.case.id,
                entity_key="person-mark",
            )
        )
        self.assertFalse(
            restore_significant_entity_after_restore(
                self.db,
                case_id=self.case.id,
                entity_key="event-1",
            )
        )
        self.assertEqual(
            get_significant_entity_keys(self.db, case_id=self.case.id),
            ["person-mark"],
        )


if __name__ == "__main__":
    unittest.main()
