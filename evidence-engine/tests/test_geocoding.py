import pytest

from app.services import geocoding as geocoding_module
from app.services.geocoding import (
    GeocodeResult,
    GeocodingService,
    build_geocode_request,
    normalize_geocode_query,
)


class FakeGeocodingService(GeocodingService):
    def __init__(self, result: GeocodeResult) -> None:
        super().__init__()
        self.provider_result = result
        self.cache: dict[tuple[str, str], GeocodeResult] = {}
        self.provider_calls = 0

    async def _load_cached_result(
        self,
        provider: str,
        normalized_query: str,
    ) -> GeocodeResult | None:
        return self.cache.get((provider, normalized_query))

    async def _save_cached_result(self, result: GeocodeResult) -> None:
        self.cache[(result.provider, result.normalized_query)] = result

    async def _fetch_from_provider(
        self,
        original_query: str,
        normalized_query: str,
    ) -> GeocodeResult:
        self.provider_calls += 1
        return GeocodeResult(
            provider=self.provider_result.provider,
            normalized_query=normalized_query,
            original_query=original_query,
            status=self.provider_result.status,
            latitude=self.provider_result.latitude,
            longitude=self.provider_result.longitude,
            formatted_address=self.provider_result.formatted_address,
            confidence=self.provider_result.confidence,
            raw_response=self.provider_result.raw_response,
        )


def test_normalize_geocode_query_collapses_case_and_whitespace() -> None:
    assert normalize_geocode_query("  123  Fleet Street,   London  ") == "123 fleet street, london"


def test_build_geocode_request_prefers_structured_fields() -> None:
    request = build_geocode_request(
        "Organization",
        "Nexus Trading",
        {
            "location_raw": "Monaco office",
            "address": "12 Quai Antoine",
            "city": "Monaco",
            "country": "Monaco",
        },
    )

    assert request is not None
    assert request.query == "12 Quai Antoine, Monaco, Monaco"
    assert request.location_raw == "Monaco office"


def test_build_geocode_request_uses_location_name_only_for_locations() -> None:
    non_location = build_geocode_request("Event", "Monaco", {})
    location = build_geocode_request("Location", "Monaco", {})

    assert non_location is None
    assert location is not None
    assert location.query == "Monaco"
    assert location.location_raw == "Monaco"


def test_build_geocode_request_rejects_vague_location_text() -> None:
    request = build_geocode_request(
        "Communication",
        "Meeting",
        {"location_raw": "overseas"},
    )

    assert request is None


@pytest.mark.asyncio
async def test_geocode_uses_cache_after_first_success() -> None:
    service = FakeGeocodingService(
        GeocodeResult(
            provider="nominatim",
            normalized_query="ignored",
            original_query="ignored",
            status="success",
            latitude=51.5,
            longitude=-0.12,
            formatted_address="London, Greater London, England, United Kingdom",
            confidence="high",
            raw_response={"lat": "51.5", "lon": "-0.12"},
        )
    )

    first = await service.geocode("London")
    second = await service.geocode("  london  ")

    assert first.status == "success"
    assert second.status == "success"
    assert service.provider_calls == 1


@pytest.mark.asyncio
async def test_failed_geocode_is_cached_and_not_retried() -> None:
    service = FakeGeocodingService(
        GeocodeResult(
            provider="nominatim",
            normalized_query="ignored",
            original_query="ignored",
            status="failed",
        )
    )

    first = await service.geocode("Unknown Place XYZ")
    second = await service.geocode("unknown   place xyz")

    assert first.status == "failed"
    assert second.status == "failed"
    assert service.provider_calls == 1


@pytest.mark.asyncio
async def test_fetch_from_provider_maps_nominatim_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "lat": "43.7384",
            "lon": "7.4246",
            "display_name": "Monaco, 98000, Monaco",
            "importance": 0.82,
            "type": "city",
        }
    ]

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(geocoding_module.httpx, "AsyncClient", FakeClient)

    service = GeocodingService()
    result = await service._fetch_from_provider("Monaco", "monaco")

    assert result.status == "success"
    assert result.latitude == 43.7384
    assert result.longitude == 7.4246
    assert result.formatted_address == "Monaco, 98000, Monaco"
    assert result.confidence == "high"
    assert result.raw_response == payload[0]
