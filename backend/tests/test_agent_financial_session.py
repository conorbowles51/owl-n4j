"""Agent SQL reads use one read-only snapshot, without changing writer sessions.

PostgreSQL checks are opt-in and use only a disposable loopback schema. They
never read DATABASE_URL or connect to the application's configured database.
"""
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from services.agent.tools import _financial_session


@pytest.fixture
def postgres_snapshot(monkeypatch):
    if os.getenv("LOUPE_TEST_LOCAL_POSTGRES") != "1":
        pytest.skip("Requires isolated local PostgreSQL")
    url = make_url(os.environ["LOUPE_TEST_LOCAL_POSTGRES_URL"])
    assert (url.host, url.port, url.database) == ("127.0.0.1", 55434, "loupe_local")
    schema = "agent_snapshot_" + uuid4().hex
    admin = create_engine(url, connect_args={"connect_timeout": 2})
    options = {"connect_timeout": 2, "options": f"-csearch_path={schema} -cstatement_timeout=5000"}
    # One pooled read connection makes the post-call reset assertion exercise
    # the exact connection that previously carried the agent's read snapshot.
    engine = create_engine(url, connect_args=options, pool_size=1, max_overflow=0)
    writer = create_engine(url, connect_args=options, pool_size=1, max_overflow=0)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr("postgres.session._get_session_local", lambda: sessions)
    try:
        with admin.begin() as connection:
            assert connection.scalar(text("SELECT current_database()")) == "loupe_local"
            connection.execute(text("CREATE SCHEMA " + schema))
        with writer.begin() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
            connection.execute(text("CREATE TABLE saved_amount (id integer PRIMARY KEY, amount bigint NOT NULL)"))
            connection.execute(text("INSERT INTO saved_amount VALUES (1, 100)"))
        yield engine, writer, sessions
    finally:
        engine.dispose()
        writer.dispose()
        with admin.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS " + schema + " CASCADE"))
        admin.dispose()


def test_postgres_one_call_keeps_snapshot_and_next_call_sees_committed_correction(postgres_snapshot):
    engine, writer, sessions = postgres_snapshot
    with _financial_session() as reader:
        assert reader.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert reader.scalar(text("SHOW transaction_read_only")) == "on"
        assert reader.scalar(text("SELECT amount FROM saved_amount WHERE id = 1")) == 100
        with writer.begin() as editor:
            editor.execute(text("UPDATE saved_amount SET amount = 250 WHERE id = 1"))
        # A tool's labels, rows and aggregates cannot mix before/after values.
        assert reader.scalar(text("SELECT sum(amount) FROM saved_amount")) == 100
    with _financial_session() as reader:
        assert reader.scalar(text("SELECT sum(amount) FROM saved_amount")) == 250
    # Closing either tool call returns ordinary writable isolation to the pool.
    with sessions.begin() as editor:
        assert editor.scalar(text("SHOW transaction_read_only")) == "off"
        assert editor.scalar(text("SHOW transaction_isolation")) == "read committed"
        editor.execute(text("UPDATE saved_amount SET amount = 300 WHERE id = 1"))
    with engine.connect() as reader:
        assert reader.scalar(text("SELECT amount FROM saved_amount WHERE id = 1")) == 300


def test_postgres_agent_write_is_denied_and_failed_transaction_is_released(postgres_snapshot):
    _, _, sessions = postgres_snapshot
    with pytest.raises(DBAPIError) as error:
        with _financial_session() as reader:
            reader.execute(text("UPDATE saved_amount SET amount = 999 WHERE id = 1"))
    assert (getattr(error.value.orig, "sqlstate", None) or getattr(error.value.orig, "pgcode", None)) == "25006"
    with sessions.begin() as editor:
        assert editor.scalar(text("SELECT amount FROM saved_amount WHERE id = 1")) == 100
        assert editor.scalar(text("SHOW transaction_read_only")) == "off"
        editor.execute(text("UPDATE saved_amount SET amount = 200 WHERE id = 1"))
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        with _financial_session() as reader:
            assert reader.scalar(text("SELECT amount FROM saved_amount WHERE id = 1")) == 200
            raise RuntimeError("synthetic interruption")
    with _financial_session() as reader:
        assert reader.scalar(text("SELECT amount FROM saved_amount WHERE id = 1")) == 200


def test_sqlite_session_remains_usable_without_postgres_configuration(monkeypatch):
    engine = create_engine("sqlite://")
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr("postgres.session._get_session_local", lambda: sessions)
    try:
        with _financial_session() as reader:
            assert reader.scalar(text("SELECT 42")) == 42
    finally:
        engine.dispose()
