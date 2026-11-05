"""The one way a case entity is written to the graph: the graph screen's Create node and an accepted agent proposal.

``create_case_entity`` is the route's own path, moved here so a proposal a person accepted cannot take another. A
proposal passes ``key_suffix`` so its key cannot meet another entity's: the generated Cypher MERGEs on type and key,
and a shared key would overwrite that entity. ``same_name`` is the check a proposal makes first.
"""
from __future__ import annotations

import re
from typing import Any, Mapping


def entity_key(name: str, *, key_suffix: str | None = None) -> str:
    key = re.sub(r'[^a-z0-9]+', '-', name.strip().lower()).strip('-')
    if not key:
        key = f"node-{abs(hash(name)) % 1000000}"
    return f'{key}-{key_suffix}' if key_suffix else key


def create_case_entity(*, case_id: str, name: str, entity_type: str, summary: str | None = None,
                       notes: str | None = None, properties: Mapping[str, Any] | None = None,
                       key_suffix: str | None = None) -> tuple[str, str]:
    """Write the node; returns ``(key, cypher)``."""
    from services.cypher_generator import generate_cypher_from_graph
    from services.neo4j_service import neo4j_service
    key = entity_key(name, key_suffix=key_suffix)
    node = {"key": key, "name": name.strip(), "type": entity_type.strip(), "id": key,
            "summary": summary.strip() if summary else None, "notes": notes.strip() if notes else None}
    if properties:
        # Standard fields are handled above; the generator merges the rest with them.
        node["properties"] = {k: v for k, v in properties.items()
                              if k not in ('key', 'id', 'name', 'type', 'summary', 'notes', 'case_id')}
    cypher = generate_cypher_from_graph({"nodes": [node], "links": []}, case_id=str(case_id))
    neo4j_service.run_cypher(cypher, {})
    return key, cypher


def same_name(case_id: str, name: str) -> list[dict]:
    """Entities of this case with exactly this name, any type (first 5)."""
    from services.neo4j_service import neo4j_service
    rows = neo4j_service.run_cypher(
        "MATCH (n {case_id: $case_id}) WHERE toLower(n.name) = toLower($name) AND NOT coalesce(n.deleted, false) "
        "RETURN n.key AS key, n.name AS name, labels(n) AS labels LIMIT 5",
        {"case_id": str(case_id), "name": name.strip()})
    return [dict(r) for r in rows or []]
