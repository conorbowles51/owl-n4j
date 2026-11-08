"""A Process press is sent in requests the engine accepts; one bad file fails alone (lx-chunking, 8 Nov 2026).

'SB4 - Pop & Locke': 250 files failed in one press on 28 Oct because their processing metadata, about 45 KB a file
(each lists the 365 files of its folder), made one form part of about 11 MB and the engine refuses a part over
1 MiB. The fake engine here applies that same limit and answers as the real one did. Real session (SQLite), real
files on disk; the engine and the job subscription are faked.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from services.evidence_failure_words import plain_failure
from services import evidence_processing_service as processing

PART_LIMIT = 1_048_576
SIBLINGS = [{"name": f"SB4 - Pop & Locke production volume 2 statement {i:03d}.pdf", "type": "application/pdf",
             "size": 123456, "id": str(uuid4())} for i in range(365)]  # about 45 KB a file, as SB4 measured


def _files(tmp_path, names, *, sha=None):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__,
                                             EvidenceFile.__table__, IngestionLog.__table__])
    db = Session(engine)
    case_id = uuid4()
    ids = []
    for index, name in enumerate(names):
        path = tmp_path / f"{index}-{name}"
        path.write_text("same bytes" if sha else f"file {index}")
        record = EvidenceFile(case_id=case_id, original_filename=name, stored_path=str(path),
                              sha256=(sha or f"{index:064d}"))
        db.add(record)
        db.flush()
        ids.append(record.id)
    db.commit()
    return db, case_id, ids


class FakeEngine:
    """The engine's answers: a part over 1 MiB, or a named file, is refused (400) and nothing is created."""

    def __init__(self, *, refuse_names=(), fail_on_request=None) -> None:
        self.requests: list[dict] = []
        self.closed: list[str] = []
        self.refuse_names = set(refuse_names)
        self.fail_on_request = fail_on_request
        self.count = 0

    @staticmethod
    def _refuse(detail):
        request = httpx.Request("POST", "http://engine/cases/x/files")
        response = httpx.Response(400, json={"detail": detail}, request=request)
        raise httpx.HTTPStatusError(f"Client error '400 Bad Request' for url '{request.url}'", request=request,
                                    response=response)

    async def upload(self, *, case_id, files, processing_metadata, batch_id=None):
        self.count += 1
        if self.fail_on_request == self.count:
            raise httpx.ConnectError("All connection attempts failed")
        if len(json.dumps(processing_metadata)) > PART_LIMIT:
            self._refuse("Part exceeded maximum size of 1024KB.")
        if any(name in self.refuse_names for name, _path, _type in files):
            self._refuse("Invalid upload filename")
        self.requests.append({"batch_id": batch_id, "files": [name for name, _p, _t in files],
                              "bytes": len(json.dumps(processing_metadata))})
        return [{"id": f"job-{self.count}-{i}"} for i in range(len(files))]

    async def close(self, case_id, batch_id):
        self.closed.append(batch_id)
        return {"closed": True}


def _press(db, case_id, ids, engine):
    subscriber = type("Subscriber", (), {"track_jobs": AsyncMock()})()
    with patch.object(processing, "build_processing_snapshot", return_value={"sibling_files": SIBLINGS}), \
            patch.object(processing, "reconcile_case_jobs", new=AsyncMock()), \
            patch.object(processing.evidence_engine_client, "upload_file_paths_batch", new=engine.upload), \
            patch.object(processing.evidence_engine_client, "close_batch", new=engine.close, create=True), \
            patch.object(processing.evidence_engine_client, "list_jobs", new=AsyncMock(return_value=[])), \
            patch.object(processing, "get_subscriber", return_value=subscriber):
        return asyncio.run(processing.process_db_files(db, case_id=case_id, file_ids=ids))


def _rows(db, ids):
    db.expire_all()
    return [db.get(EvidenceFile, i) for i in ids]


def test_a_260_file_press_is_accepted_and_every_file_queued(tmp_path):
    db, case_id, ids = _files(tmp_path, [f"SB4 statement {i:03d}.pdf" for i in range(260)])
    engine = FakeEngine()

    result = _press(db, case_id, ids, engine)

    assert result["sent_count"] == result["total_count"] == result["file_count"] == 260
    assert len(result["job_ids"]) == 260 and "refused" not in result
    assert result["message"] == "Processing 260 file(s)" and result["request_count"] == len(engine.requests) > 1
    assert max(r["bytes"] for r in engine.requests) < PART_LIMIT
    batch_ids = {r["batch_id"] for r in engine.requests}
    assert len(batch_ids) == 1 and None not in batch_ids and engine.closed == list(batch_ids)
    assert all(row.status == "processing" and row.engine_job_id for row in _rows(db, ids))


def test_a_press_with_one_refused_file_leaves_the_others_queued(tmp_path):
    names = [f"statement {i:02d}.pdf" for i in range(30)]
    names[17] = "bad.pdf"
    db, case_id, ids = _files(tmp_path, names)
    engine = FakeEngine(refuse_names={"bad.pdf"})

    result = _press(db, case_id, ids, engine)

    rows = _rows(db, ids)
    assert result["sent_count"] == 29 and result["total_count"] == 30
    assert [r["name"] for r in result["refused"]] == ["bad.pdf"]
    assert "Invalid upload filename" in result["refused"][0]["reason"]
    assert rows[17].status == "failed" and "Invalid upload filename" in rows[17].last_error
    assert all(row.status == "processing" and row.engine_job_id for i, row in enumerate(rows) if i != 17)
    assert len({r["batch_id"] for r in engine.requests}) == 1 and len(engine.closed) == 1


def test_two_identical_files_in_different_chunks_are_read_in_one_engine_batch(tmp_path):
    # The engine deduplicates the files of one batch together; the press's chunks are one open batch, closed once.
    db, case_id, ids = _files(tmp_path, [f"copy {i:02d}.pdf" for i in range(40)], sha="d" * 64)
    engine = FakeEngine()

    _press(db, case_id, ids, engine)

    first, last = engine.requests[0], engine.requests[-1]
    assert "copy 00.pdf" in first["files"] and "copy 39.pdf" in last["files"] and first is not last
    assert first["batch_id"] == last["batch_id"] and engine.closed == [first["batch_id"]]


def test_a_failed_request_leaves_the_files_it_did_not_try_not_processed(tmp_path):
    db, case_id, ids = _files(tmp_path, [f"statement {i:03d}.pdf" for i in range(60)])
    engine = FakeEngine(fail_on_request=2)

    result = _press(db, case_id, ids, engine)

    rows = _rows(db, ids)
    first = len(engine.requests[0]["files"])
    assert [row.status for row in rows[:first]] == ["processing"] * first
    failed = [row for row in rows if row.status == "failed"]
    assert failed and all("could not be reached" in plain_failure(r.last_error) for r in failed)
    not_sent = [row for row in rows if row.status == "unprocessed"]
    assert len(not_sent) == 60 - first - len(failed) > 0
    assert all(row.last_error == processing.NOT_SENT for row in not_sent)
    assert result["sent_count"] == first and "not sent" in result["message"]
    assert engine.closed == [engine.requests[0]["batch_id"]]


def test_a_refused_single_request_is_split_into_one_engine_batch(tmp_path):
    # 20 files fit one request by count but not by bytes once their lists are large: the halves share one batch.
    db, case_id, ids = _files(tmp_path, [f"statement {i:02d}.pdf" for i in range(4)])
    engine = FakeEngine(refuse_names={"statement 02.pdf"})

    result = _press(db, case_id, ids, engine)

    assert result["sent_count"] == 3 and result["request_count"] == 1
    assert len({r["batch_id"] for r in engine.requests}) == 1 and None not in {r["batch_id"] for r in engine.requests}
    assert engine.closed == [engine.requests[0]["batch_id"]]


def test_a_one_request_press_is_sent_as_before(tmp_path):
    db, case_id, ids = _files(tmp_path, ["one.pdf", "two.pdf"])
    engine = FakeEngine()
    result = _press(db, case_id, ids, engine)
    assert result["message"] == "Processing 2 file(s)" and [r["batch_id"] for r in engine.requests] == [None]
    assert engine.closed == []
