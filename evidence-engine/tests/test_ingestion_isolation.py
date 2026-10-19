"""The real worker entry points must keep statement preparation out of AI work."""
from contextlib import asynccontextmanager
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app import worker
from app.models.job import JobStatus
from app.pipeline import batch_orchestrator, prepare_pdf_review
from app.services import graph_identity, ingestion_control


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [True, False])
async def test_pdf_worker_runs_when_graph_is_unavailable(monkeypatch, batch):
    job = SimpleNamespace(id=uuid4(), case_id=str(uuid4()), job_type='pdf_review',
                          status=JobStatus.PENDING)
    db = SimpleNamespace(
        get=AsyncMock(return_value=job), commit=AsyncMock(),
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [job]))))

    @asynccontextmanager
    async def session():
        yield db

    @asynccontextmanager
    async def scope(*args):
        yield

    monkeypatch.setattr(worker, 'async_session', session)
    monkeypatch.setattr(ingestion_control, 'async_session', session)
    monkeypatch.setattr(ingestion_control, 'checkpoint_scope', scope)
    graph = AsyncMock(side_effect=RuntimeError('Graph unavailable'))
    monkeypatch.setattr(graph_identity, 'ensure_identity_indexes', graph)
    policy, ai, prepare = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(batch_orchestrator, 'load_ai_model_policy', policy)
    monkeypatch.setattr(worker, 'run_pipeline', ai)
    monkeypatch.setattr(prepare_pdf_review, 'prepare_pdf_review', prepare)

    if batch:
        await worker.process_batch({}, str(uuid4()), job.case_id)
    else:
        await worker.process_file({}, str(job.id))
    prepare.assert_awaited_once()
    graph.assert_not_awaited()
    policy.assert_not_awaited()
    ai.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [RuntimeError('Synthetic read failure'), asyncio.CancelledError()])
async def test_single_pdf_failure_updates_only_its_own_job(monkeypatch, error):
    job = SimpleNamespace(id=uuid4(), case_id=str(uuid4()), job_type='pdf_review', progress=.2)
    @asynccontextmanager
    async def session():
        yield SimpleNamespace(get=AsyncMock(return_value=job))
    async def controlled(scope_id, case_id, operation, **kwargs):
        assert scope_id == str(job.id) and case_id == job.case_id
        await operation()
    monkeypatch.setattr(worker, 'async_session', session)
    monkeypatch.setattr(worker, 'run_controlled', controlled)
    monkeypatch.setattr(prepare_pdf_review, 'prepare_pdf_review', AsyncMock(side_effect=error))
    update = AsyncMock()
    monkeypatch.setattr(batch_orchestrator, '_update_job_status', update)
    with pytest.raises(type(error)):
        await worker.process_file({}, str(job.id))
    update.assert_awaited_once()
    assert update.call_args.args[:3] == (job.id, JobStatus.FAILED, .2)
