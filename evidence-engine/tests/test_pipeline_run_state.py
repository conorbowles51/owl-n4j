from datetime import UTC, datetime, timedelta

from types import SimpleNamespace

import pytest

from app.services import chunk_publication
from app.models.job import JobStatus
from app.services.pipeline_run_state import (
    build_extraction_quality_report,
    transition_batch_dispatch,
    transition_chunk_publication,
    transition_pipeline_state,
)


def test_stage_progress_is_durable_without_counting_progress_updates_as_retries() -> None:
    started = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    state = transition_pipeline_state(
        {},
        stage="extracting_text",
        message="Extracting text",
        now=started,
    )
    state = transition_pipeline_state(
        state,
        stage="extracting_text",
        message="OCR page 5 of 20",
        now=started + timedelta(seconds=30),
    )
    state = transition_pipeline_state(
        state,
        stage="chunking",
        message="Chunking document",
        now=started + timedelta(seconds=45),
    )

    assert state["current_stage"] == "chunking"
    assert state["stages"]["extracting_text"]["attempt_count"] == 1
    assert state["stages"]["extracting_text"]["attempts"][0]["status"] == "completed"
    assert state["stages"]["extracting_text"]["attempts"][0]["duration_ms"] == 45000
    assert state["stages"]["chunking"]["attempt_count"] == 1
    assert state["last_message"] == "Chunking document"


def test_failure_is_attached_to_the_stage_that_failed() -> None:
    started = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    state = transition_pipeline_state(
        {},
        stage="extracting_entities",
        message="Extracting entities",
        now=started,
    )
    state = transition_pipeline_state(
        state,
        stage="failed",
        message="Model response invalid",
        error="schema validation failed",
        now=started + timedelta(seconds=12),
    )

    attempt = state["stages"]["extracting_entities"]["attempts"][0]
    assert attempt["status"] == "failed"
    assert attempt["error"] == "schema validation failed"
    assert attempt["duration_ms"] == 12000
    assert state["current_stage"] == "failed"


def test_quality_report_exposes_grounding_and_ocr_risk() -> None:
    entity = SimpleNamespace(
        source_location={"page_start": 1},
        verified_facts=[{"source_location": {"page_start": 1}}],
        confidence=0.9,
    )
    relationship = SimpleNamespace(source_location=None, confidence=0.7)

    report = build_extraction_quality_report(
        entities=[entity],
        relationships=[relationship],
        chunk_count=3,
        document_metadata={
            "ocr_low_confidence_pages": 2,
            "page_count": 10,
            "document_summary_status": "failed",
        },
    )

    assert report["status"] == "warning"
    assert report["grounding"]["grounded_records"] == 2
    assert report["grounding"]["total_records"] == 3
    assert report["grounding"]["coverage"] == 0.6667
    assert report["ocr"]["low_confidence_pages"] == 2
    assert "ungrounded_records" in report["warnings"]
    assert "low_confidence_ocr" in report["warnings"]
    assert "document_summary_failed" in report["warnings"]
    assert report["document_summary"]["status"] == "failed"


def test_chunk_publication_state_is_a_retryable_outbox_record() -> None:
    now = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    state = transition_chunk_publication(
        {},
        publication_state="staged",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        file_name="Report.pdf",
        now=now,
    )
    state = transition_chunk_publication(
        state,
        publication_state="ready",
        now=now + timedelta(seconds=2),
    )
    state = transition_chunk_publication(
        state,
        publication_state="publishing",
        now=now + timedelta(seconds=3),
    )
    state = transition_chunk_publication(
        state,
        publication_state="retry",
        error="ChromaDB unavailable",
        now=now + timedelta(seconds=4),
    )

    publication = state["chunk_publication"]
    assert publication["state"] == "retry"
    assert publication["attempt_count"] == 1
    assert publication["evidence_file_id"] == "evidence-1"
    assert publication["last_error"] == "ChromaDB unavailable"


def test_batch_dispatch_state_is_a_retryable_outbox_record() -> None:
    now = datetime(2026, 7, 21, 10, 0, tzinfo=UTC)
    state = transition_batch_dispatch(
        {},
        dispatch_state="ready",
        batch_id="batch-1",
        case_id="case-1",
        now=now,
    )
    state = transition_batch_dispatch(
        state,
        dispatch_state="dispatching",
        now=now + timedelta(seconds=1),
    )
    state = transition_batch_dispatch(
        state,
        dispatch_state="retry",
        error="Redis unavailable",
        now=now + timedelta(seconds=2),
    )

    dispatch = state["batch_dispatch"]
    assert dispatch["state"] == "retry"
    assert dispatch["attempt_count"] == 1
    assert dispatch["batch_id"] == "batch-1"
    assert dispatch["case_id"] == "case-1"
    assert dispatch["last_error"] == "Redis unavailable"


@pytest.mark.asyncio
async def test_ready_publication_is_activated_then_marked_published(monkeypatch) -> None:
    state = transition_chunk_publication(
        {},
        publication_state="staged",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        file_name="Report.pdf",
    )
    state = transition_chunk_publication(state, publication_state="ready")
    job = SimpleNamespace(id="job-1", case_id="case-1", pipeline_state=state)
    commits: list[str] = []
    activations: list[dict] = []

    class FakeDb:
        async def commit(self) -> None:
            commits.append(job.pipeline_state["chunk_publication"]["state"])

    async def fake_activate(**kwargs):
        activations.append(kwargs)
        return SimpleNamespace(activated_count=2, retired_count=1)

    monkeypatch.setattr(chunk_publication, "activate_chunk_revision", fake_activate)

    result = await chunk_publication.publish_chunk_revision(job, FakeDb())

    assert result.activated_count == 2
    assert activations == [
        {
            "case_id": "case-1",
            "evidence_file_id": "evidence-1",
            "revision_id": "revision-1",
            "file_name": "Report.pdf",
        }
    ]
    assert commits == ["publishing", "published"]
    assert job.pipeline_state["chunk_publication"]["state"] == "published"


@pytest.mark.asyncio
async def test_recovered_publication_finalizes_unfinished_job(monkeypatch) -> None:
    state = transition_chunk_publication(
        {},
        publication_state="staged",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        file_name="Report.pdf",
    )
    state = transition_chunk_publication(state, publication_state="ready")
    state = transition_chunk_publication(state, publication_state="published")
    job = SimpleNamespace(
        id="job-1",
        case_id="case-1",
        status=JobStatus.WRITING_GRAPH,
        progress=0.9,
        pipeline_state=state,
        entity_count=3,
        relationship_count=2,
        document_summary="summary",
    )
    commits = []
    events = []

    class FakeDb:
        async def commit(self) -> None:
            commits.append(job.status)

    async def fake_publish(_channel: str, payload: dict) -> None:
        events.append(payload)

    monkeypatch.setattr(chunk_publication, "publish_progress", fake_publish)

    finalized = await chunk_publication.finalize_published_job(job, FakeDb())

    assert finalized is True
    assert job.status is JobStatus.COMPLETED
    assert job.progress == 1.0
    assert job.pipeline_state["current_stage"] == "completed"
    assert commits == [JobStatus.COMPLETED]
    assert events[0]["entity_count"] == 3
