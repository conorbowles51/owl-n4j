"""Bare generic words are not places: the checks that refuse them, on stored answers too, and the case re-run that
clears the pins they placed (followups m11090937097381: "notaría" in a Mexican chat was pinned to a notary office in
Madrid, and 72 more such pins on 7 cases)."""
import asyncio

import pytest

from app.services import geocoding as geocoding_module
from app.services.geocoding import (
    GeocodeRequest,
    GeocodeResult,
    GeocodingService,
    _candidate_match_confidence,
    _match_cache_key,
    recheck_cached_result,
)

MADRID_NOTARY = {
    "lat": "40.4569421",
    "lon": "-3.7039229",
    "addresstype": "office",
    "type": "notary",
    "importance": 8.58e-05,
    "display_name": "Notaría, Calle de Lope de Haro, Berruguete, Tetuán, Madrid, 28039, Spain",
    "address": {"office": "Notaría", "road": "Calle de Lope de Haro", "city": "Madrid", "country": "Spain"},
}
COLOMBIA_HAMLET = {
    "lat": "1.1", "lon": "-74.0", "addresstype": "hamlet", "type": "hamlet", "importance": 0.13,
    "display_name": "El Hotel, Cartagena del Chairá, Caquetá, Colombia",
    "address": {"hamlet": "El Hotel", "country": "Colombia"},
}
LA_CITY = {
    "lat": "34.05", "lon": "-118.24", "addresstype": "city", "type": "administrative", "importance": 0.84,
    "display_name": "Los Angeles, Los Angeles County, California, United States",
    "address": {"city": "Los Angeles", "country": "United States"},
}
POLANCO = {
    "lat": "19.43", "lon": "-99.19", "addresstype": "suburb", "type": "suburb", "importance": 0.4,
    "display_name": "Polanco, Miguel Hidalgo, Mexico City, Mexico",
    "address": {"suburb": "Polanco", "city": "Mexico City", "country": "Mexico"},
}


def _req(raw: str, **kw) -> GeocodeRequest:
    return GeocodeRequest(query=kw.pop("query", raw), location_raw=raw, location_specificity="unknown", **kw)


def test_accented_single_word_is_one_word() -> None:
    # Old code read "notaría" as "notar a", two words, and took the Madrid notary office.
    assert _candidate_match_confidence(_req("notaría"), MADRID_NOTARY) == (None, "granularity_mismatch")


def test_article_and_generic_word_is_one_word() -> None:
    assert _candidate_match_confidence(_req("el hotel"), COLOMBIA_HAMLET) == (None, "granularity_mismatch")
    assert _candidate_match_confidence(_req("En la oficina"), COLOMBIA_HAMLET)[0] is None


def test_text_with_no_place_word_is_refused() -> None:
    assert _candidate_match_confidence(_req("la of"), LA_CITY) == (None, "no_place_words")


def test_named_place_with_its_city_still_placed() -> None:
    assert _candidate_match_confidence(_req("Polanco, Mexico City, Mexico"), POLANCO)[0] is not None


def test_word_count_with_context_is_unchanged() -> None:
    # A town beside it: the plain word count, as before ("el hotel" with a city is two words, not one).
    request = _req("el hotel", city="Cartagena del Chairá", query="el hotel, Cartagena del Chairá")
    assert _candidate_match_confidence(request, {**COLOMBIA_HAMLET, "address": {
        "hamlet": "El Hotel", "town": "Cartagena del Chairá", "country": "Colombia"}})[0] is not None


def test_accents_no_longer_break_a_city_match() -> None:
    request = GeocodeRequest(query="Calle 1, Torreón, Mexico", location_raw="Calle 1, Torreón, Mexico",
                             location_specificity="city", city="Torreon", country="Mexico")
    candidate = {"addresstype": "city", "type": "administrative", "display_name": "Torreón, Coahuila, Mexico",
                 "address": {"city": "Torreón", "country": "México"}}
    assert _candidate_match_confidence(request, candidate)[0] is not None


def _stored(raw: dict) -> GeocodeResult:
    return GeocodeResult(provider="nominatim", normalized_query="k", original_query="notaría", status="success",
                         latitude=float(raw["lat"]), longitude=float(raw["lon"]),
                         formatted_address=raw["display_name"], confidence="medium", raw_response=raw)


def test_stored_success_refused_today_is_ambiguous_and_marked() -> None:
    result = recheck_cached_result(_req("notaría"), _stored(MADRID_NOTARY))
    assert result.status == "ambiguous"
    assert result.latitude is None
    assert result.raw_response["rechecked"] is True
    assert result.raw_response["rejection_reason"] == "granularity_mismatch"


def test_stored_success_still_right_is_unchanged() -> None:
    stored = _stored(POLANCO)
    assert recheck_cached_result(_req("Polanco, Mexico City, Mexico"), stored) is stored


class _CacheOnly(GeocodingService):
    def __init__(self, cache: dict[str, GeocodeResult]) -> None:
        super().__init__()
        self.cache = cache
        self.provider_calls = 0

    async def _load_cached_result(self, provider, normalized_query):
        return self.cache.get(normalized_query)

    async def _save_cached_result(self, result):
        raise AssertionError("a stored answer is never written back")

    async def _fetch_from_provider(self, *args, **kwargs):
        self.provider_calls += 1
        raise AssertionError("no geocoder is asked")


def test_geocode_holds_a_stored_answer_to_todays_checks() -> None:
    request = _req("notaría")
    service = _CacheOnly({_match_cache_key(request): _stored(MADRID_NOTARY)})
    result = asyncio.run(service.geocode(request))
    assert result.status == "ambiguous"
    assert asyncio.run(service.cached_only(request)).status == "ambiguous"
    assert service.provider_calls == 0


@pytest.mark.no_geocoder_here
def test_case_rerun_only_refused_clears_exactly_the_refused_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import regeocode_case as rc

    notary = _req("notaría")
    polanco = _req("Polanco, Mexico City, Mexico")
    service = _CacheOnly({_match_cache_key(notary): _stored(MADRID_NOTARY),
                          _match_cache_key(polanco): _stored(POLANCO)})
    monkeypatch.setattr(rc, "geocoding_service", service)
    monkeypatch.setattr(rc, "_GEOCODABLE_CATEGORIES", {"Event", "Transaction", "Location"})
    rows = [
        {"key": "e1", "name": "Notary appointment", "category": "Event",
         # The stored properties of a live pin (case d5b330d1), as written by an ingestion.
         "properties": {"location_raw": "notaría", "location_specificity": "unknown", "latitude": 40.4569421,
                        "longitude": -3.7039229, "location_formatted": MADRID_NOTARY["display_name"],
                        "geocoding_formatted_address": MADRID_NOTARY["display_name"],
                        "geocoding_provider": "nominatim", "geocoding_query": "notaría",
                        "location_granularity": "street", "geocoding_provider_importance": 8.58e-05,
                        "geocoding_confidence": "medium", "geocoding_status": "success"}},
        {"key": "l1", "name": "Office", "category": "Location",
         "properties": {"location_raw": "Polanco, Mexico City, Mexico", "location_specificity": "unknown",
                        "latitude": 19.43, "longitude": -99.19}},
        # Not geocodable (a transaction with an unknown place): left alone in this mode, pin and all.
        {"key": "t1", "name": "Payment", "category": "Transaction",
         "properties": {"location_raw": "Notaría", "location_specificity": "unknown", "latitude": 23.6,
                        "longitude": -102.0}},
        # Nothing stored for it: left alone.
        {"key": "l2", "name": "Querétaro", "category": "Location",
         "properties": {"location_raw": "Queretaro, Mexico", "location_specificity": "city", "latitude": 20.5,
                        "longitude": -100.4}},
    ]
    writes: list[tuple[str, dict]] = []

    async def query(cypher, params):
        return rows

    async def write(cypher, params):
        writes.append((cypher, params))

    monkeypatch.setattr(rc.neo4j_client, "execute_query", query)
    monkeypatch.setattr(rc.neo4j_client, "execute_write", write)

    report = asyncio.run(rc.regeocode_case("case-1", apply=True, only_refused=True))

    assert [p["key"] for _, p in writes] == ["e1"]
    cypher, params = writes[0]
    assert "REMOVE n.latitude" in cypher
    assert params["status"] == "ambiguous"
    assert params["location_raw"] == "notaría"  # the text read from the evidence stays
    assert report["counts"]["cleared_refused"] == 1
    assert service.provider_calls == 0
