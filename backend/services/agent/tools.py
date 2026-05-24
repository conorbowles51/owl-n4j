from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Literal

from neo4j import READ_ACCESS
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from services.agent.cypher_safety import UnsafeCypherError, repair_common_cypher, run_readonly_cypher
from services.agent.json_utils import to_jsonable, truncate_payload, truncate_text
from services.neo4j.driver import driver
from services.neo4j.financial_service import financial_service
from services.neo4j.geo_service import geo_service
from services.neo4j.graph_service import graph_service
from services.neo4j.timeline_service import timeline_service
from services.vector_db_service import get_vector_db_service


@dataclass
class AgentToolContext:
    case_id: str
    artifact_preference: str = "auto"
    result_store: dict[str, Any] = field(default_factory=dict)

    def result(
        self,
        tool_name: str,
        data: Any,
        *,
        summary: str,
        artifact: dict[str, Any] | None = None,
        status: Literal["success", "error"] = "success",
        error: str | None = None,
    ) -> dict[str, Any]:
        result_id = f"res_{uuid.uuid4().hex[:12]}"
        safe_data = to_jsonable(data)
        self.result_store[result_id] = safe_data
        payload = {
            "result_id": result_id,
            "status": status,
            "summary": summary,
            "data": safe_data,
        }
        if error:
            payload["error"] = error
        if artifact:
            payload["artifact"] = artifact
        return payload


class EmptyArgs(BaseModel):
    pass


class ClarificationOptionArgs(BaseModel):
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None


class ClarificationArgs(BaseModel):
    question: str = Field(..., min_length=1)
    options: list[ClarificationOptionArgs] = Field(..., min_length=2, max_length=4)
    allow_free_text: bool = True
    reason: str | None = None


class SearchGraphEntitiesArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Name, alias, key, or phrase to search for.")
    limit: int = Field(10, ge=1, le=25)


class EntityKeyArgs(BaseModel):
    entity_key: str = Field(..., min_length=1, description="Exact graph node key.")


class EntityNeighborhoodArgs(EntityKeyArgs):
    depth: int = Field(1, ge=1, le=3)


class PathArgs(BaseModel):
    source_key: str = Field(..., min_length=1)
    target_key: str = Field(..., min_length=1)
    max_depth: int = Field(4, ge=1, le=6)


class SearchDocumentsArgs(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(8, ge=1, le=20)


class ReadonlyCypherArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Read-only Cypher. Must include $case_id.")
    params: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(50, ge=1, le=200)


class TimelineArgs(BaseModel):
    event_types: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(25, ge=1, le=100)


class FinancialArgs(BaseModel):
    entity_keys: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    categories: list[str] | None = None
    mode: Literal["transactions", "intelligence"] = "transactions"
    limit: int = Field(25, ge=1, le=100)


class MapArgs(BaseModel):
    entity_types: list[str] | None = None
    entity_keys: list[str] | None = None
    limit: int = Field(50, ge=1, le=200)


class GraphArtifactArgs(BaseModel):
    node_keys: list[str] = Field(default_factory=list)
    title: str | None = None
    depth: int = Field(1, ge=0, le=3)
    mode: Literal[
        "entity_neighborhood",
        "transaction_only",
        "transactions_plus_accounts",
        "transaction_flow",
        "shortest_paths",
    ] = "entity_neighborhood"
    node_types: list[str] | None = None
    relationship_types: list[str] | None = None
    max_nodes: int = Field(75, ge=1, le=250)
    max_relationships: int = Field(200, ge=0, le=500)
    include_bridge_nodes: bool = True


class TimelineArtifactArgs(BaseModel):
    title: str | None = None
    event_keys: list[str] = Field(default_factory=list)
    entity_keys: list[str] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    mode: Literal["direct_only", "communications_only", "communications_plus_related"] = "communications_plus_related"
    include_documents: bool = False
    limit: int = Field(50, ge=1, le=200)


class TableArtifactArgs(BaseModel):
    title: str | None = None
    query: str = Field(..., min_length=1, description="Read-only Cypher that returns table rows and includes $case_id.")
    params: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(50, ge=1, le=200)


class MapArtifactArgs(BaseModel):
    title: str | None = None
    entity_keys: list[str] = Field(default_factory=list)
    entity_types: list[str] | None = None
    limit: int = Field(100, ge=1, le=200)


class FinancialArtifactArgs(FinancialArgs):
    title: str | None = None


def _artifact(artifact_type: str, title: str, data: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": artifact_type,
        "title": title,
        "data": to_jsonable(data),
        "metadata": to_jsonable(metadata or {}),
    }


def _graph_counts(graph: dict[str, Any]) -> str:
    return f"{len(graph.get('nodes') or [])} nodes and {len(graph.get('links') or [])} relationships"


def _compact_node(node: dict[str, Any]) -> dict[str, Any]:
    props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    key = node.get("key") or props.get("key") or node.get("id")
    return {
        "id": node.get("id") or key,
        "key": key,
        "name": node.get("name") or props.get("name") or key,
        "type": node.get("type") or props.get("type"),
        "summary": truncate_text(node.get("summary") or props.get("summary"), 500),
        "date": node.get("date") or props.get("date"),
        "amount": node.get("amount") or props.get("amount"),
    }


def _compact_link(link: dict[str, Any]) -> dict[str, Any]:
    props = link.get("properties") if isinstance(link.get("properties"), dict) else {}
    compact_props = {
        key: truncate_text(props.get(key), 300)
        for key in ("detail", "date", "amount", "currency", "confidence")
        if props.get(key) is not None
    }
    source_files = props.get("source_files")
    if isinstance(source_files, list):
        compact_props["source_files"] = source_files[:5]
    return {
        "source": link.get("source"),
        "target": link.get("target"),
        "type": link.get("type"),
        "properties": compact_props,
    }


def _compact_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [_compact_node(node) for node in as_dict_list(graph.get("nodes"))],
        "links": [_compact_link(link) for link in as_dict_list(graph.get("links"))],
    }


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _filter_transactions(
    transactions: list[dict[str, Any]],
    *,
    entity_keys: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    keys = set(entity_keys or [])
    filtered: list[dict[str, Any]] = []
    for tx in transactions:
        if keys:
            from_entity = tx.get("from_entity") or {}
            to_entity = tx.get("to_entity") or {}
            if tx.get("key") not in keys and from_entity.get("key") not in keys and to_entity.get("key") not in keys:
                continue
        filtered.append(tx)
        if len(filtered) >= limit:
            break
    return filtered


def _events_for_keys(case_id: str, event_keys: list[str], limit: int) -> list[dict[str, Any]]:
    if not event_keys:
        return []
    rows = run_readonly_cypher(
        """
        MATCH (n)
        WHERE n.case_id = $case_id AND n.key IN $event_keys AND n.date IS NOT NULL
        RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
               n.date AS date, n.time AS time, n.amount AS amount,
               n.summary AS summary, n.notes AS notes
        ORDER BY n.date ASC, coalesce(n.time, '') ASC
        """,
        case_id=case_id,
        params={"event_keys": event_keys},
        limit=limit,
    )
    return rows


def _events_for_entities(
    case_id: str,
    entity_keys: list[str],
    start_date: str | None,
    end_date: str | None,
    limit: int,
    *,
    mode: Literal["direct_only", "communications_only", "communications_plus_related"] = "communications_plus_related",
) -> list[dict[str, Any]]:
    if not entity_keys:
        return []
    params: dict[str, Any] = {"entity_keys": entity_keys}
    filters = ["n.case_id = $case_id", "n.date IS NOT NULL"]
    depth = 1 if mode in {"direct_only", "communications_only"} else 2
    if mode == "communications_only":
        filters.append("labels(n)[0] = 'Communication'")
    elif mode == "communications_plus_related":
        filters.append("labels(n)[0] IN ['Communication', 'Event', 'Transaction', 'LegalAction']")
    if start_date:
        filters.append("n.date >= $start_date")
        params["start_date"] = start_date
    if end_date:
        filters.append("n.date <= $end_date")
        params["end_date"] = end_date
    where_clause = " AND ".join(filters)
    query = f"""
        MATCH (entity)
        WHERE entity.case_id = $case_id AND entity.key IN $entity_keys
        MATCH (entity)-[*0..{depth}]-(n)
        WHERE {where_clause}
        RETURN DISTINCT n.key AS key, n.name AS name, labels(n)[0] AS type,
               n.date AS date, n.time AS time, n.amount AS amount,
               n.summary AS summary, n.notes AS notes
        ORDER BY n.date ASC, coalesce(n.time, '') ASC
    """
    rows = run_readonly_cypher(query, case_id=case_id, params=params, limit=limit)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = str(row.get("key") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(row)
    return deduped


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    return [{"key": key, "label": key.replace("_", " ").title()} for key in keys]


def _find_paths(case_id: str, source_key: str, target_key: str, max_depth: int) -> list[dict[str, Any]]:
    depth = max(1, min(max_depth, 6))
    query = f"""
        MATCH (source {{key: $source_key, case_id: $case_id}})
        MATCH (target {{key: $target_key, case_id: $case_id}})
        MATCH path = allShortestPaths((source)-[*..{depth}]-(target))
        WHERE all(node IN nodes(path) WHERE node.case_id = $case_id)
          AND all(rel IN relationships(path) WHERE rel.case_id = $case_id)
        RETURN
          [node IN nodes(path) | {{
            key: node.key,
            name: node.name,
            type: labels(node)[0],
            summary: left(coalesce(node.summary, ''), 500)
          }}] AS nodes,
          [rel IN relationships(path) | {{
            source: startNode(rel).key,
            target: endNode(rel).key,
            type: type(rel),
            properties: properties(rel)
          }}] AS relationships
        LIMIT 5
    """
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            query,
            case_id=case_id,
            source_key=source_key,
            target_key=target_key,
        )
        return [to_jsonable(dict(row)) for row in rows]


def _graph_node_map(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    props = node.get("properties") if isinstance(node.get("properties"), dict) else node
    key = node.get("key") or props.get("key") or node.get("id")
    return {
        "id": node.get("id") or key,
        "key": key,
        "name": node.get("name") or props.get("name") or key,
        "type": node.get("type") or props.get("type"),
        "summary": node.get("summary") or props.get("summary"),
        "date": node.get("date") or props.get("date"),
        "amount": node.get("amount") or props.get("amount"),
        "properties": props if props is not node else {},
    }


def _relationship_map(rel: Any) -> dict[str, Any]:
    if not isinstance(rel, dict):
        return {}
    return {
        "source": rel.get("source"),
        "target": rel.get("target"),
        "type": rel.get("type"),
        "properties": rel.get("properties") if isinstance(rel.get("properties"), dict) else {},
    }


def _dedupe_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes_by_key: dict[str, dict[str, Any]] = {}
    for raw in as_dict_list(graph.get("nodes")):
        node = _graph_node_map(raw)
        key = node.get("key")
        if key and key not in nodes_by_key:
            nodes_by_key[key] = node

    seen_links: set[tuple[str, str, str]] = set()
    links: list[dict[str, Any]] = []
    for raw in as_dict_list(graph.get("links")):
        link = _relationship_map(raw)
        source = link.get("source")
        target = link.get("target")
        rel_type = link.get("type") or "RELATED_TO"
        if not source or not target:
            continue
        marker = (str(source), str(target), str(rel_type))
        if marker in seen_links:
            continue
        seen_links.add(marker)
        links.append(link)

    return {"nodes": list(nodes_by_key.values()), "links": links}


def _limit_graph(
    graph: dict[str, Any],
    *,
    max_nodes: int,
    max_relationships: int,
    focus_keys: list[str] | None = None,
) -> dict[str, Any]:
    focus = set(focus_keys or [])
    nodes = as_dict_list(graph.get("nodes"))
    links = as_dict_list(graph.get("links"))
    degree: dict[str, int] = {}
    for link in links:
        source = str(link.get("source") or "")
        target = str(link.get("target") or "")
        if source:
            degree[source] = degree.get(source, 0) + 1
        if target:
            degree[target] = degree.get(target, 0) + 1

    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            0 if node.get("key") in focus else 1,
            -degree.get(str(node.get("key") or ""), 0),
            str(node.get("name") or node.get("key") or ""),
        ),
    )[:max_nodes]
    kept = {node.get("key") for node in ordered_nodes if node.get("key")}
    kept_links = [
        link
        for link in links
        if link.get("source") in kept and link.get("target") in kept
    ][:max_relationships]
    return {"nodes": ordered_nodes, "links": kept_links}


def _filter_graph(
    graph: dict[str, Any],
    *,
    node_types: list[str] | None = None,
    relationship_types: list[str] | None = None,
    include_bridge_nodes: bool = True,
    focus_keys: list[str] | None = None,
    max_nodes: int = 75,
    max_relationships: int = 200,
) -> dict[str, Any]:
    deduped = _dedupe_graph(graph)
    allowed_nodes = {item.lower() for item in (node_types or []) if item}
    allowed_rels = {item.upper() for item in (relationship_types or []) if item}
    focus = set(focus_keys or [])

    all_nodes = as_dict_list(deduped.get("nodes"))
    all_links = as_dict_list(deduped.get("links"))
    initial_keys = {
        node.get("key")
        for node in all_nodes
        if node.get("key")
        and (not allowed_nodes or str(node.get("type") or "").lower() in allowed_nodes or node.get("key") in focus)
    }
    links = [
        link
        for link in all_links
        if not allowed_rels or str(link.get("type") or "").upper() in allowed_rels
    ]

    if include_bridge_nodes and allowed_nodes:
        kept_keys = set(initial_keys)
        for link in links:
            source = link.get("source")
            target = link.get("target")
            if source in initial_keys or target in initial_keys:
                if source:
                    kept_keys.add(source)
                if target:
                    kept_keys.add(target)
    else:
        kept_keys = set(initial_keys)

    filtered = {
        "nodes": [node for node in all_nodes if node.get("key") in kept_keys],
        "links": [
            link
            for link in links
            if link.get("source") in kept_keys and link.get("target") in kept_keys
        ],
    }
    return _limit_graph(
        filtered,
        max_nodes=max_nodes,
        max_relationships=max_relationships,
        focus_keys=focus_keys,
    )


def _query_nodes_graph(case_id: str, node_keys: list[str] | None, node_types: list[str] | None, limit: int) -> dict[str, Any]:
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            """
            MATCH (n)
            WHERE n.case_id = $case_id
              AND (size($node_keys) = 0 OR n.key IN $node_keys)
              AND (size($node_types) = 0 OR labels(n)[0] IN $node_types)
            RETURN n.id AS id, n.key AS key, n.name AS name, labels(n)[0] AS type,
                   n.summary AS summary, n.date AS date, n.amount AS amount,
                   properties(n) AS properties
            ORDER BY coalesce(n.date, ''), coalesce(n.name, n.key)
            LIMIT $limit
            """,
            case_id=case_id,
            node_keys=node_keys or [],
            node_types=node_types or [],
            limit=max(1, min(limit, 250)),
        )
        nodes = [_graph_node_map(dict(row)) for row in rows]
    return {"nodes": nodes, "links": []}


def _transaction_flow_graph(
    case_id: str,
    *,
    node_keys: list[str] | None,
    neighbor_types: list[str],
    relationship_types: list[str] | None,
    limit: int,
) -> dict[str, Any]:
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            """
            MATCH (t:Transaction)
            WHERE t.case_id = $case_id
              AND (size($node_keys) = 0 OR t.key IN $node_keys)
            WITH t
            ORDER BY coalesce(t.date, ''), coalesce(t.name, t.key)
            LIMIT $limit
            OPTIONAL MATCH (t)-[r]-(n)
            WHERE r.case_id = $case_id
              AND n.case_id = $case_id
              AND (size($neighbor_types) = 0 OR labels(n)[0] IN $neighbor_types)
              AND (size($relationship_types) = 0 OR type(r) IN $relationship_types)
            RETURN collect(DISTINCT {
                id: t.id, key: t.key, name: t.name, type: labels(t)[0],
                summary: t.summary, date: t.date, amount: t.amount, properties: properties(t)
            }) AS transaction_nodes,
            collect(DISTINCT CASE WHEN n IS NULL THEN NULL ELSE {
                id: n.id, key: n.key, name: n.name, type: labels(n)[0],
                summary: n.summary, date: n.date, amount: n.amount, properties: properties(n)
            } END) AS neighbor_nodes,
            collect(DISTINCT CASE WHEN r IS NULL THEN NULL ELSE {
                source: startNode(r).key, target: endNode(r).key,
                type: type(r), properties: properties(r)
            } END) AS links
            """,
            case_id=case_id,
            node_keys=node_keys or [],
            neighbor_types=neighbor_types,
            relationship_types=relationship_types or [],
            limit=max(1, min(limit, 250)),
        )
        record = rows.single()
    if not record:
        return {"nodes": [], "links": []}
    return {
        "nodes": [item for item in [*(record["transaction_nodes"] or []), *(record["neighbor_nodes"] or [])] if item],
        "links": [item for item in (record["links"] or []) if item],
    }


def _shortest_path_graph(case_id: str, node_keys: list[str], max_depth: int) -> dict[str, Any]:
    if len(node_keys) < 2:
        return {"nodes": [], "links": []}
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for source_key, target_key in combinations(list(dict.fromkeys(node_keys))[:8], 2):
        for row in _find_paths(case_id, source_key, target_key, max_depth):
            nodes.extend(row.get("nodes") or [])
            links.extend(row.get("relationships") or [])
    return _dedupe_graph({"nodes": nodes, "links": links})


def make_agent_tools(context: AgentToolContext) -> list[StructuredTool]:
    def request_clarification(
        question: str,
        options: list[dict[str, Any]],
        allow_free_text: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any]:
        raw_options = [
            option.model_dump() if isinstance(option, BaseModel) else option
            for option in options
            if isinstance(option, (dict, BaseModel))
        ]
        clarification = {
            "question": question,
            "options": [
                {
                    "id": str(option.get("id") or f"option_{index}"),
                    "label": str(option.get("label") or option.get("id") or f"Option {index}"),
                    "description": option.get("description"),
                }
                for index, option in enumerate(raw_options[:4], start=1)
            ],
            "allow_free_text": allow_free_text,
            "context": {"reason": reason or "agent_requested_clarification"},
        }
        return context.result(
            "request_clarification",
            {"clarification": clarification},
            summary=f"Requested clarification: {question}",
            artifact=None,
        ) | {"clarification": clarification}

    def get_case_overview() -> dict[str, Any]:
        summary = graph_service.get_graph_summary(context.case_id)
        compact = {
            "total_nodes": summary.get("total_nodes", 0),
            "total_relationships": summary.get("total_relationships", 0),
            "entity_types": summary.get("entity_types", {}),
            "relationship_types": summary.get("relationship_types", {}),
            "sample_entities": (summary.get("entities") or [])[:25],
        }
        return context.result(
            "get_case_overview",
            compact,
            summary=(
                f"Case has {compact['total_nodes']} nodes and "
                f"{compact['total_relationships']} relationships."
            ),
        )

    def search_graph_entities(query: str, limit: int = 10) -> dict[str, Any]:
        rows = graph_service.search_nodes(query=query, limit=limit, case_id=context.case_id)
        return context.result(
            "search_graph_entities",
            {"entities": rows, "count": len(rows)},
            summary=f"Found {len(rows)} graph entities matching '{query}'.",
        )

    def get_entity_details(entity_key: str) -> dict[str, Any]:
        details = graph_service.get_node_details(entity_key, case_id=context.case_id)
        return context.result(
            "get_entity_details",
            {"entity": details},
            summary=(f"Loaded details for {entity_key}." if details else f"No entity found for key {entity_key}."),
        )

    def get_entity_neighborhood(entity_key: str, depth: int = 1) -> dict[str, Any]:
        graph = graph_service.get_node_with_neighbours(entity_key, depth=depth, case_id=context.case_id)
        return context.result(
            "get_entity_neighborhood",
            graph,
            summary=f"Loaded {_graph_counts(graph)} around {entity_key}.",
        )

    def find_paths_between_entities(source_key: str, target_key: str, max_depth: int = 4) -> dict[str, Any]:
        paths = _find_paths(context.case_id, source_key, target_key, max_depth)
        return context.result(
            "find_paths_between_entities",
            {"paths": paths, "count": len(paths)},
            summary=f"Found {len(paths)} shortest path(s) between {source_key} and {target_key}.",
        )

    def search_documents(query: str, limit: int = 8) -> dict[str, Any]:
        from services.vector_db_service import get_vector_db_health

        health = get_vector_db_health()
        vector_db = get_vector_db_service()
        if vector_db is None:
            reason = health.get("reason") or "Vector document search is not configured."
            return context.result(
                "search_documents",
                {"available": False, "health": health, "chunks": []},
                summary=f"Vector document search is unavailable: {reason}",
                status="error",
                error=str(reason),
            )
        from services.embedding_service import embedding_service
        if embedding_service is None:
            return context.result(
                "search_documents",
                {"available": False, "health": health, "chunks": []},
                summary="Vector document search is unavailable: embedding service is not configured.",
                status="error",
                error="Embedding service is not configured.",
            )

        embedding = embedding_service.generate_embedding(query)
        chunks = vector_db.search_chunks(
            embedding,
            top_k=limit,
            filter_metadata={"case_id": context.case_id},
        )
        compact = [
            {
                "id": chunk.get("id"),
                "text": truncate_text(chunk.get("text"), 1200),
                "metadata": chunk.get("metadata") or {},
                "distance": chunk.get("distance"),
            }
            for chunk in chunks
        ]
        return context.result(
            "search_documents",
            {"available": True, "health": health, "chunks": compact, "count": len(compact)},
            summary=f"Found {len(compact)} semantically similar document chunk(s).",
        )

    def run_cypher(query: str, params: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        repaired = repair_common_cypher(query)
        used_repair = repaired != query.strip()
        rows = run_readonly_cypher(repaired, case_id=context.case_id, params=params, limit=limit)
        return context.result(
            "run_readonly_cypher",
            {"rows": rows, "count": len(rows), "query": repaired, "repaired": used_repair},
            summary=(
                f"Read-only Cypher returned {len(rows)} row(s)"
                + (" after applying a safe syntax repair." if used_repair else ".")
            ),
        )

    def get_timeline_events(
        event_types: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        page = timeline_service.get_timeline_page(
            event_types=event_types,
            start_date=start_date,
            end_date=end_date,
            case_id=context.case_id,
            limit=limit,
        )
        return context.result(
            "get_timeline_events",
            page,
            summary=f"Loaded {page.get('count', 0)} timeline event(s).",
        )

    def get_financial_transactions(
        entity_keys: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        categories: list[str] | None = None,
        mode: Literal["transactions", "intelligence"] = "transactions",
        limit: int = 25,
    ) -> dict[str, Any]:
        data = financial_service.get_financial_transactions(
            case_id=context.case_id,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            mode=mode,
        )
        transactions = _filter_transactions(
            data.get("transactions") or [],
            entity_keys=entity_keys,
            limit=limit,
        )
        result = {**data, "transactions": transactions, "returned": len(transactions)}
        return context.result(
            "get_financial_transactions",
            result,
            summary=f"Loaded {len(transactions)} financial record(s).",
        )

    def get_map_locations(
        entity_types: list[str] | None = None,
        entity_keys: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        locations = geo_service.get_entities_with_locations(entity_types=entity_types, case_id=context.case_id)
        keys = set(entity_keys or [])
        if keys:
            locations = [location for location in locations if location.get("key") in keys]
        locations = locations[:limit]
        return context.result(
            "get_map_locations",
            {"locations": locations, "count": len(locations)},
            summary=f"Loaded {len(locations)} mapped location(s).",
        )

    def build_graph_artifact(
        node_keys: list[str] | None = None,
        title: str | None = None,
        depth: int = 1,
        mode: Literal[
            "entity_neighborhood",
            "transaction_only",
            "transactions_plus_accounts",
            "transaction_flow",
            "shortest_paths",
        ] = "entity_neighborhood",
        node_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
        max_nodes: int = 75,
        max_relationships: int = 200,
        include_bridge_nodes: bool = True,
    ) -> dict[str, Any]:
        keys = list(dict.fromkeys(node_keys or []))
        if mode == "transaction_only":
            graph = _query_nodes_graph(
                context.case_id,
                keys,
                ["Transaction"],
                max_nodes,
            )
        elif mode == "transactions_plus_accounts":
            graph = _transaction_flow_graph(
                context.case_id,
                node_keys=keys,
                neighbor_types=["Account"],
                relationship_types=relationship_types,
                limit=max_nodes,
            )
        elif mode == "transaction_flow":
            graph = _transaction_flow_graph(
                context.case_id,
                node_keys=keys,
                neighbor_types=node_types or ["Account", "Organization", "Person"],
                relationship_types=relationship_types,
                limit=max_nodes,
            )
        elif mode == "shortest_paths":
            graph = _shortest_path_graph(context.case_id, keys, max(1, depth or 1))
        elif keys and depth > 0:
            graph = graph_service.expand_nodes(keys, depth=depth, case_id=context.case_id)
        elif keys:
            context_rows = graph_service.get_context_for_nodes(keys, context.case_id).get("selected_entities") or []
            graph = {"nodes": context_rows, "links": []}
        else:
            graph = graph_service.get_graph_structure(context.case_id, limit=max_nodes, sort_by="degree")
        if mode != "transaction_only":
            graph = _filter_graph(
                graph,
                node_types=node_types,
                relationship_types=relationship_types,
                include_bridge_nodes=include_bridge_nodes,
                focus_keys=keys,
                max_nodes=max_nodes,
                max_relationships=max_relationships,
            )
        graph = _compact_graph(graph)
        artifact = _artifact(
            "graph",
            title or "Agent graph",
            graph,
            {
                "mode": mode,
                "depth": depth,
                "node_count": len(graph.get("nodes") or []),
                "relationship_count": len(graph.get("links") or []),
                "node_types": node_types or [],
                "relationship_types": relationship_types or [],
                "max_nodes": max_nodes,
                "max_relationships": max_relationships,
                "include_bridge_nodes": include_bridge_nodes,
            },
        )
        return context.result(
            "build_graph_artifact",
            {"artifact_id": artifact["id"], "summary": artifact["metadata"]},
            summary=f"Built graph artifact with {_graph_counts(graph)}.",
            artifact=artifact,
        )

    def build_timeline_artifact(
        title: str | None = None,
        event_keys: list[str] | None = None,
        entity_keys: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        mode: Literal["direct_only", "communications_only", "communications_plus_related"] = "communications_plus_related",
        include_documents: bool = False,
        limit: int = 50,
    ) -> dict[str, Any]:
        if event_keys:
            events = _events_for_keys(context.case_id, event_keys, limit)
        elif entity_keys:
            events = _events_for_entities(
                context.case_id,
                entity_keys,
                start_date,
                end_date,
                limit,
                mode=mode,
            )
        else:
            event_types = ["Communication"] if mode == "communications_only" else None
            events = timeline_service.get_timeline_page(
                event_types=event_types,
                start_date=start_date,
                end_date=end_date,
                case_id=context.case_id,
                limit=limit,
            ).get("events") or []
        artifact = _artifact(
            "timeline",
            title or "Agent timeline",
            {"events": events},
            {"event_count": len(events), "mode": mode, "include_documents": include_documents},
        )
        return context.result(
            "build_timeline_artifact",
            {"artifact_id": artifact["id"], "event_count": len(events)},
            summary=f"Built timeline artifact with {len(events)} event(s).",
            artifact=artifact,
        )

    def build_table_artifact(query: str, title: str | None = None, params: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        repaired = repair_common_cypher(query)
        rows = run_readonly_cypher(repaired, case_id=context.case_id, params=params, limit=limit)
        artifact = _artifact(
            "table",
            title or "Agent table",
            {"columns": _columns_from_rows(rows), "rows": rows},
            {"row_count": len(rows), "query": repaired, "repaired": repaired != query.strip()},
        )
        return context.result(
            "build_table_artifact",
            {"artifact_id": artifact["id"], "row_count": len(rows)},
            summary=f"Built table artifact with {len(rows)} row(s).",
            artifact=artifact,
        )

    def build_map_artifact(
        title: str | None = None,
        entity_keys: list[str] | None = None,
        entity_types: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        locations = geo_service.get_entities_with_locations(entity_types=entity_types, case_id=context.case_id)
        keys = set(entity_keys or [])
        if keys:
            locations = [location for location in locations if location.get("key") in keys]
        locations = locations[:limit]
        artifact = _artifact(
            "map",
            title or "Agent map",
            {"locations": locations},
            {"location_count": len(locations)},
        )
        return context.result(
            "build_map_artifact",
            {"artifact_id": artifact["id"], "location_count": len(locations)},
            summary=f"Built map artifact with {len(locations)} location(s).",
            artifact=artifact,
        )

    def build_financial_artifact(
        entity_keys: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        categories: list[str] | None = None,
        mode: Literal["transactions", "intelligence"] = "transactions",
        limit: int = 50,
        title: str | None = None,
    ) -> dict[str, Any]:
        data = financial_service.get_financial_transactions(
            case_id=context.case_id,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            mode=mode,
        )
        transactions = _filter_transactions(
            data.get("transactions") or [],
            entity_keys=entity_keys,
            limit=limit,
        )
        total_volume = sum(abs(float(tx.get("amount") or 0)) for tx in transactions)
        artifact_data = {
            "transactions": transactions,
            "total": len(transactions),
            "total_volume": round(total_volume, 2),
            "dataset_mode": data.get("dataset_mode"),
            "uses_legacy_financial_model": data.get("uses_legacy_financial_model"),
        }
        artifact = _artifact(
            "financial",
            title or "Agent financial view",
            artifact_data,
            {"transaction_count": len(transactions), "total_volume": round(total_volume, 2)},
        )
        return context.result(
            "build_financial_artifact",
            {"artifact_id": artifact["id"], "transaction_count": len(transactions)},
            summary=f"Built financial artifact with {len(transactions)} transaction(s).",
            artifact=artifact,
        )

    def wrap(func, *, name: str, description: str, args_schema: type[BaseModel]):
        def guarded(**kwargs):
            try:
                return func(**kwargs)
            except UnsafeCypherError as exc:
                return context.result(
                    name,
                    {"error": str(exc)},
                    summary=f"{name} rejected an unsafe Cypher query.",
                    status="error",
                    error=str(exc),
                )

        return StructuredTool.from_function(
            func=guarded,
            name=name,
            description=description,
            args_schema=args_schema,
        )

    return [
        StructuredTool.from_function(
            func=request_clarification,
            name="request_clarification",
            description=(
                "Pause and ask the user a clarification question with 2-4 answer options when a request is ambiguous. "
                "Use before building an artifact if two plausible interpretations would produce meaningfully different outputs."
            ),
            args_schema=ClarificationArgs,
        ),
        StructuredTool.from_function(
            func=get_case_overview,
            name="get_case_overview",
            description="Get case-level graph counts, available entity types, relationship types, and sample entities.",
            args_schema=EmptyArgs,
        ),
        wrap(
            search_graph_entities,
            name="search_graph_entities",
            description="Search graph entities by display name, key, summary, notes, or alias-like text.",
            args_schema=SearchGraphEntitiesArgs,
        ),
        wrap(
            get_entity_details,
            name="get_entity_details",
            description="Load detailed information and immediate connections for one exact graph entity key.",
            args_schema=EntityKeyArgs,
        ),
        wrap(
            get_entity_neighborhood,
            name="get_entity_neighborhood",
            description="Load a graph neighborhood around one exact entity key.",
            args_schema=EntityNeighborhoodArgs,
        ),
        wrap(
            find_paths_between_entities,
            name="find_paths_between_entities",
            description="Find shortest case-scoped relationship paths between two exact entity keys.",
            args_schema=PathArgs,
        ),
        wrap(
            search_documents,
            name="search_documents",
            description="Semantic search over ingested document chunks for the current case.",
            args_schema=SearchDocumentsArgs,
        ),
        wrap(
            run_cypher,
            name="run_readonly_cypher",
            description=(
                "Run a strictly read-only, case-scoped Neo4j Cypher query. Scope real nodes or relationships "
                "with .case_id = $case_id, put ORDER BY after RETURN, avoid NULLS FIRST/LAST, and use numeric LIMITs."
            ),
            args_schema=ReadonlyCypherArgs,
        ),
        wrap(
            get_timeline_events,
            name="get_timeline_events",
            description="Retrieve chronological events from the current case.",
            args_schema=TimelineArgs,
        ),
        wrap(
            get_financial_transactions,
            name="get_financial_transactions",
            description="Retrieve financial transaction or intelligence records, optionally focused on entity keys.",
            args_schema=FinancialArgs,
        ),
        wrap(
            get_map_locations,
            name="get_map_locations",
            description="Retrieve geocoded case entities for map reasoning.",
            args_schema=MapArgs,
        ),
        wrap(
            build_graph_artifact,
            name="build_graph_artifact",
            description=(
                "Create a focused graph artifact. Supports modes: entity_neighborhood, transaction_only, "
                "transactions_plus_accounts, transaction_flow, and shortest_paths. Use node/relationship filters "
                "and size caps to match the user's requested scope exactly."
            ),
            args_schema=GraphArtifactArgs,
        ),
        wrap(
            build_timeline_artifact,
            name="build_timeline_artifact",
            description=(
                "Create a deterministic timeline artifact. Use direct_only, communications_only, or "
                "communications_plus_related modes, then sort and deduplicate events chronologically."
            ),
            args_schema=TimelineArtifactArgs,
        ),
        wrap(
            build_table_artifact,
            name="build_table_artifact",
            description="Create a mini table artifact from a safe read-only Cypher query.",
            args_schema=TableArtifactArgs,
        ),
        wrap(
            build_map_artifact,
            name="build_map_artifact",
            description="Create a mini map artifact for display in the Agent workspace.",
            args_schema=MapArtifactArgs,
        ),
        wrap(
            build_financial_artifact,
            name="build_financial_artifact",
            description="Create a mini financial artifact for display in the Agent workspace.",
            args_schema=FinancialArtifactArgs,
        ),
    ]
