from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


POSTGRES_NULL_REPLACEMENT = "\ufffd"


def sanitize_text(value: Any, *, none_as_empty: bool = True) -> str:
    """Remove text bytes PostgreSQL cannot store in text/jsonb columns."""
    text = "" if value is None and none_as_empty else str(value)
    return text.replace("\x00", POSTGRES_NULL_REPLACEMENT)


def to_jsonable(value: Any) -> Any:
    """Convert Neo4j, SQLAlchemy, and Python objects into JSON-safe data."""
    if value is None or isinstance(value, (int, bool)):
        return value
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {sanitize_text(k, none_as_empty=False): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]

    labels = getattr(value, "labels", None)
    if labels is not None and hasattr(value, "items"):
        return {
            "element_id": getattr(value, "element_id", None),
            "labels": list(labels),
            "properties": {str(k): to_jsonable(v) for k, v in dict(value.items()).items()},
        }

    rel_type = getattr(value, "type", None)
    if rel_type is not None and hasattr(value, "items"):
        return {
            "element_id": getattr(value, "element_id", None),
            "type": rel_type,
            "properties": {str(k): to_jsonable(v) for k, v in dict(value.items()).items()},
        }

    nodes = getattr(value, "nodes", None)
    relationships = getattr(value, "relationships", None)
    if nodes is not None and relationships is not None:
        return {
            "nodes": [to_jsonable(node) for node in nodes],
            "relationships": [to_jsonable(rel) for rel in relationships],
        }

    return sanitize_text(value)


def truncate_text(value: Any, max_chars: int = 1000) -> str:
    text = sanitize_text(value)
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def truncate_payload(value: Any, *, max_items: int = 25, max_text_chars: int = 1200) -> Any:
    safe = to_jsonable(value)
    if isinstance(safe, list):
        return [truncate_payload(item, max_items=max_items, max_text_chars=max_text_chars) for item in safe[:max_items]]
    if isinstance(safe, dict):
        return {
            key: truncate_payload(item, max_items=max_items, max_text_chars=max_text_chars)
            for key, item in list(safe.items())[:max_items]
        }
    if isinstance(safe, str):
        return truncate_text(safe, max_text_chars)
    return safe
