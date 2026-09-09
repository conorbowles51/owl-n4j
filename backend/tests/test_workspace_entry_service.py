import unittest
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
    WorkspaceLegacyMapping,
)
from services.workspace_entry_service import (
    WorkspaceEntryConflict,
    WorkspaceEntryValidationError,
    add_entry_link,
    change_confidence,
    change_lifecycle,
    convert_theory_to_finding,
    create_entry,
    get_entry,
    search_attachment_options,
    restore_entry,
    soft_delete_entry,
    update_entry,
    update_entry_link,
)


ENTRY_TABLES = [
    CaseProfile.__table__,
    User.__table__,
    Case.__table__,
    EvidenceFile.__table__,
    CaseDeadline.__table__,
    CaseTask.__table__,
    WorkspaceEntry.__table__,
    WorkspaceEntryRevision.__table__,
    WorkspaceEntryLink.__table__,
    WorkspaceEntryEvent.__table__,
    WorkspaceLegacyMapping.__table__,
]


class WorkspaceEntryServiceTests(unittest.TestCase):
    def test_dossier_search_and_linking_are_case_scoped(self):
        from datetime import datetime, timezone
        dossier_id, foreign_id, archived_id = uuid4(), uuid4(), uuid4()
        with self.SessionLocal() as db:
            db.add_all([
                CaseProfile(id=dossier_id, case_id=self.case_id, profile_type="person", display_name="Marcus Chen", summary="Procurement manager"),
                CaseProfile(id=foreign_id, case_id=self.other_case_id, profile_type="person", display_name="Marcus elsewhere"),
                CaseProfile(id=archived_id, case_id=self.case_id, profile_type="person", display_name="Marcus archived", archived_at=datetime.now(timezone.utc)),
            ])
            db.commit()
            results = search_attachment_options(db, case_id=self.case_id, target_type="dossier", query_text="Marcus")
            self.assertEqual([item["target_id"] for item in results], [str(dossier_id)])
            self.assertEqual(results[0]["label"], "Marcus Chen")
            self.assertEqual(search_attachment_options(db, case_id=self.case_id, target_type="dossier", query_text="missing"), [])
            self.assertEqual(search_attachment_options(db, case_id=self.case_id, target_type="dossier", target_ids=[str(foreign_id)]), [])
            note = create_entry(db, case_id=self.case_id, current_user=self._user(db), entry_type="note", body="Interview follow-up", links=[{"target_type": "dossier", "target_id": str(dossier_id), "target_label": "Marcus Chen"}])
            self.assertEqual(note["links"][0]["target_id"], str(dossier_id))
            for invalid_id in [foreign_id, archived_id]:
                with self.assertRaises(WorkspaceEntryValidationError):
                    add_entry_link(db, case_id=self.case_id, entry_id=UUID(note["id"]), current_user=self._user(db), expected_version=1, link={"target_type": "dossier", "target_id": str(invalid_id)})

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=ENTRY_TABLES)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.user_id = uuid4()
        self.case_id = uuid4()
        self.other_case_id = uuid4()
        self.evidence_id = uuid4()
        self.other_evidence_id = uuid4()
        with self.SessionLocal() as db:
            db.add(
                User(
                    id=self.user_id,
                    email="investigator@example.test",
                    name="Investigator",
                    password_hash="hash",
                )
            )
            for case_id, title in (
                (self.case_id, "Primary case"),
                (self.other_case_id, "Other case"),
            ):
                db.add(
                    Case(
                        id=case_id,
                        title=title,
                        created_by_user_id=self.user_id,
                        owner_user_id=self.user_id,
                    )
                )
            db.add_all(
                [
                    EvidenceFile(
                        id=self.evidence_id,
                        case_id=self.case_id,
                        original_filename="ledger.pdf",
                        stored_path="C:/evidence/ledger.pdf",
                        size=100,
                        sha256="a" * 64,
                        status="processed",
                    ),
                    EvidenceFile(
                        id=self.other_evidence_id,
                        case_id=self.other_case_id,
                        original_filename="other.pdf",
                        stored_path="C:/evidence/other.pdf",
                        size=100,
                        sha256="b" * 64,
                        status="processed",
                    ),
                ]
            )
            db.commit()

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=reversed(ENTRY_TABLES))
        self.engine.dispose()

    def _user(self, db):
        return db.get(User, self.user_id)

    def test_typed_creation_and_immutable_revision_history(self):
        with self.SessionLocal() as db:
            note = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="note",
                body="Check the transfer date.",
            )
            finding = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="finding",
                title="Transfer predates the agreement",
                body="The ledger records the transfer on 4 March.",
                significance="high",
            )

            updated = update_entry(
                db,
                case_id=self.case_id,
                entry_id=UUID(note["id"]),
                current_user=self._user(db),
                expected_version=1,
                body="Check the transfer date against the signed agreement.",
            )

        self.assertIsNone(note["title"])
        self.assertEqual(finding["lifecycle_state"], "draft")
        self.assertEqual(finding["significance"], "high")
        self.assertEqual(updated["version"], 2)
        self.assertEqual([item["revision_number"] for item in updated["revisions"]], [1, 2])
        self.assertEqual(updated["revisions"][0]["body"], "Check the transfer date.")

    def test_stale_edit_is_rejected_without_overwriting(self):
        with self.SessionLocal() as db:
            entry = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="note",
                body="Original",
            )
            update_entry(
                db,
                case_id=self.case_id,
                entry_id=UUID(entry["id"]),
                current_user=self._user(db),
                expected_version=1,
                body="First editor",
            )

            with self.assertRaises(WorkspaceEntryConflict):
                update_entry(
                    db,
                    case_id=self.case_id,
                    entry_id=UUID(entry["id"]),
                    current_user=self._user(db),
                    expected_version=1,
                    body="Stale editor",
                )
            current = get_entry(db, case_id=self.case_id, entry_id=UUID(entry["id"]))

        self.assertEqual(current["body"], "First editor")

    def test_confidence_change_requires_rationale_after_initial_assessment(self):
        with self.SessionLocal() as db:
            theory = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="theory",
                title="The transfer concealed beneficial ownership",
                body="The transfer and nominee records may be connected.",
            )
            assessed = change_confidence(
                db,
                case_id=self.case_id,
                entry_id=UUID(theory["id"]),
                current_user=self._user(db),
                expected_version=1,
                confidence=60,
            )
            with self.assertRaises(WorkspaceEntryValidationError):
                change_confidence(
                    db,
                    case_id=self.case_id,
                    entry_id=UUID(theory["id"]),
                    current_user=self._user(db),
                    expected_version=2,
                    confidence=75,
                )
            revised = change_confidence(
                db,
                case_id=self.case_id,
                entry_id=UUID(theory["id"]),
                current_user=self._user(db),
                expected_version=2,
                confidence=75,
                rationale="A second nominee agreement was identified.",
            )

        self.assertEqual(assessed["confidence"], 60)
        self.assertEqual(revised["confidence"], 75)
        self.assertEqual(revised["events"][-1]["event_type"], "confidence_changed")

    def test_links_are_case_scoped_and_keep_relationship_and_anchor(self):
        with self.SessionLocal() as db:
            theory = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="theory",
                title="Ledger entry is backdated",
                body="The sequence is inconsistent.",
            )
            linked = add_entry_link(
                db,
                case_id=self.case_id,
                entry_id=UUID(theory["id"]),
                current_user=self._user(db),
                expected_version=1,
                link={
                    "target_type": "evidence",
                    "target_id": str(self.evidence_id),
                    "target_label": "ledger.pdf",
                    "relationship": "supports",
                    "source_anchor": {"page": 4, "excerpt": "4 March"},
                },
            )
            link_id = UUID(linked["links"][0]["id"])
            relabelled = update_entry_link(
                db,
                case_id=self.case_id,
                entry_id=UUID(theory["id"]),
                link_id=link_id,
                current_user=self._user(db),
                expected_version=2,
                relationship="contradicts",
                source_anchor={"page": 5},
            )

            with self.assertRaises(WorkspaceEntryValidationError):
                add_entry_link(
                    db,
                    case_id=self.case_id,
                    entry_id=UUID(theory["id"]),
                    current_user=self._user(db),
                    expected_version=3,
                    link={
                        "target_type": "evidence",
                        "target_id": str(self.other_evidence_id),
                    },
                )

        self.assertEqual(relabelled["links"][0]["relationship"], "contradicts")
        self.assertEqual(relabelled["links"][0]["source_anchor"], {"page": 5})

    def test_theory_conversion_is_atomic_and_preserves_provenance_and_links(self):
        with self.SessionLocal() as db:
            theory = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="theory",
                title="The transfer was concealed",
                body="The ledger and nominee agreement align.",
                tags=["ownership"],
                confidence=85,
                links=[
                    {
                        "target_type": "evidence",
                        "target_id": str(self.evidence_id),
                        "relationship": "supports",
                    }
                ],
            )
            converted = convert_theory_to_finding(
                db,
                case_id=self.case_id,
                theory_id=UUID(theory["id"]),
                current_user=self._user(db),
                expected_version=1,
                significance="high",
            )

        self.assertEqual(converted["theory"]["lifecycle_state"], "converted")
        self.assertEqual(converted["finding"]["lifecycle_state"], "draft")
        self.assertEqual(converted["finding"]["source_theory_entry_id"], theory["id"])
        self.assertEqual(converted["finding"]["tags"], ["ownership"])
        self.assertEqual(converted["finding"]["links"][0]["relationship"], "supports")

    def test_task_attachments_use_only_canonical_case_tasks(self):
        task_id = uuid4()
        foreign_task_id = uuid4()
        with self.SessionLocal() as db:
            db.add_all(
                [
                    CaseTask(
                        id=task_id,
                        case_id=self.case_id,
                        title="Interview the account holder",
                        status="todo",
                        priority="high",
                    ),
                    CaseTask(
                        id=foreign_task_id,
                        case_id=self.other_case_id,
                        title="Foreign case task",
                        status="todo",
                        priority="standard",
                    ),
                ]
            )
            db.commit()
            note = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="note",
                body="Follow-up work",
                links=[{"target_type": "task", "target_id": str(task_id)}],
            )
            results = search_attachment_options(
                db,
                case_id=self.case_id,
                target_type="task",
                query_text="account holder",
                limit=20,
            )
            with self.assertRaises(WorkspaceEntryValidationError):
                add_entry_link(
                    db,
                    case_id=self.case_id,
                    entry_id=UUID(note["id"]),
                    current_user=self._user(db),
                    expected_version=1,
                    link={"target_type": "task", "target_id": str(foreign_task_id)},
                )

        self.assertEqual([row["target_id"] for row in results], [str(task_id)])

    def test_soft_delete_and_restore_preserve_the_entry(self):
        with self.SessionLocal() as db:
            note = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="note",
                body="Preserve this note.",
            )
            soft_delete_entry(
                db,
                case_id=self.case_id,
                entry_id=UUID(note["id"]),
                current_user=self._user(db),
                expected_version=1,
            )
            deleted = get_entry(
                db,
                case_id=self.case_id,
                entry_id=UUID(note["id"]),
                include_deleted=True,
            )
            restored = restore_entry(
                db,
                case_id=self.case_id,
                entry_id=UUID(note["id"]),
                current_user=self._user(db),
                expected_version=2,
            )

        self.assertIsNotNone(deleted["deleted_at"])
        self.assertIsNone(restored["deleted_at"])
        self.assertEqual(restored["body"], "Preserve this note.")

    def test_raw_html_and_invalid_type_fields_are_rejected(self):
        with self.SessionLocal() as db:
            with self.assertRaises(WorkspaceEntryValidationError):
                create_entry(
                    db,
                    case_id=self.case_id,
                    current_user=self._user(db),
                    entry_type="note",
                    body="<script>alert('x')</script>",
                )

    def test_database_constraints_reject_invalid_types_relationships_and_duplicate_links(self):
        with self.SessionLocal() as db:
            invalid = WorkspaceEntry(
                case_id=self.case_id,
                entry_type="memo",
                title="Invalid type",
                body="Body",
                review_state="accepted",
            )
            db.add(invalid)
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            note = create_entry(
                db,
                case_id=self.case_id,
                current_user=self._user(db),
                entry_type="note",
                body="Constraint target",
                links=[
                    {
                        "target_type": "graph_entity",
                        "target_id": "person:henry",
                    }
                ],
            )
            note_id = UUID(note["id"])
            db.add(
                WorkspaceEntryLink(
                    entry_id=note_id,
                    case_id=self.case_id,
                    target_type="graph_entity",
                    target_id="person:other",
                    relationship_type="agrees_with",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()

            db.add(
                WorkspaceEntryLink(
                    entry_id=note_id,
                    case_id=self.case_id,
                    target_type="graph_entity",
                    target_id="person:henry",
                    relationship_type="unclassified",
                )
            )
            with self.assertRaises(IntegrityError):
                db.commit()
            db.rollback()
            with self.assertRaises(WorkspaceEntryValidationError):
                create_entry(
                    db,
                    case_id=self.case_id,
                    current_user=self._user(db),
                    entry_type="finding",
                    title="Finding",
                    body="Body",
                    significance=None,
                )


if __name__ == "__main__":
    unittest.main()
