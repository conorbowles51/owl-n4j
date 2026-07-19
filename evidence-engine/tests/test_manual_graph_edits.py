import pytest

from app.pipeline import write_graph
from app.pipeline.resolve_entities import ResolvedEntity
from app.services.geocoding import GeocodeResult


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
async def test_apply_geocoding_attempts_and_retains_vague_locations(monkeypatch):
    monkeypatch.setattr(write_graph, "GEOCODABLE_CATEGORIES", {"Communication"})
    queries = []

    async def fake_geocode(query):
        queries.append(query)
        return GeocodeResult(
            provider="nominatim",
            normalized_query=query,
            original_query=query,
            status="failed",
        )

    monkeypatch.setattr(write_graph.geocoding_service, "geocode", fake_geocode)

    entity = ResolvedEntity(
        id="comm-1",
        category="Communication",
        specific_type="Message",
        name="Message mentioning location",
        properties={"location_raw": "overseas"},
        summary="A message mentioning a vague location.",
    )

    await write_graph._apply_geocoding([entity])

    assert queries == ["overseas"]
    assert entity.properties["location_raw"] == "overseas"
    assert entity.properties["location_specificity"] == "unknown"
    assert entity.properties["geocoding_status"] == "failed"
    assert "latitude" not in entity.properties
    assert "longitude" not in entity.properties


@pytest.mark.asyncio
async def test_apply_geocoding_replaces_coarse_pin_after_successful_specificity_upgrade(
    monkeypatch,
):
    monkeypatch.setattr(write_graph, "GEOCODABLE_CATEGORIES", {"Location"})

    async def fake_geocode(query):
        assert query == "12 Fleet Street, London, United Kingdom"
        return GeocodeResult(
            provider="nominatim",
            normalized_query=query.lower(),
            original_query=query,
            status="success",
            latitude=51.513,
            longitude=-0.111,
            formatted_address="12 Fleet Street, London, United Kingdom",
            confidence="high",
        )

    monkeypatch.setattr(write_graph.geocoding_service, "geocode", fake_geocode)
    entity = ResolvedEntity(
        id="loc-1",
        category="Location",
        specific_type="Address",
        name="Fleet Street location",
        properties={
            "address": "12 Fleet Street",
            "city": "London",
            "country": "United Kingdom",
            "location_specificity": "exact_address",
            "latitude": 54.0,
            "longitude": -2.0,
            "_force_regeocode": True,
            "_previous_geocoding_state": {
                "location_raw": "United Kingdom",
                "location_specificity": "country",
                "latitude": 54.0,
                "longitude": -2.0,
                "geocoding_status": "success",
            },
        },
    )

    await write_graph._apply_geocoding([entity])

    assert entity.properties["latitude"] == 51.513
    assert entity.properties["longitude"] == -0.111
    assert entity.properties["location_specificity"] == "exact_address"
    assert entity.properties["geocoding_status"] == "success"


@pytest.mark.asyncio
async def test_apply_geocoding_keeps_coarse_pin_when_specificity_upgrade_fails(
    monkeypatch,
):
    monkeypatch.setattr(write_graph, "GEOCODABLE_CATEGORIES", {"Location"})

    async def fake_geocode(query):
        return GeocodeResult(
            provider="nominatim",
            normalized_query=query.lower(),
            original_query=query,
            status="failed",
        )

    monkeypatch.setattr(write_graph.geocoding_service, "geocode", fake_geocode)
    entity = ResolvedEntity(
        id="loc-1",
        category="Location",
        specific_type="Address",
        name="Fleet Street location",
        properties={
            "address": "12 Fleet Street",
            "city": "London",
            "location_specificity": "exact_address",
            "latitude": 54.0,
            "longitude": -2.0,
            "_force_regeocode": True,
            "_previous_geocoding_state": {
                "location_raw": "United Kingdom",
                "location_specificity": "country",
                "latitude": 54.0,
                "longitude": -2.0,
                "geocoding_status": "success",
                "geocoding_confidence": "high",
            },
        },
    )

    await write_graph._apply_geocoding([entity])

    assert entity.properties["latitude"] == 54.0
    assert entity.properties["longitude"] == -2.0
    assert entity.properties["location_specificity"] == "country"
    assert entity.properties["geocoding_status"] == "success"
    assert entity.properties["geocoding_confidence"] == "high"


@pytest.mark.asyncio
async def test_write_entities_persists_location_and_geocoder_signals_separately(
    monkeypatch,
):
    captured = {}

    async def fake_geocode(query):
        assert query == "Ireland"
        return GeocodeResult(
            provider="nominatim",
            normalized_query="ireland",
            original_query="Ireland",
            status="success",
            latitude=53.4,
            longitude=-8.0,
            formatted_address="Ireland",
            confidence="high",
        )

    async def fake_execute_write(query, params):
        captured["params"] = params

    monkeypatch.setattr(write_graph.geocoding_service, "geocode", fake_geocode)
    monkeypatch.setattr(write_graph.neo4j_client, "execute_write", fake_execute_write)
    entity = ResolvedEntity(
        id="ireland-1",
        category="Location",
        specific_type="Country",
        name="Ireland",
        properties={
            "location_raw": "Ireland",
            "country": "Ireland",
            "location_specificity": "country",
        },
        confidence=0.2,
    )

    await write_graph._write_entities([entity], case_id="case-1", job_id="job-1")

    node = captured["params"]["nodes"][0]
    assert node["confidence"] == 0.2
    assert node["location_specificity"] == "country"
    assert node["geocoding_confidence"] == "high"
    assert node["geocoding_status"] == "success"
