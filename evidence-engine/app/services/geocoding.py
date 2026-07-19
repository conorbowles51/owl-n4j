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
from app.pipeline.property_canonicalization import (
    canonicalize_properties,
    infer_structured_location_specificity,
    location_specificity_rank,
)

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class GeocodeRequest:
    query: str
    location_raw: str
    location_specificity: str = "unknown"


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
    confidence_score: float | None = None
    location_granularity: str | None = None
    raw_response: dict[str, Any] | None = None


def _importance_from_raw_response(raw_response: Any) -> float | None:
    """Recover the provider's raw importance score from a cached response."""
    if not isinstance(raw_response, dict):
        return None
    try:
        importance = raw_response.get("importance")
        return float(importance) if importance is not None else None
    except (TypeError, ValueError):
        return None


def normalize_geocode_query(query: str) -> str:
    return _WHITESPACE_RE.sub(" ", (query or "").strip().lower())


def _clean_geo_value(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE_RE.sub(" ", str(value).strip())


def _top_row_from_raw_response(raw_response: Any) -> dict[str, Any] | None:
    """Return the top provider row from either raw-response cache format.

    Newer cache entries store ``{"results": [...], "requested_limit": n}``;
    older entries store the top result row directly.
    """
    if not isinstance(raw_response, dict):
        return None
    rows = raw_response.get("results")
    if isinstance(rows, list):
        return rows[0] if rows and isinstance(rows[0], dict) else None
    return raw_response or None


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

    structured_query = ", ".join(part for part in (address, city, region, country) if part)
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
        )

    if location_raw:
        return GeocodeRequest(
            query=location_raw,
            location_raw=location_raw,
            location_specificity=location_specificity,
        )

    location_name = _clean_geo_value(name)
    if category == "Location" and location_name:
        return GeocodeRequest(
            query=location_name,
            location_raw=location_raw or location_name,
            location_specificity=location_specificity,
        )

    return None


class GeocodingService:
    def __init__(self) -> None:
        self._memoized_results: dict[tuple[str, str], GeocodeResult] = {}
        self._memoized_candidates: dict[tuple[str, str, int], list[GeocodeResult]] = {}
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

        cached = await self._load_cached_result(self.provider, normalized_query, required_limit=1)
        if cached is not None:
            self._memoized_results[memo_key] = cached
            return cached

        result = await self._fetch_from_provider(original_query, normalized_query, limit=1)
        await self._save_cached_result(result)
        self._memoized_results[memo_key] = result
        return result

    async def geocode_candidates(self, query: str, limit: int = 5) -> list[GeocodeResult]:
        original_query = _clean_geo_value(query)
        normalized_query = normalize_geocode_query(original_query)
        limit = max(1, min(int(limit or 1), 10))
        if not normalized_query:
            return []

        memo_key = (self.provider, normalized_query, limit)
        if memo_key in self._memoized_candidates:
            return self._memoized_candidates[memo_key]

        result = await self._load_cached_result(
            self.provider,
            normalized_query,
            required_limit=limit,
        )
        if result is None:
            result = await self._fetch_from_provider(original_query, normalized_query, limit=limit)
            await self._save_cached_result(result)

        candidates = self._candidate_results_from_response(result, limit)
        self._memoized_candidates[memo_key] = candidates
        if candidates:
            self._memoized_results[(self.provider, normalized_query)] = candidates[0]
        return candidates

    async def _load_cached_result(
        self,
        provider: str,
        normalized_query: str,
        required_limit: int = 1,
    ) -> GeocodeResult | None:
        async with async_session() as session:
            stmt = select(GeocodingCacheEntry).where(
                GeocodingCacheEntry.provider == provider,
                GeocodingCacheEntry.normalized_query == normalized_query,
            )
            record = (await session.execute(stmt)).scalar_one_or_none()

        if record is None:
            return None

        raw_response = record.raw_response
        if required_limit > 1 and not self._cache_satisfies_limit(raw_response, required_limit):
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
            confidence_score=_importance_from_raw_response(_top_row_from_raw_response(raw_response)),
            location_granularity=_location_granularity(_top_row_from_raw_response(raw_response)),
            raw_response=raw_response,
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
        limit: int = 1,
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
                        "limit": limit,
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
                raw_response={"results": [], "requested_limit": limit},
            )

        if not payload:
            return GeocodeResult(
                provider=self.provider,
                normalized_query=normalized_query,
                original_query=original_query,
                status="failed",
                raw_response={"results": [], "requested_limit": limit},
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
            confidence_score=importance,
            location_granularity=_location_granularity(top_result),
            raw_response={"results": payload, "requested_limit": limit},
        )

    def _candidate_results_from_response(
        self,
        result: GeocodeResult,
        limit: int,
    ) -> list[GeocodeResult]:
        raw = result.raw_response or {}
        if isinstance(raw, dict) and isinstance(raw.get("results"), list):
            rows = raw.get("results", [])[:limit]
        elif isinstance(raw, dict) and raw:
            rows = [raw]
        else:
            rows = []

        candidates: list[GeocodeResult] = []
        for row in rows:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            importance = float(row.get("importance", 0) or 0)
            candidates.append(
                GeocodeResult(
                    provider=result.provider,
                    normalized_query=result.normalized_query,
                    original_query=result.original_query,
                    status="success",
                    latitude=lat,
                    longitude=lon,
                    formatted_address=row.get("display_name", result.original_query),
                    confidence=self._confidence_from_importance(importance),
                    confidence_score=importance,
                    location_granularity=_location_granularity(row),
                    raw_response=row,
                )
            )
        return candidates

    @staticmethod
    def _cache_satisfies_limit(raw_response: dict[str, Any] | None, required_limit: int) -> bool:
        if required_limit <= 1:
            return True
        if not isinstance(raw_response, dict):
            return False
        results = raw_response.get("results")
        requested_limit = int(raw_response.get("requested_limit") or 0)
        return isinstance(results, list) and requested_limit >= required_limit

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
