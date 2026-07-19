import pytest

from app.pipeline import write_graph
from app.pipeline.resolve_entities import ResolvedEntity
from app.services.location_validation import (
    GEOCODING_STATUS_UNMAPPED_RETRIABLE,
    LocationRejectionReason,
)


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
async def test_write_entities_rejects_disallowed_coordinates_before_graph_write(monkeypatch):
    captured = {}

    async def fake_apply_geocoding(entities):
        return None

    async def fake_execute_write(query, params):
        captured["params"] = params

    monkeypatch.setattr(write_graph, "_apply_geocoding", fake_apply_geocoding)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_execute_write)

    entity = ResolvedEntity(
        id="doc-1",
        category="Document",
        specific_type="PDF",
        name="Source document",
        properties={"latitude": "51.5", "longitude": "-0.12"},
    )

    await write_graph._write_entities([entity], case_id="case-1", job_id="job-1")

    node = captured["params"]["nodes"][0]
    assert "latitude" not in node
    assert "longitude" not in node
    assert node["geocoding_status"] == "rejected"
    assert node["geocoding_rejection_reason"] == LocationRejectionReason.DISALLOWED_ENTITY_TYPE


@pytest.mark.asyncio
async def test_write_entities_stamps_legacy_provenance_on_pregeocode_coordinates(monkeypatch):
    captured = {}

    async def fake_apply_geocoding(entities):
        for entity in entities:
            write_graph._validate_entity_coordinates(entity)

    async def fake_execute_write(query, params):
        captured["params"] = params

    monkeypatch.setattr(write_graph, "_apply_geocoding", fake_apply_geocoding)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_execute_write)

    entity = ResolvedEntity(
        id="loc-legacy",
        category="Location",
        specific_type="City",
        name="Springfield",
        properties={"latitude": 39.9526, "longitude": -75.1652, "location_raw": "Springfield"},
    )

    await write_graph._write_entities([entity], case_id="case-1", job_id="job-1")

    node = captured["params"]["nodes"][0]
    assert node["latitude"] == 39.9526
    assert node["longitude"] == -75.1652
    assert node["geocoding_status"] == "mapped"
    assert node["geocoding_provider"] == "legacy"
    assert node["geocoding_query"] == "Springfield"
    assert node["geocoding_precision"] == "unknown"
    assert node["geocoding_confidence"] == "low"


@pytest.mark.asyncio
async def test_write_entities_keeps_existing_provenance_on_pregeocode_coordinates(monkeypatch):
    captured = {}

    async def fake_apply_geocoding(entities):
        for entity in entities:
            write_graph._validate_entity_coordinates(entity)

    async def fake_execute_write(query, params):
        captured["params"] = params

    monkeypatch.setattr(write_graph, "_apply_geocoding", fake_apply_geocoding)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_execute_write)

    entity = ResolvedEntity(
        id="loc-agentic",
        category="Location",
        specific_type="City",
        name="Springfield",
        properties={
            "latitude": 39.9526,
            "longitude": -75.1652,
            "geocoding_provider": "nominatim",
            "geocoding_query": "Springfield, PA",
            "geocoding_precision": "city",
            "geocoding_confidence": "high",
        },
    )

    await write_graph._write_entities([entity], case_id="case-1", job_id="job-1")

    node = captured["params"]["nodes"][0]
    assert node["geocoding_status"] == "mapped"
    assert node["geocoding_provider"] == "nominatim"
    assert node["geocoding_query"] == "Springfield, PA"
    assert node["geocoding_precision"] == "city"
    assert node["geocoding_confidence"] == "high"


@pytest.mark.asyncio
async def test_apply_geocoding_provider_failure_keeps_retriable_unmapped_state(monkeypatch):
    class FakeResult:
        provider = "nominatim"
        original_query = "London"
        status = GEOCODING_STATUS_UNMAPPED_RETRIABLE
        provider_error = "network down"

    class FakeService:
        async def geocode(self, query):
            return FakeResult()

    monkeypatch.setattr(write_graph, "geocoding_service", FakeService())

    entity = ResolvedEntity(
        id="loc-1",
        category="Location",
        specific_type="City",
        name="London",
        properties={},
    )

    await write_graph._apply_geocoding([entity])

    assert "latitude" not in entity.properties
    assert "longitude" not in entity.properties
    assert entity.properties["geocoding_status"] == GEOCODING_STATUS_UNMAPPED_RETRIABLE
    assert entity.properties["geocoding_provider_error"] == "network down"
