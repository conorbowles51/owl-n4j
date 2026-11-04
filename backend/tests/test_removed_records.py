"""Removing analyst work keeps a copy, and the removal can be undone exactly (followups m11032229063349).

Before: a dossier assessment (with its supporting links), an interview (with its working notes and evidence links),
a media item and a dossier link were hard-deleted with nothing kept; a saved snapshot likewise. Each test fails on
that code (no kept copy, nothing to restore).
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from postgres.models.collection_membership import CollectionMembership
from postgres.models.dossier import DossierAssessment, DossierAssessmentLink, DossierInterview, DossierInterviewEvidenceLink, DossierLink, DossierMedia
from postgres.models.removed_record import RemovedRecord
from postgres.models.runtime_state import SnapshotRecord
from postgres.models.user import User
from services import dossier_service, removed_records
from tests import test_dossier_service as base
from tests.test_dossier_service import permissions  # noqa: F401 - autouse fixture

setup_db = base.setup_db


def _values(row):
    return removed_records.row_values(row)


def test_a_removed_assessment_and_its_links_come_back_exactly(setup_db):
    factory, user_id, case_id, _image, source_id, _foreign = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier_id = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                              data={"display_name": "Witness"})["id"])
        made = dossier_service.create_assessment(db, dossier_id=dossier_id, user=user, data={
            "category": "credibility", "content": "Account is internally consistent",
            "supporting_links": [{"target_type": "evidence", "target_id": str(source_id), "source_anchor": {"page": 4}}]})
        aid = uuid.UUID(made["id"])
        before = [_values(db.get(DossierAssessment, aid))] + [
            _values(r) for r in db.scalars(select(DossierAssessmentLink).where(DossierAssessmentLink.assessment_id == aid))]
        dossier_service.delete_assessment(db, dossier_id=dossier_id, assessment_id=aid, user=user)
        assert db.get(DossierAssessment, aid) is None
        [kept] = removed_records.list_removed(db, case_id=case_id)["items"]
        assert (kept["kind"], kept["rows"], kept["removed_by"]) == ("dossier_assessment", 2, "owner@example.test")
        assert "internally consistent" in kept["label"]
        removed_records.restore(db, removed_records.load(db, kept["id"]), user=user)
        db.commit()
        db.expire_all()
        after = [_values(db.get(DossierAssessment, aid))] + [
            _values(r) for r in db.scalars(select(DossierAssessmentLink).where(DossierAssessmentLink.assessment_id == aid))]
        assert after == before
        assert removed_records.list_removed(db, case_id=case_id)["items"] == []
        with pytest.raises(removed_records.RemovedRecordError, match="already undone"):
            removed_records.restore(db, removed_records.load(db, kept["id"]), user=user)


def test_a_removed_interview_keeps_its_working_notes_and_evidence_links(setup_db):
    factory, user_id, case_id, image_id, source_id, _foreign = setup_db
    with factory() as db, patch.object(dossier_service, "_case_member_ids", return_value=set()):
        user = db.get(User, user_id)
        dossier_id = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                              data={"display_name": "Witness"})["id"])
        made = dossier_service.create_interview(db, dossier_id=dossier_id, user=user, data={
            "date_value": "2025-07", "working_notes": "Said she saw the van twice; follow up the second time.",
            "evidence_links": [{"evidence_file_id": image_id}, {"evidence_file_id": source_id}]})
        iid = uuid.UUID(made["id"])
        dossier_service.delete_interview(db, dossier_id=dossier_id, interview_id=iid, user=user)
        [kept] = removed_records.list_removed(db, case_id=case_id)["items"]
        assert (kept["kind"], kept["rows"]) == ("dossier_interview", 3)
        removed_records.restore(db, removed_records.load(db, kept["id"]), user=user)
        db.commit()
        db.expire_all()
        assert db.get(DossierInterview, iid).working_notes == "Said she saw the van twice; follow up the second time."
        assert len(db.scalars(select(DossierInterviewEvidenceLink)
                              .where(DossierInterviewEvidenceLink.interview_id == iid)).all()) == 2


def test_removed_media_and_links_are_kept_and_come_back(setup_db):
    factory, user_id, case_id, image_id, source_id, _foreign = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier_id = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                              data={"display_name": "Henry"})["id"])
        media = dossier_service.add_media(db, dossier_id=dossier_id, user=user,
                                          data={"evidence_file_id": image_id, "caption": "At the station"})
        dossier_service.add_evidence_links(db, dossier_id=dossier_id, user=user, evidence_file_ids=[source_id])
        dossier_service.delete_media(db, dossier_id=dossier_id, media_id=uuid.UUID(media["id"]), user=user)
        [link] = db.scalars(select(DossierLink).where(DossierLink.dossier_id == dossier_id)).all()
        link_before = _values(link)
        dossier_service.remove_link(db, dossier_id=dossier_id, link_id=link.id, user=user)
        kinds = {item["kind"] for item in removed_records.list_removed(db, case_id=case_id)["items"]}
        assert kinds == {"dossier_media", "dossier_link"}
        link_kept = next(i for i in removed_records.list_removed(db, case_id=case_id)["items"] if i["kind"] == "dossier_link")
        removed_records.restore(db, removed_records.load(db, link_kept["id"]), user=user)
        db.commit()
        db.expire_all()
        assert _values(db.get(DossierLink, link.id)) == link_before
        media_kept = next(i for i in removed_records.list_removed(db, case_id=case_id)["items"] if i["kind"] == "dossier_media")
        assert media_kept["label"] == "At the station"
        removed_records.restore(db, removed_records.load(db, media_kept["id"]), user=user)
        db.commit()
        assert db.get(DossierMedia, uuid.UUID(media["id"])).caption == "At the station"


def test_a_removed_snapshot_is_kept_for_its_owner_and_comes_back(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from postgres.base import Base
    from postgres.models.case import Case
    from services.snapshot_storage import SnapshotStorage
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, SnapshotRecord.__table__,
                                             RemovedRecord.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(SnapshotRecord(id="snap-1", owner="alex", case_id="not-a-case", name="Van sightings",
                              data={"subgraph": {"nodes": [1, 2]}, "notes": "keep"}))
        db.commit()
        storage = SnapshotStorage()
        assert storage.delete("snap-1", db=db, removed_by={"username": "alex"}) is True
        db.commit()
        assert db.get(SnapshotRecord, "snap-1") is None
        [kept] = db.scalars(select(RemovedRecord)).all()
        assert (kept.kind, kept.case_id, kept.label, kept.removed_by) == ("snapshot", None, "Van sightings", "alex")
        removed_records.restore(db, kept, user={"username": "alex"})
        db.commit()
        assert db.get(SnapshotRecord, "snap-1").data == {"subgraph": {"nodes": [1, 2]}, "notes": "keep"}
    engine.dispose()


# -- the graph: a purge keeps the last copy, a permanent delete goes through it, removed values are kept ----------

def _bin_db(item):
    from unittest.mock import MagicMock
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.side_effect = (
        lambda: item if item.status == ("purged" if db._want_purged else "active") else None)
    db._want_purged = False
    return db


def test_a_purge_keeps_the_snapshot_and_can_be_undone():
    from types import SimpleNamespace
    from services.neo4j.entity_service import entity_service
    item = SimpleNamespace(status="active", snapshot={"node": {"key": "k", "name": "Henry"}}, original_key="k",
                           original_name="Henry")
    db = _bin_db(item)
    case = str(uuid.uuid4())
    entity_service.permanently_delete_recycled("rb-k", case, db=db, purged_by="alex")
    assert (item.status, item.snapshot) == ("purged", {"node": {"key": "k", "name": "Henry"}})
    db._want_purged = True
    out = entity_service.return_purged_to_bin("rb-k", case, db=db)
    assert (item.status, out["returned"]["name"]) == ("active", "Henry")
    item.status, item.snapshot = "purged", None  # purged before copies were kept
    with pytest.raises(ValueError, match="before copies were kept"):
        entity_service.return_purged_to_bin("rb-k", case, db=db)


def test_a_permanent_node_delete_goes_through_the_recycle_bin_and_its_purge():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import auth, graph, users
    from services.neo4j import neo4j_service
    app = FastAPI()
    app.include_router(graph.router)
    app.dependency_overrides[auth.get_current_user] = lambda: {"username": "alex"}
    from types import SimpleNamespace
    from postgres.models.enums import GlobalRole
    app.dependency_overrides[users.get_current_db_user] = lambda: SimpleNamespace(
        id=uuid.uuid4(), email="alex@example.test", name="Alex", global_role=GlobalRole.super_admin)
    from postgres.session import get_db
    from unittest.mock import MagicMock
    app.dependency_overrides[get_db] = lambda: MagicMock()
    case = str(uuid.uuid4())
    with patch.object(neo4j_service, "soft_delete_entity", return_value={"success": True, "recycle_key": "rb-k"}) as soft, \
            patch.object(neo4j_service, "permanently_delete_recycled",
                         return_value={"permanently_deleted": {"recycle_key": "rb-k"}}) as purge, \
            patch.object(neo4j_service, "delete_node") as bare, \
            patch.object(graph, "suspend_significant_entity_for_delete", return_value=False), \
            patch.object(graph, "suspend_dossier_for_entity_delete", return_value=0):
        response = TestClient(app).delete(f"/api/graph/node/k?case_id={case}&permanent=true")
    assert response.status_code == 200, response.text
    bare.assert_not_called()
    assert soft.call_args.kwargs["reason"] == "permanent_delete"
    assert purge.call_args.args[:2] == ("rb-k", case)


def test_a_removed_location_returns_the_values_it_removed():
    from services.neo4j.graph_edit_service import GraphEditService
    service = GraphEditService.__new__(GraphEditService)
    changes = {"latitude": {"before": 51.5, "after": None}, "location_name": {"before": "Camden", "after": None}}
    with patch.object(GraphEditService, "update_node", return_value={"success": True, "changes": changes}):
        out = service.remove_location("k", case_id="c")
    assert out["before"] == {"latitude": 51.5, "location_name": "Camden"}
    assert out["after"] == {"latitude": None, "location_name": None}


def test_the_removals_of_one_dossier_are_listed_for_it_and_put_back_through_the_route(setup_db):
    from routers import removed_records as route
    factory, user_id, case_id, _image, _source, _foreign = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        first = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "A"})["id"])
        second = uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "B"})["id"])
        for dossier_id in (first, second):
            made = dossier_service.create_assessment(db, dossier_id=dossier_id, user=user,
                                                     data={"category": "risk", "content": f"About {dossier_id}"})
            dossier_service.delete_assessment(db, dossier_id=dossier_id, assessment_id=uuid.UUID(made["id"]), user=user)
    from fastapi import HTTPException
    # The route functions, called in this thread (the in-memory database is per connection).
    with factory() as db, patch("services.case_service.check_case_access", return_value=(None, None)):
        user = db.get(User, user_id)
        listed = route.list_removed(case_id=case_id, dossier_id=first, db=db, user=user)["items"]
        assert [i["dossier_id"] for i in listed] == [str(first)]
        assert route.restore_removed(case_id=case_id, removed_id=uuid.UUID(listed[0]["id"]), db=db, user=user)["restored_at"]
        with pytest.raises(HTTPException) as again:
            route.restore_removed(case_id=case_id, removed_id=uuid.UUID(listed[0]["id"]), db=db, user=user)
        assert again.value.status_code == 409
        assert route.list_removed(case_id=case_id, dossier_id=first, db=db, user=user)["items"] == []
        with pytest.raises(HTTPException) as other:
            route.restore_removed(case_id=uuid.uuid4(), removed_id=uuid.UUID(listed[0]["id"]), db=db, user=user)
        assert other.value.status_code == 404
    with factory() as db:
        assert db.scalar(select(DossierAssessment).where(DossierAssessment.dossier_id == first)).content == f"About {first}"
