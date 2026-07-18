from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.pipeline.chunk_embed import TextChunk
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship
from app.services import neo4j_client
from app.services.geocoding import (
    GeocodeRequest,
    GeocodeResult,
    build_geocode_request,
    geocoding_service,
    normalize_geocode_query,
)

TAXONOMY_VERSION = "dkt-693-default-v1"

# PR review flag: this baked default taxonomy defines ingestion-time map precision.
LOCATION_GRANULARITY_TAXONOMY_FOR_PR_REVIEW = {
    "version": TAXONOMY_VERSION,
    "exact": ["street_address", "point_of_interest", "intersection", "coordinates"],
    "approximate": ["city", "town", "neighborhood", "postal_area"],
    "unmapped_review": [
        "country_only",
        "region_only",
        "organization_without_address",
        "ambiguous_candidates",
        "document_artifact",
        "vague_or_unknown",
    ],
}

EXACT_GRANULARITIES = set(LOCATION_GRANULARITY_TAXONOMY_FOR_PR_REVIEW["exact"])
APPROXIMATE_GRANULARITIES = set(LOCATION_GRANULARITY_TAXONOMY_FOR_PR_REVIEW["approximate"])
UNMAPPED_GRANULARITIES = set(LOCATION_GRANULARITY_TAXONOMY_FOR_PR_REVIEW["unmapped_review"])

_ADDRESS_TOKEN_RE = re.compile(
    r"\b\d{1,6}\s+[a-z0-9.' -]+\b(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|"
    r"boulevard|blvd|court|ct|place|pl|way|terrace|ter|close|crescent|square|sq)\b",
    re.IGNORECASE,
)
_COORDINATE_RE = re.compile(r"[-+]?\d{1,2}\.\d{3,}\s*,\s*[-+]?\d{1,3}\.\d{3,}")
_INTERSECTION_RE = re.compile(r"\b(?:and|&|at)\b", re.IGNORECASE)
_CONTACT_BLOCK_RE = re.compile(
    r"\b(?:registered office|head office|letterhead|footer|contact us|telephone|tel\.?|"
    r"phone|fax|email|e-mail|www\.|all rights reserved|confidentiality notice|"
    r"page\s+\d+\s+of\s+\d+)\b",
    re.IGNORECASE,
)
_ORG_SUFFIX_RE = re.compile(
    r"\b(?:inc|inc\.|llc|ltd|limited|corp|corporation|company|co\.|plc|gmbh|sa|ag|"
    r"foundation|association|university|bank|office)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GeocodeCandidateSummary:
    latitude: float | None
    longitude: float | None
    formatted_address: str | None
    confidence: str | None
    place_class: str | None = None
    place_type: str | None = None
    importance: float | None = None


@dataclass(frozen=True)
class ExistingLocation:
    id: str
    key: str | None
    name: str
    type: str
    latitude: float
    longitude: float
    location_raw: str | None = None
    location_formatted: str | None = None
    geocoding_granularity: str | None = None
    geocoding_precision: str | None = None
    manual_fields: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    job_id: str | None = None


@dataclass
class GeocodingDecision:
    entity_id: str
    entity_name: str
    category: str
    status: str
    granularity: str
    precision: str
    reason: str
    confidence: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    formatted_address: str | None = None
    location_raw: str | None = None
    deduped_to: str | None = None
    decision: str = "unmapped"
    source_files: list[str] = field(default_factory=list)
    candidates: list[GeocodeCandidateSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _AcceptedLocation:
    entity_id: str
    name: str
    latitude: float
    longitude: float
    location_raw: str | None = None
    location_formatted: str | None = None


def _has_coordinates(properties: dict[str, Any]) -> bool:
    return properties.get("latitude") is not None and properties.get("longitude") is not None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normal_name(value: str | None) -> str:
    text = normalize_geocode_query(value or "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _candidate_summary(result: GeocodeResult) -> GeocodeCandidateSummary:
    raw = result.raw_response or {}
    return GeocodeCandidateSummary(
        latitude=result.latitude,
        longitude=result.longitude,
        formatted_address=result.formatted_address,
        confidence=result.confidence,
        place_class=raw.get("class") if isinstance(raw, dict) else None,
        place_type=raw.get("type") if isinstance(raw, dict) else None,
        importance=float(raw.get("importance", 0) or 0) if isinstance(raw, dict) else None,
    )


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _raw_address(result: GeocodeResult | None) -> dict[str, Any]:
    if not result or not isinstance(result.raw_response, dict):
        return {}
    address = result.raw_response.get("address")
    return address if isinstance(address, dict) else {}


def _raw_class_type(result: GeocodeResult | None) -> tuple[str, str]:
    raw = result.raw_response if result and isinstance(result.raw_response, dict) else {}
    return str(raw.get("class") or "").lower(), str(raw.get("type") or "").lower()


def _classify_granularity(
    entity: ResolvedEntity,
    request: GeocodeRequest | None,
    best: GeocodeResult | None,
) -> str:
    props = entity.properties
    query = request.query if request else entity.name
    place_class, place_type = _raw_class_type(best)
    address = _raw_address(best)
    specificity = str(props.get("specificity") or "").lower()

    if _has_coordinates(props) or _COORDINATE_RE.search(str(props.get("coordinates_hint") or query)):
        return "coordinates"
    if "intersection" in specificity or _INTERSECTION_RE.search(query or "") and _ADDRESS_TOKEN_RE.search(query or ""):
        return "intersection"
    if props.get("address") or _ADDRESS_TOKEN_RE.search(query or "") or address.get("house_number"):
        return "street_address"

    if place_class == "boundary" and place_type in {"administrative", "political"}:
        admin_level = str((best.raw_response or {}).get("admin_level") or "")
        if admin_level in {"2"}:
            return "country_only"
        return "region_only"

    if place_class == "place":
        if place_type == "country":
            return "country_only"
        if place_type in {"state", "province", "region", "county"}:
            return "region_only"
        if place_type in {"city", "municipality"}:
            return "city"
        if place_type in {"town", "village", "hamlet"}:
            return "town"
        if place_type in {"suburb", "neighbourhood", "neighborhood", "quarter"}:
            return "neighborhood"
        if place_type in {"postcode", "postal_code"}:
            return "postal_area"

    if address.get("postcode") and not (address.get("road") or address.get("house_number")):
        return "postal_area"
    if props.get("city") and not props.get("address"):
        return "city"
    if props.get("region") and not (props.get("city") or props.get("address")):
        return "region_only"
    if props.get("country") and not (props.get("region") or props.get("city") or props.get("address")):
        return "country_only"

    if place_class in {"amenity", "shop", "tourism", "leisure", "building", "historic"}:
        return "point_of_interest"
    if place_class in {"office", "craft"} or place_type in {"company", "corporate_office"}:
        if props.get("address") or _ADDRESS_TOKEN_RE.search(query or ""):
            return "point_of_interest"
        return "organization_without_address"
    if _ORG_SUFFIX_RE.search(query or "") and not (props.get("address") or _ADDRESS_TOKEN_RE.search(query or "")):
        return "organization_without_address"

    return "vague_or_unknown"


def _precision_for_granularity(granularity: str) -> str:
    if granularity in EXACT_GRANULARITIES:
        return "exact"
    if granularity in APPROXIMATE_GRANULARITIES:
        return "approximate"
    return "unmapped"


def _materially_ambiguous(candidates: list[GeocodeResult]) -> bool:
    if len(candidates) < 2:
        return False
    first, second = candidates[0], candidates[1]
    if None in (first.latitude, first.longitude, second.latitude, second.longitude):
        return False

    distance = _haversine_meters(
        float(first.latitude),
        float(first.longitude),
        float(second.latitude),
        float(second.longitude),
    )
    first_importance = (_candidate_summary(first).importance or 0.0)
    second_importance = (_candidate_summary(second).importance or 0.0)
    if distance < 50_000:
        return False
    if second_importance >= first_importance * 0.75:
        return True

    first_address = _raw_address(first)
    second_address = _raw_address(second)
    first_country = first_address.get("country_code") or first_address.get("country")
    second_country = second_address.get("country_code") or second_address.get("country")
    return bool(first_country and second_country and first_country != second_country)


def _related_entity_ids(relationships: list[ResolvedRelationship], entity_id: str) -> set[str]:
    related: set[str] = set()
    for relationship in relationships:
        if relationship.source_entity_id == entity_id:
            related.add(relationship.target_entity_id)
        if relationship.target_entity_id == entity_id:
            related.add(relationship.source_entity_id)
    return related


def _matching_chunks(entity: ResolvedEntity, chunks: list[TextChunk]) -> list[TextChunk]:
    needles = [
        entity.name,
        str(entity.properties.get("location_raw") or ""),
        str(entity.properties.get("address") or ""),
        *entity.source_quotes[:3],
    ]
    clean_needles = [needle.strip() for needle in needles if needle and len(needle.strip()) >= 4]
    if not clean_needles:
        return []
    matches: list[TextChunk] = []
    for chunk in chunks:
        text = chunk.text.lower()
        if any(needle.lower() in text for needle in clean_needles):
            matches.append(chunk)
    return matches


def _looks_like_document_artifact(
    entity: ResolvedEntity,
    chunks: list[TextChunk],
    relationships: list[ResolvedRelationship],
) -> bool:
    if _related_entity_ids(relationships, entity.id):
        return False

    text = " ".join(
        str(value or "")
        for value in [
            entity.name,
            entity.properties.get("location_raw"),
            entity.properties.get("address"),
            *entity.source_quotes,
        ]
    )
    matching_chunks = _matching_chunks(entity, chunks)
    chunk_text = " ".join(chunk.text[:1200] for chunk in matching_chunks[:3])
    haystack = f"{text}\n{chunk_text}"
    if not _CONTACT_BLOCK_RE.search(haystack):
        return False

    if not matching_chunks:
        return True

    max_index = max((chunk.index for chunk in chunks), default=0)
    page_numbers = [
        page
        for chunk in chunks
        for page in (chunk.metadata.get("page_start"), chunk.metadata.get("page_end"))
        if page is not None
    ]
    max_page = max(page_numbers, default=None)
    for chunk in matching_chunks:
        page_start = chunk.metadata.get("page_start")
        page_end = chunk.metadata.get("page_end")
        first_or_last_chunk = chunk.index == 0 or chunk.index == max_index
        first_or_last_page = page_start == 1 or page_end == 1 or (
            max_page is not None and (page_start == max_page or page_end == max_page)
        )
        if first_or_last_chunk or first_or_last_page:
            return True
    return len(matching_chunks) > 1


def _dedupe_target(
    name: str,
    location_raw: str | None,
    formatted_address: str | None,
    latitude: float,
    longitude: float,
    existing_locations: list[ExistingLocation],
    accepted_locations: list[_AcceptedLocation],
) -> str | None:
    names = {_normal_name(name), _normal_name(location_raw), _normal_name(formatted_address)}
    names.discard("")

    for existing in existing_locations:
        existing_names = {
            _normal_name(existing.name),
            _normal_name(existing.location_raw),
            _normal_name(existing.location_formatted),
        }
        existing_names.discard("")
        if names & existing_names:
            return existing.id
        distance = _haversine_meters(latitude, longitude, existing.latitude, existing.longitude)
        if distance <= 100:
            return existing.id

    for accepted in accepted_locations:
        accepted_names = {
            _normal_name(accepted.name),
            _normal_name(accepted.location_raw),
            _normal_name(accepted.location_formatted),
        }
        accepted_names.discard("")
        if names & accepted_names:
            return accepted.entity_id
        distance = _haversine_meters(latitude, longitude, accepted.latitude, accepted.longitude)
        if distance <= 100:
            return accepted.entity_id

    return None


def _existing_location_from_row(row: dict[str, Any]) -> ExistingLocation | None:
    lat = _float_or_none(row.get("latitude"))
    lon = _float_or_none(row.get("longitude"))
    loc_id = str(row.get("id") or row.get("key") or "")
    if not loc_id or lat is None or lon is None:
        return None
    return ExistingLocation(
        id=loc_id,
        key=row.get("key"),
        name=str(row.get("name") or ""),
        type=str(row.get("type") or "Location"),
        latitude=lat,
        longitude=lon,
        location_raw=row.get("location_raw"),
        location_formatted=row.get("location_formatted"),
        geocoding_granularity=row.get("geocoding_granularity"),
        geocoding_precision=row.get("geocoding_precision"),
        manual_fields=list(row.get("manual_fields") or []),
        source_files=list(row.get("source_files") or []),
        job_id=row.get("job_id"),
    )


def _mark_unmapped(
    entity: ResolvedEntity,
    request: GeocodeRequest | None,
    status: str,
    granularity: str,
    reason: str,
    candidates: list[GeocodeCandidateSummary] | None = None,
) -> GeocodingDecision:
    entity.properties.pop("latitude", None)
    entity.properties.pop("longitude", None)
    if request is not None:
        entity.properties["location_raw"] = request.location_raw
    entity.properties["geocoding_status"] = status
    entity.properties["geocoding_reason"] = reason
    entity.properties["geocoding_granularity"] = granularity
    entity.properties["geocoding_precision"] = "unmapped"
    if candidates:
        entity.properties["geocoding_candidates"] = json.dumps([asdict(c) for c in candidates])
    return GeocodingDecision(
        entity_id=entity.id,
        entity_name=entity.name,
        category=entity.category,
        status=status,
        granularity=granularity,
        precision="unmapped",
        reason=reason,
        location_raw=request.location_raw if request else entity.properties.get("location_raw"),
        source_files=entity.source_files,
        candidates=candidates or [],
    )


def _mark_accepted(
    entity: ResolvedEntity,
    request: GeocodeRequest,
    result: GeocodeResult,
    granularity: str,
    candidates: list[GeocodeCandidateSummary],
    deduped_to: str | None,
) -> GeocodingDecision:
    precision = _precision_for_granularity(granularity)
    entity.properties["location_raw"] = request.location_raw
    entity.properties["latitude"] = result.latitude
    entity.properties["longitude"] = result.longitude
    entity.properties["location_formatted"] = result.formatted_address
    entity.properties["geocoding_confidence"] = result.confidence
    entity.properties["geocoding_status"] = "success"
    entity.properties["geocoding_granularity"] = granularity
    entity.properties["geocoding_precision"] = precision
    if candidates:
        entity.properties["geocoding_candidates"] = json.dumps([asdict(c) for c in candidates])
    if deduped_to:
        entity.properties["geocoding_decision"] = "deduped"
        entity.properties["geocoding_deduped_to"] = deduped_to

    return GeocodingDecision(
        entity_id=entity.id,
        entity_name=entity.name,
        category=entity.category,
        status="success",
        granularity=granularity,
        precision=precision,
        reason="deduped_to_existing_location" if deduped_to else "accepted",
        confidence=result.confidence,
        latitude=result.latitude,
        longitude=result.longitude,
        formatted_address=result.formatted_address,
        location_raw=request.location_raw,
        deduped_to=deduped_to,
        decision="deduped" if deduped_to else "accepted",
        source_files=entity.source_files,
        candidates=candidates,
    )


def _mark_coordinate_entity(entity: ResolvedEntity) -> GeocodingDecision:
    entity.properties["geocoding_status"] = entity.properties.get("geocoding_status") or "success"
    entity.properties["geocoding_granularity"] = "coordinates"
    entity.properties["geocoding_precision"] = "exact"
    entity.properties["geocoding_confidence"] = entity.properties.get("geocoding_confidence") or "high"
    return GeocodingDecision(
        entity_id=entity.id,
        entity_name=entity.name,
        category=entity.category,
        status="success",
        granularity="coordinates",
        precision="exact",
        reason="explicit_coordinates",
        confidence=entity.properties.get("geocoding_confidence"),
        latitude=_float_or_none(entity.properties.get("latitude")),
        longitude=_float_or_none(entity.properties.get("longitude")),
        formatted_address=entity.properties.get("location_formatted"),
        location_raw=entity.properties.get("location_raw"),
        decision="accepted",
        source_files=entity.source_files,
    )


async def apply_contextual_geocoding(
    entities: list[ResolvedEntity],
    relationships: list[ResolvedRelationship],
    case_id: str,
    chunks: list[TextChunk] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    existing_rows = await neo4j_client.get_case_geocoded_locations(case_id)
    existing_locations = [
        location for row in existing_rows if (location := _existing_location_from_row(row)) is not None
    ]
    chunks = chunks or []
    decisions: list[GeocodingDecision] = []
    id_remaps: dict[str, str] = {}
    accepted_locations: list[_AcceptedLocation] = []

    for entity in entities:
        if entity.category != "Location" and not any(
            entity.properties.get(key) for key in ("address", "city", "region", "country", "location_raw")
        ):
            continue

        if _has_coordinates(entity.properties):
            decision = _mark_coordinate_entity(entity)
            decisions.append(decision)
            lat = decision.latitude
            lon = decision.longitude
            if lat is not None and lon is not None:
                target = _dedupe_target(
                    entity.name,
                    entity.properties.get("location_raw"),
                    entity.properties.get("location_formatted"),
                    lat,
                    lon,
                    existing_locations,
                    accepted_locations,
                )
                if target and target != entity.id:
                    id_remaps[entity.id] = target
                    entity.properties["geocoding_decision"] = "deduped"
                    entity.properties["geocoding_deduped_to"] = target
                    decision.deduped_to = target
                    decision.decision = "deduped"
                else:
                    accepted_locations.append(
                        _AcceptedLocation(entity.id, entity.name, lat, lon, entity.properties.get("location_raw"))
                    )
            continue

        request = build_geocode_request(entity.category, entity.name, entity.properties)
        if request is None:
            if entity.category == "Location":
                decisions.append(
                    _mark_unmapped(
                        entity,
                        None,
                        "rejected",
                        "vague_or_unknown",
                        "no_specific_geocodable_location",
                    )
                )
            continue

        if _looks_like_document_artifact(entity, chunks, relationships):
            decisions.append(
                _mark_unmapped(
                    entity,
                    request,
                    "rejected",
                    "document_artifact",
                    "document_artifact_or_boilerplate",
                )
            )
            continue

        candidates = await geocoding_service.geocode_candidates(request.query, limit=5)
        candidate_summaries = [_candidate_summary(candidate) for candidate in candidates]
        if not candidates:
            decisions.append(
                _mark_unmapped(
                    entity,
                    request,
                    "needs_review",
                    "vague_or_unknown",
                    "geocoder_returned_no_candidates",
                    candidate_summaries,
                )
            )
            continue

        if _materially_ambiguous(candidates):
            decisions.append(
                _mark_unmapped(
                    entity,
                    request,
                    "needs_review",
                    "ambiguous_candidates",
                    "top_geocoder_candidates_disagree_materially",
                    candidate_summaries,
                )
            )
            continue

        best = candidates[0]
        granularity = _classify_granularity(entity, request, best)
        if granularity in UNMAPPED_GRANULARITIES:
            decisions.append(
                _mark_unmapped(
                    entity,
                    request,
                    "needs_review",
                    granularity,
                    f"{granularity}_not_pinned_by_default_taxonomy",
                    candidate_summaries,
                )
            )
            continue

        lat = _float_or_none(best.latitude)
        lon = _float_or_none(best.longitude)
        if lat is None or lon is None:
            decisions.append(
                _mark_unmapped(
                    entity,
                    request,
                    "needs_review",
                    "vague_or_unknown",
                    "geocoder_candidate_missing_coordinates",
                    candidate_summaries,
                )
            )
            continue

        target = _dedupe_target(
            entity.name,
            request.location_raw,
            best.formatted_address,
            lat,
            lon,
            existing_locations,
            accepted_locations,
        )
        if target and target != entity.id:
            id_remaps[entity.id] = target
        else:
            accepted_locations.append(
                _AcceptedLocation(entity.id, entity.name, lat, lon, request.location_raw, best.formatted_address)
            )
        decisions.append(_mark_accepted(entity, request, best, granularity, candidate_summaries, target))

    counts: dict[str, int] = {
        "accepted": 0,
        "approximate": 0,
        "deduped": 0,
        "needs_review": 0,
        "rejected": 0,
    }
    for decision in decisions:
        if decision.decision == "deduped":
            counts["deduped"] += 1
        elif decision.status == "success":
            counts["accepted"] += 1
            if decision.precision == "approximate":
                counts["approximate"] += 1
        elif decision.status == "needs_review":
            counts["needs_review"] += 1
        elif decision.status == "rejected":
            counts["rejected"] += 1

    summary = {
        "geocoding": {
            "taxonomy_version": TAXONOMY_VERSION,
            "taxonomy_review_flag": "LOCATION_GRANULARITY_TAXONOMY_FOR_PR_REVIEW",
            "counts": counts,
            "decisions": [decision.to_dict() for decision in decisions],
        }
    }
    return summary, id_remaps
