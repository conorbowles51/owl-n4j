"""A page-image reading's checks hold no database transaction open; its writes keep their locked transaction.

Live 2026-10-31 15:15-15:24 (pg_stat_activity every 1 s): the page-image process held one transaction open for up
to 133 s per statement, idle in transaction while read_statement_import parsed between its selects, holding the
vacuum horizon of every table. Opt-in PostgreSQL checks (FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.financial import vision_reader
from services.financial.read_only_session import WriteInReadOnlyComparison

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture
def engine():
    admin = create_engine(URL)
    schema = 'vision_txn_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE files (id int PRIMARY KEY, note text)'))
        connection.execute(text("INSERT INTO files VALUES (1, 'held')"))
    try:
        yield engine, admin
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _state(admin, pid):
    with admin.connect() as connection:
        return connection.execute(text('SELECT state FROM pg_stat_activity WHERE pid = :p'), dict(p=pid)).scalar()


@needs_pg
def test_reads_hold_no_transaction_and_the_write_phase_is_one_transaction(engine):
    engine, admin = engine
    with Session(engine) as db:
        vision_reader._reads_outside_transaction(db)
        pid = db.execute(text('SELECT pg_backend_pid()')).scalar()
        first = db.execute(text('SELECT txid_current()')).scalar()
        second = db.execute(text('SELECT txid_current()')).scalar()
        assert first != second, 'each read is its own transaction'
        assert _state(admin, pid) == 'idle', 'nothing is held open between reads'
        vision_reader._write_phase(db)
        db.execute(text('SELECT note FROM files WHERE id = 1 FOR UPDATE'))
        pid = db.execute(text('SELECT pg_backend_pid()')).scalar()
        assert db.execute(text('SELECT txid_current()')).scalar() == db.execute(text('SELECT txid_current()')).scalar()
        assert _state(admin, pid) == 'idle in transaction', 'the lock and the write share one transaction'
        with admin.connect() as other:
            locked = other.execute(text("SELECT count(*) FROM pg_locks WHERE pid = :p AND locktype = 'transactionid'"),
                                   dict(p=pid)).scalar()
        assert locked == 1
        db.execute(text("UPDATE files SET note = 'reading' WHERE id = 1"))
        db.commit()
    with engine.connect() as connection:
        assert connection.execute(text('SELECT note FROM files WHERE id = 1')).scalar() == 'reading'


@needs_pg
def test_read_item_reads_its_statement_without_an_open_transaction(engine, monkeypatch):
    engine, admin = engine
    seen = {}

    class Reading(Session):
        def get(self, entity, ident, **kw):
            seen['autocommit'] = self.connection().connection.driver_connection.autocommit
            return None  # the statement is gone: nothing to read

    record = vision_reader._read_item(lambda: Reading(engine), uuid.uuid4(), lambda path: path)
    assert record['reason'] == 'gone'
    assert seen['autocommit'] is True, 'each of its reads runs in its own transaction'


def test_a_check_that_tries_to_write_is_not_counted_as_a_failed_reading(monkeypatch):
    finished = []
    monkeypatch.setattr(vision_reader, '_finish', lambda *a, **kw: finished.append(a) or {})

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, entity, ident):
            raise WriteInReadOnlyComparison('A read-only comparison tried to write (new 1, changed 0, deleted 0)')

    record = vision_reader._read_item(lambda: Db(), uuid.uuid4(), lambda path: path)
    assert record['reason'] == 'write_refused' and record['status'] == 'skipped'
    assert 'failures' not in record and not finished, 'no failure counted, nothing recorded'
