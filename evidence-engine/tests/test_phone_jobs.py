"""Phone capture jobs: idempotent creation (PA-7 to PA-10), the phone queue, pause/resume and cancel routing,
the worker settings and progress (01 sections 4.3, 10.1, 10.2, 10.6)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes import phone as api
from app.models.job import JobStatus
from app.phone import paths


class Db:
    def __init__(self):
        self.rows = {}

    async def get(self, model, identity):
        return self.rows.get(identity)

    def add(self, job):
        self.rows[job.id] = job

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, job, *a):
        pass


class Pool:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def enqueue_job(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail:
            raise OSError("Synthetic lost Redis acknowledgement")


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "data_root", lambda: tmp_path)
    (tmp_path / "case" / "_upload_groups" / "g" / "payload").mkdir(parents=True)
    (tmp_path / "case" / "_upload_groups" / "g" / "payload" / "Phone.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)
    return tmp_path


def body(identity, **kw):
    return api.PhoneJobRequest(request_id=identity, container_path="_upload_groups/g/payload/Phone.zip",
                               root_path="Phone_Report", container_evidence_id=uuid4(), **kw)


def req(pool):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(arq_pool=pool)))


@pytest.mark.asyncio
async def test_pa7_pa10_same_request_is_one_job_dispatched_once_on_the_phone_queue(case):
    identity = uuid4()
    b = body(identity)
    db, pool = Db(), Pool(fail=True)
    first = await api.create_phone_job("case", b, req(pool), db)
    assert first.job_type == "phone_capture" and first.pipeline_state["batch_dispatch"]["state"] == "retry"
    pool.fail = False
    second = await api.create_phone_job("case", b, req(pool), db)
    assert second is first and len(db.rows) == 1  # PA-7
    assert second.pipeline_state["batch_dispatch"]["state"] == "dispatched"
    args, kwargs = pool.calls[-1]
    assert args == ("process_phone_capture", str(identity), "case")
    assert kwargs["_queue_name"] == "arq:phone-capture" and kwargs["_job_id"] == "phone-capture:%s" % identity
    await api.create_phone_job("case", b, req(pool), db)
    assert len(pool.calls) == 2  # PA-10: not dispatched again


@pytest.mark.asyncio
async def test_pa8_reused_request_id_with_another_body_or_case(case):
    identity = uuid4()
    db, pool = Db(), Pool()
    b = body(identity)
    await api.create_phone_job("case", b, req(pool), db)
    with pytest.raises(HTTPException) as e:
        await api.create_phone_job("case", b.model_copy(update={"root_path": "Other"}), req(pool), db)
    assert (e.value.status_code, e.value.detail) == (409, "This processing request belongs to another selection")
    (case / "other" / "_upload_groups" / "g" / "payload").mkdir(parents=True)
    (case / "other" / "_upload_groups" / "g" / "payload" / "Phone.zip").write_bytes(b"x")
    with pytest.raises(HTTPException) as e:
        await api.create_phone_job("other", b, req(pool), db)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_pa9_a_concurrent_first_request_that_loses_the_insert_gets_the_winners_job(case):
    from sqlalchemy.exc import IntegrityError
    identity = uuid4()
    b = body(identity)
    winner_db, pool = Db(), Pool()
    winner = await api.create_phone_job("case", b, req(pool), winner_db)

    class LoserDb(Db):
        calls = 0

        async def get(self, model, ident):
            LoserDb.calls += 1
            return None if LoserDb.calls == 1 else winner  # not there when it looked, there after the race

        async def commit(self):
            raise IntegrityError("insert", {}, Exception("duplicate key"))
    got = await api.create_phone_job("case", b, req(pool), LoserDb())
    assert got is winner and len(winner_db.rows) == 1


@pytest.mark.asyncio
async def test_root_path_cannot_climb(case):
    with pytest.raises(HTTPException) as e:
        await api.create_phone_job("case", body(uuid4()).model_copy(update={"root_path": "../x"}), req(Pool()), Db())
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_phone_jobs_pause_and_resume_on_the_phone_function():
    from app.api.routes.jobs import control_job
    identity = uuid4()
    job = SimpleNamespace(id=identity, case_id="case", batch_id=None, job_type="phone_capture",
                          status=JobStatus.CAPTURING, pause_requested=False, paused=False, resumable=True,
                          resume_generation=0, error_message=None,
                          pipeline_state={"processing_queue": "arq:phone-capture"})
    db = Db()
    db.rows[identity] = job
    db.execute = AsyncMock(return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [job])))
    pool = Pool()
    assert (await control_job(identity, "pause", req(pool), "case", db))["state"] == "pausing"
    job.paused, job.status = True, JobStatus.PENDING
    assert (await control_job(identity, "resume", req(pool), "case", db))["state"] == "queued"
    args, kwargs = pool.calls[0]
    assert args == ("process_phone_capture", str(identity), "case") and kwargs["_queue_name"] == "arq:phone-capture"


@pytest.mark.asyncio
async def test_cancel_on_an_active_extraction_is_refused(monkeypatch):
    identity = uuid4()
    job = SimpleNamespace(id=identity, case_id="case", job_type="phone_capture", status=JobStatus.COMPLETED,
                          pipeline_state={}, pause_requested=False, paused=False)
    db = Db()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: job))
    monkeypatch.setattr(api, "_standing", AsyncMock(return_value="active"))
    with pytest.raises(HTTPException) as e:
        await api.cancel_phone_job(identity, "case", db)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_cancel_while_running_asks_the_worker_to_stop(monkeypatch):
    identity = uuid4()
    job = SimpleNamespace(id=identity, case_id="case", job_type="phone_capture", status=JobStatus.CAPTURING,
                          pipeline_state={"phone": {"stage": "capturing"}}, pause_requested=False, paused=False)
    db = Db()
    db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: job))
    monkeypatch.setattr(api, "_standing", AsyncMock(return_value="pending"))
    assert await api.cancel_phone_job(identity, "case", db) == {"state": "cancelling"}
    assert job.pause_requested and job.pipeline_state["phone"]["cancel_requested"]


def test_cancel_route_is_matched_before_the_generic_job_action():
    from app.main import app
    routes = []
    for r in app.routes:  # FastAPI 0.16x wraps each included router
        inner = getattr(getattr(r, "original_router", None), "routes", None)
        routes.extend(x.path for x in (inner if inner is not None else [r]) if hasattr(x, "path"))
    assert routes.index("/jobs/{job_id}/cancel") < routes.index("/jobs/{job_id}/{action}")


def test_phone_worker_settings():
    from app.worker import PdfReviewWorkerSettings, PhoneCaptureWorkerSettings, WorkerSettings
    s = PhoneCaptureWorkerSettings
    assert s.queue_name == "arq:phone-capture" and s.max_jobs == 1
    assert [f.__name__ for f in s.functions] == ["process_phone_capture"]
    assert s.job_timeout >= 292 * 60  # v1's longest phone ingest (01 section 1.7)
    assert "process_phone_capture" not in [f.__name__ for f in PdfReviewWorkerSettings.functions]
    assert getattr(WorkerSettings, "queue_name", None) is None


def test_compose_runs_the_phone_worker_with_its_memory_limit():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    block = text.split("  evidence-phone-worker:\n", 1)[1].split("\n\n", 1)[0]
    assert "command: arq app.worker.PhoneCaptureWorkerSettings" in block and "mem_limit: 1g" in block
    assert "<<: *evidence-worker" in block


@pytest.mark.asyncio
async def test_progress_carries_stage_and_counts_every_second(monkeypatch):
    """The job publishes each stage in order with structured counts, and repeats the last state each second."""
    from app.phone import job as phone_job
    published = []
    monkeypatch.setattr(phone_job, "publish_progress", AsyncMock(side_effect=lambda jid, p: published.append(p)))

    def fake_run(conn, **kw):
        rep = kw["reporter"]
        for stage, p in (("verifying_container", 0.01), ("detecting", 0.05), ("counting", 0.1),
                         ("capturing", 0.3), ("reconciling", 0.7), ("indexing_files", 0.8)):
            rep.stage(stage, p, stage, {"records": 1})
            import time
            time.sleep(1.2 if stage == "capturing" else 0.05)
        return {"state": "captured", "records": 1, "files": 0, "message": "done", "extraction_id": "e"}

    monkeypatch.setattr(phone_job, "run_capture", fake_run)
    monkeypatch.setattr(phone_job, "connect", lambda url: SimpleNamespace(close=lambda: None))
    from app.services import ingestion_checkpoints
    monkeypatch.setattr(ingestion_checkpoints, "pause_boundary", AsyncMock())
    job = SimpleNamespace(id=uuid4(), case_id="case", merge_payload={}, progress=0.0, pipeline_state={},
                          status=JobStatus.PENDING, error_message=None, entity_count=0)

    class JobDb(Db):
        async def execute(self, *a, **k):
            return SimpleNamespace(scalar_one=lambda: job)
    await phone_job.run_phone_capture(str(job.id), JobDb())
    stages = [p.get("stage") for p in published]
    order = [s for i, s in enumerate(stages) if s and (i == 0 or stages[i - 1] != s)]
    assert order == ["verifying_container", "detecting", "counting", "capturing", "reconciling", "indexing_files",
                     "finishing"]
    assert stages.count("capturing") >= 2  # repeated while the stage runs
    assert all("counts" in p for p in published if p.get("stage") == "capturing")
    assert published[-1]["status"] == "completed" and job.status == JobStatus.COMPLETED
    assert {p["status"] for p in published} >= {"verifying_source", "capturing", "reconciling"}


@pytest.mark.asyncio
async def test_stored_progress_records_when_the_stage_and_the_counts_last_changed(monkeypatch):
    """The card's stall rule (07 4.7) reads changed_at: it moves when the stage or the counts change, not on a repeat,
    and a cancel request written by another session is never overwritten."""
    from app.phone import job as phone_job
    monkeypatch.setattr(phone_job, "publish_progress", AsyncMock())
    clock = iter(["2026-11-01T10:00:0%d+00:00" % i for i in range(10)])

    class Clock:
        @staticmethod
        def now(tz=None):
            return SimpleNamespace(isoformat=lambda: next(clock))
    monkeypatch.setattr(phone_job, "datetime", Clock)
    job = SimpleNamespace(id=uuid4(), pipeline_state={"phone": {"cancel_requested": True}}, status=None, progress=0,
                          error_message=None)
    db = SimpleNamespace(refresh=AsyncMock(), commit=AsyncMock())
    phone = lambda: job.pipeline_state["phone"]
    await phone_job._publish(job, db, JobStatus.CAPTURING, 0.3, "m", stage="capturing", counts={"records": 1})
    assert (phone()["stage_started_at"], phone()["changed_at"], phone()["cancel_requested"]) == (
        "2026-11-01T10:00:00+00:00", "2026-11-01T10:00:00+00:00", True)
    await phone_job._publish(job, db, JobStatus.CAPTURING, 0.3, "m", stage="capturing", counts={"records": 1})
    assert phone()["changed_at"] == "2026-11-01T10:00:00+00:00"  # a repeat is not a change
    await phone_job._publish(job, db, JobStatus.CAPTURING, 0.4, "m", stage="capturing", counts={"records": 9})
    assert phone()["changed_at"] == "2026-11-01T10:00:02+00:00"
    assert phone()["stage_started_at"] == "2026-11-01T10:00:00+00:00"
    await phone_job._publish(job, db, JobStatus.RECONCILING, 0.7, "m", stage="reconciling", counts={"records": 9})
    assert phone()["stage_started_at"] == phone()["changed_at"] == "2026-11-01T10:00:03+00:00"
