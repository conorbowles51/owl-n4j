from __future__ import annotations

import asyncio
import ipaddress
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.dependencies import async_session
from app.models.geocoding_cache import GeocodingCacheEntry
from app.pipeline.property_canonicalization import (
    canonicalize_properties,
    infer_structured_location_specificity,
    location_specificity_rank,
)

_WHITESPACE_RE = re.compile(r"\s+")
_MULTI_LOCATION_SEPARATOR_RE = re.compile(r";|\||→|->")
_RELATIVE_INTERNAL_LOCATION_RE = re.compile(
    r"\b(?:conference|meeting)\s+room\b|\bhead\s+office\b",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# Words that name no place on their own. "el hotel", "en la oficina" or "la of" is one generic word or none once
# these are left out, so it is held to the one-word rule below: a guess at the nearest feature of that name anywhere
# in the world is not a place (the bare word "notaría" in a Mexican chat was pinned to a notary office in Madrid).
_NON_PLACE_WORDS = frozenset(
    "a al at de del el en in la las lo los of on the un una".split()
)
_UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeocodeRequest:
    query: str
    location_raw: str
    location_specificity: str = "unknown"
    address: str = ""
    city: str = ""
    region: str = ""
    country: str = ""


@dataclass(frozen=True)
class GeocodeResult:
    provider: str
    normalized_query: str
    original_query: str
    status: str
    latitude: float | None = None
    longitude: float | None = None
    formatted_address: str | None = None
    confidence: str | None = None
    provider_importance: float | None = None
    location_granularity: str | None = None
    raw_response: dict[str, Any] | None = None


def normalize_geocode_query(query: str) -> str:
    return _WHITESPACE_RE.sub(" ", (query or "").strip().lower())


def _match_cache_key(request: GeocodeRequest) -> str:
    components = (
        request.query,
        request.location_specificity,
        request.address,
        request.city,
        request.region,
        request.country,
    )
    return "match-v4|" + "|".join(
        normalize_geocode_query(component) for component in components
    )


def _clean_geo_value(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value).strip())


def _extract_postcode(value: str) -> str | None:
    match = _UK_POSTCODE_RE.search(value or "")
    if not match:
        return None
    return _WHITESPACE_RE.sub("", match.group(1)).upper()


def _fold_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)
    )


def _normalize_component(value: Any) -> str:
    # Accents folded first: without it "notaría" read as the two words "notar a" and "Torreón" never matched
    # "Torreon".
    return _NON_ALNUM_RE.sub(" ", _fold_accents(str(value or "").lower())).strip()


def _place_words(value: Any) -> list[str]:
    return [token for token in _normalize_component(value).split() if token not in _NON_PLACE_WORDS]


def _component_matches(expected: str, actual: str) -> bool:
    expected_norm = _normalize_component(expected)
    actual_norm = _normalize_component(actual)
    if not expected_norm or not actual_norm:
        return False
    aliases = {
        "uk": "united kingdom",
        "gb": "united kingdom",
        "great britain": "united kingdom",
        "bvi": "british virgin islands",
        "uae": "united arab emirates",
    }
    expected_norm = aliases.get(expected_norm, expected_norm)
    actual_norm = aliases.get(actual_norm, actual_norm)
    return (
        expected_norm == actual_norm
        or expected_norm in actual_norm
        or actual_norm in expected_norm
    )


def _all_tokens_match(expected: str, actual: str) -> bool:
    expected_tokens = set(_normalize_component(expected).split())
    actual_tokens = set(_normalize_component(actual).split())
    return bool(expected_tokens) and expected_tokens <= actual_tokens


def _extract_house_number(value: str) -> str | None:
    match = re.match(r"^\s*(\d+[a-z]?)\b", value or "", re.IGNORECASE)
    return match.group(1).lower() if match else None


def _candidate_match_confidence(
    request: GeocodeRequest,
    candidate: dict[str, Any],
) -> tuple[str | None, str | None]:
    address = candidate.get("address") or {}
    display_name = str(candidate.get("display_name") or "")
    result_type = str(candidate.get("addresstype") or candidate.get("type") or "").lower()

    expected_postcode = _extract_postcode(request.address or request.query)
    candidate_postcode = _extract_postcode(str(address.get("postcode") or ""))
    if expected_postcode and candidate_postcode != expected_postcode:
        return None, "postcode_mismatch"

    expected_house_number = _extract_house_number(request.address)
    candidate_house_number = _extract_house_number(str(address.get("house_number") or ""))
    if expected_house_number and candidate_house_number != expected_house_number:
        return None, "house_number_mismatch"

    candidate_country = str(address.get("country") or address.get("country_code") or "")
    if request.country and not _component_matches(request.country, candidate_country):
        return None, "country_mismatch"

    candidate_city = str(
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("borough")
        or ""
    )
    if request.city and not (
        _component_matches(request.city, candidate_city)
        or _component_matches(request.city, display_name)
    ):
        return None, "city_mismatch"

    specificity = request.location_specificity
    if specificity == "city" and result_type not in {
        "city",
        "town",
        "village",
        "municipality",
        "borough",
        "district",
        "administrative",
    }:
        return None, "granularity_mismatch"
    if specificity == "region" and result_type not in {
        "state",
        "region",
        "county",
        "administrative",
    }:
        return None, "granularity_mismatch"
    if specificity == "country" and result_type not in {"country", "administrative"}:
        return None, "granularity_mismatch"

    raw_text = request.location_raw or request.query
    has_context = bool(request.city or request.region or request.country or request.address)
    if specificity == "unknown" and not has_context:
        # No town, region or country beside the text: one place word or none is too little to choose among the
        # features of that name worldwide, so only a settlement or an area of that name is taken.
        place_word_count = len(_place_words(raw_text))
        if place_word_count == 0:
            return None, "no_place_words"
    else:
        # With a town, region or country beside it, the word count is the plain one it always was.
        place_word_count = len(_NON_ALNUM_RE.sub(" ", raw_text.lower()).split())
    if specificity == "unknown" and place_word_count == 1 and result_type not in {
        "administrative",
        "borough",
        "city",
        "country",
        "county",
        "district",
        "island",
        "municipality",
        "region",
        "state",
        "town",
        "village",
    }:
        return None, "granularity_mismatch"

    query_text = request.location_raw or request.query
    query_matches_display = _component_matches(
        query_text, display_name
    ) or _all_tokens_match(query_text, display_name)
    if specificity == "exact_address":
        if expected_postcode or expected_house_number:
            return "high", None
        if query_matches_display:
            return "high", None
        return None, "name_mismatch"

    if request.city or request.country or request.region:
        return "high" if specificity in {"country", "region", "city"} else "medium", None
    if query_matches_display:
        return "medium", None
    return "low", None


def _location_granularity(result: dict[str, Any] | None) -> str | None:
    if not result:
        return None
    address = result.get("address") or {}
    result_type = str(result.get("type") or result.get("addresstype") or "").lower()
    if address.get("house_number") or result_type in {"house", "building"}:
        return "address"
    if address.get("road") or result_type in {"road", "street"}:
        return "street"
    if result_type in {"neighbourhood", "neighborhood", "suburb", "quarter", "hamlet"}:
        return "neighborhood"
    if result_type in {"city", "town", "village", "municipality", "borough"}:
        return "city"
    if result_type in {"county", "state", "region"}:
        return "region"
    if result_type == "country":
        return "country"
    return None


def build_geocode_request(
    category: str,
    name: str,
    properties: dict[str, Any],
) -> GeocodeRequest | None:
    normalized_properties = canonicalize_properties(category, properties)
    address = _clean_geo_value(normalized_properties.get("address"))
    city = _clean_geo_value(normalized_properties.get("city"))
    region = _clean_geo_value(normalized_properties.get("region"))
    country = _clean_geo_value(normalized_properties.get("country"))
    location_raw = _clean_geo_value(normalized_properties.get("location_raw"))
    location_specificity = _clean_geo_value(
        normalized_properties.get("location_specificity")
    ) or "unknown"

    structured_parts = [address, city]
    if not city:
        structured_parts.append(region)
    structured_parts.append(country)
    structured_query = ", ".join(part for part in structured_parts if part)
    if location_raw and _MULTI_LOCATION_SEPARATOR_RE.search(location_raw) and not structured_query:
        return None
    if (
        location_raw
        and _RELATIVE_INTERNAL_LOCATION_RE.search(location_raw)
        and not structured_query
    ):
        return None
    if (
        category == "Transaction"
        and location_raw
        and location_specificity == "unknown"
        and not structured_query
    ):
        return None
    if structured_query:
        structured_specificity = infer_structured_location_specificity(
            normalized_properties
        )
        if (
            location_raw
            and location_specificity_rank(location_specificity)
            > location_specificity_rank(structured_specificity)
        ):
            raw_normalized = normalize_geocode_query(location_raw)
            query_parts = [location_raw]
            query_parts.extend(
                part
                for part in (address, city, region, country)
                if part and normalize_geocode_query(part) not in raw_normalized
            )
            structured_query = ", ".join(query_parts)
        return GeocodeRequest(
            query=structured_query,
            location_raw=location_raw or structured_query,
            location_specificity=location_specificity,
            address=address,
            city=city,
            region=region,
            country=country,
        )

    if location_raw:
        return GeocodeRequest(
            query=location_raw,
            location_raw=location_raw,
            location_specificity=location_specificity,
            address=address,
            city=city,
            region=region,
            country=country,
        )

    location_name = _clean_geo_value(name)
    if category == "Location" and location_name:
        return GeocodeRequest(
            query=location_name,
            location_raw=location_raw or location_name,
            location_specificity=location_specificity,
            address=address,
            city=city,
            region=region,
            country=country,
        )

    return None


def recheck_cached_result(request: GeocodeRequest | None, cached: GeocodeResult) -> GeocodeResult:
    """A stored answer is held to today's checks before it places anything: answers stored before a check existed
    (or while one was broken) would otherwise keep putting the same wrong pin on every case that asks again. A stored
    success keeps the provider's chosen result in raw_response; when today's checks refuse it the answer is
    ambiguous, as a fresh lookup refusing every candidate is."""
    if request is None or cached.status != "success" or not isinstance(cached.raw_response, dict):
        return cached
    confidence, rejection = _candidate_match_confidence(request, cached.raw_response)
    if confidence is not None:
        return cached
    return GeocodeResult(
        provider=cached.provider,
        normalized_query=cached.normalized_query,
        original_query=cached.original_query,
        status="ambiguous",
        raw_response={
            "results": [cached.raw_response],
            "rejection_reason": rejection or "no_valid_candidate",
            # Marks a stored success refused by today's checks, so a case re-run clears exactly the pins it placed.
            "rechecked": True,
        },
    )


# The status an address gets when no geocoder on this server is configured: nothing was sent, nothing is cached
# (a geocoder held on this server later still gets the question), and the address is not placed.
NOT_RUN_STATUS = "not_run"
NOT_RUN_MESSAGE = "Address not placed: geocoding is not run on this server."


def held_on_this_server(url: str) -> bool:
    """Whether a service address is on this server or its private network (loopback, a private address, or a
    one-word container name), never a public host such as nominatim.openstreetmap.org."""
    try:
        host = (urlsplit(url or "").hostname or "").strip().lower()
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost" or ("." not in host and ":" not in host):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


class GeocodingService:
    def __init__(self) -> None:
        self._memoized_results: dict[tuple[str, str], GeocodeResult] = {}
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0

    @property
    def provider(self) -> str:
        return settings.geocoding_provider.strip().lower() or "nominatim"

    async def geocode(self, query: str | GeocodeRequest) -> GeocodeResult:
        request = query if isinstance(query, GeocodeRequest) else None
        original_query = _clean_geo_value(request.query if request else query)
        normalized_query = (
            _match_cache_key(request)
            if request is not None
            else normalize_geocode_query(original_query)
        )
        if not normalized_query:
            return GeocodeResult(
                provider=self.provider,
                normalized_query="",
                original_query="",
                status="failed",
            )

        memo_key = (self.provider, normalized_query)
        if memo_key in self._memoized_results:
            return self._memoized_results[memo_key]

        cached = await self._load_cached_result(self.provider, normalized_query)
        if cached is not None:
            cached = recheck_cached_result(request, cached)
            self._memoized_results[memo_key] = cached
            return cached

        if not held_on_this_server(settings.geocoding_nominatim_url):
            result = GeocodeResult(
                provider=self.provider,
                normalized_query=normalized_query,
                original_query=original_query,
                status=NOT_RUN_STATUS,
            )
            self._memoized_results[memo_key] = result
            return result

        if request is None:
            result = await self._fetch_from_provider(original_query, normalized_query)
        else:
            result = await self._fetch_from_provider(
                original_query,
                normalized_query,
                request=request,
            )
        await self._save_cached_result(result)
        self._memoized_results[memo_key] = result
        return result

    async def cached_only(self, request: GeocodeRequest) -> GeocodeResult | None:
        """The stored answer for a request, held to today's checks, without asking any geocoder (a dry run)."""
        cached = await self._load_cached_result(self.provider, _match_cache_key(request))
        return recheck_cached_result(request, cached) if cached is not None else None

    async def _load_cached_result(
        self,
        provider: str,
        normalized_query: str,
    ) -> GeocodeResult | None:
        async with async_session() as session:
            stmt = select(GeocodingCacheEntry).where(
                GeocodingCacheEntry.provider == provider,
                GeocodingCacheEntry.normalized_query == normalized_query,
            )
            record = (await session.execute(stmt)).scalar_one_or_none()

        if record is None:
            return None

        return GeocodeResult(
            provider=record.provider,
            normalized_query=record.normalized_query,
            original_query=record.original_query,
            status=record.status,
            latitude=record.latitude,
            longitude=record.longitude,
            formatted_address=record.formatted_address,
            confidence=record.confidence,
            provider_importance=(
                float((record.raw_response or {}).get("importance", 0) or 0)
                if record.status == "success"
                else None
            ),
            location_granularity=_location_granularity(record.raw_response),
            raw_response=record.raw_response,
        )

    async def _save_cached_result(self, result: GeocodeResult) -> None:
        async with async_session() as session:
            stmt = insert(GeocodingCacheEntry).values(
                provider=result.provider,
                normalized_query=result.normalized_query,
                original_query=result.original_query,
                status=result.status,
                latitude=result.latitude,
                longitude=result.longitude,
                formatted_address=result.formatted_address,
                confidence=result.confidence,
                raw_response=result.raw_response,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["provider", "normalized_query"],
                set_={
                    "original_query": result.original_query,
                    "status": result.status,
                    "latitude": result.latitude,
                    "longitude": result.longitude,
                    "formatted_address": result.formatted_address,
                    "confidence": result.confidence,
                    "raw_response": result.raw_response,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def _fetch_from_provider(
        self,
        original_query: str,
        normalized_query: str,
        request: GeocodeRequest | None = None,
    ) -> GeocodeResult:
        if self.provider != "nominatim":
            raise ValueError(f"Unsupported geocoding provider: {self.provider}")

        await self._respect_rate_limit()

        try:
            async with httpx.AsyncClient(timeout=settings.geocoding_timeout_seconds) as client:
                response = await client.get(
                    settings.geocoding_nominatim_url,
                    params={
                        "q": original_query,
                        "format": "json",
                        "limit": 5,
                        "addressdetails": 1,
                    },
                    headers={
                        "User-Agent": settings.geocoding_user_agent,
                        "Accept": "application/json",
                        "Accept-Language": "en",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return GeocodeResult(
                provider=self.provider,
                normalized_query=normalized_query,
                original_query=original_query,
                status="failed",
            )

        if not payload:
            return GeocodeResult(
                provider=self.provider,
                normalized_query=normalized_query,
                original_query=original_query,
                status="failed",
                raw_response={"results": []},
            )

        top_result = payload[0]
        match_confidence: str | None = None
        if request is not None:
            confidence_rank = {"low": 1, "medium": 2, "high": 3}
            accepted: list[tuple[int, int, dict[str, Any], str]] = []
            rejection_reasons: list[str] = []
            for index, candidate in enumerate(payload):
                candidate_confidence, candidate_rejection = _candidate_match_confidence(
                    request,
                    candidate,
                )
                if candidate_confidence is None:
                    if candidate_rejection:
                        rejection_reasons.append(candidate_rejection)
                    continue
                accepted.append(
                    (
                        confidence_rank[candidate_confidence],
                        -index,
                        candidate,
                        candidate_confidence,
                    )
                )
            if not accepted:
                return GeocodeResult(
                    provider=self.provider,
                    normalized_query=normalized_query,
                    original_query=original_query,
                    status="ambiguous",
                    raw_response={
                        "results": payload,
                        "rejection_reason": (
                            rejection_reasons[0]
                            if rejection_reasons
                            else "no_valid_candidate"
                        ),
                    },
                )
            _, _, top_result, match_confidence = max(accepted, key=lambda item: item[:2])
        importance = float(top_result.get("importance", 0) or 0)
        confidence = match_confidence or self._confidence_from_importance(importance)
        return GeocodeResult(
            provider=self.provider,
            normalized_query=normalized_query,
            original_query=original_query,
            status="success",
            latitude=float(top_result["lat"]),
            longitude=float(top_result["lon"]),
            formatted_address=top_result.get("display_name", original_query),
            confidence=confidence,
            provider_importance=importance,
            location_granularity=_location_granularity(top_result),
            raw_response=top_result,
        )

    async def _respect_rate_limit(self) -> None:
        async with self._rate_limit_lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            self._last_request_time = time.monotonic()

    @staticmethod
    def _confidence_from_importance(importance: float) -> str:
        if importance > 0.7:
            return "high"
        if importance > 0.4:
            return "medium"
        return "low"


geocoding_service = GeocodingService()
