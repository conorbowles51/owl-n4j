from types import SimpleNamespace

import pytest

from app.services import batch_dispatch
from app.services.pipeline_run_state import transition_batch_dispatch


class FakeDb:
    def __init__(self, job) -> None:
        self.job = job
        self.commits: list[str] = []
        self.refreshes: list[object] = []

    async def commit(self) -> None:
        self.commits.append(self.job.pipeline_state["batch_dispatch"]["state"])

    async def refresh(self, job) -> None:
        self.refreshes.append(job)


class FakePool:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple] = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(job_id=kwargs.get("_job_id"))


def dispatch_job():
    state = transition_batch_dispatch(
        {},
        dispatch_state="ready",
        batch_id="batch-1",
        case_id="case-1",
    )
    return SimpleNamespace(id="job-1", pipeline_state=state)


@pytest.mark.asyncio
async def test_dispatch_uses_stable_queue_id_and_marks_outbox_dispatched() -> None:
    job = dispatch_job()
    db = FakeDb(job)
    pool = FakePool()

    dispatched = await batch_dispatch.dispatch_ingestion_batch(job, db, pool)

    assert dispatched is True
    assert db.commits == ["dispatching", "dispatched"]
    assert db.refreshes == [job]
    assert pool.calls == [
        (
            ("process_batch", "batch-1", "case-1"),
            {"_job_id": "evidence-batch:batch-1"},
        )
    ]


@pytest.mark.asyncio
async def test_dispatch_failure_is_durable_and_can_be_retried() -> None:
    job = dispatch_job()
    db = FakeDb(job)
    pool = FakePool(RuntimeError("Redis unavailable"))

    dispatched = await batch_dispatch.dispatch_ingestion_batch(job, db, pool)

    assert dispatched is False
    assert db.commits == ["dispatching", "retry"]
    assert db.refreshes == [job]
    dispatch = job.pipeline_state["batch_dispatch"]
    assert dispatch["attempt_count"] == 1
    assert dispatch["last_error"] == "Redis unavailable"

    pool.error = None
    dispatched = await batch_dispatch.dispatch_ingestion_batch(job, db, pool)

    assert dispatched is True
    assert pool.calls[-1][1]["_job_id"] == "evidence-batch:batch-1"
    assert job.pipeline_state["batch_dispatch"]["state"] == "dispatched"
