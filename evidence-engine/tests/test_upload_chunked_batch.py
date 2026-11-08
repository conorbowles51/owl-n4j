"""A press sent in chunks is one engine batch: the chunks wait undispatched, the close queues the whole batch once,
so the single unified dedup pass still sees every file of the press (lx-chunking, 8 Nov 2026)."""
import json
import logging
import uuid
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.api.routes.upload import upload_files
from app.config import settings
from app.services import batch_dispatch


class FakeResult:
    def __init__(self, jobs):
        self.jobs = jobs

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self.jobs))


class FakeDb:
    """Holds the jobs of one batch; every select returns them in insertion order."""

    def __init__(self, jobs=None) -> None:
        self.jobs = list(jobs or [])

    def add(self, job) -> None:
        self.jobs.append(job)

    async def execute(self, _query):
        return FakeResult(self.jobs)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def refresh(self, job) -> None:
        return None


class FakePool:
    def __init__(self) -> None:
        self.calls = []

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(job_id=kwargs.get("_job_id"))


async def send_chunk(db, pool, case_id, batch_id, names, *, open_batch=True):
    return await upload_files(
        case_id=case_id,
        request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool))),
        files=[UploadFile(file=BytesIO(b"same bytes"), filename=name) for name in names],
        processing_metadata=json.dumps([{"ingestion_request_id": "r", "source_evidence_file_id": str(uuid.uuid4())}
                                        for _ in names]),
        batch_id=str(batch_id), batch_open="true" if open_batch else None, db=db,
    )


@pytest.mark.asyncio
async def test_chunks_wait_and_the_close_queues_the_whole_press_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    db, pool, case_id, batch_id = FakeDb(), FakePool(), str(uuid.uuid4()), uuid.uuid4()

    first = await send_chunk(db, pool, case_id, batch_id, ["a.txt", "b.txt"])
    second = await send_chunk(db, pool, case_id, batch_id, ["a-copy.txt"])

    assert pool.calls == []  # nothing is read before the press is whole
    assert {job.batch_id for job in first + second} == {batch_id}
    assert all("batch_dispatch" not in job.pipeline_state for job in db.jobs)
    # Two identical files in different chunks are in one batch, so the unified pass reads them together.
    assert len({job.sha256 for job in db.jobs}) == 1 and len(db.jobs) == 3

    answer = await batch_dispatch.close_open_batch(db, case_id, batch_id, pool)
    again = await batch_dispatch.close_open_batch(db, case_id, batch_id, pool)

    assert answer == {"batch_id": str(batch_id), "job_count": 3, "closed": True} and again["closed"]
    assert pool.calls[0][0] == ("process_batch", str(batch_id), case_id)
    assert len({call[1]["_job_id"] for call in pool.calls}) == 1  # one stable queue id: queued once
    owners = [job for job in db.jobs if job.pipeline_state.get("batch_dispatch")]
    assert owners == [db.jobs[0]] and all("batch_open" not in job.pipeline_state for job in db.jobs)


@pytest.mark.asyncio
async def test_a_closed_or_foreign_batch_takes_no_more_chunks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    db, pool, case_id, batch_id = FakeDb(), FakePool(), str(uuid.uuid4()), uuid.uuid4()
    await send_chunk(db, pool, case_id, batch_id, ["a.txt"])
    with pytest.raises(HTTPException) as foreign:
        await send_chunk(db, pool, str(uuid.uuid4()), batch_id, ["b.txt"])
    await batch_dispatch.close_open_batch(db, case_id, batch_id, pool)
    with pytest.raises(HTTPException) as closed:
        await send_chunk(db, pool, case_id, batch_id, ["c.txt"])
    assert (foreign.value.status_code, closed.value.status_code) == (409, 409)
    assert "already been closed" in closed.value.detail


@pytest.mark.asyncio
async def test_an_open_chunk_needs_a_batch_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    with pytest.raises(HTTPException) as refused:
        await upload_files(case_id=str(uuid.uuid4()), request=None,
                           files=[UploadFile(file=BytesIO(b"x"), filename="a.txt")], batch_open="true", db=FakeDb())
    assert refused.value.status_code == 400


def test_a_refused_upload_says_why_in_the_log(caplog, monkeypatch) -> None:
    from app import main
    monkeypatch.setattr(settings, "service_api_key", "")
    boundary = "b0undary"
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="processing_metadata"\r\n\r\n'
            + "x" * (1024 * 1024 + 10) + f'\r\n--{boundary}--\r\n').encode()
    with caplog.at_level(logging.WARNING, logger="app.refusals"):
        response = TestClient(main.app).post(
            f"/cases/{uuid.uuid4()}/files", content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert response.status_code == 400
    assert "Part exceeded maximum size" in caplog.text and "request-refused POST" in caplog.text
