"""The engine jobs poll (GET /api/evidence/engine/jobs) is repeated every few seconds from every open Evidence and
Financial batch page. It must not load whole evidence rows, must not reconcile an unchanged job list again, and must
keep its database work off the event loop."""

from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from services import evidence_job_sync


@pytest.fixture()
def Session():
    # One shared connection usable from the worker thread the handler moves its database work to.
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__])
    yield sessionmaker(bind=engine, future=True)
    engine.dispose()


@pytest.fixture(autouse=True)
def _fresh_poll_state():
    evidence_job_sync._poll_settled.clear()
    yield
    evidence_job_sync._poll_settled.clear()


def _file(case_id, *, job_id=None, status="processing", request_id=None):
    return EvidenceFile(
        id=uuid4(), case_id=case_id, original_filename="a.pdf", stored_path="/tmp/a.pdf", size=1,
        sha256="a" * 64, status=status, engine_job_id=job_id,
        last_processed_profile_snapshot={"ingestion_request_id": request_id, "bulky": "x" * 1000} if request_id else None,
    )


def test_reconcile_reads_the_accepted_request_without_loading_the_snapshot(Session):
    case_id = uuid4()
    with Session() as db:
        current = _file(case_id, request_id="r2")
        db.add(current)
        db.commit()
        file_id = current.id

    old_job, new_job = str(uuid4()), str(uuid4())
    jobs = [
        dict(id=new_job, source_evidence_file_id=str(file_id), status="completed", entity_count=4,
             created_at="2026-10-30T10:00:00Z", pipeline_state={"ingestion_request_id": "r2"}),
        dict(id=old_job, source_evidence_file_id=str(file_id), status="failed", error_message="old",
             created_at="2026-10-30T11:00:00Z", pipeline_state={"ingestion_request_id": "r1"}),
    ]
    statements = []
    with Session() as db:
        listener = lambda conn, cursor, statement, *rest: statements.append(statement)
        event.listen(db.get_bind(), "before_cursor_execute", listener)
        assert evidence_job_sync.reconcile_jobs_payload(db, jobs) == 1
        event.remove(db.get_bind(), "before_cursor_execute", listener)
        record = db.get(EvidenceFile, file_id)
        # The newer attempt belongs to an earlier upload: only the accepted request controls the record.
        assert (record.status, record.engine_job_id, record.entity_count) == ("processed", new_job, 4)
        db.commit()

    selects = [s for s in statements if s.lstrip().startswith("SELECT")]
    assert selects
    for statement in selects:
        # Only the request id is read from the snapshot, and no bulky column is loaded.
        assert "last_processed_profile_snapshot" not in statement.replace(
            "JSON_EXTRACT(evidence_files.last_processed_profile_snapshot", "")
        assert "evidence_files.metadata" not in statement


def test_poll_reconciles_only_when_the_job_list_changed(Session, monkeypatch):
    case_id = uuid4()
    with Session() as db:
        record = _file(case_id)
        db.add(record)
        db.commit()
        file_id = record.id
    calls = []
    real = evidence_job_sync._reconcile
    monkeypatch.setattr(evidence_job_sync, "_reconcile", lambda db, jobs: calls.append(1) or real(db, jobs))

    job = dict(id=str(uuid4()), source_evidence_file_id=str(file_id), status="extracting_text")
    with Session() as db:
        evidence_job_sync.reconcile_case_poll(db, str(case_id), [job])
        evidence_job_sync.reconcile_case_poll(db, str(case_id), [dict(job)])
        assert len(calls) == 1
        evidence_job_sync.reconcile_case_poll(db, str(case_id), [dict(job, status="completed", entity_count=2)])
        assert len(calls) == 2
        assert db.get(EvidenceFile, file_id).status == "processed"

        monkeypatch.setattr(evidence_job_sync, "POLL_RECHECK_SECONDS", 0.0)
        evidence_job_sync.reconcile_case_poll(db, str(case_id), [dict(job, status="completed", entity_count=2)])
        assert len(calls) == 3


def test_poll_runs_again_while_a_record_was_left_for_later(monkeypatch):
    calls = []
    monkeypatch.setattr(evidence_job_sync, "_reconcile", lambda db, jobs: calls.append(1) or (0, False))
    db = SimpleNamespace(commit=lambda: None)
    jobs = [dict(id="j", status="completed")]
    evidence_job_sync.reconcile_case_poll(db, "case", jobs)
    evidence_job_sync.reconcile_case_poll(db, "case", jobs)
    assert len(calls) == 2


def test_list_engine_jobs_links_files_with_its_database_work_off_the_event_loop(Session, monkeypatch):
    from routers import evidence as router

    case_id = uuid4()
    job_id = str(uuid4())
    with Session() as db:
        linked = _file(case_id, job_id=job_id, status="processed")
        db.add(linked)
        db.add(_file(uuid4(), job_id=str(uuid4())))
        db.commit()
        file_id = linked.id

    loop_thread = []
    db_threads = []

    def check_access(db, case, user, required_permission):
        db_threads.append(threading.current_thread())

    async def list_jobs(case):
        loop_thread.append(threading.current_thread())
        return [dict(id=job_id, status="completed"), dict(id=str(uuid4()), status="pending")]

    import services.case_service as case_service

    monkeypatch.setattr(case_service, "check_case_access", check_access)
    monkeypatch.setattr(router, "USE_EVIDENCE_ENGINE", True)
    monkeypatch.setattr(router.evidence_engine_client, "list_jobs", list_jobs)

    with Session() as db:
        @event.listens_for(db.get_bind(), "before_cursor_execute")
        def _record_thread(*args):
            db_threads.append(threading.current_thread())

        answer = asyncio.run(router.list_engine_jobs(SimpleNamespace(headers={}), case_id=str(case_id),
                                                     current_user=SimpleNamespace(), db=db))
        body = json.loads(answer.body)

    assert [job["evidence_file_id"] for job in body] == [str(file_id), None]
    assert db_threads and loop_thread
    assert all(thread is not loop_thread[0] for thread in db_threads)
