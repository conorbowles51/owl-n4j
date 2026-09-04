from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, func, select

from postgres.backfills.workspace_cutover import (
    backfill_legacy_evidence_dossier_links,
    backfill_missing_entry_history,
)
from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierLink
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryRevision,
)


TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    CaseProfile.__table__,
    DossierLink.__table__,
    WorkspaceEntry.__table__,
    WorkspaceEntryRevision.__table__,
    WorkspaceEntryEvent.__table__,
]


def test_missing_entry_history_is_recovered_once_and_preserves_snapshot():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    user_id, case_id, entry_id = uuid4(), uuid4(), uuid4()
    created_at = datetime(2025, 4, 3, 2, 1, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert().values(
                id=user_id,
                email="owner@example.test",
                name="Owner",
                password_hash="x",
            )
        )
        connection.execute(
            Case.__table__.insert().values(
                id=case_id,
                title="Cutover case",
                created_by_user_id=user_id,
                owner_user_id=user_id,
            )
        )
        connection.execute(
            WorkspaceEntry.__table__.insert().values(
                id=entry_id,
                case_id=case_id,
                entry_type="theory",
                title="Recovered theory",
                body="Current canonical body",
                tags=["cutover"],
                lifecycle_state="investigating",
                confidence=70,
                review_state="accepted",
                author_user_id=user_id,
                author_email="owner@example.test",
                author_name="Owner",
                updated_by_user_id=user_id,
                updated_by_email="owner@example.test",
                updated_by_name="Owner",
                version=4,
                migration_metadata={},
                needs_migration_review=False,
                created_at=created_at,
                updated_at=created_at,
            )
        )

        first = backfill_missing_entry_history(connection)
        second = backfill_missing_entry_history(connection)

        revision = connection.execute(
            select(WorkspaceEntryRevision.__table__).where(
                WorkspaceEntryRevision.entry_id == entry_id
            )
        ).mappings().one()
        event = connection.execute(
            select(WorkspaceEntryEvent.__table__).where(
                WorkspaceEntryEvent.entry_id == entry_id
            )
        ).mappings().one()
        revision_count = connection.scalar(
            select(func.count()).select_from(WorkspaceEntryRevision)
        )
        event_count = connection.scalar(
            select(func.count()).select_from(WorkspaceEntryEvent)
        )

    assert first == {"entries": 1, "revisions_created": 1, "events_created": 1}
    assert second == {"entries": 1, "revisions_created": 0, "events_created": 0}
    assert revision_count == 1
    assert event_count == 1
    assert revision["revision_number"] == 4
    assert revision["body"] == "Current canonical body"
    assert event["after_state"]["version"] == 4
    engine.dispose()


def test_missing_entry_history_can_be_scoped_to_fixture_cases():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    user_id, included_case_id, excluded_case_id = uuid4(), uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert().values(
                id=user_id,
                email="fixture-owner@example.test",
                name="Fixture Owner",
                password_hash="x",
            )
        )
        connection.execute(
            Case.__table__.insert(),
            [
                {
                    "id": case_id,
                    "title": title,
                    "created_by_user_id": user_id,
                    "owner_user_id": user_id,
                }
                for case_id, title in (
                    (included_case_id, "Included fixture"),
                    (excluded_case_id, "Unrelated case"),
                )
            ],
        )
        connection.execute(
            WorkspaceEntry.__table__.insert(),
            [
                {
                    "id": uuid4(),
                    "case_id": case_id,
                    "entry_type": "note",
                    "body": title,
                    "tags": [],
                    "review_state": "accepted",
                    "author_user_id": user_id,
                    "author_email": "fixture-owner@example.test",
                    "author_name": "Fixture Owner",
                    "updated_by_user_id": user_id,
                    "updated_by_email": "fixture-owner@example.test",
                    "updated_by_name": "Fixture Owner",
                    "version": 1,
                    "migration_metadata": {},
                    "needs_migration_review": False,
                }
                for case_id, title in (
                    (included_case_id, "Included"),
                    (excluded_case_id, "Excluded"),
                )
            ],
        )

        report = backfill_missing_entry_history(
            connection, case_ids=[included_case_id]
        )
        history_case_ids = set(
            connection.execute(select(WorkspaceEntryRevision.case_id)).scalars()
        )

    assert report == {"entries": 1, "revisions_created": 1, "events_created": 1}
    assert history_case_ids == {included_case_id}
    engine.dispose()


def test_legacy_evidence_profile_links_become_canonical_dossier_links_once():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    user_id, case_id = uuid4(), uuid4()
    other_case_id, dossier_id, other_dossier_id, evidence_id = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    with engine.begin() as connection:
        connection.execute(
            User.__table__.insert().values(
                id=user_id,
                email="owner@example.test",
                name="Owner",
                password_hash="x",
            )
        )
        connection.execute(
            Case.__table__.insert(),
            [
                {
                    "id": value,
                    "title": title,
                    "created_by_user_id": user_id,
                    "owner_user_id": user_id,
                }
                for value, title in (
                    (case_id, "Cutover case"),
                    (other_case_id, "Other case"),
                )
            ],
        )
        connection.execute(
            CaseProfile.__table__.insert(),
            [
                {
                    "id": dossier_id,
                    "case_id": case_id,
                    "profile_type": "person",
                    "display_name": "Henry",
                    "linkage_state": "unlinked",
                    "status": "active",
                    "needs_link_review": False,
                    "graph_entity_deleted": False,
                    "created_by_user_id": user_id,
                },
                {
                    "id": other_dossier_id,
                    "case_id": other_case_id,
                    "profile_type": "person",
                    "display_name": "Other person",
                    "linkage_state": "unlinked",
                    "status": "active",
                    "needs_link_review": False,
                    "graph_entity_deleted": False,
                    "created_by_user_id": user_id,
                },
            ],
        )
        connection.execute(
            EvidenceFile.__table__.insert().values(
                id=evidence_id,
                case_id=case_id,
                original_filename="portrait.jpg",
                stored_path="evidence/portrait.jpg",
                size=10,
                sha256="a" * 64,
                status="processed",
                linked_entity_ids=[
                    str(dossier_id),
                    str(dossier_id),
                    str(other_dossier_id),
                    "not-a-uuid",
                ],
                created_by_id=user_id,
            )
        )

        first = backfill_legacy_evidence_dossier_links(connection)
        second = backfill_legacy_evidence_dossier_links(connection)
        created = connection.execute(select(DossierLink.__table__)).mappings().all()

    assert first == {
        "evidence_files_scanned": 1,
        "source_links": 3,
        "links_created": 1,
        "links_already_present": 0,
        "unresolved_links": 2,
    }
    assert second == {
        "evidence_files_scanned": 1,
        "source_links": 3,
        "links_created": 0,
        "links_already_present": 1,
        "unresolved_links": 2,
    }
    assert len(created) == 1
    assert created[0]["dossier_id"] == dossier_id
    assert created[0]["target_id"] == str(evidence_id)
    assert created[0]["source_anchor"] == {
        "legacy_source": "evidence_files.linked_entity_ids"
    }
    engine.dispose()
