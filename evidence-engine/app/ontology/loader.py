"""Load and provide typed access to the ontology schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_PATH = Path(__file__).parent / "schema.yaml"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertyDef:
    name: str
    type: str
    description: str = ""
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class CategoryDef:
    name: str
    description: str
    properties: tuple[PropertyDef, ...]
    extraction_notes: str = ""


@dataclass(frozen=True)
class RelationshipDef:
    name: str
    description: str
    typical_source: tuple[str, ...] = ()
    typical_target: tuple[str, ...] = ()
    properties: tuple[PropertyDef, ...] = ()


@dataclass(frozen=True)
class DisambiguationRule:
    categories: tuple[str, ...]
    rule: str


@dataclass(frozen=True)
class ViewDef:
    name: str
    description: str
    categories: tuple[str, ...]
    date_field: str = ""
    requires: tuple[str, ...] = ()


@dataclass(frozen=True)
class OntologySchema:
    version: str
    _categories: dict[str, CategoryDef] = field(default_factory=dict)
    _relationships: dict[str, RelationshipDef] = field(default_factory=dict)
    disambiguation_rules: tuple[DisambiguationRule, ...] = ()
    _views: dict[str, ViewDef] = field(default_factory=dict)

    # -- Categories ----------------------------------------------------------

    @property
    def categories(self) -> list[str]:
        return list(self._categories.keys())

    def get_category(self, name: str) -> CategoryDef:
        return self._categories[name]

    # -- Relationships -------------------------------------------------------

    @property
    def relationship_types(self) -> list[str]:
        return list(self._relationships.keys())

    def get_relationship(self, name: str) -> RelationshipDef:
        return self._relationships[name]

    # -- Views ---------------------------------------------------------------

    @property
    def views(self) -> dict[str, ViewDef]:
        return dict(self._views)

    @property
    def temporal_categories(self) -> list[str]:
        """Categories that appear on the Timeline view."""
        view = self._views.get("timeline")
        return list(view.categories) if view else []

    @property
    def geocodable_categories(self) -> list[str]:
        """Categories that appear on the Map view."""
        view = self._views.get("map")
        return list(view.categories) if view else []

    @property
    def financial_categories(self) -> list[str]:
        """Categories that appear on the Financial view."""
        view = self._views.get("financial")
        return list(view.categories) if view else []


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------

def _parse_properties(props_raw: dict[str, Any]) -> tuple[PropertyDef, ...]:
    result = []
    for name, spec in props_raw.items():
        if isinstance(spec, dict):
            result.append(PropertyDef(
                name=name,
                type=spec.get("type", "string"),
                description=spec.get("description", ""),
                enum=tuple(str(v) for v in spec["enum"]) if "enum" in spec else (),
            ))
        else:
            result.append(PropertyDef(name=name, type="string"))
    return tuple(result)


def _parse_schema(raw: dict[str, Any]) -> OntologySchema:
    # Categories
    categories: dict[str, CategoryDef] = {}
    for name, spec in raw.get("entity_categories", {}).items():
        categories[name] = CategoryDef(
            name=name,
            description=spec.get("description", ""),
            properties=_parse_properties(spec.get("properties", {})),
            extraction_notes=spec.get("extraction_notes", "").strip(),
        )

    # Relationships
    relationships: dict[str, RelationshipDef] = {}
    for name, spec in raw.get("relationship_types", {}).items():
        relationships[name] = RelationshipDef(
            name=name,
            description=spec.get("description", ""),
            typical_source=tuple(spec.get("typical_source", [])),
            typical_target=tuple(spec.get("typical_target", [])),
            properties=_parse_properties(spec.get("properties", {})),
        )

    # Disambiguation
    disambiguation = tuple(
        DisambiguationRule(
            categories=tuple(r.get("categories", [])),
            rule=r.get("rule", "").strip(),
        )
        for r in raw.get("disambiguation", [])
    )

    # Views
    views: dict[str, ViewDef] = {}
    for name, spec in raw.get("views", {}).items():
        cats = spec.get("categories", [])
        if cats == "all":
            cats = list(categories.keys())
        views[name] = ViewDef(
            name=name,
            description=spec.get("description", ""),
            categories=tuple(cats),
            date_field=spec.get("date_field", ""),
            requires=tuple(spec.get("requires", [])),
        )

    return OntologySchema(
        version=str(raw.get("version", "1.0")),
        _categories=categories,
        _relationships=relationships,
        disambiguation_rules=disambiguation,
        _views=views,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_ontology(schema_path: str | None = None) -> OntologySchema:
    """Load the ontology schema from YAML. Cached after first call."""
    path = Path(schema_path) if schema_path else _SCHEMA_PATH
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _parse_schema(raw)
