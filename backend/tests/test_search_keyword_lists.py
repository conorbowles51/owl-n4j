"""Saved keyword lists (03 section 11.2; 07 J-6 "Saves", section 14). Opt-in PostgreSQL.

Invented data only: 555 numbers and made-up words.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import text

from services.search import keyword_lists as K
from services.search import search as S
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def msg(instant, sender, recips, body, thread="t"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties, thread=thread,
                direction="outgoing" if sender == OWNER else "incoming")


@contextmanager
def client_for(engine, case_id):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.search import router
    from routers.users import get_current_db_user

    with engine.connect() as c:
        uid, email = c.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                    "WHERE k.id = :c"), {"c": case_id}).one()
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(router)

    def db():
        s = Session()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_db_user] = lambda: User(id=uid, email=email, name="synthetic",
                                                                 global_role=GlobalRole.user)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, _ = phone(c, case, label="C3", events=[
                msg(at(2023, 3, 14, 10), ANA, [OWNER], "the blue van is at the dock"),
                msg(at(2023, 3, 14, 11), OWNER, [ANA], "Blue VAN again, and the dock"),
                msg(at(2023, 3, 15, 9), BEN, [OWNER], "nothing here", thread="u")])
            phone(c, other, label="C9", events=[msg(at(2023, 3, 14, 10), ANA, [OWNER], "blue van elsewhere")])
        yield {"engine": engine, "case": case, "other": other, "ext": str(ext)}


def _save(client, case, name="Vehicles", terms=("blue van", "dock"), **kw):
    r = client.post("/api/search/keyword-lists", json=dict(case_id=str(case), name=name, terms=list(terms), **kw))
    assert r.status_code == 200, r.text
    return r.json()


def test_a_saved_list_is_one_workspace_note_and_runs_on_every_phone_with_exact_totals(world):
    e, case = world["engine"], world["case"]
    with client_for(e, case) as client:
        saved = _save(client, case)
        assert saved["state"] == "not_run" and "Not run yet" in saved["summary"]
        with e.connect() as c:
            notes = c.execute(text("SELECT entry_type, title, tags FROM workspace_entries WHERE case_id = :c"),
                              {"c": case}).fetchall()
        assert [(n[0], n[1], list(n[2])) for n in notes] == [("note", "Keyword list: Vehicles", ["keyword list"])]
        done = K.run_stale(e)
        assert done == {saved["entry_id"]: 4}  # 2 messages hold "blue van" and 2 hold "dock", on the one phone
        got = client.get("/api/search/keyword-lists/%s" % saved["entry_id"], params={"case_id": str(case)}).json()
    assert got["state"] == "current"
    run = got["run"]
    assert [p["extraction_id"] for p in run["phones"]] == [world["ext"]]
    assert run["terms"] == {"blue van": 2, "dock": 2}
    assert run["phones"][0]["terms"]["blue van"]["messages"] == 2
    assert "on 1 phone, 4 matches in all" in got["summary"]
    # the list's total for a phone and term is the search's own total for that phone and term (same fold, S-4)
    with e.connect() as c:
        page = S.group_page(c, case, "blue van", "messages", phones=[world["ext"]])
    assert page["total"] == 2 and len(page["items"]) == 2
    assert all(h["open"]["screen"] == "conversations" and h["open"]["params"]["event"] for h in page["items"])
    # nothing ran again while nothing changed
    assert K.run_stale(e) == {}


def test_a_phone_added_later_is_counted_and_a_phone_still_reading_is_named(world):
    e, case = world["engine"], world["case"]
    with client_for(e, case) as client:
        saved = _save(client, case)
        K.run_stale(e)
        with e.begin() as c:
            late, _ = phone(c, case, label="C4", interpreted=False, events=[
                msg(at(2023, 4, 1, 10), BEN, [OWNER], "dock at noon", thread="w")])
        assert K.run_stale(e) == {saved["entry_id"]: 5}
        got = client.get("/api/search/keyword-lists/%s" % saved["entry_id"], params={"case_id": str(case)}).json()
        assert got["run"]["terms"]["dock"] == 3
        names = [p["message"] for p in got["run"]["not_counted"]]
        assert len(names) == 1 and names[0].startswith("C4 is still being read")
        assert "C4 is still being read" in got["summary"]
        # the phone finishes reading: the list runs again and the phone is no longer named
        with e.begin() as c:
            c.execute(text("UPDATE phone_interpretation_state SET status = 'done', texts_at = now(), projected_at = "
                           "now(), generation = generation + 0 WHERE extraction_id = :e"), {"e": late})
        assert K.run_stale(e) == {saved["entry_id"]: 5}
        got = client.get("/api/search/keyword-lists/%s" % saved["entry_id"], params={"case_id": str(case)}).json()
        assert got["run"]["not_counted"] == [] and got["state"] == "current"


def test_a_list_refuses_short_or_empty_terms_and_writes_nothing(world):
    e, case = world["engine"], world["case"]
    with client_for(e, case) as client:
        r = client.post("/api/search/keyword-lists", json={"case_id": str(case), "name": "x", "terms": ["ab"]})
        assert r.status_code == 400 and "at least 3 letters" in r.json()["detail"]
        r = client.post("/api/search/keyword-lists", json={"case_id": str(case), "name": "x", "terms": ["  "]})
        assert r.status_code == 400
        assert client.get("/api/search/keyword-lists", params={"case_id": str(case)}).json()["total"] == 0
    with e.connect() as c:
        assert c.execute(text("SELECT count(*) FROM workspace_entries WHERE case_id = :c"), {"c": case}).scalar() == 0


def test_a_deleted_note_removes_the_list_and_another_case_never_sees_it(world):
    e, case, other = world["engine"], world["case"], world["other"]
    with client_for(e, case) as client:
        saved = _save(client, case)
        assert client.get("/api/search/keyword-lists/%s" % saved["entry_id"],
                          params={"case_id": str(other)}).status_code in (403, 404)
        with e.begin() as c:
            c.execute(text("UPDATE workspace_entries SET deleted_at = now() WHERE id = :e"), {"e": saved["entry_id"]})
        assert client.get("/api/search/keyword-lists", params={"case_id": str(case)}).json()["total"] == 0


def test_b_a_list_attached_to_a_theory_shows_on_the_theory_with_its_totals(world):
    from postgres.models.user import User
    from services.workspace_entry_service import create_entry
    from sqlalchemy.orm import Session
    e, case = world["engine"], world["case"]
    with client_for(e, case) as client:
        saved = _save(client, case)
        with Session(e) as s:
            uid, email = s.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                        "WHERE k.id = :c"), {"c": case}).one()
            theory = create_entry(s, case_id=case, current_user=User(id=uid, email=email, name="synthetic"),
                                  entry_type="theory", body="The van moved the goods.", title="Van theory")
        r = client.post("/api/search/keyword-lists/%s/theories" % saved["entry_id"],
                        json={"case_id": str(case), "theory_id": theory["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["theories"] == [{"id": theory["id"], "title": "Van theory"}]
        K.run_stale(e)
        on = client.get("/api/search/keyword-lists", params={"case_id": str(case), "theory": theory["id"]}).json()
        assert on["total"] == 1 and on["items"][0]["run"]["total"] == 4
        # a note is not a theory
        r = client.post("/api/search/keyword-lists/%s/theories" % saved["entry_id"],
                        json={"case_id": str(case), "theory_id": saved["entry_id"]})
        assert r.status_code == 400


def test_e_coverage_lists_each_keyword_list_with_its_terms_and_run(world):
    e, case = world["engine"], world["case"]
    with client_for(e, case) as client:
        _save(client, case)
    K.run_stale(e)
    with e.connect() as c:
        cov = K.for_coverage(c, case)
    assert [(x["name"], x["terms"], x["phones"], x["total"]) for x in cov] == [
        ("Vehicles", ["blue van", "dock"], 1, 4)]


def test_c_investigator_terms_read_case_terms_and_keyword_lists(world):
    from sqlalchemy.orm import Session

    from postgres.models.user import User
    from services.pattern_of_life import key_dates
    e, case = world["engine"], world["case"]
    with client_for(e, case) as client:
        _save(client, case, terms=("blue van", "Dock"))
    with Session(e) as s:
        uid, email = s.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                    "WHERE k.id = :c"), {"c": case}).one()
        key_dates.create(s, case, User(id=uid, email=email, name="synthetic"), kind="term", label="Meeting word",
                         term="usual place")
    with e.connect() as c:
        assert K.investigator_terms(c, case) == ["Dock", "blue van", "usual place"]
