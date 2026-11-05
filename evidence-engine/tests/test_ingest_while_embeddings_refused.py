"""An ingestion survives the embedding service refusing (lx-ingestpending)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import uuid

import httpx
import openai
import pytest

from app.models.job import JobStatus
from app.pipeline import batch_orchestrator, chunk_embed, orchestrator, resolve_entities, write_graph
from app.pipeline.extract_text import ExtractedDocument
from app.services import embedding_refusal
from app.services.embedding_refusal import ENTITY_VECTORS_PENDING, is_embedding_refusal, start_collecting_skipped


def quota_error() -> openai.RateLimitError:
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    return openai.RateLimitError("You have no credits remaining", response=response, body=None)


def bad_request() -> openai.BadRequestError:
    response = httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
    return openai.BadRequestError("malformed input", response=response, body=None)


async def refused(_texts: list[str], **_kwargs: object) -> list[list[float]]:
    raise quota_error()


def document(text: str = "Marcus Chen approved the invoice.") -> ExtractedDocument:
    return ExtractedDocument(text=text, tables=[], metadata={"file_type": "txt"})


async def value(result: object) -> object:
    return result


def test_only_a_provider_failure_counts_as_a_refusal() -> None:
    assert is_embedding_refusal(quota_error())
    assert is_embedding_refusal(ValueError("OpenAI is not connected. Add its API key in Settings"))
    assert not is_embedding_refusal(bad_request())
    assert not is_embedding_refusal(RuntimeError("OpenAI embedding request is too large"))
    assert not is_embedding_refusal(ValueError("a bug"))


@pytest.mark.asyncio
async def test_refused_chunks_are_kept_with_text_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    kept: dict[str, object] = {}

    async def store(**kwargs: object) -> int:
        kept.update(kwargs)
        return 1

    collection = SimpleNamespace(get=lambda **_kwargs: {"ids": [], "metadatas": []})
    monkeypatch.setattr(chunk_embed, "embed_texts", refused)
    monkeypatch.setattr(chunk_embed, "store_pending_chunks", store)
    monkeypatch.setattr(chunk_embed, "get_or_create_collection", lambda _name: collection)
    monkeypatch.setattr(chunk_embed, "upsert_embeddings", lambda **_kwargs: pytest.fail("no vector to store"))

    chunks = await chunk_embed.chunk_and_embed(
        document(), "case-1", "job-1", "Board Minutes.txt", evidence_file_id="file-1", revision_id="rev-1",
    )

    assert [chunk.metadata["vector_pending"] for chunks_ in [chunks] for chunk in chunks_] == [True]
    assert kept["ids"] == ["file-1:rev-1:chunk:0"]
    assert kept["texts"] == ["Marcus Chen approved the invoice."]
    assert kept["metadatas"][0]["doc_key"] == "board-minutestxt"  # type: ignore[index]
    assert "no credits" in str(kept["reason"])


@pytest.mark.asyncio
async def test_a_real_embedding_error_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(_texts: list[str]) -> list[list[float]]:
        raise bad_request()

    monkeypatch.setattr(chunk_embed, "embed_texts", broken)
    with pytest.raises(openai.BadRequestError):
        await chunk_embed.chunk_and_embed(document(), "case-1", "job-1", "a.txt", revision_id="rev-1")


@pytest.mark.asyncio
async def test_a_repeat_of_a_published_transcript_keeps_it_and_waits_for_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored: list[object] = []

    async def store(**kwargs: object) -> int:
        stored.extend(kwargs["ids"])  # type: ignore[arg-type]
        return 0

    chunk_id = "file-1:rev-1:chunk:0"
    collection = SimpleNamespace(get=lambda **_kwargs: {"ids": [chunk_id], "metadatas": [
        {"case_id": "case-1", "evidence_file_id": "file-1", "revision_id": "rev-1", "ingestion_state": "active"}]})
    monkeypatch.setattr(chunk_embed, "embed_texts", refused)
    monkeypatch.setattr(chunk_embed, "store_pending_chunks", store)
    monkeypatch.setattr(chunk_embed, "get_or_create_collection", lambda _name: collection)

    chunks = await chunk_embed.chunk_and_embed(
        document(), "case-1", "job-1", "a.txt", evidence_file_id="file-1", revision_id="rev-1",
    )

    assert stored == []
    assert "vector_pending" not in chunks[0].metadata


@pytest.mark.asyncio
async def test_refused_entity_vectors_are_marked_inside_the_graph_write(monkeypatch: pytest.MonkeyPatch) -> None:
    writes: list[tuple[str, dict]] = []

    async def write(query: str, parameters: dict) -> None:
        writes.append((query, parameters))

    monkeypatch.setattr(write_graph, "embed_texts", refused)
    requested: list[bool] = []

    async def request_backfill() -> None:
        requested.append(True)

    monkeypatch.setattr(write_graph, "_checkpointed_graph_write", write)
    monkeypatch.setattr(write_graph, "request_gap_backfill", request_backfill)
    entity = SimpleNamespace(
        id="e-1", category="Person", name="Marcus Chen", properties={}, aliases=[], verified_facts=[], specific_type="",
    )
    skipped = start_collecting_skipped()

    await write_graph._embed_entities([entity], "case-1")  # type: ignore[list-item]

    assert "vector_pending = true" in writes[0][0]
    assert writes[0][1] == {"ids": ["e-1"], "case_id": "case-1"}
    assert skipped == [ENTITY_VECTORS_PENDING]
    assert requested == [True]


@pytest.mark.asyncio
async def test_a_real_error_embedding_entities_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(_texts: list[str]) -> list[list[float]]:
        raise bad_request()

    monkeypatch.setattr(write_graph, "embed_texts", broken)
    entity = SimpleNamespace(
        id="e-1", category="Person", name="M", properties={}, aliases=[], verified_facts=[], specific_type="",
    )
    with pytest.raises(openai.BadRequestError):
        await write_graph._embed_entities([entity], "case-1")  # type: ignore[list-item]


@pytest.mark.asyncio
async def test_dedup_within_the_run_goes_on_without_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def refuse_counted(texts: list[str]) -> list[list[float]]:
        calls.append(texts)
        raise quota_error()

    monkeypatch.setattr(resolve_entities, "embed_texts", refuse_counted)
    people = [SimpleNamespace(category="Person", name=name, properties={}) for name in ("Ann", "Anne")]
    places = [SimpleNamespace(category="Location", name=name, properties={}) for name in ("Rome", "Roma")]
    skipped = start_collecting_skipped()

    pairs = await resolve_entities._embedding_candidates(people + places, set())  # type: ignore[arg-type]

    assert pairs == []
    assert len(calls) == 1  # one refused call, not one per category
    assert skipped == [embedding_refusal.ENTITY_DEDUP_SKIPPED]


def _job(job_id: uuid.UUID, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=job_id, created_at=None, status=JobStatus.PENDING, file_path=name, file_name=name, llm_profile="",
        folder_context=None, sibling_files=None, effective_context=None, effective_mandatory_instructions=[],
        effective_special_entity_types=[], requested_by_user_id=None, source_evidence_file_id=None,
        case_id="case-1", pipeline_state={}, progress=0.0, quality_report=None, job_type="ingestion",
        document_summary=None, transcription=None, transcription_segments=None, entity_count=None,
        relationship_count=None,
    )


@pytest.mark.asyncio
async def test_429_at_stage_2_completes_the_job_with_entities(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _job(uuid.uuid4(), "notes.txt")
    published: list[object] = []

    class FakeResult:
        def scalar_one(self) -> object:
            return job

    class FakeDb:
        async def execute(self, _query: object) -> FakeResult:
            return FakeResult()

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

    @asynccontextmanager
    async def cost_context(**_kwargs: object):
        yield

    async def update(the_job: object, status: JobStatus, progress: float, _db: object, *_a: object, **_k: object) -> None:
        the_job.status = status  # type: ignore[attr-defined]

    async def no_op(*_args: object, **_kwargs: object) -> None:
        return None

    async def store(**_kwargs: object) -> int:
        return 1

    async def ingestion_document(*_args: object, **_kwargs: object) -> ExtractedDocument:
        return document()

    async def extract(chunks: list, *_args: object, **_kwargs: object) -> tuple[list, list]:
        assert chunks, "entity extraction reads the kept chunks"
        return ["raw"], []

    async def pair(entities: list, relationships: list, *_a: object, **_k: object) -> tuple[list, list]:
        return entities, relationships

    async def first(items: list, *_a: object) -> list:
        return items

    async def publish(the_job: object, _db: object) -> None:
        published.append(the_job)

    from app.pipeline import audio_review
    from app.services import graph_identity

    monkeypatch.setattr(orchestrator, "load_ai_model_policy", no_op)
    monkeypatch.setattr(orchestrator, "get_ai_runtime_snapshot", lambda: {})
    monkeypatch.setattr(orchestrator, "detect_financial_route", lambda _path: SimpleNamespace(
        is_native=False, as_state=lambda: {}))
    monkeypatch.setattr(graph_identity, "ensure_identity_indexes", no_op)
    monkeypatch.setattr(orchestrator, "ingestion_cost_context", cost_context)
    monkeypatch.setattr(orchestrator, "_update_job", update)
    monkeypatch.setattr(orchestrator, "publish_progress", no_op)
    monkeypatch.setattr(audio_review, "ingestion_document", ingestion_document)
    monkeypatch.setattr(orchestrator, "get_transcription", lambda _doc: None)
    monkeypatch.setattr(orchestrator, "get_transcription_segments", lambda _doc: None)
    monkeypatch.setattr(orchestrator, "generate_document_summary", lambda *_a, **_k: value("A summary"))
    monkeypatch.setattr(chunk_embed, "embed_texts", refused)
    monkeypatch.setattr(chunk_embed, "store_pending_chunks", store)
    monkeypatch.setattr(chunk_embed, "get_or_create_collection", lambda _name: SimpleNamespace(
        get=lambda **_kwargs: {"ids": [], "metadatas": []}))
    monkeypatch.setattr(orchestrator, "extract_entities_and_relationships", extract)
    monkeypatch.setattr(orchestrator, "build_extraction_quality_report", lambda **_k: {"warnings": []})
    monkeypatch.setattr(orchestrator, "consolidate_entities", pair)
    monkeypatch.setattr(orchestrator, "resolve_entities", pair)
    monkeypatch.setattr(orchestrator, "resolve_relationships", first)
    monkeypatch.setattr(orchestrator, "link_transaction_parties", lambda _e, relationships: relationships)
    monkeypatch.setattr(orchestrator, "generate_summaries", first)
    monkeypatch.setattr(orchestrator, "write_graph", no_op)
    monkeypatch.setattr(orchestrator, "publish_chunk_revision", publish)
    monkeypatch.setattr(orchestrator.settings, "claim_verification_enabled", False)

    await orchestrator.run_pipeline(str(job.id), FakeDb())  # type: ignore[arg-type]

    assert job.status == JobStatus.COMPLETED
    assert job.entity_count == 1
    assert job.document_summary == "A summary"
    assert published == [job]
    assert job.pipeline_state["chunk_publication"]["state"] == "ready"


def _batch_harness(monkeypatch: pytest.MonkeyPatch, jobs: list[SimpleNamespace], extract) -> list[tuple]:
    statuses: list[tuple] = []

    class FakeScalars:
        def all(self) -> list[object]:
            return jobs

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeDb:
        async def execute(self, _query: object) -> FakeResult:
            return FakeResult()

        async def commit(self) -> None:
            return None

    async def status(job_id: uuid.UUID, state: JobStatus, *_a: object, **_k: object) -> None:
        statuses.append((job_id, state))

    async def no_op(*_args: object, **_kwargs: object) -> None:
        return None

    from app.services import graph_identity

    monkeypatch.setattr(batch_orchestrator, "load_ai_model_policy", no_op)
    monkeypatch.setattr(batch_orchestrator, "get_ai_runtime_snapshot", lambda: {})
    monkeypatch.setattr(graph_identity, "ensure_identity_indexes", no_op)
    monkeypatch.setattr(batch_orchestrator, "_update_job_status", status)
    monkeypatch.setattr(batch_orchestrator, "_extract_file", extract)
    monkeypatch.setattr(batch_orchestrator, "_activate_chunk_revisions", lambda *_a: value(set()))
    monkeypatch.setattr(batch_orchestrator, "load_retired_claims", no_op, raising=False)
    from app.pipeline import transcript_replacement
    monkeypatch.setattr(transcript_replacement, "load_retired_claims", lambda *_a: value([]))
    FakeDb.statuses = statuses  # type: ignore[attr-defined]
    return statuses, FakeDb()  # type: ignore[return-value]


def _staged(job_id: uuid.UUID, name: str) -> tuple:
    return ([], [], None, None, [], batch_orchestrator.StagedChunkRevision(
        evidence_file_id=str(job_id), revision_id="rev", file_name=name, has_chunks=True, job_id=str(job_id)))


@pytest.mark.asyncio
async def test_one_files_failure_ends_only_that_file_and_says_so_when_it_happens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken, sibling = _job(uuid.uuid4(), "broken.txt"), _job(uuid.uuid4(), "sibling.txt")
    sibling_may_finish = asyncio.Event()
    failed_while_sibling_ran: list[bool] = []

    async def extract(job_id: uuid.UUID, _path: str, name: str, *_a: object, **_k: object) -> tuple:
        if job_id == broken.id:
            raise RuntimeError("a bug in this file's reader")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        failed_while_sibling_ran.append((broken.id, JobStatus.FAILED) in statuses)
        return _staged(job_id, name)

    statuses, db = _batch_harness(monkeypatch, [broken, sibling], extract)

    await batch_orchestrator.run_batch_pipeline("batch-1", "case-1", db)  # type: ignore[arg-type]

    assert failed_while_sibling_ran == [True]  # 5 Nov: a failed file read "chunking" for up to 10.5 minutes
    assert statuses.count((broken.id, JobStatus.FAILED)) == 1
    assert (sibling.id, JobStatus.COMPLETED) in statuses
    assert (sibling.id, JobStatus.FAILED) not in statuses
    assert (broken.id, JobStatus.COMPLETED) not in statuses
