from __future__ import annotations

import json

import pytest

from app.pipeline import consolidate_entities as consolidation
from app.pipeline.extract_entities import RawEntity


def _mention(
    temp_id: str,
    *,
    source_file: str,
    chunk_index: int,
    fact_text: str,
    claim_id: str,
) -> RawEntity:
    return RawEntity(
        temp_id=temp_id,
        category="Person",
        specific_type="Employee",
        name="Marcus Chen",
        source_quote=fact_text,
        source_file=source_file,
        source_chunk_index=chunk_index,
        source_location={"source_file": source_file, "page_start": 1},
        source_claim_ids=[claim_id],
        verified_facts=[
            {
                "text": fact_text,
                "quote": fact_text,
                "source_doc": source_file,
                "page": 1,
                "source_location": {"source_file": source_file, "page_start": 1},
            }
        ],
    )


def test_deterministic_consolidation_preserves_every_fact_and_claim_id() -> None:
    entities = [
        _mention(
            "E1",
            source_file="interview.pdf",
            chunk_index=2,
            fact_text="Marcus Chen joined the company in 2017.",
            claim_id="claim-1",
        ),
        _mention(
            "E2",
            source_file="interview.pdf",
            chunk_index=3,
            fact_text="Marcus Chen became Senior Procurement Manager.",
            claim_id="claim-2",
        ),
    ]

    consolidated, _, _, merge_count = consolidation._deterministic_consolidate(
        entities, []
    )

    assert merge_count == 1
    assert {fact["text"] for fact in consolidated[0].verified_facts} == {
        "Marcus Chen joined the company in 2017.",
        "Marcus Chen became Senior Procurement Manager.",
    }
    assert set(consolidated[0].source_claim_ids) == {"claim-1", "claim-2"}


@pytest.mark.asyncio
async def test_cross_document_llm_consolidation_preserves_complete_evidence(
    monkeypatch,
) -> None:
    async def fake_completion(**_kwargs) -> str:
        return json.dumps(
            {
                "groups": [
                    {
                        "indices": [0, 1],
                        "canonical_name": "Marcus Chen",
                        "confidence": 0.99,
                        "reasoning": "Same named employee across corroborating records.",
                    }
                ]
            }
        )

    monkeypatch.setattr(consolidation, "chat_completion", fake_completion)
    entities = [
        _mention(
            "E1",
            source_file="complaint.pdf",
            chunk_index=0,
            fact_text="The complaint identifies Marcus Chen as procurement manager.",
            claim_id="claim-a",
        ),
        _mention(
            "E2",
            source_file="interview.pdf",
            chunk_index=0,
            fact_text="Marcus Chen denied approving unsupported invoices.",
            claim_id="claim-b",
        ),
    ]

    consolidated, _, merge_count = await consolidation._llm_consolidate(entities, [])

    assert merge_count == 1
    assert len(consolidated[0].verified_facts) == 2
    assert set(consolidated[0].source_claim_ids) == {"claim-a", "claim-b"}
