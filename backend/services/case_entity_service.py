"""
Case Entity Profile Service (Phase 5)

CaseEntity = an investigator-defined dossier for a person/address/event/device/
organisation/vehicle. Distinct from ingestion-derived Person/Location/... nodes —
used by the investigator to "build up evidence" around a subject.

Stored as Neo4j nodes with label CaseEntity. Linked to other graph nodes via
[:LINKED_TO] relationships. Linked to evidence records via each record's
linked_entity_ids field in evidence_storage.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.neo4j_service import neo4j_service
from services.evidence_storage import evidence_storage


# Accepted entity types (soft-validated — extend as needed)
ENTITY_TYPES = {
    "person",
    "address",
    "event",
    "device",
    "organisation",
    "vehicle",
    "other",
}


# Type-specific fields we persist verbatim when supplied in the patch.
TYPE_FIELDS: Dict[str, List[str]] = {
    "person": ["phone_numbers", "emails", "date_of_birth", "role"],
    "address": ["address", "coordinates_lat", "coordinates_lon"],
    "event": ["date", "address", "coordinates_lat", "coordinates_lon"],
    "device": ["device_model", "imei", "phone_numbers"],
    "organisation": ["address", "coordinates_lat", "coordinates_lon"],
    "vehicle": ["registration", "vehicle_make", "vehicle_model", "vehicle_color"],
    "other": [],
}


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _coerce_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None]
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    return []


def _build_props(
    case_id: str,
    entity_type: str,
    name: str,
    patch: Dict[str, Any],
    base: Optional[Dict[str, Any]] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the final property dict from the base + patch. Filters unknown fields."""
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Invalid entity_type: {entity_type}")
    now = _now_iso()
    props: Dict[str, Any] = dict(base or {})
    props.update(
        {
            "case_id": case_id,
            "entity_type": entity_type,
            "name": (name or "").strip(),
            "updated_at": now,
        }
    )
    if not base:
        props["id"] = f"ent_{uuid.uuid4().hex[:16]}"
        props["created_at"] = now
        props["status"] = "active"
        if created_by:
            props["created_by"] = created_by

    # Common string/list fields
    if "description" in patch:
        props["description"] = patch.get("description") or ""
    if "notes" in patch:
        props["notes"] = patch.get("notes") or ""
    if "aliases" in patch:
        props["aliases"] = _coerce_list(patch.get("aliases"))
    if "tags" in patch:
        props["tags"] = _coerce_list(patch.get("tags"))
    if "status" in patch:
        status = str(patch.get("status") or "active").lower()
        props["status"] = status if status in {"active", "archived"} else "active"

    # Type-specific fields
    for f in TYPE_FIELDS.get(entity_type, []):
        if f in patch:
            v = patch[f]
            if f in {"phone_numbers", "emails"}:
                props[f] = _coerce_list(v)
            elif f in {"coordinates_lat", "coordinates_lon"}:
                try:
                    props[f] = float(v) if v is not None and v != "" else None
                except (TypeError, ValueError):
                    props[f] = None
            else:
                props[f] = v

    # Drop None values so Neo4j isn't cluttered
    return {k: v for k, v in props.items() if v is not None and v != ""}


def _entity_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Neo4j node record to a plain dict for the API."""
    if rec is None:
        return None
    return dict(rec)


# ----------------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------------


def create_entity(
    case_id: str,
    entity_type: str,
    name: str,
    patch: Optional[Dict[str, Any]] = None,
    created_by: Optional[str] = None,
) -> Dict[str, Any]:
    if not name or not name.strip():
        raise ValueError("Entity name is required")
    props = _build_props(case_id, entity_type, name, patch or {}, created_by=created_by)
    with neo4j_service._driver.session() as session:
        result = session.run(
            """
            CREATE (e:CaseEntity $props)
            RETURN e
            """,
            props=props,
        )
        rec = result.single()
        return _entity_from_record(rec["e"]) if rec else None


def get_entity(case_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
    with neo4j_service._driver.session() as session:
        rec = session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})
            RETURN e LIMIT 1
            """,
            case_id=case_id,
            entity_id=entity_id,
        ).single()
        return _entity_from_record(rec["e"]) if rec else None


def list_entities(
    case_id: str,
    entity_type: Optional[str] = None,
    search: Optional[str] = None,
    status: str = "active",
    limit: int = 500,
) -> List[Dict[str, Any]]:
    where = ["e.case_id = $case_id"]
    params: Dict[str, Any] = {"case_id": case_id, "limit": int(limit)}
    if status:
        where.append("coalesce(e.status, 'active') = $status")
        params["status"] = status
    if entity_type and entity_type != "all":
        where.append("e.entity_type = $entity_type")
        params["entity_type"] = entity_type
    if search:
        where.append(
            "(toLower(e.name) CONTAINS toLower($search) "
            "OR any(a IN coalesce(e.aliases, []) WHERE toLower(a) CONTAINS toLower($search)) "
            "OR toLower(coalesce(e.description, '')) CONTAINS toLower($search))"
        )
        params["search"] = search
    where_clause = " AND ".join(where)
    cypher = f"""
        MATCH (e:CaseEntity)
        WHERE {where_clause}
        OPTIONAL MATCH (e)-[:LINKED_TO]->(n)
        WITH e, count(DISTINCT n) AS graph_node_count
        RETURN e, graph_node_count
        ORDER BY e.updated_at DESC
        LIMIT $limit
    """
    out: List[Dict[str, Any]] = []
    with neo4j_service._driver.session() as session:
        for rec in session.run(cypher, params):
            ent = _entity_from_record(rec["e"])
            ent["graph_node_count"] = int(rec["graph_node_count"] or 0)
            ent["evidence_count"] = len(
                evidence_storage.list_by_entity(case_id, ent["id"])
            )
            out.append(ent)
    return out


def update_entity(
    case_id: str,
    entity_id: str,
    patch: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    existing = get_entity(case_id, entity_id)
    if not existing:
        return None
    entity_type = patch.get("entity_type") or existing.get("entity_type")
    name = patch.get("name") or existing.get("name")
    props = _build_props(case_id, entity_type, name, patch, base=existing)
    # Preserve id + created_at
    props["id"] = existing["id"]
    props["created_at"] = existing.get("created_at") or props.get("created_at")
    if "created_by" in existing:
        props["created_by"] = existing["created_by"]
    with neo4j_service._driver.session() as session:
        rec = session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})
            SET e = $props
            RETURN e
            """,
            case_id=case_id,
            entity_id=entity_id,
            props=props,
        ).single()
        return _entity_from_record(rec["e"]) if rec else None


def archive_entity(case_id: str, entity_id: str) -> bool:
    with neo4j_service._driver.session() as session:
        rec = session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})
            SET e.status = 'archived', e.updated_at = $now
            RETURN e.id AS id
            """,
            case_id=case_id,
            entity_id=entity_id,
            now=_now_iso(),
        ).single()
        return rec is not None


def delete_entity(case_id: str, entity_id: str) -> bool:
    """Hard delete: removes the node, its graph links, and unlinks from all evidence."""
    evidence_storage.unlink_entities_from_all(case_id, entity_id)
    with neo4j_service._driver.session() as session:
        rec = session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})
            WITH e, e.id AS id
            DETACH DELETE e
            RETURN id
            """,
            case_id=case_id,
            entity_id=entity_id,
        ).single()
        return rec is not None


# ----------------------------------------------------------------------------
# Graph node linking
# ----------------------------------------------------------------------------


def link_graph_node(case_id: str, entity_id: str, node_key: str) -> bool:
    """Create a (CaseEntity)-[:LINKED_TO]->(node) edge for any case-scoped node with `key`."""
    with neo4j_service._driver.session() as session:
        rec = session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})
            MATCH (n {case_id: $case_id, key: $node_key})
            MERGE (e)-[:LINKED_TO]->(n)
            WITH e
            SET e.updated_at = $now
            RETURN e.id AS id
            """,
            case_id=case_id,
            entity_id=entity_id,
            node_key=node_key,
            now=_now_iso(),
        ).single()
        return rec is not None


def unlink_graph_node(case_id: str, entity_id: str, node_key: str) -> bool:
    with neo4j_service._driver.session() as session:
        session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})-[r:LINKED_TO]->(n {case_id: $case_id, key: $node_key})
            DELETE r
            """,
            case_id=case_id,
            entity_id=entity_id,
            node_key=node_key,
        )
        session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})
            SET e.updated_at = $now
            """,
            case_id=case_id,
            entity_id=entity_id,
            now=_now_iso(),
        )
        return True


# ----------------------------------------------------------------------------
# Evidence linking (delegates to evidence_storage)
# ----------------------------------------------------------------------------


def link_evidence(case_id: str, entity_id: str, evidence_ids: List[str]) -> int:
    return evidence_storage.link_entities(evidence_ids, [entity_id])


def unlink_evidence(case_id: str, entity_id: str, evidence_ids: List[str]) -> int:
    return evidence_storage.unlink_entities(evidence_ids, [entity_id])


# ----------------------------------------------------------------------------
# Full dossier
# ----------------------------------------------------------------------------


def get_entity_context(case_id: str, entity_id: str) -> Optional[Dict[str, Any]]:
    entity = get_entity(case_id, entity_id)
    if not entity:
        return None

    linked_nodes: List[Dict[str, Any]] = []
    timeline: List[Dict[str, Any]] = []
    by_label: Dict[str, int] = {}

    with neo4j_service._driver.session() as session:
        rs = session.run(
            """
            MATCH (e:CaseEntity {case_id: $case_id, id: $entity_id})-[:LINKED_TO]->(n)
            RETURN n, labels(n) AS labels
            ORDER BY coalesce(n.timestamp, n.date, n.updated_at) DESC
            """,
            case_id=case_id,
            entity_id=entity_id,
        )
        for rec in rs:
            n = dict(rec["n"])
            labels = list(rec["labels"] or [])
            label = labels[0] if labels else "Node"
            by_label[label] = by_label.get(label, 0) + 1
            summary = {
                "label": label,
                "key": n.get("key"),
                "name": n.get("name") or n.get("subject") or n.get("summary") or "",
                "timestamp": n.get("timestamp") or n.get("date") or None,
                "latitude": n.get("latitude"),
                "longitude": n.get("longitude"),
                "source_app": n.get("source_app"),
            }
            linked_nodes.append(summary)
            if summary["timestamp"]:
                timeline.append(summary)

    # Linked evidence
    linked_evidence = evidence_storage.list_by_entity(case_id, entity_id)

    # Sort timeline ascending
    timeline.sort(key=lambda x: x.get("timestamp") or "")

    return {
        "entity": entity,
        "linked_graph_nodes": linked_nodes,
        "linked_evidence": linked_evidence,
        "timeline": timeline,
        "stats": {
            "graph_node_count": len(linked_nodes),
            "evidence_count": len(linked_evidence),
            "by_label": by_label,
        },
    }
