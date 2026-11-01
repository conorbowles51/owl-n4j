"""The reverse lookup: where a record is used in the case (07 section 6.4 item 7; CO-16 API)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres import link_types
from postgres.base import Base
from postgres.models.activity_event import ActivityEvent
from postgres.models.collection_membership import CollectionMembership
from postgres.models.user import User
from postgres.models.work import CaseTask, CaseTaskLink
from postgres.models.workspace_entry import WorkspaceEntryEvent, WorkspaceEntryRevision
from services import collection_lookup, dossier_service, work_service
from services import workspace_entry_service as entries
from tests.test_dossier_service import TABLES as DOSSIER_TABLES
from tests.test_workspace_entry_service import ENTRY_TABLES

SELECTION = tuple(f"rec-{n}" for n in range(12345))


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    tables = list(dict.fromkeys(DOSSIER_TABLES + ENTRY_TABLES + [
        WorkspaceEntryRevision.__table__, WorkspaceEntryEvent.__table__, CaseTaskLink.__table__,
        ActivityEvent.__table__, CollectionMembership.__table__]))
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    from postgres.models.case import Case

    user_id, case_id = uuid.uuid4(), uuid.uuid4()
    with factory() as db:
        db.add(User(id=user_id, email="owner@example.test", name="Owner", password_hash="x"))
        db.flush()
        db.add(Case(id=case_id, title="Case", created_by_user_id=user_id, owner_user_id=user_id))
        db.commit()
    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver("phone_record", lambda db, case, target: link_types.PhoneTarget(
        label=target, mapping_versions={"m": 1}))
    link_types.register_phone_resolver("phone_selection", lambda db, case, target: link_types.PhoneTarget(
        label="Selection", mapping_versions={"m": 1}, members=SELECTION if target == "sel-big" else ("rec-1", "rec-2")))
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None), \
            patch.object(dossier_service, "_case_member_ids", return_value=set()), \
            patch.object(work_service, "check_case_access", return_value=(None, None), create=True):
        yield factory, user_id, case_id
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)
    engine.dispose()


def _finding(db, case_id, user, title="Finding"):
    return uuid.UUID(entries.create_entry(db, case_id=case_id, current_user=user, entry_type="finding",
                                          title=title, body="synthetic")["id"])


def test_a_record_collected_only_inside_a_12345_item_selection_shows_in_1_finding(world):
    """CO-16 (API)."""
    factory, user_id, case_id = world
    with factory() as db:
        user = db.get(User, user_id)
        finding = _finding(db, case_id, user)
        entries.batch_add_entry_links(db, case_id=case_id, entry_id=finding, current_user=user,
                                      links=[{"target_type": "phone_selection", "target_id": "sel-big"}],
                                      rationale="Added from Conversations")
        result = collection_lookup.lookup(db, case_id=case_id, target_type="phone_record",
                                          target_ids=["rec-12000", "rec-99999"])
        inside, outside = result["results"]
        assert inside["summary"] == "In 1 finding"
        assert inside["counts"] == {"finding": 1}
        assert [(use["kind"], use["container_id"], use["via"]) for use in inside["uses"]] == [
            ("finding", str(finding), "selection")]
        assert outside == {"target_id": "rec-99999", "uses": [], "counts": {}, "summary": None}


def test_direct_and_selection_uses_across_containers_and_removed_or_deleted_ones_are_not_reported(world):
    factory, user_id, case_id = world
    with factory() as db:
        user = db.get(User, user_id)
        finding = _finding(db, case_id, user)
        entries.batch_add_entry_links(db, case_id=case_id, entry_id=finding, current_user=user, rationale="t", links=[
            {"target_type": "phone_record", "target_id": "rec-1", "relationship": "supports"},
            {"target_type": "phone_selection", "target_id": "sel-small"}])
        dossier_id = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                             data={"display_name": "Subject"})["id"])
        added = dossier_service.add_links(db, dossier_id=dossier_id, user=user, links=[
            {"target_type": "phone_selection", "target_id": "sel-small"}])
        dossier_service.create_interview(db, dossier_id=dossier_id, user=user, data={
            "evidence_links": [{"target_type": "phone_record", "target_id": "rec-2"}]})
        task = CaseTask(id=uuid.uuid4(), case_id=case_id, title="Review", created_by_user_id=user_id,
                        updated_by_user_id=user_id)
        db.add(task)
        db.flush()
        work_service._replace_links(db, task=task, user=user, links=[{"target_type": "phone_selection", "target_id": "sel-small"}])
        db.commit()
        result = collection_lookup.lookup(db, case_id=case_id, target_type="phone_record", target_ids=["rec-1", "rec-2"])
        one, two = result["results"]
        assert one["counts"] == {"finding": 1, "dossier": 1, "task": 1}  # direct + selection on the finding counts once
        assert one["summary"] == "In 1 finding, 1 dossier and 1 task"
        assert {use["via"] for use in one["uses"] if use["kind"] == "finding"} == {"direct", "selection"}
        assert two["counts"] == {"finding": 1, "dossier": 1, "interview": 1, "task": 1}

        dossier_service.remove_link(db, dossier_id=dossier_id, link_id=uuid.UUID(added["added_link_ids"][0]), user=user)
        db.get(CaseTask, task.id).deleted_at = task.created_at
        db.commit()
        entries.soft_delete_entry(db, case_id=case_id, entry_id=finding, current_user=user,
                                  expected_version=entries.get_entry(db, case_id=case_id, entry_id=finding)["version"])
        after = collection_lookup.lookup(db, case_id=case_id, target_type="phone_record", target_ids=["rec-1", "rec-2"])
        assert [item["counts"] for item in after["results"]] == [{}, {"interview": 1}]


def test_batches_are_bounded_and_refused_not_cut(world):
    factory, _, case_id = world
    with factory() as db:
        with pytest.raises(collection_lookup.LookupRefused, match="at most 200"):
            collection_lookup.lookup(db, case_id=case_id, target_type="phone_record",
                                     target_ids=[f"r{n}" for n in range(201)])
        with pytest.raises(collection_lookup.LookupRefused, match="Unknown link type"):
            collection_lookup.lookup(db, case_id=case_id, target_type="bogus", target_ids=["x"])


def test_route(world):
    from postgres.session import get_db
    from routers import workspace_entries
    from routers.case_access import require_case_view

    factory, user_id, case_id = world
    app = FastAPI()
    app.include_router(workspace_entries.router)

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[require_case_view] = lambda: None
    client = TestClient(app)
    response = client.get(f"/api/workspace/{case_id}/collections",
                          params=[("target_type", "phone_record"), ("target_ids[]", "rec-1"), ("target_ids[]", "rec-2")])
    assert response.status_code == 200, response.text
    assert [item["target_id"] for item in response.json()["results"]] == ["rec-1", "rec-2"]
    refused = client.get(f"/api/workspace/{case_id}/collections",
                         params=[("target_type", "phone_record")] + [("target_ids[]", f"r{n}") for n in range(201)])
    assert refused.status_code == 400 and "at most 200" in refused.json()["detail"]


def test_replacing_links_keeps_the_selection_index_in_step_and_conversion_keeps_collected_versions(world):
    factory, user_id, case_id = world
    with factory() as db:
        user = db.get(User, user_id)
        dossier_id = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                             data={"display_name": "Subject"})["id"])
        dossier_service.replace_links(db, dossier_id=dossier_id, user=user, links=[
            {"target_type": "phone_selection", "target_id": "sel-small"}])
        found = collection_lookup.lookup(db, case_id=case_id, target_type="phone_record", target_ids=["rec-1"])
        assert found["results"][0]["counts"] == {"dossier": 1}
        dossier_service.replace_links(db, dossier_id=dossier_id, user=user, links=[])
        assert db.query(CollectionMembership).count() == 0

        theory = uuid.UUID(entries.create_entry(db, case_id=case_id, current_user=user, entry_type="theory",
                                                title="Theory", body="synthetic")["id"])
        entries.batch_add_entry_links(db, case_id=case_id, entry_id=theory, current_user=user, rationale="t", links=[
            {"target_type": "phone_record", "target_id": "rec-1"}, {"target_type": "phone_selection", "target_id": "sel-small"}])
        link_types._RESOLVERS.clear()  # conversion must not re-resolve what was collected
        version = entries.get_entry(db, case_id=case_id, entry_id=theory)["version"]
        finding = entries.convert_theory_to_finding(db, case_id=case_id, theory_id=theory, current_user=user,
                                                    expected_version=version, significance="medium",
                                                    title="Finding", body="synthetic")
        copied = {link["target_type"]: link for link in finding["finding"]["links"]}
        assert copied["phone_record"]["source_anchor"]["mapping_versions"] == {"m": 1}
        result = collection_lookup.lookup(db, case_id=case_id, target_type="phone_record", target_ids=["rec-2"])
        assert result["results"][0]["counts"].get("finding") == 1


def test_interview_evidence_files_are_found_by_evidence_id(world):
    from postgres.models.evidence import EvidenceFile

    factory, user_id, case_id = world
    with factory() as db:
        user = db.get(User, user_id)
        file = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename="a.pdf", stored_path="/x", size=1,
                            sha256="a" * 64, status="processed")
        db.add(file)
        db.commit()
        dossier_id = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                             data={"display_name": "Subject"})["id"])
        dossier_service.create_interview(db, dossier_id=dossier_id, user=user, data={"evidence_links": [{"evidence_file_id": file.id}]})
        result = collection_lookup.lookup(db, case_id=case_id, target_type="evidence", target_ids=[str(file.id), "not-a-uuid"])
        assert [item["counts"] for item in result["results"]] == [{"interview": 1}, {}]
