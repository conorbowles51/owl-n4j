"""Row-version memos never keep a row this transaction wrote: it can change again before commit under one xmin.

Opt-in PostgreSQL checks (FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL, a disposable schema per test)."""
import os
import uuid

import pytest
from sqlalchemy import Column, Integer, String, create_engine, text
from sqlalchemy.orm import Session, declarative_base

from services.financial import row_versions

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')
Base = declarative_base()


class Note(Base):
    __tablename__ = 'notes'
    id = Column(Integer, primary_key=True)
    body = Column(String, nullable=False)


@pytest.fixture
def engine():
    admin = create_engine(URL)
    schema = 'row_versions_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE notes (id serial PRIMARY KEY, body text NOT NULL)'))
        connection.execute(text("INSERT INTO notes (body) VALUES ('committed')"))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def read(memo, session):
    return [row.body for row in memo.rows(session, [Note.id], [Note.body.label('body')], [Note.id > 0])]


def test_a_row_written_twice_in_one_transaction_is_read_as_it_is_now(engine):
    memo = row_versions.RowValues(Note)
    with Session(engine) as session:
        session.execute(text("UPDATE notes SET body = 'first change'"))
        assert read(memo, session) == ['first change']
        # The same transaction changes it again: the row keeps the same xmin.
        session.execute(text("UPDATE notes SET body = 'second change'"))
        assert read(memo, session) == ['second change']
        session.commit()
    with Session(engine) as session:
        assert read(memo, session) == ['second change']


def test_committed_rows_are_still_reused(engine):
    memo = row_versions.RowValues(Note)
    with Session(engine) as session:
        assert read(memo, session) == ['committed']
        session.execute(text("INSERT INTO notes (body) VALUES ('mine')"))  # this transaction now has an id
        assert sorted(read(memo, session)) == ['committed', 'mine']
        assert len(memo._values) == 1, "only the committed row is kept; this transaction's own row is not"


def test_the_floor(engine):
    with Session(engine) as session:
        assert row_versions.own_write_floor(session) is None
        session.execute(text("UPDATE notes SET body = body"))
        floor = row_versions.own_write_floor(session)
        own = session.execute(text('SELECT xmin::text FROM notes')).scalar()
        assert floor == int(own) and not row_versions.memoisable(own, floor)
        assert row_versions.memoisable(str(floor - 1), floor) and not row_versions.memoisable('5', 0)
