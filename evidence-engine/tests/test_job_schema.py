import uuid
from datetime import datetime, timezone

from app.models.job import JobStatus
from app.schemas.job import JobResponse


def test_job_response_exposes_source_evidence_file_id_for_upload_recovery() -> None:
    source_id = uuid.uuid4()

    response = JobResponse(
        id=uuid.uuid4(),
        case_id=str(uuid.uuid4()),
        source_evidence_file_id=source_id,
        status=JobStatus.PENDING,
        progress=0,
        error_message=None,
        entity_count=0,
        relationship_count=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert response.source_evidence_file_id == source_id
    assert response.model_dump()["source_evidence_file_id"] == source_id
