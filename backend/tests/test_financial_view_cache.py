"""Opt-in PostgreSQL checks for compute-once Financial views; every test uses a new, disposable schema.

Set FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL to a local test PostgreSQL connection. No existing application
tables are read or changed.
"""
import json
import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.financial import view_cache

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture(autouse=True)
def _saved_copies_stay_in_the_test(tmp_path, monkeypatch):
    """Saved values and views go to this test's own directory, never the user's cache."""
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))


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
        raise HTTPException(status_code=409, detail='no')

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


def test_the_cycle_collector_waits_only_while_a_view_computes(engine):
    import gc
    seen = []

    @view_cache.cached_view('collector')
    def handler(case_id, db):
        seen.append(gc.isenabled())
        db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id))
        return dict(ok=True)

    @view_cache.cached_view('collector-failing')
    def failing(case_id, db):
        seen.append(gc.isenabled())
        raise ValueError('view failed')
    assert gc.isenabled()
    assert call(engine, handler, uuid.uuid4()).body == b'{"ok":true}'
    with pytest.raises(ValueError):
        call(engine, failing, uuid.uuid4())
    assert seen == [False, False] and gc.isenabled()
    gc.disable()  # a process that turned it off itself keeps it off
    try:
        call(engine, handler, uuid.uuid4())
        assert not gc.isenabled()
    finally:
        gc.enable()


def test_overlapping_views_resume_the_collector_when_the_last_one_ends():
    import gc
    first, second = view_cache._CollectorPaused(), view_cache._CollectorPaused()
    first.__enter__(); second.__enter__()
    first.__exit__(None, None, None)
    assert not gc.isenabled()
    second.__exit__(None, None, None)
    assert gc.isenabled()


def memo_view(counter, memo):
    """A view whose per-row part is reused by row version (as account_history reuses saved statement checks)."""
    @view_cache.cached_view('memo')
    def handler(case_id, db):
        rows = db.execute(text('SELECT id, amount FROM payments WHERE case_id = :c ORDER BY id'), dict(c=case_id)).all()
        versions = view_cache.row_versions(db, 'payments', [id_ for id_, _ in rows]) if view_cache.in_snapshot() else None
        def compute(amount):
            counter.calls += 1
            return dict(double=amount * 2)
        out = []
        for id_, amount in rows:
            key = versions and (id_, versions.get(id_))
            out.append(memo.get(key, lambda: compute(amount)) if key else compute(amount))
        return out
    return handler


def test_a_row_version_memo_recomputes_only_the_changed_row(engine):
    case, counter = uuid.uuid4(), Counter()
    memo = view_cache.VersionMemo('test', 100)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1), (:c, 2), (:c, 3)', c=case)
    view = memo_view(counter, memo)
    assert call(engine, view, case).body == b'[{"double":2},{"double":4},{"double":6}]' and counter.calls == 3
    write(engine, 'UPDATE payments SET amount = 10 WHERE case_id = :c AND amount = 2', c=case)
    assert call(engine, view, case).body == b'[{"double":2},{"double":20},{"double":6}]' and counter.calls == 4
    # Rewriting a row with the same values is still a new version: computed again, with the same result.
    write(engine, 'UPDATE payments SET amount = amount WHERE case_id = :c AND amount = 1', c=case)
    assert call(engine, view, case).body == b'[{"double":2},{"double":20},{"double":6}]' and counter.calls == 5
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 4)', c=case)
    assert call(engine, view, case).body == b'[{"double":2},{"double":20},{"double":6},{"double":8}]' and counter.calls == 6


def test_a_row_version_memo_is_not_used_outside_a_view_snapshot(engine):
    case, counter = uuid.uuid4(), Counter()
    memo = view_cache.VersionMemo('test', 100)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1)', c=case)
    handler = memo_view(counter, memo).__wrapped__
    with Session(engine) as db:
        assert not view_cache.in_snapshot()
        # An uncommitted change in the caller's own transaction is never stored.
        db.execute(text('UPDATE payments SET amount = 50 WHERE case_id = :c'), dict(c=case))
        assert handler(case_id=case, db=db) == [dict(double=100)]
        db.rollback()
    assert memo.stats == dict(hits=0, misses=0, saved_hits=0)
    assert call(engine, memo_view(counter, memo), case).body == b'[{"double":2}]'


def test_a_row_version_memo_hands_out_copies_and_stays_bounded():
    memo = view_cache.VersionMemo('test', 2)
    value = memo.get('a', lambda: dict(items=[1]))
    value['items'].append(2)
    assert memo.get('a', lambda: None) == dict(items=[1])
    memo.get('a', lambda: None)['items'].append(3)
    assert memo.get('a', lambda: None) == dict(items=[1])
    memo.get('b', lambda: 1); memo.get('c', lambda: 2)
    assert memo.get('a', lambda: 'again') == 'again'


def test_a_views_own_refusal_is_kept_and_raised_again_until_its_rows_change(engine):
    from fastapi import HTTPException
    case, other, counter = uuid.uuid4(), uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5), (:o, 7)', c=case, o=other)

    @view_cache.cached_view('refusing')
    def refusing(case_id, db):
        counter.calls += 1
        total = db.execute(text('SELECT sum(amount) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar()
        raise HTTPException(status_code=422, detail=f'The complete ledger record exceeds 64 MiB ({total}).')

    details = []
    for _ in range(2):
        with pytest.raises(HTTPException) as caught:
            call(engine, refusing, case)
        details.append((caught.value.status_code, caught.value.detail, caught.value.headers))
    assert counter.calls == 1, 'the same rows give the same refusal'
    assert details == [(422, 'The complete ledger record exceeds 64 MiB (5).', None)] * 2
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:o, 1)', o=other)
    with pytest.raises(HTTPException):
        call(engine, refusing, case)
    assert counter.calls == 1, "another case's write does not recompute"
    write(engine, 'UPDATE payments SET amount = 6 WHERE case_id = :c', c=case)
    with pytest.raises(HTTPException) as caught:
        call(engine, refusing, case)
    assert counter.calls == 2 and caught.value.detail == 'The complete ledger record exceeds 64 MiB (6).'


def test_a_refusal_through_the_app_has_the_same_bytes_as_without_the_cache(engine):
    from fastapi import FastAPI, HTTPException, Depends
    from fastapi.testclient import TestClient
    case = uuid.uuid4()

    def refuse(case_id, db):
        db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id))
        raise HTTPException(status_code=422, detail='More than 1,000 payments match these filters. Choose an account or a shorter date range, then run this check again.')

    def db():
        with Session(engine) as session:
            yield session
    app = FastAPI()
    cached = view_cache.cached_view('refuse-app')(refuse)

    @app.get('/plain')
    def plain(case_id: uuid.UUID, db=Depends(db)):
        return refuse(case_id=case_id, db=db)

    @app.get('/cached')
    def through_cache(case_id: uuid.UUID, db=Depends(db)):
        return cached(case_id=case_id, db=db)
    client = TestClient(app)
    expected = client.get(f'/plain?case_id={case}')
    first = client.get(f'/cached?case_id={case}')
    hits = view_cache.stats['hits']
    second = client.get(f'/cached?case_id={case}')
    assert view_cache.stats['hits'] == hits + 1, 'the second answer is the kept refusal'
    for response in (first, second):
        assert (response.status_code, response.content, response.headers['content-type']) == (
            expected.status_code, expected.content, expected.headers['content-type'])


def test_other_refusals_are_not_kept(engine):
    from fastapi import HTTPException
    case, counter = uuid.uuid4(), Counter()

    @view_cache.cached_view('refusal-with-headers')
    def with_headers(case_id, db):
        counter.calls += 1
        db.execute(text('SELECT count(*) FROM payments'))
        raise HTTPException(status_code=422, detail='no', headers={'Retry-After': '5'})

    @view_cache.cached_view('refusal-reading-nothing')
    def reads_nothing(case_id, db):
        counter.calls += 1
        raise HTTPException(status_code=422, detail='no')

    for handler in (with_headers, with_headers, reads_nothing, reads_nothing):
        with pytest.raises(HTTPException):
            call(engine, handler, case)
    assert counter.calls == 4 and not view_cache._entries


def saved_memo(name='saved', decode=lambda saved: saved):
    return view_cache.VersionMemo(name, 100, decode=decode)


def saved_view(counter, memo):
    """memo_view, saving the memo's values the way account_history does (bind in the snapshot, flush after)."""
    inner = memo_view(counter, memo).__wrapped__

    @view_cache.cached_view('saved-' + memo.name)
    def handler(case_id, db):
        memo.bind(db)
        try:
            return inner(case_id=case_id, db=db)
        finally:
            memo.flush()
    return handler


@pytest.fixture
def memo_dir(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    return tmp_path


def test_saved_values_survive_a_restart_and_a_changed_row_still_recomputes(engine, memo_dir):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1), (:c, 2)', c=case)
    assert call(engine, saved_view(counter, saved_memo()), case).body == b'[{"double":2},{"double":4}]'
    assert counter.calls == 2 and (memo_dir / 'saved.json').exists()
    # A new process: empty memory, empty view cache. The saved values are used, nothing is computed.
    view_cache.clear()
    restarted = saved_memo()
    assert call(engine, saved_view(counter, restarted), case).body == b'[{"double":2},{"double":4}]'
    assert counter.calls == 2 and restarted.stats['saved_hits'] == 2
    view_cache.clear()
    write(engine, 'UPDATE payments SET amount = 10 WHERE case_id = :c AND amount = 2', c=case)
    again = saved_memo()
    assert call(engine, saved_view(counter, again), case).body == b'[{"double":2},{"double":20}]'
    assert counter.calls == 3 and again.stats['saved_hits'] == 1


def test_saved_values_are_not_used_by_other_code_or_another_database(engine, memo_dir, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1)', c=case)
    call(engine, saved_view(counter, saved_memo()), case)
    assert counter.calls == 1
    view_cache.clear()
    monkeypatch.setattr(view_cache, '_code_identity', 'another release')
    call(engine, saved_view(counter, saved_memo()), case)
    assert counter.calls == 2
    view_cache.clear()
    saved = json.loads((memo_dir / 'saved.json').read_text())
    saved['scope']['database'] = 'another database'
    (memo_dir / 'saved.json').write_text(json.dumps(saved))
    call(engine, saved_view(counter, saved_memo()), case)
    assert counter.calls == 3


def test_nothing_is_saved_once_transaction_ids_could_have_wrapped(engine, memo_dir, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1)', c=case)
    monkeypatch.setattr(view_cache, 'MEMO_XID_LIMIT', 1)
    call(engine, saved_view(counter, saved_memo()), case)
    assert not (memo_dir / 'saved.json').exists()


def test_a_value_that_json_would_change_is_not_saved(engine, memo_dir):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1)', c=case)
    # The decoder gives a list back for the computed dict: not exactly the value, so it stays in memory only.
    call(engine, saved_view(counter, saved_memo(decode=lambda saved: [saved])), case)
    assert json.loads((memo_dir / 'saved.json').read_text())['entries'] == [] if (memo_dir / 'saved.json').exists() else True
    view_cache.clear()
    call(engine, saved_view(counter, saved_memo(decode=lambda saved: [saved])), case)
    assert counter.calls == 2


def test_an_unreadable_saved_file_is_computed_again(engine, memo_dir):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 3)', c=case)
    (memo_dir / 'saved.json').write_text('{not json')
    assert call(engine, saved_view(counter, saved_memo()), case).body == b'[{"double":6}]'
    assert counter.calls == 1 and json.loads((memo_dir / 'saved.json').read_text())['entries']


def test_exact_json_keeps_types():
    same = view_cache._exact_json
    as_tuple = lambda saved: tuple(saved)
    assert same((dict(a=1), 'x', 2), as_tuple) == [dict(a=1), 'x', 2]
    assert same((True,), lambda saved: tuple(saved)) == [True]
    assert same((1.0,), as_tuple) is not view_cache._MISSING
    assert same(({1: 'int key'},), as_tuple) is view_cache._MISSING
    assert same((object(),), as_tuple) is view_cache._MISSING


def test_a_database_restored_to_an_earlier_point_does_not_use_saved_values(engine, memo_dir):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1)', c=case)
    call(engine, saved_view(counter, saved_memo()), case)
    assert counter.calls == 1
    # As if the database went back in time: the store has seen later transaction ids than the database hands out.
    saved = json.loads((memo_dir / 'saved.json').read_text())
    saved['xmax'] += 10 ** 6
    (memo_dir / 'saved.json').write_text(json.dumps(saved))
    view_cache.clear()
    call(engine, saved_view(counter, saved_memo()), case)
    assert counter.calls == 2


def test_a_changed_setting_is_another_identity(monkeypatch):
    before = view_cache._identity_now()
    monkeypatch.setenv('LOUPE_FINANCIAL_SUMMARY_PAGES', 'synthetic')
    assert view_cache._identity_now() not in (before, None)
    monkeypatch.setenv('INVOCATION_ID', 'another start')
    monkeypatch.delenv('LOUPE_FINANCIAL_SUMMARY_PAGES')
    assert view_cache._identity_now() == before


def test_a_temporary_file_left_by_a_killed_writer_is_removed(engine, memo_dir):
    case, counter = uuid.uuid4(), Counter()
    (memo_dir / 'saved.json.4242.tmp').write_text('partial')
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 1)', c=case)
    call(engine, saved_view(counter, saved_memo()), case)
    assert not (memo_dir / 'saved.json.4242.tmp').exists() and (memo_dir / 'saved.json').exists()


@pytest.fixture
def saved_views(memo_dir, monkeypatch):
    """Every computed view counts as slow, so it is saved."""
    monkeypatch.setattr(view_cache, 'SAVE_MIN_SECONDS', 0)
    return memo_dir / 'views'


def test_a_saved_view_serves_another_worker_and_the_next_start_until_its_rows_change(engine, saved_views):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5), (:c, 7)', c=case)
    first = call(engine, payments_view(counter), case)
    assert counter.calls == 1 and len(list(saved_views.glob('*.view'))) == 1
    # Another process (or this one after a restart): nothing in memory. The saved copy answers, same bytes.
    view_cache.clear()
    saved_hits = view_cache.stats['saved_hits']
    again = call(engine, payments_view(counter), case)
    assert (again.body, again.status_code, again.media_type) == (first.body, first.status_code, first.media_type)
    assert counter.calls == 1 and view_cache.stats['saved_hits'] == saved_hits + 1
    assert call(engine, payments_view(counter), case).body == first.body and counter.calls == 1, 'then from memory'
    view_cache.clear()
    write(engine, 'UPDATE payments SET amount = amount WHERE case_id = :c AND amount = 5', c=case)
    assert call(engine, payments_view(counter), case).body == b'{"total":12}' and counter.calls == 2
    write(engine, 'DELETE FROM payments WHERE case_id = :c AND amount = 5', c=case)
    view_cache.clear()
    assert call(engine, payments_view(counter), case).body == b'{"total":7}' and counter.calls == 3
    view_cache.clear()
    assert call(engine, payments_view(counter), case).body == b'{"total":7}' and counter.calls == 3, 'the new copy replaced the old'
    assert len(list(saved_views.glob('*.view'))) == 1


def test_a_saved_view_is_not_used_by_other_code_another_database_or_a_database_gone_back(engine, saved_views, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, payments_view(counter), case)
    view_cache.clear()
    with monkeypatch.context() as other:
        other.setattr(view_cache, '_code_identity', 'another release')
        call(engine, payments_view(counter), case)
    assert counter.calls == 2
    for change in ('database', 'xmax'):
        for path in saved_views.glob('*.view'):
            header, body = path.read_bytes().split(b'\n', 1)
            header = json.loads(header)
            if change == 'database':
                header['scope']['database'] = 'another database'
            else:
                header['xmax'] += 10 ** 6  # computed at transaction ids this database has not handed out yet
            path.write_bytes(json.dumps(header).encode() + b'\n' + body)
        view_cache.clear()
        assert call(engine, payments_view(counter), case).body == b'{"total":5}'
    assert counter.calls == 4


def test_fast_views_and_wrapped_transaction_ids_are_not_saved(engine, memo_dir, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    monkeypatch.setattr(view_cache, 'SAVE_MIN_SECONDS', 3600)
    call(engine, payments_view(counter), case)
    assert not list(memo_dir.glob('views/*.view'))
    monkeypatch.setattr(view_cache, 'SAVE_MIN_SECONDS', 0)
    monkeypatch.setattr(view_cache, 'MEMO_XID_LIMIT', 1)
    view_cache.clear()
    call(engine, payments_view(counter), case)
    assert not list(memo_dir.glob('views/*.view')) and counter.calls == 2


def test_a_saved_refusal_is_raised_again_after_a_restart(engine, saved_views):
    from fastapi import HTTPException
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)

    @view_cache.cached_view('refusing-saved')
    def refusing(case_id, db):
        counter.calls += 1
        db.execute(text('SELECT count(*) FROM payments WHERE case_id = :c'), dict(c=case_id))
        raise HTTPException(status_code=422, detail='More than 1,000 payments match these filters.')

    for _ in range(2):
        with pytest.raises(HTTPException) as caught:
            call(engine, refusing, case)
        assert (caught.value.status_code, caught.value.detail) == (422, 'More than 1,000 payments match these filters.')
        view_cache.clear()
    assert counter.calls == 1


def test_an_unreadable_or_cut_saved_view_is_computed_again(engine, saved_views):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, payments_view(counter), case)
    (path,) = saved_views.glob('*.view')
    whole = path.read_bytes()
    assert whole.endswith(b'5}')
    for damage in (b'{not json\n{"total":5}', whole[:-3], whole[:-2] + b'6}'):
        path.write_bytes(damage)
        view_cache.clear()
        assert call(engine, payments_view(counter), case).body == b'{"total":5}'
    assert counter.calls == 4, 'a changed body of the same size is caught by its checksum'
    view_cache.clear()
    assert call(engine, payments_view(counter), case).body == b'{"total":5}' and counter.calls == 4, 'rewritten whole'


def test_saved_views_stay_within_their_budget_oldest_first(engine, saved_views, monkeypatch):
    import os
    import time
    counter = Counter()
    cases = [uuid.uuid4() for _ in range(3)]
    for case in cases:
        write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    saved_views.mkdir(parents=True)
    (saved_views / 'old.view.1.1.tmp').write_text('partial')
    os.utime(saved_views / 'old.view.1.1.tmp', (time.time() - 7200,) * 2)
    (saved_views / 'recent.view.2.2.tmp').write_text('being written')
    seen = set()
    for number, case in enumerate(cases):
        if number == 1:
            size = next(saved_views.glob('*.view')).stat().st_size
            monkeypatch.setattr(view_cache, 'MAX_SAVED_BYTES', 2 * size + size // 2)
        call(engine, payments_view(counter), case)
        for path in set(saved_views.glob('*.view')) - seen:
            os.utime(path, (time.time() - 1000 + 100 * number,) * 2)  # saved in this order
            seen.add(path)
    assert len(list(saved_views.glob('*.view'))) == 2
    assert not (saved_views / 'old.view.1.1.tmp').exists() and (saved_views / 'recent.view.2.2.tmp').exists()
    view_cache.clear()
    call(engine, payments_view(counter), cases[0])
    assert counter.calls == 4, 'the oldest copy was the one removed'
    view_cache.clear()
    call(engine, payments_view(counter), cases[2])
    assert counter.calls == 4, 'the newest copy was kept'


def test_no_saved_view_is_used_once_the_database_hands_out_ids_below_the_highest_seen(engine, saved_views):
    case, other, counter = uuid.uuid4(), uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5), (:o, 1)', c=case, o=other)
    call(engine, payments_view(counter), case)
    # Another view was saved at a later counter than this database now hands out: it went back in time.
    (saved_views / 'xmax').write_text(str(10 ** 9))
    view_cache.clear()
    call(engine, payments_view(counter), case)
    assert counter.calls == 2


def test_a_failed_save_leaves_no_partial_file_and_the_answer_stands(engine, saved_views, monkeypatch):
    import os
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    real_fdopen = os.fdopen

    def full_disk(descriptor, *args, **kwargs):
        handle = real_fdopen(descriptor, *args, **kwargs)
        handle.write = lambda data: (_ for _ in ()).throw(OSError(28, 'No space left on device'))
        return handle
    monkeypatch.setattr(os, 'fdopen', full_disk)
    assert call(engine, payments_view(counter), case).body == b'{"total":5}'
    assert not list(saved_views.glob('*.tmp')) and not list(saved_views.glob('*.view'))


def test_when_the_saved_scope_cannot_be_read_the_view_is_still_answered(engine, saved_views, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    real_execute = view_cache.text

    def refusing_text(sql):
        if 'pg_control_system' in sql:
            sql = 'SELECT * FROM no_such_table_for_this_test'
        return real_execute(sql)
    monkeypatch.setattr(view_cache, 'text', refusing_text)
    assert call(engine, payments_view(counter), case).body == b'{"total":5}'
    assert call(engine, payments_view(counter), case).body == b'{"total":5}' and counter.calls == 1, 'kept in memory'
    assert not list(saved_views.glob('*.view'))
