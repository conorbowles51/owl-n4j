"""05 section 17.2: a record's source database file and row, by both mechanisms, with the file's state.

Synthetic phone: every value is invented. Needs ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL`` (tests/phone_pg.py)."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template

# record ordinal -> its report id; ordinal 1 is nested inside 0
IDS = {0: "rec-top", 1: "rec-nested", 2: "rec-absent", 3: "rec-mixed", 4: "rec-none", 5: "rec-jump"}
# file ordinal -> (Tags, capture outcome)
FILES = {0: ("Database", "match"), 1: ("Database", "missing"), 2: ("Database", "mismatch"),
         3: ("Database", "empty_placeholder"), 4: ("Database, Application", "match"), 5: ("Image", "match")}


def _records():
    out = []
    for o, rid in IDS.items():
        parent = 0 if o == 1 else None
        out.append((o, parent, 0 if o == 1 else o, model("Chat" if o != 1 else "InstantMessage",
                                                         [fld("Body", ("String", "synthetic"))], id=rid)))
    return out


def _world(c):
    case = make_case(c)
    ext = make_extraction(c, case, _records())
    for o, (tags, outcome) in FILES.items():
        c.execute(text(
            "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, source_file_id, local_path, tags, "
            "outcome, disk_size, body) VALUES (:e, 0, :o, :u, :sid, :lp, :t, :out, 10, CAST(:b AS jsonb))"),
            {"e": ext, "o": o, "u": uuid.uuid4(), "sid": "file-%d" % o, "lp": "files/Database/synthetic-%d.db" % o,
             "t": tags, "out": outcome,
             "b": json.dumps(["file", {"id": "file-%d" % o, "path": "/data/synthetic-%d.db" % o}, None, None])})
    # extraInfo ordinal, its id, and its nodes (node id, table, offset, file ordinal or None)
    infos = [(0, "rec-nested", [("file-0", "messages", "12", 0)]),
             (1, "rec-absent", [("file-1", "sms", "3", 1)]),
             (2, "rec-mixed", [("no-such-file", "calls", "7", None), ("file-2", "calls", "7", 2),
                               ("file-5", None, "0", 5)]),
             (3, "not-a-record", [("file-0", "messages", "99", 0)])]
    for xo, sid, nodes in infos:
        c.execute(text(
            "INSERT INTO phone_extra_infos (extraction_id, document_index, ordinal, source_id, info_type, body) VALUES "
            "(:e, 0, :o, :s, 'model', CAST('[]' AS jsonb))"), {"e": ext, "o": xo, "s": sid})
        for k, (nid, table, offset, fo) in enumerate(nodes):
            c.execute(text(
                "INSERT INTO phone_extra_info_nodes (extraction_id, document_index, extra_ordinal, body_path, node_id, "
                "table_name, node_offset, node_size, file_document_index, file_ordinal, resolution) VALUES (:e, 0, :x, "
                ":bp, :nid, :t, :off, '64', :fd, :fo, :r)"),
                {"e": ext, "x": xo, "bp": "sourceInfo/nodeInfo[%d]" % k, "nid": nid, "t": table, "off": offset,
                 "fd": None if fo is None else 0, "fo": fo, "r": "unresolved" if fo is None else "tagged_file_id"})
    # record 5 names a Database file only through a jump target; record 4 has an image jump target only
    for ro, fo in ((5, 4), (4, 5)):
        c.execute(text(
            "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
            "reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES (:e, 0, :r, 'jumptargets', "
            "'jumptarget', :ref, 0, :f, 'tagged_file', false)"), {"e": ext, "r": ro, "ref": "file-%d" % fo, "f": fo})
    return case, ext


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, ext = _world(c)
        yield engine, case, ext


@needs_template
def test_a_record_with_a_node_to_a_verified_database_resolves_with_table_and_offset(world):
    from services.phone import source_db
    engine, _, ext = world
    with engine.connect() as c:
        s = source_db.record_sources(c, ext, 0, 0)  # the top record: its nested record holds the extraInfo id
    assert [(x["mechanism"], x["state"], x["table_name"], x["offset"], x["size"]) for x in s] == [
        ("extra_info", "verified", "messages", "12", "64")]
    assert s[0]["file"]["is_database"] and s[0]["file"]["original_path"] == "/data/synthetic-0.db"
    row = source_db.source_row(s)
    assert row["available"] and row["row_named"] and row["table_name"] == "messages" and row["offset"] == "12"


@needs_template
def test_a_record_with_a_node_to_an_absent_file_returns_the_reason_absent(world):
    from services.phone import source_db
    engine, _, ext = world
    with engine.connect() as c:
        s = source_db.record_sources(c, ext, 0, 2)
    assert [x["state"] for x in s] == ["absent"]
    row = source_db.source_row(s)
    assert not row["available"] and row["files"][0]["state"] == "absent"
    assert row["reason"] == "The app database this record was read from: is not in the production."


@needs_template
def test_each_state_unresolved_mismatch_and_a_non_database_file_are_listed_never_guessed(world):
    from services.phone import source_db
    engine, _, ext = world
    with engine.connect() as c:
        s = source_db.record_sources(c, ext, 0, 3)
    assert [(x["resolution"], x["state"], x["file"] and x["file"]["is_database"]) for x in s] == [
        ("unresolved", "unresolved", None), ("tagged_file_id", "md5_mismatch", True),
        ("tagged_file_id", "verified", False)]
    assert s[0]["file"] is None and s[0]["node"]["id"] == "no-such-file"
    row = source_db.source_row(s)  # a verified image is not a database: no row to open
    assert not row["available"] and "does not match its MD5" in row["reason"]


def test_zero_bytes_state_and_words():
    assert source_db_state("empty_placeholder") == "zero_bytes"
    assert source_db_state("mismatch") == "md5_mismatch" and source_db_state("missing") == "absent"
    assert source_db_state("match") == "verified" and source_db_state(None) == "not_checked"


def source_db_state(outcome):
    from services.phone import source_db
    return source_db.file_state(outcome)


@needs_template
def test_a_jump_target_to_a_database_file_names_the_file_but_not_the_row(world):
    from services.phone import source_db
    engine, _, ext = world
    with engine.connect() as c:
        s = source_db.record_sources(c, ext, 0, 5)
        none = source_db.record_sources(c, ext, 0, 4)
    assert [(x["mechanism"], x["state"]) for x in s] == [("jump_target", "verified")]
    row = source_db.source_row(s)
    assert row["available"] and not row["row_named"]
    assert row["reason"] == "The report does not say which row this record came from."
    assert none == []  # an image jump target is not a source database
    assert source_db.source_row(none)["reason"] == \
        "The production does not include the app database this record was read from."


@needs_template
def test_the_gate_count_takes_top_level_records_once_by_each_mechanism(world):
    from services.phone import source_db
    engine, _, ext = world
    with engine.connect() as c:
        n = source_db.record_count(c, ext)
    assert n == {"verified_database_files": 2, "records_by_extra_info_id": 1, "records_by_extra_info": 1,
                 "records_by_jump_target": 1, "records": 2}


@pytest.fixture
def api(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user
    from services import evidence_engine_client
    from services.phone import ids, registry, sweep
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case, ext = _world(c)
            owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        Session = sessionmaker(bind=engine)
        app = FastAPI()
        app.include_router(router)

        def db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        def user():
            s = Session()
            try:
                return s.get(User, owner)
            finally:
                s.close()
        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_db_user] = user
        calls = []

        async def fake(case_id, extraction_id, document_index, ordinal, params):
            calls.append((document_index, ordinal, params))
            return {"open_mode": "read-only, immutable", "tables": [], "named_row": {"found": True, "rowid": 12}}
        monkeypatch.setattr(evidence_engine_client, "source_database", fake)
        rec = lambda o: str(ids.record_uid(ext, 0, o))  # noqa: E731
        yield TestClient(app, raise_server_exceptions=True), case, rec, calls


@needs_template
def test_the_route_opens_only_a_verified_database_and_says_why_otherwise(api):
    client, case, rec, calls = api
    r = client.get("/api/phones/records/%s/source-database" % rec(2), params={"case_id": str(case)})
    assert r.status_code == 200 and r.json()["view"] is None and calls == []
    assert r.json()["refused"] == "The report lists this file, but it is not in the production."
    panel = client.get("/api/phones/records/%s" % rec(2), params={"case_id": str(case)}).json()
    assert panel["source_row"]["files"][0]["state"] == "absent" and len(panel["sources"]) == 1
    r = client.get("/api/phones/records/%s/source-database" % rec(0), params={"case_id": str(case)})
    body = r.json()
    assert r.status_code == 200 and body["refused"] is None and body["view"]["named_row"]["rowid"] == 12
    assert calls == [(0, 0, {"table": "messages", "offset": "12", "browse": None, "page": 1})]
    assert body["read_by"].startswith("Read from the app database file") and "not the report's record" in body["read_by"]
    r = client.get("/api/phones/records/%s/source-database" % rec(5), params={"case_id": str(case)})
    assert r.json()["view"]["named_row"] == {"found": False,
                                             "reason": "The report does not say which row this record came from."}
    assert client.get("/api/phones/records/%s/source-database" % rec(4),
                      params={"case_id": str(case)}).status_code == 404
