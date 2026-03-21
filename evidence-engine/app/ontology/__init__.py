"""Ontology module — single source of truth for entity categories and relationship types."""

from app.ontology.loader import (
    CategoryDef,
    DisambiguationRule,
    OntologySchema,
    PropertyDef,
    RelationshipDef,
    ViewDef,
    load_ontology,
)

__all__ = [
    "load_ontology",
    "OntologySchema",
    "CategoryDef",
    "RelationshipDef",
    "PropertyDef",
    "DisambiguationRule",
    "ViewDef",
    "ENTITY_CATEGORIES",
    "CORE_RELATIONSHIP_TYPES",
]


def _get_categories() -> list[str]:
    return load_ontology().categories


def _get_relationship_types() -> list[str]:
    return load_ontology().relationship_types


# Convenience constants — these are evaluated on first access.
# Import these when you just need the list of names.
ENTITY_CATEGORIES: list[str] = _get_categories()
CORE_RELATIONSHIP_TYPES: list[str] = _get_relationship_types()
