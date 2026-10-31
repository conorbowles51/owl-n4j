"""process_db_files (every Evidence and Financial send to the engine) keeps its database work in the thread pool:
on the event loop it stalled every other request in the worker. A real session, the engine and the job subscription
faked; every path must leave the same rows and run no SQL on the event-loop thread."""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from services import evidence_processing_service as processing


@pytest.fixture()
def world(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__,
                                             EvidenceFile.__table__, IngestionLog.__table__])
    db = Session(engine)
    case_id = uuid4()
    files = []
    for index in range(2):
        path = tmp_path / f"f{index}.txt"
        path.write_text("x")
        record = EvidenceFile(case_id=case_id, original_filename=path.name, stored_path=str(path), sha256="a" * 64)
        db.add(record)
        files.append(record)
    db.commit()
    loop_sql = []
    watching = threading.Event()

    @event.listens_for(engine, "before_cursor_execute")
    def _on_the_loop(conn, cursor, statement, *rest):
        if watching.is_set() and threading.current_thread() is threading.main_thread():
            loop_sql.append(statement.split("\n")[0][:80])

    yield db, case_id, [f.id for f in files], loop_sql, watching
    db.close()
    engine.dispose()


def _send(db, case_id, file_ids, watching, *, upload, list_jobs=None):
    subscriber = type("Subscriber", (), {"track_jobs": AsyncMock()})()
    watching.set()
    try:
        with patch.object(processing, "build_processing_snapshot", return_value={}), \
                patch.object(processing, "reconcile_case_jobs", new=AsyncMock()), \
                patch.object(processing.evidence_engine_client, "upload_file_paths_batch", new=upload), \
                patch.object(processing.evidence_engine_client, "list_jobs", new=list_jobs or AsyncMock(return_value=[])), \
                patch.object(processing, "get_subscriber", return_value=subscriber):
            return asyncio.run(processing.process_db_files(db, case_id=case_id, file_ids=file_ids)), subscriber
    finally:
        watching.clear()


def test_a_send_records_its_jobs_without_sql_on_the_event_loop(world):
    db, case_id, file_ids, loop_sql, watching = world

    async def upload(**kwargs):
        return [{"id": f"job{i}"} for i in range(len(kwargs["files"]))]

    result, subscriber = _send(db, case_id, file_ids, watching, upload=upload)
    assert result["job_ids"] == ["job0", "job1"] and result["file_count"] == 2
    assert [(db.get(EvidenceFile, i).status, db.get(EvidenceFile, i).engine_job_id) for i in file_ids] == [
        ("processing", "job0"), ("processing", "job1")]
    subscriber.track_jobs.assert_awaited_once_with(["job0", "job1"], str(case_id))
    assert loop_sql == []


def test_a_failed_upload_marks_the_files_and_raises_the_same_error_without_sql_on_the_loop(world):
    db, case_id, file_ids, loop_sql, watching = world
    boom = RuntimeError("upload boom")

    async def upload(**kwargs):
        raise boom

    with pytest.raises(RuntimeError) as raised:
        _send(db, case_id, file_ids, watching, upload=upload)
    assert raised.value is boom
    assert [(db.get(EvidenceFile, i).status, db.get(EvidenceFile, i).last_error) for i in file_ids] == [
        ("failed", "upload boom"), ("failed", "upload boom")]
    assert loop_sql == []


def test_jobs_the_engine_accepted_before_the_upload_reply_failed_are_recovered_without_sql_on_the_loop(world):
    db, case_id, file_ids, loop_sql, watching = world
    request = {}

    async def upload(**kwargs):
        request["id"] = kwargs["processing_metadata"][0]["ingestion_request_id"]
        raise RuntimeError("reply lost")

    async def list_jobs(case):
        return [{"id": f"r{i}", "source_evidence_file_id": str(file_id),
                 "pipeline_state": {"ingestion_request_id": request["id"]}} for i, file_id in enumerate(file_ids)]

    result, _ = _send(db, case_id, file_ids, watching, upload=upload, list_jobs=list_jobs)
    assert result["recovered_after_response_error"] is True and result["job_ids"] == ["r0", "r1"]
    assert [db.get(EvidenceFile, i).engine_job_id for i in file_ids] == ["r0", "r1"]
    assert loop_sql == []


def test_files_missing_on_disk_are_reported_and_nothing_is_sent(world, tmp_path):
    db, case_id, file_ids, loop_sql, watching = world
    for path in tmp_path.glob("f*.txt"):
        path.unlink()
    upload = AsyncMock()
    result, _ = _send(db, case_id, file_ids, watching, upload=upload)
    assert result["message"] == "No files found on disk" and result["missing_on_disk"] == 2
    upload.assert_not_awaited()
    assert loop_sql == []
