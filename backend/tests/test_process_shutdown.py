"""Shutdown must finish within a bound whatever the background work is doing.

The hang these tests pin down: on stop, Uvicorn waited without limit for
request tasks, and the lifespan then awaited background loops that were
themselves awaiting uncancellable worker threads (an atomic statement unit,
the identity-graph sweep). A deploy's restart could therefore stall for the
whole systemd stop window.
"""

import asyncio
import importlib.util
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from services import process_shutdown
from services.financial import identity_graph
from services.financial.import_batches import _finish_atomic

BACKEND_DIR = Path(__file__).resolve().parents[1]


class ShutdownStateMixin:
    def setUp(self):
        process_shutdown._reset_for_tests()
        self.release = threading.Event()

    def tearDown(self):
        # Let abandoned worker threads return so the test process stays clean.
        self.release.set()
        process_shutdown._reset_for_tests()


class BackgroundTaskBoundTests(ShutdownStateMixin, unittest.TestCase):
    def blocking_unit(self, entered):
        entered.set()
        self.release.wait(60)

    def test_atomic_unit_stuck_in_a_thread_is_abandoned_within_the_bound(self):
        entered = threading.Event()

        async def scenario():
            stuck = asyncio.create_task(_finish_atomic(self.blocking_unit, entered), name="stuck-import")
            idle = asyncio.create_task(asyncio.sleep(3600), name="idle-loop")
            while not entered.is_set():
                await asyncio.sleep(0.01)
            started = time.monotonic()
            pending = await process_shutdown.stop_background_tasks([stuck, idle, None], timeout=0.5)
            elapsed = time.monotonic() - started
            self.assertEqual(pending, {stuck})
            self.assertTrue(idle.cancelled())
            self.assertLess(elapsed, 1.5)
            self.assertTrue(process_shutdown.shutdown_requested())
            # The event loop's own teardown cancels again; the abandoned task
            # must then end without waiting for its thread.
            stuck.cancel()
            self.release.set()  # Else asyncio.run's executor shutdown waits on it.
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(stuck, 1)
            return elapsed

        asyncio.run(scenario())

    def test_previous_unbounded_pattern_does_not_finish(self):
        """Baseline: the old lifespan exit (cancel, then gather) waits for the thread."""
        entered = threading.Event()

        async def scenario():
            stuck = asyncio.create_task(_finish_atomic(self.blocking_unit, entered))
            while not entered.is_set():
                await asyncio.sleep(0.01)
            stuck.cancel()
            done, _ = await asyncio.wait([asyncio.ensure_future(
                asyncio.gather(stuck, return_exceptions=True))], timeout=2)
            self.assertFalse(done, "the old pattern should still be waiting on the thread")
            self.release.set()
            await asyncio.gather(stuck, return_exceptions=True)

        asyncio.run(scenario())

    def test_identity_sweep_stuck_in_a_case_is_abandoned_within_the_bound(self):
        entered = threading.Event()

        def sweep(stop=None):
            # A projection blocked inside one case never reaches the
            # between-case stop check.
            self.blocking_unit(entered)

        async def scenario():
            with patch.object(identity_graph, "sync_saved_identities", sweep):
                task = asyncio.create_task(identity_graph.run_identity_graph_forever(), name="sweep")
                while not entered.is_set():
                    await asyncio.sleep(0.01)
                started = time.monotonic()
                pending = await process_shutdown.stop_background_tasks([task], timeout=0.5)
                self.assertLess(time.monotonic() - started, 1.5)
                self.assertEqual(pending, {task})
                task.cancel()
                self.release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 1)

        asyncio.run(scenario())

    def test_identity_sweep_that_observes_stop_finishes_inside_the_bound(self):
        entered = threading.Event()

        def sweep(stop=None):
            entered.set()
            while not stop.is_set():
                time.sleep(0.01)

        async def scenario():
            with patch.object(identity_graph, "sync_saved_identities", sweep):
                task = asyncio.create_task(identity_graph.run_identity_graph_forever(), name="sweep")
                while not entered.is_set():
                    await asyncio.sleep(0.01)
                pending = await process_shutdown.stop_background_tasks([task], timeout=2)
                self.assertEqual(pending, set())
                self.assertTrue(task.cancelled())

        asyncio.run(scenario())


class WatchdogTests(ShutdownStateMixin, unittest.TestCase):
    def test_watchdog_ends_the_process_at_the_deadline_once(self):
        exits = []
        exited = threading.Event()

        def fake_exit(code):
            exits.append((code, time.monotonic()))
            exited.set()

        started = time.monotonic()
        process_shutdown.request_shutdown(deadline=0.3, diagnose_after=0.1, exit_process=fake_exit)
        process_shutdown.request_shutdown(deadline=0.01, exit_process=fake_exit)  # Already armed.
        self.assertTrue(exited.wait(3))
        time.sleep(0.2)
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0][0], 1)
        self.assertGreaterEqual(exits[0][1] - started, 0.29)
        self.assertTrue(process_shutdown.shutdown_requested())

    def test_signal_handler_chains_to_the_server_handler_and_arms_the_watchdog(self):
        seen = []
        exited = threading.Event()
        original = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

        async def scenario():
            signal.signal(signal.SIGTERM, lambda sig, frame: seen.append(sig))
            with patch.object(process_shutdown, "HARD_DEADLINE_SECONDS", 0.2), \
                    patch.object(process_shutdown, "DIAGNOSE_AFTER_SECONDS", 0.05):
                self.assertTrue(process_shutdown.install_signal_handlers(
                    exit_process=lambda code: exited.set()))
                os.kill(os.getpid(), signal.SIGTERM)
                await asyncio.sleep(0.05)
                self.assertEqual(seen, [signal.SIGTERM])
                self.assertTrue(process_shutdown.shutdown_requested())
                await asyncio.sleep(0.4)

        try:
            asyncio.run(scenario())
        finally:
            for sig, handler in original.items():
                signal.signal(sig, handler)
        self.assertTrue(exited.wait(2))

    def test_describe_task_names_the_innermost_await(self):
        async def inner():
            await asyncio.sleep(3600)

        async def outer():
            await inner()

        async def scenario():
            task = asyncio.create_task(outer(), name="probe")
            await asyncio.sleep(0)
            text = process_shutdown.describe_task(task)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return text

        text = asyncio.run(scenario())
        self.assertIn("probe", text)
        self.assertIn("inner", text)


def _main_importable():
    try:
        import main  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(_main_importable(), "main.py import chain needs the full backend requirements")
class LifespanShutdownTests(ShutdownStateMixin, unittest.TestCase):
    """The real lifespan with its background loops running, stopped within the bound."""

    def test_lifespan_exit_completes_within_the_bound_with_stuck_background_work(self):
        import main
        entered = {"batches": threading.Event(), "sweep": threading.Event(), "recovery": threading.Event()}

        def stuck(name):
            async def loop():
                await _finish_atomic(self.blocking_unit_named, name, entered[name])
            return loop

        class Subscriber:
            async def start(self):
                pass

            async def stop(self):
                pass

        async def forever(**_):
            await asyncio.sleep(3600)

        async def no_op():
            return None

        patches = [
            patch.object(main.snapshot_storage, "reload", lambda: None),
            patch.object(main.snapshot_storage, "get_all", lambda: []),
            patch.object(main, "_cleanup_stale_chunks", forever),
            patch.object(main, "reap_stale_runs_forever", forever),
            patch.object(main, "get_subscriber", lambda: Subscriber()),
            patch.object(main.neo4j_service, "close", lambda: None),
            patch.object(main.evidence_engine_client, "close", no_op),
            patch.object(main, "close_redis", no_op),
            patch("services.financial.import_batches.run_batches_forever", stuck("batches")),
            patch("services.financial.identity_graph.run_identity_graph_forever", stuck("sweep")),
            patch("services.financial.deployment_recovery.run_recovery_forever", stuck("recovery")),
            patch.object(process_shutdown, "BACKGROUND_STOP_SECONDS", 0.5),
        ]

        async def scenario():
            for item in patches:
                item.start()
            try:
                # Not on the main thread's signal path: install is harmless here.
                async with main.lifespan(main.app):
                    for event in entered.values():
                        while not event.is_set():
                            await asyncio.sleep(0.01)
                    started = time.monotonic()
                elapsed = time.monotonic() - started
                self.release.set()
                return elapsed
            finally:
                for item in reversed(patches):
                    item.stop()

        original = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            elapsed = asyncio.run(scenario())
        finally:
            for sig, handler in original.items():
                signal.signal(sig, handler)
        self.assertLess(elapsed, 2.0)

    def blocking_unit_named(self, name, entered):
        entered.set()
        self.release.wait(60)


APP_SOURCE = textwrap.dedent('''
    import asyncio, os, threading
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    from services import process_shutdown
    from services.financial.import_batches import _finish_atomic

    FIXED = os.environ.get("SHUTDOWN_VARIANT") == "fixed"
    MARKER = os.environ["HANG_MARKER"]
    never = threading.Event()

    def atomic_unit():
        never.wait(600)

    @asynccontextmanager
    async def lifespan(app):
        if FIXED:
            process_shutdown.install_signal_handlers()
        task = asyncio.create_task(_finish_atomic(atomic_unit), name="stuck-import")
        yield
        if FIXED:
            await process_shutdown.stop_background_tasks([task])
        else:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(lifespan=lifespan)

    @app.get("/ready")
    async def ready():
        return {"ok": True}

    @app.get("/hang")
    async def hang():
        open(MARKER + str(os.getpid()), "w").close()
        await asyncio.to_thread(never.wait, 600)
''')


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(port, path, timeout):
    import http.client
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path)
        return connection.getresponse().status
    finally:
        connection.close()


@unittest.skipUnless(importlib.util.find_spec("uvicorn"), "uvicorn is not installed")
class UvicornStopTests(unittest.TestCase):
    """A real Uvicorn server holding a hung request and a stuck lifespan unit."""

    def stop_time(self, *, variant, workers, extra_args=(), env=None, give_up=20.0):
        workdir = tempfile.mkdtemp(prefix=f"loupe-shutdown-{os.getuid()}-")
        Path(workdir, "hang_app.py").write_text(APP_SOURCE)
        port = _free_port()
        marker = str(Path(workdir, "hang-"))
        environment = {**os.environ, "PYTHONPATH": f"{workdir}{os.pathsep}{BACKEND_DIR}",
                       "SHUTDOWN_VARIANT": variant, "HANG_MARKER": marker,
                       "PYTHONDONTWRITEBYTECODE": "1", **(env or {})}
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "hang_app:app", "--host", "127.0.0.1",
             "--port", str(port), "--workers", str(workers), *extra_args],
            cwd=workdir, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 60
            while True:
                try:
                    if _get(port, "/ready", 1) == 200:
                        break
                except OSError:
                    pass
                self.assertIsNone(server.poll(), "server exited during startup")
                self.assertLess(time.monotonic(), deadline, "server did not start")
                time.sleep(0.2)
            # One hung request per worker (connections are spread by the kernel).
            for _ in range(workers * 3):
                threading.Thread(target=lambda: _swallow(_get, port, "/hang", 120), daemon=True).start()
            deadline = time.monotonic() + 20
            while len(list(Path(workdir).glob("hang-*"))) < min(workers, 1):
                self.assertLess(time.monotonic(), deadline, "hung request never arrived")
                time.sleep(0.05)
            time.sleep(0.5)
            started = time.monotonic()
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(give_up)
                return time.monotonic() - started, server
            except subprocess.TimeoutExpired:
                return None, server
        finally:
            if server.poll() is None:
                server.kill()
                server.wait(10)
            for child in _children_of(server.pid):
                _swallow(os.kill, child, signal.SIGKILL)
            shutil.rmtree(workdir, ignore_errors=True)

    def test_before_fix_the_stop_never_completes(self):
        elapsed, server = self.stop_time(variant="old", workers=1, give_up=8)
        self.assertIsNone(elapsed, "baseline unexpectedly stopped; the hang reproduction is invalid")

    def test_request_timeout_and_lifespan_bound_stop_a_single_worker(self):
        elapsed, server = self.stop_time(variant="fixed", workers=1,
                                         extra_args=("--timeout-graceful-shutdown", "2"),
                                         env={"LOUPE_SHUTDOWN_BACKGROUND_SECONDS": "1"})
        self.assertIsNotNone(elapsed)
        self.assertLess(elapsed, 6)

    def test_watchdog_stops_the_process_without_the_uvicorn_timeout(self):
        elapsed, server = self.stop_time(variant="fixed", workers=1,
                                         env={"LOUPE_SHUTDOWN_DEADLINE_SECONDS": "3",
                                              "LOUPE_SHUTDOWN_DIAGNOSE_SECONDS": "1"})
        self.assertIsNotNone(elapsed)
        self.assertLess(elapsed, 6)
        output = server.stdout.read()
        self.assertIn("still running", output)
        self.assertIn("/hang", output)

    def test_two_workers_stop_within_the_bound_on_a_parent_sigterm(self):
        elapsed, server = self.stop_time(variant="fixed", workers=2,
                                         extra_args=("--timeout-graceful-shutdown", "2"),
                                         env={"LOUPE_SHUTDOWN_BACKGROUND_SECONDS": "1"})
        self.assertIsNotNone(elapsed)
        self.assertLess(elapsed, 8)


def _swallow(function, *args):
    try:
        function(*args)
    except Exception:
        pass


def _children_of(pid):
    try:
        output = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout
        return [int(line) for line in output.split()]
    except Exception:
        return []


if __name__ == "__main__":
    unittest.main()
