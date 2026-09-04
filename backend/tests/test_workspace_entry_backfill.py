import unittest
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.backfills.workspace_entries import backfill_workspace_entries
from postgres.models.case import Case
from postgres.models.case_profile import (
    CaseProfile,
    CaseProfileFindingLink,
    CaseProfileNoteLink,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding, WorkspaceNote, WorkspaceTheory
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
    WorkspaceLegacyMapping,
)
from services.workspace_entry_reconciliation_service import (
    build_workspace_entry_reconciliation_report,
)


BACKFILL_TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    NotebookNote.__table__,
    NotebookNoteLink.__table__,
    WorkspaceNote.__table__,
    WorkspaceFinding.__table__,
    WorkspaceTheory.__table__,
    WorkspaceEntry.__table__,
    WorkspaceEntryRevision.__table__,
    WorkspaceEntryLink.__table__,
    WorkspaceEntryEvent.__table__,
    WorkspaceLegacyMapping.__table__,
    CaseProfile.__table__,
    CaseProfileNoteLink.__table__,
    CaseProfileFindingLink.__table__,
]


class WorkspaceEntryBackfillTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=BACKFILL_TABLES)

    def tearDown(self):
        Base.metadata.drop_all(self.engine, tables=reversed(BACKFILL_TABLES))
        self.engine.dispose()

    def test_empty_database_is_a_repeatable_no_op(self):
        with self.engine.begin() as connection:
            first = backfill_workspace_entries(connection)
            second = backfill_workspace_entries(connection)

        self.assertEqual(first["summary"]["source_records"], 0)
        self.assertEqual(first["summary"]["migrated_entries"], 0)
        self.assertEqual(second["summary"]["source_records"], 0)
        self.assertEqual(second["summary"]["migrated_entries"], 0)

    def test_representative_legacy_data_is_preserved_and_idempotent(self):
        user_id = uuid4()
        case_id = uuid4()
        evidence_id = uuid4()
        notebook_id = uuid4()
        deleted_notebook_id = uuid4()
        profile_id = uuid4()
        profile_note_link_id = uuid4()
        profile_finding_link_id = uuid4()
        created_at = datetime(2024, 2, 3, 10, 11, 12, tzinfo=timezone.utc)
        updated_at = datetime(2024, 3, 4, 13, 14, 15, tzinfo=timezone.utc)
        deleted_at = datetime(2024, 4, 5, 16, 17, 18, tzinfo=timezone.utc)

        with self.engine.begin() as connection:
            connection.execute(
                User.__table__.insert().values(
                    id=user_id,
                    email="investigator@example.test",
                    name="Investigator",
                    password_hash="hash",
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                Case.__table__.insert().values(
                    id=case_id,
                    title="Representative case",
                    created_by_user_id=user_id,
                    owner_user_id=user_id,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                EvidenceFile.__table__.insert().values(
                    id=evidence_id,
                    case_id=case_id,
                    original_filename="ledger.pdf",
                    stored_path="C:/evidence/ledger.pdf",
                    size=100,
                    sha256="a" * 64,
                    status="processed",
                    legacy_id="legacy-ledger",
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                NotebookNote.__table__.insert(),
                [
                    {
                        "id": notebook_id,
                        "case_id": case_id,
                        "author_user_id": user_id,
                        "author_email": "investigator@example.test",
                        "author_name": "Investigator",
                        "title": "Notebook title",
                        "body": "Notebook body",
                        "tags": ["interview"],
                        "visibility": "case",
                        "deleted_at": None,
                        "created_at": created_at,
                        "updated_at": updated_at,
                    },
                    {
                        "id": deleted_notebook_id,
                        "case_id": case_id,
                        "author_user_id": None,
                        "author_email": "former@example.test",
                        "author_name": "Former investigator",
                        "title": None,
                        "body": "A recoverable deleted note",
                        "tags": [],
                        "visibility": "case",
                        "deleted_at": deleted_at,
                        "created_at": created_at,
                        "updated_at": updated_at,
                    },
                ],
            )
            connection.execute(
                NotebookNoteLink.__table__.insert(),
                [
                    {
                        "id": uuid4(),
                        "note_id": notebook_id,
                        "case_id": case_id,
                        "target_type": "document",
                        "target_id": "ledger.pdf",
                        "target_label": "Ledger",
                        "metadata": {
                            "relationship": "supporting",
                            "source_anchor": {"page": 8},
                        },
                        "created_at": created_at,
                        "updated_at": updated_at,
                    },
                    {
                        "id": uuid4(),
                        "note_id": notebook_id,
                        "case_id": case_id,
                        "target_type": "entity",
                        "target_id": "person:henry",
                        "target_label": "Henry",
                        "metadata": {},
                        "created_at": created_at,
                        "updated_at": updated_at,
                    },
                ],
            )
            connection.execute(
                WorkspaceNote.__table__.insert().values(
                    id=uuid4(),
                    case_id=case_id,
                    note_id="legacy-note-1",
                    data={
                        "title": "Legacy note",
                        "content": "Legacy note body",
                        "tags": ["finance"],
                        "author_email": "legacy@example.test",
                        "linked_evidence_ids": ["legacy-ledger"],
                        "linked_entity_keys": ["company:acme"],
                    },
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                WorkspaceFinding.__table__.insert().values(
                    id=uuid4(),
                    case_id=case_id,
                    finding_id="legacy-finding-1",
                    data={
                        "content": "Meaningful finding without its required fields",
                        "priority": "urgent",
                    },
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                WorkspaceTheory.__table__.insert().values(
                    id=uuid4(),
                    case_id=case_id,
                    theory_id="legacy-theory-1",
                    data={
                        "title": "Concealed ownership",
                        "hypothesis": "Henry controls Acme.",
                        "confidence_score": 83,
                        "attached_document_ids": ["ledger.pdf"],
                        "attached_task_ids": ["legacy-task-1"],
                    },
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                CaseProfile.__table__.insert().values(
                    id=profile_id,
                    case_id=case_id,
                    profile_type="person",
                    display_name="Henry",
                    created_by_user_id=user_id,
                    updated_by_user_id=user_id,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                CaseProfileNoteLink.__table__.insert().values(
                    id=profile_note_link_id,
                    profile_id=profile_id,
                    case_id=case_id,
                    note_id="legacy-note-1",
                    relationship_type="context",
                    created_by_user_id=user_id,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
            connection.execute(
                CaseProfileFindingLink.__table__.insert().values(
                    id=profile_finding_link_id,
                    profile_id=profile_id,
                    case_id=case_id,
                    finding_id="legacy-finding-1",
                    relationship_type="about",
                    created_by_user_id=user_id,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )

            first = backfill_workspace_entries(connection)
            second = backfill_workspace_entries(connection)
            reconciliation = build_workspace_entry_reconciliation_report(
                Session(bind=connection)
            )

            entries = connection.execute(sa.select(WorkspaceEntry.__table__)).mappings().all()
            links = connection.execute(sa.select(WorkspaceEntryLink.__table__)).mappings().all()
            revisions = connection.scalar(sa.select(sa.func.count()).select_from(WorkspaceEntryRevision.__table__))
            events = connection.scalar(sa.select(sa.func.count()).select_from(WorkspaceEntryEvent.__table__))
            mappings = connection.scalar(sa.select(sa.func.count()).select_from(WorkspaceLegacyMapping.__table__))
            profile_note_entry_id = connection.scalar(
                sa.select(CaseProfileNoteLink.__table__.c.workspace_entry_id).where(
                    CaseProfileNoteLink.__table__.c.id == profile_note_link_id
                )
            )
            profile_finding_entry_id = connection.scalar(
                sa.select(CaseProfileFindingLink.__table__.c.workspace_entry_id).where(
                    CaseProfileFindingLink.__table__.c.id == profile_finding_link_id
                )
            )

        by_source = {(row["legacy_source"], row["legacy_id"]): row for row in entries}
        self.assertEqual(first["summary"]["source_records"], 5)
        self.assertEqual(first["summary"]["migrated_entries"], 5)
        self.assertEqual(second["summary"]["migrated_entries"], 0)
        self.assertEqual(second["summary"]["existing_entries"], 5)
        self.assertEqual(reconciliation["summary"]["source_records"], 5)
        self.assertEqual(reconciliation["summary"]["canonical_entries"], 5)
        self.assertEqual(reconciliation["summary"]["missing_mappings"], 0)
        self.assertEqual(reconciliation["summary"]["missing_targets"], 0)
        self.assertEqual(reconciliation["summary"]["inconsistent_targets"], 0)
        self.assertEqual(reconciliation["summary"]["unrepointed_profile_links"], 0)
        self.assertEqual(reconciliation["summary"]["unresolved_links"], 1)
        self.assertEqual(reconciliation["summary"]["needs_migration_review"], 1)
        self.assertEqual(len(entries), 5)
        self.assertEqual(revisions, 5)
        self.assertEqual(events, 5)
        self.assertEqual(mappings, 5)

        notebook_entry = by_source[("notebook_note", str(notebook_id))]
        deleted_entry = by_source[("notebook_note", str(deleted_notebook_id))]
        finding_entry = by_source[("workspace_finding", "legacy-finding-1")]
        note_entry = by_source[("workspace_note", "legacy-note-1")]
        self.assertEqual(notebook_entry["id"], notebook_id)
        self.assertEqual(notebook_entry["author_user_id"], user_id)
        self.assertEqual(notebook_entry["created_at"], created_at.replace(tzinfo=None))
        self.assertEqual(notebook_entry["updated_at"], updated_at.replace(tzinfo=None))
        self.assertEqual(deleted_entry["deleted_at"], deleted_at.replace(tzinfo=None))
        self.assertTrue(finding_entry["needs_migration_review"])
        self.assertTrue(finding_entry["migration_metadata"]["missing_title"])
        self.assertEqual(finding_entry["migration_metadata"]["original_priority"], "urgent")
        self.assertEqual(profile_note_entry_id, note_entry["id"])
        self.assertEqual(profile_finding_entry_id, finding_entry["id"])

        notebook_links = [row for row in links if row["entry_id"] == notebook_id]
        evidence_links = [row for row in links if row["target_type"] == "evidence"]
        unresolved_task = next(row for row in links if row["target_type"] == "task")
        self.assertEqual(len(notebook_links), 2)
        self.assertTrue(all(row["target_id"] == str(evidence_id) for row in evidence_links))
        self.assertEqual(
            next(row for row in notebook_links if row["target_type"] == "evidence")["relationship"],
            "supports",
        )
        self.assertEqual(
            next(row for row in notebook_links if row["target_type"] == "evidence")["source_anchor"],
            {"page": 8},
        )
        self.assertTrue(unresolved_task["metadata"]["migration_unresolved"])


if __name__ == "__main__":
    unittest.main()
