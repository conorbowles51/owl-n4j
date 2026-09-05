"""The schedule the run safety net runs on.

:func:`services.financial.runs.reap_stale_runs` decides which runs have been
abandoned and writes that down.  It had no caller.  A safety net nothing calls
is not a safety net, and the gap it left was specific: the one failure mode the
run machinery cannot cover from inside — a process killed outright, with no
handler left to write a terminal status — is exactly the one that produced rows
saying ``running`` with nothing on the way to correct them.  This module is the
caller.

It holds the schedule and nothing else.  The judgement of what counts as
abandoned stays in ``runs``, and neither the threshold nor the interval is
invented here: both are passed in, so that the deployment knob lives in
``config`` with every other deployment knob and this package keeps its property
of importing no configuration at all.  That property is what lets the financial
package be tested without an environment, and it is worth more than the
convenience of a default.

Two details of the loop are deliberate rather than incidental.

*The first sweep happens at startup, before the first sleep.*  A restart is
precisely the event that abandons runs, so the moment the application comes back
up is the moment there is most likely something to close.  Sleeping first would
mean the rows stay wrong for a full interval after the one event most likely to
have created them.

*A failed sweep does not stop the schedule.*  The loop catches and logs, then
carries on.  The alternative — the shape used by ``_cleanup_stale_chunks`` in
``routers.snapshots``, which has no handler at all — silently ends the task on
the first transient database error and disables the safety net for the lifetime
of the process, with nothing said.  ``asyncio.CancelledError`` is re-raised
rather than swallowed, because that one is shutdown asking the loop to stop and
catching it would hang the shutdown.

The reaper is global rather than case-scoped: it selects every ``running`` row
regardless of case.  That is the reason this is a background loop and not an
endpoint.  Behind a case-scoped route, a caller with access to one case would be
terminating runs in cases they cannot see.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from services.financial.runs import SessionFactory, reap_stale_runs

logger = logging.getLogger(__name__)


async def reap_stale_runs_forever(
    *,
    older_than: timedelta,
    every: timedelta,
    session_factory: SessionFactory | None = None,
) -> None:
    """Sweep for abandoned runs on a fixed interval until cancelled.

    ``older_than`` is how long a run may sit in ``running`` before it is taken
    to have been abandoned; ``every`` is the gap between sweeps.  Both are
    required, because a wrong staleness threshold closes runs that are still
    working and a silent default is how a wrong one goes unnoticed.

    Never returns normally.  Cancellation is the only exit, and it propagates.
    """
    if older_than <= timedelta(0):
        raise ValueError(
            f"older_than must be a positive age, not {older_than}; a "
            "non-positive threshold would reap every run the moment it started"
        )
    if every <= timedelta(0):
        raise ValueError(
            f"every must be a positive interval, not {every}; a non-positive "
            "one would spin without yielding"
        )

    interval = every.total_seconds()

    while True:
        try:
            reaped = await asyncio.to_thread(
                reap_stale_runs,
                older_than=older_than,
                session_factory=session_factory,
            )
            _report(reaped, older_than)
        except asyncio.CancelledError:
            # Shutdown, not a fault.  Swallowing this would keep the loop alive
            # through cancellation and hang the application on the way down.
            raise
        except Exception:
            # One bad sweep must not end the schedule.  The next one is a few
            # minutes away and will find the same rows still waiting.
            logger.exception("Sweep for abandoned financial ingestion runs failed")

        await asyncio.sleep(interval)


def _report(reaped: list[UUID], older_than: timedelta) -> None:
    """Say what was closed, and stay quiet when nothing was.

    A sweep that finds nothing is the normal case and logging it every few
    minutes would bury the sweeps that found something.
    """
    if not reaped:
        return
    logger.warning(
        "Closed %d abandoned financial ingestion run(s) as failed after %s: %s",
        len(reaped),
        older_than,
        ", ".join(str(run_id) for run_id in reaped),
    )
