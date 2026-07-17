import unittest
import uuid
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.workspace import WorkspaceNote, WorkspaceTheory, WorkspaceWitness
import services.workspace_service as workspace_service_module


WORKSPACE_TABLES = [
    User.__table__,
    Case.__table__,
    WorkspaceWitness.__table__,
    WorkspaceTheory.__table__,
    WorkspaceNote.__table__,
]


class WorkspaceServiceConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=WORKSPACE_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.original_get_background_session = workspace_service_module.get_background_session
        workspace_service_module.get_background_session = self.get_background_session
        self.service = workspace_service_module.WorkspaceService()

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        with self.SessionLocal() as db:
            db.add(
                User(
                    id=self.user_id,
                    email="investigator@example.com",
                    name="Investigator",
                    password_hash="hash",
                )
            )
            db.add(
                Case(
                    id=self.case_id,
                    title="Case",
                    created_by_user_id=self.user_id,
                    owner_user_id=self.user_id,
                )
            )
            db.commit()

    def tearDown(self):
        workspace_service_module.get_background_session = self.original_get_background_session
        Base.metadata.drop_all(self.engine, tables=WORKSPACE_TABLES)
        self.engine.dispose()

    @contextmanager
    def get_background_session(self):
        db = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def test_versioned_workspace_entities_reject_stale_updates_and_deletes(self):
        cases = [
            {
                "name": "note",
                "create": {"title": "Initial note", "content": "First draft"},
                "update": {"content": "Accepted edit"},
                "stale": {"content": "Stale edit"},
                "save": self.service.save_note,
                "get": self.service.get_note,
                "delete": self.service.delete_note,
                "id_field": "note_id",
                "check_field": "content",
            },
            {
                "name": "theory",
                "create": {
                    "title": "Initial theory",
                    "type": "PRIMARY",
                    "hypothesis": "First draft",
                    "privilege_level": "PUBLIC",
                },
                "update": {"hypothesis": "Accepted edit"},
                "stale": {"hypothesis": "Stale edit"},
                "save": self.service.save_theory,
                "get": self.service.get_theory,
                "delete": self.service.delete_theory,
                "id_field": "theory_id",
                "check_field": "hypothesis",
            },
            {
                "name": "witness",
                "create": {
                    "name": "Initial witness",
                    "category": "NEUTRAL",
                    "statement_summary": "First draft",
                },
                "update": {"statement_summary": "Accepted edit"},
                "stale": {"statement_summary": "Stale edit"},
                "save": self.service.save_witness,
                "get": self.service.get_witness,
                "delete": self.service.delete_witness,
                "id_field": "witness_id",
                "check_field": "statement_summary",
            },
        ]

        for entity in cases:
            with self.subTest(entity=entity["name"]):
                entity_id = entity["save"](str(self.case_id), dict(entity["create"]))
                created = entity["get"](str(self.case_id), entity_id)

                self.assertEqual(created["version"], 1)

                accepted = {**created, **entity["update"]}
                entity["save"](
                    str(self.case_id),
                    accepted,
                    expected_version=created["version"],
                )
                current = entity["get"](str(self.case_id), entity_id)

                self.assertEqual(current["version"], 2)
                self.assertEqual(current[entity["check_field"]], "Accepted edit")

                stale = {**created, **entity["stale"], entity["id_field"]: entity_id}
                with self.assertRaises(
                    workspace_service_module.WorkspaceVersionConflict
                ) as conflict:
                    entity["save"](
                        str(self.case_id),
                        stale,
                        expected_version=created["version"],
                    )

                self.assertEqual(conflict.exception.entity, entity["name"])
                self.assertEqual(conflict.exception.current_version, 2)
                preserved = entity["get"](str(self.case_id), entity_id)
                self.assertEqual(preserved[entity["check_field"]], "Accepted edit")
                self.assertEqual(preserved["version"], 2)

                with self.assertRaises(workspace_service_module.WorkspaceVersionConflict):
                    entity["delete"](
                        str(self.case_id),
                        entity_id,
                        expected_version=created["version"],
                    )

                self.assertIsNotNone(entity["get"](str(self.case_id), entity_id))
                self.assertTrue(
                    entity["delete"](
                        str(self.case_id),
                        entity_id,
                        expected_version=preserved["version"],
                    )
                )
                self.assertIsNone(entity["get"](str(self.case_id), entity_id))


if __name__ == "__main__":
    unittest.main()
