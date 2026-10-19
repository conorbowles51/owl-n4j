"""Real Redis checks, opt-in against the isolated local test Redis only."""
import asyncio
import os
import multiprocessing
from uuid import uuid4
import pytest
from arq.connections import create_pool, RedisSettings
from arq.worker import Worker, func
from arq.constants import in_progress_key_prefix, job_key_prefix
from app.services.pdf_queue_recovery import MOVE_WAITING_PDF

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not os.environ.get('LOUPE_TEST_REDIS_URL'), reason='isolated Redis integration test')]


async def test_reserved_worker_progresses_while_general_worker_is_busy():
    pool = await create_pool(RedisSettings.from_dsn(os.environ['LOUPE_TEST_REDIS_URL']))
    namespace = 'queue-test:' + str(uuid4())
    started, release, pdf_finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def general(ctx):
        started.set()
        await release.wait()
    async def pdf(ctx):
        pdf_finished.set()
    general_worker = Worker([func(general, name='general')], redis_pool=pool, queue_name=namespace + ':general', max_jobs=1, burst=True, poll_delay=.01, handle_signals=False)
    pdf_worker = Worker([func(pdf, name='pdf')], redis_pool=pool, queue_name=namespace + ':pdf', max_jobs=1, burst=True, poll_delay=.01, handle_signals=False)
    jobs = [await pool.enqueue_job('general', _queue_name=namespace + ':general'),
            await pool.enqueue_job('pdf', _queue_name=namespace + ':pdf')]
    tasks = []
    try:
        tasks.append(asyncio.create_task(general_worker.async_run()))
        await asyncio.wait_for(started.wait(), 5)
        tasks.append(asyncio.create_task(pdf_worker.async_run()))
        await asyncio.wait_for(pdf_finished.wait(), 5)
        assert not release.is_set()
        release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), 5)
    finally:
        release.set()
        for task in tasks:
            if not task.done(): task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await pool.delete(*[prefix + job.job_id for prefix in ('arq:job:', 'arq:result:', 'arq:in-progress:') for job in jobs], namespace + ':general', namespace + ':pdf', namespace + ':general:health-check', namespace + ':pdf:health-check')
        await general_worker.close()
        await pdf_worker.close()


async def test_legacy_move_keeps_identity_and_never_moves_a_running_or_missing_job():
    pool = await create_pool(RedisSettings.from_dsn(os.environ['LOUPE_TEST_REDIS_URL']))
    identity = 'legacy-test:' + str(uuid4())
    old, new = identity + ':old', identity + ':new'
    running, payload = in_progress_key_prefix + identity, job_key_prefix + identity
    try:
        await pool.zadd(old, {identity: 123})
        assert await pool.eval(MOVE_WAITING_PDF, 4, old, new, running, payload, identity) == 0
        await pool.set(payload, b'unchanged-payload')
        await pool.set(running, b'worker-lock')
        assert await pool.eval(MOVE_WAITING_PDF, 4, old, new, running, payload, identity) == 0
        await pool.delete(running)
        async with pool.pipeline(transaction=True) as racing_worker:
            await racing_worker.watch(running)
            assert await pool.eval(MOVE_WAITING_PDF, 4, old, new, running, payload, identity) == 1
            racing_worker.multi()
            racing_worker.set(running, b'old-worker')
            from redis.exceptions import WatchError
            with pytest.raises(WatchError):
                await racing_worker.execute()
        assert await pool.zscore(old, identity) is None
        assert await pool.zscore(new, identity) == 123
        assert await pool.get(payload) == b'unchanged-payload'
        assert await pool.eval(MOVE_WAITING_PDF, 4, old, new, running, payload, identity) == 0
    finally:
        await pool.delete(old, new, running, payload)
        await pool.aclose()


async def _overlapping_work(ctx, namespace, role, outcome):
    pool = ctx['redis']
    await pool.set(namespace + ':' + role + ':started', '1')
    if outcome == 'fail':
        raise RuntimeError('Synthetic isolated job failure')
    if outcome == 'timeout':
        await asyncio.Event().wait()
    while not await pool.exists(namespace + ':' + role + ':release'):
        await pool.incr(namespace + ':' + role + ':heartbeat')
        await asyncio.sleep(.02)
    return role


def _isolated_worker(redis_url, queue, timeout):
    async def run():
        worker = Worker([func(_overlapping_work, name='process_batch')],
            redis_settings=RedisSettings.from_dsn(redis_url), queue_name=queue,
            max_jobs=1, burst=True, poll_delay=.01, job_timeout=timeout,
            handle_signals=False)
        try:
            await worker.async_run()
        finally:
            await worker.close()
    asyncio.run(run())


@pytest.mark.parametrize('first', ['ai', 'financial'])
@pytest.mark.parametrize('outcome', ['complete', 'fail', 'timeout'])
async def test_starting_second_ingestion_never_stops_first_in_separate_workers(first, outcome):
    """Actual Redis + spawned ARQ processes; no live service or provider calls."""
    redis_url = os.environ['LOUPE_TEST_REDIS_URL']
    pool = await create_pool(RedisSettings.from_dsn(redis_url))
    namespace = 'overlap-test:' + str(uuid4())
    second = 'financial' if first == 'ai' else 'ai'
    processes, jobs = [], []

    async def until(predicate):
        async with asyncio.timeout(15):
            while not await predicate():
                await asyncio.sleep(.02)

    async def submit(role, result):
        queue = namespace + ':' + role
        job = await pool.enqueue_job('process_batch', namespace, role, result,
            _queue_name=queue, _job_id=namespace + ':' + role + ':job')
        jobs.append(job)
        process = multiprocessing.get_context('spawn').Process(target=_isolated_worker,
            args=(redis_url, queue, .25 if result == 'timeout' else 25))
        process.start()
        processes.append(process)
        await until(lambda: pool.exists(namespace + ':' + role + ':started'))
        return job

    try:
        first_job = await submit(first, 'complete')
        before = int(await pool.get(namespace + ':' + first + ':heartbeat') or 0)
        second_job = await submit(second, outcome)
        await pool.set(namespace + ':' + second + ':release', '1')
        await until(lambda: second_job.result_info())
        info = await second_job.result_info()
        assert info.success == (outcome == 'complete')
        assert await first_job.result_info() is None

        async def still_progressing():
            return int(await pool.get(namespace + ':' + first + ':heartbeat') or 0) > before + 2
        await until(still_progressing)
        await pool.set(namespace + ':' + first + ':release', '1')
        assert await first_job.result(timeout=10) == first
    finally:
        for role in (first, second):
            await pool.set(namespace + ':' + role + ':release', '1')
        for process in processes:
            await asyncio.to_thread(process.join, 3)
            if process.is_alive():
                process.terminate()
                await asyncio.to_thread(process.join, 3)
            process.close()
        keys = [key async for key in pool.scan_iter(match=namespace + ':*')]
        keys += [prefix + job.job_id for prefix in ('arq:job:', 'arq:result:', 'arq:in-progress:') for job in jobs]
        if keys: await pool.delete(*keys)
        await pool.aclose()
