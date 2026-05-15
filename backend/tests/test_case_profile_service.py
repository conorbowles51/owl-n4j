import uuid
import unittest
import importlib.util
import sys
import types
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_profile import (
    CaseProfile,
    CaseProfileAttribute,
    CaseProfileEvidenceLink,
    CaseProfileFindingLink,
    CaseProfileGraphNodeLink,
    CaseProfileNoteLink,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding, WorkspaceNote


def _load_case_profile_service():
    """Load the service with permission checks stubbed to avoid heavy services package imports."""
    services_pkg = types.ModuleType("services")
    services_pkg.__path__ = []
    case_service = types.ModuleType("services.case_service")

    class CaseAccessDenied(Exception):
        pass

    class CaseNotFound(Exception):
        pass

    def check_case_access(db, case_id, user, required_permission=None):
        return None, None

    def get_case_if_allowed(db, case_id, user):
        return None

    case_service.CaseAccessDenied = CaseAccessDenied
    case_service.CaseNotFound = CaseNotFound
    case_service.check_case_access = check_case_access
    case_service.get_case_if_allowed = get_case_if_allowed
    sys.modules.setdefault("services", services_pkg)
    sys.modules["services.case_service"] = case_service

    path = Path(__file__).resolve().parents[1] / "services" / "case_profile_service.py"
    spec = importlib.util.spec_from_file_location("case_profile_service_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["case_profile_service_under_test"] = module
    spec.loader.exec_module(module)
    return module


case_profile_service = _load_case_profile_service()
create_case_profile = case_profile_service.create_case_profile
get_case_profile_context = case_profile_service.get_case_profile_context
list_case_profiles = case_profile_service.list_case_profiles
update_case_profile = case_profile_service.update_case_profile


CASE_PROFILE_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFile.__table__,
    WorkspaceNote.__table__,
    WorkspaceFinding.__table__,
    CaseProfile.__table__,
    CaseProfileAttribute.__table__,
    CaseProfileGraphNodeLink.__table__,
    CaseProfileEvidenceLink.__table__,
    CaseProfileNoteLink.__table__,
    CaseProfileFindingLink.__table__,
]


class CaseProfileServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=CASE_PROFILE_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        self.evidence_id = uuid.uuid4()
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
            db.add(
                EvidenceFile(
                    id=self.evidence_id,
                    case_id=self.case_id,
                    original_filename="report.pdf",
                    stored_path="C:/evidence/report.pdf",
                    size=100,
                    sha256="a" * 64,
                    status="processed",
                )
            )
            db.add(
                WorkspaceNote(
                    case_id=self.case_id,
                    note_id="note_123",
                    data={"title": "Witness note", "content": "Interview notes"},
                )
            )
            db.add(
                WorkspaceFinding(
                    case_id=self.case_id,
                    finding_id="finding_456",
                    data={"title": "Key finding", "content": "Profile relevant finding"},
                )
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=CASE_PROFILE_TABLES)
        self.engine.dispose()

    def test_create_update_and_search_profile(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            created = create_case_profile(
                db,
                case_id=self.case_id,
                user=user,
                data={
                    "profile_type": "person",
                    "display_name": "Elena Petrova",
                    "summary": "Bookkeeper and narrative witness.",
                    "aliases": ["E. Petrova"],
                    "tags": ["witness"],
                    "attributes": [{"kind": "email", "value": "elena@example.test"}],
                    "graph_node_links": [{"node_key": "person-elena", "node_name": "Elena Petrova"}],
                    "evidence_links": [{"evidence_file_id": str(self.evidence_id), "page": 4}],
                    "note_links": [{"note_id": "note_123"}],
                    "finding_links": [{"finding_id": "finding_456"}],
                },
            )

            self.assertEqual(created["profile_type"], "person")
            self.assertEqual(created["aliases"], ["E. Petrova"])
            self.assertEqual(created["tags"], ["witness"])
            self.assertEqual(created["attributes"][2]["kind"], "email")
            self.assertEqual(created["evidence_links"][0]["evidence"]["original_filename"], "report.pdf")

            updated = update_case_profile(
                db,
                profile_id=uuid.UUID(created["id"]),
                user=user,
                data={"aliases": ["Petrova"]},
            )

            self.assertEqual(updated["aliases"], ["Petrova"])
            self.assertEqual(updated["tags"], ["witness"])
            self.assertEqual(
                [attr for attr in updated["attributes"] if attr["kind"] == "email"][0]["value"],
                "elena@example.test",
            )

            searched = list_case_profiles(db, case_id=self.case_id, user=user, query="petrova")
            self.assertEqual(searched["total"], 1)
            linked = list_case_profiles(
                db,
                case_id=self.case_id,
                user=user,
                linked_evidence_file_id=self.evidence_id,
            )
            self.assertEqual(linked["total"], 1)

    def test_context_uses_relational_links(self):
        with self.SessionLocal() as db:
            user = db.get(User, self.user_id)
            created = create_case_profile(
                db,
                case_id=self.case_id,
                user=user,
                data={
                    "profile_type": "other",
                    "display_name": "Silver Bridge Club",
                    "evidence_links": [{"evidence_file_id": str(self.evidence_id)}],
                },
            )

            context = get_case_profile_context(db, profile_id=uuid.UUID(created["id"]), user=user)

            self.assertEqual(context["profile"]["display_name"], "Silver Bridge Club")
            self.assertEqual(context["evidence_links"][0]["evidence"]["id"], str(self.evidence_id))
            self.assertEqual(context["notes"], [])
            self.assertEqual(context["findings"], [])


if __name__ == "__main__":
    unittest.main()
