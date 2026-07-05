import uuid
from typing import Any

import pytest

from app.pipeline import batch_orchestrator
from app.pipeline import generate_document_summary as summary_module
from app.pipeline.extract_text import ExtractedDocument


@pytest.mark.asyncio
async def test_generate_document_summary_includes_processing_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_chat_completion(*, messages: list[dict[str, str]], model: str) -> str:
        captured["messages"] = messages
        captured["model"] = model
        return "  summary text  "

    monkeypatch.setattr(summary_module.settings, "openai_document_summary_model", "summary-test")
    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)

    doc = ExtractedDocument(
        text=(
            "This jail call recording discusses the case, participants, and events. "
            "The transcript includes references to the caller and recipient."
        )
    )

    result = await summary_module.generate_document_summary(
        doc,
        "jail-call-001.mp3",
        case_context="[Jail calls]\nAll calls in this folder were made by Timothy.",
        mandatory_instructions=["Identify Timothy as the caller when summarizing these calls."],
        special_entity_types=[
            {
                "name": "Jail Call Participant",
                "description": "A person participating in a recorded jail call.",
            }
        ],
    )

    assert result == "summary text"
    assert captured["model"] == "summary-test"
    prompt = captured["messages"][0]["content"]
    assert "All calls in this folder were made by Timothy." in prompt
    assert "Identify Timothy as the caller" in prompt
    assert "Jail Call Participant" in prompt
    assert "**Content:**" in prompt


@pytest.mark.asyncio
async def test_generate_document_summary_skips_short_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_chat_completion(**_: object) -> str:
        pytest.fail("short content should not call the LLM")

    monkeypatch.setattr(summary_module, "chat_completion", fail_chat_completion)

    result = await summary_module.generate_document_summary(
        ExtractedDocument(text="Too short."),
        "empty.txt",
        case_context="Context should not matter for short content.",
    )

    assert result is None


@pytest.mark.asyncio
async def test_batch_extraction_passes_effective_profile_to_document_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCostContext:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    async def fake_update_job_status(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_extract_text(_file_path: str, _file_name: str) -> ExtractedDocument:
        return ExtractedDocument(
            text=(
                "This jail call transcript contains enough content for summary generation "
                "and entity extraction."
            )
        )

    async def fake_generate_document_summary(
        _doc: ExtractedDocument,
        _file_name: str,
        **kwargs: object,
    ) -> str:
        captured.update(kwargs)
        return "summary"

    async def fake_chunk_and_embed(*_args: object, **_kwargs: object) -> list[object]:
        return []

    async def fake_extract_entities_and_relationships(
        _chunks: list[object],
        case_context: str,
        _file_name: str,
        **kwargs: object,
    ) -> tuple[list[object], list[object]]:
        captured["entity_context"] = case_context
        captured["entity_kwargs"] = kwargs
        return [], []

    monkeypatch.setattr(batch_orchestrator, "ingestion_cost_context", lambda **_: FakeCostContext())
    monkeypatch.setattr(batch_orchestrator, "_update_job_status", fake_update_job_status)
    monkeypatch.setattr(batch_orchestrator, "extract_text", fake_extract_text)
    monkeypatch.setattr(batch_orchestrator, "get_transcription", lambda _doc: None)
    monkeypatch.setattr(batch_orchestrator, "generate_document_summary", fake_generate_document_summary)
    monkeypatch.setattr(batch_orchestrator, "chunk_and_embed", fake_chunk_and_embed)
    monkeypatch.setattr(
        batch_orchestrator,
        "extract_entities_and_relationships",
        fake_extract_entities_and_relationships,
    )

    await batch_orchestrator._extract_file(
        job_id=uuid.uuid4(),
        file_path="call.mp3",
        file_name="call.mp3",
        case_id="case-1",
        llm_profile="generic",
        effective_context="[Jail calls]\nAll calls in this folder were made by Timothy.",
        effective_mandatory_instructions=["Treat Timothy as the caller."],
        effective_special_entity_types=[{"name": "Jail Call Participant"}],
    )

    assert captured["case_context"] == "[Jail calls]\nAll calls in this folder were made by Timothy."
    assert captured["mandatory_instructions"] == ["Treat Timothy as the caller."]
    assert captured["special_entity_types"] == [{"name": "Jail Call Participant"}]
    assert captured["entity_context"] == captured["case_context"]
