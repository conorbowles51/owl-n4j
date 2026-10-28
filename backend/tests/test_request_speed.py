"""Request speed: what the middleware keeps, that saving never touches a request, and the arithmetic.

Pins: the route template is kept, never the raw path or a query value other than the case id;
the case comes from the path or the query; status, bytes and the person's email (resolved to an
id only in the writer) are kept; a failing queue or database never changes a response; failed
flushes keep their totals for the next one; percentiles come from the merged histogram;
requests over 2 s become slow rows and over 5 s log one WARNING line; page views are validated.
"""
import logging
import time
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from fastapi import Depends, FastAPI, Query
from fastapi.testclient import TestClient

from services import request_speed as rs

CASE = 'd5b330d1-1111-2222-3333-444455556666'


def person():
    rs.note_person('alex@example.com')


def build_app():
    app = FastAPI()
    app.add_middleware(rs.RequestSpeedMiddleware)

    @app.get('/api/cases/{case_id}/files/{file_id}')
    def file(case_id: str, file_id: str, _=Depends(person)):
        return {'ok': True}

    @app.get('/api/financial/summary')
    def summary(case_id: str = Query(None), secret: str = Query(None), _=Depends(person)):
        return {'rows': [1, 2, 3]}

    @app.get('/api/stream')
    def stream():
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter([b'data: 1\n\n']), media_type='text/event-stream')

    @app.get('/api/public')
    def public(case_id: str = Query(None)):
        return {}

    @app.api_route('/api/odd', methods=['MKCALENDAR'])
    def odd():
        return {}

    @app.get('/api/boom')
    def boom():
        raise RuntimeError('boom')

    @app.get('/health')
    def health():
        return {}
    return app


class Captured(TestCase):
    def setUp(self):
        rs._queue.clear()
        started = patch.object(rs._writer, 'ensure_started')
        started.start()
        self.addCleanup(started.stop)
        self.client = TestClient(build_app(), raise_server_exceptions=False)

    def drained(self):
        items = list(rs._queue)
        rs._queue.clear()
        return items


class MiddlewareRecords(Captured):
    def test_template_case_status_bytes_and_person(self):
        response = self.client.get(f'/api/cases/{CASE}/files/abc123')
        self.assertEqual(response.status_code, 200)
        [(at, kind, method, route, case, status, ms, size, email)] = self.drained()
        self.assertEqual((kind, method, route), ('api', 'GET', '/api/cases/{case_id}/files/{file_id}'))
        self.assertEqual(case, CASE)
        self.assertEqual(status, 200)
        self.assertEqual(size, len(response.content))
        self.assertEqual(email, 'alex@example.com')
        self.assertGreater(ms, 0)
        self.assertLess(abs(at - time.time()), 60)

    def test_case_from_query_and_no_other_query_value_kept(self):
        self.client.get(f'/api/financial/summary?secret=hunter2&case_id={CASE.upper()}')
        [item] = self.drained()
        self.assertEqual(item[3], '/api/financial/summary')
        self.assertEqual(item[4], CASE)
        self.assertNotIn('hunter2', repr(item))
        self.assertEqual(item[8], 'alex@example.com')

    def test_anonymous_or_unmatched_requests_keep_no_case(self):
        self.client.get(f'/api/public?case_id={CASE}')
        self.client.get(f'/api/nothing?case_id={CASE}')
        self.assertEqual([item[4] for item in self.drained()], [None, None])

    def test_event_streams_are_labelled_and_never_slow(self):
        with patch.object(rs, 'SLOW_LOG_SECONDS', 0.0), patch.object(rs, 'SLOW_ROW_SECONDS', 0.0), \
                self.assertNoLogs(rs.log, logging.WARNING):
            self.client.get('/api/stream')
        items = self.drained()
        self.assertEqual(items[0][3], '/api/stream (stream)')
        with patch.object(rs, 'SLOW_ROW_SECONDS', 0.0):
            self.assertEqual(rs.aggregate(items, {})[1], [])

    def test_unknown_methods_are_kept_as_other(self):
        self.client.request('MKCALENDAR', '/api/odd')
        self.client.request('PROPPATCHXYZ', '/api/odd')
        self.assertEqual({item[2] for item in self.drained()}, {'OTHER'})

    def test_unmatched_path_is_not_kept_raw(self):
        self.client.get(f'/api/nothing/{CASE}/here')
        [item] = self.drained()
        self.assertEqual((item[3], item[5]), (rs.UNMATCHED, 404))
        self.assertNotIn('nothing', repr(item))

    def test_server_error_is_recorded(self):
        self.assertEqual(self.client.get('/api/boom').status_code, 500)
        [item] = self.drained()
        self.assertEqual((item[3], item[5]), ('/api/boom', 500))

    def test_only_api_is_timed(self):
        self.client.get('/health')
        self.assertEqual(self.drained(), [])

    def test_not_a_uuid_is_not_a_case(self):
        self.client.get('/api/financial/summary?case_id=../../etc')
        self.assertIsNone(self.drained()[0][4])

    def test_slow_request_logs_one_warning_line(self):
        with patch.object(rs, 'SLOW_LOG_SECONDS', 0.0), self.assertLogs(rs.log, logging.WARNING) as logs:
            self.client.get(f'/api/financial/summary?case_id={CASE}')
        self.assertEqual(len(logs.records), 1)
        self.assertRegex(logs.output[0], r'Slow request: GET /api/financial/summary case d5b330d1 \d+\.\d s')


class NeverBreaksARequest(Captured):
    def test_queue_failure_leaves_the_response_alone(self):
        with patch.object(rs, '_template', side_effect=RuntimeError('x')), self.assertLogs(rs.log, logging.ERROR):
            response = self.client.get(f'/api/financial/summary?case_id={CASE}')
        self.assertEqual((response.status_code, response.json()), (200, {'rows': [1, 2, 3]}))

    def test_database_failure_keeps_totals_and_never_raises(self):
        def broken():
            raise RuntimeError('database is busy')
        writer = rs.Writer(session_factory=broken)
        self.client.get(f'/api/financial/summary?case_id={CASE}')
        self.client.get(f'/api/financial/summary?case_id={CASE}')
        with self.assertLogs(rs.log, logging.WARNING):
            writer.flush()
        self.assertEqual(len(rs._queue), 0)
        [group] = writer.pending_groups.values()
        self.assertEqual(group.count, 2)
        writer.flush()  # still failing: kept, not doubled
        self.assertEqual([g.count for g in writer.pending_groups.values()], [2])

    def test_pending_is_bounded(self):
        writer = rs.Writer(session_factory=lambda: (_ for _ in ()).throw(RuntimeError('down')))
        with patch.object(rs, 'MAX_PENDING_KEYS', 3), self.assertLogs(rs.log, logging.WARNING):
            for i in range(5):
                rs.enqueue('api', 'GET', f'/api/r{i}', None, 200, 5, 0, None)
            writer.flush()
        self.assertEqual(writer.pending_groups, {})

    def test_successful_flush_writes_and_clears(self):
        calls = []

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def rollback(self):
                pass

            def execute(self, statement, params=None):
                class Result:
                    def all(self_inner):
                        return [('alex@example.com', 'u-1')]
                return Result()
        writer = rs.Writer(session_factory=Session)
        rs.enqueue('api', 'GET', '/api/x', CASE, 200, 3000, 10, 'alex@example.com')
        with patch.object(rs, 'write', side_effect=lambda s, g, sl: calls.append((dict(g), list(sl)))):
            writer.flush()
        [(groups, slow)] = calls
        [key] = groups
        self.assertEqual(key[1:], ('api', 'GET', '/api/x', CASE, 'u-1'))
        self.assertEqual(slow[0]['user_id'], 'u-1')
        self.assertEqual(writer.pending_groups, {})


class RefusedRowsDoNotBlock(TestCase):
    def test_a_refused_group_is_dropped_alone(self):
        from contextlib import nullcontext
        from sqlalchemy.exc import DataError
        done = []

        class Row:
            id, buckets, max_ms = 1, [0] * rs.BUCKET_COUNT, 5.0

        class Session:
            def begin_nested(self):
                return nullcontext()

            def commit(self):
                done.append('commit')

            def execute(self, statement, params=None):
                if 'INSERT INTO request_speed_hourly' in str(statement):
                    if params['route'] == '/bad':
                        raise DataError('x', {}, Exception('value too long'))
                    done.append(params['route'])

                class Result:
                    def one(self_inner):
                        return Row
                return Result()
        groups, slow = rs.aggregate([(1e9, 'api', 'GET', '/bad', None, 200, 5.0, 0, None),
                                     (1e9, 'api', 'GET', '/good', None, 200, 5.0, 0, None)], {})
        with self.assertLogs(rs.log, logging.WARNING):
            rs.write(Session(), groups, slow)
        self.assertEqual(done, ['/good', 'commit'])


class Arithmetic(TestCase):
    def test_buckets_cover_every_duration(self):
        self.assertEqual(rs.bucket_of(0), 0)
        self.assertEqual(rs.bucket_of(1.0), 0)
        self.assertEqual(rs.bucket_of(1.01), 1)
        self.assertEqual(rs.bucket_of(10 ** 9), rs.BUCKET_COUNT - 1)
        self.assertGreater(rs.BUCKET_EDGES_MS[-1], 600000)

    def test_percentiles_within_a_bucket_of_the_truth(self):
        group = rs.Group()
        for ms in range(1, 1001):
            group.add(float(ms), 0, 200)
        p50 = rs.percentile(group.buckets, 0.5, group.max_ms)
        p95 = rs.percentile(group.buckets, 0.95, group.max_ms)
        self.assertTrue(500 / 1.15 <= p50 <= 500 * 1.15, p50)
        self.assertTrue(950 / 1.15 <= p95 <= 1000, p95)
        self.assertEqual(rs.percentile(group.buckets, 1.0, group.max_ms), 1000)
        self.assertIsNone(rs.percentile([0] * rs.BUCKET_COUNT, 0.5))

    def test_merged_histograms_give_the_same_percentiles_as_one(self):
        a, b, whole = rs.Group(), rs.Group(), rs.Group()
        for i, ms in enumerate([5, 7, 9, 120, 800, 3000, 15, 22, 40, 9000]):
            (a if i % 2 else b).add(ms, 100, 200 if ms < 9000 else 503)
            whole.add(ms, 100, 200 if ms < 9000 else 503)
        a.merge(b)
        self.assertEqual(a.buckets, whole.buckets)
        self.assertEqual((a.count, a.max_ms, a.bytes, a.errors), (10, 9000, 1000, 1))
        self.assertEqual(a.total_ms, sum([5, 7, 9, 120, 800, 3000, 15, 22, 40, 9000]))
        for q in (0.5, 0.95):
            self.assertEqual(rs.percentile(a.buckets, q, a.max_ms), rs.percentile(whole.buckets, q, whole.max_ms))

    def test_aggregate_groups_by_hour_and_keeps_only_slow_rows(self):
        t = datetime(2026, 10, 28, 13, 59, 59, tzinfo=timezone.utc).timestamp()
        items = [(t, 'api', 'GET', '/a', CASE, 200, 100.0, 1, 'x@y'),
                 (t, 'api', 'GET', '/a', CASE, 200, 2500.0, 1, 'x@y'),
                 (t + 2, 'api', 'GET', '/a', CASE, 200, 50.0, 1, 'x@y')]
        groups, slow = rs.aggregate(items, {'x@y': 'u1'})
        self.assertEqual(sorted((k[0].hour, g.count) for k, g in groups.items()), [(13, 2), (14, 1)])
        self.assertEqual([(s['duration_ms'], s['user_id'], s['route']) for s in slow], [(2500.0, 'u1', '/a')])


class PageViews(TestCase):
    def setUp(self):
        rs._queue.clear()
        started = patch.object(rs._writer, 'ensure_started')
        started.start()
        self.addCleanup(started.stop)

    def test_valid_view_is_queued_as_a_page(self):
        self.assertTrue(rs.enqueue_page_view('financial/overview', 'LOAD', CASE, 1234.5, 'a@b'))
        [item] = list(rs._queue)
        self.assertEqual(item[1:9], ('page', 'LOAD', 'financial/overview', CASE, 200, 1234.5, 0, 'a@b'))
        self.assertTrue(rs.enqueue_page_view('financial/ledger', 'LEFT', CASE, 90000, 'a@b'))

    def test_bad_names_methods_and_times_are_refused(self):
        for args in [('Financial/../x', 'LOAD', None, 5), ('financial/overview', 'GET', None, 5),
                     ('financial/made-up', 'VIEW', None, 5), ('financial/statements/queue/x', 'VIEW', None, 5),
                     ('financial/overview', 'VIEW', None, -1), ('financial/overview', 'VIEW', None, 10 ** 7),
                     ('', 'VIEW', None, 5)]:
            self.assertFalse(rs.enqueue_page_view(*args, None), args)
        self.assertEqual(len(rs._queue), 0)

    def test_router_accepts_a_batch(self):
        from routers import request_speed as router
        app = FastAPI()
        app.include_router(router.router)
        app.dependency_overrides[router.get_current_user] = lambda: {'username': 'a@b'}
        response = TestClient(app).post('/api/request-speed/page-views', json={'views': [
            {'page': 'financial/ledger', 'method': 'VIEW', 'case_id': CASE, 'ms': 900},
            {'page': 'BAD NAME', 'method': 'VIEW', 'ms': 900}]})
        self.assertEqual((response.status_code, response.json()), (202, {'accepted': 1}))
        self.assertEqual(len(rs._queue), 1)


class PageNamesMatchTheFrontend(TestCase):
    def test_financial_views_are_the_frontend_list(self):
        import re
        from pathlib import Path
        store = (Path(__file__).resolve().parents[2] / 'frontend_v2/src/features/financial/stores/financial.store.ts').read_text()
        block = re.search(r'financialMainViews = \[(.*?)\] as const', store, re.S).group(1)
        views = set(re.findall(r'"([a-z-]+)"', block))
        self.assertEqual(views - {'statements'}, set(rs.FINANCIAL_VIEWS))
        page = (Path(__file__).resolve().parents[2] / 'frontend_v2/src/features/financial/components/FinancialPage.tsx').read_text()
        sections = re.search(r'type StatementSection = ([^\n]+)', page).group(1)
        self.assertEqual(set(re.findall(r'"([a-z]+)"', sections)), set(rs.STATEMENT_SECTIONS))
