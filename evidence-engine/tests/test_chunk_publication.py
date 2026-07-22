from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
import uuid

import pytest

from app.pipeline import chunk_embed
from app.pipeline import batch_orchestrator
from app.pipeline import orchestrator
from app.pipeline.extract_text import ExtractedDocument


@pytest.mark.asyncio
async def test_chunk_embeddings_are_versioned_drafts_and_idempotently_upserted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    collection = object()

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def fake_upsert_embeddings(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(chunk_embed, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(chunk_embed, "get_or_create_collection", lambda _name: collection)
    monkeypatch.setattr(chunk_embed, "upsert_embeddings", fake_upsert_embeddings, raising=False)

    doc = ExtractedDocument(
        text="Marcus Chen approved the invoice.",
        tables=[],
        metadata={"file_type": "pdf"},
    )

    await chunk_embed.chunk_and_embed(
        doc,
        case_id="case-1",
        job_id="job-1",
        file_name="Board Minutes.pdf",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
    )

    assert captured["collection"] is collection
    assert captured["ids"] == ["evidence-1:revision-1:chunk:0"]
    metadata = captured["metadatas"][0]  # type: ignore[index]
    assert metadata["case_id"] == "case-1"
    assert metadata["doc_id"] == "evidence-1"
    assert metadata["doc_key"] == "board-minutespdf"
    assert metadata["evidence_file_id"] == "evidence-1"
    assert metadata["revision_id"] == "revision-1"
    assert metadata["ingestion_state"] == "draft"


@pytest.mark.asyncio
async def test_activation_promotes_current_revision_and_retires_previous_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeCollection:
        def __init__(self) -> None:
            self.updated: dict[str, dict[str, object]] = {}

        def get(self, *, where: dict[str, object], include: list[str]) -> dict[str, object]:
            assert include == ["metadatas"]
            if "evidence_file_id" in str(where):
                return {
                    "ids": ["old", "current"],
                    "metadatas": [
                        {
                            "case_id": "case-1",
                            "evidence_file_id": "evidence-1",
                            "revision_id": "revision-0",
                            "ingestion_state": "active",
                        },
                        {
                            "case_id": "case-1",
                            "evidence_file_id": "evidence-1",
                            "revision_id": "revision-1",
                            "ingestion_state": "draft",
                        },
                    ],
                }
            return {"ids": [], "metadatas": []}

        def update(self, *, ids: list[str], metadatas: list[dict[str, object]]) -> None:
            self.updated.update(dict(zip(ids, metadatas)))

    collection = FakeCollection()
    monkeypatch.setattr(
        chunk_embed,
        "get_or_create_collection",
        lambda _name: collection,
    )

    result = await chunk_embed.activate_chunk_revision(
        case_id="case-1",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        file_name="Board Minutes.pdf",
    )

    assert result.activated_count == 1
    assert result.retired_count == 1
    assert collection.updated["current"]["ingestion_state"] == "active"
    assert collection.updated["old"]["ingestion_state"] == "inactive"


@pytest.mark.asyncio
async def test_chunk_revision_identity_is_stable_across_job_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_ids: list[list[str]] = []

    async def fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    def capture_upsert(**kwargs: object) -> None:
        captured_ids.append(kwargs["ids"])  # type: ignore[arg-type]

    monkeypatch.setattr(chunk_embed, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(chunk_embed, "get_or_create_collection", lambda _name: object())
    monkeypatch.setattr(chunk_embed, "upsert_embeddings", capture_upsert)

    doc = ExtractedDocument(
        text="The source content is unchanged between retry attempts.",
        tables=[],
        metadata={"file_type": "pdf"},
    )

    await chunk_embed.chunk_and_embed(
        doc,
        case_id="case-1",
        job_id="attempt-1",
        file_name="report.pdf",
        evidence_file_id="evidence-1",
    )
    await chunk_embed.chunk_and_embed(
        doc,
        case_id="case-1",
        job_id="attempt-2",
        file_name="report.pdf",
        evidence_file_id="evidence-1",
    )

    assert captured_ids[0] == captured_ids[1]


@pytest.mark.asyncio
async def test_single_file_pipeline_activates_chunks_only_after_graph_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    chunk_kwargs: dict[str, object] = {}
    job_id = uuid.uuid4()
    job = SimpleNamespace(
        id=job_id,
        case_id="case-1",
        requested_by_user_id=None,
        source_evidence_file_id=None,
        file_name="report.pdf",
        file_path="report.pdf",
        folder_context=None,
        sibling_files=None,
        llm_profile="",
        effective_context=None,
        effective_mandatory_instructions=[],
        effective_special_entity_types=[],
        progress=0.0,
        status=None,
        error_message=None,
        document_summary=None,
        transcription=None,
        entity_count=0,
        relationship_count=0,
    )
    doc = ExtractedDocument(
        text="Stable canonical evidence content for publication.",
        tables=[],
        metadata={"file_type": "pdf"},
    )

    class FakeResult:
        def scalar_one(self) -> object:
            return job

    class FakeDb:
        async def execute(self, _query: object) -> FakeResult:
            return FakeResult()

        async def commit(self) -> None:
            return None

        async def commit(self) -> None:
            return None

    @asynccontextmanager
    async def fake_cost_context(**_kwargs: object):
        yield

    async def fake_update(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_chunk_and_embed(*_args: object, **kwargs: object) -> list[object]:
        chunk_kwargs.update(kwargs)
        return [object()]

    async def fake_write_graph(*_args: object, **_kwargs: object) -> None:
        events.append("graph")

    async def fake_publish(_job: object, _db: object) -> object:
        events.append("chunks")
        return SimpleNamespace(activated_count=1, retired_count=0)

    async def return_empty_pair(*_args: object, **_kwargs: object) -> tuple[list[object], list[object]]:
        return [], []

    async def return_first(value: object, *_args: object, **_kwargs: object) -> object:
        return value

    monkeypatch.setattr(orchestrator, "ingestion_cost_context", fake_cost_context)
    monkeypatch.setattr(orchestrator, "_update_job", fake_update)
    monkeypatch.setattr(orchestrator, "publish_progress", fake_update)
    monkeypatch.setattr(orchestrator, "extract_text", lambda *_args, **_kwargs: _async_value(doc))
    monkeypatch.setattr(orchestrator, "get_transcription", lambda _doc: None)
    monkeypatch.setattr(orchestrator, "generate_document_summary", lambda *_args, **_kwargs: _async_value(None))
    monkeypatch.setattr(orchestrator, "chunk_and_embed", fake_chunk_and_embed)
    monkeypatch.setattr(orchestrator, "extract_entities_and_relationships", return_empty_pair)
    monkeypatch.setattr(orchestrator, "consolidate_entities", return_empty_pair)
    monkeypatch.setattr(orchestrator, "resolve_entities", return_empty_pair)
    monkeypatch.setattr(orchestrator, "resolve_relationships", return_first)
    monkeypatch.setattr(orchestrator, "generate_summaries", return_first)
    monkeypatch.setattr(orchestrator, "write_graph", fake_write_graph)
    monkeypatch.setattr(orchestrator, "publish_chunk_revision", fake_publish)

    await orchestrator.run_pipeline(str(job_id), FakeDb())  # type: ignore[arg-type]

    assert events == ["graph", "chunks"]
    assert chunk_kwargs["evidence_file_id"] == str(job_id)
    assert chunk_kwargs["revision_id"] == chunk_embed.get_document_revision_id(doc)


async def _async_value(value: object) -> object:
    return value


@pytest.mark.asyncio
async def test_batch_activates_successful_text_only_documents_with_no_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = uuid.uuid4()
    job = SimpleNamespace(
        id=job_id,
        created_at=None,
        file_path="notes.txt",
        file_name="notes.txt",
        llm_profile="",
        folder_context=None,
        sibling_files=None,
        effective_context=None,
        effective_mandatory_instructions=[],
        effective_special_entity_types=[],
        requested_by_user_id=None,
        source_evidence_file_id=None,
    )
    activations: list[dict[str, object]] = []

    class FakeScalars:
        def all(self) -> list[object]:
            return [job]

    class FakeResult:
        def scalars(self) -> FakeScalars:
            return FakeScalars()

    class FakeDb:
        async def execute(self, _query: object) -> FakeResult:
            return FakeResult()

        async def commit(self) -> None:
            return None

    async def fake_extract_file(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        return (
            [],
            [],
            None,
            None,
            SimpleNamespace(
                evidence_file_id=str(job_id),
                revision_id="revision-1",
                file_name="notes.txt",
                has_chunks=True,
            ),
        )

    async def fake_status(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_activate(**kwargs: object) -> object:
        activations.append(kwargs)
        return SimpleNamespace(activated_count=1, retired_count=0)

    monkeypatch.setattr(batch_orchestrator, "_extract_file", fake_extract_file)
    monkeypatch.setattr(batch_orchestrator, "_update_job_status", fake_status)
    monkeypatch.setattr(
        batch_orchestrator,
        "activate_chunk_revision",
        fake_activate,
        raising=False,
    )

    await batch_orchestrator.run_batch_pipeline(
        batch_id="batch-1",
        case_id="case-1",
        db=FakeDb(),  # type: ignore[arg-type]
    )

    assert activations == [
        {
            "case_id": "case-1",
            "evidence_file_id": str(job_id),
            "revision_id": "revision-1",
            "file_name": "notes.txt",
        }
    ]
