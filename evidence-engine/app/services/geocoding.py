from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.dependencies import async_session
from app.models.geocoding_cache import GeocodingCacheEntry

_WHITESPACE_RE = re.compile(r"\s+")
_VAGUE_LOCATION_TERMS = {
    "abroad",
    "around town",
    "city center",
    "conference room",
    "elsewhere",
    "everywhere",
    "headquarters",
    "home",
    "international",
    "multiple locations",
    "nationwide",
    "office",
    "offshore",
    "online",
    "overseas",
    "remote",
    "residence",
    "somewhere",
    "statewide",
    "the area",
    "the city",
    "unknown",
    "unspecified",
    "various locations",
    "warehouse",
    "worldwide",
}


@dataclass(frozen=True)
class GeocodeRequest:
    query: str
    location_raw: str


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
    raw_response: dict[str, Any] | None = None


def normalize_geocode_query(query: str) -> str:
    return _WHITESPACE_RE.sub(" ", (query or "").strip().lower())


def _clean_geo_value(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value).strip())


def _is_specific_location_text(value: str) -> bool:
    cleaned = _clean_geo_value(value)
    if not cleaned:
        return False
    return normalize_geocode_query(cleaned) not in _VAGUE_LOCATION_TERMS


def build_geocode_request(
    category: str,
    name: str,
    properties: dict[str, Any],
) -> GeocodeRequest | None:
    address = _clean_geo_value(properties.get("address"))
    city = _clean_geo_value(properties.get("city"))
    region = _clean_geo_value(properties.get("region"))
    country = _clean_geo_value(properties.get("country"))
    location_raw = _clean_geo_value(properties.get("location_raw"))

    structured_query = ", ".join(part for part in (address, city, region, country) if part)
    if structured_query and _is_specific_location_text(structured_query):
        return GeocodeRequest(
            query=structured_query,
            location_raw=location_raw or structured_query,
        )

    city_query = ", ".join(part for part in (city, region, country) if part)
    if city_query and _is_specific_location_text(city_query):
        return GeocodeRequest(
            query=city_query,
            location_raw=location_raw or city_query,
        )

    if location_raw and _is_specific_location_text(location_raw):
        return GeocodeRequest(query=location_raw, location_raw=location_raw)

    location_name = _clean_geo_value(name)
    if category == "Location" and location_name and _is_specific_location_text(location_name):
        return GeocodeRequest(query=location_name, location_raw=location_raw or location_name)

    return None


class GeocodingService:
    def __init__(self) -> None:
        self._memoized_results: dict[tuple[str, str], GeocodeResult] = {}
        self._rate_limit_lock = asyncio.Lock()
        self._last_request_time = 0.0

    @property
    def provider(self) -> str:
        return settings.geocoding_provider.strip().lower() or "nominatim"

    async def geocode(self, query: str) -> GeocodeResult:
        original_query = _clean_geo_value(query)
        normalized_query = normalize_geocode_query(original_query)
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
            self._memoized_results[memo_key] = cached
            return cached

        result = await self._fetch_from_provider(original_query, normalized_query)
        await self._save_cached_result(result)
        self._memoized_results[memo_key] = result
        return result

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
                        "limit": 1,
                        "addressdetails": 1,
                    },
                    headers={
                        "User-Agent": settings.geocoding_user_agent,
                        "Accept": "application/json",
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
        importance = float(top_result.get("importance", 0) or 0)
        confidence = self._confidence_from_importance(importance)
        return GeocodeResult(
            provider=self.provider,
            normalized_query=normalized_query,
            original_query=original_query,
            status="success",
            latitude=float(top_result["lat"]),
            longitude=float(top_result["lon"]),
            formatted_address=top_result.get("display_name", original_query),
            confidence=confidence,
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
