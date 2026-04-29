import pytest

from app.pipeline.resolve_entities import ResolvedEntity, coalesce_resolved_entities_by_id
from app.pipeline import write_graph as write_graph_module


def test_coalesce_resolved_entities_merges_duplicate_ids() -> None:
    first = ResolvedEntity(
        id="existing-entity-id",
        category="Person",
        specific_type="Suspect",
        name="Marco Rivera",
        aliases=["Marco D. Rivera"],
        properties={"description": "Short description"},
        source_quotes=["quote one"],
        confidence=0.7,
        source_files=["USA-027854.pdf"],
        verified_facts=[{"text": "Owns Solaris", "source_doc": "USA-027854.pdf", "page": 1}],
        mandatory_instructions=["Keep beneficial owners distinct"],
        is_existing=True,
    )
    second = ResolvedEntity(
        id="existing-entity-id",
        category="Person",
        specific_type="",
        name="M. Rivera",
        aliases=["Rivera"],
        properties={"description": "Longer description with more context", "role": "Organizer"},
        source_quotes=["quote one", "quote two"],
        confidence=0.9,
        source_files=["USA-027860.pdf"],
        ai_insights=[{"text": "Appears in related file", "source_doc": "USA-027860.pdf"}],
    )

    coalesced = coalesce_resolved_entities_by_id([first, second])

    assert len(coalesced) == 1
    entity = coalesced[0]
    assert entity.id == "existing-entity-id"
    assert entity.confidence == 0.9
    assert entity.is_existing is True
    assert entity.specific_type == "Suspect"
    assert entity.properties["description"] == "Longer description with more context"
    assert entity.properties["role"] == "Organizer"
    assert entity.aliases == ["M. Rivera", "Marco D. Rivera", "Rivera"]
    assert entity.source_files == ["USA-027854.pdf", "USA-027860.pdf"]
    assert entity.source_quotes == ["quote one", "quote two"]
    assert entity.verified_facts == [
        {"text": "Owns Solaris", "source_doc": "USA-027854.pdf", "page": 1}
    ]
    assert entity.ai_insights == [
        {"text": "Appears in related file", "source_doc": "USA-027860.pdf"}
    ]
    assert entity.mandatory_instructions == ["Keep beneficial owners distinct"]


@pytest.mark.asyncio
async def test_write_graph_coalesces_entities_before_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_entity_counts: list[int] = []
    embedded_ids: list[str] = []

    async def fake_ensure_indexes() -> None:
        return None

    async def fake_write_entities(entities, case_id, job_id) -> None:
        seen_entity_counts.append(len(entities))

    async def fake_write_relationships(relationships, case_id) -> None:
        return None

    async def fake_embed_entities(entities, case_id) -> None:
        embedded_ids.extend(entity.id for entity in entities)

    monkeypatch.setattr(write_graph_module, "_ensure_indexes", fake_ensure_indexes)
    monkeypatch.setattr(write_graph_module, "_write_entities", fake_write_entities)
    monkeypatch.setattr(write_graph_module, "_write_relationships", fake_write_relationships)
    monkeypatch.setattr(write_graph_module, "_embed_entities", fake_embed_entities)

    await write_graph_module.write_graph(
        [
            ResolvedEntity(
                id="c1a5a2de-8bea-4680-a1e1-fc51e405912d",
                category="Person",
                specific_type="Suspect",
                name="Marco Rivera",
            ),
            ResolvedEntity(
                id="c1a5a2de-8bea-4680-a1e1-fc51e405912d",
                category="Person",
                specific_type="Suspect",
                name="M. Rivera",
            ),
        ],
        [],
        "case-id",
        "job-id",
    )

    assert seen_entity_counts == [1]
    assert embedded_ids == ["c1a5a2de-8bea-4680-a1e1-fc51e405912d"]
