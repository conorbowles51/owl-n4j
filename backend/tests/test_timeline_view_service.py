import csv
import io
import unittest
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.timeline_view import TimelineView, TimelineViewEvent
from postgres.models.user import User
from services import timeline_view_service


TIMELINE_VIEW_TABLES = [
    User.__table__,
    Case.__table__,
    TimelineView.__table__,
    TimelineViewEvent.__table__,
]


def _event(key, date="2024-01-01", time=None):
    return {
        "key": key,
        "name": f"Event {key}",
        "type": "Event",
        "date": date,
        "time": time,
        "amount": None,
        "summary": f"Summary {key}",
        "notes": None,
        "connections": [],
        "source_files": [f"{key}.pdf"],
    }


class TimelineViewServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=TIMELINE_VIEW_TABLES)
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
        Base.metadata.drop_all(self.engine, tables=TIMELINE_VIEW_TABLES)

    def _user(self, db):
        return db.query(User).filter(User.id == self.user_id).one()

    def test_create_view_deduplicates_and_stores_fixed_event_membership(self):
        with self.SessionLocal() as db, patch.object(
            timeline_view_service.neo4j_service,
            "get_timeline_events_by_keys",
            return_value=[_event("a", time="09:00"), _event("b", time=None)],
        ) as get_events, patch.object(timeline_view_service.system_log_service, "log"):
            result = timeline_view_service.create_timeline_view(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                title="Focused",
                event_keys=["a", "b", "a"],
            )

        self.assertEqual(result["event_count"], 2)
        self.assertEqual([item["event_key"] for item in result["events"]], ["a", "b"])
        get_events.assert_called_once()
        self.assertEqual(get_events.call_args.kwargs["event_keys"], ["a", "b"])

    def test_batch_remove_keeps_view_fixed(self):
        with self.SessionLocal() as db, patch.object(
            timeline_view_service.neo4j_service,
            "get_timeline_events_by_keys",
            return_value=[_event("a"), _event("b")],
        ), patch.object(timeline_view_service.system_log_service, "log"):
            created = timeline_view_service.create_timeline_view(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                title="Focused",
                event_keys=["a", "b"],
            )
            updated = timeline_view_service.batch_update_view_events(
                db,
                case_id=self.case_id,
                view_id=UUID(created["id"]),
                current_user=self._user(db),
                action="remove",
                event_keys=["a"],
            )

        self.assertEqual(updated["event_count"], 1)
        self.assertEqual(updated["events"][0]["event_key"], "b")

    def test_selection_export_rejects_missing_event_keys(self):
        with self.SessionLocal() as db, patch.object(
            timeline_view_service.neo4j_service,
            "get_timeline_events_by_keys",
            return_value=[_event("a")],
        ), patch.object(timeline_view_service.system_log_service, "log"):
            with self.assertRaises(ValueError):
                timeline_view_service.export_timeline(
                    db,
                    case_id=self.case_id,
                    case_name="Case Alpha",
                    current_user=self._user(db),
                    export_format="csv",
                    source="selection",
                    event_keys=["a", "missing"],
                )

    def test_pdf_html_includes_source_appendix(self):
        html = timeline_view_service._render_pdf_html(
            events=[_event("a", time="10:00")],
            case_name="Case Alpha",
            title="Focused",
            fields=timeline_view_service._default_fields("standard"),
            detail_level="standard",
            generated_by="Investigator",
            footer_label="Confidential",
            notes_by_event={},
        )

        self.assertIn("Focused", html)
        self.assertRegex(html, r"exp_[0-9a-f]{12}")
        self.assertIn("AI-generated summaries", html)
        self.assertIn("Source citations", html)
        self.assertIn("Source Appendix", html)
        self.assertIn("a.pdf", html)

    def test_selection_csv_includes_export_metadata_and_source_citations(self):
        with self.SessionLocal() as db, patch.object(
            timeline_view_service.neo4j_service,
            "get_timeline_events_by_keys",
            return_value=[_event("a", time="10:00")],
        ), patch.object(timeline_view_service.system_log_service, "log"):
            exported = timeline_view_service.export_timeline(
                db,
                case_id=self.case_id,
                case_name="Case Alpha",
                current_user=self._user(db),
                export_format="csv",
                source="selection",
                event_keys=["a"],
            )

        rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))

        self.assertEqual(rows[0]["Export ID"], exported.export_id)
        self.assertRegex(rows[0]["Export ID"], r"^exp_[0-9a-f]{12}$")
        self.assertIn("Source: Selected events", rows[0]["Filters / Scope"])
        self.assertIn("AI-generated summaries", rows[0]["AI Disclosure"])
        self.assertIn("a.pdf", rows[0]["Source Citations"])

    def test_snapshot_sort_time_falls_back_to_datetime_in_date_field(self):
        self.assertEqual(
            timeline_view_service._event_sort_time(
                _event("a", date="2025-04-12 06:21:47-06:23:45", time=None)
            ),
            "06:21",
        )


if __name__ == "__main__":
    unittest.main()
