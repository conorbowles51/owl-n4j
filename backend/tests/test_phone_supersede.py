"""Replace and Retire of a phone report (01 section 10.7, unit 2.3): through the app with a real session on SQLite.
Synthetic rows only. The ledger's PostgreSQL constraints are exercised in test_phone_capture_schema (opt-in)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.activity_event import ActivityEvent
from postgres.models.case import Case
from postgres.models.financial import AdjudicationEvent
from postgres.models.phone_extraction import (PhoneExtraction, PhoneExtractionContainer, PhoneExtractionDocument,
                                              PhoneTimestamp)
from postgres.models.user import User
from routers import phone_extractions
from routers.phone_extractions import router
from routers.users import get_current_db_user
from postgres.session import get_db

TABLES = [User.__table__, Case.__table__, PhoneExtractionContainer.__table__, PhoneExtraction.__table__,
          PhoneExtractionDocument.__table__, PhoneTimestamp.__table__, AdjudicationEvent.__table__,
          ActivityEvent.__table__]


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=TABLES)
    Session = sessionmaker(bind=engine, autoflush=False)
    case_id, other_case, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with Session() as db:
        db.add(User(id=user_id, email="investigator@example.com", name="Investigator", password_hash="x"))
        db.flush()
        for c in (case_id, other_case):
            db.add(Case(id=c, title="Synthetic", created_by_user_id=user_id, owner_user_id=user_id))
        db.commit()
    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_db_user] = lambda: Session().get(User, user_id)
    allowed = []
    with patch.object(phone_extractions, "authorize_case", side_effect=lambda db, c, u, p: allowed.append(p)):
        with TestClient(app) as client:
            yield client, Session, case_id, other_case, allowed
    engine.dispose()


def add_report(Session, case_id, name, *, state="captured", standing="active", started=None):
    with Session() as db:
        container = PhoneExtractionContainer(case_id=case_id, container_kind="folder", stored_path="p/" + name,
                                             original_name=name, size_bytes=1, sha256="a" * 64, md5="b" * 32,
                                             intake_outcome="readable", classification={})
        db.add(container)
        db.flush()
        ext = PhoneExtraction(case_id=case_id, report_set_sha256=uuid.uuid4().hex * 2, first_container_id=container.id,
                              form="folder", capture_state=state, standing=standing, capture_code_version="t",
                              flags={}, record_count=3, file_count=2)
        db.add(ext)
        db.flush()
        if started:
            db.add(PhoneExtractionDocument(extraction_id=ext.id, document_index=0, path="r.xml", role="report",
                                           size_bytes=1, sha256="c" * 64, md5="d" * 32))
            db.flush()
            for i, at in enumerate(started):
                db.add(PhoneTimestamp(extraction_id=ext.id, document_index=0, owner_kind="skeleton", owner_ordinal=0,
                                      body_path="3.%d" % i, field_name=phone_extractions.EXTRACTION_START,
                                      value_type="TimeStamp", original_text="x", instant=at, offset_state="explicit",
                                      parse_rule="iso"))
        db.commit()
        return ext.id


def snapshot(Session, *ids):
    with Session() as db:
        return [(e.standing, e.supersedes_id, e.superseded_reason) for e in (db.get(PhoneExtraction, i) for i in ids)]


def test_replace_retires_the_older_report_records_the_reason_and_keeps_its_records(world):
    client, Session, case_id, _, allowed = world
    older = add_report(Session, case_id, "Older report", started=[datetime(2026, 3, 2, 9, tzinfo=timezone.utc)])
    newer = add_report(Session, case_id, "Newer report")
    r = client.post("/api/phone-extractions/%s/supersede" % newer, json={"previous_id": str(older), "reason": "  Full copy  "})
    assert r.status_code == 200, r.text
    assert ("evidence", "upload") in allowed
    assert snapshot(Session, older, newer) == [("superseded", None, "Full copy"), ("active", older, None)]
    with Session() as db:
        events = db.scalars(select(AdjudicationEvent)).all()
        assert [(e.subject_type, e.subject_id, e.decision, e.reason, e.after["replaced_by"]) for e in events] == [
            ("phone_extraction", older, "supersede_phone_extraction", "Full copy", str(newer))]
        assert [a.action for a in db.scalars(select(ActivityEvent))] == ["phone_extraction_superseded"]
        assert db.get(PhoneExtraction, older).record_count == 3  # nothing deleted
    listed = {row["id"]: row for row in client.get("/api/phone-extractions", params={"case_id": str(case_id)}).json()}
    assert listed[str(older)]["replaced_by_id"] == str(newer)
    assert listed[str(older)]["superseded_by"] == "Investigator"
    assert listed[str(older)]["extracted_from"].startswith("2026-03-02T09:00:00")
    assert listed[str(newer)]["supersedes_id"] == str(older) and listed[str(newer)]["extracted_from"] is None


@pytest.mark.parametrize("reason", ["", "   \n"])
def test_a_blank_reason_is_refused_and_nothing_changes(world, reason):
    client, Session, case_id, _, _ = world
    older, newer = add_report(Session, case_id, "A"), add_report(Session, case_id, "B")
    r = client.post("/api/phone-extractions/%s/supersede" % newer, json={"previous_id": str(older), "reason": reason})
    assert (r.status_code, r.json()["detail"]) == (422, phone_extractions.REASON_REQUIRED)
    assert snapshot(Session, older, newer) == [("active", None, None), ("active", None, None)]


@pytest.mark.parametrize("state", ["capturing", "reconciling", "reconciliation_failed", "failed", "cancelled"])
def test_a_newer_report_not_read_in_full_cannot_replace_and_the_older_stays_active(world, state):
    client, Session, case_id, _, _ = world
    older = add_report(Session, case_id, "A")
    newer = add_report(Session, case_id, "B", state=state, standing="pending")
    r = client.post("/api/phone-extractions/%s/supersede" % newer, json={"previous_id": str(older), "reason": "copy"})
    assert (r.status_code, r.json()["detail"]) == (409, phone_extractions.NOT_READ_IN_FULL)
    assert snapshot(Session, older)[0] == ("active", None, None)
    with Session() as db:
        assert db.scalars(select(AdjudicationEvent)).all() == []


def test_replace_twice_other_cases_and_self_are_refused(world):
    client, Session, case_id, other_case, _ = world
    older, newer, third = (add_report(Session, case_id, n) for n in "ABC")
    elsewhere = add_report(Session, other_case, "D")
    post = lambda new, prev: client.post("/api/phone-extractions/%s/supersede" % new,
                                         json={"previous_id": str(prev), "reason": "copy"})
    assert post(newer, older).status_code == 200
    assert (post(third, older).status_code, post(third, older).json()["detail"]) == (409, phone_extractions.NOT_ACTIVE)
    assert post(newer, newer).json()["detail"] == phone_extractions.SAME_REPORT
    assert post(elsewhere, third).json()["detail"] == phone_extractions.OTHER_CASE
    assert post(uuid.uuid4(), older).status_code == 404
    with Session() as db:
        assert len(db.scalars(select(AdjudicationEvent)).all()) == 1


def test_one_newer_report_can_replace_two_older_ones_and_both_say_so(world):
    client, Session, case_id, _, _ = world
    first, second, newest = (add_report(Session, case_id, n) for n in ("First", "Second", "Newest"))
    for older in (first, second):
        r = client.post("/api/phone-extractions/%s/supersede" % newest, json={"previous_id": str(older), "reason": "x"})
        assert r.status_code == 200, r.text
    listed = {row["id"]: row for row in client.get("/api/phone-extractions", params={"case_id": str(case_id)}).json()}
    assert [listed[str(i)]["replaced_by_id"] for i in (first, second)] == [str(newest), str(newest)]
    assert listed[str(newest)]["standing"] == "active"


def test_a_caller_who_cannot_see_the_case_gets_not_found_and_a_viewer_without_upload_is_refused(world):
    from fastapi import HTTPException
    client, Session, case_id, _, _ = world
    older, newer = add_report(Session, case_id, "A"), add_report(Session, case_id, "B")
    post = lambda: client.post("/api/phone-extractions/%s/supersede" % newer,
                               json={"previous_id": str(older), "reason": "x"})

    def stranger(db, c, u, p):
        raise HTTPException(403, "Not a member")
    with patch.object(phone_extractions, "authorize_case", side_effect=stranger):
        r = post()
    assert (r.status_code, r.json()["detail"]) == (404, phone_extractions.NOT_FOUND)

    def viewer(db, c, u, p):
        if p != ("case", "view"):
            raise HTTPException(403, "No upload permission")
    with patch.object(phone_extractions, "authorize_case", side_effect=viewer):
        r = post()
    assert (r.status_code, r.json()["detail"]) == (403, "No upload permission")
    assert snapshot(Session, older, newer) == [("active", None, None), ("active", None, None)]
