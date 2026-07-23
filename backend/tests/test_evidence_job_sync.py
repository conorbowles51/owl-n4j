import asyncio
from types import SimpleNamespace
from uuid import uuid4

from services import evidence_job_sync
from services.evidence_job_sync import reconcile_job_by_id, reconcile_jobs_payload


class FakeScalarResult:
    def __init__(self, records) -> None:
        self.records = records

    def all(self):
        return self.records


class FakeDb:
    def __init__(self, records) -> None:
        self.records = records
        self.flush_count = 0
        self.commit_count = 0

    def scalars(self, statement):
        return FakeScalarResult(self.records)

    def flush(self) -> None:
        self.flush_count += 1

    def commit(self) -> None:
        self.commit_count += 1


def _evidence_record(evidence_id, engine_job_id=None):
    return SimpleNamespace(
        id=evidence_id,
        engine_job_id=str(engine_job_id) if engine_job_id else None,
        status="failed",
        last_error="old failure",
        processing_stale=False,
        processed_at=None,
        summary=None,
        transcription=None,
        entity_count=None,
        relationship_count=None,
    )


def test_reconcile_jobs_repairs_missing_engine_link_from_source_evidence_id() -> None:
    evidence_id = uuid4()
    engine_job_id = uuid4()
    record = _evidence_record(evidence_id)
    record.last_error = "500 after accepted upload"
    db = FakeDb([record])

    updated = reconcile_jobs_payload(
        db,
        [
            {
                "id": str(engine_job_id),
                "source_evidence_file_id": str(evidence_id),
                "status": "completed",
                "document_summary": "Comprehensive recovered summary",
                "transcription": None,
                "entity_count": 9,
                "relationship_count": 12,
            }
        ],
    )

    assert updated == 1
    assert record.engine_job_id == str(engine_job_id)
    assert record.status == "processed"
    assert record.last_error is None
    assert record.summary == "Comprehensive recovered summary"
    assert record.entity_count == 9
    assert record.relationship_count == 12
    assert db.flush_count == 1


def test_reconcile_jobs_ignores_older_failed_attempt_for_same_file() -> None:
    evidence_id = uuid4()
    failed_job_id = uuid4()
    completed_job_id = uuid4()
    record = _evidence_record(evidence_id, failed_job_id)
    record.last_error = "OCR failed: Tesseract process timeout"
    db = FakeDb([record])

    updated = reconcile_jobs_payload(
        db,
        [
            {
                "id": str(completed_job_id),
                "source_evidence_file_id": str(evidence_id),
                "status": "completed",
                "created_at": "2026-07-23T00:37:01.121498Z",
                "document_summary": "Successful reprocessing summary",
                "entity_count": 166,
                "relationship_count": 122,
            },
            {
                "id": str(failed_job_id),
                "source_evidence_file_id": str(evidence_id),
                "status": "failed",
                "created_at": "2026-07-22T20:07:42.091961Z",
                "error_message": "OCR failed: Tesseract process timeout",
                "entity_count": 0,
                "relationship_count": 0,
            },
        ],
    )

    assert updated == 1
    assert record.engine_job_id == str(completed_job_id)
    assert record.status == "processed"
    assert record.last_error is None
    assert record.summary == "Successful reprocessing summary"
    assert record.entity_count == 166
    assert record.relationship_count == 122
    assert record.processed_at is not None
    assert db.flush_count == 1


def test_reconcile_jobs_uses_created_at_when_payload_is_not_newest_first() -> None:
    evidence_id = uuid4()
    failed_job_id = uuid4()
    completed_job_id = uuid4()
    record = _evidence_record(evidence_id, failed_job_id)
    db = FakeDb([record])

    reconcile_jobs_payload(
        db,
        [
            {
                "id": str(failed_job_id),
                "source_evidence_file_id": str(evidence_id),
                "status": "failed",
                "created_at": "2026-07-22T20:07:42.091961",
                "error_message": "old failure",
            },
            {
                "id": str(completed_job_id),
                "source_evidence_file_id": str(evidence_id),
                "status": "completed",
                "created_at": "2026-07-23T00:37:01.121498",
                "document_summary": "new success",
            },
        ],
    )

    assert record.engine_job_id == str(completed_job_id)
    assert record.status == "processed"
    assert record.summary == "new success"


def test_reconcile_old_job_detail_uses_latest_case_attempt(monkeypatch) -> None:
    evidence_id = uuid4()
    failed_job_id = uuid4()
    completed_job_id = uuid4()
    case_id = str(uuid4())
    record = _evidence_record(evidence_id, completed_job_id)
    record.status = "processed"
    record.last_error = None
    record.summary = "new success"
    db = FakeDb([record])

    failed_job = {
        "id": str(failed_job_id),
        "case_id": case_id,
        "source_evidence_file_id": str(evidence_id),
        "status": "failed",
        "created_at": "2026-07-22T20:07:42.091961Z",
        "error_message": "old failure",
    }
    completed_job = {
        "id": str(completed_job_id),
        "case_id": case_id,
        "source_evidence_file_id": str(evidence_id),
        "status": "completed",
        "created_at": "2026-07-23T00:37:01.121498Z",
        "document_summary": "new success",
    }

    async def fake_get_job(job_id):
        assert job_id == str(failed_job_id)
        return failed_job

    async def fake_list_jobs(requested_case_id):
        assert requested_case_id == case_id
        return [completed_job, failed_job]

    monkeypatch.setattr(
        evidence_job_sync.evidence_engine_client, "get_job", fake_get_job
    )
    monkeypatch.setattr(
        evidence_job_sync.evidence_engine_client, "list_jobs", fake_list_jobs
    )

    returned = asyncio.run(reconcile_job_by_id(db, str(failed_job_id)))

    assert returned == failed_job
    assert record.engine_job_id == str(completed_job_id)
    assert record.status == "processed"
    assert record.last_error is None
    assert record.summary == "new success"
    assert db.commit_count == 1
