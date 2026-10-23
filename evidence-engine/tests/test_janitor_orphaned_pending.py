import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from arq.constants import in_progress_key_prefix, job_key_prefix

from app.jobs import janitor
from app.models.job import JobStatus

BATCH = uuid.uuid4()
DISPATCHED = {"state": "dispatched", "queue_job_id": "evidence-resume:batch:1"}


def job(**values):
    base = dict(id=uuid.uuid4(), case_id="case-1", batch_id=BATCH, status=JobStatus.PENDING, paused=False,
                pipeline_state={}, error_message=None, progress=0.2,
                updated_at=datetime.utcnow() - timedelta(days=9))
    return SimpleNamespace(**{**base, **values})


class FakePool:
    def __init__(self, keys=()):
        self.keys = set(keys)
        self.calls = 0

    async def exists(self, *names):
        self.calls += 1
        return sum(name in self.keys for name in names)


class FakeDb:
    def __init__(self, pending, owners):
        self.results = [pending, owners]
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement):
        rows = self.results.pop(0)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    async def commit(self):
        self.commits += 1


@pytest.fixture
def published(monkeypatch):
    sent = []

    async def publish(job_id, payload):
        sent.append((job_id, payload))

    monkeypatch.setattr(janitor, "publish_progress", publish)
    return sent


def run(monkeypatch, pending, owners, pool):
    db = FakeDb(pending, owners)
    monkeypatch.setattr(janitor, "async_session", lambda: db)
    return db


def test_queue_identity_uses_own_or_batch_owner_dispatch_and_only_when_dispatched():
    owner = {("case-1", BATCH): DISPATCHED}
    assert janitor.queue_identity(job(), owner) == DISPATCHED["queue_job_id"]
    assert janitor.queue_identity(job(pipeline_state={"batch_dispatch": DISPATCHED}), {}) == DISPATCHED["queue_job_id"]
    for state in ("ready", "retry", "dispatching"):
        assert janitor.queue_identity(job(), {("case-1", BATCH): {**DISPATCHED, "state": state}}) is None
    assert janitor.queue_identity(job(), {}) is None
    assert janitor.queue_identity(job(batch_id=None), owner) is None
    assert janitor.queue_identity(job(case_id="case-2"), owner) is None


@pytest.mark.asyncio
async def test_a_pending_member_whose_batch_job_left_the_queue_is_failed(monkeypatch, published):
    orphan = job()
    owner = job(status=JobStatus.FAILED, pipeline_state={"batch_dispatch": DISPATCHED})
    db = run(monkeypatch, [orphan], [owner], None)
    assert await janitor.reap_orphaned_pending({"redis": FakePool()}) == 1
    assert orphan.status == JobStatus.FAILED and "Safe to retry" in orphan.error_message
    assert db.commits == 1 and published[0][0] == str(orphan.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", [job_key_prefix, in_progress_key_prefix])
async def test_pending_work_still_queued_or_running_is_left_alone(monkeypatch, published, key):
    members = [job(), job()]
    owner = job(pipeline_state={"batch_dispatch": DISPATCHED})
    run(monkeypatch, members, [owner], None)
    pool = FakePool({key + DISPATCHED["queue_job_id"]})
    assert await janitor.reap_orphaned_pending({"redis": pool}) == 0
    assert all(member.status == JobStatus.PENDING for member in members)
    assert pool.calls == 1  # one queue check per batch, not per member
    assert published == []


@pytest.mark.asyncio
async def test_undispatched_or_unknown_pending_work_is_never_guessed_at(monkeypatch, published):
    waiting = job()
    owner = job(pipeline_state={"batch_dispatch": {**DISPATCHED, "state": "retry"}})
    loose = job(batch_id=None)
    run(monkeypatch, [waiting, loose], [owner], None)
    assert await janitor.reap_orphaned_pending({"redis": FakePool()}) == 0
    assert waiting.status == loose.status == JobStatus.PENDING


@pytest.mark.asyncio
async def test_no_redis_pool_reaps_nothing():
    assert await janitor.reap_orphaned_pending({}) == 0
