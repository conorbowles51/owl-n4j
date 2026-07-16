from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import uuid

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _postgres_url() -> str:
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    url = url or "postgresql+psycopg://owl_us:owl_pw@localhost:5432/owl_db"
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://") and "+psycopg" not in url:
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


@pytest.fixture(scope="session")
def pg_url() -> str:
    return _postgres_url()


@pytest.fixture(scope="session")
def db_schema(pg_url: str):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    create_engine = sqlalchemy.create_engine
    text = sqlalchemy.text

    if not pg_url.startswith("postgresql"):
        pytest.skip("workspace note durability tests require PostgreSQL")

    connect_args = {"connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2"))}
    admin_engine = create_engine(pg_url, future=True, pool_pre_ping=True, connect_args=connect_args)
    schema = f"test_dkt448_{os.getpid()}_{uuid.uuid4().hex[:8]}"

    try:
        with admin_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        admin_engine.dispose()
        pytest.skip(f"PostgreSQL test database is not reachable: {exc}")

    try:
        yield schema
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture(scope="session")
def pg_engine(pg_url: str, db_schema: str):
    sqlalchemy = pytest.importorskip("sqlalchemy")
    create_engine = sqlalchemy.create_engine

    from postgres.base import Base
    from postgres.models.case import Case
    from postgres.models.case_membership import CaseMembership
    from postgres.models.user import User
    from postgres.models.workspace import WorkspaceNote

    connect_args = {
        "connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2")),
        "options": f"-csearch_path={db_schema},public",
    }
    engine = create_engine(
        pg_url,
        future=True,
        pool_pre_ping=True,
        pool_size=8,
        max_overflow=8,
        connect_args=connect_args,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Case.__table__,
            CaseMembership.__table__,
            WorkspaceNote.__table__,
        ],
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(pg_engine):
    sqlalchemy_orm = pytest.importorskip("sqlalchemy.orm")
    return sqlalchemy_orm.sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)


@pytest.fixture
def background_session_factory(session_factory):
    @contextmanager
    def _background_session():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    return _background_session
