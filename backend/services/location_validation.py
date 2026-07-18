"""Location validation and geocoding provenance helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class LocationRejectionReason(StrEnum):
    NON_NUMERIC = "non_numeric"
    OUT_OF_RANGE_LATITUDE = "out_of_range_latitude"
    OUT_OF_RANGE_LONGITUDE = "out_of_range_longitude"
    NULL_ISLAND = "null_island"
    DISALLOWED_ENTITY_TYPE = "disallowed_entity_type"
    PROVIDER_FAILURE = "provider_failure"


GEOCODING_STATUS_MAPPED = "mapped"
GEOCODING_STATUS_REJECTED = "rejected"
GEOCODING_STATUS_UNMAPPED_RETRIABLE = "unmapped_retriable"

ALLOWED_COORDINATE_ENTITY_TYPES = frozenset(
    {
        "Location",
        "Event",
        "Communication",
        "LegalAction",
        "Intelligence",
        "Transaction",
        "Person",
        "Organization",
        "Group",
        "Account",
        "FinancialInstrument",
        "Vehicle",
        "Device",
        "PhysicalEvidence",
        "Media",
    }
)


@dataclass(frozen=True)
class GeocodeProvenance:
    geocoder: str | None = None
    query: str | None = None
    formatted_address: str | None = None
    precision: str | None = None
    confidence: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    provider_status: str | None = None
    failure_reason: str | None = None

    def as_cache_values(self) -> dict[str, Any]:
        return {
            "geocoder": self.geocoder,
            "query": self.query,
            "formatted_address": self.formatted_address,
            "precision": self.precision,
            "confidence": self.confidence,
            "candidates": self.candidates,
            "provider_error": self.failure_reason,
        }

    def as_node_properties(self, *, status: str, rejection_reason: str | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {
            "geocoding_provider": self.geocoder,
            "geocoding_query": self.query,
            "location_formatted": self.formatted_address,
            "location_name": self.formatted_address,
            "geocoding_precision": self.precision,
            "geocoding_confidence": self.confidence,
            "geocoding_status": status,
            "geocoding_rejection_reason": rejection_reason,
            "geocoding_provider_error": self.failure_reason,
        }
        if self.candidates:
            props["geocoding_candidates"] = json.dumps(self.candidates, separators=(",", ":"))
        else:
            props["geocoding_candidates"] = None
        return props


@dataclass(frozen=True)
class ValidatedLocation:
    latitude: float | None
    longitude: float | None
    provenance: GeocodeProvenance
    status: str
    rejection_reason: LocationRejectionReason | None = None

    @property
    def is_valid(self) -> bool:
        return self.status == GEOCODING_STATUS_MAPPED and self.rejection_reason is None

    def as_node_properties(self) -> dict[str, Any]:
        props = self.provenance.as_node_properties(
            status=self.status,
            rejection_reason=self.rejection_reason.value if self.rejection_reason else None,
        )
        if self.is_valid:
            props["latitude"] = self.latitude
            props["longitude"] = self.longitude
        else:
            props["latitude"] = None
            props["longitude"] = None
        return props


def _coerce_coordinate(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def validate_location(
    *,
    latitude: Any,
    longitude: Any,
    entity_type: str | None,
    provenance: GeocodeProvenance | None = None,
) -> ValidatedLocation:
    provenance = provenance or GeocodeProvenance()

    if provenance.provider_status == GEOCODING_STATUS_UNMAPPED_RETRIABLE:
        return ValidatedLocation(
            None,
            None,
            provenance,
            GEOCODING_STATUS_UNMAPPED_RETRIABLE,
            LocationRejectionReason.PROVIDER_FAILURE,
        )

    if entity_type not in ALLOWED_COORDINATE_ENTITY_TYPES:
        return ValidatedLocation(
            None,
            None,
            provenance,
            GEOCODING_STATUS_REJECTED,
            LocationRejectionReason.DISALLOWED_ENTITY_TYPE,
        )

    lat = _coerce_coordinate(latitude)
    lon = _coerce_coordinate(longitude)
    if lat is None or lon is None:
        return ValidatedLocation(
            None,
            None,
            provenance,
            GEOCODING_STATUS_REJECTED,
            LocationRejectionReason.NON_NUMERIC,
        )
    if not -90 <= lat <= 90:
        return ValidatedLocation(
            None,
            None,
            provenance,
            GEOCODING_STATUS_REJECTED,
            LocationRejectionReason.OUT_OF_RANGE_LATITUDE,
        )
    if not -180 <= lon <= 180:
        return ValidatedLocation(
            None,
            None,
            provenance,
            GEOCODING_STATUS_REJECTED,
            LocationRejectionReason.OUT_OF_RANGE_LONGITUDE,
        )
    if lat == 0 and lon == 0:
        return ValidatedLocation(
            None,
            None,
            provenance,
            GEOCODING_STATUS_REJECTED,
            LocationRejectionReason.NULL_ISLAND,
        )

    return ValidatedLocation(lat, lon, provenance, GEOCODING_STATUS_MAPPED)


def strip_coordinate_properties(properties: dict[str, Any]) -> None:
    for key in ("latitude", "longitude"):
        properties.pop(key, None)
