"""A send that cannot go on says why and changes nothing; a stopped send leaves no file 'processing' (17 Nov 2026).

Tiryaki (3ae71ddf), 17 Nov: scripts/reprocess_failed_files.py waited 15 min on a row lock another transaction held
for over an hour (Postgres log: "still waiting for ShareLock ... after 910836 ms"), printed nothing, and was killed;
the second attempt got the lock, marked the file processing, and was killed before the engine had it, so the file
sat 'processing' with no engine job, off the failed list. Real session (SQLite); the engine is faked.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from postgres.models.evidence import EvidenceFile, IngestionLog
from services import evidence_processing_service as processing
from services import job_status_subscriber as subscriber_module
from tests.test_evidence_processing_chunks import FakeEngine, _files, _press, _rows


class _LockNotAvailable(Exception):
    sqlstate = "55P03"


def test_a_send_that_cannot_take_its_locks_says_why_and_marks_nothing(tmp_path):
    db, case_id, ids = _files(tmp_path, ["statement.pdf"])
    locked = OperationalError("SELECT ... FOR UPDATE", {}, _LockNotAvailable("canceling statement due to lock timeout"))

    with patch.object(processing, "_prepare_files", side_effect=locked), pytest.raises(HTTPException) as refused:
        _press(db, case_id, ids, FakeEngine())

    assert refused.value.status_code == 409 and refused.value.detail == processing.LOCKED_DETAIL
    assert _rows(db, ids)[0].status == "unprocessed"


def test_the_send_limits_its_lock_wait_on_postgres():
    statements = []

    class _Db(processing.Session):
        def __init__(self):
            pass

        def get_bind(self, *a, **k):
            return type("Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()})()

        def execute(self, statement, *a, **k):
            statements.append(str(statement))
            raise RuntimeError("stop after the lock statements")

    with pytest.raises(RuntimeError):
        processing._prepare_files(_Db(), case_id=None, file_ids=[], force_reprocess=False, preparation_mode="full",
                                  requested_by_user_id=None, ingestion_request_id="r")
    assert statements == [f"SET LOCAL lock_timeout = '{processing.SEND_LOCK_TIMEOUT}'"]


def test_a_send_stopped_before_the_engine_answers_puts_the_files_back(tmp_path):
    db, case_id, ids = _files(tmp_path, ["one.pdf", "two.pdf"])
    engine = FakeEngine()

    async def killed(**kwargs):
        raise KeyboardInterrupt  # what a kill of the script raises in the send (SIGTERM -> SystemExit likewise)

    engine.upload = killed
    with pytest.raises(KeyboardInterrupt):
        _press(db, case_id, ids, engine)

    rows = _rows(db, ids)
    assert [row.status for row in rows] == ["unprocessed", "unprocessed"]
    assert all(row.last_error == processing.NOT_SENT for row in rows)


def _left_processing(db, case_id, ids, *, request_id="req-1", minutes=45, source_type=None):
    for file_id in ids:
        row = db.get(EvidenceFile, file_id)
        row.status = "processing"
        row.engine_job_id = None
        row.source_type = source_type
        row.last_processed_profile_snapshot = {"ingestion_request_id": request_id}
        row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    db.commit()


class _Background:
    def __init__(self, db):
        self.db = db

    def __call__(self):
        return self

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


def _sweep(db, jobs):
    subscriber = subscriber_module.JobStatusSubscriber.__new__(subscriber_module.JobStatusSubscriber)
    subscriber._warned = set()
    with patch("postgres.session.get_background_session", new=_Background(db)), \
            patch("services.evidence_engine_client.list_jobs", new=AsyncMock(return_value=jobs)):
        return asyncio.run(subscriber._settle_unsent())


def test_a_file_marked_processing_and_never_sent_is_failed_with_the_reason(tmp_path):
    db, case_id, ids = _files(tmp_path, ["tiryaki.pdf"])
    _left_processing(db, case_id, ids)

    assert _sweep(db, jobs=[]) == []

    row = _rows(db, ids)[0]
    assert row.status == "failed" and row.last_error == subscriber_module._UNSENT_REASON
    assert db.query(IngestionLog).filter_by(evidence_file_id=row.id, level="error").count() == 1


def test_a_send_whose_answer_was_lost_gets_its_engine_job(tmp_path):
    db, case_id, ids = _files(tmp_path, ["tiryaki.pdf"])
    _left_processing(db, case_id, ids)
    jobs = [{"id": "job-9", "source_evidence_file_id": str(ids[0]), "pipeline_state": {"ingestion_request_id": "req-1"}},
            {"id": "job-old", "source_evidence_file_id": str(ids[0]), "pipeline_state": {"ingestion_request_id": "x"}}]

    assert _sweep(db, jobs) == [("job-9", str(case_id), None)]
    row = _rows(db, ids)[0]
    assert row.status == "processing" and row.engine_job_id == "job-9"


def test_a_recent_send_and_a_phone_report_being_read_are_left_alone(tmp_path):
    db, case_id, ids = _files(tmp_path, ["fresh.pdf", "phone.ufdr", "no-send.pdf"])
    _left_processing(db, case_id, ids[:1], minutes=5)
    _left_processing(db, case_id, ids[1:2], source_type="phone_extraction")
    _left_processing(db, case_id, ids[2:], request_id=None)

    assert _sweep(db, jobs=[]) == []
    assert [row.status for row in _rows(db, ids)] == ["processing"] * 3
