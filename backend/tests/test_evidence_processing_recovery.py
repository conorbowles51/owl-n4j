from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services import evidence_processing_service as processing


class FakeDb:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


class FakeSubscriber:
    def __init__(self) -> None:
        self.tracked: list[tuple[list[str], str]] = []

    async def track_jobs(self, job_ids: list[str], case_id: str) -> None:
        self.tracked.append((job_ids, case_id))


@pytest.mark.asyncio
async def test_process_files_recovers_jobs_when_upload_response_fails_after_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = uuid4()
    evidence_id = uuid4()
    engine_job_id = uuid4()
    stored_file = tmp_path / "report.pdf"
    stored_file.write_bytes(b"%PDF-test")
    evidence_file = SimpleNamespace(
        id=evidence_id,
        status="unprocessed",
        processing_stale=False,
        stored_path=str(stored_file),
        folder_id=None,
        original_filename="report.pdf",
        engine_job_id=None,
        last_error=None,
    )
    subscriber = FakeSubscriber()
    captured_metadata: list[dict] = []
    marked_failed: list[object] = []

    async def no_initial_reconciliation(db, requested_case_id: str) -> int:
        return 0

    async def accepted_but_response_failed(*, processing_metadata, **kwargs):
        captured_metadata.extend(processing_metadata)
        raise RuntimeError("500 after accepted upload")

    async def list_accepted_jobs(requested_case_id: str):
        assert requested_case_id == str(case_id)
        return [
            {
                "id": str(engine_job_id),
                "source_evidence_file_id": str(evidence_id),
                "status": "pending",
                "pipeline_state": {
                    "ingestion_request_id": captured_metadata[0]["ingestion_request_id"]
                },
            }
        ]

    def mark_processing(db, file_ids, force=False) -> None:
        evidence_file.status = "processing"

    def mark_processed(db, file_ids, error=None) -> None:
        marked_failed.extend(file_ids)

    monkeypatch.setattr(processing, "reconcile_case_jobs", no_initial_reconciliation)
    monkeypatch.setattr(
        processing.EvidenceDBStorage,
        "get_files_by_ids",
        lambda db, file_ids: [evidence_file],
    )
    monkeypatch.setattr(processing.EvidenceDBStorage, "mark_processing", mark_processing)
    monkeypatch.setattr(
        processing.EvidenceDBStorage,
        "set_processing_snapshot",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        processing,
        "build_processing_snapshot",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        processing.evidence_engine_client,
        "upload_file_paths_batch",
        accepted_but_response_failed,
    )
    monkeypatch.setattr(
        processing.evidence_engine_client,
        "list_jobs",
        list_accepted_jobs,
    )
    monkeypatch.setattr(processing.EvidenceDBStorage, "mark_processed", mark_processed)
    monkeypatch.setattr(processing, "get_subscriber", lambda: subscriber)

    result = await processing.process_db_files(
        FakeDb(),
        case_id=case_id,
        file_ids=[evidence_id],
    )

    assert result["job_ids"] == [str(engine_job_id)]
    assert result["file_count"] == 1
    assert evidence_file.engine_job_id == str(engine_job_id)
    assert evidence_file.status == "processing"
    assert marked_failed == []
    assert subscriber.tracked == [([str(engine_job_id)], str(case_id))]
