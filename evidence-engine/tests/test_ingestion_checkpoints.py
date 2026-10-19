"""Pause, restart and policy changes across persistent work-unit boundaries."""
import json
from uuid import uuid4

import pytest
from arq import Retry

from app.services import ingestion_checkpoints as checkpoints
from app.services import ai_model_policy


async def never_pause():
    return False


@pytest.fixture
def root(tmp_path,monkeypatch):
    monkeypatch.setattr(checkpoints.settings,'storage_path',str(tmp_path))
    return tmp_path


async def test_pause_finishes_and_saves_current_unit_then_resume_skips_completed_work(root):
    paused=False; calls=[]; scope=str(uuid4());case=str(uuid4())
    async def requested():return paused
    @checkpoints.checkpointed('synthetic/extract:v1')
    async def unit(number):
        nonlocal paused
        calls.append(number)
        if number==2:paused=True
        return {'number':number,'value':f'result-{number}'}
    with pytest.raises(checkpoints.IngestionPaused):
        async with checkpoints.checkpoint_scope(scope,case,requested):
            for number in (1,2,3):await unit(number)
    assert calls==[1,2]
    paused=False
    async with checkpoints.checkpoint_scope(scope,case,requested):
        values=[await unit(number) for number in (1,2,3)]
    assert calls==[1,2,3] and [v['number'] for v in values]==[1,2,3]
    assert len(list(root.rglob('*.json')))==3


async def test_interrupted_unit_retries_without_repeating_previous_units(root):
    calls=[]; scope=str(uuid4());case=str(uuid4()); fail=True
    @checkpoints.checkpointed('synthetic/write:v1')
    async def unit(number):
        calls.append(number)
        if number==2 and fail:raise TimeoutError('Synthetic network interruption')
        return number
    with pytest.raises(TimeoutError):
        async with checkpoints.checkpoint_scope(scope,case,never_pause):
            for number in (1,2,3):await unit(number)
    fail=False
    async with checkpoints.checkpoint_scope(scope,case,never_pause):
        assert [await unit(n) for n in (1,2,3)]==[1,2,3]
    assert calls==[1,2,2,3]


async def test_queued_pause_calls_no_provider_and_releases_run_lock(root):
    scope=str(uuid4());case=str(uuid4());entered=False
    async def yes():return True
    with pytest.raises(checkpoints.IngestionPaused):
        async with checkpoints.checkpoint_scope(scope,case,yes):entered=True
    assert not entered
    async with checkpoints.checkpoint_scope(scope,case,never_pause):pass


async def test_same_scope_cannot_publish_concurrently_but_another_case_can_run(root):
    scope=str(uuid4());case=str(uuid4())
    async with checkpoints.checkpoint_scope(scope,case,never_pause):
        with pytest.raises(Retry):
            async with checkpoints.checkpoint_scope(scope,case,never_pause):pass
        async with checkpoints.checkpoint_scope(scope,str(uuid4()),never_pause):pass


async def test_outer_stage_recomputes_when_model_policy_changes(root,monkeypatch):
    scope=str(uuid4());case=str(uuid4());calls=[];policy={'model':'one'}
    monkeypatch.setattr(ai_model_policy,'get_ai_runtime_snapshot',lambda:policy.copy())
    @checkpoints.checkpointed('synthetic/outer-stage:v1')
    async def unit(number=1):
        calls.append(policy['model'])
        return policy['model']
    async with checkpoints.checkpoint_scope(scope,case,never_pause):
        assert await unit()=='one'
        assert await unit(1)=='one'
        policy['model']='two'
        assert await unit()=='two'
    assert calls==['one','two']


async def test_corrupt_checkpoint_is_visible_and_never_silently_repeats_paid_work(root):
    scope=str(uuid4());case=str(uuid4());calls=[]
    @checkpoints.checkpointed('synthetic/provider:v1')
    async def unit():calls.append(1);return {'result':1}
    async with checkpoints.checkpoint_scope(scope,case,never_pause):await unit()
    next(root.rglob('*.json')).write_text('{interrupted')
    with pytest.raises(json.JSONDecodeError):
        async with checkpoints.checkpoint_scope(scope,case,never_pause):await unit()
    assert calls==[1]
