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

    async def fake_chat_completion(**kwargs: Any) -> str:
        messages = kwargs["messages"]
        if kwargs.get("response_format"):
            return '{"corrected_summary":"summary text","correction_count":0}'
        captured["messages"] = messages
        captured["workload"] = kwargs.get("workload")
        return "  summary text  "

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
    assert captured["workload"] == "ingestion_document_summary"
    assert captured["messages"][0]["role"] == "system"
    assert "untrusted evidence data" in captured["messages"][0]["content"]
    prompt = captured["messages"][-1]["content"]
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
async def test_document_summary_failure_is_recorded_for_quality_reporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_chat_completion(**_: object) -> str:
        raise RuntimeError("summary provider unavailable")

    monkeypatch.setattr(summary_module, "chat_completion", fail_chat_completion)
    document = ExtractedDocument(
        text="This source has enough material to require a document summary. " * 3
    )

    result = await summary_module.generate_document_summary(document, "report.txt")

    assert result is None
    assert document.metadata["document_summary_status"] == "failed"
    assert "summary provider unavailable" in document.metadata["document_summary_error"]


@pytest.mark.asyncio
async def test_large_document_requests_a_comprehensive_multi_paragraph_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_chat_completion(**kwargs: Any) -> str:
        prompt = kwargs["messages"][-1]["content"]
        if kwargs.get("response_format"):
            return '{"corrected_summary":"summary","correction_count":0}'
        captured["prompt"] = prompt
        return "summary"

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    document = ExtractedDocument(
        text=(
            "This is representative evidence from a lengthy investigative report. "
            "It identifies the principal subjects, events, transactions, and findings."
        ),
        metadata={"file_type": "pdf", "page_count": 400},
    )

    await summary_module.generate_document_summary(document, "long-report.pdf")

    prompt = captured["prompt"]
    assert "standalone, comprehensive narrative summary" in prompt
    assert "five to eight substantive paragraphs" in prompt
    assert "Do not limit the Overview to an abstract or a few introductory sentences" in prompt
    assert "distinguish documented facts from attributed allegations" in prompt


@pytest.mark.asyncio
async def test_oversized_document_summarizes_every_source_segment_before_reduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts: list[str] = []

    async def fake_chat_completion(**kwargs: Any) -> str:
        prompt = kwargs["messages"][-1]["content"]
        prompts.append(prompt)
        if kwargs.get("response_format"):
            return '{"corrected_summary":"final summary","correction_count":0}'
        if "SOURCE SEGMENT" in prompt:
            if "START OF DOCUMENT" in prompt:
                return "Digest containing START OF DOCUMENT"
            if "MIDDLE OF DOCUMENT" in prompt:
                return "Digest containing MIDDLE OF DOCUMENT"
            if "END OF DOCUMENT" in prompt:
                return "Digest containing END OF DOCUMENT"
            return "Digest of intervening source material"
        return "final summary"

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    content = (
        "START OF DOCUMENT: opening allegation and scope.\n\n"
        + ("Early evidence and procedural history. " * 700)
        + "\n\nMIDDLE OF DOCUMENT: central transaction findings.\n\n"
        + ("Later evidence and witness material. " * 700)
        + "\n\nEND OF DOCUMENT: final findings and requested action."
    )
    assert len(content) > summary_module.MAX_CONTENT_CHARS

    await summary_module.generate_document_summary(
        ExtractedDocument(
            text=content,
            metadata={"file_type": "pdf", "page_count": 150},
        ),
        "oversized-report.pdf",
    )

    map_prompts = [prompt for prompt in prompts if "SOURCE SEGMENT" in prompt]
    assert len(map_prompts) >= 3
    assert "START OF DOCUMENT" in "\n".join(map_prompts)
    assert "MIDDLE OF DOCUMENT" in "\n".join(map_prompts)
    assert "END OF DOCUMENT" in "\n".join(map_prompts)
    synthesis_prompt = next(prompt for prompt in prompts if "COMPLETE SET OF SOURCE-SEGMENT DIGESTS" in prompt)
    assert "representative excerpts" not in synthesis_prompt


@pytest.mark.asyncio
async def test_verbose_singleton_digests_are_forced_into_a_converging_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_chat_completion(**kwargs: Any) -> str:
        calls.append(kwargs)
        prompt = kwargs["messages"][-1]["content"]
        if "SOURCE SEGMENT" in prompt:
            return "M" * 160
        if "DIGEST CONSOLIDATION" in prompt:
            return "R" * 80
        raise AssertionError(f"Unexpected prompt: {prompt[:80]}")

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(summary_module, "SUMMARY_MAP_CHARS", 100)
    monkeypatch.setattr(summary_module, "SUMMARY_REDUCE_CHARS", 300)

    result = await summary_module._summarize_all_segments(
        "x" * 260,
        file_name="verbose-report.pdf",
        profile_guidance="",
    )

    map_calls = [
        call for call in calls if "SOURCE SEGMENT" in call["messages"][-1]["content"]
    ]
    reduce_calls = [
        call for call in calls if "DIGEST CONSOLIDATION" in call["messages"][-1]["content"]
    ]
    assert len(map_calls) == 3
    assert len(reduce_calls) == 2
    assert len(result) <= summary_module.SUMMARY_REDUCE_CHARS
    assert all(
        call["max_output_tokens"] == summary_module.SUMMARY_MAP_OUTPUT_TOKENS
        for call in map_calls
    )
    assert all(
        call["max_output_tokens"] == summary_module.SUMMARY_REDUCE_OUTPUT_TOKENS
        for call in reduce_calls
    )


@pytest.mark.asyncio
async def test_single_digest_reduction_accepts_actual_payload_shrinkage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_chat_completion(**kwargs: Any) -> str:
        prompt = kwargs["messages"][-1]["content"]
        if "SOURCE SEGMENT" in prompt:
            return "M" * 400
        if "DIGEST CONSOLIDATION" in prompt:
            return "R" * 100
        raise AssertionError(f"Unexpected prompt: {prompt[:80]}")

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(summary_module, "SUMMARY_MAP_CHARS", 100)
    monkeypatch.setattr(summary_module, "SUMMARY_REDUCE_CHARS", 300)

    result = await summary_module._summarize_all_segments(
        "x" * 80,
        file_name="single-segment-report.pdf",
        profile_guidance="",
    )

    assert len(result) <= summary_module.SUMMARY_REDUCE_CHARS
    assert "R" * 100 in result


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

    async def fake_extract_text(
        _file_path: str,
        _file_name: str,
        **_kwargs: object,
    ) -> ExtractedDocument:
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
