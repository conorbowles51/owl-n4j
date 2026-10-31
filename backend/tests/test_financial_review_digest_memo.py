"""The statement register's duplicate checks hash each period's saved review once per computation, and reuse it
across computations only while its file's PostgreSQL row version is unchanged and final.

The PostgreSQL tests need FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL (a local test connection); each runs in a
throwaway schema.
"""
import os
import uuid
from collections import defaultdict
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.financial import pending_duplicate_projection as projection

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture
def hashed(monkeypatch):
    calls = []
    original = projection._digest

    def counting(value):
        calls.append(value)
        return original(value)
    monkeypatch.setattr(projection, '_digest', counting)
    projection._REVIEW_DIGESTS.clear()
    yield calls
    projection._REVIEW_DIGESTS.clear()


def _file(review):
    return SimpleNamespace(metadata_={'financial_review_progress': {'statement-1': review}})


def _context(files, versions):
    return dict(files=files, guards={key: 'reading' for key in files}, drafts=defaultdict(list), sources={},
                review_digests={}, file_versions=versions)


def test_each_period_review_is_hashed_once_per_computation(hashed):
    context = _context({'file-1': _file({'rows': [1, 2, 3]})}, {})
    first = projection._period_guard(context, 'file-1', 'statement-1')
    again = projection._period_guard(context, 'file-1', 'statement-1')
    assert first == again
    assert hashed == [{'rows': [1, 2, 3]}]


@pytest.fixture
def engine():
    assert URL.startswith('postgresql'), 'This test requires PostgreSQL'
    admin = create_engine(URL)
    schema = 'review_digest_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE evidence_files (id uuid PRIMARY KEY, metadata jsonb)'))
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _add(engine):
    identifier = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(text('INSERT INTO evidence_files (id, metadata) VALUES (:id, CAST(:m AS jsonb))'),
                           dict(id=identifier, m='{}'))
    return str(identifier)


def _computation(engine, files, isolation='REPEATABLE READ'):
    """One read-only computation: the period's guard in its own transaction at this isolation level."""
    with Session(engine) as session:
        session.connection(execution_options={'isolation_level': isolation})
        context = _context(files, projection._file_versions(session, files))
        return context, projection._period_guard(context, next(iter(files)), 'statement-1')['shared_review']


@needs_pg
def test_a_review_is_reused_across_computations_until_its_file_row_changes(engine, hashed):
    identifier = _add(engine)
    files = {identifier: _file({'rows': [1]})}
    context, first = _computation(engine, files)
    assert context['file_versions'] and len(hashed) == 1
    _, again = _computation(engine, files)
    assert again == first and len(hashed) == 1  # same row version: not hashed again
    with engine.begin() as connection:
        connection.execute(text("UPDATE evidence_files SET metadata = '{\"changed\": true}' WHERE id = :id"),
                           dict(id=identifier))
    files = {identifier: _file({'rows': [1, 2]})}
    _, changed = _computation(engine, files)
    assert len(hashed) == 2 and changed != first  # a new row version is hashed again


@needs_pg
def test_no_reuse_across_computations_outside_one_snapshot(engine, hashed):
    identifier = _add(engine)
    files = {identifier: _file({'rows': [1]})}
    context, _ = _computation(engine, files, isolation='READ COMMITTED')
    assert context['file_versions'] == {}
    _computation(engine, files, isolation='READ COMMITTED')
    assert len(hashed) == 2


@needs_pg
def test_a_row_this_transaction_wrote_is_never_reused(engine, hashed):
    identifier = _add(engine)
    files = {identifier: _file({'rows': [1]})}
    with Session(engine) as session:
        session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        session.execute(text("UPDATE evidence_files SET metadata = '{}' WHERE id = :id"), dict(id=identifier))
        assert projection._file_versions(session, files) == {}
        session.rollback()
