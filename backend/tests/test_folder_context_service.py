import uuid
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from services.folder_context_service import gather_sibling_files


class FolderContextServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(
            self.engine,
            tables=[User.__table__, Case.__table__, EvidenceFile.__table__],
        )
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_root_siblings_are_scoped_to_the_current_case(self):
        user_id = uuid.uuid4()
        case_id = uuid.uuid4()
        other_case_id = uuid.uuid4()
        selected_file_id = uuid.uuid4()

        with self.SessionLocal() as db:
            db.add(
                User(
                    id=user_id,
                    email="investigator@example.com",
                    name="Investigator",
                    password_hash="hash",
                )
            )
            db.add_all(
                [
                    Case(
                        id=case_id,
                        title="Current case",
                        created_by_user_id=user_id,
                        owner_user_id=user_id,
                    ),
                    Case(
                        id=other_case_id,
                        title="Other case",
                        created_by_user_id=user_id,
                        owner_user_id=user_id,
                    ),
                ]
            )
            db.add_all(
                [
                    EvidenceFile(
                        id=selected_file_id,
                        case_id=case_id,
                        original_filename="selected.pdf",
                        stored_path="C:/evidence/selected.pdf",
                        size=10,
                        sha256="a" * 64,
                    ),
                    EvidenceFile(
                        case_id=case_id,
                        original_filename="same-case.pdf",
                        stored_path="C:/evidence/same-case.pdf",
                        size=20,
                        sha256="b" * 64,
                    ),
                    EvidenceFile(
                        case_id=other_case_id,
                        original_filename="other-case.pdf",
                        stored_path="C:/evidence/other-case.pdf",
                        size=30,
                        sha256="c" * 64,
                    ),
                ]
            )
            db.commit()

            siblings = gather_sibling_files(
                db,
                case_id,
                folder_id=None,
                exclude_file_id=selected_file_id,
            )

        self.assertEqual(
            siblings,
            [
                {
                    "name": "same-case.pdf",
                    "mime_type": "application/pdf",
                    "size": 20,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
