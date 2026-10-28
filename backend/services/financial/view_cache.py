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
  the sum of ``xmin`` of this case's rows; for any other table, the same over the whole table. Any insert,
  update or delete of a row in scope changes the count or brings a newer ``xmin``, so it changes the
  fingerprint. Freezing keeps ``xmin``, so vacuum does not.
* A later request takes the fingerprint of the same tables in its own snapshot; only an equal fingerprint
  returns the stored bytes. Otherwise the view is computed again. Nothing is ever invalidated by hand, so
  no write path (imports, labels, categories, identities, notes) can be forgotten.

Not stored: errors, non-JSON responses, views that read a large table without ``case_id`` (the check would
cost more than it saves), and anything over the size limits. Off on databases other than PostgreSQL.
Views whose result depends on anything besides these tables and their parameters (the clock, files, the
graph database, other threads) must not use this.
"""
from __future__ import annotations

import functools
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
MAX_TOTAL_BYTES = 640 * 1024 * 1024
# A table without case_id is fingerprinted whole; above this size a view reading it is not stored.
MAX_UNSCOPED_BYTES = 64 * 1024 * 1024

_recording: ContextVar['_Recording | None'] = ContextVar('financial_view_cache_recording', default=None)
_lock = threading.Lock()
_entries: OrderedDict = OrderedDict()
_total_bytes = 0
_key_locks: dict = {}
stats = dict(hits=0, misses=0, stored=0, not_stored=0)


@dataclass
class _Recording:
    owner: object
    snapshot: str
    tables: set = field(default_factory=set)


@dataclass(frozen=True)
class _Entry:
    tables: tuple
    fingerprint: tuple
    body: bytes
    status_code: int
    media_type: str


_TOKEN = re.compile(r'[a-z_][a-z0-9_]*')
_tables_cache: dict = {}


def _load_tables(connection):
    """Every base table in the database (mapped or not), and whether it has case_id. Read once per process."""
    if not _tables_cache:
        rows = connection.execute(text(
            "SELECT t.table_name, bool_or(c.column_name = 'case_id') FROM information_schema.tables t "
            "JOIN information_schema.columns c ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
            "WHERE t.table_schema = current_schema() AND t.table_type = 'BASE TABLE' GROUP BY t.table_name")).all()
        _tables_cache.update((name, bool(scoped)) for name, scoped in rows)
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
    if recording is None or _dbapi(conn) is recording.owner:
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
    """(table, rows, sum of xmin) per table, or None when a table is too large to check without case_id."""
    known = _mapped_tables()
    result = []
    for table in sorted(tables):
        if known.get(table):
            rows, total = connection.execute(text(
                f'SELECT count(*), coalesce(sum(xmin::text::bigint), 0) FROM "{table}" WHERE case_id = :case_id'),
                dict(case_id=case_id)).one()
        else:
            size = connection.execute(text("SELECT pg_relation_size(to_regclass(:name))"), dict(name=table)).scalar()
            if size is None or size > MAX_UNSCOPED_BYTES:
                return None
            rows, total = connection.execute(text(
                f'SELECT count(*), coalesce(sum(xmin::text::bigint), 0) FROM "{table}"')).one()
        result.append((table, int(rows), int(total)))
    return tuple(result)


def _key_lock(key):
    with _lock:
        return _key_locks.setdefault(key, threading.Lock())


def _store(key, entry):
    global _total_bytes
    with _lock:
        old = _entries.pop(key, None)
        if old is not None:
            _total_bytes -= len(old.body)
        _entries[key] = entry
        _total_bytes += len(entry.body)
        while _total_bytes > MAX_TOTAL_BYTES and _entries:
            _, evicted = _entries.popitem(last=False)
            _total_bytes -= len(evicted.body)


def _lookup(key):
    with _lock:
        entry = _entries.get(key)
        if entry is not None:
            _entries.move_to_end(key)
        return entry


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
            with _key_lock(key):
                return _serve(handler, key, engine, db, case_id, kwargs)
        return wrapper
    return decorate


def _serve(handler, key, engine, db, case_id, kwargs):
    from fastapi.encoders import jsonable_encoder
    from fastapi.responses import JSONResponse, Response
    # The access check ran in the session's own transaction; end it so this view's reads begin in the snapshot.
    db.rollback()
    started = time.perf_counter()
    with engine.connect() as owner:
        owner = owner.execution_options(isolation_level='REPEATABLE READ')
        with owner.begin():
            owner.exec_driver_sql('SET TRANSACTION READ ONLY')
            snapshot = owner.exec_driver_sql('SELECT pg_export_snapshot()').scalar()
            if not _load_tables(owner):
                return handler(**kwargs)
            entry = _lookup(key)
            if entry is not None and fingerprint(owner, entry.tables, case_id) == entry.fingerprint:
                stats['hits'] += 1
                logger.info('Financial view %s served unchanged (%.2f s)', key[0], time.perf_counter() - started)
                return _response(entry)
            stats['misses'] += 1
            recording = _Recording(owner=_dbapi(owner), snapshot=snapshot)
            token = _recording.set(recording)
            try:
                result = handler(**kwargs)
                # Lazy loads after the handler returns still belong to this snapshot.
                response = result if isinstance(result, Response) else JSONResponse(content=jsonable_encoder(result))
            finally:
                _recording.reset(token)
                db.rollback()
            if type(response) is not JSONResponse or response.status_code != 200:
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
