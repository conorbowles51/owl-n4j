from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import (
    DossierAssessment, DossierAssessmentLink, DossierGeneratedOutput,
    DossierInterview, DossierInterviewEvidenceLink, DossierLegacyMapping,
    DossierLink, DossierMedia, DossierRole,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import WorkspaceEntry
from services import dossier_service
from services.case_service import CaseAccessDenied


TABLES = [
    User.__table__, Case.__table__, EvidenceFile.__table__, WorkspaceEntry.__table__,
    CaseDeadline.__table__, CaseTask.__table__,
    CaseProfile.__table__, DossierRole.__table__, DossierLink.__table__,
    DossierAssessment.__table__, DossierAssessmentLink.__table__, DossierMedia.__table__,
    DossierInterview.__table__, DossierInterviewEvidenceLink.__table__,
    DossierGeneratedOutput.__table__, DossierLegacyMapping.__table__,
]


@pytest.fixture()
def setup_db(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    user_id, case_id, other_case_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with session_factory() as db:
        user = User(id=user_id, email="owner@example.test", name="Owner", password_hash="x")
        db.add(user)
        db.add_all([
            Case(id=case_id, title="Case", created_by_user_id=user_id, owner_user_id=user_id),
            Case(id=other_case_id, title="Other", created_by_user_id=user_id, owner_user_id=user_id),
        ])
        image_path = tmp_path / "portrait.png"; image_path.write_bytes(b"image")
        image = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename="portrait.png", stored_path=str(image_path), size=5, sha256="a" * 64, status="unprocessed", metadata_={"camera": "A"})
        source = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename="statement.pdf", stored_path=str(tmp_path / "statement.pdf"), size=8, sha256="b" * 64, status="processed", metadata_={})
        foreign = EvidenceFile(id=uuid.uuid4(), case_id=other_case_id, original_filename="foreign.png", stored_path=str(tmp_path / "foreign.png"), size=1, sha256="c" * 64, status="unprocessed", metadata_={})
        db.add_all([image, source, foreign]); db.commit()
    yield session_factory, user_id, case_id, image.id, source.id, foreign.id
    engine.dispose()


@pytest.fixture(autouse=True)
def permissions():
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), patch.object(dossier_service, "get_case_if_allowed", return_value=None):
        yield


def test_unlinked_and_linked_dossier_uniqueness_and_current_identity(setup_db):
    factory, user_id, case_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        unlinked = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Unknown caller", "dossier_type": "person", "roles": [{"name": "Source"}, {"name": "Custom role"}]})
        assert unlinked["linkage_state"] == "unlinked"
        assert {role["name"] for role in unlinked["roles"]} == {"Source", "Custom role"}

        graph = {"key": "person:henry", "name": "Henry Current", "type": "Person", "verified_facts": [{"fact": "current"}], "connections": []}
        with patch.object(dossier_service, "_graph_identity", return_value=graph), patch.object(dossier_service, "add_significant_entities") as significant:
            linked = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"canonical_entity_key": "person:henry", "display_name": "Stale"})
            assert linked["display_name"] == "Henry Current"
            assert linked["display_name_snapshot"] == "Henry Current"
            significant.assert_called_once()
            with pytest.raises(dossier_service.DossierConflict):
                dossier_service.create_dossier(db, case_id=case_id, user=user, data={"canonical_entity_key": "person:henry"})


def test_task_and_deadline_links_enforce_case_isolation(setup_db):
    factory, user_id, case_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        other_case_id = db.scalar(select(Case.id).where(Case.id != case_id))
        local_deadline = CaseDeadline(case_id=case_id, name="Local", due_date=date(2026, 9, 20))
        foreign_deadline = CaseDeadline(case_id=other_case_id, name="Foreign", due_date=date(2026, 9, 21))
        db.add_all([local_deadline, foreign_deadline]); db.flush()
        local_task = CaseTask(case_id=case_id, title="Local task", status="todo", priority="standard")
        foreign_task = CaseTask(case_id=other_case_id, title="Foreign task", status="todo", priority="standard")
        db.add_all([local_task, foreign_task]); db.commit()
        dossier = dossier_service.create_dossier(
            db,
            case_id=case_id,
            user=user,
            data={"display_name": "Link isolation", "dossier_type": "person"},
        )
        updated = dossier_service.replace_links(
            db,
            dossier_id=uuid.UUID(dossier["id"]),
            user=user,
            links=[
                {"target_type": "task", "target_id": str(local_task.id)},
                {"target_type": "deadline", "target_id": str(local_deadline.id)},
            ],
        )
        assert {link["target_id"] for link in updated["links"]} == {
            str(local_task.id),
            str(local_deadline.id),
        }
        with pytest.raises(ValueError, match="not in this case"):
            dossier_service.replace_links(
                db,
                dossier_id=uuid.UUID(dossier["id"]),
                user=user,
                links=[{"target_type": "task", "target_id": str(foreign_task.id)}],
            )
        with pytest.raises(ValueError, match="not in this case"):
            dossier_service.replace_links(
                db,
                dossier_id=uuid.UUID(dossier["id"]),
                user=user,
                links=[{"target_type": "deadline", "target_id": str(foreign_deadline.id)}],
            )


def test_media_is_non_destructive_single_cover_and_cross_case_safe(setup_db):
    factory, user_id, case_id, image_id, _source_id, foreign_id = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Henry"})
        original = db.get(EvidenceFile, image_id)
        fingerprint = (original.sha256, original.size, dict(original.metadata_))
        media = dossier_service.add_media(db, dossier_id=uuid.UUID(dossier["id"]), user=user, data={"evidence_file_id": image_id, "is_cover": True, "caption": "At the station", "focal_x": .25, "focal_y": .6})
        assert media["is_cover"] is True and media["evidence"]["file_url"].endswith("/file")
        second_image = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename="second.png", stored_path="second.png", size=6, sha256="d" * 64, status="unprocessed", metadata_={})
        db.add(second_image); db.commit()
        second = dossier_service.add_media(db, dossier_id=uuid.UUID(dossier["id"]), user=user, data={"evidence_file_id": second_image.id})
        reordered = dossier_service.reorder_media(
            db,
            dossier_id=uuid.UUID(dossier["id"]),
            user=user,
            media_ids=[uuid.UUID(second["id"]), uuid.UUID(media["id"])],
        )
        assert [item["ordinal"] for item in reordered] == [0, 1]
        assert [item["id"] for item in reordered] == [second["id"], media["id"]]
        with pytest.raises(ValueError, match="every gallery item"):
            dossier_service.reorder_media(db, dossier_id=uuid.UUID(dossier["id"]), user=user, media_ids=[uuid.UUID(media["id"])])
        dossier_service.update_media(db, dossier_id=uuid.UUID(dossier["id"]), media_id=uuid.UUID(media["id"]), user=user, data={"caption": "Updated", "focal_x": .5})
        dossier_service.delete_media(db, dossier_id=uuid.UUID(dossier["id"]), media_id=uuid.UUID(media["id"]), user=user)
        db.expire_all()
        evidence = db.get(EvidenceFile, image_id)
        assert (evidence.sha256, evidence.size, dict(evidence.metadata_)) == fingerprint
        with pytest.raises(ValueError, match="not in this case"):
            dossier_service.add_media(db, dossier_id=uuid.UUID(dossier["id"]), user=user, data={"evidence_file_id": foreign_id})


def test_evidence_links_are_canonical_idempotent_filterable_and_case_safe(setup_db):
    factory, user_id, case_id, image_id, source_id, foreign_id = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        linked = dossier_service.create_dossier(
            db, case_id=case_id, user=user, data={"display_name": "Linked"}
        )
        unlinked = dossier_service.create_dossier(
            db, case_id=case_id, user=user, data={"display_name": "Unlinked"}
        )
        dossier_id = uuid.UUID(linked["id"])

        result = dossier_service.add_evidence_links(
            db,
            dossier_id=dossier_id,
            evidence_file_ids=[image_id, source_id, image_id],
            user=user,
        )
        evidence_links = [
            link for link in result["links"] if link["target_type"] == "evidence"
        ]
        assert {link["target_id"] for link in evidence_links} == {
            str(image_id),
            str(source_id),
        }
        assert db.query(DossierLink).filter_by(dossier_id=dossier_id).count() == 2

        filtered = dossier_service.list_dossiers(
            db,
            case_id=case_id,
            user=user,
            linked_evidence_file_id=image_id,
        )
        assert [item["id"] for item in filtered["dossiers"]] == [linked["id"]]
        assert unlinked["id"] not in {item["id"] for item in filtered["dossiers"]}

        with pytest.raises(ValueError, match="belong to the Dossier case"):
            dossier_service.add_evidence_links(
                db,
                dossier_id=dossier_id,
                evidence_file_ids=[foreign_id],
                user=user,
            )

        dossier_service.remove_evidence_link(
            db,
            dossier_id=dossier_id,
            evidence_file_id=image_id,
            user=user,
        )
        filtered = dossier_service.list_dossiers(
            db,
            case_id=case_id,
            user=user,
            linked_evidence_file_id=image_id,
        )
        assert filtered["total"] == 0


def test_evidence_link_mutations_require_case_edit_permission(setup_db):
    factory, user_id, case_id, image_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier = dossier_service.create_dossier(
            db, case_id=case_id, user=user, data={"display_name": "Protected"}
        )
        with patch.object(
            dossier_service,
            "check_case_access",
            side_effect=CaseAccessDenied("Edit permission required"),
        ) as access:
            with pytest.raises(CaseAccessDenied):
                dossier_service.add_evidence_links(
                    db,
                    dossier_id=uuid.UUID(dossier["id"]),
                    evidence_file_ids=[image_id],
                    user=user,
                )
        access.assert_called_once_with(
            db,
            case_id,
            user,
            required_permission=("case", "edit"),
        )


def test_assessment_provenance_and_interview_multiple_sources(setup_db):
    factory, user_id, case_id, image_id, source_id, foreign_id = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Witness A", "roles": [{"name": "Witness"}]})
        dossier_id = uuid.UUID(dossier["id"])
        assessment = dossier_service.create_assessment(db, dossier_id=dossier_id, user=user, data={"category": "credibility", "content": "Account is internally consistent", "supporting_links": [{"target_type": "evidence", "target_id": str(source_id), "source_anchor": {"page": 4}}]})
        assert assessment["author_user_id"] == str(user_id)
        assert assessment["supporting_links"][0]["source_anchor"] == {"page": 4}
        with pytest.raises(ValueError, match="not in this case"):
            dossier_service.create_assessment(db, dossier_id=dossier_id, user=user, data={"category": "risk", "content": "x", "supporting_links": [{"target_type": "evidence", "target_id": str(foreign_id)}]})
        db.rollback()
        with patch.object(dossier_service, "_case_member_ids", return_value={str(user_id)}):
            interview = dossier_service.create_interview(db, dossier_id=dossier_id, user=user, data={"status": "completed", "participants": ["Witness A"], "interviewer_user_ids": [user_id], "working_notes": "Follow-up required", "evidence_links": [{"evidence_file_id": image_id}, {"evidence_file_id": source_id, "source_anchor": {"page": 2}}]})
        assert len(interview["evidence_links"]) == 2
        assert interview["created_by_user_id"] == str(user_id)


def test_graph_lifecycle_preserves_material_and_flags_ambiguous_merge(setup_db):
    factory, user_id, case_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        graph = lambda _case_id, key: {"key": key, "name": key, "type": "Person", "connections": []}
        with patch.object(dossier_service, "_graph_identity", side_effect=graph), patch.object(dossier_service, "add_significant_entities"):
            first = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"canonical_entity_key": "a"})
            second = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"canonical_entity_key": "b"})
        assert dossier_service.suspend_dossier_for_entity_delete(db, case_id=case_id, entity_key="a") == 1
        assert db.get(CaseProfile, uuid.UUID(first["id"])).linkage_state == "deleted"
        assert dossier_service.restore_dossier_after_entity_restore(db, case_id=case_id, entity_key="a") == 1
        assert dossier_service.transfer_dossiers_after_merge(db, case_id=case_id, source_entity_keys=["a", "b"], merged_entity_key="merged") == 2
        rows = db.scalars(select(CaseProfile).where(CaseProfile.id.in_([uuid.UUID(first["id"]), uuid.UUID(second["id"])]))).all()
        assert all(row.canonical_entity_key is None and row.needs_link_review for row in rows)
        assert db.scalar(select(DossierLink).where(DossierLink.dossier_id == rows[0].id, DossierLink.target_id == "merged"))
