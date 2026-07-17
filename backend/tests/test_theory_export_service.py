import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from services import theory_export


class FakeDB:
    def __init__(self):
        self.flushed = False
        self.committed = False

    def flush(self):
        self.flushed = True

    def commit(self):
        self.committed = True


def _user(role="attorney"):
    return SimpleNamespace(
        email="attorney@example.com",
        name="Attorney User",
        global_role=SimpleNamespace(value=role),
    )


class TheoryExportServiceTests(unittest.TestCase):
    def test_html_contains_narrative_scoped_events_and_attached_records(self):
        html = theory_export._render_theory_pdf_html(
            theory={
                "title": "Alternative Suspect",
                "type": "PRIMARY",
                "confidence_score": 72,
                "privilege_level": "PUBLIC",
                "hypothesis": "The payment came from a third party.",
                "supporting_evidence": ["Bank transfer matches third-party account"],
                "counter_arguments": ["Witness recollection is incomplete"],
                "next_steps": ["Interview account holder"],
            },
            case_name="Case Alpha",
            scoped_events=[
                {
                    "date": "2026-01-03T10:00:00",
                    "thread": "Evidence",
                    "type": "evidence_uploaded",
                    "title": "Evidence Uploaded: bank.pdf",
                    "description": "File uploaded: bank.pdf",
                }
            ],
            scoped_evidence={
                "witnesses": [
                    {
                        "name": "Jane Witness",
                        "category": "FRIENDLY",
                        "credibility_rating": 4,
                        "statement_summary": "Saw another person handling the account.",
                    }
                ],
                "notes": [
                    {
                        "title": "Interview prep",
                        "content": "Ask about account access.",
                        "tags": ["finance"],
                    }
                ],
                "evidence": [
                    {
                        "id": "ev-1",
                        "original_filename": "bank.pdf",
                        "created_at": "2026-01-02T09:00:00",
                    }
                ],
                "documents": [
                    {
                        "id": "doc-1",
                        "original_filename": "memo.pdf",
                        "created_at": "2026-01-04T09:00:00",
                    }
                ],
            },
            generated_by="Attorney User",
            generated_at=datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc),
            footer_label="Confidential",
        )

        self.assertIn("Narrative", html)
        self.assertIn("The payment came from a third party.", html)
        self.assertIn("Scoped Events", html)
        self.assertIn("Evidence Uploaded: bank.pdf", html)
        self.assertIn("Scoped Evidence", html)
        self.assertIn("Jane Witness", html)
        self.assertIn("Interview prep", html)
        self.assertIn("memo.pdf", html)

    def test_render_pdf_blocks_attorney_only_theory_for_non_attorney(self):
        case = SimpleNamespace(id=uuid4(), title="Case Alpha")

        with patch.object(
            theory_export.workspace_service,
            "get_theory",
            return_value={"title": "Privileged", "privilege_level": "ATTORNEY_ONLY"},
        ):
            with self.assertRaises(theory_export.TheoryAccessDenied):
                theory_export.render_theory_pdf(
                    FakeDB(),
                    case=case,
                    theory_id="theory_1",
                    current_user=_user(role="user"),
                )

    def test_render_pdf_returns_pdf_export_for_scoped_theory(self):
        case = SimpleNamespace(id=uuid4(), title="Case Alpha")
        db = FakeDB()

        with (
            patch.object(
                theory_export.workspace_service,
                "get_theory",
                return_value={
                    "title": "Alternative Suspect",
                    "privilege_level": "PUBLIC",
                    "hypothesis": "Third-party access.",
                },
            ),
            patch.object(
                theory_export.workspace_service,
                "get_theory_timeline",
                return_value=[{"title": "Theory Created", "date": "2026-01-01"}],
            ),
            patch.object(
                theory_export.workspace_service,
                "get_theory_scoped_evidence",
                return_value={"witnesses": [], "notes": [], "evidence": [], "documents": []},
            ),
            patch.object(theory_export, "_render_pdf", return_value=b"%PDF theory"),
            patch.object(theory_export.system_log_service, "log") as log,
        ):
            exported = theory_export.render_theory_pdf(
                db,
                case=case,
                theory_id="theory_1",
                current_user=_user(),
            )

        self.assertEqual(exported.content, b"%PDF theory")
        self.assertEqual(exported.media_type, "application/pdf")
        self.assertTrue(exported.filename.startswith("Alternative-Suspect-"))
        self.assertTrue(db.flushed)
        self.assertTrue(db.committed)
        log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
