"""Compute-once Financial read views, reused only while every row they read is unchanged.

A slow Financial view (a case's totals, posting graph, party directory ...) recomputed everything from the
ledger on every request, for every person, although the case had not changed in between. ``cached_view``
keeps the encoded response of one view for one set of parameters and serves it again only when the
database proves nothing it was computed from has changed since.

How a stored response is known to be current:

* The view runs inside one PostgreSQL snapshot. A read-only REPEATABLE READ transaction is opened and its
  snapshot exported; every transaction the view begins on any connection in this request imports that
  snapshot, so the whole view (including reads on connections the view opens itself) sees one state.
* Every table the view reads is recorded from the SQL it runs, by name, against all tables in the database.
* In the same snapshot, a fingerprint of those tables is taken: for a table with ``case_id``, the count and
  an md5 of the sorted ``xmin`` of this case's rows; for any other table, the same over the whole table.
  Any insert or update of a row in scope adds the ``xmin`` of a transaction that was not visible before,
  and a delete changes the count, so either changes the fingerprint. Freezing keeps ``xmin``, so vacuum
  does not.
* A later request takes the fingerprint of the same tables in its own snapshot; only an equal fingerprint
  returns the stored bytes. Otherwise the view is computed again. Nothing is ever invalidated by hand, so
  no write path (imports, labels, categories, identities, notes) can be forgotten.

A view's own refusal (the route's 422, e.g. "exceeds 64 MiB" or "more than 1,000 payments") is kept like a
result and raised again with the same text while the fingerprint is equal: it is computed from the same rows.
Not stored: other errors, non-JSON responses, views that read a large table without ``case_id`` (the check would
cost more than it saves), and anything over the size limits. Off on databases other than PostgreSQL.
Views whose result depends on anything besides these tables and their parameters (the clock, files, the
graph database, other threads) must not use this.
"""
from __future__ import annotations

import functools
import gc
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import event, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

MAX_ENTRY_BYTES = 96 * 1024 * 1024
MAX_TOTAL_BYTES = 384 * 1024 * 1024
# Bounds the entry count too: many tiny bodies (paging past the end) must not grow memory through per-entry overhead.
MAX_ENTRIES = 2000
# A table without case_id is fingerprinted whole; above this size a view reading it is not stored.
MAX_UNSCOPED_BYTES = 64 * 1024 * 1024

_recording: ContextVar['_Recording | None'] = ContextVar('financial_view_cache_recording', default=None)
_lock = threading.Lock()
_entries: OrderedDict = OrderedDict()
_total_bytes = 0
_key_locks: dict = {}
stats = dict(hits=0, misses=0, stored=0, not_stored=0)
_Encoded = None
_gc_lock = threading.Lock()
_gc_pauses = 0
_gc_resume = False


class _CollectorPaused:
    """Python's cycle collector waits while a view is computed, and runs as usual once no view is computing.

    A large case decodes hundreds of MB of stored JSON into millions of objects; the collector re-scanned
    them again and again while they were being built (d5b330d1: 46 s of 60 s decoding source metadata).
    Pausing it changes no value: objects are still freed when unreferenced, and cycles are collected later.
    Process-wide, so it is counted: the collector resumes when the last computing view ends."""

    def __enter__(self):
        global _gc_pauses, _gc_resume
        with _gc_lock:
            if _gc_pauses == 0:
                _gc_resume = gc.isenabled()
                gc.disable()
            _gc_pauses += 1

    def __exit__(self, *exc):
        global _gc_pauses
        with _gc_lock:
            _gc_pauses -= 1
            if _gc_pauses == 0 and _gc_resume:
                gc.enable()
        return False


@dataclass
class _Recording:
    owner: object
    snapshot: str
    tables: set = field(default_factory=set)
    paused: bool = False


@dataclass(frozen=True)
class _Entry:
    tables: tuple
    fingerprint: tuple
    body: bytes
    status_code: int
    media_type: str
    refusal: str | None = None


_TOKEN = re.compile(r'[a-z_][a-z0-9_]*')
# table name -> data type of its case_id column, or None when it has none
_tables_cache: dict = {}


def _load_tables(connection):
    """Every base table in the database (mapped or not) and its case_id type. Read once per process."""
    if not _tables_cache:
        rows = connection.execute(text(
            "SELECT t.table_name, max(CASE WHEN c.column_name = 'case_id' THEN c.data_type END) "
            "FROM information_schema.tables t JOIN information_schema.columns c "
            "ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema = current_schema() AND t.table_type = 'BASE TABLE' GROUP BY t.table_name")).all()
        _tables_cache.update(rows)
    return _tables_cache


def _mapped_tables():
    return _tables_cache


def _dbapi(connection):
    try:
        return connection.connection.dbapi_connection
    except Exception:  # noqa: BLE001 - a closed or invalidated connection is not the owner
        return None


@event.listens_for(Engine, 'before_cursor_execute')
def _record_tables(conn, cursor, statement, parameters, context, executemany):
    recording = _recording.get()
    if recording is None or recording.paused:
        return
    known = _mapped_tables()
    recording.tables.update(token for token in _TOKEN.findall(statement.lower()) if token in known)


@event.listens_for(Engine, 'begin')
def _join_snapshot(conn):
    recording = _recording.get()
    if recording is None or _dbapi(conn) is recording.owner:
        return
    conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    conn.exec_driver_sql(f"SET TRANSACTION SNAPSHOT '{recording.snapshot}'")
    conn.exec_driver_sql('SET TRANSACTION READ ONLY')


def fingerprint(connection, tables, case_id):
    """(table, rows, md5 of the sorted xmin of those rows) per table; None when a table cannot be checked.

    Rows are the case's rows (case_id), or the whole table when it has no case_id and is small. A row
    inserted or updated since the last fingerprint carries the xid of a transaction that had not committed
    then, so the sorted xmin list differs; a delete changes the count. (A sum of xmin could balance out.)
    """
    known = _mapped_tables()
    result = []
    try:
        with connection.begin_nested():
            for table in sorted(tables):
                case_type = known.get(table)
                if case_type is not None:
                    parameter = case_id if case_type == 'uuid' else str(case_id)
                    rows, digest = connection.execute(text(
                        f'SELECT count(*), md5(coalesce(string_agg(xmin::text, \',\' ORDER BY xmin::text::bigint), \'\')) '
                        f'FROM "{table}" WHERE case_id = :case_id'), dict(case_id=parameter)).one()
                else:
                    size = connection.execute(text("SELECT pg_relation_size(to_regclass(:name))"), dict(name=table)).scalar()
                    if size is None or size > MAX_UNSCOPED_BYTES:
                        return None
                    rows, digest = connection.execute(text(
                        f'SELECT count(*), md5(coalesce(string_agg(xmin::text, \',\' ORDER BY xmin::text::bigint), \'\')) '
                        f'FROM "{table}"')).one()
                result.append((table, int(rows), digest))
    except Exception:  # noqa: BLE001 - a table that cannot be checked means the view is simply not reused
        logger.warning('Financial view fingerprint unavailable for %s', ', '.join(sorted(tables)), exc_info=True)
        return None
    return tuple(result)


class _KeyLock:
    """One computation per view key at a time; the entry is dropped once nobody holds or waits for it."""

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        with _lock:
            lock, users = _key_locks.get(self.key, (threading.Lock(), 0))
            _key_locks[self.key] = (lock, users + 1)
        lock.acquire()
        self.lock = lock

    def __exit__(self, *exc):
        self.lock.release()
        with _lock:
            lock, users = _key_locks[self.key]
            if users <= 1:
                del _key_locks[self.key]
            else:
                _key_locks[self.key] = (lock, users - 1)


def _cost(key, entry):
    """Memory an entry holds: its body plus key, table names and fingerprint, with a fixed allowance per object."""
    return (len(entry.body) + len(entry.refusal or '') + len(key[0]) + len(key[1]) + 1024
            + sum(len(table) + 128 for table in entry.tables) + 256 * len(entry.fingerprint))


def _store(key, entry):
    global _total_bytes
    with _lock:
        old = _entries.pop(key, None)
        if old is not None:
            _total_bytes -= _cost(key, old)
        _entries[key] = entry
        _total_bytes += _cost(key, entry)
        while (_total_bytes > MAX_TOTAL_BYTES or len(_entries) > MAX_ENTRIES) and _entries:
            evicted_key, evicted = _entries.popitem(last=False)
            _total_bytes -= _cost(evicted_key, evicted)


def _lookup(key):
    with _lock:
        entry = _entries.get(key)
        if entry is not None:
            _entries.move_to_end(key)
        return entry


def in_snapshot():
    """True while a cached view computes: every row read now is a committed row version of its snapshot."""
    recording = _recording.get()
    return recording is not None and not recording.paused


def row_versions(session, table, ids):
    """{id: xmin} of rows of ``table`` in the computing view's snapshot (in_snapshot() only).

    A row's id and xmin name one committed version of it: any later update is a new version with the xmin of
    another transaction (two updates in one transaction leave only the last version visible to anyone)."""
    ids = list(ids)
    if not ids:
        return {}
    rows = session.execute(text(f'SELECT id, xmin::text FROM "{table}" WHERE id = ANY(:ids)'), dict(ids=ids)).all()
    return {row[0]: row[1] for row in rows}


class VersionMemo:
    """A value computed from fixed row versions only (see row_versions), reused while those versions are current.

    Filled only inside a computing view's read-only snapshot, so no uncommitted or in-request change is ever
    stored. Bounded; least recently used entries go first. Callers get a deep copy, never the stored value."""

    def __init__(self, name, max_entries):
        self.name, self.max_entries = name, max_entries
        self._values: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.stats = dict(hits=0, misses=0)

    def has(self, key):
        with self._lock:
            return key is not None and key in self._values

    def get(self, key, compute):
        from copy import deepcopy
        with self._lock:
            found = self._values.get(key, _MISSING)
            if found is not _MISSING:
                self._values.move_to_end(key)
                self.stats['hits'] += 1
                return deepcopy(found)
            self.stats['misses'] += 1
        value = compute()
        with self._lock:
            self._values[key] = deepcopy(value)
            self._values.move_to_end(key)
            while len(self._values) > self.max_entries:
                self._values.popitem(last=False)
        return value

    def clear(self):
        with self._lock:
            self._values.clear()


_MISSING = object()


def clear():
    global _total_bytes
    with _lock:
        _entries.clear()
        _key_locks.clear()
        _total_bytes = 0


def _parameter(value):
    if isinstance(value, (list, tuple)):
        return [_parameter(item) for item in value]
    return None if value is None else str(value)


def _response(entry):
    from fastapi.responses import Response
    return Response(content=entry.body, status_code=entry.status_code, media_type=entry.media_type)


def _encoded_class():
    from fastapi.responses import JSONResponse

    class Encoded(JSONResponse):
        """A JSONResponse whose content is already its encoded body."""
        def render(self, content):
            return content
    return Encoded


def _json_response(result):
    """FastAPI's own response for this result, without its slow pass over plain JSON.

    jsonable_encoder walks every value in Python (13.8 s for one case's 61 MB payment list) and changes
    nothing in data that is already JSON: dicts, lists, strings, numbers, booleans and None. json.dumps with
    JSONResponse's settings writes those bytes directly and refuses (TypeError) anything else, which then
    takes FastAPI's full path.
    """
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse
    try:
        body = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=None, separators=(',', ':')).encode('utf-8')
    except TypeError:
        return JSONResponse(content=jsonable_encoder(result))
    if b'"_sa' in body:
        # jsonable_encoder drops dict keys starting with "_sa" (SQLAlchemy state); keep its exact output.
        return JSONResponse(content=jsonable_encoder(result))
    global _Encoded
    if _Encoded is None:
        _Encoded = _encoded_class()
    return _Encoded(content=body)


def cached_view(name):
    """Decorate a synchronous route handler that has ``case_id`` and ``db`` parameters."""
    def decorate(handler):
        @functools.wraps(handler)
        def wrapper(*args, **kwargs):
            db, case_id = kwargs.get('db'), kwargs.get('case_id')
            if args or db is None or case_id is None or not hasattr(db, 'get_bind') or _recording.get() is not None:
                return handler(*args, **kwargs)
            engine = db.get_bind()
            if getattr(getattr(engine, 'dialect', None), 'name', None) != 'postgresql':
                return handler(*args, **kwargs)
            key = (name, json.dumps({k: _parameter(v) for k, v in kwargs.items() if k != 'db'}, sort_keys=True))
            # The access check ran in the session's own transaction. End it, which returns its connection to
            # the pool, before waiting: a request waiting for the same view holds no connection.
            db.rollback()
            state = dict(handler_started=False)
            try:
                with _KeyLock(key):
                    return _serve(handler, key, engine, case_id, kwargs, state)
            except Exception:
                if state['handler_started']:
                    raise
                # The reuse machinery itself failed (connection, snapshot, table list): answer as if it were absent,
                # so the route's own error handling and messages apply.
                logger.warning('Financial view reuse unavailable for %s; computing directly', name, exc_info=True)
                return handler(*args, **kwargs)
        return wrapper
    return decorate


def _serve(handler, key, engine, case_id, kwargs, state):
    from fastapi.responses import Response
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from sqlalchemy.orm import Session
    started = time.perf_counter()
    # One connection for the whole view, as before: the snapshot owner is also the handler's session
    # connection (the session works in a savepoint of the owner's transaction).
    with engine.connect() as owner:
        owner = owner.execution_options(isolation_level='REPEATABLE READ')
        with owner.begin():
            owner.exec_driver_sql('SET TRANSACTION READ ONLY')
            snapshot = owner.exec_driver_sql('SELECT pg_export_snapshot()').scalar()
            _load_tables(owner)
            entry = _lookup(key)
            if entry is not None and fingerprint(owner, entry.tables, case_id) == entry.fingerprint:
                stats['hits'] += 1
                logger.info('Financial view %s served unchanged (%.2f s)', key[0], time.perf_counter() - started)
                if entry.refusal is not None:
                    from fastapi import HTTPException
                    state['handler_started'] = True
                    raise HTTPException(status_code=422, detail=entry.refusal)
                return _response(entry)
            stats['misses'] += 1
            recording = _Recording(owner=_dbapi(owner), snapshot=snapshot)
            token = _recording.set(recording)
            session = Session(bind=owner, autoflush=False, join_transaction_mode='create_savepoint')
            refusal = None
            try:
                state['handler_started'] = True
                with _CollectorPaused():
                    try:
                        result = handler(**{**kwargs, 'db': session})
                    except StarletteHTTPException as exc:
                        refusal = exc
                    else:
                        # Lazy loads while encoding still belong to this snapshot and are recorded.
                        response = result if isinstance(result, Response) else _json_response(result)
            finally:
                recording.paused = True
                _recording.reset(token)
                session.close()
            if refusal is not None:
                # Only the route's plain 422 with a text reason: the same rows give the same refusal.
                tables = tuple(sorted(recording.tables))
                if refusal.status_code == 422 and refusal.headers is None and isinstance(refusal.detail, str) and tables:
                    current = fingerprint(owner, tables, case_id)
                    if current is not None:
                        _store(key, _Entry(tables, current, b'', 422, 'application/json', refusal=refusal.detail))
                        stats['stored'] += 1
                        logger.info('Financial view %s refusal kept (%.2f s, %d tables)', key[0],
                                    time.perf_counter() - started, len(tables))
                        raise refusal
                stats['not_stored'] += 1
                raise refusal
            # Only plain results encoded here are kept: a handler's own Response may carry headers of its own.
            if isinstance(result, Response) or response.status_code != 200:
                stats['not_stored'] += 1
                return response
            tables = tuple(sorted(recording.tables))
            current = fingerprint(owner, tables, case_id) if tables else None
            if current is None or len(response.body) > MAX_ENTRY_BYTES:
                stats['not_stored'] += 1
                return response
            _store(key, _Entry(tables, current, bytes(response.body), response.status_code, response.media_type))
            stats['stored'] += 1
            logger.info('Financial view %s computed (%.2f s, %d bytes, %d tables)', key[0],
                        time.perf_counter() - started, len(response.body), len(tables))
            return response
