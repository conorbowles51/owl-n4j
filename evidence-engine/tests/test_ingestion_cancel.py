"""Cancel, a killed worker and the release pause on real rows (needs PostgreSQL: LOUPE_TEST_ENGINE_PG_URL)."""
import asyncio
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from arq.constants import in_progress_key_prefix
from fastapi import HTTPException
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import jobs as jobs_api
from app.api.routes import phone as phone_api
from app.jobs import janitor
from app.models.job import Job, JobStatus
from app.pipeline import batch_orchestrator
from app.services import ingestion_checkpoints as checkpoints
from app.services import ingestion_control as control

URL = os.environ.get("LOUPE_TEST_ENGINE_PG_URL")
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(not URL, reason="Requires LOUPE_TEST_ENGINE_PG_URL (a scratch PostgreSQL)")]


@pytest_asyncio.fixture
async def world(monkeypatch, tmp_path):
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
    sent = []

    async def publish(job_id, payload):
        sent.append((job_id, payload))

    for module in (control, janitor, batch_orchestrator):
        monkeypatch.setattr(module, "async_session", session)
        monkeypatch.setattr(module, "publish_progress", publish)
    monkeypatch.setattr(checkpoints.settings, "storage_path", str(tmp_path))
    yield SimpleNamespace(session=session, sent=sent, engine=engine)
    async with engine.begin() as conn:  # the other scratch-PostgreSQL modules rebuild evidence_files
        await conn.execute(text("DROP TABLE evidence_document_texts"))
    await engine.dispose()


async def make(world, statuses, *, job_type="ingestion", batched=True, **values):
    case, batch = str(uuid4()), uuid4()
    rows = [Job(id=uuid4(), case_id=case, batch_id=batch if batched else None, job_type=job_type, status=status,
                **{"file_name": f"file-{n}.txt", **values}) for n, status in enumerate(statuses)]
    async with world.session() as db:
        db.add_all(rows)
        await db.commit()
    return rows[0].case_id, batch, rows


async def read(world, rows):
    async with world.session() as db:
        found = [await db.get(Job, row.id) for row in rows]
    return found


async def cancel(world, row, case):
    async with world.session() as db:
        return await phone_api.cancel_phone_job(row.id, case, db)


async def control_job(world, row, case, action):
    async with world.session() as db:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=None)))
        return await jobs_api.control_job(row.id, action, request, case, db)


def units(calls, started, release):
    """A run of work units; the first unit waits, so a cancel lands while it runs, as a provider call."""
    @checkpoints.checkpointed("test/unit:v1", ignore=())
    async def unit(number):
        calls.append(number)
        if number == 1:
            started.set()
            await release.wait()
        return number

    async def operation():
        for number in (1, 2, 3):
            await unit(number)
    return operation


async def test_cancel_of_a_running_ingestion_stops_at_the_next_work_unit(world):
    """Fails on the old code: cancel answers 409 "Only phone report readings can be cancelled"."""
    case, batch, rows = await make(world, [JobStatus.COMPLETED, JobStatus.EXTRACTING_TEXT, JobStatus.EXTRACTING_TEXT])
    calls, started, release = [], asyncio.Event(), asyncio.Event()
    run = asyncio.create_task(control.run_controlled(str(batch), case, units(calls, started, release)))
    await asyncio.wait_for(started.wait(), 30)
    assert await cancel(world, rows[1], case) == {"state": "cancelling", "affected_jobs": 2}
    still = await read(world, rows)
    assert still[1].status == JobStatus.EXTRACTING_TEXT and not still[1].cancelled_at  # the worker has not stopped yet
    release.set()
    await asyncio.wait_for(run, 30)
    assert calls == [1]  # unit 1 finished and saved; 2 and 3 never ran
    done = await read(world, rows)
    assert done[0].status == JobStatus.COMPLETED and done[0].cancelled_at is None  # finished work stays finished
    for row in done[1:]:
        assert row.status == JobStatus.FAILED and row.cancelled_at and not row.paused and not row.pause_requested
        assert row.error_message.startswith(control.CANCELLED_PREFIX)
        assert "In this batch of 3: 2 cancelled, 1 finished and stay in the case." in row.error_message
    assert sorted(job for job, _ in world.sent) == sorted(str(row.id) for row in done[1:])


async def test_double_cancel_changes_nothing(world):
    case, batch, rows = await make(world, [JobStatus.CHUNKING, JobStatus.CHUNKING])
    assert (await cancel(world, rows[0], case))["state"] == "cancelling"
    assert await cancel(world, rows[1], case) == {"state": "cancelling", "affected_jobs": 0}
    await control.finish_cancel(control.scope_filter(batch, True), case)
    first = await read(world, rows)
    assert await cancel(world, rows[0], case) == {"state": "cancelled", "affected_jobs": 0}
    await control.finish_cancel(control.scope_filter(batch, True), case)
    second = await read(world, rows)
    assert [r.cancelled_at for r in first] == [r.cancelled_at for r in second]
    assert len(world.sent) == 2


async def test_queued_work_is_cancelled_at_once_and_its_run_does_nothing(world):
    case, batch, rows = await make(world, [JobStatus.PENDING, JobStatus.PENDING])
    assert await cancel(world, rows[0], case) == {"state": "cancelled", "affected_jobs": 2}
    entered = []

    async def operation():
        entered.append(1)
    await control.run_controlled(str(batch), case, operation)  # the queue still holds it, and a retry may come
    assert entered == []
    assert all(r.status == JobStatus.FAILED and r.cancelled_at and not r.paused for r in await read(world, rows))


@pytest.mark.parametrize("job_type", ["pdf_review", "audio_review"])
async def test_a_person_paused_batch_cancels_at_once_and_resume_cannot_undo_it(world, job_type):
    case, _, rows = await make(world, [JobStatus.PENDING], job_type=job_type, paused=True, pause_requested=True)
    assert (await cancel(world, rows[0], case))["state"] == "cancelled"
    for action in ("resume", "pause"):
        with pytest.raises(HTTPException) as refused:
            await control_job(world, rows[0], case, action)
        assert refused.value.status_code == 409 and "cancelled" in refused.value.detail
    row = (await read(world, rows))[0]
    assert row.status == JobStatus.FAILED and row.cancelled_at
    assert ("PDF" if job_type == "pdf_review" else "recording") in row.error_message


async def test_resume_all_of_a_release_does_not_undo_a_cancel(world):
    """wcontrol's own statements: it flags unfinished rows, and on resume clears the flag of exactly those rows."""
    case, _, rows = await make(world, [JobStatus.PENDING, JobStatus.PENDING])
    async with world.engine.begin() as conn:
        await conn.execute(text("update jobs set paused = true where status not in ('completed','failed') "
                                "and coalesce(paused,false) = false"))
    assert (await cancel(world, rows[0], case))["state"] == "cancelled"
    async with world.engine.begin() as conn:
        for row in rows:
            await conn.execute(text("update jobs set paused = false where id = :i"), {"i": row.id})
    assert all(r.status == JobStatus.FAILED and r.cancelled_at for r in await read(world, rows))


async def test_a_release_pause_does_not_read_as_a_cancel(world):
    case, batch, rows = await make(world, [JobStatus.PENDING], batched=True)
    async with world.engine.begin() as conn:
        await conn.execute(text("update jobs set paused = true"))
    await control.finish_cancel(control.scope_filter(batch, True), case)
    row = (await read(world, rows))[0]
    assert row.status == JobStatus.PENDING and row.paused and not row.cancel_requested and row.cancelled_at is None


async def test_pause_still_pauses(world):
    case, batch, rows = await make(world, [JobStatus.CHUNKING], pause_requested=True)
    entered = []

    async def operation():
        entered.append(1)
    await control.run_controlled(str(batch), case, operation)
    row = (await read(world, rows))[0]
    assert entered == [] and row.paused and row.status == JobStatus.PENDING and row.cancelled_at is None


async def test_once_writing_has_begun_a_cancel_is_refused_with_the_reason(world):
    case, batch, rows = await make(world, [JobStatus.GENERATING_SUMMARIES, JobStatus.GENERATING_SUMMARIES])
    await control.begin_publication([row.id for row in rows])
    with pytest.raises(HTTPException) as refused:
        await cancel(world, rows[0], case)
    assert refused.value.status_code == 409 and "writing to the case" in refused.value.detail
    assert not any(r.cancel_requested for r in await read(world, rows))


async def test_a_batch_paused_after_writing_began_still_refuses_a_cancel(world):
    case, batch, rows = await make(world, [JobStatus.WRITING_GRAPH])
    await control.begin_publication([rows[0].id])
    async with world.session() as db:
        await db.execute(update(Job).values(status=JobStatus.PENDING, paused=True))
        await db.commit()
    with pytest.raises(HTTPException):
        await cancel(world, rows[0], case)


async def test_a_cancel_that_arrives_first_stops_the_write(world):
    case, batch, rows = await make(world, [JobStatus.GENERATING_SUMMARIES])
    await cancel(world, rows[0], case)
    with pytest.raises(checkpoints.IngestionPaused):
        await control.begin_publication([rows[0].id])
    assert "publication_begun" not in (await read(world, rows))[0].pipeline_state


async def test_kinds_that_cannot_cancel_say_so(world):
    case, _, rows = await make(world, [JobStatus.MERGING_PROPERTIES], job_type="entity_merge", batched=False)
    with pytest.raises(HTTPException) as refused:
        await cancel(world, rows[0], case)
    assert refused.value.status_code == 409 and "cannot be cancelled" in refused.value.detail


async def test_nothing_to_cancel_is_a_refusal_not_a_cancel(world):
    case, _, rows = await make(world, [JobStatus.COMPLETED, JobStatus.FAILED])
    with pytest.raises(HTTPException) as refused:
        await cancel(world, rows[0], case)
    assert "already finished" in refused.value.detail
    assert not any(r.cancelled_at for r in await read(world, rows))


async def test_a_real_failure_stays_a_failure_and_is_counted(world):
    case, batch, rows = await make(world, [JobStatus.FAILED, JobStatus.CHUNKING])
    await cancel(world, rows[1], case)
    await control.finish_cancel(control.scope_filter(batch, True), case)
    failed, cancelled = await read(world, rows)
    assert failed.cancelled_at is None and cancelled.cancelled_at and "1 failed earlier" in cancelled.error_message


async def test_resume_of_a_failed_file_cannot_rerun_a_cancelled_batch(world):
    """A resumed run takes every unfinished row: it would write over the cancelled files and then stop for ever."""
    case, batch, rows = await make(world, [JobStatus.FAILED, JobStatus.CHUNKING], resumable=True)
    await cancel(world, rows[1], case)
    await control.finish_cancel(control.scope_filter(batch, True), case)
    with pytest.raises(HTTPException) as refused:
        await control_job(world, rows[0], case, "resume")
    assert refused.value.status_code == 409 and "Process the file again" in refused.value.detail
    failed, cancelled = await read(world, rows)
    assert failed.status == JobStatus.FAILED and not failed.resumable and cancelled.status == JobStatus.FAILED


async def test_a_pdf_batch_stays_cancellable_after_one_file_is_stored(world):
    case, batch, rows = await make(world, [JobStatus.EXTRACTING_TEXT, JobStatus.PENDING], job_type="pdf_review")
    await control.begin_publication([rows[0].id])
    async with world.session() as db:
        (await db.get(Job, rows[0].id)).status = JobStatus.COMPLETED
        await db.commit()
    assert (await cancel(world, rows[1], case))["state"] == "cancelled"
    finished, stopped = await read(world, rows)
    assert finished.status == JobStatus.COMPLETED and finished.cancelled_at is None and stopped.cancelled_at


async def test_a_cancel_just_before_the_pdf_store_keeps_the_earlier_reading(world, monkeypatch):
    """The window after the last page: the same lock decides, so an accepted cancel writes nothing."""
    from app.pipeline import prepare_pdf_review as pdf
    case, _, rows = await make(world, [JobStatus.EXTRACTING_TEXT], job_type="pdf_review", batched=False,
                               file_name="a.pdf", file_path="/a.pdf", source_evidence_file_id=uuid4())

    async def extract(*_a, **_k):
        await cancel(world, rows[0], case)
        return SimpleNamespace(metadata={})

    async def status(*_a, **_k):
        return None

    async def stored(*_a, **_k):
        raise AssertionError("the file's text was replaced after an accepted cancel")
    monkeypatch.setattr(pdf, "extract_text", extract)
    monkeypatch.setattr(pdf, "upsert_evidence_document_text", stored)
    with pytest.raises(checkpoints.IngestionPaused):
        await pdf.prepare_pdf_review((await read(world, rows))[0], status)


async def test_a_failure_after_the_cancel_ends_cancelled_and_resume_is_refused(world):
    """A single-file run's own handlers write FAILED. Without this: Resume refused for ever, and the file's earlier
    run cleared as if it had failed."""
    case, _, rows = await make(world, [JobStatus.CHUNKING], batched=False)
    await cancel(world, rows[0], case)
    async with world.session() as db:
        row = await db.get(Job, rows[0].id)
        row.status, row.error_message = JobStatus.FAILED, "Job interrupted (worker timeout or shutdown)"
        await db.commit()
    await control.finish_cancel(control.scope_filter(rows[0].id, False), case)
    row = (await read(world, rows))[0]
    assert row.cancelled_at and row.error_message.startswith(control.CANCELLED_PREFIX)
    assert world.sent[-1][1]["cancelled_at"]


async def test_a_worker_write_after_a_queued_cancel_cannot_leave_it_running(world):
    case, batch, rows = await make(world, [JobStatus.PENDING])
    await cancel(world, rows[0], case)
    async with world.session() as db:  # a run that had just started when the cancel landed
        (await db.get(Job, rows[0].id)).status = JobStatus.EXTRACTING_TEXT
        await db.commit()
    await control.finish_cancel(control.scope_filter(batch, True), case)
    assert (await read(world, rows))[0].status == JobStatus.FAILED


async def test_a_batch_crash_during_a_cancel_reads_as_cancelled(world):
    case, batch, rows = await make(world, [JobStatus.CHUNKING])
    await cancel(world, rows[0], case)
    await batch_orchestrator._force_fail_unfinished_batch_rows(str(batch), "Batch pipeline failed: boom")

    async def operation():
        raise RuntimeError("boom")
    await control.run_controlled(str(batch), case, operation)
    row = (await read(world, rows))[0]
    assert row.cancelled_at and row.error_message.startswith(control.CANCELLED_PREFIX)


async def test_text_kept_with_a_cancelled_file_is_stated_with_its_count(world):
    case, batch, rows = await make(world, [JobStatus.EXTRACTING_ENTITIES])
    file_id = uuid4()
    async with world.engine.begin() as conn:
        await conn.execute(text("insert into evidence_files (id) values (:i)"), {"i": file_id})
        await conn.execute(text("insert into evidence_document_texts (evidence_file_id, engine_job_id, content, "
                                "content_sha256, character_count) values (:f, :j, 'x', '0', 1)"),
                           {"f": file_id, "j": rows[0].id})
    await cancel(world, rows[0], case)
    await control.finish_cancel(control.scope_filter(batch, True), case)
    assert "stays with 1 file, in place of any earlier text, and document search can find it" in (await read(world, rows))[0].error_message


async def test_a_cancel_whose_worker_was_killed_finishes(world):
    """Fails on the old code: nothing finishes it until the 2 h janitor, and then as a crash."""
    case, _, rows = await make(world, [JobStatus.CHUNKING, JobStatus.CHUNKING], cancel_requested=True)
    async with world.engine.begin() as conn:
        await conn.execute(text("update jobs set updated_at = :t"), {"t": datetime.utcnow() - timedelta(minutes=6)})
    assert await janitor.finish_abandoned_cancels() == 2
    assert all(r.status == JobStatus.FAILED and r.cancelled_at for r in await read(world, rows))
    assert await janitor.finish_abandoned_cancels() == 0


async def test_a_recent_cancel_is_left_to_its_worker(world):
    await make(world, [JobStatus.CHUNKING], cancel_requested=True)
    assert await janitor.finish_abandoned_cancels() == 0


async def test_the_janitor_never_turns_a_killed_job_into_a_cancel(world):
    _, _, rows = await make(world, [JobStatus.CHUNKING])
    async with world.engine.begin() as conn:
        await conn.execute(text("update jobs set updated_at = :t"), {"t": datetime.utcnow() - timedelta(hours=3)})
    await janitor.reap_stale_jobs({})
    row = (await read(world, rows))[0]
    assert row.status == JobStatus.FAILED and row.cancelled_at is None and "worker likely crashed" in row.error_message


class Queue:
    """The keys recover_interrupted_work reads."""

    def __init__(self, members, marks):
        self.members, self.marks = set(members), set(marks)

    async def zscore(self, queue, member):
        return 1.0 if member in self.members else None

    async def delete(self, key):
        present = key in self.marks
        self.marks.discard(key)
        return int(present)


async def test_a_killed_workers_mark_is_cleared_when_a_worker_starts(world):
    """Fails on the old code: only phone jobs were recovered; these waited for ARQ's 4 h timeout."""
    dispatch = {"batch_dispatch": {"state": "dispatched", "queue_job_id": "evidence:one"}}
    _, _, rows = await make(world, [JobStatus.EXTRACTING_TEXT], pipeline_state=dispatch)
    queue = Queue({"evidence:one"}, {in_progress_key_prefix + "evidence:one"})
    assert await janitor.recover_interrupted_work(queue, "arq:queue") == 1
    assert not queue.marks


async def test_a_member_row_finds_its_owners_queue_entry(world):
    case, batch, rows = await make(world, [JobStatus.COMPLETED, JobStatus.EXTRACTING_TEXT])
    async with world.session() as db:
        owner = await db.get(Job, rows[0].id)
        owner.pipeline_state = {"batch_dispatch": {"state": "dispatched", "queue_job_id": "evidence:b"}}
        await db.commit()
    queue = Queue({"evidence:b"}, {in_progress_key_prefix + "evidence:b"})
    assert await janitor.recover_interrupted_work(queue, "arq:queue") == 1


async def test_another_queues_work_and_paused_work_are_left_alone(world):
    dispatch = {"batch_dispatch": {"state": "dispatched", "queue_job_id": "evidence:two"}}
    await make(world, [JobStatus.EXTRACTING_TEXT], pipeline_state=dispatch)
    paused = {"batch_dispatch": {"state": "dispatched", "queue_job_id": "evidence:three"}}
    await make(world, [JobStatus.EXTRACTING_TEXT], pipeline_state=paused, paused=True)
    queue = Queue({"evidence:three"}, {in_progress_key_prefix + "evidence:two", in_progress_key_prefix + "evidence:three"})
    assert await janitor.recover_interrupted_work(queue, "arq:queue") == 0
    assert len(queue.marks) == 2


async def test_resume_works_after_a_worker_died_while_pausing(world, monkeypatch):
    """Fails on the old code: the row is failed, yet Resume answers "Pausing" for ever."""
    from app.services import batch_dispatch

    async def dispatched(job, db, pool):
        return True
    monkeypatch.setattr(batch_dispatch, "dispatch_ingestion_batch", dispatched)
    case, _, rows = await make(world, [JobStatus.FAILED], pause_requested=True, resumable=True)
    assert (await control_job(world, rows[0], case, "resume"))["state"] == "queued"


async def test_an_old_retry_of_a_failed_merge_changes_nothing(world, monkeypatch):
    """Fails on the old code: ARQ's retry after a killed worker ran a merge the janitor had already failed."""
    from unittest.mock import AsyncMock
    from app.pipeline import merge_orchestrator
    monkeypatch.setattr(merge_orchestrator, "load_ai_model_policy", AsyncMock())
    update_job = AsyncMock()
    monkeypatch.setattr(merge_orchestrator, "_update_job", update_job)
    _, _, rows = await make(world, [JobStatus.FAILED], job_type="entity_merge", batched=False, merge_payload={"entities": []})
    async with world.session() as db:
        await merge_orchestrator.run_merge_pipeline(rows[0].id, db)
    update_job.assert_not_awaited()
