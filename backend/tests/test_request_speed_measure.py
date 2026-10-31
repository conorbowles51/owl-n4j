"""What people wait for, joinable by minute (lx-measure): Server-Timing, start time and worker on slow rows,
page timing from every route with the browser's figures, the per-worker event-loop lag probe, the host
recorder and the read-only report.

Pins: every /api response carries Server-Timing with the time to headers and the worker pid, plus Postgres
time and count when the request ran SQL (also from a sync handler in the thread pool) and the view-cache
state; a slow row keeps its start time, worker, Postgres and compression time; the start is before the
completion; every app route is a known page name and unknown names are still refused; a browser figure that
is malformed, out of range or carries an id is left out, never guessed; a blocked loop is measured as lag;
the writer saves page and lag rows and keeps them through a database failure; the recorder's counters are
deltas over the measured interval and no command-line secret is kept; the probe records refusals as errors;
every column the code writes exists in the migration.
"""
import asyncio
import http.server
import re
import socket
import threading
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from services import request_speed as rs

CASE = 'd5b330d1-1111-2222-3333-444455556666'
BACKEND = Path(__file__).resolve().parents[1]


def build_app(engine):
    app = FastAPI()
    app.add_middleware(rs.RequestSpeedMiddleware)

    @app.get('/api/sync-sql')
    def sync_sql():
        with engine.connect() as conn:
            conn.execute(text('SELECT 1')).all()
            conn.execute(text('SELECT 2')).all()
        return {'ok': True}

    @app.get('/api/async-sql')
    async def async_sql():
        with engine.connect() as conn:
            conn.execute(text('SELECT 1')).all()
        return {'ok': True}

    @app.get('/api/cached')
    def cached():
        rs.note_cache('saved')
        return {'ok': True}

    @app.get('/api/plain')
    def plain():
        return {'ok': True}

    @app.get('/outside')
    def outside():
        return {'ok': True}
    return app


class Captured(TestCase):
    def setUp(self):
        rs._queue.clear()
        rs._pages.clear()
        rs._lag.clear()
        started = patch.object(rs._writer, 'ensure_started')
        started.start()
        self.addCleanup(started.stop)
        self.engine = create_engine('sqlite://')
        self.client = TestClient(build_app(self.engine))

    def drained(self):
        items = list(rs._queue)
        rs._queue.clear()
        return items


def timing(response):
    return dict(re.match(r'\s*([a-z]+)(.*)', part).groups() for part in response.headers['server-timing'].split(','))


class ServerTiming(Captured):
    def test_every_api_response_has_app_time_and_worker(self):
        response = self.client.get('/api/plain')
        parts = timing(response)
        self.assertRegex(parts['app'], r'^;dur=\d+\.\d$')
        self.assertEqual(parts['w'], f';desc={__import__("os").getpid()}')
        self.assertNotIn('pg', parts)
        self.assertNotIn('server-timing', self.client.get('/outside').headers)

    def test_sql_in_a_threadpool_handler_is_timed_and_counted(self):
        response = self.client.get('/api/sync-sql')
        self.assertEqual(response.json(), {'ok': True})
        self.assertRegex(timing(response)['pg'], r'^;dur=\d+\.\d;desc="2 statements"$')
        [item] = self.drained()
        self.assertEqual(item[9]['pg_count'], 2)
        self.assertGreaterEqual(item[9]['pg_ms'], 0)

    def test_sql_on_the_loop_is_timed_too(self):
        self.assertIn('desc="1 statements"', timing(self.client.get('/api/async-sql'))['pg'])

    def test_sql_outside_a_request_is_not_counted(self):
        with self.engine.connect() as conn:
            conn.execute(text('SELECT 1')).all()
        self.assertNotIn('pg', timing(self.client.get('/api/plain')))

    def test_cache_state_and_a_miss_wins(self):
        self.assertEqual(timing(self.client.get('/api/cached'))['cache'], ';desc=saved')
        holder = {}
        token = rs._person.set(holder)
        try:
            rs.note_cache('miss')
            rs.note_cache('hit')
            rs.note_cache('bogus')
        finally:
            rs._person.reset(token)
        self.assertEqual(holder, {'cache': 'miss'})

    def test_body_is_unchanged(self):
        self.assertEqual(self.client.get('/api/plain').content, b'{"ok":true}')


class SlowRows(Captured):
    def test_slow_row_keeps_start_worker_and_stage_times(self):
        self.client.get('/api/sync-sql')
        [item] = self.drained()
        at, ms, extra = item[0], item[6], item[9]
        self.assertLessEqual(extra['started_at'], at)
        self.assertAlmostEqual(at - extra['started_at'], ms / 1000, delta=0.05)
        slow_item = (at, *item[1:6], 2500.0, *item[7:])
        _, [row] = rs.aggregate([slow_item], {})
        self.assertEqual(row['pid'], __import__('os').getpid())
        self.assertEqual(row['pg_count'], 2)
        self.assertLess(row['started_at'], row['at'])
        self.assertIsNone(row['cache'])

    def test_old_nine_field_items_still_aggregate(self):
        _, [row] = rs.aggregate([(time.time(), 'api', 'GET', '/x', None, 200, 3000.0, 0, None)], {})
        self.assertIsNone(row['started_at'])
        self.assertIsNone(row['pid'])

    def test_gzip_time_is_noted(self):
        from services.json_gzip import JSONGZipMiddleware
        app = FastAPI()
        app.add_middleware(JSONGZipMiddleware)
        app.add_middleware(rs.RequestSpeedMiddleware)

        @app.get('/api/big')
        def big():
            return {'rows': list(range(5000))}
        response = TestClient(app).get('/api/big', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(response.json(), {'rows': list(range(5000))})
        self.assertIn('gz', timing(response))
        self.assertGreater(self.drained()[0][9]['gzip_ms'], 0)


class PageViews(Captured):
    def test_every_app_route_is_a_page_and_unknown_names_are_refused(self):
        for page in ('case/timeline', 'case/graph', 'case/evidence', 'cases', 'admin/speed', 'settings/ai', 'other'):
            self.assertTrue(rs.enqueue_page_view(page, 'LOAD', CASE, 100, 'a@b'), page)
        for page in ('case/made-up', 'case/../x', 'timeline', ''):
            self.assertFalse(rs.enqueue_page_view(page, 'LOAD', CASE, 100, 'a@b'), page)

    def test_app_page_names_match_the_frontend_routes(self):
        source = (BACKEND.parent / 'frontend_v2/src/lib/route-speed.ts').read_text()
        case = set(re.findall(r'"([a-z-]+)"', re.search(r'CASE_ROUTES = new Set\(\[(.*?)\]\)', source, re.S).group(1)))
        admin = set(re.findall(r'"([a-z-]+)"', re.search(r'ADMIN_ROUTES = new Set\(\[(.*?)\]\)', source, re.S).group(1)))
        self.assertEqual(case, set(rs.CASE_ROUTES))
        self.assertEqual(admin, set(rs.ADMIN_ROUTES))
        routes = (BACKEND.parent / 'frontend_v2/src/app/routes.tsx').read_text()
        case_block = routes[routes.index('path="/cases/:id"'):routes.index('{/* Admin routes */}')]
        live = set(re.findall(r'path="([a-z-]+)" element=\{<LazyPage>|path="([a-z-]+)" element=\{<Evidence', case_block))
        self.assertEqual({a or b for a, b in live}, set(rs.CASE_ROUTES))

    def test_detail_is_checked_value_by_value(self):
        detail = dict(queue_max_ms=812.4, resources=31, resource_bytes=1234567, largest_route='/api/timeline',
                      largest_ms=5300.5, effective_type='4g', downlink_mbps=9.5, rtt_ms=50, heap_used_mb=410.2,
                      longest_task_ms=-5, nav_dom_ms='soon', long_tasks=float('nan'))
        self.assertTrue(rs.enqueue_page_view('case/timeline', 'LOAD', CASE, 9000, 'a@b', detail,
                                             lambda path: '/api/timeline' if path == '/api/timeline' else None))
        [row] = list(rs._pages)
        self.assertEqual((row['page'], row['method'], row['case_id'], row['ms']), ('case/timeline', 'LOAD', CASE, 9000.0))
        self.assertEqual((row['queue_max_ms'], row['resources'], row['resource_bytes']), (812.4, 31, 1234567))
        self.assertEqual((row['largest_route'], row['effective_type'], row['downlink_mbps']), ('/api/timeline', '4g', 9.5))
        self.assertIsNone(row['longest_task_ms'])  # negative
        self.assertIsNone(row['nav_dom_ms'])  # not a number
        self.assertIsNone(row['long_tasks'])  # NaN
        self.assertEqual(set(row) - {'at', 'page', 'method', 'case_id', 'ms', 'email'}, set(rs.PAGE_COLUMNS))

    def test_the_browser_route_is_kept_only_as_an_app_route_template(self):
        app = FastAPI()

        @app.get('/api/graph/node/{node_key}')
        def node(node_key: str):
            return {}

        @app.post('/api/cases/{case_id}/notes')
        def notes(case_id: str):
            return {}

        def route_of(path):
            return rs.route_template(app.router.routes, path)
        kept = lambda route: rs.page_detail({'largest_route': route}, route_of)['largest_route']  # noqa: E731
        # A name in a path (graph entity keys are name slugs) is never stored, only the template.
        self.assertEqual(kept('/api/graph/node/john-smith'), '/api/graph/node/{node_key}')
        self.assertEqual(kept('/api/graph/node/{id}'), '/api/graph/node/{node_key}')
        self.assertEqual(kept(f'/api/cases/{CASE}/notes'), '/api/cases/{case_id}/notes')  # path matches, method not
        for route in ('/api/unknown/john-smith', '/api/x?case_id=1', 'api/x', '/a b', '/cases/john-smith'):
            self.assertIsNone(kept(route), route)
        self.assertIsNone(rs.page_detail({'largest_route': '/api/graph/node/john-smith'})['largest_route'])
        self.assertEqual(kept('/assets/index-Bx12.js'), '/assets/index-Bx12.js')
        self.assertIsNone(kept('/assets/../john'))
        self.assertIsNone(rs.page_detail({'effective_type': 'fast'})['effective_type'])

    def test_router_passes_the_detail(self):
        from routers import request_speed as router
        app = FastAPI()
        app.include_router(router.router)

        @app.get('/api/graph/node/{node_key}')
        def node(node_key: str):
            return {}
        app.dependency_overrides[router.get_current_user] = lambda: {'username': 'a@b'}
        response = TestClient(app).post('/api/request-speed/page-views', json={'views': [
            {'page': 'case/graph', 'method': 'VIEW', 'case_id': CASE, 'ms': 900,
             'detail': {'queue_max_ms': 12, 'largest_route': '/api/graph/node/john-smith'}},
            {'page': 'case/graph', 'method': 'VIEW', 'ms': 900}]})
        self.assertEqual((response.status_code, response.json()), (202, {'accepted': 2}))
        self.assertEqual(len(rs._queue), 2)
        [row] = list(rs._pages)
        self.assertEqual(row['queue_max_ms'], 12.0)
        self.assertEqual(row['largest_route'], '/api/graph/node/{node_key}')


class LoopLagProbe(TestCase):
    def setUp(self):
        rs._lag.clear()
        started = patch.object(rs._writer, 'ensure_started')
        started.start()
        self.addCleanup(started.stop)

    def test_minutes_roll_over_into_rows(self):
        lag = rs.LoopLag()
        lag.add(120.5, 3.0)
        lag.add(150.0, 150.0)
        lag.add(179.9, 1500.0)
        self.assertEqual(len(rs._lag), 0)
        lag.add(180.1, 1.0)
        [row] = list(rs._lag)
        self.assertEqual((row['minute'].timestamp(), row['samples'], row['max_ms'], row['over_100ms'], row['over_1s']),
                         (120.0, 3, 1500.0, 2, 1))
        self.assertEqual(row['total_ms'], 1653.0)

    def test_a_blocked_loop_is_measured(self):
        async def scenario():
            task = asyncio.create_task(rs.run_loop_lag_probe(interval=0.05))
            await asyncio.sleep(0.12)
            time.sleep(0.4)  # the loop is held, as a blocking handler would
            await asyncio.sleep(0.12)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        asyncio.run(scenario())
        rows = list(rs._lag)
        self.assertTrue(rows)
        self.assertGreaterEqual(max(r['max_ms'] for r in rows), 300)
        self.assertGreaterEqual(sum(r['over_100ms'] for r in rows), 1)


class WriterSavesPagesAndLag(TestCase):
    def setUp(self):
        for q in (rs._queue, rs._pages, rs._lag):
            q.clear()
        started = patch.object(rs._writer, 'ensure_started')
        started.start()
        self.addCleanup(started.stop)

    def session_class(self, fail=False):
        class Result:
            def all(self_inner):
                return [('a@b', 'u-1')]

        class Session:
            def __enter__(self_inner):
                if fail:
                    raise OSError('database down')
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def rollback(self_inner):
                pass

            def execute(self_inner, statement, params=None):
                return Result()
        return Session

    def test_page_and_lag_rows_are_written_with_the_person(self):
        calls = []
        writer = rs.Writer(session_factory=self.session_class())
        rs.enqueue_page_view('case/timeline', 'VIEW', CASE, 900, 'a@b', {'resources': 3})
        lag = rs.LoopLag()
        lag.add(60.0, 5.0)
        lag.close()
        with patch.object(rs, 'write', side_effect=lambda s, g, sl, pages, lags: calls.append((list(pages), list(lags)))):
            writer.flush()
        [(pages, lags)] = calls
        self.assertEqual((pages[0]['user_id'], pages[0]['resources']), ('u-1', 3))
        self.assertNotIn('email', pages[0])
        self.assertEqual(lags[0]['samples'], 1)
        self.assertEqual((writer.pending_pages, writer.pending_lag), ([], []))

    def test_a_database_failure_keeps_them(self):
        writer = rs.Writer(session_factory=self.session_class(fail=True))
        rs.enqueue_page_view('case/timeline', 'VIEW', CASE, 900, 'a@b', {})
        lag = rs.LoopLag()
        lag.add(60.0, 5.0)
        lag.close()
        writer.flush()
        self.assertEqual((len(writer.pending_pages), len(writer.pending_lag)), (1, 1))


class MigrationHasEveryColumn(TestCase):
    def test_written_columns_exist(self):
        migration = (BACKEND / 'postgres/alembic/versions/20261031_lx_measure.py').read_text()
        for column in ('started_at', 'pid', 'pg_ms', 'pg_count', 'gzip_ms', 'cache', *rs.PAGE_COLUMNS):
            self.assertIn(f"'{column}'", migration, column)
        for table in ('request_speed_pages', 'request_speed_loop_lag', 'host_load_minute', 'availability_probe'):
            self.assertIn(f"'{table}'", migration)
        from scripts import host_recorder
        for column in re.findall(r'%\((\w+)\)s', host_recorder.INSERT_HOST + host_recorder.INSERT_PROBE):
            self.assertIn(f"'{column}'", migration, column)


class HostRecorder(TestCase):
    def test_pressure_and_secret_free_command(self):
        from scripts import host_recorder as hr
        with patch.object(hr, '_read', return_value='some avg10=1.00 avg60=2.00 avg300=3.00 total=1500\n'
                                                  'full avg10=0.00 avg60=0.00 avg300=0.00 total=20\n'):
            self.assertEqual(hr._pressure('x'), {'some': 1500, 'full': 20})
        cmd = '\0'.join(['/usr/bin/psql', 'postgresql://u:pw@h/db', '--password=hunter2', 'user@example.com', '-c',
                         'SELECT 1']) + '\0'
        with patch.object(hr, '_read', return_value=cmd):
            out = hr._command(1)
        self.assertEqual(out, 'psql -c SELECT 1')
        self.assertNotIn('hunter2', out)

    def test_sample_is_a_delta_over_the_measured_interval(self):
        from scripts import host_recorder as hr
        sampler = hr.Sampler()
        snaps = []

        def snap(mono, busy, cpu_some, group_us, ticks, self_cpu):
            return dict(mono=mono, wall=1_000_000_020.0 + mono, self_cpu=self_cpu,
                        host=dict(busy=busy, cpu_p={'some': cpu_some}, mem_p={}, io_p={}, swpin=10, swpout=4,
                                  mem_available=1000.0, swap_used=50.0, load1=3.0),
                        groups={'system.slice/owl-backend-v2.service': dict(cpu_us=group_us, cpu_p={'some': 0}, io_p={},
                                                                             mem_mb=500.0, swap_mb=0.0),
                                'system.slice/tiny.service': dict(cpu_us=0, cpu_p={}, io_p={}, mem_mb=1.0, swap_mb=0.0)},
                        procs={42: (ticks, 'python', 10), 43: (5, 'idle', 0)})
        snaps = [snap(0.0, 0, 0, 0, 0, 0.0), snap(60.0, 60 * hr.CLK * 2, 30_000_000, 90_000_000, 60 * hr.CLK, 0.012)]
        with patch.object(sampler, 'take', side_effect=snaps), patch.object(hr, '_command', return_value='python x'), \
                patch.object(hr, '_cgroup_of', return_value='/system.slice/fin-watchdog.service'):
            self.assertIsNone(sampler.sample())
            row = sampler.sample()
        self.assertEqual(row['interval_s'], 60.0)
        self.assertEqual(row['cpu_busy_cores'], 2.0)
        self.assertEqual(row['psi_cpu_some'], 50.0)
        self.assertEqual(row['groups'], {'system.slice/owl-backend-v2.service': dict(
            cores=1.5, cpu_some=0.0, cpu_full=None, io_some=None, mem_mb=500.0, swap_mb=0.0)})
        self.assertEqual([(p['pid'], p['cores']) for p in row['top']], [(42, 1.0)])
        self.assertEqual(row['recorder_cpu_ms'], 12.0)
        self.assertEqual(row['minute'].timestamp() % 60, 0)

    def test_probe_records_status_and_refusal(self):
        from scripts import host_recorder as hr

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'{"status":"ok"}'
                self.send_response(200 if self.path == '/api/health' else 502)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        ok = hr.probe('api', '/api/health', base=base, timeout=5)
        self.assertEqual((ok['status'], ok['bytes'], ok['error']), (200, 15, None))
        self.assertEqual(hr.probe('app', '/', base=base, timeout=5)['status'], 502)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            free = s.getsockname()[1]
        down = hr.probe('app', '/', base=f'http://127.0.0.1:{free}', timeout=2)
        self.assertIsNone(down['status'])
        self.assertIn('refused', down['error'].lower())


class RecorderWatchdog(TestCase):
    def test_a_stalled_loop_exits_to_be_restarted(self):
        from scripts import host_recorder as hr
        progress = [time.monotonic() - 10]
        with patch.object(hr.os, '_exit', side_effect=SystemExit(3)) as exited, patch.object(hr.time, 'sleep'):
            with self.assertRaises(SystemExit):
                hr.watchdog(progress, stall=5)
        exited.assert_called_once_with(3)


class SqlListenersNeverRaise(Captured):
    def test_a_broken_connection_info_does_not_replace_the_result(self):
        rs.install_sql_timing()
        before, after, failed = rs._SQL_TIMED[0]

        class Broken:
            @property
            def info(self):
                raise RuntimeError('invalidated')
        token = rs._person.set({})
        try:
            before(Broken(), None, 'SELECT 1', None, None, False)
            after(Broken(), None, 'SELECT 1', None, None, False)

            class Context:
                connection = Broken()
            failed(Context())
        finally:
            rs._person.reset(token)


class RecorderStore(TestCase):
    def test_rows_survive_a_failed_write_and_rows_added_meanwhile_are_kept(self):
        from scripts import host_recorder as hr
        store = hr.Store('postgresql://nowhere.invalid/x')
        store.add(host={'minute': 1}, probes=[{'p': 1}])

        def connect(*a, **k):
            store.add(probes=[{'p': 2}])  # the probe thread, during the write
            raise OSError('down')
        import psycopg
        with patch.object(psycopg, 'connect', side_effect=connect):
            store.flush()
        self.assertEqual(store.hosts, [{'minute': 1}])
        self.assertEqual(store.probes, [{'p': 1}, {'p': 2}])

    def test_a_probe_added_during_a_successful_write_is_not_lost(self):
        from contextlib import nullcontext
        from scripts import host_recorder as hr
        store = hr.Store('postgresql://x/y')
        store.add(probes=[{'p': 1}])
        written = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a):
                pass

            def executemany(self, sql, rows):
                written.extend(rows)
                store.add(probes=[{'p': 2}])  # the probe thread, during the write

        class Conn:
            closed = False

            def transaction(self):
                return nullcontext()

            def cursor(self):
                return Cursor()
        store.conn = Conn()
        store.pruned = time.time()
        store.flush()
        self.assertEqual(written, [{'p': 1}])
        self.assertEqual(store.probes, [{'p': 2}])
