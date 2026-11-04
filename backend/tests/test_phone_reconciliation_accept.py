"""07 J-1 and 03 section 7.3: a held reconciliation difference on the Phone summary, with Accept the difference
(typed reason, ``accept_phone_reconciliation_difference``, 02 decision 37) and Keep held (nothing written). Synthetic
phones only; the engine's own pass of accepted differences is tested in evidence-engine tests/phone/test_capture.py.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"
pytestmark = needs_template

DIFFS = [{"path": "/project/decodedData/modelType/model", "measure": "elements", "attribute": None, "source": 1204,
          "captured": 1198},
         {"path": "/project/decodedData/modelType/model/field", "measure": "texts", "attribute": None, "source": 9,
          "captured": 8}]


def held(c, ext, diffs=DIFFS):
    rid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_reconciliations (id, extraction_id, document_index, counter_version, result, source_totals, "
        "captured_totals, differences, difference_count, ran_at) VALUES (:i, :e, 0, 'synthetic', 'differs', '{}', '{}', "
        "CAST(:d AS jsonb), :n, clock_timestamp())"), {"i": rid, "e": ext, "d": json.dumps(diffs), "n": len(diffs)})
    return str(rid)


@pytest.fixture
def api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user

    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, _ = phone(c, case, events=[dict(kind="message", instant=at(2023, 3, 14), body="synthetic",
                                                 parties=[(ANA, "sender", False, None, None),
                                                          (OWNER, "recipient", True, None, None)],
                                                 direction="incoming")])
            rid = held(c, ext)
            owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
            email = c.execute(text("SELECT email FROM users WHERE id = :u"), {"u": owner}).scalar()
        Session = sessionmaker(bind=engine)
        app = FastAPI()
        app.include_router(router)

        def db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_db_user] = lambda: User(
            id=owner, email=email, name="synthetic", global_role=GlobalRole.user)
        with TestClient(app, raise_server_exceptions=False) as client:
            yield {"client": client, "case": str(case), "other": str(other), "ext": str(ext), "rid": rid,
                   "engine": engine}


def _profile(api):
    r = api["client"].get(f"/api/phones/{api['ext']}/profile", params={"case_id": api["case"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_held_difference_is_shown_in_words_with_every_difference(api):
    p = _profile(api)
    need = [n for n in p["needs"] if n["kind"] == "reconciliation"]
    assert need and need[0]["words"] == ("Held: the report lists 1,204 elements at decodedData / modelType / model; "
                                         "1,198 were read. 1 more difference.")
    h = p["completeness"]["held"]
    assert [x["difference_count"] for x in h] == [2] and h[0]["shown"] == 2 and h[0]["accepted"] is None
    assert h[0]["differences"][1] == {"where": "modelType / model / field", "measure": "texts", "what": "texts",
                                      "attribute": None, "stated": 9, "read": 8}
    assert p["verdict"]["word"] == "Partly read"


def test_accept_the_difference_records_one_decision_and_the_phone_stays_partly_read(api):
    from services.phone import generic
    c, url = api["client"], f"/api/phones/{api['ext']}/reconciliation/accept"
    with api["engine"].connect() as conn:
        assert generic.held_documents(conn, api["ext"]) == [0]
    assert c.post(url, json={"case_id": api["case"], "reason": "   "}).status_code == 422
    assert c.post(url, json={"case_id": api["other"], "reason": "synthetic"}).status_code in (403, 404, 422)
    r = c.post(url, json={"case_id": api["case"], "reason": "synthetic: the examiner confirmed the cut"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["accepted_documents"] == [{"document_index": 0, "reconciliation_id": api["rid"], "difference_count": 2}]
    # the synthetic phone has no reading job: the decision stands and the person is told why reading did not restart
    assert out["restart"]["state"] == "not_restarted" and "Choose Resume" in out["restart"]["words"]
    with api["engine"].connect() as conn:
        d = conn.execute(text("SELECT before, after, reason, reason_kind FROM adjudications WHERE subject_id::text = :e "
                              "AND decision = 'accept_phone_reconciliation_difference'"), {"e": api["ext"]}).all()
        mc = conn.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'phone_reconciliation' AND "
                               "case_id::text = :c"), {"c": api["case"]}).scalar()
        assert generic.held_documents(conn, api["ext"]) == []
        rows = conn.execute(text("SELECT result FROM phone_reconciliations WHERE extraction_id::text = :e"),
                            {"e": api["ext"]}).scalars().all()
    assert len(d) == 1 and d[0].before == {"accepted_documents": []} and d[0].reason_kind == "typed"
    assert d[0].after["accepted_documents"][0]["reconciliation_id"] == api["rid"] and mc == 1
    assert rows == ["differs"]  # the check's own result is never rewritten
    p = _profile(api)
    assert not [n for n in p["needs"] if n["kind"] == "reconciliation"]
    acc = p["completeness"]["held"][0]["accepted"]
    assert acc["reason"] == "synthetic: the examiner confirmed the cut" and acc["by"]
    assert p["verdict"]["word"] == "Partly read"
    # nothing left to accept: refused, and no second decision
    assert c.post(url, json={"case_id": api["case"], "reason": "again"}).status_code == 409


def test_a_later_reading_with_other_differences_is_held_again(api):
    from services.phone import generic
    c, url = api["client"], f"/api/phones/{api['ext']}/reconciliation/accept"
    assert c.post(url, json={"case_id": api["case"], "reason": "synthetic"}).status_code == 200
    with api["engine"].begin() as conn:
        held(conn, api["ext"], DIFFS)  # the same differences again: still accepted
        assert generic.held_documents(conn, api["ext"]) == []
        held(conn, api["ext"], DIFFS[:1])  # different differences: a new decision is needed
        assert generic.held_documents(conn, api["ext"]) == [0]
    assert [n["kind"] for n in _profile(api)["needs"]].count("reconciliation") == 1


def test_keep_held_writes_nothing(api):
    """Keep held is the absence of a decision: the profile read writes no adjudication and no manual change."""
    _profile(api)
    with api["engine"].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM adjudications WHERE subject_id::text = :e"),
                            {"e": api["ext"]}).scalar() == 0


def test_a_hash_difference_is_shown_as_values_differ_never_as_a_number():
    """Attribute and text values are compared by fingerprint: a held reading whose first difference is a hash says
    the values differ (the profile page must load), and a counted difference is named when there is one."""
    from services.phone import profile
    assert profile._count("00ab12cd34ef5678") is None and profile._count(1204) == 1204 and profile._count(True) is None
    hashed = {"where": "a / b", "measure": "attr_hash", "what": "attribute values", "attribute": "x",
              "stated": profile._count("00ab12cd34ef5678"), "read": profile._count("99ab12cd34ef5678")}
    counted = {"where": "a / c", "measure": "elements", "what": "elements", "attribute": None, "stated": 1204, "read": 1198}
    held = [{"accepted": None, "difference_count": 2, "differences": [hashed, counted]}]
    assert profile.held_sentence(held) == "Held: the report lists 1,204 elements at a / c; 1,198 were read. 1 more difference."
    only = [{"accepted": None, "difference_count": 1, "differences": [hashed]}]
    assert profile.held_sentence(only) == "Held: the attribute values at a / b differ from what the report states."
