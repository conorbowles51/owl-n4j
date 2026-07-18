import pytest

from app.pipeline import write_graph
from app.pipeline.resolve_entities import ResolvedEntity


@pytest.mark.asyncio
async def test_write_entities_preserves_manual_fields(monkeypatch):
    captured = {}

    async def fake_apply_geocoding(entities):
        return None

    async def fake_execute_write(query, params):
        captured["query"] = query
        captured["params"] = params

    monkeypatch.setattr(write_graph, "_apply_geocoding", fake_apply_geocoding)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_execute_write)

    entity = ResolvedEntity(
        id="event-1",
        category="Event",
        specific_type="Incident",
        name="Warehouse incident",
        properties={"date": "2024-01-01", "description": "AI description"},
        summary="AI summary",
    )

    await write_graph._write_entities([entity], case_id="case-1", job_id="job-1")

    assert "coalesce(n.manual_fields, []) AS manual_fields" in captured["query"]
    assert "apoc.map.removeKeys(node, manual_fields)" in captured["query"]
    assert "WHEN 'summary' IN manual_fields THEN prev_summary" in captured["query"]
    assert "WHEN NOT 'category' IN manual_fields" in captured["query"]
    assert captured["params"]["nodes"][0]["date"] == "2024-01-01"


@pytest.mark.asyncio
async def test_write_entities_canonicalizes_temporal_aliases_and_preserves_lists(monkeypatch):
    captured = {}

    async def fake_apply_geocoding(entities):
        return None

    async def fake_execute_write(query, params):
        captured["query"] = query
        captured["params"] = params

    monkeypatch.setattr(write_graph, "_apply_geocoding", fake_apply_geocoding)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_execute_write)

    entity = ResolvedEntity(
        id="comm-1",
        category="Communication",
        specific_type="Phone Call",
        name="Jail call",
        properties={
            "timestamp": "2025-04-12 06:21:47-06:23:45",
            "participants": ["Timothy Valentin", "Unknown recipient"],
        },
        summary="A jail call.",
    )

    await write_graph._write_entities([entity], case_id="case-1", job_id="job-1")

    node = captured["params"]["nodes"][0]
    assert node["date"] == "2025-04-12"
    assert node["time"] == "06:21"
    assert node["end_time"] == "06:23"
    assert node["participants"] == ["Timothy Valentin", "Unknown recipient"]


@pytest.mark.asyncio
async def test_apply_geocoding_marks_vague_locations_ambiguous(monkeypatch):
    monkeypatch.setattr(write_graph, "GEOCODABLE_CATEGORIES", {"Communication"})

    entity = ResolvedEntity(
        id="comm-1",
        category="Communication",
        specific_type="Message",
        name="Message mentioning location",
        properties={"location_raw": "overseas"},
        summary="A message mentioning a vague location.",
    )

    await write_graph._apply_geocoding([entity])

    assert entity.properties["location_raw"] == "overseas"
    assert entity.properties["geocoding_status"] == "ambiguous"
    assert "latitude" not in entity.properties
    assert "longitude" not in entity.properties
