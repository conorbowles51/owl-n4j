"""Dossier links: append, remove and replace (07 section 6.4 item 2; tests CO-2 API and CO-3)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres import link_types
from postgres.base import Base
from postgres.models.activity_event import ActivityEvent
from postgres.models.case import Case
from postgres.models.case_profile import CaseProfile
from postgres.models.collection_membership import CollectionMembership
from postgres.models.dossier import DossierLink
from postgres.models.user import User
from postgres.models.workspace_entry import WorkspaceEntry
from services import dossier_service

from tests.test_dossier_service import TABLES as DOSSIER_TABLES

TABLES = list(dict.fromkeys(DOSSIER_TABLES + [ActivityEvent.__table__, CollectionMembership.__table__]))


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    owner, other, case_id, dossier_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entries = [uuid.uuid4() for _ in range(3)]
    with factory() as db:
        db.add_all([User(id=owner, email="owner@example.test", name="Owner", password_hash="x"),
                    User(id=other, email="other@example.test", name="Other", password_hash="x")])
        db.flush()
        db.add(Case(id=case_id, title="Case", created_by_user_id=owner, owner_user_id=owner))
        db.flush()
        db.add(CaseProfile(id=dossier_id, case_id=case_id, display_name="Subject", profile_type="person",
                           created_by_user_id=owner, updated_by_user_id=owner))
        for entry_id in entries:
            db.add(WorkspaceEntry(id=entry_id, case_id=case_id, entry_type="note", body="synthetic",
                                  author_user_id=owner))
        db.commit()
    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver(
        "phone_record",
        lambda db, case, target: link_types.PhoneTarget(label=None, mapping_versions={"sender": "m1"})
        if case == case_id else None,
    )
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None):
        yield factory, owner, other, case_id, dossier_id, entries
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)
    engine.dispose()


def _entry_links(entries):
    return [{"target_type": "entry", "target_id": str(value)} for value in entries]


def _events(db, action):
    return [row.details for row in db.scalars(select(ActivityEvent).where(ActivityEvent.action == action)).all()]


def test_add_is_append_only_and_idempotent_with_counts_and_an_event(world):
    factory, owner, _, _, dossier_id, entries = world
    with factory() as db:
        user = db.get(User, owner)
        first = dossier_service.add_links(db, dossier_id=dossier_id, user=user, links=_entry_links(entries[:2]),
                                          origin="Added from Conversations")
        assert (first["added"], first["skipped"], first["total_links"]) == (2, 0, 2)
        second = dossier_service.add_links(db, dossier_id=dossier_id, user=user, links=_entry_links(entries))
        assert (second["added"], second["skipped"], second["total_links"]) == (1, 2, 3)
        events = _events(db, "dossier_links_added")
        assert [(event["added"], event["skipped"]) for event in events] == [(2, 0), (1, 2)]
        assert events[0]["origin"] == "Added from Conversations"


def test_bulk_add_of_12345_in_parts_reports_every_add_and_clips_nothing(world):
    """CO-2 (API): 'Added 12,342; 3 were already there'."""
    factory, owner, _, case_id, dossier_id, _ = world
    links = [{"target_type": "phone_record", "target_id": f"rec-{n}"} for n in range(12345)]
    with factory() as db:
        user = db.get(User, owner)
        dossier_service.add_links(db, dossier_id=dossier_id, user=user, links=[links[10], links[5000], links[12344]])
        added = skipped = 0
        for start in range(0, len(links), dossier_service.LINKS_ADD_LIMIT):
            result = dossier_service.add_links(
                db, dossier_id=dossier_id, user=user, links=links[start:start + dossier_service.LINKS_ADD_LIMIT])
            added += result["added"]
            skipped += result["skipped"]
        assert (added, skipped) == (12342, 3)
        assert result["total_links"] == 12345
        stored = db.scalars(select(DossierLink).where(DossierLink.target_type == "phone_record")).all()
        assert len(stored) == 12345
        assert all(row.source_anchor["mapping_versions"] == {"sender": "m1"} for row in stored)


def test_more_than_the_limit_in_one_request_is_refused_and_nothing_is_added(world):
    factory, owner, _, _, dossier_id, _ = world
    links = [{"target_type": "phone_record", "target_id": f"rec-{n}"} for n in range(dossier_service.LINKS_ADD_LIMIT + 1)]
    with factory() as db:
        with pytest.raises(ValueError, match="Send them in parts; nothing was added"):
            dossier_service.add_links(db, dossier_id=dossier_id, user=db.get(User, owner), links=links)
        assert db.scalar(select(DossierLink.id)) is None


def test_remove_one_link_writes_an_event_and_leaves_the_rest(world):
    factory, owner, _, _, dossier_id, entries = world
    with factory() as db:
        user = db.get(User, owner)
        dossier_service.add_links(db, dossier_id=dossier_id, user=user, links=_entry_links(entries))
        link = db.scalar(select(DossierLink).where(DossierLink.target_id == str(entries[1])))
        assert dossier_service.remove_link(db, dossier_id=dossier_id, link_id=link.id, user=user)["removed"] == 1
        assert sorted(db.scalars(select(DossierLink.target_id)).all()) == sorted(str(e) for e in (entries[0], entries[2]))
        assert _events(db, "dossier_link_removed")[0]["link_id"] == str(link.id)
        with pytest.raises(dossier_service.DossierNotFound):
            dossier_service.remove_link(db, dossier_id=dossier_id, link_id=link.id, user=user)


def test_adder_and_time_survive_another_person_replacing_the_links(world):
    """CO-3."""
    factory, owner, other, _, dossier_id, entries = world
    with factory() as db:
        dossier_service.add_links(db, dossier_id=dossier_id, user=db.get(User, owner),
                                  links=_entry_links(entries[:1]) + [{"target_type": "phone_record", "target_id": "rec-1"}])
        before = {row.target_id: (row.id, row.created_by_user_id, row.created_at, dict(row.source_anchor))
                  for row in db.scalars(select(DossierLink)).all()}
    with factory() as db:
        dossier_service.replace_links(db, dossier_id=dossier_id, user=db.get(User, other), links=[
            {"target_type": "entry", "target_id": str(entries[0]), "relationship_type": "supports"},
            {"target_type": "phone_record", "target_id": "rec-1", "source_anchor": {"note": "edited"}},
            {"target_type": "entry", "target_id": str(entries[1])},
        ])
        rows = {row.target_id: row for row in db.scalars(select(DossierLink)).all()}
        for target_id, (link_id, adder, added_at, _) in before.items():
            assert (rows[target_id].id, rows[target_id].created_by_user_id, rows[target_id].created_at) == (link_id, adder, added_at)
        assert rows[str(entries[0])].relationship_type == "supports"
        assert rows["rec-1"].source_anchor == {"note": "edited", "mapping_versions": {"sender": "m1"}}
        assert rows[str(entries[1])].created_by_user_id == other
        assert _events(db, "dossier_links_replaced") == [{"dossier_id": str(dossier_id), "added": 1, "kept": 2, "removed": 0}]


def test_routes_add_and_delete(world):
    from postgres.session import get_db
    from routers import dossiers
    from routers.users import get_current_db_user

    factory, owner, _, _, dossier_id, entries = world
    app = FastAPI()
    app.include_router(dossiers.router)

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_db_user] = lambda: factory().get(User, owner)
    client = TestClient(app)
    response = client.post(f"/api/dossiers/{dossier_id}/links:add", json={"links": _entry_links(entries[:2])})
    assert response.status_code == 200, response.text
    assert (response.json()["added"], response.json()["skipped"]) == (2, 0)
    again = client.post(f"/api/dossiers/{dossier_id}/links:add", json={"links": _entry_links(entries[:2])})
    assert (again.json()["added"], again.json()["skipped"]) == (0, 2)
    refused = client.post(f"/api/dossiers/{dossier_id}/links:add",
                          json={"links": [{"target_type": "phone_thread", "target_id": "t1"}]})
    assert refused.status_code == 400
    assert refused.json()["detail"] == link_types.PHONE_TYPE_UNAVAILABLE_MESSAGE.format(target_type="phone_thread")
    link_id = response.json()["added_link_ids"][0]
    assert client.delete(f"/api/dossiers/{dossier_id}/links/{link_id}").status_code == 200
    assert client.delete(f"/api/dossiers/{dossier_id}/links/{link_id}").status_code == 404


def test_route_refuses_more_than_the_limit_with_413_before_reading_the_dossier_and_takes_a_null_anchor(world):
    """The kit's Add to... (journey CO-kit) sends parts of 5,000; one more is refused, never cut."""
    from postgres.session import get_db
    from routers import dossiers
    from routers.users import get_current_db_user

    factory, owner, _, _, dossier_id, entries = world
    app = FastAPI()
    app.include_router(dossiers.router)

    def db_dependency():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = db_dependency
    app.dependency_overrides[get_current_db_user] = lambda: factory().get(User, owner)
    client = TestClient(app)
    over = [{"target_type": "phone_record", "target_id": f"x{n}", "source_anchor": None}
            for n in range(dossier_service.LINKS_ADD_LIMIT + 1)]
    for target in (dossier_id, uuid.uuid4()):  # an unknown dossier gets the same refusal: nothing is read
        refused = client.post(f"/api/dossiers/{target}/links:add", json={"links": over, "origin": "test"})
        assert refused.status_code == 413, refused.text
        assert refused.json()["detail"] == "5,001 links were sent; one request takes at most 5,000. Send them in parts; nothing was added."
    links = [{**link, "source_anchor": None} for link in _entry_links(entries[:1])]
    added = client.post(f"/api/dossiers/{dossier_id}/links:add", json={"links": links})
    assert added.status_code == 200 and added.json()["added"] == 1, added.text
