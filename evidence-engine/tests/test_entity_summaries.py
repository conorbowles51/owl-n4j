from __future__ import annotations

import json
from typing import Any

from app.pipeline import generate_summaries as summary_module
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship


async def test_entity_summary_prompt_excludes_ai_analysis_and_requires_attribution(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_chat_completion(**kwargs: Any) -> str:
        prompt = kwargs["messages"][1]["content"]
        if "Audit each draft entity summary" not in prompt:
            captured.update(kwargs)
        return json.dumps(
            {
                "summaries": [
                    {
                        "entity_index": 0,
                        "summary": "## Background\nVanderhoff is listed as an FTO.",
                    }
                ]
            }
        )

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    entity = ResolvedEntity(
        id="entity-1",
        category="Person",
        specific_type="Field Training Officer/Supervisor",
        name="Vanderhoff",
        verified_facts=[
            {
                "text": "The PCR lists Vanderhoff as Field Training Officer/Supervisor.",
                "quote": "FTO/Supervisor: Vanderhoff",
                "source_doc": "PCR.pdf",
                "page": 1,
            }
        ],
        ai_insights=[
            {
                "text": "By role title alone, this indicates supervisory responsibility.",
                "confidence": "medium",
                "reasoning": "Inferred from the role label.",
            }
        ],
        source_files=["PCR.pdf"],
    )

    result = await summary_module.generate_summaries([entity], [])

    assert result[0].summary.startswith("## Background")
    prompt = captured["messages"][1]["content"]
    assert "untrusted evidence data" in captured["messages"][0]["content"]
    assert "By role title alone" not in prompt
    assert "Do not include analysis, opinions, theories, or inferred implications" in prompt
    assert "Attribute allegations, claims, and disputed statements to their source" in prompt
    assert "Only describe relationships that are explicitly supported" in prompt


async def test_entity_summary_relationship_context_includes_documentary_support(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_chat_completion(**kwargs: Any) -> str:
        prompt = kwargs["messages"][1]["content"]
        if "Audit each draft entity summary" not in prompt:
            captured.update(kwargs)
            return json.dumps({"summaries": []})
        return json.dumps(
            {
                "summaries": [
                    {"entity_index": 0, "summary": "## Evidence Summary\nSupported."},
                    {"entity_index": 1, "summary": "## Evidence Summary\nSupported."},
                ]
            }
        )

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    entities = [
        ResolvedEntity(
            id="person-1",
            category="Person",
            specific_type="Employee",
            name="Marcus Chen",
        ),
        ResolvedEntity(
            id="org-1",
            category="Organization",
            specific_type="Vendor",
            name="Nexus Trading Ltd",
        ),
    ]
    relationship = ResolvedRelationship(
        source_entity_id="person-1",
        target_entity_id="org-1",
        type="ADDED_AS_VENDOR",
        detail="The complaint reports that Marcus Chen added Nexus as a vendor.",
        source_quotes=["Marcus Chen added Nexus Trading Ltd as a new vendor."],
        source_files=["whistleblower-complaint.pdf"],
        confidence=0.91,
    )

    await summary_module.generate_summaries(entities, [relationship])

    prompt = captured["messages"][1]["content"]
    assert "Marcus Chen added Nexus Trading Ltd as a new vendor." in prompt
    assert '"source_files": [' in prompt
    assert '"confidence": 0.91' in prompt


async def test_missing_model_summary_retries_then_uses_evidence_only_fallback(
    monkeypatch,
) -> None:
    calls = 0

    async def fake_chat_completion(**_kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        return json.dumps({"summaries": []})

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    entity = ResolvedEntity(
        id="person-1",
        category="Person",
        specific_type="Employee",
        name="Alex Smith",
        verified_facts=[
            {
                "text": "Alex Smith approved payment reference P-104.",
                "quote": "Alex Smith approved payment reference P-104",
                "source_doc": "approval.pdf",
                "source_location": {"source_file": "approval.pdf"},
            }
        ],
        source_files=["approval.pdf"],
    )

    result = await summary_module.generate_summaries([entity], [])

    assert calls == 3
    assert "Alex Smith approved payment reference P-104." in result[0].summary
    assert "[approval.pdf](evidence://approval.pdf)" in result[0].summary


async def test_central_entity_summary_receives_complete_cited_case_dossier(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_chat_completion(**kwargs: Any) -> str:
        prompt = kwargs["messages"][1]["content"]
        if "Audit each draft entity summary" not in prompt:
            captured["prompt"] = prompt
        return json.dumps(
            {
                "summaries": [
                    {
                        "entity_index": 0,
                        "summary": "## Background\nA comprehensive evidence-backed profile.",
                    }
                ]
            }
        )

    monkeypatch.setattr(summary_module, "chat_completion", fake_chat_completion)
    facts = []
    for index in range(25):
        page = index + 1
        facts.append(
            {
                "text": f"Documented fact number {index + 1} about Marcus Chen.",
                "quote": f"Fact number {index + 1}",
                "source_doc": f"record-{index % 3}.pdf",
                "page": page,
                "importance": 3,
                "source_location": {
                    "source_file": f"record-{index % 3}.pdf",
                    "page_start": page,
                },
            }
        )
    entity = ResolvedEntity(
        id="person-1",
        category="Person",
        specific_type="Employee",
        name="Marcus Chen",
        verified_facts=facts,
        source_files=["record-0.pdf", "record-1.pdf", "record-2.pdf"],
        is_existing=True,
        existing_summary="A prior short summary that must not be merged as evidence.",
    )

    result = await summary_module.generate_summaries([entity], [])

    prompt = captured["prompt"]
    assert "Documented fact number 1" in prompt
    assert "Documented fact number 25" in prompt
    assert "doc://record-0.pdf/1" in prompt
    assert '"evidence_item_count": 25' in prompt
    assert "A prior short summary that must not be merged as evidence." not in prompt
    assert "regenerate the profile from the complete accumulated dossier" in prompt
    assert "Natural paraphrase and synthesis are allowed" in prompt
    assert "Documented fact number 25" in result[0].summary
    assert "doc://record-0.pdf/1" in result[0].summary
