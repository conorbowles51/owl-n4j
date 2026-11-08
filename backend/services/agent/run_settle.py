"""An agent run killed by a restart is settled, never left ``running`` for ever.

A run executes inside its web request: when a release restarts the backend, the worker dies and the ``agent_runs``
row used to stay ``running`` with no ``completed_at``, while its thread kept a question with no answer (measured
8 Nov 2026: 10 such rows on live, 2 to 33 days old). ``services/agent/disconfirm.py`` ``_settle`` already settles
its own sweeps; this is the same pattern for the general run path.

Liveness is the heartbeat, not age: every run beats ``agent_runs.heartbeat_at`` every ``HEARTBEAT_SECONDS`` while
its worker lives (``RunHeartbeat``), so the sweep touches only runs whose beat has stopped. A run from before the
heartbeat column (``heartbeat_at`` empty) is keyed on ``started_at``: a living run would have beaten within
``HEARTBEAT_SECONDS``, so an empty beat long past that has no living worker.

The sweep (``settle_orphaned_runs``) marks each orphaned run ``interrupted`` — never ``completed``, and never left
``running`` — states the cut on the run record (``error``), and puts a plain line in the thread so the person who
asked sees why there is no answer. It runs once at startup and then every ``SWEEP_SECONDS`` in every worker
(``settle_forever``); rows are taken with FOR UPDATE SKIP LOCKED so two workers never settle, or write the thread
line for, the same run twice.

Decisions (lx-agentruns, 8 Nov 2026):
- D-r1 The sweep keys on the heartbeat (ownership), not age alone: a slow run that still beats is never touched.
  Reverse if a run's beat thread is shown to outlive its worker.
- D-r2 The thread line is stored as an assistant message with no model named: it renders where the person waits for
  the answer. Reverse if threads gain a system-line kind.
- D-r3 A periodic sweep in every worker, not only at launch: a release overlaps old and new backends
  (services.backend_handover), so runs cut when the old one stops die after the new one's startup pass.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 10
STALE_AFTER = 90          # as disconfirm.STALE_AFTER: a beat older than this has no living worker
SWEEP_SECONDS = 60

INTERRUPTED = 'interrupted'
THREAD_LINE = ('This run was interrupted by a restart before it could answer. Nothing already saved is lost; '
               'ask the question again.')
RECORD_WORDS = ('The service restarted while this run was working, so it never finished. '
                'The tool calls stored before the cut are its record.')


def _now():
    return datetime.now(timezone.utc)


class RunHeartbeat:
    """Beats ``agent_runs.heartbeat_at`` on its own connection while the run's worker lives.

    It also carries the run's live progress (services.agent.live_runs): a changed progress line is written at once
    to ``extra_metadata['progress']``, so a person who leaves and comes back, or reads from the other worker, sees
    the same step. Every ``POLL_SECONDS`` it reads the run's status: a Stop written by the other web worker
    (``cancelled``) is passed to this worker's run (services.agent.cancellation), which stops at its next check.

    A beat that fails is logged and retried on the next tick; the run itself is never touched by a beat failure.
    """

    POLL_SECONDS = 2

    def __init__(self, run_id):
        self.run_id = run_id
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._progress = None
        self._progress_dirty = False
        self._last_beat = 0.0
        self._thread = threading.Thread(target=self._beat, name=f'agent-run-heartbeat-{run_id}', daemon=True)

    def start(self) -> 'RunHeartbeat':
        self._beat_once()
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def note_progress(self, progress: dict) -> None:
        with self._lock:
            self._progress = dict(progress)
            self._progress_dirty = True
        self._wake.set()

    def _beat(self) -> None:
        import time
        while not self._stop.is_set():
            self._wake.wait(self.POLL_SECONDS)
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                dirty = self._progress_dirty
            if dirty or time.monotonic() - self._last_beat >= HEARTBEAT_SECONDS:
                self._beat_once()
            self._check_stopped_elsewhere()

    def _beat_once(self) -> None:
        import time
        from postgres.models.agent import AgentRun
        from postgres.session import get_background_session
        with self._lock:
            progress = self._progress if self._progress_dirty else None
            self._progress_dirty = False
        try:
            with get_background_session() as session:
                session.execute(update(AgentRun).where(AgentRun.id == self.run_id)
                                .values(heartbeat_at=_now()))
                if progress is not None:
                    _write_progress(session, self.run_id, progress)
                session.commit()
            self._last_beat = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - the run goes on; the next tick tries again
            log.warning('Agent run %s heartbeat failed: %s', self.run_id, exc)
            if progress is not None:
                with self._lock:
                    if not self._progress_dirty:
                        self._progress, self._progress_dirty = progress, True

    def _check_stopped_elsewhere(self) -> None:
        from postgres.models.agent import AgentRun
        from postgres.session import get_background_session
        from services.agent.cancellation import request_cancel
        try:
            with get_background_session() as session:
                status = session.execute(select(AgentRun.status).where(AgentRun.id == self.run_id)).scalar()
            if status is not None and status != 'running':
                request_cancel(str(self.run_id))
        except Exception as exc:  # noqa: BLE001
            log.warning('Agent run %s status check failed: %s', self.run_id, exc)


def _write_progress(session, run_id, progress: dict) -> None:
    """``extra_metadata['progress'] = progress`` without touching the run's other metadata keys (on PostgreSQL one
    ``jsonb_set``, so a key the run writes at the same moment is never lost)."""
    import json
    from sqlalchemy import text
    from postgres.models.agent import AgentRun
    from services.agent.json_utils import to_jsonable
    payload = to_jsonable(progress)
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text("UPDATE agent_runs SET extra_metadata = jsonb_set(COALESCE(extra_metadata, '{}'::jsonb), "
                             "'{progress}', CAST(:p AS jsonb)) WHERE id = :id"),
                        {'p': json.dumps(payload), 'id': str(run_id)})
        return
    run = session.get(AgentRun, run_id)
    if run is not None:
        run.extra_metadata = {**(run.extra_metadata or {}), 'progress': payload}


def settle_orphaned_runs(session) -> list[dict]:
    """Every ``running`` run with no living worker: marked ``interrupted``, the cut on the record, a line in the
    thread. New and beating runs are untouched. Returns what was settled, for the log."""
    from postgres.models.agent import AgentRun
    from services.agent import storage
    cutoff = _now() - timedelta(seconds=STALE_AFTER)
    query = (select(AgentRun)
             .where(AgentRun.status == 'running',
                    func.coalesce(AgentRun.heartbeat_at, AgentRun.started_at) < cutoff)
             .with_for_update(skip_locked=True))
    settled = []
    for run in session.scalars(query).all():
        if run.status != 'running':  # re-read under the lock
            continue
        run.status = INTERRUPTED
        run.error = RECORD_WORDS
        run.completed_at = _now()
        if run.record_summary is None:
            run.record_summary = {'basis': RECORD_WORDS}
        thread = run.thread
        if thread is not None:
            storage.append_message(session, thread=thread, role='assistant', content=THREAD_LINE, run=run)
        settled.append(dict(run_id=str(run.id), thread_id=str(run.thread_id),
                            started_at=run.started_at.isoformat() if run.started_at else None))
    session.commit()
    if settled:
        log.warning('Settled %d orphaned agent run(s) as interrupted: %s', len(settled),
                    ', '.join(r['run_id'] for r in settled))
    return settled


def _settle_once() -> None:
    from postgres.session import get_background_session
    with get_background_session() as session:
        settle_orphaned_runs(session)


async def settle_forever() -> None:
    """Startup pass, then one pass per ``SWEEP_SECONDS``. A failed pass is logged; the loop goes on."""
    while True:
        try:
            await asyncio.to_thread(_settle_once)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the next pass tries again
            log.warning('Agent run settle pass failed: %s', exc)
        await asyncio.sleep(SWEEP_SECONDS)
