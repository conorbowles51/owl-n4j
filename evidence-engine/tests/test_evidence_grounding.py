import json
import asyncio

import pytest

from app.pipeline import extract_entities
from app.pipeline import write_graph
from app.pipeline.extract_entities import (
    RawEntity,
    _extract_entities_from_chunk,
    _extract_relationships_from_chunk,
    _normalize_verified_facts,
    extract_entities_and_relationships,
)
from app.pipeline.chunk_embed import TextChunk
from app.pipeline.resolve_entities import _apply_merges
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship


def test_verified_facts_require_a_grounded_quote_and_keep_atomic_provenance() -> None:
    chunk_text = (
        "Opening paragraph.\n"
        "Marcus Chen approved EUR 125,000 on 15 March 2023.\n"
        "Closing paragraph."
    )
    quote = "Marcus Chen approved EUR 125,000 on 15 March 2023."

    facts = _normalize_verified_facts(
        [
            {"text": "Marcus Chen approved the payment.", "quote": quote, "page": 4},
            {
                "text": "Marcus Chen owned the supplier.",
                "quote": "Marcus Chen secretly owned the supplier.",
                "page": 4,
            },
        ],
        file_name="Report.pdf",
        fallback_page=4,
        chunk_text=chunk_text,
        chunk_index=7,
        chunk_start_char=1200,
        chunk_page_start=4,
        chunk_page_end=4,
        source_document_id="evidence-1",
        revision_id="revision-1",
        is_table=False,
    )

    assert len(facts) == 1
    assert facts[0]["quote"] == quote
    assert facts[0]["source_doc"] == "Report.pdf"
    assert facts[0]["source_location"] == {
        "source_document_id": "evidence-1",
        "revision_id": "revision-1",
        "source_file": "Report.pdf",
        "chunk_index": 7,
        "page_start": 4,
        "page_end": 4,
        "quote_start_char": 1219,
        "quote_end_char": 1219 + len(quote),
        "coordinate_space": "document_text",
    }


@pytest.mark.asyncio
async def test_entity_without_any_grounded_evidence_is_rejected(monkeypatch) -> None:
    async def fake_completion(**_kwargs) -> str:
        return json.dumps(
            {
                "entities": [
                    {
                        "category": "Person",
                        "specific_type": "Person",
                        "name": "Marcus Chen",
                        "properties": {},
                        "source_quote": "Marcus Chen secretly owned the supplier.",
                        "confidence": 0.95,
                        "verified_facts": [],
                        "ai_insights": [],
                    }
                ]
            }
        )

    monkeypatch.setattr(extract_entities, "chat_completion", fake_completion)

    entities = await _extract_entities_from_chunk(
        "Marcus Chen approved a payment.",
        3,
        "Report.pdf",
        "",
        page_start=8,
        page_end=8,
        source_document_id="evidence-1",
        revision_id="revision-1",
        chunk_start_char=400,
    )

    assert entities == []


@pytest.mark.asyncio
async def test_automated_entity_extraction_discards_ai_opinions(monkeypatch) -> None:
    async def fake_completion(**_kwargs) -> str:
        return json.dumps(
            {
                "entities": [
                    {
                        "category": "Person",
                        "specific_type": "Officer",
                        "name": "Vanderhoff",
                        "properties": {},
                        "source_quote": "Vanderhoff — Field Training Officer/Supervisor",
                        "confidence": 0.9,
                        "verified_facts": [],
                        "ai_insights": [
                            {
                                "text": "The title implies supervisory responsibility.",
                                "confidence": "medium",
                                "reasoning": "Inferred from the role title.",
                            }
                        ],
                    }
                ]
            }
        )

    monkeypatch.setattr(extract_entities, "chat_completion", fake_completion)

    entities = await _extract_entities_from_chunk(
        "Vanderhoff — Field Training Officer/Supervisor",
        1,
        "Report.pdf",
        "",
    )

    assert len(entities) == 1
    assert entities[0].ai_insights == []


@pytest.mark.asyncio
async def test_relationships_require_grounded_quotes_with_atomic_locations(monkeypatch) -> None:
    async def fake_completion(**_kwargs) -> str:
        return json.dumps(
            {
                "relationships": [
                    {
                        "source_entity_id": "E1",
                        "target_entity_id": "E2",
                        "type": "APPROVED",
                        "detail": "Approved a payment",
                        "properties": {},
                        "source_quote": "Marcus Chen approved the payment to Nexus Trading Ltd.",
                        "confidence": 0.9,
                    },
                    {
                        "source_entity_id": "E1",
                        "target_entity_id": "E2",
                        "type": "OWNS",
                        "detail": "Owns the supplier",
                        "properties": {},
                        "source_quote": "Marcus Chen secretly owns Nexus Trading Ltd.",
                        "confidence": 0.9,
                    },
                ]
            }
        )

    monkeypatch.setattr(extract_entities, "chat_completion", fake_completion)
    chunk_text = "Marcus Chen approved the payment to Nexus Trading Ltd."
    entities = [
        RawEntity("E1", "Person", "Person", "Marcus Chen"),
        RawEntity("E2", "Organization", "Company", "Nexus Trading Ltd"),
    ]

    relationships = await _extract_relationships_from_chunk(
        chunk_text,
        5,
        entities,
        "Report.pdf",
        "",
        page_start=9,
        page_end=9,
        source_document_id="evidence-1",
        revision_id="revision-1",
        chunk_start_char=900,
    )

    assert len(relationships) == 1
    assert relationships[0].source_location == {
        "source_document_id": "evidence-1",
        "revision_id": "revision-1",
        "source_file": "Report.pdf",
        "chunk_index": 5,
        "page_start": 9,
        "page_end": 9,
        "quote_start_char": 900,
        "quote_end_char": 900 + len(chunk_text),
        "coordinate_space": "document_text",
    }


def test_entity_resolution_preserves_quote_file_and_location_as_one_record() -> None:
    location = {
        "source_document_id": "evidence-1",
        "revision_id": "revision-1",
        "source_file": "Report.pdf",
        "chunk_index": 2,
        "page_start": 3,
        "page_end": 3,
        "quote_start_char": 100,
        "quote_end_char": 120,
        "coordinate_space": "document_text",
    }
    raw = RawEntity(
        "E1",
        "Person",
        "Person",
        "Marcus Chen",
        source_quote="Marcus Chen approved",
        source_file="Report.pdf",
        source_location=location,
        source_claim_ids=["claim-1"],
        confidence=0.9,
    )

    resolved, _id_map = _apply_merges([raw], [])

    assert resolved[0].source_locations == [
        {**location, "quote": "Marcus Chen approved"}
    ]
    assert resolved[0].source_claim_ids == ["claim-1"]


@pytest.mark.asyncio
async def test_graph_projection_serializes_structured_source_locations(monkeypatch) -> None:
    captured: list[dict] = []

    async def fake_geocode(_entities) -> None:
        return None

    async def fake_write(_query, params) -> None:
        captured.append(params)

    monkeypatch.setattr(write_graph, "_apply_geocoding", fake_geocode)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_write)

    location = {
        "source_document_id": "evidence-1",
        "revision_id": "revision-1",
        "source_file": "Report.pdf",
        "chunk_index": 2,
        "page_start": 3,
        "page_end": 3,
        "quote_start_char": 100,
        "quote_end_char": 120,
        "coordinate_space": "document_text",
        "quote": "Marcus Chen approved",
    }
    entity = ResolvedEntity(
        id="entity-1",
        category="Person",
        specific_type="Person",
        name="Marcus Chen",
        source_locations=[location],
    )
    relationship = ResolvedRelationship(
        source_entity_id="entity-1",
        target_entity_id="entity-2",
        type="APPROVED",
        source_locations=[location],
    )

    await write_graph._write_entities([entity], "case-1", "job-1")
    await write_graph._write_relationships([relationship], "case-1")

    assert json.loads(captured[0]["nodes"][0]["source_locations"]) == [location]
    assert json.loads(captured[1]["rels"][0]["source_locations"]) == [location]


@pytest.mark.asyncio
async def test_chunk_extraction_fanout_is_bounded(monkeypatch) -> None:
    active = 0
    peak = 0

    async def fake_entities(_text, chunk_index, *_args, **_kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return [RawEntity(f"E{chunk_index}", "Person", "Person", f"Person {chunk_index}")]

    async def fake_relationships(*_args, **_kwargs):
        await asyncio.sleep(0.001)
        return []

    monkeypatch.setattr(extract_entities.settings, "extraction_max_concurrency", 3, raising=False)
    monkeypatch.setattr(extract_entities, "_extract_entities_from_chunk", fake_entities)
    monkeypatch.setattr(extract_entities, "_extract_relationships_from_chunk", fake_relationships)
    chunks = [
        TextChunk(text=f"Person {index}", index=index, start_char=0, end_char=8)
        for index in range(12)
    ]

    await extract_entities_and_relationships(chunks, "", "Report.pdf")

    assert peak == 3
