"""A retained upload must reconnect to one phone job after a lost response."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import cellebrite as api


class Db:
    def __init__(self): self.rows = {}
    async def get(self, model, identity): return self.rows.get(identity)
    def add(self, job): self.rows[job.id] = job
    async def commit(self): pass
    async def refresh(self, job): pass


@pytest.mark.asyncio
async def test_phone_pause_acknowledgement_resumes_the_phone_worker_once():
    from unittest.mock import AsyncMock
    from app.api.routes.jobs import control_job
    from app.models.job import JobStatus
    identity = uuid4()
    job = SimpleNamespace(id=identity, case_id='case', batch_id=None, job_type='cellebrite_ingestion',
        status=JobStatus.WRITING_GRAPH, pause_requested=False, paused=False, resumable=True,
        resume_generation=0, pipeline_state={}, error_message=None)
    db = Db(); db.rows[identity] = job
    db.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [job])))
    pool = Pool(); pool.fail = False
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool)))
    assert (await control_job(identity, 'pause', request, 'case', db))['state'] == 'pausing'
    with pytest.raises(HTTPException) as error:
        await control_job(identity, 'resume', request, 'case', db)
    assert error.value.status_code == 409 and not pool.calls
    job.paused = True; job.status = JobStatus.PENDING
    assert (await control_job(identity, 'resume', request, 'case', db))['state'] == 'queued'
    assert not job.paused and not job.pause_requested and job.resume_generation == 1
    assert pool.calls[0][0] == ('process_cellebrite', str(identity), 'case')
    assert (await control_job(identity, 'resume', request, 'case', db))['state'] == 'running'
    assert len(pool.calls) == 1
    with pytest.raises(HTTPException) as error:
        await control_job(identity, 'resume', request, 'other-case', db)
    assert error.value.status_code == 404


class Pool:
    def __init__(self): self.calls = []; self.fail = True
    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail: raise OSError('Synthetic lost Redis acknowledgement')
        return None  # ARQ duplicate acknowledgement is also successful.


@pytest.mark.asyncio
async def test_same_request_recovers_queue_without_creating_another_job(tmp_path, monkeypatch):
    monkeypatch.setattr(api, '_repo_data_root', lambda: tmp_path)
    (tmp_path / 'case' / 'Phone').mkdir(parents=True)
    identity = uuid4()
    body = api.CellebriteJobRequest(request_id=identity, folder_path='Phone', force=True)
    db, pool = Db(), Pool()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool)))
    first = await api.create_cellebrite_job('case', body, request, db)
    assert first.pipeline_state['batch_dispatch']['state'] == 'retry'
    pool.fail = False
    retry = await api.create_cellebrite_job('case', body, request, db)
    assert retry is first and len(db.rows) == 1
    assert retry.pipeline_state['batch_dispatch']['state'] == 'dispatched'
    assert pool.calls[0] == pool.calls[1]
    assert pool.calls[0][0] == ('process_cellebrite', str(identity), 'case')
    assert pool.calls[0][1]['_job_id'] == f'cellebrite:{identity}'
    await api.create_cellebrite_job('case', body, request, db)
    assert len(pool.calls) == 2
    with pytest.raises(HTTPException) as error:
        await api.create_cellebrite_job('case', body.model_copy(update={'force': False}), request, db)
    assert error.value.status_code == 409
