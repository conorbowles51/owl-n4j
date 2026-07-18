import pytest

from app.services import geocoding as geocoding_module
from app.services.geocoding import (
    GEOCODING_CANDIDATE_LIMIT,
    GeocodeResult,
    GeocodingService,
    build_geocode_request,
    normalize_geocode_query,
)
from app.services.location_validation import (
    GEOCODING_STATUS_MAPPED,
    GEOCODING_STATUS_REJECTED,
    GEOCODING_STATUS_UNMAPPED_RETRIABLE,
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
        result = self.cache.get((provider, normalized_query))
        if result and result.status == GEOCODING_STATUS_UNMAPPED_RETRIABLE:
            return None
        return result

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
            precision=self.provider_result.precision,
            confidence=self.provider_result.confidence,
            candidates=self.provider_result.candidates,
            rejection_reason=self.provider_result.rejection_reason,
            provider_error=self.provider_result.provider_error,
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
            status=GEOCODING_STATUS_MAPPED,
            latitude=51.5,
            longitude=-0.12,
            formatted_address="London, Greater London, England, United Kingdom",
            precision="city",
            confidence="high",
            raw_response={"lat": "51.5", "lon": "-0.12"},
        )
    )

    first = await service.geocode("London")
    second = await service.geocode("  london  ")

    assert first.status == GEOCODING_STATUS_MAPPED
    assert second.status == GEOCODING_STATUS_MAPPED
    assert service.provider_calls == 1


@pytest.mark.asyncio
async def test_invalid_address_is_cached_and_not_retried() -> None:
    service = FakeGeocodingService(
        GeocodeResult(
            provider="nominatim",
            normalized_query="ignored",
            original_query="ignored",
            status=GEOCODING_STATUS_REJECTED,
            rejection_reason="no_results",
        )
    )

    first = await service.geocode("Unknown Place XYZ")
    second = await service.geocode("unknown   place xyz")

    assert first.status == GEOCODING_STATUS_REJECTED
    assert second.status == GEOCODING_STATUS_REJECTED
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
            "addresstype": "city",
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

    assert result.status == GEOCODING_STATUS_MAPPED
    assert result.latitude == 43.7384
    assert result.longitude == 7.4246
    assert result.formatted_address == "Monaco, 98000, Monaco"
    assert result.precision == "city"
    assert result.confidence == "high"
    assert result.candidates == [
        {
            "latitude": 43.7384,
            "longitude": 7.4246,
            "formatted_address": "Monaco, 98000, Monaco",
            "precision": "city",
            "confidence": "high",
        }
    ]
    assert result.raw_response == payload


@pytest.mark.asyncio
async def test_fetch_preserves_duplicate_place_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"lat": "39.9526", "lon": "-75.1652", "display_name": "Springfield, Pennsylvania", "importance": 0.66, "type": "city"},
        {"lat": "39.7817", "lon": "-89.6501", "display_name": "Springfield, Illinois", "importance": 0.64, "type": "city"},
    ]
    request_params = []

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
            request_params.append(kwargs.get("params", {}))
            return FakeResponse()

    monkeypatch.setattr(geocoding_module.httpx, "AsyncClient", FakeClient)

    result = await GeocodingService()._fetch_from_provider("Springfield", "springfield")

    assert result.status == GEOCODING_STATUS_MAPPED
    assert request_params[0]["limit"] == GEOCODING_CANDIDATE_LIMIT
    assert len(result.candidates or []) == 2
    assert result.candidates[0]["formatted_address"] == "Springfield, Pennsylvania"
    assert result.candidates[1]["formatted_address"] == "Springfield, Illinois"


@pytest.mark.asyncio
async def test_country_only_value_records_country_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"lat": "46.2276", "lon": "2.2137", "display_name": "France", "importance": 0.9, "type": "country"},
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

    result = await GeocodingService()._fetch_from_provider("France", "france")

    assert result.status == GEOCODING_STATUS_MAPPED
    assert result.precision == "country"
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_mixed_confidence_candidates_are_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"lat": "51.5", "lon": "-0.12", "display_name": "London, UK", "importance": 0.9, "type": "city"},
        {"lat": "42.9849", "lon": "-81.2453", "display_name": "London, Ontario", "importance": 0.5, "type": "city"},
        {"lat": "0.1", "lon": "32.5", "display_name": "London Road", "importance": 0.2, "type": "road"},
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

    result = await GeocodingService()._fetch_from_provider("London", "london")

    assert [candidate["confidence"] for candidate in result.candidates or []] == ["high", "medium", "low"]


@pytest.mark.asyncio
async def test_invalid_provider_coordinates_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {"lat": "0", "lon": "0", "display_name": "Null Island", "importance": 0.9, "type": "place"},
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

    result = await GeocodingService()._fetch_from_provider("Null Island", "null island")

    assert result.status == GEOCODING_STATUS_REJECTED
    assert result.latitude is None
    assert result.longitude is None
    assert result.rejection_reason == "null_island"


@pytest.mark.asyncio
async def test_provider_failure_is_retriable_and_not_memoized() -> None:
    service = FakeGeocodingService(
        GeocodeResult(
            provider="nominatim",
            normalized_query="ignored",
            original_query="ignored",
            status=GEOCODING_STATUS_UNMAPPED_RETRIABLE,
            provider_error="network down",
        )
    )

    first = await service.geocode("London")
    second = await service.geocode("london")

    assert first.status == GEOCODING_STATUS_UNMAPPED_RETRIABLE
    assert second.status == GEOCODING_STATUS_UNMAPPED_RETRIABLE
    assert service.provider_calls == 2
