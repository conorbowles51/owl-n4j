from types import SimpleNamespace
from uuid import uuid4

from services.evidence_job_sync import reconcile_jobs_payload


class FakeScalarResult:
    def __init__(self, records) -> None:
        self.records = records

    def all(self):
        return self.records


class FakeDb:
    def __init__(self, records) -> None:
        self.records = records
        self.flush_count = 0

    def scalars(self, statement):
        return FakeScalarResult(self.records)

    def flush(self) -> None:
        self.flush_count += 1


def test_reconcile_jobs_repairs_missing_engine_link_from_source_evidence_id() -> None:
    evidence_id = uuid4()
    engine_job_id = uuid4()
    record = SimpleNamespace(
        id=evidence_id,
        engine_job_id=None,
        status="failed",
        last_error="500 after accepted upload",
        processing_stale=False,
        processed_at=None,
        summary=None,
        transcription=None,
        entity_count=None,
        relationship_count=None,
    )
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
