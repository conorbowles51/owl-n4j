"""Tests for the schedule the run safety net runs on.

``reap_stale_runs`` is tested against a database in ``test_financial_runs``:
which rows it picks, what it writes on them, how it reads a naive timestamp.
None of that is retested here.  What is tested here is the loop around it, and
the properties that matter about a loop are the ones that only show up when
something goes wrong.

*It sweeps before it sleeps.*  A restart is the event most likely to have
abandoned a run, so a loop that slept first would leave those rows wrong for a
full interval after the one moment they are most likely to exist.

*One bad sweep does not end the schedule.*  A background task that dies on its
first transient database error disables the safety net for the lifetime of the
process and says nothing.  That is the failure mode of the loop this one is
modelled on but does not copy.

*Cancellation still stops it.*  The handler that keeps the loop alive through
errors must not keep it alive through shutdown.

*The blocking call goes to a thread.*  ``reap_stale_runs`` opens a database
connection and waits on it.  Awaiting it inline would stall every request the
process is serving for the duration of the sweep, and nothing about the code
reads as wrong when it does.

Sweeps are observed through a spy that signals an event rather than by sleeping
for a plausible interval, so the tests neither race nor pad.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole, IngestionRunStatus
from postgres.models.financial import FinancialIngestionRun
from postgres.models.user import User
from services.financial import run_reaper
from services.financial.run_reaper import reap_stale_runs_forever

TABLES = [User.__table__, Case.__table__, FinancialIngestionRun.__table__]

# Short enough that a test never waits on it, long enough that a second sweep
# only happens because a test asked for one.
LONG_INTERVAL = timedelta(seconds=30)
TIGHT_INTERVAL = timedelta(milliseconds=1)


class _TailWatchingLogger:
    """The module logger, plus a signal when the error handler has spoken.

    Stands in for ``run_reaper.logger`` for the duration of a harnessed sweep.
    Every call is forwarded to the real logger object rather than to a
    look-alike, so ``assertLogs`` and ``assertNoLogs`` — which install their
    handler on the logger of that name — still see every record.  The one
    addition is that ``exception`` reports back, because that call is how an
    iteration ends when the sweep raised, and the harness has to know an
    iteration ended before it cancels the loop.
    """

    def __init__(self, wrapped, on_exception):
        self._wrapped = wrapped
        self._on_exception = on_exception

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def exception(self, *args, **kwargs):
        self._wrapped.exception(*args, **kwargs)
        self._on_exception()


class ReaperLoopTestCase(unittest.IsolatedAsyncioTestCase):
    """A database on disk, and a way to watch the loop sweep it.

    On disk rather than in memory for the same reason the run tests are: the
    sweep opens connections of its own, and under ``:memory:`` it would either
    get an empty database or share the caller's single transaction.  Here it is
    running on a worker thread as well, which an in-memory SQLite connection
    would refuse outright.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-reaper-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'ledger.db'}",
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )

        # The ids are held, the rows are not.  Committing expires an instance
        # and closing detaches it, so an attribute read afterwards would go
        # looking for a session that is gone.  Nothing here needs the objects
        # again; the fixture exists only to give the runs a case to belong to.
        self.user_id = uuid.uuid4()
        self.case_id = uuid.uuid4()
        session = self.SessionLocal()
        try:
            session.add_all(
                [
                    User(
                        id=self.user_id,
                        email="investigator@example.test",
                        name="Investigator",
                        password_hash="not-used",
                        global_role=GlobalRole.user,
                        is_active=True,
                    ),
                    Case(
                        id=self.case_id,
                        title="Reaper Fixture",
                        created_by_user_id=self.user_id,
                        owner_user_id=self.user_id,
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        # The loop is meant to be loud when it closes a run, and several tests
        # here close one incidentally on the way to checking something else.
        # Left alone those warnings print during the suite, which trains the
        # reader to skim past exactly the line that matters in production.
        # Silenced at the source instead; `assertLogs` installs its own handler
        # and re-enables propagation for its block, so the tests that assert on
        # this logger still see everything.
        self._reaper_logger = logging.getLogger("services.financial.run_reaper")
        self._was_propagating = self._reaper_logger.propagate
        self._quiet_handler = logging.NullHandler()
        self._reaper_logger.addHandler(self._quiet_handler)
        self._reaper_logger.propagate = False

    def tearDown(self):
        self._reaper_logger.removeHandler(self._quiet_handler)
        self._reaper_logger.propagate = self._was_propagating
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def insert_run(self, *, age: timedelta, status=IngestionRunStatus.running):
        """Put a run in the database at a chosen age, bypassing the service."""
        run_id = uuid.uuid4()
        session = self.SessionLocal()
        try:
            session.add(
                FinancialIngestionRun(
                    id=run_id,
                    case_id=self.case_id,
                    status=status.value,
                    code_version="test",
                    config={},
                    started_at=datetime.now(timezone.utc) - age,
                )
            )
            session.commit()
        finally:
            session.close()
        return run_id

    def read_run(self, run_id):
        session = self.SessionLocal()
        try:
            return session.get(FinancialIngestionRun, run_id)
        finally:
            session.close()

    async def sweep(
        self,
        *,
        times: int = 1,
        older_than: timedelta = timedelta(hours=1),
        every: timedelta = LONG_INTERVAL,
        behaviour=None,
    ):
        """Run the loop until it has swept ``times`` times, then cancel it.

        Returns the recorded calls.  ``behaviour`` may replace what each sweep
        does, taking the call number and the real function's keyword arguments;
        by default the real sweep runs.

        The spy executes on a worker thread, so the event that releases the test
        is set through the loop rather than directly.

        Counting sweeps is not on its own enough to know an iteration is over.
        The sweep runs through ``asyncio.to_thread``, and everything the loop
        says about it — the warning ``_report`` writes, the traceback the error
        handler logs — happens back on the event loop *after* the worker thread
        has returned.  Releasing the test when the spy returns therefore races
        the very lines these tests assert on, and cancelling the task wins that
        race often enough to fail.  So the release is in two parts: the spy says
        a sweep ran, and then the loop-side tail of that iteration is waited for
        as well.  Every iteration ends in exactly one of those two calls, which
        is what makes the second wait terminate rather than pad.
        """
        loop = asyncio.get_running_loop()
        real = run_reaper.reap_stale_runs
        real_report = run_reaper._report
        real_logger = run_reaper.logger

        calls: list[dict] = []
        enough = asyncio.Event()
        finished = asyncio.Event()
        completed = 0
        wanted: int | None = None

        def iteration_finished():
            """Called on the event loop at the end of one pass of the loop."""
            nonlocal completed
            completed += 1
            finished.set()

        def report_spy(reaped, older_than_):
            real_report(reaped, older_than_)
            iteration_finished()

        def spy(**kwargs):
            nonlocal wanted
            index = len(calls)
            calls.append({**kwargs, "thread": threading.current_thread()})
            try:
                if behaviour is not None:
                    return behaviour(index, kwargs)
                return real(**kwargs)
            finally:
                if len(calls) >= times and wanted is None:
                    # Read back on the event loop; the hand-off below is what
                    # publishes it there.
                    wanted = len(calls)
                    loop.call_soon_threadsafe(enough.set)

        run_reaper.reap_stale_runs = spy
        run_reaper._report = report_spy
        run_reaper.logger = _TailWatchingLogger(real_logger, iteration_finished)
        task = asyncio.create_task(
            reap_stale_runs_forever(
                older_than=older_than,
                every=every,
                session_factory=self.SessionLocal,
            )
        )
        try:
            await asyncio.wait_for(enough.wait(), timeout=10)
            while completed < wanted:
                finished.clear()
                await asyncio.wait_for(finished.wait(), timeout=10)
        finally:
            run_reaper.reap_stale_runs = real
            run_reaper._report = real_report
            run_reaper.logger = real_logger
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        return calls


class TheFirstSweepTests(ReaperLoopTestCase):
    """Startup is when abandoned runs are most likely to be sitting there."""

    async def test_it_sweeps_before_it_sleeps(self):
        stale = self.insert_run(age=timedelta(hours=6))

        # A thirty second interval: if the loop slept first, this would time out
        # rather than pass, which is the point of choosing it.
        await self.sweep(older_than=timedelta(hours=1), every=LONG_INTERVAL)

        stored = self.read_run(stale)
        self.assertEqual(stored.status, IngestionRunStatus.failed.value)
        self.assertIn("Abandoned", stored.error)

    async def test_a_run_inside_the_threshold_survives_the_sweep(self):
        fresh = self.insert_run(age=timedelta(minutes=5))

        await self.sweep(older_than=timedelta(hours=1))

        self.assertEqual(
            self.read_run(fresh).status, IngestionRunStatus.running.value
        )

    async def test_the_threshold_reaches_the_sweep_unchanged(self):
        calls = await self.sweep(older_than=timedelta(hours=6))

        self.assertEqual(calls[0]["older_than"], timedelta(hours=6))

    async def test_the_session_factory_reaches_the_sweep(self):
        """The loop opens no session itself; it hands the factory through.

        In production nothing is passed and the sweep falls back to a background
        session of its own, which is why this is the argument that has to travel
        rather than a session.
        """
        calls = await self.sweep()

        self.assertIs(calls[0]["session_factory"], self.SessionLocal)


class KeepingGoingTests(ReaperLoopTestCase):
    """A schedule that stops at the first bad sweep is not a schedule."""

    async def test_it_sweeps_again_after_the_interval(self):
        calls = await self.sweep(times=3, every=TIGHT_INTERVAL)

        self.assertGreaterEqual(len(calls), 3)

    async def test_a_run_that_goes_stale_later_is_caught_by_a_later_sweep(self):
        run_id = self.insert_run(age=timedelta(minutes=30))

        # Not stale against an hour, stale against a minute.  Changing the
        # threshold stands in for time passing, which the loop cannot be asked
        # to wait for.
        await self.sweep(older_than=timedelta(hours=1), every=TIGHT_INTERVAL)
        self.assertEqual(
            self.read_run(run_id).status, IngestionRunStatus.running.value
        )

        # Captured rather than left to print: the closure is a real warning and
        # the loop is right to emit it, but a test suite that prints it is
        # teaching its reader to ignore the line.
        with self.assertLogs("services.financial.run_reaper", "WARNING"):
            await self.sweep(older_than=timedelta(minutes=1), every=TIGHT_INTERVAL)
        self.assertEqual(
            self.read_run(run_id).status, IngestionRunStatus.failed.value
        )

    async def test_a_failing_sweep_does_not_end_the_loop(self):
        def explode_once(index, _kwargs):
            if index == 0:
                raise RuntimeError("database went away")
            return []

        with self.assertLogs("services.financial.run_reaper", "ERROR"):
            calls = await self.sweep(
                times=2, every=TIGHT_INTERVAL, behaviour=explode_once
            )

        self.assertGreaterEqual(len(calls), 2)

    async def test_a_failing_sweep_is_logged_with_its_traceback(self):
        def always_explode(_index, _kwargs):
            raise RuntimeError("database went away")

        with self.assertLogs("services.financial.run_reaper", "ERROR") as captured:
            await self.sweep(times=1, every=TIGHT_INTERVAL, behaviour=always_explode)

        self.assertIn("database went away", captured.output[0])
        self.assertIn("Traceback", captured.output[0])


class StoppingTests(ReaperLoopTestCase):
    """The handler that survives errors must not survive shutdown."""

    async def test_cancellation_during_the_sleep_stops_the_loop(self):
        task = asyncio.create_task(
            reap_stale_runs_forever(
                older_than=timedelta(hours=1),
                every=LONG_INTERVAL,
                session_factory=self.SessionLocal,
            )
        )
        # Let the first sweep finish so the task is parked in the sleep.
        await asyncio.sleep(0.05)
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(task.cancelled())

    async def test_cancellation_is_not_swallowed_by_the_error_handler(self):
        """The bug this guards against is a bare ``except Exception`` ordering.

        ``CancelledError`` inherits from ``BaseException`` in current Python, so
        the ordering here is right by construction — but it was
        ``Exception`` before 3.8, the loop this one is modelled on predates the
        distinction being obvious, and a later edit widening the handler would
        reintroduce a task that cannot be shut down.
        """
        started = asyncio.Event()
        loop = asyncio.get_running_loop()
        real = run_reaper.reap_stale_runs

        def slow(**_kwargs):
            loop.call_soon_threadsafe(started.set)
            return []

        run_reaper.reap_stale_runs = slow
        try:
            task = asyncio.create_task(
                reap_stale_runs_forever(
                    older_than=timedelta(hours=1),
                    every=TIGHT_INTERVAL,
                    session_factory=self.SessionLocal,
                )
            )
            await asyncio.wait_for(started.wait(), timeout=10)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            run_reaper.reap_stale_runs = real

        self.assertTrue(task.done())


class OffTheEventLoopTests(ReaperLoopTestCase):
    """The sweep blocks on a database; it must not block the application."""

    async def test_the_sweep_runs_on_a_worker_thread(self):
        calls = await self.sweep()

        self.assertIsNot(calls[0]["thread"], threading.main_thread())
        self.assertIs(threading.current_thread(), threading.main_thread())


class ReportingTests(ReaperLoopTestCase):
    """A sweep that finds nothing every few minutes must not fill the log."""

    async def test_a_sweep_that_closes_nothing_says_nothing(self):
        self.insert_run(age=timedelta(minutes=1))

        with self.assertNoLogs("services.financial.run_reaper"):
            await self.sweep(older_than=timedelta(hours=1))

    async def test_a_sweep_that_closes_a_run_names_it(self):
        stale = self.insert_run(age=timedelta(hours=6))

        with self.assertLogs("services.financial.run_reaper", "WARNING") as captured:
            await self.sweep(older_than=timedelta(hours=1))

        self.assertIn(str(stale), captured.output[0])

    async def test_the_message_gives_the_threshold_that_was_applied(self):
        """Without it the log says a run was abandoned but not by what measure.

        Which is the first thing anyone reads the line to find out, because it
        is what decides whether the run was really abandoned or the threshold is
        set too tight.
        """
        self.insert_run(age=timedelta(hours=6))

        with self.assertLogs("services.financial.run_reaper", "WARNING") as captured:
            await self.sweep(older_than=timedelta(hours=1))

        self.assertIn("1:00:00", captured.output[0])


class RefusedArgumentsTests(unittest.IsolatedAsyncioTestCase):
    """Neither number has a default, and neither may be nonsense.

    No database here: these are refused before the first sweep, which is the
    property being asserted.
    """

    async def test_a_zero_threshold_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            await reap_stale_runs_forever(
                older_than=timedelta(0), every=LONG_INTERVAL
            )

        self.assertIn("older_than", str(caught.exception))

    async def test_a_negative_threshold_is_refused(self):
        with self.assertRaises(ValueError):
            await reap_stale_runs_forever(
                older_than=timedelta(hours=-1), every=LONG_INTERVAL
            )

    async def test_a_zero_interval_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            await reap_stale_runs_forever(
                older_than=timedelta(hours=1), every=timedelta(0)
            )

        self.assertIn("every", str(caught.exception))

    async def test_a_bad_threshold_is_refused_before_any_sweep_happens(self):
        real = run_reaper.reap_stale_runs
        calls = []

        def spy(**kwargs):
            calls.append(kwargs)
            return []

        run_reaper.reap_stale_runs = spy
        try:
            with self.assertRaises(ValueError):
                await reap_stale_runs_forever(
                    older_than=timedelta(0), every=LONG_INTERVAL
                )
        finally:
            run_reaper.reap_stale_runs = real

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
