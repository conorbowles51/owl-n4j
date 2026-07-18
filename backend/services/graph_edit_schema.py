"""Schema helpers for investigator-facing graph edits."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


SYSTEM_PROPERTY_KEYS = frozenset(
    {
        "id",
        "key",
        "label",
        "type",
        "case_id",
        "node_key",
        "job_id",
        "source_files",
        "source_quotes",
        "source_file",
        "source_quote",
        "verified_facts",
        "ai_insights",
        "confidence",
        "mentioned",
        "community_id",
        "embedding",
        "embedding_id",
        "vector_id",
        "system_node",
        "deleted_at",
        "deleted_by",
        "recycle_key",
        "original_key",
        "original_name",
        "manual_fields",
        "last_edited_at",
        "last_edited_by",
        "last_edit_source",
        "geocoding_status",
        "geocoding_confidence",
        "geocode_confidence",
        "geocode_source",
        "geocode_accuracy",
        "formatted_address",
        "nearest_location_key",
        "nearest_location_lat",
        "nearest_location_lon",
        "nearest_location_delta_s",
        "nearest_location_source",
        "location_source",
        "location_corrected_at",
        "location_corrected_by",
        "location_correction_source",
        "location_correction_address",
        "location_correction_undone_at",
        "location_correction_undone_by",
        "last_location_relocation_key",
    }
)

TIMELINE_PROPERTY_KEYS = frozenset({"date", "time", "date_precision"})
LOCATION_PROPERTY_KEYS = frozenset(
    {"latitude", "longitude", "location_raw", "location_formatted", "location_name"}
)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "evidence-engine" / "app" / "ontology" / "schema.yaml"


def _parse_properties(raw: dict[str, Any]) -> list[dict[str, Any]]:
    properties: list[dict[str, Any]] = []
    for name, spec in raw.items():
        if isinstance(spec, dict):
            properties.append(
                {
                    "name": name,
                    "type": spec.get("type", "string"),
                    "description": spec.get("description", ""),
                    "enum": list(spec.get("enum", [])),
                }
            )
        else:
            properties.append(
                {"name": name, "type": "string", "description": "", "enum": []}
            )
    return properties


@lru_cache(maxsize=1)
def get_graph_edit_schema() -> dict[str, Any]:
    """Return the ontology-backed edit schema consumed by Frontend V2."""
    with _schema_path().open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    category_specs = raw.get("entity_categories", {}) or {}
    categories = []
    category_properties: dict[str, list[dict[str, Any]]] = {}
    for name, spec in category_specs.items():
        properties = _parse_properties((spec or {}).get("properties", {}) or {})
        categories.append(
            {
                "name": name,
                "description": (spec or {}).get("description", ""),
                "properties": properties,
            }
        )
        category_properties[name] = properties

    views = raw.get("views", {}) or {}
    timeline = views.get("timeline", {}) or {}
    map_view = views.get("map", {}) or {}

    return {
        "version": str(raw.get("version", "1.0")),
        "categories": categories,
        "category_properties": category_properties,
        "timeline": {
            "categories": list(timeline.get("categories", []) or []),
            "date_field": timeline.get("date_field", "date"),
            "fields": [
                {"name": "date", "type": "date"},
                {"name": "time", "type": "time"},
                {
                    "name": "date_precision",
                    "type": "string",
                    "enum": ["day", "month", "year", "approximate"],
                },
            ],
        },
        "map": {
            "categories": list(map_view.get("categories", []) or []),
            "requires": list(map_view.get("requires", []) or ["latitude", "longitude"]),
            "fields": [
                {"name": "latitude", "type": "number"},
                {"name": "longitude", "type": "number"},
                {"name": "location_raw", "type": "string"},
                {"name": "location_formatted", "type": "string"},
                {"name": "location_name", "type": "string"},
            ],
        },
        "hidden_properties": sorted(SYSTEM_PROPERTY_KEYS),
        "system_properties": sorted(SYSTEM_PROPERTY_KEYS),
    }


def ontology_category_names() -> set[str]:
    return {category["name"] for category in get_graph_edit_schema()["categories"]}
