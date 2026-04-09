"""Generate OpenAI Structured Output JSON schemas from the ontology."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.ontology.loader import OntologySchema, load_ontology


def _entity_item_schema(categories: list[str]) -> dict[str, Any]:
    """Schema for a single extracted entity."""
    financial_provenance_schema = {
        "type": "object",
        "properties": {
            "financial_record_kind": {
                "type": "string",
                "enum": [
                    "transaction",
                    "invoice",
                    "payment_instruction",
                    "balance",
                    "asset_value",
                    "fraud_total",
                    "allegation",
                    "summary_metric",
                    "other",
                ],
            },
            "financial_view_mode": {
                "type": "string",
                "enum": ["transaction", "intelligence"],
            },
            "is_financial_event": {"type": "boolean"},
            "is_evidence_backed_transaction": {"type": "boolean"},
            "evidence_strength": {
                "type": "string",
                "enum": ["documentary", "derived", "narrative", "unknown"],
            },
            "evidence_source_type": {
                "type": "string",
                "enum": [
                    "bank_statement",
                    "invoice",
                    "receipt",
                    "wire",
                    "card_statement",
                    "ledger",
                    "official_report",
                    "email",
                    "interview",
                    "other",
                ],
            },
            "source_page": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "null"},
                ]
            },
            "source_excerpt": {"type": "string"},
        },
        "required": [
            "financial_record_kind",
            "financial_view_mode",
            "is_financial_event",
            "is_evidence_backed_transaction",
            "evidence_strength",
            "evidence_source_type",
            "source_page",
            "source_excerpt",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": categories,
            },
            "specific_type": {"type": "string"},
            "name": {"type": "string"},
            "properties": {"type": "object"},
            "source_quote": {"type": "string"},
            "confidence": {"type": "number"},
            "verified_facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "quote": {"type": "string"},
                        "page": {
                            "anyOf": [
                                {"type": "integer"},
                                {"type": "null"},
                            ]
                        },
                        "importance": {"type": "integer"},
                    },
                    "required": ["text", "quote", "page", "importance"],
                    "additionalProperties": False,
                },
            },
            "ai_insights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "reasoning": {"type": "string"},
                    },
                    "required": ["text", "confidence", "reasoning"],
                    "additionalProperties": False,
                },
            },
            "financial_provenance": {
                "anyOf": [
                    financial_provenance_schema,
                    {"type": "null"},
                ]
            },
        },
        "required": [
            "category",
            "specific_type",
            "name",
            "properties",
            "source_quote",
            "confidence",
            "verified_facts",
            "ai_insights",
            "financial_provenance",
        ],
        "additionalProperties": False,
    }


def build_entity_schema(ontology: OntologySchema | None = None) -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for entity extraction.

    Category is enforced as an enum.  ``specific_type`` and ``properties``
    remain free-form so the AI can express fine-grained detail.
    """
    if ontology is None:
        ontology = load_ontology()

    return {
        "type": "json_schema",
        "json_schema": {
            "name": "entity_extraction",
            "schema": {
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": _entity_item_schema(ontology.categories),
                    },
                },
                "required": ["entities"],
                "additionalProperties": False,
            },
        },
    }


def build_relationship_schema() -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for relationship extraction.

    ``type`` is intentionally NOT constrained to an enum so the AI can create
    custom relationship types beyond the core set.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "relationship_extraction",
            "schema": {
                "type": "object",
                "properties": {
                    "relationships": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_entity_id": {"type": "string"},
                                "target_entity_id": {"type": "string"},
                                "type": {"type": "string"},
                                "detail": {"type": "string"},
                                "properties": {"type": "object"},
                                "source_quote": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": [
                                "source_entity_id",
                                "target_entity_id",
                                "type",
                                "detail",
                                "properties",
                                "source_quote",
                                "confidence",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["relationships"],
                "additionalProperties": False,
            },
        },
    }


def build_resolution_schema() -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for entity resolution."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "entity_resolution",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "decisions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pair_index": {"type": "integer"},
                                "decision": {
                                    "type": "string",
                                    "enum": ["MERGE", "KEEP_SEPARATE"],
                                },
                                "reasoning": {"type": "string"},
                            },
                            "required": ["pair_index", "decision", "reasoning"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["decisions"],
                "additionalProperties": False,
            },
        },
    }


def build_relationship_resolution_schema() -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for relationship resolution."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "relationship_resolution",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "decisions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "pair_index": {"type": "integer"},
                                "decision": {
                                    "type": "string",
                                    "enum": ["MERGE", "KEEP_SEPARATE"],
                                },
                                "canonical_type": {"type": "string"},
                                "reasoning": {"type": "string"},
                            },
                            "required": [
                                "pair_index",
                                "decision",
                                "canonical_type",
                                "reasoning",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["decisions"],
                "additionalProperties": False,
            },
        },
    }


def build_consolidation_schema() -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for entity consolidation."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "entity_consolidation",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                },
                                "canonical_name": {"type": "string"},
                                "reasoning": {"type": "string"},
                            },
                            "required": ["indices", "canonical_name", "reasoning"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["groups"],
                "additionalProperties": False,
            },
        },
    }


def build_summary_schema() -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for entity summary generation."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "entity_summaries",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summaries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entity_index": {"type": "integer"},
                                "summary": {"type": "string"},
                            },
                            "required": ["entity_index", "summary"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["summaries"],
                "additionalProperties": False,
            },
        },
    }


def build_merge_schema() -> dict[str, Any]:
    """Build the OpenAI Structured Output schema for entity merge.

    Uses non-strict mode because merged_properties has dynamic keys
    and fact/insight fields can be null.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "merged_entity",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "specific_type": {"type": "string"},
                    "category": {"type": "string"},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "verified_facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "quote": {"type": "string"},
                                "page": {"type": ["integer", "null"]},
                                "importance": {"type": ["integer", "null"]},
                                "source_doc": {"type": "string"},
                            },
                            "required": ["text"],
                        },
                    },
                    "ai_insights": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "confidence": {"type": "string"},
                                "reasoning": {"type": "string"},
                                "source_doc": {"type": "string"},
                            },
                            "required": ["text"],
                        },
                    },
                    "merged_properties": {
                        "type": "object",
                    },
                },
                "required": [
                    "name", "specific_type", "category", "summary",
                    "description", "verified_facts", "ai_insights",
                    "merged_properties",
                ],
            },
        },
    }


# ---------------------------------------------------------------------------
# Cached instances — built once per process
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_entity_schema() -> dict[str, Any]:
    return build_entity_schema()


@lru_cache(maxsize=1)
def get_relationship_schema() -> dict[str, Any]:
    return build_relationship_schema()


@lru_cache(maxsize=1)
def get_resolution_schema() -> dict[str, Any]:
    return build_resolution_schema()


@lru_cache(maxsize=1)
def get_relationship_resolution_schema() -> dict[str, Any]:
    return build_relationship_resolution_schema()


@lru_cache(maxsize=1)
def get_consolidation_schema() -> dict[str, Any]:
    return build_consolidation_schema()


@lru_cache(maxsize=1)
def get_merge_schema() -> dict[str, Any]:
    return build_merge_schema()


@lru_cache(maxsize=1)
def get_summary_schema() -> dict[str, Any]:
    return build_summary_schema()
