"""A changed slow Financial view is answered with its previous copy marked updating, and computed again in the
background (first visit under 2 s, 2026-10-31: after 16 corrections on 49494305 eight requests took 8-14 s).

The PostgreSQL tests are opt-in (FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL, a disposable local test database); the
key round-trip test runs everywhere.
"""
import asyncio
import json
import os
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from services.financial import view_cache, view_refresh

URL = os.environ.get('FINANCIAL_VIEW_CACHE_TEST_DATABASE_URL')
needs_pg = pytest.mark.skipif(not URL, reason='Requires an explicit local PostgreSQL test connection')


@pytest.fixture(autouse=True)
def memo(tmp_path, monkeypatch):
    monkeypatch.setenv('FINANCIAL_VIEW_MEMO_DIR', str(tmp_path))
    monkeypatch.setattr(view_cache, 'code_identity', lambda: 'code-1')
    return tmp_path


@pytest.fixture
def engine():
    admin = create_engine(URL)
    schema = 'view_refresh_test_' + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE payments (id serial PRIMARY KEY, case_id uuid NOT NULL, amount int NOT NULL)'))
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
    with engine.begin() as connection:
        connection.execute(text(sql), params)


class Counter:
    calls = 0


def total_view(counter, name='totals', limit=None):
    @view_cache.cached_view(name)
    def handler(case_id, db):
        counter.calls += 1
        total = db.execute(text('SELECT coalesce(sum(amount), 0) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar()
        if limit is not None and total > limit:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail='More than %d.' % limit)
        return dict(total=int(total))
    return handler


def call(engine, handler, case_id, accepts=True):
    token = view_cache._accepts_updating.set(accepts)
    try:
        with Session(engine) as db:
            db.execute(text('SELECT 1'))
            return handler(case_id=case_id, db=db)
    finally:
        view_cache._accepts_updating.reset(token)


def asks(memo):
    directory = memo / view_refresh.WANTED_DIR
    return [json.loads(path.read_text()) for path in directory.glob('*.json')] if directory.exists() else []


@pytest.fixture
def slow(monkeypatch):
    """Every computation counts as slow (the tests' views take milliseconds)."""
    monkeypatch.setattr(view_cache, 'UPDATING_MIN_SECONDS', 0.0)


@needs_pg
def test_a_changed_view_is_answered_with_its_previous_copy_marked_updating_then_refreshed(engine, memo, slow):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    before = time.time()
    first = call(engine, view, case)
    assert first.body == b'{"total":5}' and 'x-financial-view-state' not in first.headers
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    updating = call(engine, view, case)
    assert updating.body == b'{"total":5}', 'the previous copy, byte for byte'
    assert updating.headers['x-financial-view-state'] == 'updating'
    assert updating.headers['x-financial-view-as-of'][:19] <= time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(time.time()))
    assert updating.headers['x-financial-view-as-of'][:19] >= time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(before - 1))
    assert counter.calls == 1, 'the person did not wait for the computation'
    [ask] = asks(memo)
    assert ask['key'][0] == 'totals' and ask['case_id'] == str(case)
    # The background refresh computes it exactly as a request without the mark would.
    [(path, open_ask)] = view_refresh._open_asks('code-1')
    assert view_refresh.refresh_one(path, open_ask, session_factory=sessionmaker(engine))
    assert not path.exists(), 'keeping a current copy answers the ask'
    assert counter.calls == 2
    fresh = call(engine, view, case)
    assert fresh.body == b'{"total":12}' and 'x-financial-view-state' not in fresh.headers
    assert counter.calls == 2
    # Only current answers may be kept by the browser: a 304 for an updating answer's bytes would bring its mark back.
    assert updating.headers['cache-control'] == 'no-store' and 'etag' not in updating.headers
    assert fresh.headers['cache-control'] == 'private, no-cache' and fresh.headers['etag'].startswith('W/"')
    assert first.headers['etag'] != fresh.headers['etag']


@needs_pg
def test_a_browser_holding_the_current_bytes_gets_304_without_a_body(engine, memo):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter, name='totals-etag')
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    computed = call(engine, view, case, accepts=False)
    etag = computed.headers['etag']
    assert computed.status_code == 200 and computed.body == b'{"total":5}'
    token = view_cache._if_none_match.set('"other", ' + etag)
    try:
        unchanged = call(engine, view, case, accepts=False)
        assert unchanged.status_code == 304 and unchanged.body == b''
        assert unchanged.headers['etag'] == etag and unchanged.headers['vary'] == 'Accept-Encoding'
        write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
        changed = call(engine, view, case, accepts=False)
        assert changed.status_code == 200 and changed.body == b'{"total":12}' and changed.headers['etag'] != etag
    finally:
        view_cache._if_none_match.reset(token)
    reused = call(engine, view, case, accepts=False)  # served from memory: the same tag, the full body
    assert reused.status_code == 200 and reused.headers['etag'] == changed.headers['etag']
    assert counter.calls == 2


def test_a_kept_refusal_carries_no_etag():
    entry = view_cache._Entry(('payments',), (('payments', 1, 'x'),), b'', 422, 'application/json', refusal='No.')
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as raised:
        view_cache._kept(entry, {})
    assert not (raised.value.headers or {}).get('ETag')


@needs_pg
def test_the_refresh_saves_the_view_for_the_other_workers_however_fast(engine, memo, slow):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, view, case)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    call(engine, view, case)
    [(path, open_ask)] = view_refresh._open_asks('code-1')
    view_refresh.refresh_one(path, open_ask, session_factory=sessionmaker(engine))
    view_cache.clear()  # another worker: nothing in memory
    other = call(engine, view, case)
    assert other.body == b'{"total":12}' and 'x-financial-view-state' not in other.headers
    assert counter.calls == 2


@needs_pg
def test_a_request_that_does_not_say_it_can_show_updating_is_computed(engine, memo, slow):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, view, case, accepts=False)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    response = call(engine, view, case, accepts=False)
    assert response.body == b'{"total":12}' and 'x-financial-view-state' not in response.headers
    assert counter.calls == 2 and asks(memo) == []


@needs_pg
def test_a_fast_view_is_computed_not_served_as_updating(engine, memo):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, view, case)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    assert call(engine, view, case).body == b'{"total":12}'
    assert counter.calls == 2 and asks(memo) == []


@needs_pg
def test_an_ask_older_than_the_limit_is_computed_by_the_request(engine, memo, slow, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, view, case)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    call(engine, view, case)
    [(path, open_ask)] = view_refresh._open_asks('code-1')
    view_refresh._write(path, {**open_ask, 'asked': time.time() - view_cache.UPDATING_MAX_SECONDS - 1, 'failed': 1.0})
    response = call(engine, view, case)
    assert response.body == b'{"total":12}' and 'x-financial-view-state' not in response.headers
    assert counter.calls == 2


@needs_pg
def test_a_kept_refusal_is_also_answered_as_updating(engine, memo, slow):
    from fastapi import HTTPException
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter, name='limited', limit=10)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 50)', c=case)
    with pytest.raises(HTTPException):
        call(engine, view, case)
    write(engine, 'UPDATE payments SET amount = 1 WHERE case_id = :c', c=case)
    with pytest.raises(HTTPException) as refused:
        call(engine, view, case)
    assert refused.value.status_code == 422 and refused.value.headers['X-Financial-View-State'] == 'updating'
    assert counter.calls == 1


@needs_pg
def test_a_refresh_that_fails_marks_its_ask_failed_and_leaves_it(engine, memo, slow, monkeypatch):
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, view, case)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    call(engine, view, case)
    monkeypatch.setattr(view_refresh, 'refresh_one', lambda path, ask_, session_factory=None: 1 / 0)
    monkeypatch.setattr(view_refresh, 'IDLE_EXIT_SECONDS', 0.5)
    monkeypatch.setattr(view_refresh, 'POLL_SECONDS', 0.05)
    from services.financial import view_warmup
    monkeypatch.setattr(view_warmup, '_preparing', lambda: False)
    view_refresh.run_child()
    [ask] = asks(memo)
    assert ask.get('failed') and view_refresh._open_asks('code-1') == []


def test_a_saved_copy_without_its_computation_time_is_never_served_as_updating():
    entry = view_cache._Entry(('payments',), (('payments', 1, 'x'),), b'{}', 200, 'application/json')
    assert entry.computed_at == 0
    assert not view_cache._serve_previous(('v', '{}'), uuid.uuid4(), entry)


def test_the_mark_is_set_only_for_a_get_with_the_header():
    seen = []

    async def app(scope, receive, send):
        seen.append(view_cache._accepts_updating.get())
    middleware = view_cache.AcceptsUpdatingMiddleware(app)
    for method, headers in (('GET', [(b'x-financial-view-accept', b'updating')]), ('GET', []),
                            ('POST', [(b'x-financial-view-accept', b'updating')])):
        asyncio.run(middleware(dict(type='http', method=method, headers=headers), None, None))
    assert seen == [True, False, False]


def test_the_browsers_if_none_match_reaches_the_route():
    seen = []

    async def app(scope, receive, send):
        seen.append((view_cache._accepts_updating.get(), view_cache._if_none_match.get()))
    middleware = view_cache.AcceptsUpdatingMiddleware(app)
    for method, headers in (('GET', [(b'if-none-match', b'W/"abc"')]), ('POST', [(b'if-none-match', b'W/"abc"')]),
                            ('GET', [(b'x-financial-view-accept', b'updating'), (b'if-none-match', b'W/"d"')])):
        asyncio.run(middleware(dict(type='http', method=method, headers=headers), None, None))
    assert seen == [(False, 'W/"abc"'), (False, ''), (True, 'W/"d"')]


def test_an_asked_routes_parameters_give_back_its_key():
    """The refresh rebuilds a real route's arguments from the kept key's strings (UUIDs, dates, Literals, lists,
    numbers, booleans) and must reach the same key, or it would compute a different view."""
    import routers.financial_ledger  # noqa: F401 - registers the views
    from datetime import date
    handler = view_cache.handlers['pattern-review']
    arguments = dict(case_id=uuid.uuid4(), account_id=None, start_date=date(2024, 1, 2), end_date=None,
                     population='working', window_days=3, threshold_minor=None, threshold_currency=None,
                     cross_account=True, account_ids=[uuid.uuid4()], account_holders=['A B'])
    key = view_cache.view_key('pattern-review', arguments)
    rebuilt = view_refresh._typed(handler, json.loads(key[1]))
    assert view_cache.view_key('pattern-review', rebuilt) == key
    assert rebuilt['window_days'] == 3 and rebuilt['cross_account'] is True and rebuilt['start_date'] == date(2024, 1, 2)


@needs_pg
def test_a_refresh_that_saves_nothing_the_workers_can_read_is_not_done(engine, memo, slow, monkeypatch):
    """Review 2026-10-31: a copy kept only in the refresh process's memory would delete the ask while the workers
    keep answering updating, forever."""
    case, counter = uuid.uuid4(), Counter()
    view = total_view(counter)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    call(engine, view, case)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    call(engine, view, case)
    [(path, open_ask)] = view_refresh._open_asks('code-1')
    monkeypatch.setattr(view_cache, '_save_if_slow', lambda *args, **kwargs: None)
    assert not view_refresh.refresh_one(path, open_ask, session_factory=sessionmaker(engine))


def test_an_ask_left_by_a_refresh_process_that_died_is_marked_failed_not_taken_again(memo):
    key = ('totals', '{"case_id": "c"}')
    view_refresh.ask(key, 'c')
    [(path, open_ask)] = view_refresh._open_asks('code-1')
    view_refresh._write(path, {**open_ask, 'started': dict(pid=2 ** 22 + 12345, at=time.time())})
    assert view_refresh._open_asks('code-1') == []
    assert view_refresh._read(path)['failed']


def test_an_expired_ask_is_forgotten_only_once_a_current_copy_is_kept(memo):
    key = ('totals', '{"case_id": "c"}')
    entry = view_cache._Entry(('payments',), (), b'{}', 200, 'application/json', seconds=5.0, computed_at=time.time())
    token = view_cache._accepts_updating.set(True)
    try:
        assert view_cache._serve_previous(key, 'c', entry)
        [(path, open_ask)] = view_refresh._open_asks('code-1')
        view_refresh._write(path, {**open_ask, 'asked': time.time() - view_cache.UPDATING_MAX_SECONDS - 1, 'failed': 1.0})
        assert not view_cache._serve_previous(key, 'c', entry)
        assert not view_cache._serve_previous(key, 'c', entry), 'every request computes it until one is kept'
        view_cache._forget_ask(key)  # a request kept a current copy
        assert not path.exists()
        assert view_cache._serve_previous(key, 'c', entry), 'a new change asks again'
    finally:
        view_cache._accepts_updating.reset(token)


@needs_pg
def test_a_view_whose_new_answer_cannot_be_kept_shows_that_answer_after_the_limit_every_time(engine, memo, slow):
    """Re-review 2026-10-31: forgetting the ask before computing made an error answer loop back into updating."""
    from fastapi import HTTPException
    case, counter = uuid.uuid4(), Counter()

    @view_cache.cached_view('breaks')
    def view(case_id, db):
        counter.calls += 1
        total = db.execute(text('SELECT coalesce(sum(amount), 0) FROM payments WHERE case_id = :c'), dict(c=case_id)).scalar()
        if total > 10:
            raise HTTPException(status_code=500, detail='Could not be prepared.')
        return dict(total=int(total))
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 5)', c=case)
    token = view_cache.always_save.set(True)  # saved like a slow view, so every worker has a previous copy
    try:
        call(engine, view, case)
    finally:
        view_cache.always_save.reset(token)
    write(engine, 'INSERT INTO payments (case_id, amount) VALUES (:c, 7)', c=case)
    assert call(engine, view, case).headers['x-financial-view-state'] == 'updating'
    [(path, open_ask)] = view_refresh._open_asks('code-1')
    with pytest.raises(HTTPException):
        view_refresh.refresh_one(path, open_ask, session_factory=sessionmaker(engine))
    view_refresh._write(path, {**open_ask, 'asked': time.time() - view_cache.UPDATING_MAX_SECONDS - 1, 'failed': 1.0})
    for _ in range(2):
        with pytest.raises(HTTPException) as failed:
            call(engine, view, case)
        assert failed.value.status_code == 500
