"""A release runs two backends side by side for a few seconds: every background loop still does its work once."""
import ast
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]

HOLDER = '''
import sys, time, os
sys.path.insert(0, %(backend)r)
from services.financial import vision_rounds, batch_rounds, view_warmup
lock = {
    "vision": lambda: vision_rounds._take_lock(),
    "rounds": lambda: vision_rounds._take_lock(batch_rounds.LOCK_NAME),
    "warmup": lambda: view_warmup._take_lock(),
    "refresh": lambda: view_warmup._take_lock(name=__import__("services.financial.view_refresh", fromlist=["LOCK"]).LOCK),
}[sys.argv[1]]
out = sys.argv[2]
held = None
while True:
    if held is None:
        held = lock()
        if held is not None:
            with open(out, "a") as handle:
                handle.write("%%d\\n" %% os.getpid())
    time.sleep(0.05)
'''


class EveryLoopHasAnOwner(unittest.TestCase):
    def test_every_task_main_starts_is_listed_with_its_owner(self):
        from services.backend_handover import BACKGROUND_LOOPS
        tree = ast.parse((BACKEND / 'main.py').read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'create_task':
                name = next((k.value.value for k in node.keywords if k.arg == 'name'), None)
                self.assertIsNotNone(name, f'line {node.lineno}: a background task with no name')
                names.add(name)
        started_elsewhere = {'job-status-subscriber'}
        self.assertEqual(names | started_elsewhere, set(BACKGROUND_LOOPS))
        self.assertLessEqual(set(BACKGROUND_LOOPS.values()), {'host-lock', 'row-claim', 'per-process'})

    def test_host_lock_loops_have_a_lock_in_their_code(self):
        from services import address_lookup
        from services.financial import view_refresh, view_warmup, vision_rounds, batch_rounds
        from services.phone import sweep_worker
        self.assertTrue(address_lookup._LOCK_PATH)
        self.assertTrue(view_refresh.LOCK and view_warmup.PREPARE_LOCK)
        self.assertTrue(vision_rounds.LOCK_NAME and batch_rounds.LOCK_NAME)
        self.assertTrue(hasattr(sweep_worker, 'EXIT_ALREADY_RUNNING'))


class TwoBackendsOneHolder(unittest.TestCase):
    """Real processes, as two backends are: one holds each host-wide loop, the other takes over when it ends."""

    def _start(self, kind, out, env):
        code = HOLDER % dict(backend=str(BACKEND))
        return subprocess.Popen([sys.executable, '-c', code, kind, out], env=env, cwd=str(BACKEND))

    def test_one_holder_and_a_takeover(self):
        for kind in ('vision', 'rounds', 'warmup', 'refresh'):
            with self.subTest(kind), tempfile.TemporaryDirectory() as root:
                env = dict(os.environ, FINANCIAL_VIEW_MEMO_DIR=root, PYTHONPATH=str(BACKEND))
                out = os.path.join(root, 'holders')
                first = self._start(kind, out, env)
                second = None
                try:
                    self._wait(lambda: self._holders(out) == [str(first.pid)])
                    second = self._start(kind, out, env)
                    time.sleep(3)
                    self.assertEqual(self._holders(out), [str(first.pid)])
                    first.kill()
                    first.wait()
                    self._wait(lambda: self._holders(out) == [str(first.pid), str(second.pid)])
                finally:
                    for process in (first, second):
                        if process is not None:
                            process.kill()
                            process.wait()

    @staticmethod
    def _holders(path):
        return Path(path).read_text().split() if os.path.exists(path) else []

    @staticmethod
    def _wait(check, limit=240):
        deadline = time.monotonic() + limit
        while time.monotonic() < deadline:
            if check():
                return
            time.sleep(0.1)
        raise AssertionError('not reached')


class AfterTheOldBackendStopped(unittest.IsolatedAsyncioTestCase):
    async def test_runs_the_step_once_the_old_backend_has_stopped(self):
        from services import backend_handover
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'state.json'
            path.write_text(json.dumps(dict(handover=dict(phase='ready'))))
            ran = []

            async def step():
                ran.append(1)

            waiter = asyncio.create_task(backend_handover.after_old_backend_stopped(step, path=path, look_seconds=0.01,
                                                                                    limit_seconds=30))
            await asyncio.sleep(0.05)
            self.assertEqual(ran, [])
            path.write_text(json.dumps(dict(handover=dict(phase='done', old_stopped_at=time.time()))))
            self.assertTrue(await waiter)
            self.assertEqual(ran, [1])

    async def test_a_handover_before_this_start_runs_nothing(self):
        from services import backend_handover
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'state.json'
            path.write_text(json.dumps(dict(handover=dict(phase='done', old_stopped_at=time.time() - 60))))

            async def step():
                raise AssertionError('a plain restart has nothing to recover twice')

            self.assertFalse(await backend_handover.after_old_backend_stopped(step, path=path, look_seconds=0.01,
                                                                              limit_seconds=0.05))

    def test_a_backend_with_no_lock_location_says_so(self):
        from services import backend_handover
        with patch.dict(os.environ, FINANCIAL_VIEW_MEMO_DIR=''):
            self.assertFalse(backend_handover.process_identity()['one_owner'])
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, FINANCIAL_VIEW_MEMO_DIR=root):
            self.assertTrue(backend_handover.process_identity()['one_owner'])
