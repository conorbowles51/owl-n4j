import pytest

from app.pipeline import contextual_geocoding
from app.pipeline.chunk_embed import TextChunk
from app.pipeline.contextual_geocoding import apply_contextual_geocoding
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship
from app.services.geocoding import GeocodeResult


def _chunk(text: str, index: int = 0, page_start: int | None = 1) -> TextChunk:
    return TextChunk(
        text=text,
        index=index,
        start_char=0,
        end_char=len(text),
        metadata={"page_start": page_start, "page_end": page_start},
    )


def _candidate(
    query: str,
    lat: float = 51.5007,
    lon: float = -0.1246,
    place_class: str = "building",
    place_type: str = "yes",
    importance: float = 0.85,
) -> GeocodeResult:
    return GeocodeResult(
        provider="nominatim",
        normalized_query=query.lower(),
        original_query=query,
        status="success",
        latitude=lat,
        longitude=lon,
        formatted_address=f"{query}, formatted",
        confidence="high" if importance > 0.7 else "medium",
        raw_response={
            "lat": str(lat),
            "lon": str(lon),
            "display_name": f"{query}, formatted",
            "class": place_class,
            "type": place_type,
            "importance": importance,
            "address": {"road": "Bridge Street", "house_number": "10"},
        },
    )


@pytest.mark.asyncio
async def test_contextual_geocoding_rejects_letterhead_address(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_existing(case_id: str):
        return []

    async def should_not_geocode(query: str, limit: int = 5):
        raise AssertionError("document artifact should be rejected before geocoding")

    monkeypatch.setattr(contextual_geocoding.neo4j_client, "get_case_geocoded_locations", no_existing)
    monkeypatch.setattr(contextual_geocoding.geocoding_service, "geocode_candidates", should_not_geocode)

    entity = ResolvedEntity(
        id="loc-letterhead",
        category="Location",
        specific_type="",
        name="12 Corporate Plaza",
        properties={"address": "12 Corporate Plaza", "city": "London"},
        source_quotes=["Registered office: 12 Corporate Plaza. Tel. +44 20 0000 0000"],
        source_files=["letter.pdf"],
    )

    summary, remaps = await apply_contextual_geocoding(
        [entity],
        [],
        "case-1",
        chunks=[_chunk("Registered office: 12 Corporate Plaza\nTel. +44 20 0000 0000")],
    )

    assert remaps == {}
    assert entity.properties["geocoding_status"] == "rejected"
    assert entity.properties["geocoding_granularity"] == "document_artifact"
    assert entity.properties["geocoding_reason"] == "document_artifact_or_boilerplate"
    assert summary["geocoding"]["counts"]["rejected"] == 1


@pytest.mark.asyncio
async def test_contextual_geocoding_dedupes_same_place_with_different_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_existing(case_id: str):
        return []

    async def fake_geocode(query: str, limit: int = 5):
        return [_candidate(query)]

    monkeypatch.setattr(contextual_geocoding.neo4j_client, "get_case_geocoded_locations", no_existing)
    monkeypatch.setattr(contextual_geocoding.geocoding_service, "geocode_candidates", fake_geocode)

    first = ResolvedEntity(
        id="loc-a",
        category="Location",
        specific_type="",
        name="10 Bridge Street",
        properties={"address": "10 Bridge Street", "city": "London"},
        source_files=["a.pdf"],
    )
    second = ResolvedEntity(
        id="loc-b",
        category="Location",
        specific_type="",
        name="Bridge St office",
        properties={"address": "10 Bridge St", "city": "London"},
        source_files=["b.pdf"],
    )

    summary, remaps = await apply_contextual_geocoding([first, second], [], "case-1")

    assert remaps == {"loc-b": "loc-a"}
    assert second.properties["geocoding_decision"] == "deduped"
    assert second.properties["geocoding_deduped_to"] == "loc-a"
    assert summary["geocoding"]["counts"]["deduped"] == 1


@pytest.mark.asyncio
async def test_contextual_geocoding_accepts_exact_address_with_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_existing(case_id: str):
        return []

    async def fake_geocode(query: str, limit: int = 5):
        return [_candidate(query, importance=0.86)]

    monkeypatch.setattr(contextual_geocoding.neo4j_client, "get_case_geocoded_locations", no_existing)
    monkeypatch.setattr(contextual_geocoding.geocoding_service, "geocode_candidates", fake_geocode)

    entity = ResolvedEntity(
        id="loc-exact",
        category="Location",
        specific_type="",
        name="10 Bridge Street",
        properties={"address": "10 Bridge Street", "city": "London"},
        source_files=["case.pdf"],
    )

    summary, _ = await apply_contextual_geocoding([entity], [], "case-1")

    assert entity.properties["geocoding_status"] == "success"
    assert entity.properties["geocoding_confidence"] == "high"
    assert entity.properties["geocoding_granularity"] == "street_address"
    assert entity.properties["geocoding_precision"] == "exact"
    assert summary["geocoding"]["counts"]["accepted"] == 1


@pytest.mark.asyncio
async def test_contextual_geocoding_marks_country_only_needs_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_existing(case_id: str):
        return []

    async def fake_geocode(query: str, limit: int = 5):
        result = _candidate(
            query,
            lat=46.6034,
            lon=1.8883,
            place_class="place",
            place_type="country",
            importance=0.92,
        )
        result.raw_response["address"] = {"country": "France", "country_code": "fr"}
        return [result]

    monkeypatch.setattr(contextual_geocoding.neo4j_client, "get_case_geocoded_locations", no_existing)
    monkeypatch.setattr(contextual_geocoding.geocoding_service, "geocode_candidates", fake_geocode)

    entity = ResolvedEntity(
        id="loc-country",
        category="Location",
        specific_type="",
        name="France",
        properties={"country": "France"},
        source_files=["case.pdf"],
    )

    summary, _ = await apply_contextual_geocoding([entity], [], "case-1")

    assert entity.properties["geocoding_status"] == "needs_review"
    assert entity.properties["geocoding_granularity"] == "country_only"
    assert "latitude" not in entity.properties
    assert summary["geocoding"]["counts"]["needs_review"] == 1
