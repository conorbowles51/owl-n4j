"""postgres.session: every connection says which process opened it, the pool is sized from the environment, and
a wait for a pooled connection is measured and logged (lx-datastores, WS-G a/b)."""
import logging
import os
import tempfile
import threading
import time
import unittest

from sqlalchemy import create_engine, text

from postgres import session


class ProcessRoleTest(unittest.TestCase):
    def test_roles_from_the_entry_point(self):
        self.assertEqual(session.process_role(['/x/.venv/bin/uvicorn', 'main:app'], {}), 'web')
        self.assertEqual(session.process_role(['/b/services/financial/vision_rounds.py', '--lock-held'], {}),
                         'vision_rounds')
        self.assertEqual(session.process_role(['/b/services/financial/batch_rounds.py', '--lock-held'], {}),
                         'batch_rounds')
        self.assertEqual(session.process_role(['/b/services/financial/view_warmup.py', '--lock-held'], {}),
                         'view_warmup')
        self.assertEqual(session.process_role(['/b/services/financial/view_warmup.py', '--prepare-share', '0/3'],
                                              {}), 'prepare')
        self.assertEqual(session.process_role(['/b/services/financial/view_warmup.py', '--prepare'], {}), 'prepare')
        self.assertEqual(session.process_role([], {}), 'python')

    def test_environment_overrides(self):
        self.assertEqual(session.process_role(['/x/uvicorn'], {'LOUPE_DB_ROLE': 'jobs-instance'}), 'jobs-instance')

    def test_application_name_fits_postgres(self):
        self.assertEqual(session.application_name(['/x/uvicorn'], {}, pid=42), 'loupe-web-42')
        self.assertLessEqual(len(session.application_name(['/' + 'a' * 100], {}, pid=1)), 63)


class PoolOptionsTest(unittest.TestCase):
    def test_defaults_are_sqlalchemys(self):
        self.assertEqual(session.pool_options({}), dict(pool_size=5, max_overflow=10, pool_timeout=30.0))

    def test_from_environment(self):
        self.assertEqual(session.pool_options({'POSTGRES_POOL_SIZE': '12', 'POSTGRES_MAX_OVERFLOW': '3',
                                               'POSTGRES_POOL_TIMEOUT': '7.5'}),
                         dict(pool_size=12, max_overflow=3, pool_timeout=7.5))


class TimedPoolTest(unittest.TestCase):
    def test_a_long_wait_is_logged_with_the_pool_state(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine('sqlite:///' + os.path.join(directory, 'p.db'), poolclass=session.TimedQueuePool,
                                   pool_size=1, max_overflow=0, pool_timeout=5)
            held = engine.connect()
            released = threading.Event()

            def release():
                time.sleep(0.3)
                held.close()
                released.set()

            old = session.POOL_WAIT_LOG_SECONDS
            session.POOL_WAIT_LOG_SECONDS = 0.2
            try:
                threading.Thread(target=release).start()
                with self.assertLogs(session.logger, logging.WARNING) as logs:
                    with engine.connect() as connection:
                        self.assertEqual(connection.execute(text('select 1')).scalar(), 1)
            finally:
                session.POOL_WAIT_LOG_SECONDS = old
            self.assertTrue(released.is_set())
            self.assertIn('Postgres pool wait', logs.output[0])
            self.assertIn('Pool size: 1', logs.output[0])
            engine.dispose()

    def test_the_wait_reaches_the_request_timing_when_it_records_it(self):
        from services import request_speed
        seen = []
        had = hasattr(request_speed, 'note_pool_wait')
        old = getattr(request_speed, 'note_pool_wait', None)
        request_speed.note_pool_wait = seen.append
        try:
            with tempfile.TemporaryDirectory() as directory:
                engine = create_engine('sqlite:///' + os.path.join(directory, 'p.db'),
                                       poolclass=session.TimedQueuePool, pool_size=1, max_overflow=0)
                with engine.connect():
                    pass
                engine.dispose()
        finally:
            if had:
                request_speed.note_pool_wait = old
            else:
                del request_speed.note_pool_wait
        self.assertEqual(len(seen), 1)
        self.assertGreaterEqual(seen[0], 0.0)


if __name__ == '__main__':
    unittest.main()
