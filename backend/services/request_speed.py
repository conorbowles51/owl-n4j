"""How long requests take, kept permanently: every /api request and every Financial page view.

The request path only appends a tuple to an in-process queue (``RequestSpeedMiddleware``).
A daemon thread per worker process drains the queue every ``FLUSH_SECONDS`` and adds it to
Postgres (migration ``20261028_request_speed``):

* ``request_speed_hourly``: one row per hour, kind, method, route template, case and person,
  with count, total and max time, bytes, server errors and a duration histogram. The
  histogram (``BUCKET_EDGES_MS``, 15% wide buckets) is what makes p50 and p95 mergeable across
  flushes, both workers and any span of hours; ``p50_ms``/``p95_ms`` are kept on the row too.
* ``request_speed_slow``: one row per request over ``SLOW_ROW_SECONDS``, kept for
  ``SLOW_KEEP_DAYS`` days. ``at`` is the completion time (queued after the last byte);
  ``started_at`` is when the request reached this worker (``pid``). ``pg_ms``/``pg_count`` are
  the Postgres statement time and count inside the request, ``gzip_ms`` the compression time and
  ``cache`` the Financial view cache outcome (hit, saved, miss), ``pool_ms`` the wait for a database
  connection from the pool (postgres.session), so a slow request can be split
  into database, cache and everything else, and joined by minute to ``request_speed_loop_lag``
  (this worker's event-loop lag) and ``host_load_minute`` (scripts/host_recorder.py).
* ``request_speed_pages``: one row per page view from the browser (every route), with
  navigation, resource, long-task, memory and connection figures, kept ``PAGE_KEEP_DAYS``.
* ``request_speed_loop_lag``: per worker and minute, how late the event loop woke a timer.

Every /api response also carries a ``Server-Timing`` header (``app``: time to the response
headers, ``pg``, ``pool``, ``gz``, ``cache``, ``w``: the worker pid) for the browser's devtools.

A request over ``SLOW_LOG_SECONDS`` also logs one WARNING line. Only the route template,
the case id and the person's id are kept: never a raw path, another query value or an email
(the email noted by the sign-in check is turned into the user id inside the writer).

If the database is busy or down, a flush fails, its totals are kept for the next one (up to
``MAX_PENDING_KEYS`` groups, then dropped with a log line) and no request is ever affected.
"""
import bisect
import collections
import logging
import math
import os
import re
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import parse_qs

log = logging.getLogger(__name__)

FLUSH_SECONDS = 15
SLOW_ROW_SECONDS = 2.0
SLOW_LOG_SECONDS = 5.0
SLOW_KEEP_DAYS = 30
PAGE_KEEP_DAYS = 90
LAG_KEEP_DAYS = 90
QUEUE_LIMIT = 50000
MAX_PENDING_KEYS = 20000
UNMATCHED = '(no matching route)'
STREAM = ' (stream)'  # appended to an event-stream route: long by design, never a slow request
METHODS = frozenset(('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'))
# Bucket i holds durations in (BUCKET_EDGES_MS[i-1], BUCKET_EDGES_MS[i]]; the last bucket
# holds everything above the last edge. 1 ms .. ~11 min in 15% steps (98 buckets).
BUCKET_EDGES_MS = tuple(round(1.15 ** i, 3) for i in range(97))
BUCKET_COUNT = len(BUCKET_EDGES_MS) + 1
_UUID = re.compile(r'^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$')

_queue = collections.deque(maxlen=QUEUE_LIMIT)
_pages = collections.deque(maxlen=QUEUE_LIMIT)  # page-view detail rows
_lag = collections.deque(maxlen=QUEUE_LIMIT)  # finished minutes of event-loop lag
# One dict per request: the person (sign-in check), Postgres time and count, compression time and
# cache state. Threads started for the request (sync dependencies and handlers) copy the context,
# so they add to the same dict.
_person = ContextVar('request_speed_person', default=None)
CACHE_STATES = ('hit', 'saved', 'miss', 'updating')  # updating: the previous copy, marked so (view_cache)


def bucket_of(ms):
    return bisect.bisect_left(BUCKET_EDGES_MS, ms)


def percentile(buckets, q, max_ms=None):
    """The q-quantile from a histogram, interpolated inside the bucket holding that rank (so
    within one 15% bucket of the true value) and never above the largest time seen. None when empty."""
    total = sum(buckets)
    if total <= 0:
        return None
    rank = max(1, math.ceil(q * total))
    seen = 0
    for i, n in enumerate(buckets):
        if n and seen + n >= rank:
            low = BUCKET_EDGES_MS[i - 1] if i else 0.0
            high = BUCKET_EDGES_MS[i] if i < len(BUCKET_EDGES_MS) else (max_ms or low)
            if max_ms is not None:
                high = min(high, max_ms)
                low = min(low, high)
            return round(low + (high - low) * (rank - seen) / n, 3)
        seen += n
    return max_ms


def case_of(value):
    if not value:
        return None
    value = str(value)
    if not _UUID.match(value):
        return None
    value = value.replace('-', '').lower()
    return f'{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}'


def note_person(email):
    """Called by the sign-in check: which person this request is for (resolved to an id later)."""
    holder = _person.get()
    if holder is not None and email:
        holder['email'] = email


def note_cache(state):
    """Called by a cache serving this request: hit, saved (from the saved copy) or miss. A miss wins."""
    holder = _person.get()
    if holder is not None and state in CACHE_STATES:
        if holder.get('cache') != 'miss':
            holder['cache'] = state


def note_pool_wait(seconds):
    """Called by postgres.session for each pool checkout inside this request: time waiting for a connection."""
    holder = _person.get()
    if holder is not None:
        holder['pool_ms'] = holder.get('pool_ms', 0.0) + seconds * 1000


def note_engine(seconds):
    """Called by the evidence engine client for each call inside this request: time from sending to the whole
    answer read, so a slow engine poll splits into engine time and this server's own time."""
    holder = _person.get()
    if holder is not None:
        holder['engine_ms'] = holder.get('engine_ms', 0.0) + seconds * 1000
        holder['engine_n'] = holder.get('engine_n', 0) + 1


def note_gzip(seconds):
    holder = _person.get()
    if holder is not None:
        holder['gzip_ms'] = holder.get('gzip_ms', 0.0) + seconds * 1000


_SQL_TIMED = []


def install_sql_timing():
    """Time every Postgres statement inside a request (one listener pair for every engine, once).
    Outside a request it costs one context-variable lookup per statement."""
    if _SQL_TIMED:
        return
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    # A listener that raised would replace the statement's own result or error: each one swallows its own.
    def before(conn, cursor, statement, parameters, context, executemany):
        try:
            if _person.get() is not None:
                conn.info.setdefault('request_speed_started', []).append(time.perf_counter())
        except Exception:
            pass

    def after(conn, cursor, statement, parameters, context, executemany):
        try:
            holder = _person.get()
            started = conn.info.get('request_speed_started')
            if holder is None or not started:
                return
            holder['pg_ms'] = holder.get('pg_ms', 0.0) + (time.perf_counter() - started.pop()) * 1000
            holder['pg_n'] = holder.get('pg_n', 0) + 1
        except Exception:
            pass

    def failed(context):
        try:
            started = context.connection.info.get('request_speed_started') if context.connection is not None else None
            if started:
                started.pop()
        except Exception:
            pass

    event.listen(Engine, 'before_cursor_execute', before)
    event.listen(Engine, 'after_cursor_execute', after)
    event.listen(Engine, 'handle_error', failed)
    _SQL_TIMED.append((before, after, failed))


def server_timing(app_ms, holder):
    parts = [f'app;dur={app_ms:.1f}']
    if holder.get('pg_n'):
        parts.append(f'pg;dur={holder["pg_ms"]:.1f};desc="{holder["pg_n"]} statements"')
    if holder.get('pool_ms'):
        parts.append(f'pool;dur={holder["pool_ms"]:.1f}')
    if holder.get('gzip_ms'):
        parts.append(f'gz;dur={holder["gzip_ms"]:.1f}')
    if holder.get('engine_n'):
        parts.append(f'engine;dur={holder["engine_ms"]:.1f};desc="{holder["engine_n"]} calls"')
    if holder.get('cache'):
        parts.append(f'cache;desc={holder["cache"]}')
    parts.append(f'w;desc={os.getpid()}')
    return ', '.join(parts).encode('latin-1')


def _template(scope):
    route = scope.get('route')
    template = getattr(route, 'path_format', None) or getattr(route, 'path', None)
    return template[:255] if template else UNMATCHED


def _case(scope):
    case = case_of((scope.get('path_params') or {}).get('case_id'))
    if case:
        return case
    query = scope.get('query_string') or b''
    if b'case_id=' not in query:
        return None
    values = parse_qs(query.decode('latin-1')).get('case_id')
    return case_of(values[0]) if values else None


def enqueue(kind, method, route, case_id, status, ms, size, email, at=None, extra=None):
    """Append one measurement (``extra``: started_at, pid, pg_ms, pg_count, gzip_ms, cache). Never raises, never blocks."""
    try:
        _queue.append((at or time.time(), kind, method, route, case_id, status, float(ms), int(size or 0), email, extra))
        _writer.ensure_started()
    except Exception:  # pragma: no cover - a full deque drops the oldest; nothing else can fail here
        pass


class RequestSpeedMiddleware:
    """Pure ASGI; times every http request under ``prefix`` from arrival to the last body byte sent.

    Arrival is when this worker's event loop first runs the request: time waiting in the socket
    backlog while the loop is blocked, the frontend proxy and the browser's own queue are not in it
    (the page rows and ``request_speed_loop_lag`` measure those)."""

    def __init__(self, app, prefix='/api'):
        self.app = app
        self.prefix = prefix
        install_sql_timing()

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or not scope.get('path', '').startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        started_at = time.time()
        outcome = [None, 0, False]
        person = {}
        token = _person.set(person)

        async def measured(message):
            kind = message['type']
            if kind == 'http.response.start':
                outcome[0] = message['status']
                for name, value in message.get('headers') or ():
                    if name.lower() == b'content-type' and value.startswith(b'text/event-stream'):
                        outcome[2] = True
                try:
                    timing = server_timing((time.perf_counter() - started) * 1000, person)
                    message = {**message, 'headers': [*(message.get('headers') or ()), (b'server-timing', timing)]}
                except Exception:  # pragma: no cover - a header can never break a response
                    pass
            elif kind == 'http.response.body':
                outcome[1] += len(message.get('body') or b'')
            await send(message)

        try:
            await self.app(scope, receive, measured)
        except BaseException as error:
            if outcome[0] is None:
                outcome[0] = 500 if isinstance(error, Exception) else 499
            raise
        finally:
            _person.reset(token)
            seconds = time.perf_counter() - started
            try:
                method = scope.get('method') if scope.get('method') in METHODS else 'OTHER'
                route = _template(scope)
                streamed = outcome[2] and route != UNMATCHED
                # A case only for a matched route and a signed-in person: an anonymous caller
                # cannot create rows for made-up cases.
                case = _case(scope) if route != UNMATCHED and person.get('email') else None
                extra = dict(started_at=started_at, pid=os.getpid(), pg_ms=person.get('pg_ms'),
                             pg_count=person.get('pg_n'), gzip_ms=person.get('gzip_ms'), cache=person.get('cache'),
                             pool_ms=person.get('pool_ms'))
                enqueue('api', method, route + STREAM if streamed else route, case, outcome[0] or 499,
                        seconds * 1000, outcome[1], person.get('email'), extra=extra)
                if seconds > SLOW_LOG_SECONDS and not streamed:
                    log.warning('Slow request: %s %s case %s %.1f s (status %s)%s', method, route,
                                case[:8] if case else '-', seconds, outcome[0] or 499,
                                f' [pg {person.get("pg_ms", 0.0) / 1000:.1f} s, engine '
                                f'{person["engine_ms"] / 1000:.1f} s]' if person.get('engine_n') else '')
            except Exception:
                log.exception('Request speed: could not record a request (the request itself is unaffected)')


# --- aggregation -----------------------------------------------------------------------------

def hour_of(at):
    return datetime.fromtimestamp(at - at % 3600, tz=timezone.utc)


class Group:
    __slots__ = ('count', 'total_ms', 'max_ms', 'bytes', 'errors', 'buckets')

    def __init__(self):
        self.count = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.bytes = 0
        self.errors = 0
        self.buckets = [0] * BUCKET_COUNT

    def add(self, ms, size, status):
        self.count += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        self.bytes += size
        self.errors += 1 if (status or 0) >= 500 else 0
        self.buckets[bucket_of(ms)] += 1

    def merge(self, other):
        self.count += other.count
        self.total_ms += other.total_ms
        self.max_ms = max(self.max_ms, other.max_ms)
        self.bytes += other.bytes
        self.errors += other.errors
        self.buckets = [a + b for a, b in zip(self.buckets, other.buckets)]


def aggregate(items, user_ids):
    """(groups keyed by hour/kind/method/route/case/user, slow rows) from queued tuples."""
    groups, slow = {}, []
    for item in items:
        at, kind, method, route, case, status, ms, size, email = item[:9]
        extra = (item[9] if len(item) > 9 else None) or {}
        user = user_ids.get(email) if email else None
        key = (hour_of(at), kind, method, route, case, user)
        group = groups.get(key)
        if group is None:
            group = groups[key] = Group()
        group.add(ms, size, status)
        if ms > SLOW_ROW_SECONDS * 1000 and not route.endswith(STREAM):
            begun = extra.get('started_at')
            slow.append(dict(at=datetime.fromtimestamp(at, tz=timezone.utc), kind=kind, method=method, route=route,
                             case_id=case, user_id=user, status=status, duration_ms=ms, bytes=size,
                             started_at=datetime.fromtimestamp(begun, tz=timezone.utc) if begun else None,
                             pid=extra.get('pid'), pg_ms=extra.get('pg_ms'), pg_count=extra.get('pg_count'),
                             gzip_ms=extra.get('gzip_ms'), cache=extra.get('cache'), pool_ms=extra.get('pool_ms')))
    return groups, slow


# --- writer ----------------------------------------------------------------------------------

UPSERT = '''
INSERT INTO request_speed_hourly AS h
  (hour, kind, method, route, case_id, user_id, count, total_ms, max_ms, bytes, errors, buckets, p50_ms, p95_ms)
VALUES (:hour, :kind, :method, :route, CAST(:case_id AS uuid), CAST(:user_id AS uuid), :count, :total_ms, :max_ms,
        :bytes, :errors, CAST(:buckets AS integer[]), :p50_ms, :p95_ms)
ON CONFLICT (hour, kind, method, route, case_id, user_id) DO UPDATE SET
  count = h.count + EXCLUDED.count,
  total_ms = h.total_ms + EXCLUDED.total_ms,
  max_ms = GREATEST(h.max_ms, EXCLUDED.max_ms),
  bytes = h.bytes + EXCLUDED.bytes,
  errors = h.errors + EXCLUDED.errors,
  buckets = ARRAY(SELECT COALESCE(a, 0) + COALESCE(b, 0)
                  FROM unnest(h.buckets, EXCLUDED.buckets) WITH ORDINALITY AS u(a, b, i) ORDER BY i)
RETURNING id, buckets, max_ms
'''
# Only the writer that last changed the histogram can set the percentiles, so two workers
# flushing the same row at once never leave p50/p95 from an older histogram.
SET_PERCENTILES = '''
UPDATE request_speed_hourly SET p50_ms = :p50_ms, p95_ms = :p95_ms
WHERE id = :id AND buckets = CAST(:buckets AS integer[])
'''
INSERT_SLOW = '''
INSERT INTO request_speed_slow (at, kind, method, route, case_id, user_id, status, duration_ms, bytes,
                                started_at, pid, pg_ms, pg_count, gzip_ms, cache, pool_ms)
VALUES (:at, :kind, :method, :route, CAST(:case_id AS uuid), CAST(:user_id AS uuid), :status, :duration_ms, :bytes,
        :started_at, :pid, :pg_ms, :pg_count, :gzip_ms, :cache, :pool_ms)
'''
PRUNE = (f"DELETE FROM request_speed_slow WHERE at < now() - interval '{SLOW_KEEP_DAYS} days'",
         f"DELETE FROM request_speed_pages WHERE at < now() - interval '{PAGE_KEEP_DAYS} days'",
         f"DELETE FROM request_speed_loop_lag WHERE minute < now() - interval '{LAG_KEEP_DAYS} days'")
PAGE_COLUMNS = ('nav_response_ms', 'nav_dom_ms', 'nav_load_ms', 'nav_bytes', 'resources', 'resource_bytes',
                'queue_max_ms', 'queue_total_ms', 'transfer_total_ms', 'largest_ms', 'largest_route',
                'largest_bytes', 'longest_task_ms', 'long_tasks', 'heap_used_mb', 'heap_limit_mb',
                'effective_type', 'downlink_mbps', 'rtt_ms')
INSERT_PAGE = f'''
INSERT INTO request_speed_pages (at, page, method, case_id, user_id, ms, {', '.join(PAGE_COLUMNS)})
VALUES (:at, :page, :method, CAST(:case_id AS uuid), CAST(:user_id AS uuid), :ms, {', '.join(':' + c for c in PAGE_COLUMNS)})
'''
INSERT_LAG = '''
INSERT INTO request_speed_loop_lag AS l (minute, pid, samples, max_ms, total_ms, over_100ms, over_1s)
VALUES (:minute, :pid, :samples, :max_ms, :total_ms, :over_100ms, :over_1s)
ON CONFLICT (minute, pid) DO UPDATE SET
  samples = l.samples + EXCLUDED.samples, max_ms = GREATEST(l.max_ms, EXCLUDED.max_ms),
  total_ms = l.total_ms + EXCLUDED.total_ms, over_100ms = l.over_100ms + EXCLUDED.over_100ms,
  over_1s = l.over_1s + EXCLUDED.over_1s
'''


def write(session, groups, slow, pages=(), lags=()):
    from sqlalchemy import text
    session.execute(text("SET LOCAL statement_timeout = '10s'"))
    session.execute(text("SET LOCAL lock_timeout = '3s'"))
    from sqlalchemy.exc import DataError, IntegrityError
    for (hour, kind, method, route, case, user), g in sorted(groups.items(), key=lambda kv: tuple(map(str, kv[0]))):
        # A row the database refuses as data is dropped alone (savepoint) so it cannot block every
        # later flush; a busy or unreachable database raises and the whole flush is retried.
        try:
            with session.begin_nested():
                row = session.execute(text(UPSERT), dict(
                    hour=hour, kind=kind, method=method, route=route, case_id=case, user_id=user, count=g.count,
                    total_ms=g.total_ms, max_ms=g.max_ms, bytes=g.bytes, errors=g.errors, buckets=g.buckets,
                    p50_ms=percentile(g.buckets, 0.5, g.max_ms), p95_ms=percentile(g.buckets, 0.95, g.max_ms))).one()
                buckets = list(row.buckets)
                session.execute(text(SET_PERCENTILES), dict(
                    id=row.id, buckets=buckets, p50_ms=percentile(buckets, 0.5, row.max_ms),
                    p95_ms=percentile(buckets, 0.95, row.max_ms)))
        except (DataError, IntegrityError) as error:
            log.warning('Request speed: dropped one refused group %s %s (%s)', method, route[:80], type(error).__name__)
    for one in slow:
        try:
            with session.begin_nested():
                session.execute(text(INSERT_SLOW), one)
        except (DataError, IntegrityError) as error:
            log.warning('Request speed: dropped one refused slow row (%s)', type(error).__name__)
    for page in pages:
        try:
            with session.begin_nested():
                session.execute(text(INSERT_PAGE), page)
        except (DataError, IntegrityError) as error:
            log.warning('Request speed: dropped one refused page row (%s)', type(error).__name__)
    for lag in lags:
        try:
            with session.begin_nested():
                session.execute(text(INSERT_LAG), lag)
        except (DataError, IntegrityError) as error:
            log.warning('Request speed: dropped one refused loop-lag row (%s)', type(error).__name__)
    session.commit()


class Writer:
    def __init__(self, session_factory=None, interval=FLUSH_SECONDS):
        self.session_factory = session_factory
        self.interval = interval
        self.pending_groups = {}
        self.pending_slow = []
        self.pending_pages = []
        self.pending_lag = []
        self.user_ids = {}
        self.users_loaded = 0.0
        self.pruned = 0.0
        self.last_warning = 0.0
        self.pid = None
        self.lock = threading.Lock()
        self.flushing = threading.Lock()
        self.wake = threading.Event()

    def ensure_started(self):
        if self.pid == os.getpid():
            return
        with self.lock:
            if self.pid == os.getpid():
                return
            # A forked child inherits the parent's queue contents but not its thread.
            self.pid = os.getpid()
            threading.Thread(target=self._run, name='request-speed-writer', daemon=True).start()

    def _run(self):
        while True:
            self.wake.wait(self.interval)
            self.wake.clear()
            try:
                self.flush()
            except Exception:  # flush never raises by design; the thread must outlive a bug in it
                log.exception('Request speed: writer error')

    def _factory(self):
        if self.session_factory is None:
            from postgres.session import _get_session_local
            self.session_factory = _get_session_local()
        return self.session_factory

    def _resolve_users(self, session, emails):
        from sqlalchemy import text
        now = time.time()
        if now - self.users_loaded > 3600:
            self.user_ids, self.users_loaded = {}, now
        missing = [e for e in emails if e not in self.user_ids]
        if missing:
            found = dict(session.execute(text('SELECT email, CAST(id AS text) FROM users WHERE email = ANY(:emails)'),
                                         dict(emails=missing)).all())
            for email in missing:
                self.user_ids[email] = found.get(email)
            session.rollback()

    def flush(self):
        """Drain the queue into the database. Never raises; one flush at a time."""
        with self.flushing:
            self._flush()

    def _flush(self):
        items = _drain(_queue)
        pages = _drain(_pages)
        self.pending_lag.extend(_drain(_lag))
        if not items and not pages and not self.pending_groups and not self.pending_slow and not self.pending_pages \
                and not self.pending_lag:
            return
        try:
            with self._factory()() as session:
                emails = {item[8] for item in items if item[8]} | {p['email'] for p in pages if p.get('email')}
                if emails:
                    self._resolve_users(session, emails)
                groups, slow = aggregate(items, self.user_ids)
                items = []
                for key, group in groups.items():
                    if key in self.pending_groups:
                        self.pending_groups[key].merge(group)
                    else:
                        self.pending_groups[key] = group
                self.pending_slow.extend(slow)
                self.pending_pages.extend(_page_row(p, self.user_ids) for p in pages)
                pages = []
                write(session, self.pending_groups, self.pending_slow, self.pending_pages, self.pending_lag)
                self.pending_groups, self.pending_slow, self.pending_pages, self.pending_lag = {}, [], [], []
                if time.time() - self.pruned > 3600:
                    from sqlalchemy import text
                    for statement in PRUNE:
                        session.execute(text(statement))
                    session.commit()
                    self.pruned = time.time()
        except Exception as error:
            if items:  # failed before aggregating: keep them as totals without a person
                groups, slow = aggregate(items, {})
                for key, group in groups.items():
                    if key in self.pending_groups:
                        self.pending_groups[key].merge(group)
                    else:
                        self.pending_groups[key] = group
                self.pending_slow.extend(slow)
            self.pending_pages.extend(_page_row(p, {}) for p in pages)
            if (len(self.pending_groups) > MAX_PENDING_KEYS or len(self.pending_slow) > MAX_PENDING_KEYS
                    or len(self.pending_pages) > MAX_PENDING_KEYS or len(self.pending_lag) > MAX_PENDING_KEYS):
                log.warning('Request speed: dropped %d unsaved groups, %d slow, %d page and %d loop-lag rows after '
                            'repeated database failures', len(self.pending_groups), len(self.pending_slow),
                            len(self.pending_pages), len(self.pending_lag))
                self.pending_groups, self.pending_slow, self.pending_pages, self.pending_lag = {}, [], [], []
            if time.time() - self.last_warning > 600:
                self.last_warning = time.time()
                log.warning('Request speed: could not save timings, will retry (%s: %s)',
                            type(error).__name__, str(error)[:200])


def _drain(queue):
    items = []
    while True:
        try:
            items.append(queue.popleft())
        except IndexError:
            return items


def _page_row(page, user_ids):
    row = {k: v for k, v in page.items() if k != 'email'}
    row['user_id'] = user_ids.get(page.get('email')) if page.get('email') else None
    return row


_writer = Writer()


def flush_now():
    """Save what is queued now (at shutdown). Never raises."""
    _writer.flush()


# --- page views from the browser -------------------------------------------------------------

FINANCIAL_VIEWS = ('overview', 'follow-money', 'findings', 'patterns', 'case-context', 'ledger', 'quarantine', 'runs',
                   'decisions', 'transactions', 'counterparties', 'trends', 'tracing', 'transfers', 'posting-graph')
STATEMENT_SECTIONS = ('queue', 'files', 'accounts', 'batches', 'remove', 'judgements')
# Every route of the app (frontend src/app/routes.tsx), reported by lib/page-timing.ts as "case/<view>",
# "admin/<view>" and so on; a Financial view is also reported in detail by its own page-speed hook.
CASE_ROUTES = ('graph', 'timeline', 'map', 'table', 'financial', 'cellebrite', 'dossiers', 'evidence', 'chat',
               'agent', 'workspace', 'reports', 'settings')
ADMIN_ROUTES = ('ai-costs', 'users', 'profiles', 'logs', 'activity', 'speed', 'tasks', 'updates')
APP_PAGES = (['cases', 'triage', 'admin', 'settings', 'settings/ai', 'login', 'other']
             + [f'case/{r}' for r in CASE_ROUTES] + [f'admin/{r}' for r in ADMIN_ROUTES])
# The page names the browser may report (frontend financialMainViews and statement sections, and every route).
PAGES = frozenset([f'financial/{v}' for v in FINANCIAL_VIEWS] + [f'financial/statements/{s}' for s in STATEMENT_SECTIONS]
                  + APP_PAGES)
PAGE_METHODS = ('LOAD', 'VIEW', 'LEFT')  # LEFT: left before the data was shown (time waited)
PAGE_MAX_MS = 600000
EFFECTIVE_TYPES = ('slow-2g', '2g', '3g', '4g')
_ASSET = re.compile(r'^/assets/[A-Za-z0-9_.-]{1,120}$')


def _number(value, high):
    """A finite number in [0, high], else None (a browser figure is never trusted blindly)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0 <= value <= high else None


def page_detail(detail, route_of=None):
    """The browser's figures for one view, each checked; anything malformed is left out, never guessed.

    ``largest_route`` is never kept as the browser sent it (a path segment can be a person's name, e.g. a
    graph entity key): it is kept only as the template of the API route it matches (``route_of``, given
    by the router from the app's own routes) or as a built asset's file name, else left out."""
    detail = detail or {}
    row = {}
    for name in ('nav_response_ms', 'nav_dom_ms', 'nav_load_ms', 'queue_max_ms', 'queue_total_ms',
                 'transfer_total_ms', 'largest_ms', 'longest_task_ms', 'rtt_ms'):
        row[name] = _number(detail.get(name), PAGE_MAX_MS * 10)
    for name in ('nav_bytes', 'resource_bytes', 'largest_bytes'):
        value = _number(detail.get(name), 2 ** 40)
        row[name] = int(value) if value is not None else None
    for name in ('resources', 'long_tasks'):
        value = _number(detail.get(name), 10 ** 6)
        row[name] = int(value) if value is not None else None
    row['heap_used_mb'] = _number(detail.get('heap_used_mb'), 10 ** 6)
    row['heap_limit_mb'] = _number(detail.get('heap_limit_mb'), 10 ** 6)
    row['downlink_mbps'] = _number(detail.get('downlink_mbps'), 10 ** 5)
    effective = detail.get('effective_type')
    row['effective_type'] = effective if effective in EFFECTIVE_TYPES else None
    route = detail.get('largest_route')
    # Only a route shape the browser has already reduced (ids replaced by {id}, no query) is kept.
    kept = None
    if isinstance(route, str) and len(route) <= 600:
        if _ASSET.match(route):
            kept = route
        elif route.startswith('/api/') and route_of is not None:
            try:
                kept = route_of(route)
            except Exception:
                kept = None
    row['largest_route'] = kept[:160] if kept else None
    return row


def route_template(routes, path):
    """The route template (path_format) of the first app route matching ``path`` for GET, or None."""
    from starlette.routing import Match
    scope = {'type': 'http', 'path': path, 'method': 'GET', 'root_path': ''}
    partial = None
    for route in routes:
        try:
            match, _ = route.matches(scope)
        except Exception:
            continue
        template = getattr(route, 'path_format', None)
        if match == Match.FULL and template:
            return template
        if match == Match.PARTIAL and template and partial is None:
            partial = template  # the path matches, the method does not
    return partial


def enqueue_page_view(page, method, case_id, ms, email, detail=None, route_of=None):
    if page not in PAGES or method not in PAGE_METHODS:
        return False
    if not (0 <= ms <= PAGE_MAX_MS):
        return False
    case = case_of(case_id)
    enqueue('page', method, page, case, 200, ms, 0, email)
    if detail is not None:
        try:
            _pages.append(dict(at=datetime.now(timezone.utc), page=page, method=method, case_id=case, ms=float(ms),
                               email=email, **page_detail(detail, route_of)))
        except Exception:  # pragma: no cover - a full deque drops the oldest; nothing else can fail here
            pass
    return True


# --- event-loop lag --------------------------------------------------------------------------

LAG_INTERVAL = 0.25


class LoopLag:
    """Per minute, how late this worker's event loop ran a timer due every LAG_INTERVAL seconds."""

    def __init__(self):
        self.minute = None
        self.reset()

    def reset(self):
        self.samples, self.max_ms, self.total_ms, self.over_100ms, self.over_1s = 0, 0.0, 0.0, 0, 0

    def add(self, at, lag_ms):
        minute = at - at % 60
        if self.minute is not None and minute != self.minute:
            self.close()
        self.minute = minute
        self.samples += 1
        self.max_ms = max(self.max_ms, lag_ms)
        self.total_ms += lag_ms
        self.over_100ms += lag_ms > 100
        self.over_1s += lag_ms > 1000

    def close(self):
        if self.minute is not None and self.samples:
            _lag.append(dict(minute=datetime.fromtimestamp(self.minute, tz=timezone.utc), pid=os.getpid(),
                             samples=self.samples, max_ms=round(self.max_ms, 3), total_ms=round(self.total_ms, 3),
                             over_100ms=self.over_100ms, over_1s=self.over_1s))
            _writer.ensure_started()
        self.reset()


async def run_loop_lag_probe(interval=LAG_INTERVAL):
    """Started by each web worker (main.py lifespan). One timer wake every ``interval``; never raises."""
    import asyncio
    from services import loop_stall
    lag = LoopLag()
    # A thread beside the loop logs what the loop is running when it falls a second behind (loop_stall).
    heartbeat = loop_stall.Heartbeat(interval)
    heartbeat.beat()
    stop_watch = loop_stall.start(heartbeat)
    try:
        while True:
            due = time.perf_counter() + interval
            await asyncio.sleep(interval)
            heartbeat.beat()
            late = max(0.0, time.perf_counter() - due) * 1000
            lag.add(time.time(), late)
    except asyncio.CancelledError:
        lag.close()
        raise
    except Exception:  # pragma: no cover - the probe must never take the worker down
        log.exception('Request speed: loop-lag probe stopped')
    finally:
        if stop_watch is not None:
            stop_watch.set()


# --- reading ---------------------------------------------------------------------------------

def summary(session, days, case_id=None, kind=None, slow_limit=200):
    """Per route over the last ``days`` days (whole hours): count, p50, p95, max, bytes; slowest first.
    Plus the slow requests kept in the same window, newest first."""
    from sqlalchemy import text
    where = ["hour >= date_trunc('hour', now()) - make_interval(hours => :hours)"]
    params = dict(hours=int(days * 24) - 1)
    if case_id:
        where.append('case_id = CAST(:case_id AS uuid)')
        params['case_id'] = case_id
    if kind:
        where.append('kind = :kind')
        params['kind'] = kind
    clause = ' AND '.join(where)
    totals = session.execute(text(f'''
        SELECT kind, method, route, SUM(count) AS count, SUM(total_ms) AS total_ms, MAX(max_ms) AS max_ms,
               SUM(bytes) AS bytes, SUM(errors) AS errors, COUNT(DISTINCT case_id) AS cases
        FROM request_speed_hourly WHERE {clause} GROUP BY kind, method, route'''), params).all()
    buckets = collections.defaultdict(lambda: [0] * BUCKET_COUNT)
    for kind_, method, route, i, n in session.execute(text(f'''
            SELECT kind, method, route, u.i, SUM(u.n)
            FROM request_speed_hourly, unnest(buckets) WITH ORDINALITY AS u(n, i)
            WHERE {clause} AND u.n > 0 GROUP BY kind, method, route, u.i'''), params):
        if 1 <= i <= BUCKET_COUNT:
            buckets[(kind_, method, route)][i - 1] = int(n)
    routes = []
    for row in totals:
        hist = buckets[(row.kind, row.method, row.route)]
        count = int(row.count or 0)
        routes.append(dict(kind=row.kind, method=row.method, route=row.route, count=count,
                           p50_ms=percentile(hist, 0.5, row.max_ms), p95_ms=percentile(hist, 0.95, row.max_ms),
                           max_ms=row.max_ms, mean_ms=(row.total_ms / count) if count else None,
                           bytes=int(row.bytes or 0), errors=int(row.errors or 0), cases=int(row.cases or 0)))
    routes.sort(key=lambda r: (-(r['p95_ms'] or 0), -(r['max_ms'] or 0), r['route']))
    slow_where = ["s.at >= date_trunc('hour', now()) - make_interval(hours => :hours)"]
    if case_id:
        slow_where.append('s.case_id = CAST(:case_id AS uuid)')
    if kind:
        slow_where.append('s.kind = :kind')
    # Each slow request beside its minute: its worker's event-loop lag, the machine's CPU pressure and the
    # jobs fleet's CPU (host_load_minute, request_speed_loop_lag; None when that minute was not recorded).
    slow = [dict(at=r.at.isoformat(), kind=r.kind, method=r.method, route=r.route,
                 case_id=str(r.case_id) if r.case_id else None, case_title=r.case_title,
                 status=r.status, duration_ms=r.duration_ms, bytes=r.bytes, user_name=r.user_name,
                 started_at=r.started_at.isoformat() if r.started_at else None, pid=r.pid, pg_ms=r.pg_ms,
                 cache=r.cache, loop_lag_max_ms=r.lag_max_ms, host_cpu_pressure=r.psi_cpu_some,
                 fleet_cores=r.fleet_cores)
            for r in session.execute(text(f'''
                SELECT s.at, s.kind, s.method, s.route, s.case_id, c.title AS case_title, s.status,
                       s.duration_ms, s.bytes, u.name AS user_name, s.started_at, s.pid, s.pg_ms, s.cache,
                       l.max_ms AS lag_max_ms, h.psi_cpu_some,
                       (SELECT sum((v->>'cores')::float) FROM jsonb_each(h.groups) g(k, v)
                        WHERE k IN ('fleet.slice', 'system.slice/fin-watchdog.service')) AS fleet_cores
                FROM request_speed_slow s
                LEFT JOIN cases c ON c.id = s.case_id LEFT JOIN users u ON u.id = s.user_id
                LEFT JOIN request_speed_loop_lag l ON l.minute = date_trunc('minute', s.at) AND l.pid = s.pid
                LEFT JOIN host_load_minute h ON h.minute = date_trunc('minute', s.at)
                WHERE {' AND '.join(slow_where)} ORDER BY s.at DESC LIMIT :limit'''),
                dict(params, limit=slow_limit))]
    cases = [dict(id=str(r.case_id), title=r.title, count=int(r.count)) for r in session.execute(text('''
        SELECT h.case_id, c.title, SUM(h.count) AS count FROM request_speed_hourly h
        LEFT JOIN cases c ON c.id = h.case_id
        WHERE h.case_id IS NOT NULL AND h.hour >= date_trunc('hour', now()) - make_interval(hours => :hours)
        GROUP BY h.case_id, c.title ORDER BY count DESC LIMIT 200'''), dict(hours=params['hours']))]
    return dict(days=days, routes=routes, slow=slow, cases=cases,
                slow_row_seconds=SLOW_ROW_SECONDS, slow_keep_days=SLOW_KEEP_DAYS)
