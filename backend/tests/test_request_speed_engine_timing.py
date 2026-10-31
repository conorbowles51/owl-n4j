"""An evidence engine call inside a request is timed: Server-Timing "engine" and the slow-request log line split
a slow engine poll into engine time and this server's own time (the 14.6 s poll of 31 Oct 10:27 could not be)."""
import asyncio
import logging
from unittest import TestCase
from unittest.mock import patch

import httpx
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from services import evidence_engine_client as client_module
from services import request_speed as rs


def _engine(request):
    return httpx.Response(200, json=[{"id": "j1", "status": "completed"}])


def person():
    rs.note_person('alex@example.com')


def build_app(client):
    app = FastAPI()
    app.add_middleware(rs.RequestSpeedMiddleware)

    @app.get('/api/evidence/engine/jobs')
    async def jobs(_=Depends(person)):
        response = await client.get('/cases/c/jobs')
        return response.json()

    @app.get('/api/plain')
    def plain(_=Depends(person)):
        return {'ok': True}
    return app


class EngineTiming(TestCase):
    def setUp(self):
        rs._queue.clear()
        started = patch.object(rs._writer, 'ensure_started')
        started.start()
        self.addCleanup(started.stop)
        self.engine = client_module._TimedClient(base_url='http://engine', transport=httpx.MockTransport(_engine))
        self.client = TestClient(build_app(self.engine), raise_server_exceptions=False)

    def tearDown(self):
        rs._queue.clear()

    def test_engine_time_is_in_server_timing_and_the_body_is_unchanged(self):
        response = self.client.get('/api/evidence/engine/jobs')
        self.assertEqual(response.json(), [{"id": "j1", "status": "completed"}])
        self.assertIn('engine;dur=', response.headers['server-timing'])
        self.assertIn('desc="1 calls"', response.headers['server-timing'])

    def test_a_request_without_an_engine_call_has_no_engine_part(self):
        self.assertNotIn('engine', self.client.get('/api/plain').headers['server-timing'])

    def test_the_slow_log_line_carries_engine_and_database_time(self):
        with patch.object(rs, 'SLOW_LOG_SECONDS', 0.0), self.assertLogs(rs.log, logging.WARNING) as logged:
            self.client.get('/api/evidence/engine/jobs')
        self.assertRegex(logged.output[-1], r'\[pg [0-9.]+ s, engine [0-9.]+ s\]$')

    def test_the_shared_client_is_the_timed_one(self):
        with patch.object(client_module, '_client', None):
            shared = client_module._get_client()
            try:
                self.assertIsInstance(shared, client_module._TimedClient)
            finally:
                asyncio.run(shared.aclose())

    def test_an_engine_call_outside_a_request_is_not_an_error(self):
        async def call():
            async with client_module._TimedClient(base_url='http://engine',
                                                  transport=httpx.MockTransport(_engine)) as engine:
                return (await engine.get('/cases/c/jobs')).status_code
        self.assertEqual(asyncio.run(call()), 200)
