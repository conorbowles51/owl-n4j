import uuid
import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ENGINE_ROOT = PROJECT_ROOT / "evidence-engine"
if str(EVIDENCE_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_ENGINE_ROOT))

from app.pipeline.cellebrite.file_linker import CellebriteFileLinker
from app.pipeline.cellebrite.models import TaggedFile
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

    def test_file_linker_registers_media_under_cellebrite_export_folders(self):
        with TemporaryDirectory() as tmp, self.SessionLocal() as db:
            report_dir = Path(tmp) / "PhoneReport"
            image_dir = report_dir / "files" / "Image"
            image_dir.mkdir(parents=True)
            image_path = image_dir / "photo.jpg"
            image_path.write_bytes(b"photo-bytes")

            report_folder = EvidenceDBStorage.get_or_create_folder_path(
                db,
                self.case_id,
                "PhoneReport",
                created_by_id=self.user_id,
            )

            linker = CellebriteFileLinker(
                report_dir=report_dir,
                tagged_files=[
                    TaggedFile(
                        file_id="file-1",
                        local_path="files\\Image\\photo.jpg",
                        size=image_path.stat().st_size,
                    )
                ],
                case_id=str(self.case_id),
                report_key="cellebrite-case-e3",
            )

            created_count = linker.register_media_files(
                db,
                owner="investigator@example.com",
                evidence_root_folder_id=report_folder.id,
                created_by_id=self.user_id,
            )
            db.commit()

            self.assertEqual(created_count, 1)
            files_folder = db.query(EvidenceFolder).filter_by(name="files").one()
            image_folder = db.query(EvidenceFolder).filter_by(name="Image").one()
            file_row = db.query(EvidenceFile).one()

            self.assertEqual(files_folder.parent_id, report_folder.id)
            self.assertEqual(image_folder.parent_id, files_folder.id)
            self.assertEqual(file_row.folder_id, image_folder.id)
            self.assertEqual(file_row.source_type, "cellebrite")

    def test_list_contents_paginates_and_filters_files_server_side(self):
        with self.SessionLocal() as db:
            image_folder = EvidenceDBStorage.get_or_create_folder_path(
                db,
                self.case_id,
                "PhoneReport/files/Image",
                created_by_id=self.user_id,
            )
            EvidenceDBStorage.add_cellebrite_files(
                db,
                case_id=self.case_id,
                owner="investigator@example.com",
                folder_id=image_folder.id,
                files_data=[
                    {
                        "original_filename": "apple.jpg",
                        "stored_path": "C:/exports/files/Image/apple.jpg",
                        "size": 100,
                        "sha256": "d" * 64,
                        "cellebrite_report_key": "cellebrite-case-e4",
                        "cellebrite_file_id": "file-4",
                    },
                    {
                        "original_filename": "banana.jpg",
                        "stored_path": "C:/exports/files/Image/banana.jpg",
                        "size": 100,
                        "sha256": "e" * 64,
                        "cellebrite_report_key": "cellebrite-case-e4",
                        "cellebrite_file_id": "file-5",
                    },
                    {
                        "original_filename": "clip.mp4",
                        "stored_path": "C:/exports/files/Image/clip.mp4",
                        "size": 100,
                        "sha256": "f" * 64,
                        "cellebrite_report_key": "cellebrite-case-e4",
                        "cellebrite_file_id": "file-6",
                    },
                    {
                        "original_filename": "note.txt",
                        "stored_path": "C:/exports/files/Image/note.txt",
                        "size": 100,
                        "sha256": "0" * 64,
                        "cellebrite_report_key": "cellebrite-case-e4",
                        "cellebrite_file_id": "file-7",
                    },
                ],
            )
            db.commit()

            page = EvidenceDBStorage.list_contents(
                db,
                self.case_id,
                image_folder.id,
                limit=2,
                offset=1,
            )
            image_page = EvidenceDBStorage.list_contents(
                db,
                self.case_id,
                image_folder.id,
                type_category="Image",
            )
            clip_search = EvidenceDBStorage.list_contents(
                db,
                self.case_id,
                image_folder.id,
                search="clip",
            )

            self.assertEqual(page["file_total"], 4)
            self.assertEqual(page["file_limit"], 2)
            self.assertEqual(page["file_offset"], 1)
            self.assertEqual(
                [row["original_filename"] for row in page["files"]],
                ["banana.jpg", "clip.mp4"],
            )
            self.assertEqual(image_page["file_total"], 2)
            self.assertEqual(
                [row["original_filename"] for row in image_page["files"]],
                ["apple.jpg", "banana.jpg"],
            )
            self.assertEqual(clip_search["file_total"], 1)
            self.assertEqual(clip_search["files"][0]["original_filename"], "clip.mp4")


if __name__ == "__main__":
    unittest.main()
