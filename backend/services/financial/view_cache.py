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

# Its INFO lines (served unchanged / from the saved copy / computed, with times) reach the service journal, so a
# slow first load can be explained from the journal.
from services.financial.journal import journal  # noqa: E402
logger = journal(__name__)

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
stats = dict(hits=0, misses=0, stored=0, not_stored=0, saved_hits=0)
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
    keep: bool = True


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


def not_kept():
    """Called by a view whose answer is shown but incomplete for a passing reason (a lookup that failed): the answer
    is returned as computed and not kept, so the next request computes it again. No effect outside a cached view."""
    recording = _recording.get()
    if recording is not None:
        recording.keep = False


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
    stored. Bounded; least recently used entries go first. Callers get a deep copy, never the stored value.

    With ``decode`` (stored JSON -> value), values are also saved to disk and survive a restart, under the same
    row-version keys, and only for the same database and the same code and settings: the store names the
    database's system identifier and ``code_identity`` (every backend file, the Python version, every installed
    library and the process environment, taken when the process loaded its code), so a release, a changed
    setting or another database starts empty. A row's (id, xmin) names one version only while transaction ids
    have not wrapped around and the database has not been restored to an earlier point, so values are saved and
    reused only while the transaction counter is below 2**32 and not below the highest one the store has seen. A value is saved only if it comes back from JSON exactly as computed. ``bind`` (inside the
    view's snapshot) loads the saved values; ``flush`` writes the new ones."""

    def __init__(self, name, max_entries, decode=None):
        self.name, self.max_entries = name, max_entries
        self._values: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.stats = dict(hits=0, misses=0, saved_hits=0)
        self._decode = decode
        self._scope = None
        self._saved: dict = {}
        self._saved_stamp = None
        self._pending: dict = {}
        self._xmax = None
        self._saved_xmax = None

    def has(self, key):
        with self._lock:
            return key is not None and (key in self._values or (self._scope is not None and _memo_key(key) in self._saved))

    def get(self, key, compute):
        from copy import deepcopy
        with self._lock:
            found = self._values.get(key, _MISSING)
            if found is not _MISSING:
                self._values.move_to_end(key)
                self.stats['hits'] += 1
                return deepcopy(found)
            if self._scope is not None:
                saved = self._saved.get(_memo_key(key), _MISSING)
                if saved is not _MISSING:
                    found = self._decode(deepcopy(saved))
                    self._remember(key, found)
                    self.stats['saved_hits'] += 1
                    return deepcopy(found)
            self.stats['misses'] += 1
        value = compute()
        with self._lock:
            self._remember(key, deepcopy(value))
            if self._scope is not None:
                encoded = _exact_json(value, self._decode)
                if encoded is not _MISSING:
                    self._pending[_memo_key(key)] = encoded
        return value

    def _remember(self, key, value):
        self._values[key] = value
        self._values.move_to_end(key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)

    def bind(self, session):
        """Inside a computing view's snapshot: use the values saved for this database and this code, if any."""
        scope = None
        directory = _memo_dir()
        if self._decode is not None and directory is not None and in_snapshot():
            try:
                database, xmax = session.execute(text('SELECT (SELECT system_identifier::text FROM pg_control_system()), '
                    'pg_snapshot_xmax(pg_current_snapshot())::text')).one()
                if int(xmax) < MEMO_XID_LIMIT and code_identity() is not None:
                    scope = dict(format=1, memo=self.name, database=database, code=code_identity())
                    xmax = int(xmax)
            except Exception:
                logger.warning('Saved %s values unavailable; computing in memory only', self.name, exc_info=True)
        with self._lock:
            self._scope = scope
            # The highest transaction mark any bind has seen: an older snapshot binding later must not lower it.
            self._xmax = max(xmax, self._xmax or 0) if scope is not None else None
            if scope is None:
                self._pending.clear()
                return
            try:
                path = directory / (self.name + '.json')
                stat = path.stat()
                stamp = (stat.st_mtime_ns, stat.st_size, json.dumps(scope, sort_keys=True))
                if stamp != self._saved_stamp:
                    document = json.loads(path.read_text(encoding='utf-8'))
                    current = _current(document, scope, xmax)
                    self._saved = dict(document['entries']) if current else {}
                    self._saved_xmax = document['xmax'] if current else None
                    self._saved_stamp = stamp
                if self._saved_xmax is not None and self._saved_xmax > xmax:
                    self._saved, self._saved_xmax, self._saved_stamp = {}, None, None
            except FileNotFoundError:
                self._saved, self._saved_xmax, self._saved_stamp = {}, None, None
            except Exception:
                logger.warning('Saved %s values unreadable; computing them again', self.name, exc_info=True)
                self._saved, self._saved_xmax, self._saved_stamp = {}, None, None

    def flush(self):
        """Save the values computed since ``bind`` (merged with what other processes saved). Never raises."""
        import fcntl
        import os
        with self._lock:
            scope, xmax, pending = self._scope, self._xmax, dict(self._pending)
            self._pending.clear()
        directory = _memo_dir()
        if scope is None or not pending or directory is None:
            return
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / (self.name + '.json')
            with open(directory / (self.name + '.lock'), 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                # Under the lock no other writer is mid-write: a temporary file left now was left by a killed one.
                for left in directory.glob(self.name + '.json.*.tmp'):
                    left.unlink(missing_ok=True)
                entries, seen = {}, xmax
                try:
                    document = json.loads(path.read_text(encoding='utf-8'))
                    if _current(document, scope, xmax):
                        entries, seen = dict(document['entries']), max(xmax, document['xmax'])
                except FileNotFoundError:
                    pass
                except Exception:
                    logger.warning('Saved %s values unreadable; replacing them', self.name, exc_info=True)
                for key, value in pending.items():
                    entries.pop(key, None)
                    entries[key] = value
                kept = list(entries.items())[-self.max_entries:]
                temporary = path.with_name(path.name + '.%d.tmp' % os.getpid())
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as out:
                    json.dump(dict(scope=scope, xmax=seen, entries=kept), out, ensure_ascii=False, separators=(',', ':'))
                os.replace(temporary, path)
                stat = path.stat()
            with self._lock:
                if self._scope == scope:
                    self._saved, self._saved_xmax = dict(kept), seen
                    self._saved_stamp = (stat.st_mtime_ns, stat.st_size, json.dumps(scope, sort_keys=True))
        except Exception:
            logger.warning('Could not save %s values; they stay in memory only', self.name, exc_info=True)

    def clear(self):
        with self._lock:
            self._values.clear()
            self._saved, self._saved_xmax, self._saved_stamp, self._scope = {}, None, None, None
            self._pending.clear()


# Below this many transactions a row version's xmin is unique in the database's life (no wraparound yet).
MEMO_XID_LIMIT = 2 ** 32


def _memo_dir():
    """Where values survive a restart: FINANCIAL_VIEW_MEMO_DIR, else the user's cache; empty turns it off."""
    import os
    from pathlib import Path
    configured = os.environ.get('FINANCIAL_VIEW_MEMO_DIR')
    if configured is not None:
        return Path(configured) if configured else None
    return Path.home() / '.cache' / 'loupe-financial-view-memo'


# Set by systemd (or the shell) anew for every start; nothing in Loupe reads them.
_VOLATILE_ENVIRONMENT = frozenset(('INVOCATION_ID', 'JOURNAL_STREAM', 'SYSTEMD_EXEC_PID', 'MANAGERPID', 'LISTEN_PID',
    'LISTEN_FDS', 'LISTEN_FDNAMES', 'WATCHDOG_PID', 'WATCHDOG_USEC', 'NOTIFY_SOCKET', '_', 'OLDPWD', 'SHLVL', 'PWD'))


def _identity_now():
    """sha256 over every backend file (code, data and configuration files; tests and logs aside), the Python
    version, every installed library and the process environment. None if any of it cannot be read."""
    import hashlib
    import os
    import sys
    from importlib import metadata
    from pathlib import Path
    try:
        root = Path(__file__).resolve().parents[2]
        digest = hashlib.sha256(sys.version.encode())
        for line in sorted(f"{dist.metadata['Name']}=={dist.version}" for dist in metadata.distributions()):
            digest.update(line.encode() + b'\n')
        for name, value in sorted(os.environ.items()):
            if name not in _VOLATILE_ENVIRONMENT:
                digest.update(b'env\0' + name.encode() + b'\0' + value.encode('utf-8', 'surrogateescape') + b'\n')
        files = []
        for folder, folders, names in os.walk(root):
            folders[:] = [name for name in folders if not name.startswith('.') and name not in ('__pycache__', 'tests', 'logs')]
            files.extend(Path(folder) / name for name in names if not name.startswith('.') and not name.endswith('.pyc'))
        for path in sorted(files, key=lambda path: path.relative_to(root).as_posix()):
            digest.update(path.relative_to(root).as_posix().encode() + b'\0' + hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()
    except Exception:
        logger.warning('Code identity unavailable; Financial view values are kept in memory only', exc_info=True)
        return None


# Taken once, when this process loads its code (services.financial imports every module at start), never later:
# a release rewrites the files under a running process before restarting it, and that process must not save its
# values under the new release's identity.
_code_identity = _identity_now()


def code_identity():
    return _code_identity


def _current(document, scope, xmax):
    """Saved values belong to this database and code, and the database has not gone back in time since: a restore
    of an earlier backup keeps the system identifier but hands out transaction ids it handed out before, so a
    saved (id, xmin) could then name a different row version. ``xmax`` only grows on a database that has not."""
    return document.get('scope') == scope and type(document.get('xmax')) is int and document['xmax'] <= xmax


def _memo_key(key):
    return json.dumps(key, default=str, ensure_ascii=False, separators=(',', ':'))


def _exact_json(value, decode):
    """The JSON form of ``value`` if decoding it gives back exactly ``value`` (types included), else _MISSING."""
    try:
        encoded = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return encoded if _same(decode(json.loads(json.dumps(encoded))), value) else _MISSING
    except (TypeError, ValueError):
        return _MISSING


def _same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return list(left) == list(right) and all(_same(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    return left == right


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


class ModelOutput(dict):
    """A route's response-model output (``Model.model_validate(...).model_dump(mode='json')``). FastAPI serialised
    it with pydantic, which keeps dict keys starting with "_sa", so json_response keeps them too."""


def json_response(result):
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
    if b'"_sa' in body and not isinstance(result, ModelOutput):
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
                return _kept(entry, state)
            scope, xmax = _saved_scope(owner)
            saved = _load_saved(key, scope, xmax) if scope is not None else None
            if saved is not None and saved != entry and fingerprint(owner, saved.tables, case_id) == saved.fingerprint:
                _store(key, saved)
                stats['saved_hits'] += 1
                logger.info('Financial view %s served from the saved copy (%.2f s)', key[0], time.perf_counter() - started)
                return _kept(saved, state)
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
                        response = result if isinstance(result, Response) else json_response(result)
            finally:
                recording.paused = True
                _recording.reset(token)
                session.close()
            if not recording.keep:
                stats['not_stored'] += 1
                if refusal is not None:
                    raise refusal
                return response
            if refusal is not None:
                # Only the route's plain 422 with a text reason: the same rows give the same refusal.
                tables = tuple(sorted(recording.tables))
                if refusal.status_code == 422 and refusal.headers is None and isinstance(refusal.detail, str) and tables:
                    current = fingerprint(owner, tables, case_id)
                    if current is not None:
                        kept = _Entry(tables, current, b'', 422, 'application/json', refusal=refusal.detail)
                        _store(key, kept)
                        stats['stored'] += 1
                        _save_if_slow(key, kept, scope, xmax, started)
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
            kept = _Entry(tables, current, bytes(response.body), response.status_code, response.media_type)
            _store(key, kept)
            stats['stored'] += 1
            logger.info('Financial view %s computed (%.2f s, %d bytes, %d tables)', key[0],
                        time.perf_counter() - started, len(response.body), len(tables))
            _save_if_slow(key, kept, scope, xmax, started)
            return response


def _kept(entry, state):
    """A kept entry's answer: its response, or its refusal raised again with the same text."""
    if entry.refusal is not None:
        from fastapi import HTTPException
        state['handler_started'] = True
        raise HTTPException(status_code=422, detail=entry.refusal)
    return _response(entry)


# Views that took at least this long to compute are also saved to disk (_save_if_slow), so the other worker
# processes and the next start reuse them instead of computing them again; the saved copies take at most
# MAX_SAVED_BYTES, oldest removed first.
SAVE_MIN_SECONDS = 1.0
MAX_SAVED_BYTES = 1024 * 1024 * 1024


def _saved_dir():
    directory = _memo_dir()
    return None if directory is None else directory / 'views'


def _saved_scope(connection):
    """(scope, xmax) under which this snapshot may read and save views on disk, or (None, None).

    The same rules as VersionMemo's saved values: one database (its system identifier) and one code identity
    (a release, a changed setting or another database starts empty), and only while the transaction counter is
    below 2**32 and not below the one a saved view was computed at, so a fingerprint's xmin values still name
    the same row versions. ``xmax`` is this snapshot's own."""
    if _saved_dir() is None or code_identity() is None:
        return None, None
    try:
        with connection.begin_nested():
            database, xmax = connection.execute(text('SELECT (SELECT system_identifier::text FROM pg_control_system()), '
                'pg_snapshot_xmax(pg_current_snapshot())::text')).one()
    except Exception:  # noqa: BLE001 - views are then reused in memory only
        logger.warning('Saved Financial views unavailable; reusing views in memory only', exc_info=True)
        return None, None
    xmax = int(xmax)
    if xmax >= MEMO_XID_LIMIT:
        return None, None
    return dict(format=1, database=database, code=code_identity()), xmax


def _saved_path(key, scope):
    import hashlib
    name = hashlib.sha256(json.dumps([list(key), scope], sort_keys=True).encode()).hexdigest()
    return _saved_dir() / (name + '.view')


def _load_saved(key, scope, xmax):
    """The entry saved for this key, database and code, if it was computed no later than this snapshot and the
    store has never seen a later transaction counter (a database restored to an earlier point). Its fingerprint
    is still to be compared in this snapshot. Never raises."""
    import hashlib
    try:
        if xmax < _saved_high_water():
            return None
        with open(_saved_path(key, scope), 'rb') as saved:
            header = json.loads(saved.readline())
            if (header.get('scope') != scope or header.get('key') != list(key) or type(header.get('xmax')) is not int
                    or header['xmax'] > xmax):
                return None
            body = saved.read()
        if header.get('size') != len(body) or header.get('sha256') != hashlib.sha256(body).hexdigest():
            return None
        return _Entry(tuple(header['tables']), tuple(tuple(part) for part in header['fingerprint']), body,
                      header['status_code'], header['media_type'], header.get('refusal'))
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - an unreadable copy is computed again
        logger.warning('Saved Financial view %s unreadable; computing it again', key[0], exc_info=True)
        return None


def _saved_high_water():
    """The highest transaction counter any saved view was computed at (0 if none)."""
    try:
        return int((_saved_dir() / 'xmax').read_text())
    except FileNotFoundError:
        return 0


def _raise_high_water(directory, xmax):
    import fcntl
    import os
    with open(directory / 'xmax.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            seen = int((directory / 'xmax').read_text())
        except (FileNotFoundError, ValueError):
            seen = 0
        if xmax > seen:
            temporary = directory / ('xmax.%d.tmp' % os.getpid())
            temporary.write_text(str(xmax))
            os.replace(temporary, directory / 'xmax')


def _save_if_slow(key, entry, scope, xmax, started):
    """Save a slow view's entry for the other workers and the next start. Never raises."""
    import hashlib
    import os
    if scope is None or time.perf_counter() - started < SAVE_MIN_SECONDS or len(entry.body) > MAX_SAVED_BYTES:
        return
    temporary = None
    try:
        directory = _saved_dir()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        _raise_high_water(directory, xmax)
        path = _saved_path(key, scope)
        header = dict(scope=scope, key=list(key), xmax=xmax, tables=list(entry.tables),
                      fingerprint=[list(part) for part in entry.fingerprint], status_code=entry.status_code,
                      media_type=entry.media_type, refusal=entry.refusal, size=len(entry.body),
                      sha256=hashlib.sha256(entry.body).hexdigest())
        temporary = path.with_name('%s.%d.%d.tmp' % (path.name, os.getpid(), threading.get_ident()))
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'wb') as out:
            out.write(json.dumps(header, ensure_ascii=True, separators=(',', ':')).encode() + b'\n')
            out.write(entry.body)
        os.replace(temporary, path)
        temporary = None
    except Exception:  # noqa: BLE001 - the view stays reused in memory
        logger.warning('Could not save Financial view %s; it stays in memory only', key[0], exc_info=True)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        return
    try:
        _trim_saved(directory, keep=path)
    except Exception:  # noqa: BLE001
        logger.warning('Could not trim saved Financial views', exc_info=True)


def _trim_saved(directory, keep):
    """Oldest saved views first, until the rest fit MAX_SAVED_BYTES; temporary files left over an hour ago
    (by a killed writer) go too. The copy just written is kept."""
    files = []
    now = time.time()
    for path in directory.iterdir():
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if path.name.endswith('.tmp'):
            if now - stat.st_mtime > 3600:
                path.unlink(missing_ok=True)
        elif path.name.endswith('.view'):
            files.append((stat.st_mtime_ns, stat.st_size, path))
    total = sum(size for _, size, _ in files)
    for _, size, path in sorted(files):
        if total <= MAX_SAVED_BYTES:
            break
        if path != keep:
            path.unlink(missing_ok=True)
            total -= size
