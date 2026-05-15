import uuid
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from services.evidence_db_storage import EvidenceDBStorage


EVIDENCE_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    IngestionLog.__table__,
]


class CellebriteEvidenceDBStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=EVIDENCE_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        with self.SessionLocal() as db:
            db.add(User(
                id=self.user_id,
                email="investigator@example.com",
                name="Investigator",
                password_hash="hash",
            ))
            db.add(Case(
                id=self.case_id,
                title="Case",
                created_by_user_id=self.user_id,
                owner_user_id=self.user_id,
            ))
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=EVIDENCE_TABLES)
        self.engine.dispose()

    def test_add_resolve_list_and_delete_cellebrite_files(self):
        with self.SessionLocal() as db:
            created = EvidenceDBStorage.add_cellebrite_files(
                db,
                case_id=self.case_id,
                owner="investigator@example.com",
                files_data=[
                    {
                        "original_filename": "photo.jpg",
                        "stored_path": "C:/exports/files/Image/photo.jpg",
                        "size": 123,
                        "sha256": "a" * 64,
                        "cellebrite_report_key": "cellebrite-case-e1",
                        "cellebrite_file_id": "file-1",
                        "cellebrite_model_id": "model-1",
                        "cellebrite_category": "Image",
                    },
                    {
                        "original_filename": "voice.ogg",
                        "stored_path": "C:/exports/files/Audio/voice.ogg",
                        "size": 456,
                        "sha256": "b" * 64,
                        "cellebrite_report_key": "cellebrite-case-e1",
                        "cellebrite_file_id": "file-2",
                        "cellebrite_model_id": "model-2",
                        "cellebrite_category": "Audio",
                    },
                ],
            )
            db.commit()

            self.assertEqual(len(created), 2)
            resolved = EvidenceDBStorage.get_by_cellebrite_file_ids(
                db,
                self.case_id,
                ["file-1", "missing"],
            )
            self.assertEqual(set(resolved), {"file-1"})
            self.assertEqual(resolved["file-1"]["source_type"], "cellebrite")
            self.assertEqual(resolved["file-1"]["cellebrite_model_id"], "model-1")

            listed = EvidenceDBStorage.list_cellebrite_files(
                db,
                self.case_id,
                report_keys=["cellebrite-case-e1"],
            )
            self.assertEqual([row["cellebrite_file_id"] for row in listed], ["file-1", "file-2"])

            deleted = EvidenceDBStorage.delete_by_cellebrite_report_key(
                db,
                self.case_id,
                "cellebrite-case-e1",
            )
            db.commit()

            self.assertEqual(deleted, 2)
            self.assertEqual(EvidenceDBStorage.list_cellebrite_files(db, self.case_id), [])

    def test_tags_relevance_and_entity_links_are_postgres_backed(self):
        with self.SessionLocal() as db:
            file_row = EvidenceDBStorage.add_cellebrite_files(
                db,
                case_id=self.case_id,
                owner="investigator@example.com",
                files_data=[
                    {
                        "original_filename": "message.html",
                        "stored_path": "C:/exports/files/Text/message.html",
                        "size": 12,
                        "sha256": "c" * 64,
                        "cellebrite_report_key": "cellebrite-case-e2",
                        "cellebrite_file_id": "file-3",
                        "cellebrite_model_id": "model-3",
                        "cellebrite_category": "Text",
                    },
                ],
            )[0]

            self.assertEqual(EvidenceDBStorage.add_tags(db, [file_row.id], ["priority", "chat"]), 1)
            self.assertEqual(EvidenceDBStorage.remove_tags(db, [file_row.id], ["chat"]), 1)
            self.assertTrue(EvidenceDBStorage.set_tags(db, file_row.id, ["priority", "reviewed"]))
            self.assertEqual(
                EvidenceDBStorage.get_tag_counts(db, self.case_id),
                [{"tag": "priority", "count": 1}, {"tag": "reviewed", "count": 1}],
            )

            self.assertEqual(EvidenceDBStorage.link_entities(db, [file_row.id], ["person-1"]), 1)
            linked = EvidenceDBStorage.list_by_entity(db, self.case_id, "person-1")
            self.assertEqual([row["id"] for row in linked], [str(file_row.id)])

            self.assertEqual(EvidenceDBStorage.unlink_entities_from_all(db, self.case_id, "person-1"), 1)
            self.assertEqual(EvidenceDBStorage.list_by_entity(db, self.case_id, "person-1"), [])


if __name__ == "__main__":
    unittest.main()
