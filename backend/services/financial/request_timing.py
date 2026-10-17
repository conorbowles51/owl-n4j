"""Per-request stage timing for financial reads, reported as Server-Timing.

A request opens a recorder with `recording()`; service code marks stages with
`stage(name)`. Outside a recorder `stage` costs one context-variable lookup, so
workers and tests are unaffected. Stage names are fixed identifiers chosen in
code; no case, file or financial values are ever recorded.
"""
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

log = logging.getLogger(__name__)
_current = ContextVar('financial_request_timing', default=None)
_TOKEN = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')


class Recorder:
    def __init__(self):
        self.started = time.perf_counter()
        self.stages = {}
        self.counts = {}

    def add(self, name, seconds):
        self.stages[name] = self.stages.get(name, 0.0) + seconds

    def lap(self, name):
        """Time since the previous lap (or the start) is added to `name`."""
        now = time.perf_counter()
        self.add(name, now - getattr(self, 'last', self.started))
        self.last = now

    def count(self, name, value=1):
        self.counts[name] = self.counts.get(name, 0) + value

    def total(self):
        return time.perf_counter() - self.started

    def header(self):
        parts = [f'{name};dur={seconds * 1000:.1f}' for name, seconds in self.stages.items()]
        parts.append(f'total;dur={self.total() * 1000:.1f}')
        return ', '.join(parts)


@contextmanager
def recording():
    recorder = Recorder()
    token = _current.set(recorder)
    try:
        yield recorder
    finally:
        _current.reset(token)


@contextmanager
def stage(name):
    recorder = _current.get()
    if recorder is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        recorder.add(name, time.perf_counter() - started)


def lap(name):
    """Close a step of a sequential operation (see Recorder.lap); free outside a recorder."""
    recorder = _current.get()
    if recorder is not None:
        recorder.lap(name)


def summary(recorder):
    """'total 2.31 s: claim 0.010, ...' with fixed step names only (no case or financial values)."""
    steps = ', '.join(f'{name} {seconds:.3f}' for name, seconds in recorder.stages.items())
    counts = ', '.join(f'{name} {value}' for name, value in recorder.counts.items())
    return f'total {recorder.total():.2f} s: {steps}' + (f'; {counts}' if counts else '')


_SQL_COUNTED = []


def count_sql():
    """Count, inside a recorder, the SQL statements sent (``sql``) and the writes among them (``sql_writes``).

    One listener for every engine, registered once; outside a recorder it
    costs one context-variable lookup per statement.
    """
    if _SQL_COUNTED:
        return
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    def counted(conn, cursor, statement, parameters, context, executemany):
        recorder = _current.get()
        if recorder is None:
            return
        recorder.count('sql')
        if statement.lstrip()[:6].upper() in ('INSERT', 'UPDATE', 'DELETE'):
            recorder.count('sql_writes')
    event.listen(Engine, 'after_cursor_execute', counted)
    _SQL_COUNTED.append(counted)


def count(name, value=1):
    recorder = _current.get()
    if recorder is not None:
        recorder.count(name, value)


def request_id(incoming=None):
    """Reuse a well-formed client correlation id, otherwise mint one."""
    if incoming and _TOKEN.match(incoming):
        return incoming
    return uuid4().hex


class FinancialTimingMiddleware:
    """Correlation id and Server-Timing for financial batch endpoints.

    Pure ASGI, so the recorder reaches synchronous endpoints run in the thread
    pool. Reuses a well-formed incoming X-Request-ID or mints one, returns it,
    and logs one line per request with status and stage durations only.
    """

    def __init__(self, app, prefix='/api/financial/statement-import/batches'):
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or not scope.get('path', '').startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get('headers') or []).get(b'x-request-id')
        identifier = request_id(incoming.decode('latin-1') if incoming else None)
        recorder = Recorder()
        token = _current.set(recorder)
        outcome = {}

        async def send_with_timing(message):
            if message['type'] == 'http.response.start':
                outcome['status'] = message['status']
                headers = list(message.get('headers') or [])
                headers.append((b'x-request-id', identifier.encode('latin-1')))
                headers.append((b'server-timing', recorder.header().encode('latin-1')))
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_timing)
        finally:
            _current.reset(token)
            log.info('financial request id=%s method=%s path=%s status=%s total_ms=%.1f stages=%s counts=%s',
                     identifier, scope.get('method'), scope.get('path'), outcome.get('status'),
                     recorder.total() * 1000, {k: round(v * 1000, 1) for k, v in recorder.stages.items()},
                     recorder.counts)
