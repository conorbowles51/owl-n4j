"""Relationship aggregation helpers for AI entity merges."""

import re
from typing import Any


RELATIONSHIP_IDENTITY_PROPERTY_KEYS = frozenset(
    {"source_id", "target_id", "id", "case_id", "source", "target"}
)
RELATIONSHIP_PROVENANCE_PROPERTY_KEYS = frozenset({"source_files", "source_quotes"})


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
                {"case_id": case_id, "source_files": [], "source_quotes": []},
            )

            rel_props = rel.get("properties") or {}
            for provenance_key in RELATIONSHIP_PROVENANCE_PROPERTY_KEYS:
                bucket[provenance_key] = _union_lists(
                    bucket.get(provenance_key, []),
                    _as_list(rel.get(provenance_key)),
                    _as_list(rel_props.get(provenance_key)),
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

    return agg, source_names
