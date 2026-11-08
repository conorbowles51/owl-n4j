"""The Phone summary's change stamp (03 section 7.3): ``profile.change_stamp`` moves whenever ``profile`` could
answer differently, and the summary route answers 304 to a matching ``If-None-Match`` so a poller pays for the full
build only when something changed. Synthetic data only."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def msg(instant):
    return dict(kind="message", instant=instant, body="hello", direction="incoming", thread="t",
                parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, events=[msg(at(2023, 3, 13, 15)), msg(at(2023, 3, 14, 15))])
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": case, "ext": ext, "user": user}


def stamp(world):
    from services.phone import profile
    with world["engine"].connect() as c:
        return profile.change_stamp(c, str(world["case"]), world["ext"])


def test_the_stamp_is_stable_while_nothing_changes(world):
    assert stamp(world) == stamp(world)


def test_a_phone_of_another_case_raises_not_found(world):
    from services.phone import profile
    with world["engine"].connect() as c:
        with pytest.raises(profile.NotFound):
            profile.change_stamp(c, str(uuid.uuid4()), world["ext"])


def test_each_kind_of_change_moves_the_stamp(world):
    """One write per table the summary reads outside the phone's own generation; each must move the stamp. A new
    source of the summary added without a stamp read shows up here as the change kind that no longer moves it."""
    person, entry = uuid.uuid4(), uuid.uuid4()
    changes = (
        ("a decision (owner, zone, confirmation, acceptance, correction)",
         "INSERT INTO adjudications (id, case_id, subject_type, subject_id, subject_sequence, decision, reason, "
         "actor_name, actor_email, created_at) VALUES (:id, :c, 'phone_record', :id2, 1, 'confirm_phone_reading', "
         "'synthetic', 'Synthetic', 'synthetic@x.test', now())"),
        ("a person added or renamed",
         "INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, status, "
         "needs_link_review, graph_entity_deleted, created_at, updated_at) VALUES (:person, :c, 'person', "
         "'Synthetic Person', '[]', 'unlinked', 'active', false, false, now(), now())"),
        ("a workspace link to phone material",
         "INSERT INTO workspace_entries (id, case_id, entry_type, title, body, tags, review_state, version, "
         "migration_metadata, needs_migration_review, created_at, updated_at) VALUES (:entry, :c, 'finding', 't', "
         "'b', '[]', 'accepted', 1, '{}', false, now(), now()); "
         "INSERT INTO workspace_entry_links (id, entry_id, case_id, target_type, target_id, target_label, "
         "relationship, source_anchor, metadata, created_at, updated_at) VALUES (:id, :entry, :c, 'phone_record', "
         ":id2, 'l', 'supports', '{}', '{}', now(), now())"),
        ("a dossier link to phone material",
         "INSERT INTO dossier_links (id, dossier_id, case_id, target_type, target_id, source_anchor, created_at, "
         "updated_at) VALUES (:id, :person, :c, 'phone_record', :id2, '{}', now(), now())"),
        ("an identity's shown value",
         "UPDATE phone_identities SET updated_at = now() + interval '1 second' WHERE case_id = :c"),
        ("the case time zone setting",
         "INSERT INTO case_display_settings (case_id, time_zone, updated_by, updated_at) SELECT :c, 'Europe/Dublin', "
         "owner_user_id, now() FROM cases WHERE id = :c "
         "ON CONFLICT (case_id) DO UPDATE SET time_zone = 'Europe/Dublin', updated_at = now()"),
        ("a reconciliation run",
         "INSERT INTO phone_reconciliations (id, extraction_id, document_index, ran_at, counter_version, result, "
         "source_totals, captured_totals, differences, difference_count) VALUES (:id, :e, 0, now(), 1, 'exact', "
         "'{}', '{}', '[]', 0)"),
        ("a re-reading",
         "UPDATE phone_interpretation_state SET interpreted_at = now() + interval '1 second' "
         "WHERE extraction_id = :e"),
    )
    seen = {stamp(world)}
    for words, sql in changes:
        with world["engine"].begin() as c:
            for one in sql.split("; "):
                done = c.execute(text(one), {"c": str(world["case"]), "e": world["ext"], "person": person,
                                             "entry": entry, "id": str(uuid.uuid4()), "id2": str(uuid.uuid4())})
            assert done.rowcount != 0, "the write for %r touched no row" % words
        after = stamp(world)
        assert after not in seen, "the stamp did not move for %s" % words
        seen.add(after)


def test_the_route_answers_304_while_nothing_changes_and_200_after_a_change(world, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import routers.phones as phones_router
    from postgres.session import get_db
    from routers.users import get_current_db_user
    from sqlalchemy.orm import Session

    app = FastAPI()
    app.include_router(phones_router.router)

    class _User:
        id = world["user"]
        is_super_admin = True

    def _db():
        with Session(world["engine"]) as s:
            yield s

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_db_user] = lambda: _User()
    monkeypatch.setattr(phones_router, "authorize_case", lambda *a, **k: None)
    monkeypatch.setattr(phones_router, "_PROFILE_CACHE", {})
    client = TestClient(app)
    url = "/api/phones/%s/profile?case_id=%s" % (world["ext"], world["case"])

    first = client.get(url)
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert etag and first.headers["cache-control"] == "private, no-cache"

    again = client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.headers["etag"] == etag

    with world["engine"].begin() as c:
        c.execute(text("INSERT INTO adjudications (id, case_id, subject_type, subject_id, subject_sequence, "
                       "decision, reason, actor_name, actor_email, created_at) VALUES (:id, :c, 'phone_record', "
                       ":id2, 1, 'confirm_phone_reading', 'synthetic', 'Synthetic', 'synthetic@x.test', now())"),
                  {"id": str(uuid.uuid4()), "id2": str(uuid.uuid4()), "c": str(world["case"])})
    changed = client.get(url, headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag
    assert changed.json()["verdict"]


def test_a_cached_body_equals_a_fresh_build(world):
    """The route's per-process cache serves the same answer the service builds."""
    from services.phone import profile
    with world["engine"].connect() as c:
        a = profile.profile(c, str(world["case"]), world["ext"])
        b = profile.profile(c, str(world["case"]), world["ext"])
    assert a == b
