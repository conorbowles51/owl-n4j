import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.case_profile import CaseProfile, CaseProfileAttribute
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.runtime_state import SystemLog
from postgres.models.user import User
from services.case_export import available_sections, build_case_export_html, get_sections, render_case_export
from services.system_log_service import LogOrigin, LogType, SystemLogService


CASE_EXPORT_TABLES = [
    User.__table__,
    Case.__table__,
    CaseProfile.__table__,
    CaseProfileAttribute.__table__,
    NotebookNote.__table__,
    NotebookNoteLink.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    SystemLog.__table__,
]


class CaseExportServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=CASE_EXPORT_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        with self.SessionLocal() as db:
            self.user = User(
                email="investigator@example.com",
                name="Investigator",
                password_hash="hash",
                global_role=GlobalRole.user,
                is_active=True,
            )
            db.add(self.user)
            db.flush()
            self.case = Case(
                title="Case Alpha",
                description="Wire transfer investigation.",
                created_by_user_id=self.user.id,
                owner_user_id=self.user.id,
            )
            db.add(self.case)
            db.commit()
            db.refresh(self.user)
            db.refresh(self.case)
            self.user_id = self.user.id
            self.case_id = self.case.id

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=CASE_EXPORT_TABLES)

    def _user(self, db):
        return db.query(User).filter(User.id == self.user_id).one()

    def _case(self, db):
        return db.query(Case).filter(Case.id == self.case_id).one()

    def test_available_sections_exposes_picker_metadata(self):
        sections = available_sections()

        self.assertEqual(
            [section["key"] for section in sections],
            [
                "cover",
                "case_overview",
                "summary",
                "entities",
                "notes",
                "transcriptions",
                "audit_log",
            ],
        )
        self.assertTrue(sections[0]["default_enabled"])
        self.assertIn("description", sections[1])

    def test_get_sections_uses_defaults_and_preserves_registry_order(self):
        default_sections = get_sections(None)
        selected_sections = get_sections(["case_overview", "cover"])

        self.assertEqual(
            [section.key for section in default_sections],
            [
                "cover",
                "case_overview",
                "summary",
                "entities",
                "notes",
                "transcriptions",
                "audit_log",
            ],
        )
        self.assertEqual([section.key for section in selected_sections], ["cover", "case_overview"])

    def test_get_sections_rejects_unknown_picker_keys(self):
        with self.assertRaisesRegex(ValueError, "Unknown"):
            get_sections(["cover", "unknown"])

    def test_html_section_picker_includes_only_selected_sections(self):
        with self.SessionLocal() as db:
            html = build_case_export_html(
                db,
                case=self._case(db),
                current_user=self._user(db),
                section_keys=["case_overview"],
                generated_at=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
            )

        self.assertIn("Case Overview", html)
        self.assertIn("Wire transfer investigation.", html)
        self.assertNotIn("Included Sections", html)

    def test_case_export_renders_pdf_result(self):
        with self.SessionLocal() as db, patch("weasyprint.HTML") as html_class:
            html_class.return_value.write_pdf.return_value = b"%PDF-1.7 skeleton"
            result = render_case_export(
                db,
                case=self._case(db),
                current_user=self._user(db),
                section_keys=["cover"],
            )

        self.assertEqual(result.media_type, "application/pdf")
        self.assertTrue(result.filename.startswith("case-alpha-case-export-"))
        self.assertEqual(result.content, b"%PDF-1.7 skeleton")
        html_class.assert_called_once()
        self.assertIn("Case File Export", html_class.call_args.kwargs["string"])

    def test_content_sections_render_case_data_and_audit_log_scope(self):
        log_service = SystemLogService(session_factory=self.SessionLocal)

        with self.SessionLocal() as db:
            user = self._user(db)
            case = self._case(db)
            profile = CaseProfile(
                case_id=case.id,
                profile_type="person",
                display_name="Alice Rivera",
                summary="Primary account holder.",
                importance="high",
                created_by_user_id=user.id,
                updated_by_user_id=user.id,
            )
            db.add(profile)
            db.flush()
            db.add(
                CaseProfileAttribute(
                    profile_id=profile.id,
                    case_id=case.id,
                    kind="phone",
                    name="Mobile",
                    value="+1 555 0100",
                    normalized_value="+1 555 0100",
                    ordinal=0,
                )
            )
            note = NotebookNote(
                case_id=case.id,
                author_user_id=user.id,
                author_email=user.email,
                author_name=user.name,
                title="Interview follow-up",
                body="Confirm source of funds.",
                tags=["interview"],
                visibility="case",
            )
            db.add(note)
            db.flush()
            db.add(
                NotebookNoteLink(
                    note_id=note.id,
                    case_id=case.id,
                    target_type="entity",
                    target_id=str(profile.id),
                    target_label="Alice Rivera",
                    link_metadata={},
                )
            )
            db.add(
                EvidenceFile(
                    case_id=case.id,
                    original_filename="call-001.wav",
                    stored_path="/tmp/call-001.wav",
                    size=1024,
                    sha256="a" * 64,
                    status="processed",
                    transcription="Caller discusses the transfer.",
                    source_type="audio",
                    created_by_id=user.id,
                )
            )
            db.commit()

            log_service.log(
                LogType.CASE_OPERATION,
                LogOrigin.FRONTEND,
                "Create Notebook Note",
                details={"case_id": str(case.id), "note_id": str(note.id)},
                user=user.email,
                db=db,
            )
            log_service.log(
                LogType.CASE_OPERATION,
                LogOrigin.FRONTEND,
                "Other Case Action",
                details={"case_id": "other-case"},
                user=user.email,
                db=db,
            )

            html = build_case_export_html(
                db,
                case=case,
                current_user=user,
                section_keys=["summary", "entities", "notes", "transcriptions", "audit_log"],
                generated_at=datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc),
            )

        self.assertIn("Primary account holder.", html)
        self.assertIn("+1 555 0100", html)
        self.assertIn("Confirm source of funds.", html)
        self.assertIn("Alice Rivera", html)
        self.assertIn("Caller discusses the transfer.", html)
        self.assertIn("Create Notebook Note", html)
        self.assertNotIn("Other Case Action", html)


if __name__ == "__main__":
    unittest.main()
