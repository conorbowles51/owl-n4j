"""Opt-in PostgreSQL checks for compute-once Financial views; every test uses a new, disposable schema.

Set FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL to a local test PostgreSQL connection. No existing application
tables are read or changed.
"""
import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.financial import view_cache

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture
def engine():
    assert URL.startswith('postgresql'), 'This test requires PostgreSQL'
    admin = create_engine(URL)
    schema = 'view_cache_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE payments (id serial PRIMARY KEY, case_id uuid NOT NULL, amount int NOT NULL)'))
        connection.execute(text('CREATE TABLE labels (id serial PRIMARY KEY, name text NOT NULL)'))
        connection.execute(text("INSERT INTO labels (name) VALUES ('rent')"))
    view_cache.clear()
    view_cache._tables_cache.clear()
    try:
        yield engine
    finally:
        view_cache.clear()
        view_cache._tables_cache.clear()
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def write(engine, sql, **params):
    """A commit from outside the request, as another person or an import would make it."""
    with engine.begin() as connection:
        connection.execute(text(sql), params)


class Counter:
    def __init__(self):
        self.calls = 0


def payments_view(counter, with_labels=False):
    @view_cache.cached_view('payments')
    def handler(case_id, db, minimum=0):
        counter.calls += 1
        total = db.execute(text('SELECT coalesce(sum(amount), 0) FROM payments WHERE case_id = :c AND amount >= :m'),
                           dict(c=case_id, m=minimum)).scalar()
        result = dict(total=int(total))
        if with_labels:
            result['labels'] = [name for (name,) in db.execute(text('SELECT name FROM labels ORDER BY id'))]
        return result
    return handler


def call(engine, handler, case_id, **params):
    with Session(engine) as db:
        db.execute(text('SELECT 1'))  # the access check reads first, in its own transaction
        return handler(case_id=case_id, db=db, **params)


def test_unchanged_case_is_served_without_recomputing(engine):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5), (:c, 7)', c=case)
    view = payments_view(counter)
    first, second = call(engine, view, case), call(engine, view, case)
    assert first.body == second.body == b'{"total":12}'
    assert counter.calls == 1
    assert call(engine, view, case, minimum=6).body == b'{"total":7}'
    assert counter.calls == 2, 'other parameters are a different view'


@pytest.mark.parametrize('change', [
    'INSERT INTO payments (case_id, amount) VALUES (:c, 1)',
    'UPDATE payments SET amount = amount + 1 WHERE case_id = :c AND amount = 5',
    'UPDATE payments SET amount = amount WHERE case_id = :c AND amount = 5',
    'DELETE FROM payments WHERE case_id = :c AND amount = 5',
])
def test_any_write_to_the_case_recomputes(engine, change):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5), (:c, 7)', c=case)
    view = payments_view(counter)
    call(engine, view, case)
    write(engine, change, c=case)
    with engine.connect() as connection:
        expected = connection.execute(text('SELECT coalesce(sum(amount), 0) FROM payments WHERE case_id = :c'), dict(c=case)).scalar()
    assert call(engine, view, case).body == ('{"total":%d}' % expected).encode()
    assert counter.calls == 2


def test_another_cases_write_does_not_recompute(engine):
    case, other, counter = uuid.uuid4(), uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    view = payments_view(counter)
    call(engine, view, case)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 9)', c=other)
    assert call(engine, view, case).body == b'{"total":5}'
    assert counter.calls == 1


def test_a_table_without_case_id_is_checked_whole(engine):
    case, counter = uuid.uuid4(), Counter()
    view = payments_view(counter, with_labels=True)
    assert call(engine, view, case).body == b'{"total":0,"labels":["rent"]}'
    write(engine, "INSERT INTO labels (name) VALUES ('food')")
    assert call(engine, view, case).body == b'{"total":0,"labels":["rent","food"]}'
    assert counter.calls == 2
    view_cache.MAX_UNSCOPED_BYTES, saved = -1, view_cache.MAX_UNSCOPED_BYTES
    try:
        call(engine, view, case)
        call(engine, view, case)
        assert counter.calls == 4, 'a large table without case_id is not checked, so the view is not kept'
    finally:
        view_cache.MAX_UNSCOPED_BYTES = saved


def test_every_connection_in_the_view_reads_one_snapshot(engine):
    """A commit landing while the view runs is neither half-seen nor kept as current."""
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    seen = []

    @view_cache.cached_view('two-connections')
    def handler(case_id, db):
        counter.calls += 1
        seen.append(db.execute(text('SELECT sum(amount) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar())
        # Another person's commit, from a thread outside this request.
        worker = threading.Thread(target=write, args=(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 100)'), kwargs=dict(c=case_id))
        worker.start(); worker.join()
        with engine.connect() as separate:  # a view that opens its own connection, as ledger exports do
            seen.append(separate.execute(text('SELECT sum(amount) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar())
        return dict(total=int(seen[-1]))

    assert call(engine, handler, case).body == b'{"total":5}'
    assert seen == [5, 5]
    assert call(engine, handler, case).body == b'{"total":105}', 'the stored view described the earlier state'
    assert counter.calls == 2


def test_errors_and_non_json_responses_are_not_kept(engine):
    from fastapi import HTTPException
    from fastapi.responses import PlainTextResponse
    case, counter = uuid.uuid4(), Counter()

    @view_cache.cached_view('failing')
    def failing(case_id, db):
        counter.calls += 1
        db.execute(text('SELECT count(*) FROM payments'))
        raise HTTPException(status_code=422, detail='no')

    @view_cache.cached_view('text')
    def plain(case_id, db):
        counter.calls += 1
        db.execute(text('SELECT count(*) FROM payments'))
        return PlainTextResponse('x')

    for handler in (failing, failing):
        with pytest.raises(HTTPException):
            call(engine, handler, case)
    call(engine, plain, case); call(engine, plain, case)
    assert counter.calls == 4

    @view_cache.cached_view('own-response')
    def own(case_id, db):
        from fastapi.responses import JSONResponse
        counter.calls += 1
        db.execute(text('SELECT count(*) FROM payments'))
        return JSONResponse(content={'a': 1}, headers={'X-Loupe-Case-Id': str(case_id)})

    assert call(engine, own, case).headers['x-loupe-case-id'] == str(case)
    assert call(engine, own, case).headers['x-loupe-case-id'] == str(case)
    assert counter.calls == 6, "a handler's own response, with its own headers, is not kept"


def test_views_are_read_only(engine):
    case = uuid.uuid4()

    @view_cache.cached_view('writer')
    def writer(case_id, db):
        db.execute(text('INSERT INTO payments (case_id, amount) VALUES (:c, 1)'), dict(c=case_id))
        return {}

    with pytest.raises(Exception, match='read-only'):
        call(engine, writer, case)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM payments')).scalar() == 0


def test_the_same_bytes_as_without_the_cache(engine):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    case = uuid.uuid4()
    payload = dict(name='Café “quoted”', amount='12', items=[1, None, 2.5], nested={'b': 1, 'a': [True]})

    @view_cache.cached_view('bytes')
    def handler(case_id, db):
        db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id))
        return payload

    expected = JSONResponse(content=jsonable_encoder(payload))
    for _ in range(2):
        response = call(engine, handler, case)
        assert response.body == expected.body
        assert response.headers['content-type'] == expected.headers['content-type']
        assert response.headers['content-length'] == expected.headers['content-length']


def test_values_json_cannot_write_take_fastapis_path(engine):
    import datetime
    from decimal import Decimal
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    case = uuid.uuid4()
    payload = dict(id=case, day=datetime.date(2024, 2, 29), amount=Decimal('1.50'), tags={'x'})

    @view_cache.cached_view('typed')
    def handler(case_id, db):
        db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id))
        return payload

    assert call(engine, handler, case).body == JSONResponse(content=jsonable_encoder(payload)).body


def test_off_without_postgresql():
    counter = Counter()
    sqlite = create_engine('sqlite://')
    view = payments_view(counter)
    with sqlite.begin() as connection:
        connection.execute(text('CREATE TABLE payments (case_id text, amount int)'))
    with Session(sqlite) as db:
        assert view(case_id=str(uuid.uuid4()), db=db) == dict(total=0)
        assert view(case_id=str(uuid.uuid4()), db=db) == dict(total=0)
    assert counter.calls == 2


def test_rewrites_whose_xmin_would_balance_out_still_recompute(engine):
    """Two rows whose old xmins average to the rewriting transaction's xid (a sum would not change)."""
    case, counter = uuid.uuid4(), Counter()

    def xid(connection):
        return int(connection.execute(text('SELECT txid_current()')).scalar()) & 0xFFFFFFFF

    def next_xid():
        with engine.connect() as connection:
            return int(connection.execute(text('SELECT txid_snapshot_xmax(txid_current_snapshot())')).scalar()) & 0xFFFFFFFF

    with engine.begin() as connection:
        first = xid(connection)
        connection.execute(text('INSERT INTO payments (case_id, amount) VALUES (:c, 1)'), dict(c=case))
    for _ in range(5):
        with engine.begin() as connection:
            xid(connection)
    rewriting = engine.connect()
    transaction = rewriting.begin()
    rewriter = xid(rewriting)
    while next_xid() < 2 * rewriter - first:
        with engine.begin() as connection:
            xid(connection)
    with engine.begin() as connection:
        second = xid(connection)
        connection.execute(text('INSERT INTO payments (case_id, amount) VALUES (:c, 2)'), dict(c=case))
    assert first + second == 2 * rewriter
    view = payments_view(counter)
    assert call(engine, view, case).body == b'{"total":3}'
    rewriting.execute(text('UPDATE payments SET amount = amount + 100 WHERE case_id = :c'), dict(c=case))
    transaction.commit(); rewriting.close()
    assert call(engine, view, case).body == b'{"total":203}'


def test_one_pooled_connection_is_enough(engine):
    """The request's own connection is returned before the view takes the one it works in."""
    from sqlalchemy.pool import QueuePool
    with engine.connect() as connection:
        schema = connection.execute(text('SELECT current_schema()')).scalar()
    small = create_engine(engine.url.render_as_string(hide_password=False), poolclass=QueuePool, pool_size=1, max_overflow=0,
                          pool_timeout=2, connect_args={'options': f'-csearch_path={schema}'})
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 4)', c=case)
    try:
        view = payments_view(counter)
        assert call(small, view, case).body == b'{"total":4}'
        assert call(small, view, case).body == b'{"total":4}'
        assert counter.calls == 1
    finally:
        small.dispose()


def test_a_burst_of_the_same_view_needs_no_more_connections_than_requests(engine):
    from sqlalchemy.pool import QueuePool
    with engine.connect() as connection:
        schema = connection.execute(text('SELECT current_schema()')).scalar()
    small = create_engine(engine.url.render_as_string(hide_password=False), poolclass=QueuePool, pool_size=4, max_overflow=0,
                          pool_timeout=5, connect_args={'options': f'-csearch_path={schema}'})
    case, counter, errors, bodies = uuid.uuid4(), Counter(), [], []
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 6)', c=case)
    view = payments_view(counter)
    barrier = threading.Barrier(4)

    def one():
        try:
            with Session(small) as db:
                db.execute(text('SELECT 1'))
                barrier.wait()
                bodies.append(view(case_id=case, db=db).body)
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    try:
        threads = [threading.Thread(target=one) for _ in range(4)]
        [thread.start() for thread in threads]; [thread.join() for thread in threads]
    finally:
        small.dispose()
    assert errors == []
    assert bodies == [b'{"total":6}'] * 4
    assert counter.calls == 1
    assert view_cache._key_locks == {}


def test_keys_fastapi_would_drop_are_dropped_the_same_way(engine):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    case = uuid.uuid4()
    payload = {'_saved': 1, 'x': {'_same': 3, 'kept': 2}}

    @view_cache.cached_view('sa-keys')
    def handler(case_id, db):
        db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id))
        return payload

    assert call(engine, handler, case).body == JSONResponse(content=jsonable_encoder(payload)).body == b'{"x":{"kept":2}}'


def test_a_table_whose_case_id_is_text_is_checked(engine):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'CREATE TABLE notes (id serial PRIMARY KEY, case_id varchar(64), body text)')
    view_cache._tables_cache.clear()

    @view_cache.cached_view('text-case')
    def handler(case_id, db):
        counter.calls += 1
        return dict(n=db.execute(text('SELECT count(*) FROM notes WHERE case_id = :c'), dict(c=str(case_id))).scalar())

    assert call(engine, handler, case).body == b'{"n":0}'
    write(engine, 'INSERT INTO notes (case_id, body) VALUES (:c, :b)', c=str(case), b='x')
    assert call(engine, handler, case).body == b'{"n":1}'
    assert call(engine, handler, case).body == b'{"n":1}'
    assert counter.calls == 2


def test_many_small_views_are_bounded_by_count(engine, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    monkeypatch.setattr(view_cache, 'MAX_ENTRIES', 3)
    view = payments_view(counter)
    for minimum in range(6):
        call(engine, view, case, minimum=minimum)
    assert len(view_cache._entries) == 3
    assert view_cache._total_bytes == sum(view_cache._cost(k, e) for k, e in view_cache._entries.items())
    assert view_cache._total_bytes > sum(len(e.body) for e in view_cache._entries.values()), 'overhead is counted'
    call(engine, view, case, minimum=5)
    assert counter.calls == 6, 'the newest views are kept'


def test_when_reuse_itself_fails_the_view_is_computed_as_without_it(engine, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5), (:c, 7)', c=case)

    def broken(connection):
        raise RuntimeError('table list unavailable')
    monkeypatch.setattr(view_cache, '_load_tables', broken)
    assert call(engine, payments_view(counter), case) == dict(total=12)
    assert counter.calls == 1 and not view_cache._entries


def test_a_failing_view_is_not_run_twice(engine):
    calls = Counter()

    @view_cache.cached_view('failing')
    def handler(case_id, db):
        calls.calls += 1
        raise ValueError('view failed')
    with pytest.raises(ValueError):
        call(engine, handler, uuid.uuid4())
    assert calls.calls == 1
