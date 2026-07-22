"""Relationship aggregation helpers for AI entity merges."""

import json
import re
from typing import Any


RELATIONSHIP_IDENTITY_PROPERTY_KEYS = frozenset(
    {"source_id", "target_id", "id", "case_id", "source", "target"}
)
RELATIONSHIP_LIST_PROVENANCE_PROPERTY_KEYS = frozenset(
    {"source_files", "source_quotes", "source_claim_ids"}
)
RELATIONSHIP_PROVENANCE_PROPERTY_KEYS = (
    RELATIONSHIP_LIST_PROVENANCE_PROPERTY_KEYS | {"source_locations"}
)


def _union_lists(*lists: list | None) -> list:
    seen: set[str] = set()
    result: list = []
    for lst in lists:
        for item in lst or []:
            key = str(item)
            if key not in seen:
                seen.add(key)
                result.append(item)
    return result


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return [item for item in value if item is not None]
    if isinstance(value, (str, int, float, bool)) and str(value):
        return [value]
    return []


def _as_source_locations(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _union_source_locations(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for locations in lists:
        for location in locations:
            key = json.dumps(location, sort_keys=True, separators=(",", ":"), default=str)
            if key not in seen:
                seen.add(key)
                result.append(location)
    return result


def _union_structured_records(*lists: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for records in lists:
        for record in records or []:
            if not isinstance(record, dict):
                continue
            key = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
            if key not in seen:
                seen.add(key)
                result.append(record)
    return result


def merge_entity_evidence(
    ai_merged: dict[str, Any],
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Overlay lossless, deterministic evidence onto AI-authored merge prose."""
    merged = dict(ai_merged)
    merged["verified_facts"] = _union_structured_records(
        *[entity.get("verified_facts") for entity in entities]
    )
    merged["ai_insights"] = _union_structured_records(
        *[entity.get("ai_insights") for entity in entities]
    )
    merged["source_files"] = _union_lists(
        *[entity.get("source_files") for entity in entities]
    )
    merged["source_quotes"] = _union_lists(
        *[entity.get("source_quotes") for entity in entities]
    )
    merged["source_claim_ids"] = _union_lists(
        *[
            _as_list(entity.get("source_claim_ids"))
            + _as_list((entity.get("properties") or {}).get("source_claim_ids"))
            for entity in entities
        ]
    )
    merged["source_locations"] = _union_source_locations(
        *[
            _as_source_locations(entity.get("source_locations"))
            + _as_source_locations((entity.get("properties") or {}).get("source_locations"))
            for entity in entities
        ]
    )
    return merged


def build_merge_result_state(
    current_state: dict[str, Any] | None,
    *,
    merged_entity_key: str,
    relationship_count: int,
) -> dict[str, Any]:
    state = dict(current_state or {})
    state["merge_result"] = {
        "merged_entity_key": merged_entity_key,
        "entity_count": 1,
        "relationship_count": relationship_count,
    }
    return state


def relationship_write_properties(
    properties: dict[str, Any],
    *,
    merged_entity_key: str,
    target_key: str,
    direction: str,
) -> dict[str, Any]:
    result = dict(properties)
    if direction == "incoming":
        result["source_id"] = target_key
        result["target_id"] = merged_entity_key
    else:
        result["source_id"] = merged_entity_key
        result["target_id"] = target_key
    return result


def aggregate_relationships_for_merge(
    entities: list[dict],
    case_id: str,
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str, str], str]]:
    source_key_set = {e.get("key") for e in entities if e.get("key")}
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    source_names: dict[tuple[str, str, str], str] = {}

    for entity in entities:
        for rel in entity.get("relationships") or []:
            target_key = rel.get("target_key", "")
            if not target_key or target_key in source_key_set:
                continue
            direction = rel.get("direction", "outgoing")
            if direction not in ("outgoing", "incoming"):
                direction = "outgoing"
            rel_type = rel.get("type", "RELATED_TO")
            safe_type = re.sub(r"[^A-Z0-9_]", "_", rel_type.upper()) or "RELATED_TO"
            key = (safe_type, direction, target_key)
            bucket = agg.setdefault(
                key,
                {
                    "case_id": case_id,
                    "source_files": [],
                    "source_quotes": [],
                    "source_claim_ids": [],
                    "_source_locations": [],
                },
            )

            rel_props = rel.get("properties") or {}
            for provenance_key in RELATIONSHIP_LIST_PROVENANCE_PROPERTY_KEYS:
                bucket[provenance_key] = _union_lists(
                    bucket.get(provenance_key, []),
                    _as_list(rel.get(provenance_key)),
                    _as_list(rel_props.get(provenance_key)),
                )
            bucket["_source_locations"] = _union_source_locations(
                bucket["_source_locations"],
                _as_source_locations(rel.get("source_locations")),
                _as_source_locations(rel_props.get("source_locations")),
            )

            for k, v in rel_props.items():
                if (
                    k not in RELATIONSHIP_IDENTITY_PROPERTY_KEYS
                    and k not in RELATIONSHIP_PROVENANCE_PROPERTY_KEYS
                    and isinstance(v, (str, int, float, bool))
                    and k not in bucket
                ):
                    bucket[k] = v
            source_names.setdefault(key, entity.get("name", "?"))

    for bucket in agg.values():
        source_locations = bucket.pop("_source_locations", [])
        bucket["source_locations"] = json.dumps(
            source_locations,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    return agg, source_names
