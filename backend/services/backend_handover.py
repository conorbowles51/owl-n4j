"""What a backend needs to know when a release starts the next one before the old one stops.

A release (deploy/backend_supervisor.py, switch deploy/backend-restart.conf) can run two backends side by side on the
one API port for a few seconds. Two things follow.

Every background loop must do its work once however many backends run: ``BACKGROUND_LOOPS`` states each loop's owner,
and a loop started in main.py's lifespan without an entry fails tests/test_two_backends.py.

  host-lock   a file lock on this box: one process does the work, the others retry and take over when it ends.
  row-claim   every worker runs the loop, and a lease, row lock or advisory lock in PostgreSQL gives each unit of
              work to one of them.
  per-process the loop looks after this process's own memory or timing; each process must run its own.

Work a new backend learns about only at its start would miss what the old one began after that moment.
``after_old_backend_stopped`` runs a step again once the old backend is gone.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)

BACKGROUND_LOOPS = {
    'upload-chunk-cleanup': 'per-process',  # this process's chunk cache
    'platform-update-poll': 'per-process',  # this process's cached status; reads only
    'job-status-subscriber': 'row-claim',  # the file's row lock; a merge's advisory lock (_merge_claim)
    'financial-folder-batches': 'row-claim',  # batch lease; its rounds and page-image rounds: host-lock children
    'financial-reviewed-identities': 'row-claim',  # one advisory lock per case (identity_graph._case_claim)
    'address-lookups': 'host-lock',  # address_lookup._take_host_lock
    'phone-interpretation': 'host-lock',  # the sweep worker's lock; derive, exports and analysis run inside it
    'financial-deployment-recovery': 'row-claim',  # the case row, skip locked, and the item's status (recover_one)
    'request-speed-loop-lag': 'per-process',  # how late this process's event loop runs
    'financial-view-warmup': 'host-lock',  # view_warmup._take_lock
    'financial-view-refresh': 'host-lock',  # view_refresh.LOCK
    'financial-case-files-warmup': 'per-process',  # this process's evidence-file copies
    'deleted-items-purge': 'row-claim',  # one advisory lock across the host (casebin_purge)
    'backend-handover-recovery': 'per-process',  # this process's subscriptions
    'meaning-search-backfill-resume': 'row-claim',  # the backfill's session advisory lock (meaning_search._backfill_lock)
    'agent-run-settle': 'row-claim',  # FOR UPDATE SKIP LOCKED on the orphaned run rows (run_settle)
}

# The supervisor writes this file when it runs the backend: deploy/backend-handover.sh passes the same path.
STATE_FILE_NAME = 'backend-supervisor.json'
LOOK_SECONDS = 5
LOOK_LIMIT_SECONDS = 15 * 60


def state_file():
    return Path(__file__).resolve().parents[2] / 'deploy' / 'logs' / STATE_FILE_NAME


def process_identity():
    """For /health: which backend answered. The supervisor recognises its new workers by their parent."""
    return dict(pid=os.getpid(), parent=os.getppid(), one_owner=_one_owner())


def _one_owner():
    """True when the host locks can be taken here. Without a lock location the rounds run in every worker
    (batch_rounds), so a second backend would run them again: the supervisor refuses such a backend."""
    from services.financial import vision_rounds
    return vision_rounds._lock_usable()


def _old_backend_stopped_since(started, path):
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    stopped = ((state.get('handover') or {}).get('old_stopped_at')) or 0
    return stopped >= started


async def after_old_backend_stopped(step, *, path=None, look_seconds=LOOK_SECONDS, limit_seconds=LOOK_LIMIT_SECONDS):
    """Await ``step`` once, when the supervisor records that the old backend stopped after this process started.
    A plain restart records nothing, and there the start itself came after the old backend, so this ends at the
    limit having done nothing."""
    path = path or state_file()
    started = time.time()
    deadline = time.monotonic() + limit_seconds
    while time.monotonic() < deadline:
        if _old_backend_stopped_since(started, path):
            await step()
            return True
        await asyncio.sleep(look_seconds)
    return False
