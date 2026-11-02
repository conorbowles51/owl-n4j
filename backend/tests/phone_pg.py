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
