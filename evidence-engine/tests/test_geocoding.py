import pytest

from app.services import geocoding as geocoding_module
from app.services.geocoding import (
    GeocodeResult,
    GeocodingService,
    _candidate_match_confidence,
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
            location_granularity=self.provider_result.location_granularity,
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
    assert request.location_specificity == "exact_address"


def test_build_geocode_request_uses_location_name_only_for_locations() -> None:
    non_location = build_geocode_request("Event", "Monaco", {})
    location = build_geocode_request("Location", "Monaco", {})

    assert non_location is None
    assert location is not None
    assert location.query == "Monaco"
    assert location.location_raw == "Monaco"
    assert location.location_specificity == "unknown"


def test_build_geocode_request_accepts_vague_location_text() -> None:
    request = build_geocode_request(
        "Communication",
        "Meeting",
        {"location_raw": "overseas"},
    )

    assert request is not None
    assert request.query == "overseas"
    assert request.location_specificity == "unknown"


def test_build_geocode_request_rejects_combined_location_values() -> None:
    request = build_geocode_request(
        "Communication",
        "Email discussing two jurisdictions",
        {
            "location_raw": "Monaco; Luxembourg",
            "location_specificity": "country",
        },
    )

    assert request is None


def test_build_geocode_request_does_not_treat_transaction_counterparty_as_place() -> None:
    request = build_geocode_request(
        "Transaction",
        "Transfer to Cayman National Bank",
        {
            "location_raw": "Cayman National Bank",
            "location_specificity": "unknown",
        },
    )

    assert request is None


def test_build_geocode_request_rejects_relative_internal_room_without_address() -> None:
    request = build_geocode_request(
        "Event",
        "Internal interview",
        {
            "location_raw": "Conference Room B, Head Office",
            "location_specificity": "exact_address",
        },
    )

    assert request is None


def test_build_geocode_request_omits_redundant_region_when_city_is_present() -> None:
    request = build_geocode_request(
        "Location",
        "Dubai",
        {
            "city": "Dubai",
            "region": "Emirate of Dubai",
            "country": "United Arab Emirates",
            "location_raw": "Dubai",
            "location_specificity": "city",
        },
    )

    assert request is not None
    assert request.query == "Dubai, United Arab Emirates"


def test_candidate_city_can_match_the_displayed_admin_area() -> None:
    request = build_geocode_request(
        "Location",
        "Mayfair",
        {
            "city": "London",
            "country": "United Kingdom",
            "location_raw": "Mayfair",
            "location_specificity": "district",
        },
    )
    assert request is not None

    confidence, rejection = _candidate_match_confidence(
        request,
        {
            "display_name": (
                "Mayfair, City of Westminster, Greater London, England, "
                "United Kingdom"
            ),
            "type": "suburb",
            "addresstype": "suburb",
            "address": {
                "suburb": "Mayfair",
                "city": "City of Westminster",
                "country": "United Kingdom",
            },
        },
    )

    assert confidence == "medium"
    assert rejection is None


def test_named_exact_place_matches_when_all_name_tokens_are_in_display() -> None:
    request = build_geocode_request(
        "Event",
        "Meeting",
        {
            "location_raw": "The Wolseley, Mayfair",
            "location_specificity": "exact_address",
        },
    )
    assert request is not None

    confidence, rejection = _candidate_match_confidence(
        request,
        {
            "display_name": (
                "The Wolseley, 157-160 Piccadilly, Westminster, Mayfair, "
                "United Kingdom"
            ),
            "type": "restaurant",
            "addresstype": "amenity",
            "address": {"country": "United Kingdom"},
        },
    )

    assert confidence == "high"
    assert rejection is None


def test_unknown_single_word_place_does_not_match_a_same_named_business_or_road() -> None:
    request = build_geocode_request(
        "Location",
        "Cayman",
        {"location_raw": "Cayman", "location_specificity": "unknown"},
    )
    assert request is not None

    confidence, rejection = _candidate_match_confidence(
        request,
        {
            "display_name": "Cayman, Serua Indah, Banten, Indonesia",
            "type": "residential",
            "addresstype": "residential",
            "address": {"country": "Indonesia"},
        },
    )

    assert confidence is None
    assert rejection == "granularity_mismatch"


def test_build_geocode_request_preserves_ai_continent_specificity() -> None:
    request = build_geocode_request(
        "Location",
        "Europe",
        {"location_raw": "Europe", "location_specificity": "continent"},
    )

    assert request is not None
    assert request.query == "Europe"
    assert request.location_specificity == "continent"


def test_build_geocode_request_keeps_finer_raw_detail_with_structured_context() -> None:
    request = build_geocode_request(
        "Location",
        "Temple Bar",
        {
            "location_raw": "Temple Bar",
            "city": "Dublin",
            "country": "Ireland",
            "location_specificity": "district",
        },
    )

    assert request is not None
    assert request.query == "Temple Bar, Dublin, Ireland"
    assert request.location_specificity == "district"


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
    assert result.location_granularity == "city"
    assert result.raw_response == payload[0]


@pytest.mark.asyncio
async def test_geocode_rejects_result_with_conflicting_postcode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [
        {
            "lat": "51.6081736",
            "lon": "-0.0872343",
            "display_name": "Mayfair Gardens, Haringey, London, N17 7LP, United Kingdom",
            "importance": 0.05,
            "type": "residential",
            "address": {
                "road": "Mayfair Gardens",
                "city": "London",
                "postcode": "N17 7LP",
                "country": "United Kingdom",
                "country_code": "gb",
            },
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

    async def no_cached_result(*args, **kwargs):
        return None

    async def do_not_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(geocoding_module.httpx, "AsyncClient", FakeClient)
    service = GeocodingService()
    monkeypatch.setattr(service, "_load_cached_result", no_cached_result)
    monkeypatch.setattr(service, "_save_cached_result", do_not_persist)
    request = build_geocode_request(
        "Person",
        "Victoria Blackwood",
        {
            "address": "45 Mayfair Gardens, London, W1K 2PQ",
            "city": "London",
            "country": "United Kingdom",
            "location_specificity": "exact_address",
        },
    )
    assert request is not None

    result = await service.geocode(request)

    assert result.status == "ambiguous"
    assert result.latitude is None
    assert result.longitude is None
    assert result.confidence is None


@pytest.mark.asyncio
async def test_geocode_uses_match_quality_not_place_popularity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [
        {
            "lat": "51.5073927",
            "lon": "-0.1409072",
            "display_name": "The Wolseley, Piccadilly, Mayfair, London, United Kingdom",
            "importance": 0.34,
            "type": "restaurant",
            "address": {
                "amenity": "The Wolseley",
                "road": "Piccadilly",
                "city": "London",
                "country": "United Kingdom",
                "country_code": "gb",
            },
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

    async def no_cached_result(*args, **kwargs):
        return None

    async def do_not_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(geocoding_module.httpx, "AsyncClient", FakeClient)
    service = GeocodingService()
    monkeypatch.setattr(service, "_load_cached_result", no_cached_result)
    monkeypatch.setattr(service, "_save_cached_result", do_not_persist)
    request = build_geocode_request(
        "Location",
        "The Wolseley",
        {
            "location_raw": "The Wolseley",
            "location_specificity": "exact_address",
        },
    )
    assert request is not None

    result = await service.geocode(request)

    assert result.status == "success"
    assert result.confidence == "high"
    assert result.provider_importance == 0.34


@pytest.mark.asyncio
async def test_geocode_selects_matching_candidate_instead_of_first_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = [
        {
            "lat": "51.60",
            "lon": "-0.08",
            "display_name": "Mayfair Gardens, London, N17 7LP, United Kingdom",
            "importance": 0.9,
            "type": "residential",
            "address": {
                "road": "Mayfair Gardens",
                "city": "London",
                "postcode": "N17 7LP",
                "country": "United Kingdom",
            },
        },
        {
            "lat": "51.51",
            "lon": "-0.14",
            "display_name": "45 Mayfair Gardens, London, W1K 2PQ, United Kingdom",
            "importance": 0.01,
            "type": "house",
            "address": {
                "house_number": "45",
                "road": "Mayfair Gardens",
                "city": "London",
                "postcode": "W1K 2PQ",
                "country": "United Kingdom",
            },
        },
    ]
    requested_limits: list[int] = []
    requested_languages: list[str] = []

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
            requested_limits.append(kwargs["params"]["limit"])
            requested_languages.append(kwargs["headers"]["Accept-Language"])
            return FakeResponse()

    async def no_cached_result(*args, **kwargs):
        return None

    async def do_not_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(geocoding_module.httpx, "AsyncClient", FakeClient)
    service = GeocodingService()
    monkeypatch.setattr(service, "_load_cached_result", no_cached_result)
    monkeypatch.setattr(service, "_save_cached_result", do_not_persist)
    request = build_geocode_request(
        "Person",
        "Victoria Blackwood",
        {
            "address": "45 Mayfair Gardens, London, W1K 2PQ",
            "city": "London",
            "country": "United Kingdom",
            "location_specificity": "exact_address",
        },
    )
    assert request is not None

    result = await service.geocode(request)

    assert requested_limits == [5]
    assert requested_languages == ["en"]
    assert result.status == "success"
    assert result.latitude == 51.51
    assert result.longitude == -0.14
    assert result.confidence == "high"
    assert result.provider_importance == 0.01


@pytest.mark.asyncio
async def test_structured_geocode_uses_versioned_match_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_cache_keys: list[str] = []

    async def load_cached(provider: str, normalized_query: str):
        seen_cache_keys.append(normalized_query)
        return None

    async def save_cached(result):
        return None

    async def fetch_result(original_query, normalized_query, request=None):
        return GeocodeResult(
            provider="nominatim",
            normalized_query=normalized_query,
            original_query=original_query,
            status="success",
            latitude=51.5,
            longitude=-0.1,
            formatted_address="The Wolseley, London, United Kingdom",
            confidence="high",
        )

    service = GeocodingService()
    monkeypatch.setattr(service, "_load_cached_result", load_cached)
    monkeypatch.setattr(service, "_save_cached_result", save_cached)
    monkeypatch.setattr(service, "_fetch_from_provider", fetch_result)
    request = build_geocode_request(
        "Location",
        "The Wolseley",
        {
            "location_raw": "The Wolseley",
            "location_specificity": "exact_address",
        },
    )
    assert request is not None

    await service.geocode(request)

    assert seen_cache_keys == ["match-v4|the wolseley|exact_address||||"]
