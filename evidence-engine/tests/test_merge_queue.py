"""A person's entity merge runs on its own worker, never behind document ingests (23 Nov: merge d44bb517 waited 17+ min
behind 4 batches that held every general slot)."""
import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from arq.constants import default_queue_name, in_progress_key_prefix, job_key_prefix
from arq.jobs import serialize_job

from app.services.processing_queues import MERGE_QUEUE


def test_merge_route_enqueues_on_the_merge_queue():
    from app.api.routes.merge import MergeEntitiesRequest, merge_entities

    calls = []

    class FakePool:
        async def enqueue_job(self, *args, **kwargs):
            calls.append((args, kwargs))

    class FakeDb:
        def add(self, job):
            pass

        async def commit(self):
            pass

        async def refresh(self, job):
            pass

    body = MergeEntitiesRequest(entities=[{"key": "a", "name": "A"}, {"key": "b", "name": "B"}])
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=FakePool())))
    asyncio.run(merge_entities(case_id=str(uuid.uuid4()), body=body, request=request, db=FakeDb()))
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "process_merge"
    assert kwargs.get("_queue_name") == MERGE_QUEUE != default_queue_name


def test_merge_worker_settings():
    from app.worker import MergeWorkerSettings, WorkerSettings
    s = MergeWorkerSettings
    assert s.queue_name == MERGE_QUEUE
    assert [f.__name__ for f in s.functions] == ["process_merge"]
    assert s.max_jobs >= 2 and s.job_timeout >= 836  # longest merge measured (9 Nov)
    assert not getattr(s, "cron_jobs", None)  # the general worker owns the janitors
    # merges already waiting on the general queue at release still have a worker there
    assert "process_merge" in [f.__name__ for f in WorkerSettings.functions]


def test_compose_runs_the_merge_worker():
    text = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    block = text.split("  evidence-merge-worker:\n", 1)[1].split("\n\n", 1)[0]
    assert "command: arq app.worker.MergeWorkerSettings" in block and "<<: *evidence-worker" in block


class FakeRedis:
    def __init__(self):
        self.z, self.kv = {}, {}

    async def zrange(self, key, start, end):
        return [m.encode() for m, _ in sorted(self.z.get(key, {}).items(), key=lambda kv: kv[1])]

    async def get(self, key):
        return self.kv.get(key)

    async def eval(self, script, n, old, new, running, payload, identity):
        if running in self.kv or payload not in self.kv or identity not in self.z.get(old, {}):
            return 0
        self.z.setdefault(new, {})[identity] = self.z[old].pop(identity)
        return 1


def test_worker_start_moves_waiting_merges_only():
    from app.services.merge_queue_recovery import move_waiting_merges
    r = FakeRedis()

    def queue(identity, function, score, running=False):
        r.z.setdefault(default_queue_name, {})[identity] = score
        r.kv[job_key_prefix + identity] = serialize_job(function, (identity, "case"), {}, 1, score)
        if running:
            r.kv[in_progress_key_prefix + identity] = b"1"

    queue("merge-waiting", "process_merge", 100)
    queue("merge-running", "process_merge", 101, running=True)
    queue("batch-waiting", "process_batch", 99)
    r.z[default_queue_name]["cron:reap_stale_jobs:1"] = 98  # payload gone: never moved
    assert asyncio.run(move_waiting_merges({"redis": r})) == 1
    assert r.z[MERGE_QUEUE] == {"merge-waiting": 100}  # same id and queue time
    assert set(r.z[default_queue_name]) == {"merge-running", "batch-waiting", "cron:reap_stale_jobs:1"}
