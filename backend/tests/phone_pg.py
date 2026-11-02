"""PostgreSQL helpers for the phone interpretation tests (opt-in).

- ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``: a database at the alembic head with no data. ``fresh_db`` creates a
  throwaway copy of it per test (``CREATE DATABASE ... TEMPLATE``) and drops it afterwards, so the global registry
  starts empty in every test.
- ``LOUPE_TEST_PHONE_PG_URL``: a database holding captured extractions (corpus tests). Tests run inside one
  transaction that is rolled back; nothing is left behind.

Both skip with the reason when unset. No value from a report is read into a test or printed.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest

TEMPLATE_URL = os.getenv("LOUPE_TEST_PHONE_PG_TEMPLATE_URL")
CORPUS_URL = os.getenv("LOUPE_TEST_PHONE_PG_URL")
TEMPLATE_REASON = "Requires LOUPE_TEST_PHONE_PG_TEMPLATE_URL (a PostgreSQL database at the alembic head)"
CORPUS_REASON = "Requires LOUPE_TEST_PHONE_PG_URL (a PostgreSQL database holding captured extractions)"

needs_template = pytest.mark.skipif(not TEMPLATE_URL, reason=TEMPLATE_REASON)
needs_corpus = pytest.mark.skipif(not CORPUS_URL, reason=CORPUS_REASON)


def sa_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _split(url):
    base, name = url.rsplit("/", 1)
    return base, name


@contextmanager
def fresh_engine():
    from sqlalchemy import create_engine, text
    base, template = _split(sa_url(TEMPLATE_URL))
    name = "phone_t_%s" % uuid.uuid4().hex[:12]
    admin = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text('CREATE DATABASE "%s" TEMPLATE "%s"' % (name, template)))
    engine = create_engine(base + "/" + name)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name))
        admin.dispose()


@contextmanager
def corpus_connection():
    from sqlalchemy import create_engine
    engine = create_engine(sa_url(CORPUS_URL))
    conn = engine.connect()
    tx = conn.begin()
    try:
        yield conn
    finally:
        tx.rollback()
        conn.close()
        engine.dispose()


def make_case(conn):
    """A synthetic user and case; returns the case id."""
    from sqlalchemy import text
    uid, cid = uuid.uuid4(), uuid.uuid4()
    conn.execute(text("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) "
                      "VALUES (:u, :e, 'synthetic', 'x', 'user', true, now(), now())"),
                 {"u": uid, "e": "p%s@x.test" % uid.hex[:8]})
    conn.execute(text("INSERT INTO cases (id,title,status,archived,created_by_user_id,owner_user_id,created_at,"
                      "updated_at) VALUES (:c, 'synthetic phone test', 'active', false, :u, :u, now(), now())"),
                 {"c": cid, "u": uid})
    return cid


def make_extraction(conn, case_id, records, *, skeleton=None, label="C77", timestamps=(), capture_state="captured",
                    report_version="7.70", producer_version="7.70.0.1", standing="active", metadata=None):
    """A synthetic captured extraction. ``records``: [(ordinal, parent_ordinal, top_ordinal, body)]; the model
    type is read from the body. ``timestamps``: rows for phone_timestamps (dicts with the 01 columns)."""
    import hashlib
    import json
    from sqlalchemy import text
    ext, cont = uuid.uuid4(), uuid.uuid4()
    h = hashlib.sha256(ext.bytes).hexdigest()
    conn.execute(text(
        "INSERT INTO phone_extraction_containers (id, case_id, container_kind, stored_path, original_name, size_bytes, "
        "sha256, md5, intake_outcome, classification) VALUES (:id, :c, 'folder', 'synthetic', :n, 1, :h, :m, "
        "'phone_report', '{}'::jsonb)"), {"id": cont, "c": case_id, "n": label, "h": h, "m": h[:32]})
    conn.execute(text(
        "INSERT INTO phone_extractions (id, case_id, report_set_sha256, first_container_id, form, capture_state, "
        "standing, capture_code_version, report_version, producer_version, captured_at) VALUES (:id, :c, :h, :ct, "
        "'full', CAST(:cs AS phone_capture_state), CAST(:st AS phone_extraction_standing), 'synthetic', :rv, :pv, "
        "now())"), {"id": ext, "c": case_id, "h": h, "ct": cont, "cs": capture_state, "st": standing,
                    "rv": report_version, "pv": producer_version})
    skel = skeleton if skeleton is not None else ["project", {"reportVersion": report_version}, None, [
        ["metadata", {"section": "Additional Fields"}, None, [
            ["item", {"name": k}, v, None] for k, v in (metadata or {}).items()]],
        ["decodedData", None, None, [["@r", 0, max([r[0] for r in records if r[1] is None] or [0])]]]]]
    conn.execute(text(
        "INSERT INTO phone_extraction_documents (extraction_id, document_index, path, role, size_bytes, sha256, md5, "
        "parse_state, skeleton) VALUES (:e, 0, :p, 'full', 1, :h, :m, 'complete', CAST(:s AS jsonb))"),
        {"e": ext, "p": "%s_synthetic_Report.xml" % label, "h": h, "m": h[:32], "s": json.dumps(skel)})
    for ordinal, parent, top, body in records:
        a = body[1] or {}
        conn.execute(text(
            "INSERT INTO phone_records (extraction_id, document_index, ordinal, parent_ordinal, top_ordinal, depth, "
            "model_type, source_model_id, deleted_state, is_partial, body) VALUES (:e, 0, :o, :p, :t, :d, :mt, :sid, "
            ":ds, false, CAST(:b AS jsonb))"),
            {"e": ext, "o": ordinal, "p": parent, "t": top, "d": 0 if parent is None else 1, "mt": a.get("type"),
             "sid": a.get("id"), "ds": a.get("deleted_state"), "b": json.dumps(body)})
    for ts in timestamps:
        conn.execute(text(
            "INSERT INTO phone_timestamps (extraction_id, document_index, owner_kind, owner_ordinal, body_path, "
            "model_type, field_name, value_type, original_text, formatted_text, instant, local_wall_time, "
            "original_offset_minutes, offset_state, parse_rule) VALUES (:e, 0, 'record', :o, :bp, :mt, :fn, "
            "'TimeStamp', :ot, :ft, :i, :lw, :off, :os, :pr)"),
            dict({"ft": None, "lw": None, "off": None, "pr": "synthetic"}, e=ext, **ts))
    return ext


def model(type_name, fields, **attrs):
    return ["model", dict({"type": type_name, "id": str(uuid.uuid4()), "deleted_state": "Intact",
                           "decoding_confidence": "High"}, **attrs), None, fields]


def fld(name, *values, kind="field"):
    return [kind, {"name": name}, None, [["value", {"type": t}, v, None] for t, v in values] or None]


def refs(name, *ordinals, kind="multiModelField"):
    return [kind, {"name": name}, None, [["@", o] for o in ordinals]]
