"""SIGKILL a real ARQ worker in the middle of a batch; a new worker resumes it from its checkpoints.
Needs a scratch PostgreSQL and Redis: LOUPE_TEST_ENGINE_PG_URL, LOUPE_TEST_REDIS_URL."""
import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from arq.connections import RedisSettings, create_pool
from arq.constants import in_progress_key_prefix
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.job import Job, JobStatus

URL = os.environ.get("LOUPE_TEST_ENGINE_PG_URL")
REDIS = os.environ.get("LOUPE_TEST_REDIS_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not (URL and REDIS), reason="Requires a scratch PostgreSQL and Redis")]
QUEUE = "arq:test-kill"


def worker(tmp_path: Path, log: Path):
    env = {**os.environ, "DATABASE_URL": URL, "REDIS_URL": REDIS, "STORAGE_PATH": str(tmp_path), "UNIT_LOG": str(log),
           "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), os.environ.get("PYTHONPATH", "")])}
    output = open(tmp_path / "worker.log", "a")
    return subprocess.Popen([sys.executable, "-m", "arq", "worker_kill_stub.Settings"], env=env, stdout=output,
                            stderr=subprocess.STDOUT)


async def until(check, seconds, what):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if await check():
            return
        await asyncio.sleep(0.2)
    raise AssertionError(f"timed out after {seconds} s waiting for {what}")


async def test_a_killed_worker_resumes_from_its_checkpoint_at_the_next_start(tmp_path):
    """Fails on the old code: the in-progress mark holds the job for the 4 h job timeout, so the second worker never
    takes it and the row reads as running until the janitor fails it at 2 h."""
    engine = create_async_engine(URL)
    labels = ", ".join(f"'{status.value}'" for status in JobStatus)
    async with engine.begin() as conn:
        for statement in ("DROP TABLE IF EXISTS pending_chunk_vectors", "DROP TABLE IF EXISTS evidence_document_texts", "DROP TABLE IF EXISTS jobs",
                          "DROP TABLE IF EXISTS evidence_files", "DROP TYPE IF EXISTS jobstatus",
                          f"CREATE TYPE jobstatus AS ENUM ({labels})",
                          "CREATE TABLE evidence_files (id uuid PRIMARY KEY, deleted_at timestamptz)",
                          "CREATE TABLE evidence_document_texts (evidence_file_id uuid PRIMARY KEY REFERENCES evidence_files(id), "
                          "engine_job_id uuid, content text NOT NULL, content_sha256 varchar(64) NOT NULL, "
                          "character_count bigint NOT NULL, source_locations jsonb NOT NULL DEFAULT '[]', "
                          "processing_manifest jsonb, extracted_at timestamptz NOT NULL DEFAULT now())"):
            await conn.execute(text(statement))
        await conn.run_sync(Job.__table__.create)
    session = async_sessionmaker(engine, expire_on_commit=False)
    case, batch = str(uuid4()), uuid4()
    identity = f"evidence-kill:{batch}"
    async with session() as db:
        db.add(Job(id=uuid4(), case_id=case, batch_id=batch, job_type="ingestion", status=JobStatus.EXTRACTING_TEXT,
                   pipeline_state={"batch_dispatch": {"state": "dispatched", "queue_job_id": identity}}))
        await db.commit()
    pool = await create_pool(RedisSettings.from_dsn(REDIS))
    await pool.flushdb()
    await pool.enqueue_job("process_batch", str(batch), case, _job_id=identity, _queue_name=QUEUE)
    log = tmp_path / "units.log"
    first = worker(tmp_path, log)
    second = None
    try:
        async def in_unit_two():
            return log.exists() and log.read_text().split() == ["1", "2"]
        await until(in_unit_two, 120, "unit 2 of the first worker")
        first.send_signal(signal.SIGKILL)
        first.wait(30)
        assert await pool.exists(in_progress_key_prefix + identity)  # what a killed worker leaves behind
        second = worker(tmp_path, log)

        async def finished():
            async with session() as db:
                from sqlalchemy import select
                return await db.scalar(select(Job.status).where(Job.batch_id == batch)) == JobStatus.COMPLETED
        await until(finished, 120, "the second worker to finish the batch")
        # Unit 1 was saved and did not run again; unit 2 was lost with the worker and did; unit 3 ran once.
        assert log.read_text().split() == ["1", "2", "2", "3"]
    finally:
        for process in (first, second):
            if process and process.poll() is None:
                process.kill()
        await pool.flushdb()
        await pool.close()
        async with engine.begin() as conn:  # the other scratch-PostgreSQL modules rebuild evidence_files
            await conn.execute(text("DROP TABLE evidence_document_texts"))
        await engine.dispose()
