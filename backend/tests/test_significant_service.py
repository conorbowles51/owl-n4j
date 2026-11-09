from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.runtime_state import SystemLog
from postgres.models.significant import SignificantEntity, SignificantRelationship
from postgres.models.user import User
from services.significant_service import (
    add_significant_entities,
    add_significant_relationships,
    list_significant_entities,
    remove_significant_relationships,
    transfer_significant_relationships_after_merge,
    get_significant_entity_keys,
    get_significant_layer_keys,
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
    SignificantRelationship.__table__,
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



    # ---- relationships (GR-01) ----------------------------------------------------------------------------------
    def rel(self, s, y, t):
        return {"source_key": s, "type": y, "target_key": t}

    def test_a_relationship_mark_is_stored_with_who_and_survives_a_fresh_read(self):
        result = add_significant_relationships(
            self.db, case_id=self.case.id, current_user=self.user,
            relationships=[self.rel("p1", "DIRECTOR_OF", "c1"), self.rel("p1", "DIRECTOR_OF", "c1")],
            addition_source="manual", context={"surface": "graph"})
        self.assertEqual(result["added_relationship_count"], 1)
        case_id = self.case.id
        self.db.close()
        self.db = self.SessionLocal()  # a reload: nothing carried in the session
        rels = list_significant_entities(self.db, case_id=case_id)["relationships"]
        self.assertEqual([(r["source_key"], r["type"], r["target_key"]) for r in rels], [("p1", "DIRECTOR_OF", "c1")])
        self.assertEqual((rels[0]["added_by_name"], rels[0]["addition_source"]), ("Investigator", "manual"))
        self.assertIsNotNone(rels[0]["created_at"])
        # entity marks are unaffected
        self.assertEqual(list_significant_entities(self.db, case_id=case_id)["entity_keys"], [])

    def test_unmarking_a_relationship_keeps_the_row_with_who_removed_it(self):
        add_significant_relationships(self.db, case_id=self.case.id, current_user=self.user,
                                      relationships=[self.rel("p1", "OWNS", "c1")], addition_source="manual")
        out = remove_significant_relationships(self.db, case_id=self.case.id, current_user=self.user,
                                               relationships=[self.rel("p1", "OWNS", "c1"), self.rel("x", "Y", "z")])
        self.assertEqual((out["removed_relationship_count"], out["not_significant_relationship_count"]), (1, 1))
        self.assertEqual(out["relationships"], [])
        row = self.db.query(SignificantRelationship).one()
        self.assertEqual((row.removal_reason, row.removed_by_user_id), ("manual", self.user.id))
        again = add_significant_relationships(self.db, case_id=self.case.id, current_user=self.user,
                                              relationships=[self.rel("p1", "OWNS", "c1")], addition_source="manual")
        self.assertEqual(len(again["relationships"]), 1)
        self.assertEqual(self.db.query(SignificantRelationship).count(), 1)

    def test_a_merge_carries_relationship_marks_to_the_merged_entity(self):
        add_significant_relationships(self.db, case_id=self.case.id, current_user=self.user,
                                      relationships=[self.rel("a", "PAID", "x"), self.rel("x", "KNOWS", "b"),
                                                     self.rel("y", "KNOWS", "z")], addition_source="manual")
        moved = transfer_significant_relationships_after_merge(self.db, case_id=self.case.id,
                                                               source_entity_keys=["a", "b"], merged_entity_key="m")
        self.assertEqual(moved, 2)
        rels = list_significant_entities(self.db, case_id=self.case.id)["relationships"]
        self.assertEqual(sorted((r["source_key"], r["type"], r["target_key"]) for r in rels),
                         [("m", "PAID", "x"), ("x", "KNOWS", "m"), ("y", "KNOWS", "z")])
        carried = [r for r in rels if r["source_key"] == "m"][0]
        self.assertEqual(carried["context"]["merged_from"], ["a", "PAID", "x"])
        old = self.db.query(SignificantRelationship).filter_by(source_key="a").one()
        self.assertEqual(old.removal_reason, "entity_merged")

    def test_the_layer_shows_both_ends_of_a_marked_relationship(self):
        self.add("p1")
        add_significant_relationships(self.db, case_id=self.case.id, current_user=self.user,
                                      relationships=[self.rel("p1", "OWNS", "c1"), self.rel("x", "PAID", "y")],
                                      addition_source="manual")
        self.assertEqual(get_significant_layer_keys(self.db, case_id=self.case.id), ["p1", "c1", "x", "y"])
        self.assertEqual(get_significant_entity_keys(self.db, case_id=self.case.id), ["p1"])

    def test_a_relationship_needs_both_ends_and_a_type(self):
        with self.assertRaises(ValueError):
            add_significant_relationships(self.db, case_id=self.case.id, current_user=self.user,
                                          relationships=[self.rel("p1", "", "c1")], addition_source="manual")


class RelationshipLookupTests(unittest.TestCase):
    def test_the_graph_lookup_matches_both_ends_and_the_relationship_with_the_case_id(self):
        from unittest import mock
        import importlib
        gs = importlib.import_module("services.neo4j.graph_service")

        seen = {}

        class _Session:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def run(self, query, **params):
                seen["query"], seen["params"] = query, params
                return [{"s": "p1", "y": "OWNS", "t": "c1"}]

        with mock.patch.object(gs, "driver") as driver:
            driver.session.return_value = _Session()
            found = gs.GraphService().get_existing_relationships(
                "case-1", [{"source_key": "p1", "type": "OWNS", "target_key": "c1"},
                           {"source_key": "p1", "type": "OWNS", "target_key": "gone"}])
        self.assertEqual(found, [{"source_key": "p1", "type": "OWNS", "target_key": "c1"}])
        q = seen["query"]
        self.assertIn("a.case_id = $case_id", q)
        self.assertIn("b.case_id = $case_id", q)
        self.assertIn("r.case_id = $case_id", q)
        self.assertEqual(seen["params"]["case_id"], "case-1")

if __name__ == "__main__":
    unittest.main()
