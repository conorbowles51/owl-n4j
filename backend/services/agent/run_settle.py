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

    A beat that fails is logged and retried on the next tick; the run itself is never touched by a beat failure.
    """

    def __init__(self, run_id):
        self.run_id = run_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._beat, name=f'agent-run-heartbeat-{run_id}', daemon=True)

    def start(self) -> 'RunHeartbeat':
        self._beat_once()
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            self._beat_once()

    def _beat_once(self) -> None:
        from postgres.models.agent import AgentRun
        from postgres.session import get_background_session
        try:
            with get_background_session() as session:
                session.execute(update(AgentRun).where(AgentRun.id == self.run_id)
                                .values(heartbeat_at=_now()))
                session.commit()
        except Exception as exc:  # noqa: BLE001 - the run goes on; the next tick tries again
            log.warning('Agent run %s heartbeat failed: %s', self.run_id, exc)


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
