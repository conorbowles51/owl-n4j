"""Canonical property normalization for extracted graph entities.

The LLM schema intentionally leaves ``properties`` flexible so analysts can
still get useful case-specific detail. This module adds a conservative bridge
between that flexible extraction layer and the canonical fields the app reads.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DATE_YMD_RE = re.compile(r"(?<!\d)(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})(?!\d)")
_DATE_MDY_RE = re.compile(r"(?<!\d)(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})(?!\d)")
_TIME_RE = re.compile(
    r"(?<!\d)(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)(?::[0-5]\d)?\s*(?P<ampm>[AaPp][Mm])?(?!\d)"
)
TEMPORAL_CATEGORIES = {
    "Event",
    "LegalAction",
    "Media",
    "Intelligence",
    "Transaction",
    "Communication",
    "Document",
    # Cellebrite-specific graph labels.
    "PhoneCall",
    "Email",
    "Meeting",
    "Location",
    "CellTower",
    "DeviceEvent",
    "AppSession",
    "VisitedPage",
    "WirelessNetwork",
    "Device",
    "WebBookmark",
    "SearchedItem",
}

TEMPORAL_CATEGORY_TOKENS = (
    "event",
    "call",
    "message",
    "email",
    "chat",
    "session",
    "meeting",
    "media",
    "document",
    "transaction",
    "action",
    "location",
)

TIMESTAMP_ALIASES = {
    "timestamp",
    "time_stamp",
    "datetime",
    "date_time",
    "date_and_time",
    "event_datetime",
    "event_timestamp",
    "communication_datetime",
    "communication_timestamp",
    "transaction_datetime",
    "transaction_timestamp",
    "capture_time",
    "captured_at",
    "creation_time",
    "created_time",
    "modify_time",
    "modified_time",
    "start_time",
    "started_at",
    "time_of_call",
    "call_timestamp",
    "date_taken",
}

DATE_ALIASES = {
    "event_date",
    "transaction_date",
    "communication_date",
    "document_date",
    "media_date",
    "capture_date",
    "captured_date",
    "creation_date",
    "created_date",
    "start_date",
}

TIME_ALIASES = {
    "event_time",
    "transaction_time",
    "communication_time",
    "media_time",
    "capture_time_only",
    "call_time",
    "time_of_day",
}

AMOUNT_ALIASES = {
    "value",
    "total",
    "transaction_amount",
    "payment_amount",
    "transfer_amount",
    "amount_usd",
    "amount_eur",
    "amount_gbp",
}

SENDER_ALIASES = {
    "from",
    "from_party",
    "from_entity",
    "payer",
    "payor",
    "originator",
    "sender_name",
    "source_party",
}

RECEIVER_ALIASES = {
    "to",
    "to_party",
    "to_entity",
    "payee",
    "recipient",
    "beneficiary",
    "receiver_name",
    "destination_party",
}

LOCATION_RAW_ALIASES = {
    "location",
    "place",
    "place_name",
    "location_text",
    "location_description",
    "raw_location",
    "address_text",
}

LATITUDE_ALIASES = {"lat", "gps_latitude", "geo_latitude", "location_latitude"}
LONGITUDE_ALIASES = {
    "lon",
    "lng",
    "long",
    "gps_longitude",
    "geo_longitude",
    "location_longitude",
}

LOCATION_SPECIFICITY_LEVELS = (
    "unknown",
    "continent",
    "country",
    "region",
    "city",
    "district",
    "street",
    "exact_address",
)
LOCATION_SPECIFICITY_RANK = {
    level: rank for rank, level in enumerate(LOCATION_SPECIFICITY_LEVELS)
}
_LOCATION_SPECIFICITY_ALIASES = {
    "unknown": "unknown",
    "unspecified": "unknown",
    "vague": "unknown",
    "relative": "unknown",
    "continent": "continent",
    "continental": "continent",
    "country": "country",
    "nation": "country",
    "national": "country",
    "region": "region",
    "regional": "region",
    "state": "region",
    "province": "region",
    "county": "region",
    "city": "city",
    "town": "city",
    "village": "city",
    "municipality": "city",
    "locality": "city",
    "district": "district",
    "neighborhood": "district",
    "neighbourhood": "district",
    "borough": "district",
    "suburb": "district",
    "postcode": "district",
    "postal_code": "district",
    "street": "street",
    "road": "street",
    "exact": "exact_address",
    "exact_address": "exact_address",
    "address": "exact_address",
    "building": "exact_address",
    "premise": "exact_address",
    "poi": "exact_address",
    "point": "exact_address",
    "coordinates": "exact_address",
    "coordinate": "exact_address",
}
_LOCATION_EVIDENCE_FIELDS = (
    "location_raw",
    "address",
    "city",
    "region",
    "country",
    "coordinates_hint",
    "latitude",
    "longitude",
)


def _canonical_key(key: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", str(key or "").strip().lower())
    return re.sub(r"_+", "_", text).strip("_")


def normalize_location_specificity(value: Any) -> str | None:
    """Return a canonical location-specificity level for common model variants."""
    if value in (None, ""):
        return None
    return _LOCATION_SPECIFICITY_ALIASES.get(_canonical_key(str(value)))


def location_specificity_rank(value: Any) -> int:
    """Return the ordered rank of a specificity value, defaulting to unknown."""
    normalized = normalize_location_specificity(value) or "unknown"
    return LOCATION_SPECIFICITY_RANK[normalized]


def promote_location_specificity(
    properties: dict[str, Any],
    *candidates: dict[str, Any],
) -> None:
    """Promote a merged property set to its most-specific valid source label."""
    best = normalize_location_specificity(
        properties.get("location_specificity", properties.get("specificity"))
    )
    for candidate in candidates:
        value = normalize_location_specificity(
            candidate.get("location_specificity", candidate.get("specificity"))
        )
        if value is not None and (
            best is None
            or location_specificity_rank(value) > location_specificity_rank(best)
        ):
            best = value
    if best is not None:
        properties["location_specificity"] = best


def has_location_evidence(
    category: str,
    name: str,
    properties: dict[str, Any] | None,
) -> bool:
    """Whether an entity carries a location that ingestion must retain."""
    props = properties or {}
    if any(props.get(field) not in (None, "") for field in _LOCATION_EVIDENCE_FIELDS):
        return True
    return category == "Location" and bool(str(name or "").strip())


def infer_structured_location_specificity(properties: dict[str, Any]) -> str | None:
    """Infer a conservative level from canonical structured geo fields."""
    if properties.get("coordinates_hint") not in (None, ""):
        return "exact_address"
    if (
        properties.get("latitude") is not None
        and properties.get("longitude") is not None
        and properties.get("geocoding_status") in (None, "")
    ):
        # Coordinates present in extracted source data are exact. Coordinates
        # previously produced by the geocoder retain the input specificity that
        # was persisted alongside geocoding_status instead of becoming "exact".
        return "exact_address"

    address = str(properties.get("address") or "").strip()
    if address:
        # A house/unit number is strong evidence of an exact address. A named
        # building or POI can still be labelled exact_address by the model.
        if re.match(r"^\s*\d+[A-Za-z]?(?:\s*[-/]\s*\d+[A-Za-z]?)?\b", address):
            return "exact_address"
        return "street"
    if properties.get("city") not in (None, ""):
        return "city"
    if properties.get("region") not in (None, ""):
        return "region"
    if properties.get("country") not in (None, ""):
        return "country"
    return None


def _first_present(properties: dict[str, Any], canonical_keys: set[str]) -> tuple[str, Any] | None:
    for key, value in properties.items():
        if value in (None, ""):
            continue
        if _canonical_key(key) in canonical_keys:
            return key, value
    return None


def _is_temporal_category(category: str) -> bool:
    if category in TEMPORAL_CATEGORIES:
        return True
    lowered = str(category or "").lower()
    return any(token in lowered for token in TEMPORAL_CATEGORY_TOKENS)


def _format_date(match: re.Match[str]) -> str | None:
    try:
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
    except (IndexError, ValueError):
        return None
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _format_time(match: re.Match[str]) -> str | None:
    try:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
    except (IndexError, ValueError):
        return None
    ampm = (match.group("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not 0 <= hour <= 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def _extract_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _DATE_YMD_RE.search(text) or _DATE_MDY_RE.search(text)
    return _format_date(match) if match else None


def _extract_times(value: Any) -> tuple[str | None, str | None]:
    text = str(value or "").strip()
    if not text:
        return None, None
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ].*(?:Z|[+-]\d{2}:?\d{2})$", text):
        text = re.sub(r"(?:Z|[+-]\d{2}:?\d{2})$", "", text)
    matches = list(_TIME_RE.finditer(text))
    if not matches:
        return None, None
    start = _format_time(matches[0])
    end = None
    if len(matches) > 1:
        between = text[matches[0].end() : matches[1].start()]
        if re.search(r"-|\bto\b", between, re.IGNORECASE):
            end = _format_time(matches[1])
    return start, end


def _normalize_temporal_properties(
    category: str,
    properties: dict[str, Any],
    evidence_texts: list[str] | None = None,
) -> None:
    if not _is_temporal_category(category) and "date" not in properties:
        return

    raw_temporal: Any = None
    source = _first_present(properties, TIMESTAMP_ALIASES)
    if source:
        source_key, raw_temporal = source
        if "timestamp_raw" not in properties:
            properties["timestamp_raw"] = str(raw_temporal)
        if "timestamp" not in properties and _canonical_key(source_key) != "timestamp":
            properties["timestamp"] = str(raw_temporal)

    if raw_temporal is None and properties.get("date") not in (None, ""):
        raw_temporal = properties.get("date")

    if properties.get("date") in (None, ""):
        date_source = raw_temporal
        if date_source is None:
            source = _first_present(properties, DATE_ALIASES)
            date_source = source[1] if source else None
        parsed_date = _extract_date(date_source)
        if parsed_date:
            properties["date"] = parsed_date
    else:
        parsed_date = _extract_date(properties.get("date"))
        if parsed_date:
            properties["date"] = parsed_date

    if properties.get("time") in (None, ""):
        time_source = raw_temporal
        if time_source is None:
            source = _first_present(properties, TIME_ALIASES)
            time_source = source[1] if source else None
        parsed_time, parsed_end_time = _extract_times(time_source)
        if parsed_time:
            properties["time"] = parsed_time
        if parsed_end_time and properties.get("end_time") in (None, ""):
            properties["end_time"] = parsed_end_time
    else:
        parsed_time, parsed_end_time = _extract_times(properties.get("time"))
        if parsed_time:
            properties["time"] = parsed_time
        if parsed_end_time and properties.get("end_time") in (None, ""):
            properties["end_time"] = parsed_end_time

    if properties.get("date") and properties.get("time") in (None, ""):
        date_value = str(properties.get("date"))
        for text in evidence_texts or []:
            parsed_date = _extract_date(text)
            if parsed_date != date_value:
                continue
            parsed_time, parsed_end_time = _extract_times(text)
            if parsed_time:
                properties["time"] = parsed_time
            if parsed_end_time and properties.get("end_time") in (None, ""):
                properties["end_time"] = parsed_end_time
            if properties.get("time"):
                break


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None


def _normalize_geo_properties(properties: dict[str, Any]) -> None:
    if properties.get("latitude") in (None, ""):
        source = _first_present(properties, LATITUDE_ALIASES)
        if source:
            number = _coerce_float(source[1])
            if number is not None and -90 <= number <= 90:
                properties["latitude"] = number
            elif number is not None:
                logger.warning("Ignoring out-of-range latitude: %r", source[1])

    if properties.get("longitude") in (None, ""):
        source = _first_present(properties, LONGITUDE_ALIASES)
        if source:
            number = _coerce_float(source[1])
            if number is not None and -180 <= number <= 180:
                properties["longitude"] = number
            elif number is not None:
                logger.warning("Ignoring out-of-range longitude: %r", source[1])

    if properties.get("location_raw") in (None, ""):
        source = _first_present(properties, LOCATION_RAW_ALIASES)
        if source and isinstance(source[1], str):
            text = " ".join(source[1].split())
            if text:
                properties["location_raw"] = text

    model_specificity = normalize_location_specificity(
        properties.get("location_specificity", properties.get("specificity"))
    )
    structured_specificity = infer_structured_location_specificity(properties)

    # Structured address parts are less ambiguous than a free-form model label.
    # A finer model label is retained only when location_raw contains additional
    # detail that the structured fields do not represent (for example a district
    # plus its containing city).
    if structured_specificity:
        raw_key = _canonical_key(str(properties.get("location_raw") or ""))
        structured_keys = {
            _canonical_key(str(properties.get(field) or ""))
            for field in ("address", "city", "region", "country")
            if properties.get(field) not in (None, "")
        }
        model_describes_finer_raw_text = (
            model_specificity is not None
            and location_specificity_rank(model_specificity)
            > location_specificity_rank(structured_specificity)
            and bool(raw_key)
            and raw_key not in structured_keys
        )
        properties["location_specificity"] = (
            model_specificity
            if model_describes_finer_raw_text
            else structured_specificity
        )
    elif model_specificity:
        properties["location_specificity"] = model_specificity
    elif properties.get("location_raw") not in (None, ""):
        properties["location_specificity"] = "unknown"


def _normalize_financial_properties(category: str, properties: dict[str, Any]) -> None:
    financial_like = category in {"Transaction", "Event"} or bool(properties.get("is_financial_event"))
    if not financial_like:
        return

    if properties.get("amount") in (None, ""):
        source = _first_present(properties, AMOUNT_ALIASES)
        if source:
            properties["amount"] = source[1]

    if properties.get("sender") in (None, ""):
        source = _first_present(properties, SENDER_ALIASES)
        if source and isinstance(source[1], str):
            properties["sender"] = source[1].strip()

    if properties.get("receiver") in (None, ""):
        source = _first_present(properties, RECEIVER_ALIASES)
        if source and isinstance(source[1], str):
            properties["receiver"] = source[1].strip()


def _normalize_aliases(properties: dict[str, Any]) -> None:
    aliases = properties.get("aliases")
    if aliases in (None, ""):
        return
    if isinstance(aliases, str):
        parts = [part.strip() for part in re.split(r"[,;]", aliases) if part.strip()]
        properties["aliases"] = parts
    elif isinstance(aliases, (list, tuple, set)):
        normalized = []
        for item in aliases:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        properties["aliases"] = normalized


def canonicalize_properties(
    category: str,
    properties: dict[str, Any] | None,
    *,
    evidence_texts: list[str] | None = None,
) -> dict[str, Any]:
    """Return a canonicalized copy of extracted graph properties.

    The function only adds canonical fields when a directly related source field
    exists. It does not delete the original field, so provenance and debugging
    detail remain available to investigators and future backfills.
    """
    normalized = dict(properties or {})
    _normalize_aliases(normalized)
    _normalize_temporal_properties(category, normalized, evidence_texts=evidence_texts)
    _normalize_geo_properties(normalized)
    _normalize_financial_properties(category, normalized)
    return normalized


def is_neo4j_primitive_list(value: Any) -> bool:
    """Return true for list values Neo4j can store directly."""
    return isinstance(value, list) and all(
        isinstance(item, (str, int, float, bool)) for item in value
    )
