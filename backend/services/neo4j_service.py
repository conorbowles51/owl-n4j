"""
Neo4j Service - handles all database operations for the investigation console.
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from neo4j import GraphDatabase
import math
import random
import json
import re
import logging

logger = logging.getLogger(__name__)

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


def parse_json_field(value: Optional[str]) -> Optional[List]:
    """
    Parse a JSON string field into a Python list.
    
    Args:
        value: JSON string or None
        
    Returns:
        Parsed list or None if parsing fails
    """
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def safe_float(value, default=0) -> float:
    """Convert a value to float, returning default if it's None, NaN, or invalid."""
    if value is None:
        return default
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else round(f, 2)
    except (TypeError, ValueError):
        return default


class Neo4jService:
    """Service for Neo4j graph operations."""

    _instance = None
    _driver = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
            )
            self._ensure_case_id_index()
            # Track which cases have already been backfilled this process
            self._backfilled_keys: set = set()
            self._backfilled_refs: set = set()

    def _ensure_case_id_index(self):
        """Create index on case_id for performance."""
        try:
            with self._driver.session() as session:
                session.run("CREATE INDEX node_case_id IF NOT EXISTS FOR (n) ON (n.case_id)")
        except Exception:
            # Index may already exist or Neo4j version doesn't support this syntax
            pass

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    # -------------------------------------------------------------------------
    # Graph Visualization Data
    # -------------------------------------------------------------------------

    def get_full_graph(
        self,
        case_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, List]:
        """
        Get all nodes and relationships for visualization.

        Args:
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case
            start_date: Filter to include nodes with date >= start_date (YYYY-MM-DD) or connected to such nodes
            end_date: Filter to include nodes with date <= end_date (YYYY-MM-DD) or connected to such nodes

        Returns:
            Dict with 'nodes' and 'links' arrays
        """
        with self._driver.session() as session:
            # case_id is always required - always filter by it
            params = {"case_id": case_id}

            # Build date filter query
            if start_date or end_date:
                # Find nodes in date range and all nodes connected to them
                date_conditions = []

                if start_date:
                    date_conditions.append("n.date >= $start_date")
                    params["start_date"] = start_date
                if end_date:
                    date_conditions.append("n.date <= $end_date")
                    params["end_date"] = end_date

                date_filter = " AND " + " AND ".join(date_conditions)

                # Get nodes in date range and all nodes connected to them (directly or indirectly)
                query = f"""
                    // Find nodes with dates in range
                    MATCH (n)
                    WHERE n.case_id = $case_id AND n.date IS NOT NULL
                    {date_filter}

                    // Collect all nodes in range and their connections (up to 2 hops)
                    WITH collect(DISTINCT n) AS nodes_in_range
                    UNWIND nodes_in_range AS start_node

                    // Find all nodes connected to nodes in range (up to 2 hops)
                    MATCH path = (start_node)-[*0..2]-(connected)
                    WHERE connected.case_id = $case_id
                    WITH collect(DISTINCT start_node) + collect(DISTINCT connected) AS all_nodes
                    UNWIND all_nodes AS node

                    WITH DISTINCT node
                    RETURN
                        id(node) AS neo4j_id,
                        node.id AS id,
                        node.key AS key,
                        node.name AS name,
                        labels(node)[0] AS type,
                        node.summary AS summary,
                        node.notes AS notes,
                        properties(node) AS properties
                """
            else:
                # No date filter - get all nodes filtered by case_id
                query = """
                    MATCH (n)
                    WHERE n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
            
            nodes_result = session.run(query, **params)
            nodes = []
            node_keys = set()  # Track added nodes to avoid duplicates
            
            for record in nodes_result:
                node_key = record["key"]
                if node_key not in node_keys:
                    node_keys.add(node_key)
                    props = record["properties"] or {}
                    node = {
                        "neo4j_id": record["neo4j_id"],
                        "id": record["id"] or node_key,
                        "key": node_key,
                        "name": record["name"] or node_key,
                        "type": record["type"],
                        "summary": record["summary"],
                        "notes": record["notes"],
                        "verified_facts": parse_json_field(props.get("verified_facts")),
                        "ai_insights": parse_json_field(props.get("ai_insights")),
                        "properties": props,
                    }
                    nodes.append(node)

            # Get relationships between the filtered nodes
            if node_keys and len(node_keys) > 0:
                # Build parameter list for IN clause
                keys_list = list(node_keys)
                # Always filter relationships by case_id
                rels_query = """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $node_keys AND b.key IN $node_keys
                      AND r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                rels_result = session.run(rels_query, node_keys=keys_list, case_id=case_id)
            else:
                # No nodes, so no relationships
                rels_result = []
            
            links = []
            for record in rels_result:
                link = {
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                    "properties": record["properties"] or {},
                }
                links.append(link)

        return {"nodes": nodes, "links": links}

    def get_graph_structure(
        self,
        case_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        sort_by: Optional[str] = None,
    ) -> Dict[str, List]:
        """
        Lightweight graph structure for visualization — returns only the fields
        needed for rendering (key, name, type, confidence, mentioned) instead
        of full properties(n).  The on-demand detail endpoint still returns
        everything when a node is clicked.

        Args:
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case
            start_date: Filter to include nodes with date >= start_date (YYYY-MM-DD) or connected to such nodes
            end_date: Filter to include nodes with date <= end_date (YYYY-MM-DD) or connected to such nodes
            limit: Optional cap on number of nodes returned (top-N by sort_by)
            sort_by: Sort criterion when limit is set — 'degree' ranks by relationship count

        Returns:
            Dict with 'nodes' and 'links' arrays (slim payloads)
        """
        with self._driver.session() as session:
            params = {"case_id": case_id}

            # Smart cap: return top-N nodes by degree
            if limit and sort_by == "degree" and not start_date and not end_date:
                params["limit"] = limit

                # Get total node count first (fast count query)
                total_result = session.run(
                    "MATCH (n) WHERE n.case_id = $case_id RETURN count(n) AS cnt",
                    case_id=case_id,
                )
                total_node_count = total_result.single()["cnt"]

                nodes_result = session.run(
                    """
                    MATCH (n)
                    WHERE n.case_id = $case_id
                    OPTIONAL MATCH (n)-[r]-()
                    WHERE r.case_id = $case_id
                    WITH n, count(r) AS deg
                    ORDER BY deg DESC
                    LIMIT $limit
                    RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                           n.confidence AS confidence, n.mentioned AS mentioned
                    """,
                    **params,
                )
                nodes = []
                node_keys = set()
                for record in nodes_result:
                    nk = record["key"]
                    if nk not in node_keys:
                        node_keys.add(nk)
                        nodes.append({
                            "key": nk,
                            "name": record["name"] or nk,
                            "type": record["type"],
                            "confidence": record["confidence"],
                            "mentioned": record["mentioned"],
                        })

                links = []
                if node_keys:
                    rels_result = session.run(
                        """
                        MATCH (a)-[r]->(b)
                        WHERE a.key IN $node_keys AND b.key IN $node_keys
                          AND r.case_id = $case_id
                        RETURN a.key AS source, b.key AS target,
                               type(r) AS type, r.weight AS weight
                        """,
                        node_keys=list(node_keys), case_id=case_id,
                    )
                    for record in rels_result:
                        links.append({
                            "source": record["source"],
                            "target": record["target"],
                            "type": record["type"],
                            "weight": record["weight"],
                        })

                return {"nodes": nodes, "links": links, "total_node_count": total_node_count}

            if start_date or end_date:
                date_conditions = []
                if start_date:
                    date_conditions.append("n.date >= $start_date")
                    params["start_date"] = start_date
                if end_date:
                    date_conditions.append("n.date <= $end_date")
                    params["end_date"] = end_date

                date_filter = " AND " + " AND ".join(date_conditions)

                query = f"""
                    MATCH (n)
                    WHERE n.case_id = $case_id AND n.date IS NOT NULL
                    {date_filter}
                    WITH collect(DISTINCT n) AS nodes_in_range
                    UNWIND nodes_in_range AS start_node
                    MATCH path = (start_node)-[*0..2]-(connected)
                    WHERE connected.case_id = $case_id
                    WITH collect(DISTINCT start_node) + collect(DISTINCT connected) AS all_nodes
                    UNWIND all_nodes AS node
                    WITH DISTINCT node
                    RETURN
                        node.key AS key,
                        node.name AS name,
                        labels(node)[0] AS type,
                        node.confidence AS confidence,
                        node.mentioned AS mentioned
                """
            else:
                query = """
                    MATCH (n)
                    WHERE n.case_id = $case_id
                    RETURN
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.confidence AS confidence,
                        n.mentioned AS mentioned
                """

            nodes_result = session.run(query, **params)
            nodes = []
            node_keys = set()

            for record in nodes_result:
                node_key = record["key"]
                if node_key not in node_keys:
                    node_keys.add(node_key)
                    nodes.append({
                        "key": node_key,
                        "name": record["name"] or node_key,
                        "type": record["type"],
                        "confidence": record["confidence"],
                        "mentioned": record["mentioned"],
                    })

            if node_keys and len(node_keys) > 0:
                keys_list = list(node_keys)
                rels_query = """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $node_keys AND b.key IN $node_keys
                      AND r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        r.weight AS weight
                """
                rels_result = session.run(rels_query, node_keys=keys_list, case_id=case_id)
            else:
                rels_result = []

            links = []
            for record in rels_result:
                links.append({
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                    "weight": record["weight"],
                })

        return {"nodes": nodes, "links": links}

    def get_node_with_neighbours(self, key: str, depth: int = 1, case_id: str = None) -> Dict[str, List]:
        """
        Get a node and its neighbours up to specified depth.

        Args:
            key: The node key
            depth: How many hops to traverse (default 1)
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with 'nodes' and 'links' arrays
        """
        with self._driver.session() as session:
            # case_id is always required - always filter by it
            params = {"key": key, "case_id": case_id}

            # Get the central node and neighbours - always filter by case_id
            result = session.run(
                f"""
                MATCH path = (center {{key: $key}})-[*1..{depth}]-(neighbour)
                WHERE neighbour.case_id = $case_id
                WITH center, neighbour, relationships(path) AS rels
                UNWIND rels AS r
                WITH center, neighbour, collect(DISTINCT r) AS relationships
                RETURN
                    collect(DISTINCT {{
                        neo4j_id: id(center),
                        id: center.id,
                        key: center.key,
                        name: center.name,
                        type: labels(center)[0],
                        summary: center.summary,
                        notes: center.notes,
                        properties: properties(center)
                    }}) + collect(DISTINCT {{
                        neo4j_id: id(neighbour),
                        id: neighbour.id,
                        key: neighbour.key,
                        name: neighbour.name,
                        type: labels(neighbour)[0],
                        summary: neighbour.summary,
                        notes: neighbour.notes,
                        properties: properties(neighbour)
                    }}) AS nodes
                """,
                **params,
            )

            # Get nodes
            nodes = []
            seen_keys = set()
            record = result.single()
            if record and record["nodes"]:
                for node in record["nodes"]:
                    if node["key"] and node["key"] not in seen_keys:
                        seen_keys.add(node["key"])
                        nodes.append(node)

            # Get relationships between these nodes - always filter by case_id
            if seen_keys:
                rels_result = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $keys AND b.key IN $keys
                      AND r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                    """,
                    keys=list(seen_keys),
                    case_id=case_id,
                )
                links = [
                    {
                        "source": r["source"],
                        "target": r["target"],
                        "type": r["type"],
                        "properties": r["properties"] or {},
                    }
                    for r in rels_result
                ]
            else:
                links = []

        return {"nodes": nodes, "links": links}

    def expand_nodes(self, node_keys: List[str], depth: int = 1, case_id: str = None) -> Dict[str, List]:
        """
        Expand multiple nodes by N hops and return all nodes and relationships found.

        Args:
            node_keys: List of node keys to expand from
            depth: How many hops to traverse (default 1)
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with 'nodes' and 'links' arrays containing all expanded nodes and relationships
        """
        if not node_keys:
            return {"nodes": [], "links": []}

        with self._driver.session() as session:
            # Get all nodes reachable within depth hops from any of the starting nodes
            # Use a UNION approach to get all paths from all starting nodes
            all_node_keys = set(node_keys)

            # For each starting node, get all nodes within depth hops (always filter by case_id)
            for start_key in node_keys:
                params = {"start_key": start_key, "case_id": case_id}
                result = session.run(
                    f"""
                    MATCH path = (start {{key: $start_key}})-[*1..{depth}]-(neighbour)
                    WHERE neighbour.case_id = $case_id
                    RETURN DISTINCT neighbour.key AS key
                    """,
                    **params,
                )
                for record in result:
                    if record["key"]:
                        all_node_keys.add(record["key"])

            # Get full node details for all expanded nodes
            if not all_node_keys:
                return {"nodes": [], "links": []}

            # Always filter by case_id
            nodes_query = """
                MATCH (n)
                WHERE n.key IN $keys AND n.case_id = $case_id
                RETURN
                    id(n) AS neo4j_id,
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    properties(n) AS properties
            """
            nodes_result = session.run(nodes_query, keys=list(all_node_keys), case_id=case_id)
            nodes = []
            for record in nodes_result:
                nodes.append({
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "properties": record["properties"] or {}
                })

            # Get all relationships between these nodes - always filter by case_id
            rels_query = """
                MATCH (a)-[r]->(b)
                WHERE a.key IN $keys AND b.key IN $keys
                  AND r.case_id = $case_id
                RETURN
                    a.key AS source,
                    b.key AS target,
                    type(r) AS type,
                    properties(r) AS properties
            """
            rels_result = session.run(rels_query, keys=list(all_node_keys), case_id=case_id)
            links = [
                {
                    "source": r["source"],
                    "target": r["target"],
                    "type": r["type"],
                    "properties": r["properties"] or {},
                }
                for r in rels_result
            ]

        return {"nodes": nodes, "links": links}

    def get_node_details(self, key: str, case_id: str = None) -> Optional[Dict]:
        """
        Get detailed information about a single node.

        Args:
            key: The node key
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Node details dict or None, including parsed verified_facts and ai_insights
        """
        with self._driver.session() as session:
            # case_id is always required - always filter by it
            params = {"key": key, "case_id": case_id}

            result = session.run(
                """
                MATCH (n {key: $key})
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE connected.case_id = $case_id
                RETURN
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    n.verified_facts AS verified_facts,
                    n.ai_insights AS ai_insights,
                    properties(n) AS properties,
                    collect(DISTINCT {
                        key: connected.key,
                        name: connected.name,
                        type: labels(connected)[0],
                        relationship: type(r),
                        direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                    }) AS connections
                """,
                **params,
            )
            record = result.single()
            if record:
                # Parse JSON fields for verified_facts and ai_insights
                verified_facts = parse_json_field(record["verified_facts"])
                ai_insights = parse_json_field(record["ai_insights"])

                return {
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "verified_facts": verified_facts,
                    "ai_insights": ai_insights,
                    "properties": record["properties"],
                    "connections": [c for c in record["connections"] if c["key"]],
                }
        return None

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search_nodes(self, query: str, limit: int = 20, case_id: str = None) -> List[Dict]:
        """
        Search nodes by name, key, summary, or notes.

        Args:
            query: Search string
            limit: Max results
            case_id: REQUIRED - Filter to only include nodes belonging to this case

        Returns:
            List of matching nodes
        """
        with self._driver.session() as session:
            # Use a more robust search that handles null values and text normalization
            # Normalize the search term to lowercase for case-insensitive matching
            search_lower = query.lower().strip()
            # case_id is always required
            params = {"search_lower": search_lower, "limit": limit, "case_id": case_id}

            result = session.run(
                """
                MATCH (n)
                WHERE (
                    (n.name IS NOT NULL AND toLower(n.name) CONTAINS $search_lower)
                    OR (n.key IS NOT NULL AND toLower(n.key) CONTAINS $search_lower)
                    OR (n.summary IS NOT NULL AND toLower(n.summary) CONTAINS $search_lower)
                    OR (n.notes IS NOT NULL AND size(n.notes) > 0 AND toLower(n.notes) CONTAINS $search_lower)
                )
                AND n.case_id = $case_id
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes
                LIMIT $limit
                """,
                **params,
            )
            return [dict(r) for r in result]

    # -------------------------------------------------------------------------
    # Context for AI
    # -------------------------------------------------------------------------

    def get_graph_summary(self, case_id: str) -> Dict:
        """
        Get a summary of the entire graph for AI context.

        Args:
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with entity counts, types, and key entities
        """
        with self._driver.session() as session:
            params = {"case_id": case_id}

            # Count by type - always filter by case_id
            type_counts = session.run(
                """
                MATCH (n)
                WHERE n.case_id = $case_id
                RETURN labels(n)[0] AS type, count(*) AS count
                ORDER BY count DESC
                """,
                **params,
            )
            types = {r["type"]: r["count"] for r in type_counts}

            # Get all entities with summaries or notes (for AI context)
            entities_result = session.run(
                """
                MATCH (n)
                WHERE n.case_id = $case_id AND (n.summary IS NOT NULL OR n.notes IS NOT NULL)
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes
                ORDER BY n.name
                LIMIT 500
                """,
                **params,
            )
            entities = [dict(r) for r in entities_result]

            # Get relationship summary - always filter by case_id
            rel_counts = session.run(
                """
                MATCH ()-[r]->()
                WHERE r.case_id = $case_id
                RETURN type(r) AS type, count(*) AS count
                ORDER BY count DESC
                """,
                **params,
            )
            relationships = {r["type"]: r["count"] for r in rel_counts}

        return {
            "entity_types": types,
            "relationship_types": relationships,
            "total_nodes": sum(types.values()),
            "total_relationships": sum(relationships.values()),
            "entities": entities,
        }

    def get_context_for_nodes(self, keys: List[str], case_id: str) -> Dict:
        """
        Get detailed context for specific nodes (for focused AI queries).

        Args:
            keys: List of node keys to get context for
            case_id: The case ID to filter by

        Returns:
            Dict with detailed information about selected nodes
        """
        with self._driver.session() as session:
            # Get selected nodes with their connections (scoped to case)
            # Use a subquery to limit connections per node, preventing memory
            # explosion on hub nodes in large cases.
            result = session.run(
                """
                MATCH (n)
                WHERE n.key IN $keys
                  AND n.case_id = $case_id
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE connected.case_id = $case_id
                WITH n, r, connected
                ORDER BY CASE WHEN connected IS NULL THEN 1 ELSE 0 END, connected.name
                WITH n,
                     collect(DISTINCT {
                         key: connected.key,
                         name: connected.name,
                         type: labels(connected)[0],
                         summary: left(connected.summary, 500),
                         relationship: type(r),
                         direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                     })[0..25] AS connections
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    left(n.summary, 1000) AS summary,
                    left(n.notes, 1000) AS notes,
                    connections
                LIMIT 50
                """,
                keys=keys,
                case_id=case_id,
            )

            entities = []
            for record in result:
                entities.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "connections": [c for c in record["connections"] if c["key"]],
                })

        return {"selected_entities": entities}

    # -------------------------------------------------------------------------
    # Direct Cypher Queries
    # -------------------------------------------------------------------------

    def run_cypher(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Run a Cypher query and return results.
        
        Args:
            query: Cypher query string (should be a single query, not multiple)
            params: Query parameters
        
        Returns:
            List of result records as dicts
        """
        with self._driver.session() as session:
            # Use write transaction to ensure proper execution
            def work(tx):
                result = tx.run(query, params or {})
                return [dict(r) for r in result]
            return session.execute_write(work)
    
    def validate_cypher_batch(self, queries: List[str]) -> List[str]:
        """
        Sanity-check a batch of Cypher queries in a single transaction.
        
        Executes each query inside a transaction that is ALWAYS rolled back,
        so no changes are persisted. Collects any errors per-query.
        
        Returns:
            List of error strings. Empty list means all queries validated.
        """
        errors: List[str] = []
        if not queries:
            return errors

        with self._driver.session() as session:
            tx = session.begin_transaction()
            try:
                for idx, query in enumerate(queries):
                    q = (query or "").strip()
                    if not q:
                        continue
                    try:
                        tx.run(q)
                    except Exception as e:  # pragma: no cover - defensive
                        errors.append(f"Query {idx + 1} failed sanity check: {e}")
                # Always roll back - this is a dry run
                tx.rollback()
            except Exception:
                # If something unexpected happens, ensure rollback
                tx.rollback()
                raise

        return errors

    def execute_cypher_batch(self, queries: List[str]) -> int:
        """
        Execute a batch of Cypher queries in a single transaction.
        
        Args:
            queries: List of Cypher query strings.
        
        Returns:
            Number of queries successfully executed.
        """
        if not queries:
            return 0

        executed = 0
        with self._driver.session() as session:
            tx = session.begin_transaction()
            try:
                for query in queries:
                    q = (query or "").strip()
                    if not q:
                        continue
                    tx.run(q)
                    executed += 1
                tx.commit()
            except Exception:  # pragma: no cover - defensive
                tx.rollback()
                raise

        return executed
    
    def clear_graph(self) -> None:
        """Delete all nodes and relationships from the graph."""
        with self._driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        

    def get_entities_with_locations(
        self,
        entity_types: Optional[List[str]] = None,
        case_id: str = None,
    ) -> List[Dict]:
        """
        Get all entities that have geocoded locations.

        Args:
            entity_types: Optional filter for specific entity types
            case_id: REQUIRED - Filter to only include nodes belonging to this case

        Returns:
            List of entities with lat/lng coordinates
        """
        with self._driver.session() as session:
            type_filter = ""
            # case_id is always required
            params = {"case_id": case_id}

            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types

            # Always filter by case_id
            query = f"""
                MATCH (n)
                WHERE n.latitude IS NOT NULL
                  AND n.longitude IS NOT NULL
                  AND NOT n:Document
                  {type_filter}
                  AND n.case_id = $case_id
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE NOT connected:Document AND connected.case_id = $case_id
                WITH n, collect(DISTINCT {{
                    key: connected.key,
                    name: connected.name,
                    type: labels(connected)[0],
                    relationship: type(r),
                    direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                }}) AS connections
                RETURN
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.latitude AS latitude,
                    n.longitude AS longitude,
                    n.location_raw AS location_raw,
                    n.location_formatted AS location_formatted,
                    n.geocoding_confidence AS geocoding_confidence,
                    n.summary AS summary,
                    n.date AS date,
                    connections
            """

            result = session.run(query, **params)

            entities = []
            for record in result:
                entity = {
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "latitude": record["latitude"],
                    "longitude": record["longitude"],
                    "location_raw": record["location_raw"],
                    "location_formatted": record["location_formatted"],
                    "geocoding_confidence": record["geocoding_confidence"],
                    "summary": record["summary"],
                    "date": record["date"],
                    "connections": [c for c in record["connections"] if c["key"]],
                }
                entities.append(entity)

            return entities

    def get_timeline_events(
        self,
        event_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        case_id: str = None,
    ) -> List[Dict]:
        """
        Get all nodes that have dates, sorted chronologically.

        Args:
            event_types: Filter by specific types (e.g., ['Transaction', 'Payment']).
                        If None, returns ALL entities with dates (not just event types).
            start_date: Filter events on or after this date (YYYY-MM-DD)
            end_date: Filter events on or before this date (YYYY-MM-DD)
            case_id: REQUIRED - Filter to only include nodes belonging to this case

        Returns:
            List of nodes with their connected entities, sorted by date
        """
        with self._driver.session() as session:
            # Build date filter conditions
            date_conditions = []
            # case_id is always required
            params = {"case_id": case_id}

            if start_date:
                date_conditions.append("n.date >= $start_date")
                params["start_date"] = start_date
            if end_date:
                date_conditions.append("n.date <= $end_date")
                params["end_date"] = end_date

            date_filter = " AND " + " AND ".join(date_conditions) if date_conditions else ""

            # Build type filter condition
            type_filter = ""
            if event_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = event_types

            # Always filter by case_id
            query = f"""
                MATCH (n)
                WHERE n.date IS NOT NULL
                {type_filter}
                {date_filter}
                AND n.case_id = $case_id
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE NOT connected:Document AND NOT connected:Case AND connected.case_id = $case_id
                WITH n, collect(DISTINCT {{
                    key: connected.key,
                    name: connected.name,
                    type: labels(connected)[0],
                    relationship: type(r),
                    direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                }}) AS connections
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.date AS date,
                    n.time AS time,
                    n.amount AS amount,
                    n.summary AS summary,
                    n.notes AS notes,
                    connections
                ORDER BY n.date ASC, n.time ASC
            """

            result = session.run(query, **params)

            events = []
            for record in result:
                event = {
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "date": record["date"],
                    "time": record["time"],
                    "amount": record["amount"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "connections": [c for c in record["connections"] if c["key"]],
                }
                events.append(event)

            return events
            
    def get_shortest_paths_subgraph(self, node_keys: List[str], max_depth: int = 10, case_id: str = None) -> Dict[str, List]:
        """
        Find shortest paths between all pairs of selected nodes and return as subgraph.

        For multiple nodes, finds shortest paths between all pairs and combines them.

        Args:
            node_keys: List of node keys to find paths between
            max_depth: Maximum path length to search (default 10)
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with 'nodes' and 'links' arrays containing all nodes and relationships
            from the shortest paths connecting the selected nodes
        """
        if len(node_keys) < 2:
            return {"nodes": [], "links": []}

        with self._driver.session() as session:
            # Find shortest paths between all pairs
            all_nodes = set()
            all_links = []
            seen_links = set()

            # Generate all pairs
            for i in range(len(node_keys)):
                for j in range(i + 1, len(node_keys)):
                    key1, key2 = node_keys[i], node_keys[j]

                    # Find shortest path between this pair - filter by case_id
                    # Note: Neo4j doesn't support parameters in variable-length patterns,
                    # so we use string formatting for max_depth (validated as int)
                    result = session.run(
                        f"""
                        MATCH path = shortestPath((a {{key: $key1, case_id: $case_id}})-[*..{int(max_depth)}]-(b {{key: $key2, case_id: $case_id}}))
                        WHERE a.key = $key1 AND b.key = $key2
                        RETURN path
                        """,
                        key1=key1,
                        key2=key2,
                        case_id=case_id
                    )
                    
                    for record in result:
                        path = record["path"]
                        if path:
                            # Extract nodes from path
                            for node in path.nodes:
                                node_key = node.get("key")
                                if node_key:
                                    all_nodes.add(node_key)
                            
                            # Extract relationships from path
                            for rel in path.relationships:
                                source_key = rel.start_node.get("key")
                                target_key = rel.end_node.get("key")
                                rel_type = rel.type
                                
                                if source_key and target_key:
                                    link_key = f"{source_key}-{target_key}-{rel_type}"
                                    if link_key not in seen_links:
                                        seen_links.add(link_key)
                                        all_links.append({
                                            "source": source_key,
                                            "target": target_key,
                                            "type": rel_type,
                                            "properties": dict(rel)
                                        })
            
            # Get full node details for all nodes in paths - filter by case_id
            if not all_nodes:
                return {"nodes": [], "links": []}

            nodes_query = """
                MATCH (n)
                WHERE n.key IN $keys AND n.case_id = $case_id
                RETURN
                    id(n) AS neo4j_id,
                    n.id AS id,
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    properties(n) AS properties
            """

            nodes_result = session.run(nodes_query, keys=list(all_nodes), case_id=case_id)
            nodes = []
            for record in nodes_result:
                nodes.append({
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "properties": record["properties"] or {}
                })
            
            return {"nodes": nodes, "links": all_links}

    def get_pagerank_subgraph(
        self,
        node_keys: Optional[List[str]] = None,
        top_n: int = 20,
        iterations: int = 20,
        damping_factor: float = 0.85,
        case_id: str = None
    ) -> Dict:
        """
        Calculate PageRank for nodes and return top influential nodes as subgraph.

        Args:
            node_keys: Optional list of node keys to focus on (and their connections).
                      If None, runs on full graph filtered by case_id.
            top_n: Number of top influential nodes to return
            iterations: Number of PageRank iterations
            damping_factor: Damping factor (typically 0.85)
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with 'nodes' (sorted by PageRank score), 'links', and 'scores' (PageRank scores)
        """
        with self._driver.session() as session:
            # Step 1: Build the graph to analyze - always filter by case_id
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys AND n.case_id = $case_id
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes AND connected.case_id = $case_id
                    WITH collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
                    UNWIND allNodes AS node
                    RETURN DISTINCT node.key AS key
                """
                result = session.run(graph_query, node_keys=node_keys, case_id=case_id)
                focus_keys = [record["key"] for record in result if record["key"]]

                if not focus_keys:
                    return {"nodes": [], "links": [], "scores": {}}

                # Get all nodes and relationships in the focused subgraph
                nodes_query = """
                    MATCH (n)
                    WHERE n.key IN $keys AND n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
                links_query = """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $keys AND b.key IN $keys AND r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, keys=focus_keys, case_id=case_id)
                links_result = session.run(links_query, keys=focus_keys, case_id=case_id)
            else:
                # Use full graph filtered by case_id
                nodes_query = """
                    MATCH (n)
                    WHERE n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
                links_query = """
                    MATCH (a)-[r]->(b)
                    WHERE r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, case_id=case_id)
                links_result = session.run(links_query, case_id=case_id)
                focus_keys = None
            
            # Collect all nodes and links
            all_nodes = {}
            all_links = []
            
            for record in nodes_result:
                key = record["key"]
                if key:
                    all_nodes[key] = {
                        "id": record["id"],
                        "key": key,
                        "name": record["name"],
                        "type": record["type"],
                        "summary": record["summary"],
                        "notes": record["notes"],
                        "properties": record["properties"] or {}
                    }
            
            # Build adjacency list for PageRank calculation
            adjacency = {key: [] for key in all_nodes.keys()}
            out_degree = {key: 0 for key in all_nodes.keys()}
            
            for record in links_result:
                source = record["source"]
                target = record["target"]
                if source in all_nodes and target in all_nodes:
                    if target not in adjacency[source]:
                        adjacency[source].append(target)
                    out_degree[source] += 1
                    all_links.append({
                        "source": source,
                        "target": target,
                        "type": record["type"],
                        "properties": record["properties"] or {}
                    })
            
            # Step 2: Calculate PageRank
            N = len(all_nodes)
            if N == 0:
                return {"nodes": [], "links": [], "scores": {}}
            
            # Initialize PageRank scores
            pr = {key: 1.0 / N for key in all_nodes.keys()}
            
            # Iterate PageRank algorithm
            for _ in range(iterations):
                new_pr = {}
                for node in all_nodes.keys():
                    # Calculate contribution from incoming links
                    rank_sum = 0.0
                    for source in all_nodes.keys():
                        if node in adjacency[source]:
                            if out_degree[source] > 0:
                                rank_sum += pr[source] / out_degree[source]
                    
                    # PageRank formula
                    new_pr[node] = (1 - damping_factor) / N + damping_factor * rank_sum
                
                pr = new_pr
            
            # Step 3: Sort nodes by PageRank score and get top N
            sorted_nodes = sorted(pr.items(), key=lambda x: x[1], reverse=True)
            top_node_keys = [key for key, score in sorted_nodes[:top_n]]
            
            # Step 4: Build subgraph with top nodes and their connections
            top_nodes = [all_nodes[key] for key in top_node_keys if key in all_nodes]
            
            # Include links between top nodes
            top_links = [
                link for link in all_links
                if link["source"] in top_node_keys and link["target"] in top_node_keys
            ]
            
            # Add PageRank scores to nodes
            for node in top_nodes:
                node["pagerank_score"] = pr.get(node["key"], 0.0)
            
            # Sort nodes by PageRank score
            top_nodes.sort(key=lambda x: x.get("pagerank_score", 0.0), reverse=True)
            
            return {
                "nodes": top_nodes,
                "links": top_links,
                "scores": {key: pr[key] for key in top_node_keys if key in pr}
            }

    def _run_louvain(
        self,
        node_keys_list: List[str],
        adjacency: Dict[str, List[str]],
        degree: Dict[str, int],
        total_edges: int,
        resolution: float = 1.0,
        max_iterations: int = 10,
    ) -> Dict[str, int]:
        """
        Run Louvain community detection on pre-built adjacency data.

        Returns:
            Dict mapping node key -> community_id (renumbered sequentially from 0)
        """
        if not node_keys_list or total_edges == 0:
            return {key: 0 for key in node_keys_list}

        node_to_community = {key: i for i, key in enumerate(node_keys_list)}

        improved = True
        iteration = 0

        while improved and iteration < max_iterations:
            improved = False
            iteration += 1

            nodes_shuffled = list(node_keys_list)
            random.shuffle(nodes_shuffled)

            for node in nodes_shuffled:
                if node not in adjacency or len(adjacency[node]) == 0:
                    continue

                current_comm = node_to_community[node]
                best_comm = current_comm
                best_delta = 0.0

                neighbor_communities = set()
                for neighbor in adjacency[node]:
                    if neighbor in node_to_community:
                        neighbor_communities.add(node_to_community[neighbor])
                neighbor_communities.add(current_comm)

                for new_comm in neighbor_communities:
                    if new_comm == current_comm:
                        continue

                    k_i = degree.get(node, 0)
                    if total_edges == 0:
                        continue

                    edges_to_new_comm = sum(
                        1 for neighbor in adjacency[node]
                        if neighbor in node_to_community and node_to_community[neighbor] == new_comm
                    )
                    edges_to_current_comm = sum(
                        1 for neighbor in adjacency[node]
                        if neighbor in node_to_community and node_to_community[neighbor] == current_comm
                    )

                    delta = (edges_to_new_comm - edges_to_current_comm) / total_edges
                    delta -= resolution * k_i * (
                        sum(degree.get(n, 0) for n, c in node_to_community.items() if c == new_comm) -
                        sum(degree.get(n, 0) for n, c in node_to_community.items() if c == current_comm)
                    ) / (2.0 * total_edges * total_edges)

                    if delta > best_delta:
                        best_delta = delta
                        best_comm = new_comm

                if best_comm != current_comm and best_delta > 0:
                    node_to_community[node] = best_comm
                    improved = True

        # Renumber communities sequentially
        unique_communities = sorted(set(node_to_community.values()))
        community_map = {old: new for new, old in enumerate(unique_communities)}
        return {key: community_map[node_to_community[key]] for key in node_keys_list}

    def get_louvain_communities(
        self,
        node_keys: Optional[List[str]] = None,
        resolution: float = 1.0,
        max_iterations: int = 10,
        case_id: str = None
    ) -> Dict:
        """
        Detect communities using Louvain modularity algorithm.

        Args:
            node_keys: Optional list of node keys to focus on (and their connections).
                      If None, runs on full graph filtered by case_id.
            resolution: Resolution parameter for modularity (higher = more communities)
            max_iterations: Maximum number of iterations
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with 'nodes' (with community_id), 'links', and 'communities' (community info)
        """
        with self._driver.session() as session:
            # Step 1: Build the graph to analyze - always filter by case_id
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys AND n.case_id = $case_id
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes AND connected.case_id = $case_id
                    WITH collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
                    UNWIND allNodes AS node
                    RETURN DISTINCT node.key AS key
                """
                result = session.run(graph_query, node_keys=node_keys, case_id=case_id)
                focus_keys = [record["key"] for record in result if record["key"]]

                if not focus_keys:
                    return {"nodes": [], "links": [], "communities": {}}

                # Get all nodes and relationships in the focused subgraph
                nodes_query = """
                    MATCH (n)
                    WHERE n.key IN $keys AND n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
                links_query = """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $keys AND b.key IN $keys AND r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, keys=focus_keys, case_id=case_id)
                links_result = session.run(links_query, keys=focus_keys, case_id=case_id)
            else:
                # Use full graph filtered by case_id
                nodes_query = """
                    MATCH (n)
                    WHERE n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
                links_query = """
                    MATCH (a)-[r]->(b)
                    WHERE r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, case_id=case_id)
                links_result = session.run(links_query, case_id=case_id)
            
            # Collect all nodes and links
            all_nodes = {}
            all_links = []
            
            for record in nodes_result:
                key = record["key"]
                if key:
                    all_nodes[key] = {
                        "id": record["id"],
                        "key": key,
                        "name": record["name"],
                        "type": record["type"],
                        "summary": record["summary"],
                        "notes": record["notes"],
                        "properties": record["properties"] or {}
                    }
            
            # Build adjacency list and degree information
            adjacency = {key: [] for key in all_nodes.keys()}
            degree = {key: 0 for key in all_nodes.keys()}
            total_edges = 0
            
            for record in links_result:
                source = record["source"]
                target = record["target"]
                if source in all_nodes and target in all_nodes:
                    if target not in adjacency[source]:
                        adjacency[source].append(target)
                    if source not in adjacency[target]:
                        adjacency[target].append(source)
                    degree[source] += 1
                    degree[target] += 1
                    total_edges += 1
                    all_links.append({
                        "source": source,
                        "target": target,
                        "type": record["type"],
                        "properties": record["properties"] or {}
                    })
            
            if len(all_nodes) == 0:
                return {"nodes": [], "links": [], "communities": {}}

            # Step 2: Run Louvain via shared helper
            final_communities = self._run_louvain(
                list(all_nodes.keys()), adjacency, degree, total_edges,
                resolution=resolution, max_iterations=max_iterations,
            )
            
            # Add community_id to nodes
            result_nodes = []
            for key, node_data in all_nodes.items():
                node_data_copy = node_data.copy()
                node_data_copy["community_id"] = final_communities[key]
                result_nodes.append(node_data_copy)
            
            # Count nodes per community
            community_counts = {}
            for comm_id in final_communities.values():
                community_counts[comm_id] = community_counts.get(comm_id, 0) + 1
            
            # Sort nodes by community for better visualization
            result_nodes.sort(key=lambda x: (x["community_id"], x.get("name", "")))
            
            return {
                "nodes": result_nodes,
                "links": all_links,
                "communities": {
                    comm_id: {"id": comm_id, "size": count}
                    for comm_id, count in community_counts.items()
                }
            }

    def get_betweenness_centrality(
        self,
        node_keys: Optional[List[str]] = None,
        top_n: int = 20,
        normalized: bool = True,
        case_id: str = None
    ) -> Dict:
        """
        Calculate betweenness centrality for nodes.

        Betweenness centrality measures how often a node appears on the shortest path
        between other nodes. Nodes with high betweenness are important bridges.

        Args:
            node_keys: Optional list of node keys to focus on (and their connections).
                      If None, runs on full graph filtered by case_id.
            top_n: Number of top nodes by betweenness to return
            normalized: Whether to normalize scores (divide by (n-1)(n-2)/2 for undirected)
            case_id: REQUIRED - Filter to only include nodes/relationships belonging to this case

        Returns:
            Dict with 'nodes' (sorted by betweenness), 'links', and 'scores'
        """
        from collections import deque, defaultdict

        with self._driver.session() as session:
            # Step 1: Build the graph to analyze - always filter by case_id
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys AND n.case_id = $case_id
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes AND connected.case_id = $case_id
                    WITH collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
                    UNWIND allNodes AS node
                    RETURN DISTINCT node.key AS key
                """
                result = session.run(graph_query, node_keys=node_keys, case_id=case_id)
                focus_keys = [record["key"] for record in result if record["key"]]

                if not focus_keys:
                    return {"nodes": [], "links": [], "scores": {}}

                # Get all nodes and relationships in the focused subgraph
                nodes_query = """
                    MATCH (n)
                    WHERE n.key IN $keys AND n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
                links_query = """
                    MATCH (a)-[r]-(b)
                    WHERE a.key IN $keys AND b.key IN $keys AND r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, keys=focus_keys, case_id=case_id)
                links_result = session.run(links_query, keys=focus_keys, case_id=case_id)
            else:
                # Use full graph filtered by case_id
                nodes_query = """
                    MATCH (n)
                    WHERE n.case_id = $case_id
                    RETURN
                        id(n) AS neo4j_id,
                        n.id AS id,
                        n.key AS key,
                        n.name AS name,
                        labels(n)[0] AS type,
                        n.summary AS summary,
                        n.notes AS notes,
                        properties(n) AS properties
                """
                links_query = """
                    MATCH (a)-[r]-(b)
                    WHERE r.case_id = $case_id
                    RETURN
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, case_id=case_id)
                links_result = session.run(links_query, case_id=case_id)
            
            # Collect all nodes and links
            all_nodes = {}
            all_links = []
            
            for record in nodes_result:
                key = record["key"]
                if key:
                    all_nodes[key] = {
                        "id": record["id"],
                        "key": key,
                        "name": record["name"],
                        "type": record["type"],
                        "summary": record["summary"],
                        "notes": record["notes"],
                        "properties": record["properties"] or {}
                    }
            
            # Build adjacency list (undirected)
            adjacency = defaultdict(list)
            for record in links_result:
                source = record["source"]
                target = record["target"]
                if source in all_nodes and target in all_nodes:
                    if target not in adjacency[source]:
                        adjacency[source].append(target)
                    if source not in adjacency[target]:
                        adjacency[target].append(source)
                    all_links.append({
                        "source": source,
                        "target": target,
                        "type": record["type"],
                        "properties": record["properties"] or {}
                    })
            
            if len(all_nodes) == 0:
                return {"nodes": [], "links": [], "scores": {}}
            
            # Step 2: Calculate Betweenness Centrality using Brandes' algorithm
            # Initialize betweenness scores
            betweenness = {key: 0.0 for key in all_nodes.keys()}
            node_list = list(all_nodes.keys())
            
            # For each node, calculate its contribution to betweenness
            for s in node_list:
                # BFS to find shortest paths from s
                S = []  # Stack
                P = defaultdict(list)  # Predecessors
                sigma = defaultdict(int)  # Number of shortest paths
                sigma[s] = 1
                d = defaultdict(lambda: -1)  # Distances
                d[s] = 0
                Q = deque([s])  # Queue
                
                while Q:
                    v = Q.popleft()
                    S.append(v)
                    for w in adjacency[v]:
                        if d[w] < 0:  # w found for the first time
                            Q.append(w)
                            d[w] = d[v] + 1
                        if d[w] == d[v] + 1:  # Shortest path to w via v
                            sigma[w] += sigma[v]
                            P[w].append(v)
                
                # Accumulate betweenness
                delta = defaultdict(float)
                while S:
                    w = S.pop()
                    for v in P[w]:
                        delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
                    if w != s:
                        betweenness[w] += delta[w]
            
            # Normalize if requested
            if normalized and len(node_list) > 2:
                n = len(node_list)
                normalization = (n - 1) * (n - 2) / 2.0  # For undirected graph
                if normalization > 0:
                    betweenness = {k: v / normalization for k, v in betweenness.items()}
            
            # Step 3: Get top N nodes by betweenness
            sorted_nodes = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)
            top_node_keys = [key for key, score in sorted_nodes[:top_n]]
            
            # Build result with top nodes
            top_nodes = []
            for key in top_node_keys:
                node_data = all_nodes[key].copy()
                node_data["betweenness_centrality"] = betweenness[key]
                top_nodes.append(node_data)
            
            # Include links between top nodes
            top_links = [
                link for link in all_links
                if link["source"] in top_node_keys and link["target"] in top_node_keys
            ]
            
            # Sort nodes by betweenness score
            top_nodes.sort(key=lambda x: x.get("betweenness_centrality", 0.0), reverse=True)
            
            return {
                "nodes": top_nodes,
                "links": top_links,
                "scores": {key: betweenness[key] for key in top_node_keys if key in betweenness}
            }

    # -------------------------------------------------------------------------
    # Fact and Insight Management
    # -------------------------------------------------------------------------

    def pin_fact(self, node_key: str, fact_index: int, pinned: bool, case_id: str = None) -> Dict:
        """
        Toggle the pinned status of a verified fact.

        Args:
            node_key: The node's key
            fact_index: Index of the fact in the verified_facts array
            pinned: True to pin, False to unpin
            case_id: REQUIRED - Verify node belongs to this case

        Returns:
            Updated verified_facts array
        """
        with self._driver.session() as session:
            # Get current verified_facts - verify node belongs to case
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN n.verified_facts AS verified_facts
                """,
                key=node_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")

            verified_facts = parse_json_field(record["verified_facts"]) or []

            if fact_index < 0 or fact_index >= len(verified_facts):
                raise ValueError(f"Invalid fact index: {fact_index}")

            # Update the pinned status
            verified_facts[fact_index]["pinned"] = pinned

            # Save back to Neo4j
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.verified_facts = $verified_facts
                """,
                key=node_key,
                case_id=case_id,
                verified_facts=json.dumps(verified_facts),
            )

            return verified_facts

    def verify_insight(
        self,
        node_key: str,
        insight_index: int,
        username: str,
        source_doc: Optional[str] = None,
        page: Optional[int] = None,
        case_id: str = None
    ) -> Dict:
        """
        Convert an AI insight to a verified fact with user attribution.

        Args:
            node_key: The node's key
            insight_index: Index of the insight in the ai_insights array
            username: Username of the verifying investigator
            source_doc: Optional source document for the verification
            page: Optional page number in the source document
            case_id: REQUIRED - Verify node belongs to this case

        Returns:
            Dict with updated verified_facts and ai_insights arrays
        """
        from datetime import datetime

        with self._driver.session() as session:
            # Get current facts and insights - verify node belongs to case
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN n.verified_facts AS verified_facts, n.ai_insights AS ai_insights
                """,
                key=node_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")

            verified_facts = parse_json_field(record["verified_facts"]) or []
            ai_insights = parse_json_field(record["ai_insights"]) or []

            if insight_index < 0 or insight_index >= len(ai_insights):
                raise ValueError(f"Invalid insight index: {insight_index}")

            # Get the insight to convert
            insight = ai_insights[insight_index]

            # Create a new verified fact from the insight
            new_fact = {
                "text": insight.get("text", ""),
                "quote": None,  # No direct quote since it was an inference
                "page": page,
                "source_doc": source_doc,
                "importance": 3,  # Default to medium importance for user-verified insights
                "pinned": False,
                "verified_by": username,
                "verified_at": datetime.utcnow().isoformat(),
                "original_confidence": insight.get("confidence"),
                "original_reasoning": insight.get("reasoning"),
            }

            # Add to verified facts
            verified_facts.append(new_fact)

            # Remove from ai_insights
            ai_insights.pop(insight_index)

            # Save back to Neo4j - verify node belongs to case
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.verified_facts = $verified_facts, n.ai_insights = $ai_insights
                """,
                key=node_key,
                case_id=case_id,
                verified_facts=json.dumps(verified_facts),
                ai_insights=json.dumps(ai_insights),
            )

            return {
                "verified_facts": verified_facts,
                "ai_insights": ai_insights,
            }

    def find_similar_entities(
        self,
        case_id: str,
        entity_types: Optional[List[str]] = None,
        name_similarity_threshold: float = 0.88,
        max_results: int = 50,
    ) -> List[Dict]:
        """
        Find entities that might be duplicates based on name similarity and type.

        Args:
            case_id: The case ID to filter by
            entity_types: Optional list of entity types to filter by
            name_similarity_threshold: Minimum similarity score (0-1) for name matching
            max_results: Maximum number of pairs to return

        Returns:
            List of dicts with 'entity1' and 'entity2' entries, each containing node info
        """
        from difflib import SequenceMatcher

        with self._driver.session() as session:
            # Build type filter
            type_filter = ""
            params = {"case_id": case_id}
            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types

            # Get all entities (excluding Documents) for this case
            query = f"""
                MATCH (n)
                WHERE n.key IS NOT NULL
                  AND n.name IS NOT NULL
                  AND NOT n:Document
                  AND n.case_id = $case_id
                  {type_filter}
                RETURN
                    n.key AS key,
                    n.id AS id,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    n.verified_facts AS verified_facts,
                    n.ai_insights AS ai_insights,
                    properties(n) AS properties
                ORDER BY n.name
            """

            result = session.run(query, **params)
            entities = [dict(record) for record in result]

            # Compare entities pairwise
            similar_pairs = []
            for i, e1 in enumerate(entities):
                for e2 in entities[i+1:]:
                    # Same type required
                    if e1["type"] != e2["type"]:
                        continue

                    # Calculate name similarity
                    name1 = (e1["name"] or "").lower().strip()
                    name2 = (e2["name"] or "").lower().strip()

                    if not name1 or not name2:
                        continue

                    similarity = SequenceMatcher(None, name1, name2).ratio()

                    if similarity >= name_similarity_threshold:
                        similar_pairs.append({
                            "entity1": {
                                "key": e1["key"],
                                "id": e1["id"],
                                "name": e1["name"],
                                "type": e1["type"],
                                "summary": e1["summary"],
                                "notes": e1["notes"],
                                "verified_facts": parse_json_field(e1.get("verified_facts")),
                                "ai_insights": parse_json_field(e1.get("ai_insights")),
                                "properties": e1["properties"] or {},
                            },
                            "entity2": {
                                "key": e2["key"],
                                "id": e2["id"],
                                "name": e2["name"],
                                "type": e2["type"],
                                "summary": e2["summary"],
                                "notes": e2["notes"],
                                "verified_facts": parse_json_field(e2.get("verified_facts")),
                                "ai_insights": parse_json_field(e2.get("ai_insights")),
                                "properties": e2["properties"] or {},
                            },
                            "similarity": similarity,
                        })
            
            # Sort by similarity (highest first) and limit results
            similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)
            return similar_pairs[:max_results]

    async def find_similar_entities_streaming(
        self,
        case_id: str,
        entity_types: Optional[List[str]] = None,
        name_similarity_threshold: float = 0.88,
        max_results: int = 1000,
        rejected_pairs: Optional[Set[Tuple[str, str]]] = None,
    ):
        """
        Async generator that yields similar entity pairs with progress updates.

        Yields SSE events for streaming progress to the client.

        Args:
            case_id: The case ID to filter by
            entity_types: Optional list of entity types to filter by
            name_similarity_threshold: Minimum similarity score (0-1) for name matching
            max_results: Maximum number of pairs to return
            rejected_pairs: Set of (key1, key2) tuples to skip (already normalized/sorted)

        Yields:
            dict: SSE event data with 'event' type and 'data' payload
        """
        import asyncio
        from difflib import SequenceMatcher
        from collections import defaultdict

        # Initialize rejected_pairs to empty set if None
        if rejected_pairs is None:
            rejected_pairs = set()

        # Fetch data and close session immediately - we don't need the session
        # held open during comparison loop, which can cause hanging issues
        with self._driver.session() as session:
            # Build type filter
            type_filter = ""
            params = {"case_id": case_id}
            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types

            # Get all entities (excluding Documents) for this case
            query = f"""
                MATCH (n)
                WHERE n.key IS NOT NULL
                  AND n.name IS NOT NULL
                  AND NOT n:Document
                  AND n.case_id = $case_id
                  {type_filter}
                RETURN
                    n.key AS key,
                    n.id AS id,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    n.verified_facts AS verified_facts,
                    n.ai_insights AS ai_insights,
                    properties(n) AS properties
                ORDER BY labels(n)[0], n.name
            """

            result = session.run(query, **params)
            all_entities = [dict(record) for record in result]
        # Session is now closed - all data fetched

        # Group entities by type (backend already only compares same-type entities)
        entities_by_type = defaultdict(list)
        for entity in all_entities:
            entities_by_type[entity["type"]].append(entity)

        entity_types_list = sorted(entities_by_type.keys())

        # Calculate total comparisons needed (for progress)
        total_comparisons = 0
        for entities in entities_by_type.values():
            n = len(entities)
            # n*(n-1)/2 pairs for same-type comparison
            total_comparisons += n * (n - 1) // 2

        # Yield start event
        yield {
            "event": "start",
            "data": {
                "total_entities": len(all_entities),
                "entity_types": entity_types_list,
                "total_types": len(entity_types_list),
                "total_comparisons": total_comparisons,
            }
        }
        await asyncio.sleep(0)  # Yield control for cancellation check

        similar_pairs = []
        comparisons_done = 0
        pairs_found = 0
        last_progress_update = 0

        for type_index, type_name in enumerate(entity_types_list):
            entities = entities_by_type[type_name]
            n = len(entities)
            type_comparisons = n * (n - 1) // 2

            # Yield type_start event
            yield {
                "event": "type_start",
                "data": {
                    "type_name": type_name,
                    "type_count": len(entities),
                    "type_index": type_index,
                    "total_types": len(entity_types_list),
                    "total_comparisons": type_comparisons,
                }
            }
            await asyncio.sleep(0)

            type_pairs_found = 0

            # Compare entities within this type
            for i, e1 in enumerate(entities):
                for e2 in entities[i+1:]:
                    comparisons_done += 1

                    # Calculate name similarity
                    name1 = (e1["name"] or "").lower().strip()
                    name2 = (e2["name"] or "").lower().strip()

                    if not name1 or not name2:
                        continue

                    # Skip rejected pairs (normalize keys for lookup)
                    key1, key2 = e1["key"], e2["key"]
                    normalized_pair = (key1, key2) if key1 <= key2 else (key2, key1)
                    if normalized_pair in rejected_pairs:
                        continue

                    similarity = SequenceMatcher(None, name1, name2).ratio()

                    if similarity >= name_similarity_threshold:
                        pair = {
                            "entity1": {
                                "key": e1["key"],
                                "id": e1["id"],
                                "name": e1["name"],
                                "type": e1["type"],
                                "summary": e1["summary"],
                                "notes": e1["notes"],
                                "verified_facts": parse_json_field(e1.get("verified_facts")),
                                "ai_insights": parse_json_field(e1.get("ai_insights")),
                                "properties": e1["properties"] or {},
                            },
                            "entity2": {
                                "key": e2["key"],
                                "id": e2["id"],
                                "name": e2["name"],
                                "type": e2["type"],
                                "summary": e2["summary"],
                                "notes": e2["notes"],
                                "verified_facts": parse_json_field(e2.get("verified_facts")),
                                "ai_insights": parse_json_field(e2.get("ai_insights")),
                                "properties": e2["properties"] or {},
                            },
                            "similarity": similarity,
                        }
                        similar_pairs.append(pair)
                        pairs_found += 1
                        type_pairs_found += 1

                        # NOTE: Removed individual "result" event emission to prevent
                        # UI freezing with large numbers of pairs (93k+ causes 93k React updates).
                        # Results are now only sent in the "complete" event at the end.

                    # Emit progress every ~100 comparisons
                    if comparisons_done - last_progress_update >= 100:
                        yield {
                            "event": "progress",
                            "data": {
                                "comparisons_done": comparisons_done,
                                "total_comparisons": total_comparisons,
                                "pairs_found": pairs_found,
                                "current_type": type_name,
                                "type_index": type_index,
                            }
                        }
                        last_progress_update = comparisons_done
                        await asyncio.sleep(0)  # Yield control for cancellation check

            # Yield type_complete event
            yield {
                "event": "type_complete",
                "data": {
                    "type_name": type_name,
                    "pairs_found": type_pairs_found,
                    "type_index": type_index,
                }
            }
            await asyncio.sleep(0)

        # Emit final progress update if not already at 100%
        # This ensures the UI shows 100% before the complete event
        if comparisons_done != last_progress_update:
            yield {
                "event": "progress",
                "data": {
                    "comparisons_done": comparisons_done,
                    "total_comparisons": total_comparisons,
                    "pairs_found": pairs_found,
                    "current_type": "Finalizing...",
                    "type_index": len(entity_types_list) - 1,
                }
            }
            await asyncio.sleep(0)

        # Sort final results by similarity
        similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)

        # Yield complete event
        yield {
            "event": "complete",
            "data": {
                "total_pairs": len(similar_pairs),
                "total_comparisons": comparisons_done,
                "limited_results": similar_pairs[:max_results] if len(similar_pairs) > max_results else similar_pairs,
            }
        }
        await asyncio.sleep(0)  # Ensure event is flushed before generator ends

    def merge_entities(
        self,
        source_key: str,
        target_key: str,
        merged_data: Dict[str, Any],
        case_id: str = None,
    ) -> Dict[str, Any]:
        """
        Merge two entities into one.

        Args:
            source_key: Key of the source entity (will be deleted)
            target_key: Key of the target entity (will be kept and updated)
            merged_data: Dict with merged properties:
                - name: Merged name
                - summary: Merged summary (can be None to keep existing)
                - notes: Merged notes (can be None to keep existing)
                - type: Merged type (label)
                - properties: Dict of additional properties to set
            case_id: REQUIRED - Verify both entities belong to this case

        Returns:
            Dict with result info including merged_node and relationships_updated count
        """
        import re

        # Validate merged_data
        if merged_data is None:
            raise ValueError("merged_data cannot be None")
        if not isinstance(merged_data, dict):
            raise ValueError(f"merged_data must be a dict, got {type(merged_data)}")

        with self._driver.session() as session:
            # Get both entities - verify they belong to the case
            source_result = session.run(
                """
                MATCH (s {key: $key, case_id: $case_id})
                RETURN
                    id(s) AS neo4j_id,
                    s.id AS id,
                    s.key AS key,
                    s.name AS name,
                    labels(s)[0] AS type,
                    s.summary AS summary,
                    s.notes AS notes,
                    properties(s) AS properties
                """,
                key=source_key,
                case_id=case_id,
            )
            source_record = source_result.single()
            if not source_record:
                raise ValueError(f"Source entity not found: {source_key} in case {case_id}")

            target_result = session.run(
                """
                MATCH (t {key: $key, case_id: $case_id})
                RETURN
                    id(t) AS neo4j_id,
                    t.id AS id,
                    t.key AS key,
                    t.name AS name,
                    labels(t)[0] AS type,
                    t.summary AS summary,
                    t.notes AS notes,
                    properties(t) AS properties
                """,
                key=target_key,
                case_id=case_id,
            )
            target_record = target_result.single()
            if not target_record:
                raise ValueError(f"Target entity not found: {target_key} in case {case_id}")
            
            # Get all relationships from source
            source_rels_result = session.run(
                """
                MATCH (s {key: $key})-[r]->(target)
                RETURN 
                    type(r) AS rel_type,
                    target.key AS other_key,
                    properties(r) AS rel_properties,
                    'outgoing' AS direction
                UNION
                MATCH (source)-[r]->(s {key: $key})
                RETURN 
                    type(r) AS rel_type,
                    source.key AS other_key,
                    properties(r) AS rel_properties,
                    'incoming' AS direction
                """,
                key=source_key,
            )
            source_rels = [dict(record) for record in source_rels_result]
            
            # Update target entity with merged data
            # Build SET clause for properties
            set_clauses = []
            params = {"target_key": target_key}
            
            if "name" in merged_data:
                set_clauses.append("t.name = $merged_name")
                params["merged_name"] = merged_data["name"]
            
            if "summary" in merged_data and merged_data["summary"] is not None:
                set_clauses.append("t.summary = $merged_summary")
                params["merged_summary"] = merged_data["summary"]
            
            if "verified_facts" in merged_data and merged_data["verified_facts"] is not None:
                set_clauses.append("t.verified_facts = $merged_verified_facts")
                params["merged_verified_facts"] = json.dumps(merged_data["verified_facts"])

            if "ai_insights" in merged_data and merged_data["ai_insights"] is not None:
                set_clauses.append("t.ai_insights = $merged_ai_insights")
                params["merged_ai_insights"] = json.dumps(merged_data["ai_insights"])
            
            # Handle type (label) change if needed
            new_type = merged_data.get("type")
            if new_type and isinstance(new_type, str) and new_type.strip():
                # Remove old label and add new one
                old_type = target_record["type"]
                if old_type != new_type:
                    # Sanitize type for Cypher label
                    sanitized_new_type = re.sub(r'[^a-zA-Z0-9_]', '_', new_type.strip())
                    sanitized_new_type = re.sub(r'_+', '_', sanitized_new_type).strip('_')
                    if not sanitized_new_type:
                        sanitized_new_type = "Other"
                    
                    session.run(
                        f"""
                        MATCH (t {{key: $target_key}})
                        REMOVE t:`{old_type}`
                        SET t:`{sanitized_new_type}`
                        """,
                        target_key=target_key,
                    )
            
            # Add additional properties
            if "properties" in merged_data and merged_data["properties"] is not None:
                properties = merged_data["properties"]
                if isinstance(properties, dict):
                    for prop_key, prop_val in properties.items():
                        param_name = f"prop_{prop_key}"
                        set_clauses.append(f"t.{prop_key} = ${param_name}")
                        params[param_name] = prop_val
            
            # Update target entity
            if set_clauses:
                set_clause = ", ".join(set_clauses)
                session.run(
                    f"""
                    MATCH (t {{key: $target_key}})
                    SET {set_clause}
                    """,
                    **params,
                )
            
            # Migrate relationships from source to target
            relationships_updated = 0
            for rel in source_rels:
                rel_type = rel["rel_type"]
                rel_props = rel["rel_properties"] or {}
                direction = rel["direction"]
                other_key = rel["other_key"]  # Use the unified column name from UNION
                
                # Don't create self-loops
                if other_key == target_key:
                    continue
                
                if direction == "outgoing":
                    # Create relationship from target to other
                    if rel_props:
                        session.run(
                            f"""
                            MATCH (t {{key: $target_key}}), (o {{key: $other_key}})
                            MERGE (t)-[r:`{rel_type}`]->(o)
                            SET r += $rel_props
                            """,
                            target_key=target_key,
                            other_key=other_key,
                            rel_props=rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (t {{key: $target_key}}), (o {{key: $other_key}})
                            MERGE (t)-[r:`{rel_type}`]->(o)
                            """,
                            target_key=target_key,
                            other_key=other_key,
                        )
                    relationships_updated += 1
                else:  # incoming
                    # Create relationship from other to target
                    if rel_props:
                        session.run(
                            f"""
                            MATCH (o {{key: $other_key}}), (t {{key: $target_key}})
                            MERGE (o)-[r:`{rel_type}`]->(t)
                            SET r += $rel_props
                            """,
                            target_key=target_key,
                            other_key=other_key,
                            rel_props=rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (o {{key: $other_key}}), (t {{key: $target_key}})
                            MERGE (o)-[r:`{rel_type}`]->(t)
                            """,
                            target_key=target_key,
                            other_key=other_key,
                        )
                    relationships_updated += 1
            
            # Update transaction nodes that reference source entity in from/to properties
            merged_name = merged_data.get("name") or target_record["name"]
            session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE n.from_entity_key = $source_key
                SET n.from_entity_key = $target_key, n.from_entity_name = $merged_name
                """,
                case_id=case_id, source_key=source_key,
                target_key=target_key, merged_name=merged_name,
            )
            session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE n.to_entity_key = $source_key
                SET n.to_entity_key = $target_key, n.to_entity_name = $merged_name
                """,
                case_id=case_id, source_key=source_key,
                target_key=target_key, merged_name=merged_name,
            )
            # Also match by source name for transactions set by name rather than key
            source_name = source_record["name"]
            if source_name:
                session.run(
                    """
                    MATCH (n {case_id: $case_id})
                    WHERE n.from_entity_name = $source_name AND (n.from_entity_key IS NULL OR n.from_entity_key = $source_key)
                    SET n.from_entity_key = $target_key, n.from_entity_name = $merged_name
                    """,
                    case_id=case_id, source_key=source_key, source_name=source_name,
                    target_key=target_key, merged_name=merged_name,
                )
                session.run(
                    """
                    MATCH (n {case_id: $case_id})
                    WHERE n.to_entity_name = $source_name AND (n.to_entity_key IS NULL OR n.to_entity_key = $source_key)
                    SET n.to_entity_key = $target_key, n.to_entity_name = $merged_name
                    """,
                    case_id=case_id, source_key=source_key, source_name=source_name,
                    target_key=target_key, merged_name=merged_name,
                )

            # Soft-delete source entity to recycling bin (so it can be recovered)
            try:
                self.soft_delete_entity(
                    node_key=source_key,
                    case_id=case_id,
                    deleted_by="system",
                    reason=f"merge_into:{target_key}",
                )
            except Exception:
                # Fallback: hard-delete if soft-delete fails (e.g., entity already gone)
                session.run(
                    """
                    MATCH (s {key: $key})
                    DETACH DELETE s
                    """,
                    key=source_key,
                )

            # Get the merged node (target node after merge) for return value
            merged_node_result = session.run(
                """
                MATCH (t {key: $key})
                RETURN 
                    t.id AS id,
                    t.key AS key,
                    t.name AS name,
                    labels(t)[0] AS type
                """,
                key=target_key,
            )
            merged_node_record = merged_node_result.single()
            merged_node = dict(merged_node_record) if merged_node_record else None
            
            # Return result
            return {
                "merged_node": merged_node,
                "relationships_updated": relationships_updated,
            }
            
    def bulk_merge_entities(
        self,
        target_key: str,
        source_keys: list,
        merged_data: Dict[str, Any],
        case_id: str = None,
    ) -> Dict[str, Any]:
        """
        Merge multiple source entities into a single target entity in one operation.

        Args:
            target_key: Key of the target entity (will be kept and updated)
            source_keys: List of source entity keys (will be soft-deleted)
            merged_data: Dict with merged properties (name, summary, verified_facts, ai_insights, type, properties)
            case_id: REQUIRED - Verify all entities belong to this case

        Returns:
            Dict with merged_node, relationships_updated, entities_merged
        """
        import re

        if merged_data is None:
            raise ValueError("merged_data cannot be None")
        if not isinstance(merged_data, dict):
            raise ValueError(f"merged_data must be a dict, got {type(merged_data)}")
        if not source_keys:
            raise ValueError("source_keys cannot be empty")

        with self._driver.session() as session:
            # Validate target exists
            target_result = session.run(
                """
                MATCH (t {key: $key, case_id: $case_id})
                RETURN t.id AS id, t.key AS key, t.name AS name, labels(t)[0] AS type
                """,
                key=target_key, case_id=case_id,
            )
            target_record = target_result.single()
            if not target_record:
                raise ValueError(f"Target entity not found: {target_key} in case {case_id}")

            # Validate all sources exist
            for sk in source_keys:
                sr = session.run(
                    "MATCH (s {key: $key, case_id: $case_id}) RETURN s.key AS key",
                    key=sk, case_id=case_id,
                ).single()
                if not sr:
                    raise ValueError(f"Source entity not found: {sk} in case {case_id}")

            # Update target entity with merged data
            set_clauses = []
            params = {"target_key": target_key}

            if "name" in merged_data:
                set_clauses.append("t.name = $merged_name")
                params["merged_name"] = merged_data["name"]
            if "summary" in merged_data and merged_data["summary"] is not None:
                set_clauses.append("t.summary = $merged_summary")
                params["merged_summary"] = merged_data["summary"]
            if "verified_facts" in merged_data and merged_data["verified_facts"] is not None:
                set_clauses.append("t.verified_facts = $merged_verified_facts")
                params["merged_verified_facts"] = json.dumps(merged_data["verified_facts"])
            if "ai_insights" in merged_data and merged_data["ai_insights"] is not None:
                set_clauses.append("t.ai_insights = $merged_ai_insights")
                params["merged_ai_insights"] = json.dumps(merged_data["ai_insights"])

            # Handle type (label) change
            new_type = merged_data.get("type")
            old_type = target_record["type"]
            if new_type and isinstance(new_type, str) and new_type.strip() and old_type != new_type:
                sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', new_type.strip())
                sanitized = re.sub(r'_+', '_', sanitized).strip('_') or "Other"
                session.run(
                    f"MATCH (t {{key: $target_key}}) REMOVE t:`{old_type}` SET t:`{sanitized}`",
                    target_key=target_key,
                )

            # Add additional properties
            if "properties" in merged_data and isinstance(merged_data.get("properties"), dict):
                for prop_key, prop_val in merged_data["properties"].items():
                    param_name = f"prop_{prop_key}"
                    set_clauses.append(f"t.{prop_key} = ${param_name}")
                    params[param_name] = prop_val

            if set_clauses:
                session.run(
                    f"MATCH (t {{key: $target_key}}) SET {', '.join(set_clauses)}",
                    **params,
                )

            # Migrate relationships from all sources to target and soft-delete each
            total_relationships = 0
            all_source_keys_set = set(source_keys)

            for source_key in source_keys:
                # Get all relationships from this source
                rels_result = session.run(
                    """
                    MATCH (s {key: $key})-[r]->(target)
                    RETURN type(r) AS rel_type, target.key AS other_key,
                           properties(r) AS rel_properties, 'outgoing' AS direction
                    UNION
                    MATCH (source)-[r]->(s {key: $key})
                    RETURN type(r) AS rel_type, source.key AS other_key,
                           properties(r) AS rel_properties, 'incoming' AS direction
                    """,
                    key=source_key,
                )
                rels = [dict(r) for r in rels_result]

                for rel in rels:
                    other_key = rel["other_key"]
                    # Skip self-loops to target AND relationships to other sources (they'll be deleted too)
                    if other_key == target_key or other_key in all_source_keys_set:
                        continue

                    rel_type = rel["rel_type"]
                    rel_props = rel["rel_properties"] or {}
                    direction = rel["direction"]

                    if direction == "outgoing":
                        cypher = f"MATCH (t {{key: $target_key}}), (o {{key: $other_key}}) MERGE (t)-[r:`{rel_type}`]->(o)"
                    else:
                        cypher = f"MATCH (o {{key: $other_key}}), (t {{key: $target_key}}) MERGE (o)-[r:`{rel_type}`]->(t)"

                    if rel_props:
                        cypher += " SET r += $rel_props"
                        session.run(cypher, target_key=target_key, other_key=other_key, rel_props=rel_props)
                    else:
                        session.run(cypher, target_key=target_key, other_key=other_key)
                    total_relationships += 1

                # Update transaction nodes that reference this source entity in from/to properties
                merged_name = merged_data.get("name") or target_record["name"]
                # Get source name for name-based matching
                src_name_result = session.run(
                    "MATCH (s {key: $key, case_id: $case_id}) RETURN s.name AS name",
                    key=source_key, case_id=case_id,
                )
                src_name_rec = src_name_result.single()
                src_name = src_name_rec["name"] if src_name_rec else None

                session.run(
                    """
                    MATCH (n {case_id: $case_id})
                    WHERE n.from_entity_key = $source_key
                    SET n.from_entity_key = $target_key, n.from_entity_name = $merged_name
                    """,
                    case_id=case_id, source_key=source_key,
                    target_key=target_key, merged_name=merged_name,
                )
                session.run(
                    """
                    MATCH (n {case_id: $case_id})
                    WHERE n.to_entity_key = $source_key
                    SET n.to_entity_key = $target_key, n.to_entity_name = $merged_name
                    """,
                    case_id=case_id, source_key=source_key,
                    target_key=target_key, merged_name=merged_name,
                )
                if src_name:
                    session.run(
                        """
                        MATCH (n {case_id: $case_id})
                        WHERE n.from_entity_name = $source_name AND (n.from_entity_key IS NULL OR n.from_entity_key = $source_key)
                        SET n.from_entity_key = $target_key, n.from_entity_name = $merged_name
                        """,
                        case_id=case_id, source_key=source_key, source_name=src_name,
                        target_key=target_key, merged_name=merged_name,
                    )
                    session.run(
                        """
                        MATCH (n {case_id: $case_id})
                        WHERE n.to_entity_name = $source_name AND (n.to_entity_key IS NULL OR n.to_entity_key = $source_key)
                        SET n.to_entity_key = $target_key, n.to_entity_name = $merged_name
                        """,
                        case_id=case_id, source_key=source_key, source_name=src_name,
                        target_key=target_key, merged_name=merged_name,
                    )

                # Soft-delete the source
                try:
                    self.soft_delete_entity(
                        node_key=source_key, case_id=case_id,
                        deleted_by="system", reason=f"bulk_merge_into:{target_key}",
                    )
                except Exception:
                    session.run("MATCH (s {key: $key}) DETACH DELETE s", key=source_key)

            # Get final merged node
            merged_result = session.run(
                "MATCH (t {key: $key}) RETURN t.id AS id, t.key AS key, t.name AS name, labels(t)[0] AS type",
                key=target_key,
            )
            merged_record = merged_result.single()

            return {
                "merged_node": dict(merged_record) if merged_record else None,
                "relationships_updated": total_relationships,
                "entities_merged": len(source_keys),
            }

    def delete_node(self, node_key: str, case_id: str = None) -> Dict[str, Any]:
        """
        Delete a node and all its relationships.

        Args:
            node_key: Key of the node to delete
            case_id: REQUIRED - Verify node belongs to this case

        Returns:
            Dict with success status and deleted node info
        """
        with self._driver.session() as session:
            # First get node info before deletion for return value - verify node belongs to case
            node_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    id(n) AS neo4j_id
                """,
                key=node_key,
                case_id=case_id,
            )
            node_record = node_result.single()

            if not node_record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")

            # Count relationships before deletion
            rel_count_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})-[r]-()
                RETURN count(r) AS count
                """,
                key=node_key,
                case_id=case_id,
            )
            rel_count = rel_count_result.single()["count"]

            # Delete the node and all its relationships - verify node belongs to case
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                DETACH DELETE n
                """,
                key=node_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "deleted_node": {
                    "key": node_record["key"],
                    "name": node_record["name"],
                    "type": node_record["type"],
                },
                "relationships_deleted": rel_count,
            }
            
            # Get the merged entity (continuation of merge_entities method)
            merged_result = session.run(
                """
                MATCH (t {key: $key})
                RETURN 
                    id(t) AS neo4j_id,
                    t.id AS id,
                    t.key AS key,
                    t.name AS name,
                    labels(t)[0] AS type,
                    t.summary AS summary,
                    t.notes AS notes,
                    properties(t) AS properties
                """,
                key=target_key,
            )
            merged_record = merged_result.single()
            
            return {
                "merged_node": {
                    "key": merged_record["key"],
                    "id": merged_record["id"],
                    "name": merged_record["name"],
                    "type": merged_record["type"],
                    "summary": merged_record["summary"],
                    "notes": merged_record["notes"],
                    "properties": merged_record["properties"] or {},
                },
                "relationships_updated": relationships_updated,
                "source_deleted": True,
            }

    # -------------------------------------------------------------------------
    # Document Summaries
    # -------------------------------------------------------------------------

    def get_document_summary(self, doc_name: str, case_id: str) -> Optional[str]:
        """
        Get the summary for a document by its name.
        
        Args:
            doc_name: Document filename/name
            case_id: Case ID to filter by
            
        Returns:
            Document summary if found, None otherwise
        """
        # Normalise the document name to match the key format used during ingestion
        # This matches the normalise_key function from ingestion/scripts/entity_resolution.py
        import re
        doc_key = doc_name.strip().lower()
        doc_key = re.sub(r"[\s_]+", "-", doc_key)
        doc_key = re.sub(r"[^a-z0-9\-]", "", doc_key)
        doc_key = re.sub(r"-+", "-", doc_key)
        doc_key = doc_key.strip("-")
        
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {key: $doc_key, case_id: $case_id})
                RETURN d.summary AS summary
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            record = result.single()
            if record and record["summary"]:
                return record["summary"]
            return None

    def get_document_summaries_batch(self, doc_names: List[str], case_id: str) -> Dict[str, Optional[str]]:
        """
        Get summaries for multiple documents by their names.
        
        Args:
            doc_names: List of document filenames/names
            case_id: Case ID to filter by
            
        Returns:
            Dict mapping doc_name -> summary (None if not found)
        """
        # Normalise all document names
        import re
        summaries = {}
        
        # Build normalized keys map
        doc_key_map = {}  # doc_key -> doc_name
        for doc_name in doc_names:
            doc_key = doc_name.strip().lower()
            doc_key = re.sub(r"[\s_]+", "-", doc_key)
            doc_key = re.sub(r"[^a-z0-9\-]", "", doc_key)
            doc_key = re.sub(r"-+", "-", doc_key)
            doc_key = doc_key.strip("-")
            doc_key_map[doc_key] = doc_name
        
        if not doc_key_map:
            return summaries
        
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document)
                WHERE d.key IN $doc_keys AND d.case_id = $case_id
                RETURN d.key AS key, d.summary AS summary
                """,
                doc_keys=list(doc_key_map.keys()),
                case_id=case_id,
            )
            
            for record in result:
                doc_key = record["key"]
                summary = record["summary"]
                doc_name = doc_key_map.get(doc_key)
                if doc_name:
                    summaries[doc_name] = summary if summary else None
        
        # Fill in None for docs that weren't found
        for doc_name in doc_names:
            if doc_name not in summaries:
                summaries[doc_name] = None
        
        return summaries

    def get_folder_summary(self, folder_name: str, case_id: str) -> Optional[str]:
        """
        Get the summary for a folder by its folder name.
        
        This looks for documents that were created from folder processing,
        identified by having 'folder_name' in their metadata.
        
        Args:
            folder_name: Name of the folder (e.g., "00000128")
            case_id: Case ID to filter by
            
        Returns:
            Folder summary if found, None otherwise
        """
        with self._driver.session() as session:
            # Look for documents with folder_name in metadata
            # Folder documents are created with metadata containing folder_name
            result = session.run(
                """
                MATCH (d:Document {case_id: $case_id})
                WHERE d.folder_name = $folder_name
                   OR (d.metadata IS NOT NULL AND d.metadata.folder_name = $folder_name)
                RETURN d.summary AS summary
                ORDER BY d.created_at DESC
                LIMIT 1
                """,
                folder_name=folder_name,
                case_id=case_id,
            )
            record = result.single()
            if record and record["summary"]:
                return record["summary"]
            
            # Fallback: Try to find by document name pattern {profile}_{folder_name}
            # This matches the naming convention used in folder_ingestion.py
            result = session.run(
                """
                MATCH (d:Document {case_id: $case_id})
                WHERE d.name CONTAINS $folder_name
                   OR d.key CONTAINS $folder_name_normalized
                RETURN d.summary AS summary
                ORDER BY d.created_at DESC
                LIMIT 1
                """,
                folder_name=folder_name,
                folder_name_normalized=folder_name.lower().replace("_", "-"),
                case_id=case_id,
            )
            record = result.single()
            if record and record["summary"]:
                return record["summary"]
            
            return None

    def get_transcription_translation(self, folder_name: str, case_id: str) -> dict:
        """
        Get wiretap Spanish transcription and English translation for a folder, when available.
        Looks for Neo4j Document nodes: wiretap_{folder}_transcription_spanish,
        wiretap_{folder}_translation_english.

        Args:
            folder_name: Folder name (e.g. "00000128")
            case_id: Case ID

        Returns:
            {"spanish_transcription": str or None, "english_translation": str or None}
        """
        out = {"spanish_transcription": None, "english_translation": None}
        spanish_doc = f"wiretap_{folder_name}_transcription_spanish"
        english_doc = f"wiretap_{folder_name}_translation_english"
        s = self.get_document_summary(spanish_doc, case_id)
        e = self.get_document_summary(english_doc, case_id)
        if s and s.strip():
            out["spanish_transcription"] = s.strip()
        if e and e.strip():
            out["english_translation"] = e.strip()
        return out

    # -------------------------------------------------------------------------
    # Evidence File Deletion
    # -------------------------------------------------------------------------

    def find_document_node(self, filename: str, case_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a Document node by filename and case_id.

        Returns:
            Dict with document node info, or None if not found.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (d:Document {case_id: $case_id})
                WHERE d.name = $filename OR d.key = $filename
                RETURN d.key AS key, d.name AS name, d.case_id AS case_id,
                       id(d) AS neo4j_id
                """,
                filename=filename,
                case_id=case_id,
            )
            record = result.single()
            if record:
                return dict(record)
            return None

    def find_exclusive_entities(self, doc_key: str, case_id: str) -> List[Dict[str, Any]]:
        """
        Find entities that are ONLY mentioned in the given document
        (i.e. they have no MENTIONED_IN relationship to any other Document).

        Args:
            doc_key: Key of the Document node
            case_id: Case ID for scoping

        Returns:
            List of entity dicts with key, name, type
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                WHERE entity.case_id = $case_id
                WITH entity
                OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id})
                  WHERE other.key <> $doc_key
                WITH entity, count(other) AS other_doc_count
                WHERE other_doc_count = 0
                RETURN DISTINCT entity.key AS key, entity.name AS name,
                       labels(entity)[0] AS type
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            return [dict(record) for record in result]

    def delete_document_and_exclusive_entities(
        self, doc_key: str, case_id: str
    ) -> Dict[str, Any]:
        """
        Delete a Document node from the graph, along with any entities
        exclusively mentioned in that document (not shared with other docs).

        Args:
            doc_key: Key of the Document node to delete
            case_id: Case ID for scoping

        Returns:
            Dict with deleted_document, exclusive_entities_deleted, shared_entities_unlinked
        """
        with self._driver.session() as session:
            # 1. Verify document exists
            doc_result = session.run(
                """
                MATCH (d:Document {key: $doc_key, case_id: $case_id})
                RETURN d.key AS key, d.name AS name
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            doc_record = doc_result.single()
            if not doc_record:
                raise ValueError(f"Document not found: {doc_key} in case {case_id}")

            # 2. Find exclusive entities (only linked to this document)
            #    An entity is "exclusive" if its only MENTIONED_IN target is this doc.
            exclusive_result = session.run(
                """
                MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                WHERE entity.case_id = $case_id
                WITH entity
                OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id})
                  WHERE other.key <> $doc_key
                WITH entity, count(other) AS other_doc_count
                WHERE other_doc_count = 0
                RETURN entity.key AS key, entity.name AS name,
                       labels(entity)[0] AS type
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            exclusive_entities = [dict(r) for r in exclusive_result]

            # 3. Find shared entities (linked to this doc AND other docs)
            shared_result = session.run(
                """
                MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                WHERE entity.case_id = $case_id
                WITH entity
                OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id})
                  WHERE other.key <> $doc_key
                WITH entity, count(other) AS other_doc_count
                WHERE other_doc_count > 0
                RETURN entity.key AS key, entity.name AS name,
                       labels(entity)[0] AS type
                """,
                doc_key=doc_key,
                case_id=case_id,
            )
            shared_entities = [dict(r) for r in shared_result]

            # 4. Delete exclusive entities (DETACH DELETE removes all their rels)
            exclusive_keys = [e["key"] for e in exclusive_entities]
            if exclusive_keys:
                session.run(
                    """
                    MATCH (entity {case_id: $case_id})
                    WHERE entity.key IN $keys
                    DETACH DELETE entity
                    """,
                    case_id=case_id,
                    keys=exclusive_keys,
                )

            # 5. Remove MENTIONED_IN rels from shared entities to this doc
            if shared_entities:
                session.run(
                    """
                    MATCH (entity)-[r:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id})
                    WHERE entity.case_id = $case_id
                    DELETE r
                    """,
                    doc_key=doc_key,
                    case_id=case_id,
                )

            # 6. Delete the Document node itself (and all remaining rels)
            session.run(
                """
                MATCH (d:Document {key: $doc_key, case_id: $case_id})
                DETACH DELETE d
                """,
                doc_key=doc_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "deleted_document": {"key": doc_record["key"], "name": doc_record["name"]},
                "exclusive_entities_deleted": exclusive_entities,
                "shared_entities_unlinked": [e["key"] for e in shared_entities],
            }

    # -------------------------------------------------------------------------
    # Recycling Bin (Soft Delete)
    # -------------------------------------------------------------------------

    def soft_delete_entity(
        self, node_key: str, case_id: str, deleted_by: str, reason: str = "manual_delete"
    ) -> Dict[str, Any]:
        """
        Soft-delete an entity by moving it to the recycling bin.
        Stores full entity state (properties + relationships) as JSON on the node,
        then removes it from the active graph.

        Args:
            node_key: Key of the entity to soft-delete
            case_id: Case ID for scoping
            deleted_by: Username of who performed the deletion
            reason: Reason for deletion (e.g., 'manual_delete', 'merge_discard', 'file_delete')

        Returns:
            Dict with recycled entity info
        """
        import json as json_mod
        from datetime import datetime as dt

        with self._driver.session() as session:
            # 1. Fetch full entity properties
            entity_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                WHERE NOT n:Document
                RETURN n.key AS key, n.name AS name, labels(n) AS labels,
                       properties(n) AS props, id(n) AS neo4j_id
                """,
                key=node_key,
                case_id=case_id,
            )
            entity_record = entity_result.single()
            if not entity_record:
                raise ValueError(f"Entity not found: {node_key} in case {case_id}")

            # 2. Fetch all relationships
            rels_result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})-[r]-(other)
                RETURN type(r) AS rel_type, properties(r) AS rel_props,
                       other.key AS other_key, other.name AS other_name,
                       labels(other)[0] AS other_type,
                       CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END AS direction
                """,
                key=node_key,
                case_id=case_id,
            )
            relationships = [dict(r) for r in rels_result]

            # 3. Build the recycling bin record
            entity_props = dict(entity_record["props"])
            recycle_record = {
                "key": entity_record["key"],
                "name": entity_record["name"],
                "labels": list(entity_record["labels"]),
                "properties": entity_props,
                "relationships": relationships,
                "deleted_at": dt.now().isoformat(),
                "deleted_by": deleted_by,
                "reason": reason,
                "case_id": case_id,
            }

            # 4. Store in RecycleBin node
            session.run(
                """
                CREATE (rb:RecycleBin {
                    key: $key,
                    original_key: $original_key,
                    original_name: $original_name,
                    case_id: $case_id,
                    deleted_at: $deleted_at,
                    deleted_by: $deleted_by,
                    reason: $reason,
                    entity_data: $entity_data
                })
                """,
                key=f"recycled_{node_key}_{dt.now().strftime('%Y%m%d%H%M%S')}",
                original_key=node_key,
                original_name=entity_record["name"],
                case_id=case_id,
                deleted_at=recycle_record["deleted_at"],
                deleted_by=deleted_by,
                reason=reason,
                entity_data=json_mod.dumps(recycle_record, default=str),
            )

            # 5. Delete the original entity from graph
            session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                DETACH DELETE n
                """,
                key=node_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "recycled_entity": {
                    "key": entity_record["key"],
                    "name": entity_record["name"],
                    "type": entity_record["labels"][0] if entity_record["labels"] else "Unknown",
                },
                "relationships_stored": len(relationships),
                "reason": reason,
            }

    def list_recycled_entities(self, case_id: str) -> List[Dict[str, Any]]:
        """
        List all entities in the recycling bin for a case.

        Returns:
            List of recycled entity summaries.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (rb:RecycleBin {case_id: $case_id})
                RETURN rb.key AS key, rb.original_key AS original_key,
                       rb.original_name AS original_name,
                       rb.deleted_at AS deleted_at,
                       rb.deleted_by AS deleted_by,
                       rb.reason AS reason
                ORDER BY rb.deleted_at DESC
                """,
                case_id=case_id,
            )
            return [dict(r) for r in result]

    def restore_recycled_entity(self, recycle_key: str, case_id: str) -> Dict[str, Any]:
        """
        Restore an entity from the recycling bin back into the graph.

        Args:
            recycle_key: Key of the RecycleBin node
            case_id: Case ID for scoping

        Returns:
            Dict with restored entity info
        """
        import json as json_mod

        with self._driver.session() as session:
            # 1. Get the recycle bin record
            rb_result = session.run(
                """
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
                RETURN rb.entity_data AS entity_data, rb.original_key AS original_key,
                       rb.original_name AS original_name
                """,
                key=recycle_key,
                case_id=case_id,
            )
            rb_record = rb_result.single()
            if not rb_record:
                raise ValueError(f"Recycled entity not found: {recycle_key}")

            entity_data = json_mod.loads(rb_record["entity_data"])

            # 2. Check that original key doesn't already exist
            existing = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                RETURN count(n) AS cnt
                """,
                key=entity_data["key"],
                case_id=case_id,
            )
            if existing.single()["cnt"] > 0:
                raise ValueError(
                    f"Entity with key '{entity_data['key']}' already exists in the graph. "
                    "Cannot restore — resolve the conflict first."
                )

            # 3. Recreate entity node with stored properties
            props = entity_data.get("properties", {})
            label = entity_data["labels"][0] if entity_data.get("labels") else "Entity"

            # Build safe property SET
            safe_props = {}
            for k, v in props.items():
                if v is not None and isinstance(v, (str, int, float, bool)):
                    safe_props[k] = v

            session.run(
                f"""
                CREATE (n:`{label}`)
                SET n = $props
                """,
                props=safe_props,
            )

            # 4. Restore relationships where the other node still exists
            restored_rels = 0
            for rel in entity_data.get("relationships", []):
                other_key = rel.get("other_key")
                rel_type = rel.get("rel_type")
                direction = rel.get("direction")
                rel_props = rel.get("rel_props", {})

                if not other_key or not rel_type:
                    continue

                # Check if the other node still exists
                exists_check = session.run(
                    "MATCH (n {key: $key}) RETURN count(n) AS cnt",
                    key=other_key,
                )
                if exists_check.single()["cnt"] == 0:
                    continue

                # Filter rel props
                safe_rel_props = {}
                for k, v in (rel_props or {}).items():
                    if v is not None and isinstance(v, (str, int, float, bool)):
                        safe_rel_props[k] = v

                if direction == "outgoing":
                    if safe_rel_props:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            SET r = $props
                            """,
                            a_key=entity_data["key"],
                            b_key=other_key,
                            props=safe_rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            """,
                            a_key=entity_data["key"],
                            b_key=other_key,
                        )
                else:
                    if safe_rel_props:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            SET r = $props
                            """,
                            a_key=other_key,
                            b_key=entity_data["key"],
                            props=safe_rel_props,
                        )
                    else:
                        session.run(
                            f"""
                            MATCH (a {{key: $a_key}}), (b {{key: $b_key}})
                            CREATE (a)-[r:`{rel_type}`]->(b)
                            """,
                            a_key=other_key,
                            b_key=entity_data["key"],
                        )
                restored_rels += 1

            # 5. Delete recycle bin record
            session.run(
                """
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
                DELETE rb
                """,
                key=recycle_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "restored_entity": {
                    "key": entity_data["key"],
                    "name": entity_data.get("name", ""),
                    "type": label,
                },
                "relationships_restored": restored_rels,
            }

    def permanently_delete_recycled(self, recycle_key: str, case_id: str) -> Dict[str, Any]:
        """
        Permanently delete a recycled entity (remove from recycle bin).

        Args:
            recycle_key: Key of the RecycleBin node
            case_id: Case ID for scoping

        Returns:
            Dict with deletion info
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
                RETURN rb.original_name AS name, rb.original_key AS original_key
                """,
                key=recycle_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Recycled entity not found: {recycle_key}")

            session.run(
                """
                MATCH (rb:RecycleBin {key: $key, case_id: $case_id})
                DELETE rb
                """,
                key=recycle_key,
                case_id=case_id,
            )

            return {
                "success": True,
                "permanently_deleted": {
                    "recycle_key": recycle_key,
                    "original_key": record["original_key"],
                    "name": record["name"],
                },
            }

    def bulk_soft_delete_financial_for_document(
        self,
        doc_name: str,
        case_id: str,
        deleted_by: str,
        reason: str = "audit_replacement",
        *,
        exclude_audit_proposed: bool = True,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Soft-delete all financial transaction nodes mentioned in a single document.

        Walks (n)-[:MENTIONED_IN]->(:Document {name, case_id}) and recycles every
        node with a non-null ``amount`` (i.e. financial transactions and balances)
        via :meth:`soft_delete_entity`.  Document/Case/FinancialCategory nodes are
        excluded.  When ``exclude_audit_proposed`` is True (the default), audited
        v2 replacement nodes flagged ``audit_status='proposed'`` are also excluded
        so they survive the cleanup.

        Defaults to ``dry_run=True`` — pass ``dry_run=False`` to actually recycle.

        Args:
            doc_name:               Document name to scope the cleanup
            case_id:                Case ID for scoping
            deleted_by:             Username recorded against each recycled node
            reason:                 Reason string stored on each RecycleBin entry
            exclude_audit_proposed: Skip nodes with ``audit_status='proposed'``
            dry_run:                If True, list candidates without recycling

        Returns:
            Dict with candidate count, deleted count, and any failures.
        """
        with self._driver.session() as session:
            extra = (
                " AND coalesce(n.audit_status, '') <> 'proposed'"
                if exclude_audit_proposed
                else ""
            )
            query = f"""
                MATCH (n)-[:MENTIONED_IN]->(d:Document {{name: $doc_name, case_id: $case_id}})
                WHERE n.amount IS NOT NULL
                  AND n.case_id = $case_id
                  AND NOT n:Document
                  AND NOT n:Case
                  AND NOT n:FinancialCategory
                  AND NOT n:RecycleBin
                  {extra}
                RETURN n.key AS key, labels(n)[0] AS type, n.name AS name, n.amount AS amount,
                       n.audit_status AS audit_status
            """
            result = session.run(query, doc_name=doc_name, case_id=case_id)
            candidates = [
                {
                    "key": r["key"],
                    "type": r["type"],
                    "name": r["name"],
                    "amount": r["amount"],
                    "audit_status": r["audit_status"],
                }
                for r in result
            ]

        if dry_run:
            return {
                "doc_name": doc_name,
                "case_id": case_id,
                "candidate_count": len(candidates),
                "candidates": candidates,
                "deleted_count": 0,
                "failed_count": 0,
                "failures": [],
                "dry_run": True,
            }

        deleted: List[Dict] = []
        failures: List[Dict] = []
        for cand in candidates:
            try:
                self.soft_delete_entity(
                    node_key=cand["key"],
                    case_id=case_id,
                    deleted_by=deleted_by,
                    reason=reason,
                )
                deleted.append(cand)
            except Exception as exc:
                failures.append({"key": cand["key"], "error": str(exc)})

        return {
            "doc_name": doc_name,
            "case_id": case_id,
            "candidate_count": len(candidates),
            "deleted_count": len(deleted),
            "failed_count": len(failures),
            "failures": failures,
            "dry_run": False,
        }

    # -------------------------------------------------------------------------
    # Case Management
    # -------------------------------------------------------------------------

    def delete_case_data(self, case_id: str) -> Dict[str, Any]:
        """
        Delete all nodes and relationships belonging to a specific case.

        Args:
            case_id: The case ID whose data should be deleted

        Returns:
            Dict with counts of deleted nodes and relationships
        """
        with self._driver.session() as session:
            # Count nodes and relationships before deletion
            node_count_result = session.run(
                "MATCH (n {case_id: $case_id}) RETURN count(n) AS count",
                case_id=case_id,
            )
            node_count = node_count_result.single()["count"]

            rel_count_result = session.run(
                "MATCH ()-[r {case_id: $case_id}]-() RETURN count(r) AS count",
                case_id=case_id,
            )
            rel_count = rel_count_result.single()["count"]

            # Delete relationships first (with case_id), then nodes
            session.run(
                "MATCH ()-[r {case_id: $case_id}]-() DELETE r",
                case_id=case_id,
            )
            session.run(
                "MATCH (n {case_id: $case_id}) DELETE n",
                case_id=case_id,
            )

            return {
                "success": True,
                "case_id": case_id,
                "nodes_deleted": node_count,
                "relationships_deleted": rel_count,
            }

    # -------------------------------------------------------------------------
    # Financial Analysis
    # -------------------------------------------------------------------------

    def ensure_transaction_ref_ids(self, case_id: str) -> int:
        """Assign 8-char uppercase hex ref_id to all transaction nodes missing one.

        Uses uuid4 truncated to 8 hex chars.  Checks for collisions within the
        case and regenerates if needed.  Idempotent — safe to call repeatedly.

        Returns the number of newly assigned ref_ids.
        """
        import uuid as _uuid

        with self._driver.session() as session:
            # Existing ref_ids for collision checking
            existing = session.run(
                "MATCH (n {case_id: $case_id}) WHERE n.amount IS NOT NULL "
                "AND n.ref_id IS NOT NULL RETURN n.ref_id AS ref_id",
                case_id=case_id,
            )
            used_ids = {r["ref_id"] for r in existing}

            # Nodes missing ref_id
            missing = session.run(
                "MATCH (n {case_id: $case_id}) WHERE n.amount IS NOT NULL "
                "AND n.ref_id IS NULL RETURN n.key AS key",
                case_id=case_id,
            )
            keys_to_update = [r["key"] for r in missing]

            if not keys_to_update:
                return 0

            count = 0
            for key in keys_to_update:
                ref_id = _uuid.uuid4().hex[:8].upper()
                while ref_id in used_ids:
                    ref_id = _uuid.uuid4().hex[:8].upper()
                used_ids.add(ref_id)
                session.run(
                    "MATCH (n {key: $key, case_id: $case_id}) "
                    "SET n.ref_id = $ref_id",
                    key=key, case_id=case_id, ref_id=ref_id,
                )
                count += 1

            logger.info("[RefID] Assigned %d ref_ids for case %s", count, case_id)
            return count

    def ensure_unique_transaction_keys(self, case_id: str) -> int:
        """Deduplicate transaction keys within a case.

        Finds transaction nodes that share the same key and appends a short
        hex suffix (e.g. ``-a3f2``) to each duplicate so every key is unique.
        The first occurrence (by internal Neo4j id) is left unchanged.

        Idempotent — safe to call repeatedly (no-op when no duplicates exist).

        Returns the number of keys that were renamed.
        """
        import uuid as _uuid

        with self._driver.session() as session:
            # Find all keys that appear more than once
            dup_result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE n.amount IS NOT NULL AND n.key IS NOT NULL
                WITH n.key AS k, collect(id(n)) AS ids
                WHERE size(ids) > 1
                RETURN k AS key, ids
                """,
                case_id=case_id,
            )
            dup_groups = [(r["key"], r["ids"]) for r in dup_result]

            if not dup_groups:
                return 0

            # Collect all existing keys for collision avoidance
            all_keys_result = session.run(
                "MATCH (n {case_id: $case_id}) WHERE n.key IS NOT NULL "
                "RETURN collect(n.key) AS keys",
                case_id=case_id,
            )
            used_keys = set(all_keys_result.single()["keys"])

            count = 0
            for base_key, node_ids in dup_groups:
                # Keep the first node's key unchanged, rename the rest
                for nid in node_ids[1:]:
                    suffix = _uuid.uuid4().hex[:4]
                    new_key = f"{base_key}-{suffix}"
                    while new_key in used_keys:
                        suffix = _uuid.uuid4().hex[:4]
                        new_key = f"{base_key}-{suffix}"
                    used_keys.add(new_key)
                    session.run(
                        "MATCH (n) WHERE id(n) = $nid SET n.key = $new_key",
                        nid=nid, new_key=new_key,
                    )
                    count += 1

            if count:
                logger.info(
                    "[DedupKeys] Renamed %d duplicate transaction keys across %d groups for case %s",
                    count, len(dup_groups), case_id,
                )
            return count

    def bulk_append_notes_by_ref_id(self, case_id: str, notes_data: list) -> dict:
        """Append investigator notes to transactions matched by ref_id.

        Args:
            case_id: Case ID
            notes_data: List of dicts with 'ref_id' and 'notes' keys
                        (optionally 'interviewer', 'date', 'question', 'answer')

        Returns:
            dict with matched, unmatched_ref_ids, total
        """
        with self._driver.session() as session:
            matched = 0
            unmatched = []

            for entry in notes_data:
                ref_id = (entry.get("ref_id") or "").strip().upper()
                if not ref_id:
                    continue

                # Build formatted note text
                parts = []
                if entry.get("interviewer"):
                    parts.append(f"Interviewer: {entry['interviewer']}")
                if entry.get("date"):
                    parts.append(f"Date: {entry['date']}")
                if entry.get("question"):
                    parts.append(f"Q: {entry['question']}")
                if entry.get("answer"):
                    parts.append(f"A: {entry['answer']}")
                note_text = (entry.get("notes") or "").strip()
                if note_text:
                    parts.append(note_text)

                formatted = "\n".join(parts) if parts else ""
                if not formatted:
                    continue

                result = session.run(
                    """
                    MATCH (n {case_id: $case_id, ref_id: $ref_id})
                    WHERE n.amount IS NOT NULL
                    SET n.notes = CASE
                        WHEN n.notes IS NULL OR n.notes = '' THEN $note
                        ELSE n.notes + '\n---\n' + $note
                    END
                    RETURN n.key AS key
                    """,
                    case_id=case_id, ref_id=ref_id, note=formatted,
                )
                if list(result):
                    matched += 1
                else:
                    unmatched.append(ref_id)

            return {
                "matched": matched,
                "unmatched_ref_ids": unmatched,
                "total": len(notes_data),
            }

    def get_financial_transactions(
        self,
        case_id: str,
        types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        categories: Optional[List[str]] = None,
        data_version: Optional[str] = None,
    ) -> List[Dict]:
        """
        Get all nodes that have amount properties, with from/to entity resolution.

        Args:
            case_id: REQUIRED - Filter to only include nodes belonging to this case
            types: Filter by specific node types (e.g., ['Transaction', 'Payment'])
            start_date: Filter on or after this date (YYYY-MM-DD)
            end_date: Filter on or before this date (YYYY-MM-DD)
            categories: Filter by financial_category values

        Returns:
            List of transaction dicts with from/to entity resolution
        """
        # Lazy backfill: deduplicate keys, then ensure every transaction has a ref_id.
        # Only run once per case per process lifetime to avoid repeated full-scans.
        if case_id not in self._backfilled_keys:
            self.ensure_unique_transaction_keys(case_id)
            self._backfilled_keys.add(case_id)
        if case_id not in self._backfilled_refs:
            self.ensure_transaction_ref_ids(case_id)
            self._backfilled_refs.add(case_id)

        with self._driver.session() as session:
            params = {"case_id": case_id}
            conditions = []

            if types:
                conditions.append("labels(n)[0] IN $types")
                params["types"] = types
            if start_date:
                conditions.append("n.date >= $start_date")
                params["start_date"] = start_date
            if end_date:
                conditions.append("n.date <= $end_date")
                params["end_date"] = end_date
            if categories:
                conditions.append("coalesce(n.financial_category, 'Unknown') IN $categories")
                params["categories"] = categories
            if data_version == "legacy":
                conditions.append("coalesce(n.audit_status, '') <> 'proposed'")
            elif data_version == "v2":
                conditions.append("n.audit_status = 'proposed'")

            extra_filter = (" AND " + " AND ".join(conditions)) if conditions else ""

            # ── Phase 1: Fast property-only query (no relationship traversal) ──
            # Reads node properties directly — handles manual overrides and
            # previously-stored entity keys.  Only one lightweight OPTIONAL
            # MATCH for source_doc.
            fast_query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL
                AND n.case_id = $case_id
                {extra_filter}
                OPTIONAL MATCH (n)-[:MENTIONED_IN]->(source_doc:Document)
                WHERE source_doc.case_id = $case_id
                RETURN
                    n.key AS key,
                    n.ref_id AS ref_id,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.date AS date,
                    n.time AS time,
                    toFloat(replace(replace(replace(replace(
                      trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS amount,
                    n.amount AS raw_amount,
                    n.currency AS currency,
                    n.summary AS summary,
                    n.financial_category AS financial_category,
                    n.purpose AS purpose,
                    n.counterparty_details AS counterparty_details,
                    n.notes AS notes,
                    n.from_entity_key AS from_entity_key,
                    n.from_entity_name AS from_entity_name,
                    n.to_entity_key AS to_entity_key,
                    n.to_entity_name AS to_entity_name,
                    n.has_manual_from AS has_manual_from,
                    n.has_manual_to AS has_manual_to,
                    n.is_parent AS is_parent,
                    n.parent_transaction_key AS parent_transaction_key,
                    n.amount_corrected AS amount_corrected,
                    n.original_amount AS original_amount,
                    n.correction_reason AS correction_reason,
                    collect(DISTINCT source_doc.name) AS source_document_names
                ORDER BY n.date ASC, n.time ASC
            """

            result = session.run(fast_query, **params)
            transactions = []
            # Track keys that need relationship-based entity resolution
            needs_rel_lookup = []

            for record in result:
                amount_val = safe_float(record["amount"])
                if amount_val == 0:
                    raw = record.get("raw_amount")
                    if raw is not None:
                        cleaned = re.sub(r'[^\d.\-]', '', str(raw))
                        amount_val = safe_float(cleaned)
                        if amount_val != 0:
                            logger.warning(
                                "Amount fallback used for tx %s: raw=%r → %s",
                                record["key"], raw, amount_val
                            )
                        else:
                            logger.warning(
                                "Amount resolved to 0 for tx %s: raw=%r",
                                record["key"], raw
                            )

                from_key = record["from_entity_key"]
                from_name = record["from_entity_name"]
                to_key = record["to_entity_key"]
                to_name = record["to_entity_name"]

                # Check if this transaction needs relationship fallback
                has_from = bool(record["has_manual_from"]) or from_key or from_name
                has_to = bool(record["has_manual_to"]) or to_key or to_name
                if not has_from or not has_to:
                    needs_rel_lookup.append(record["key"])

                txn = {
                    "key": record["key"],
                    "ref_id": record["ref_id"],
                    "name": record["name"],
                    "type": record["type"],
                    "date": record["date"],
                    "time": record["time"],
                    "amount": amount_val,
                    "currency": record["currency"],
                    "summary": record["summary"],
                    "category": record["financial_category"] or "Uncategorized",
                    "purpose": record["purpose"],
                    "counterparty_details": record["counterparty_details"],
                    "notes": record["notes"],
                    "from_entity": {"key": from_key, "name": from_name} if (from_key or from_name) else None,
                    "to_entity": {"key": to_key, "name": to_name} if (to_key or to_name) else None,
                    "has_manual_from": bool(record["has_manual_from"]),
                    "has_manual_to": bool(record["has_manual_to"]),
                    "is_parent": record["is_parent"] or False,
                    "parent_transaction_key": record["parent_transaction_key"],
                    "source_document": ", ".join(filter(None, record["source_document_names"])) or None,
                }
                # Only include correction fields when they have values
                if record["amount_corrected"]:
                    txn["amount_corrected"] = True
                    txn["original_amount"] = record["original_amount"]
                    txn["correction_reason"] = record["correction_reason"]

                transactions.append(txn)

            # ── Phase 2: Relationship fallback for unresolved entities ──
            # Only runs for the subset of transactions that lack stored entity
            # properties AND have no manual override.
            if needs_rel_lookup:
                logger.info(
                    "Financial query phase 2: resolving entities for %d/%d transactions via relationships",
                    len(needs_rel_lookup), len(transactions),
                )
                rel_query = """
                    MATCH (n)
                    WHERE n.key IN $keys AND n.case_id = $case_id
                    OPTIONAL MATCH (n)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(to_entity)
                    WHERE to_entity.case_id = $case_id AND NOT to_entity:Document AND NOT to_entity:Case
                    OPTIONAL MATCH (from_entity)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(n)
                    WHERE from_entity.case_id = $case_id AND NOT from_entity:Document AND NOT from_entity:Case
                    OPTIONAL MATCH (n)-[:RECEIVED_FROM]->(rf_entity)
                    WHERE rf_entity.case_id = $case_id AND NOT rf_entity:Document AND NOT rf_entity:Case
                    OPTIONAL MATCH (n)<-[:MADE_PAYMENT|INITIATED]-(initiator)
                    WHERE initiator.case_id = $case_id AND NOT initiator:Document AND NOT initiator:Case
                    RETURN n.key AS key,
                        collect(DISTINCT to_entity.key)[0] AS rel_to_key,
                        collect(DISTINCT to_entity.name)[0] AS rel_to_name,
                        collect(DISTINCT from_entity.key)[0] AS rel_from_key,
                        collect(DISTINCT from_entity.name)[0] AS rel_from_name,
                        collect(DISTINCT rf_entity.key)[0] AS rf_key,
                        collect(DISTINCT rf_entity.name)[0] AS rf_name,
                        collect(DISTINCT initiator.key)[0] AS initiator_key,
                        collect(DISTINCT initiator.name)[0] AS initiator_name
                """
                rel_result = session.run(rel_query, keys=needs_rel_lookup, case_id=case_id)
                rel_map = {}
                for r in rel_result:
                    rel_map[r["key"]] = r

                # Build lookup for fast merge
                txn_by_key = {t["key"]: t for t in transactions}
                for key, r in rel_map.items():
                    txn = txn_by_key.get(key)
                    if not txn:
                        continue
                    # Fill in from_entity if missing
                    if not txn["from_entity"]:
                        fk = r["rel_from_key"] or r["initiator_key"]
                        fn = r["rel_from_name"] or r["initiator_name"]
                        if fk or fn:
                            txn["from_entity"] = {"key": fk, "name": fn}
                    # Fill in to_entity if missing
                    if not txn["to_entity"]:
                        tk = r["rel_to_key"] or r["rf_key"]
                        tn = r["rel_to_name"] or r["rf_name"]
                        if tk or tn:
                            txn["to_entity"] = {"key": tk, "name": tn}

            return transactions

    # ------------------------------------------------------------------
    # Paginated financial query — used by the main frontend view
    # ------------------------------------------------------------------

    def _build_financial_where(self, params: dict, *,
                                types=None, categories=None,
                                start_date=None, end_date=None,
                                search=None, search_header=None,
                                from_entity_keys=None, to_entity_keys=None,
                                include_entity_filter=True) -> str:
        """Build a reusable WHERE clause fragment for financial queries.

        Mutates *params* to add any needed query parameters.
        Returns a string like ``AND ... AND ...`` (no leading WHERE).
        """
        parts: list[str] = []

        if types:
            parts.append("labels(n)[0] IN $types")
            params["types"] = types
        if categories:
            parts.append("coalesce(n.financial_category, 'Uncategorized') IN $categories")
            params["categories"] = categories
        if start_date:
            parts.append("n.date >= $start_date")
            params["start_date"] = start_date
        if end_date:
            parts.append("n.date <= $end_date")
            params["end_date"] = end_date

        # Filter panel search — broad field set
        if search:
            params["search_q"] = search.lower()
            parts.append("""(
                toLower(coalesce(n.name, '')) CONTAINS $search_q
                OR toLower(coalesce(n.purpose, '')) CONTAINS $search_q
                OR toLower(coalesce(n.notes, '')) CONTAINS $search_q
                OR toLower(coalesce(n.counterparty_details, '')) CONTAINS $search_q
                OR toLower(coalesce(n.from_entity_name, '')) CONTAINS $search_q
                OR toLower(coalesce(n.to_entity_name, '')) CONTAINS $search_q
                OR toLower(coalesce(n.financial_category, '')) CONTAINS $search_q
                OR toLower(coalesce(n.summary, '')) CONTAINS $search_q
            )""")

        # Header bar search — narrower field set
        if search_header:
            params["search_h"] = search_header.lower()
            parts.append("""(
                toLower(coalesce(n.name, '')) CONTAINS $search_h
                OR toLower(coalesce(n.from_entity_name, '')) CONTAINS $search_h
                OR toLower(coalesce(n.to_entity_name, '')) CONTAINS $search_h
                OR toLower(coalesce(n.purpose, '')) CONTAINS $search_h
                OR toLower(coalesce(n.notes, '')) CONTAINS $search_h
                OR toLower(coalesce(n.summary, '')) CONTAINS $search_h
            )""")

        # Entity selection (only when requested)
        if include_entity_filter:
            if from_entity_keys:
                params["from_keys"] = from_entity_keys
                parts.append(
                    "(coalesce(n.from_entity_key, n.from_entity_name) IN $from_keys)"
                )
            if to_entity_keys:
                params["to_keys"] = to_entity_keys
                parts.append(
                    "(coalesce(n.to_entity_key, n.to_entity_name) IN $to_keys)"
                )

        return (" AND " + " AND ".join(parts)) if parts else ""

    def query_financial_transactions(
        self,
        case_id: str,
        *,
        types: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        search_header: Optional[str] = None,
        from_entity_keys: Optional[List[str]] = None,
        to_entity_keys: Optional[List[str]] = None,
        sort_field: str = "date",
        sort_dir: str = "asc",
        offset: int = 0,
        limit: int = 100,
        skip_aggregations: bool = False,
    ) -> Dict:
        """Server-side paginated financial query with aggregations.

        Returns a single dict with:
          transactions  – one page of transaction rows
          total         – total count matching all filters
          summary       – aggregated stats (volume, avg, inflow/outflow)
          from_entities – sender breakdown (for entity flow tables)
          to_entities   – recipient breakdown (for entity flow tables)
          volume_data   – date+category grouped volumes (for charts)
          category_breakdown – category counts/amounts (for donut chart)
        """
        # Sort field mapping
        sort_map = {
            "date": "n.date",
            "time": "n.time",
            "name": "n.name",
            "amount": "toFloat(replace(replace(replace(replace(trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', ''))",
            "type": "labels(n)[0]",
            "category": "coalesce(n.financial_category, 'Uncategorized')",
        }
        order_expr = sort_map.get(sort_field, "n.date")
        order_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"

        with self._driver.session() as session:

            # ── Shared filter kwargs ──
            filter_kw = dict(
                types=types, categories=categories,
                start_date=start_date, end_date=end_date,
                search=search, search_header=search_header,
                from_entity_keys=from_entity_keys,
                to_entity_keys=to_entity_keys,
            )

            # ═══════════════════════════════════════════════════════════
            # Query A: Count + Summary (full filtered set)
            # — skipped when skip_aggregations=True (sort/page only)
            # ═══════════════════════════════════════════════════════════
            summary = None
            if not skip_aggregations:
                logger.info("[FinQuery] Phase A: Summary query for case %s", case_id)
                has_entity_selection = bool(from_entity_keys or to_entity_keys)
                params_a = {"case_id": case_id}
                where_a = self._build_financial_where(params_a, **filter_kw)

                # total_outflows = Payments  (money leaving the account holder)
                # total_inflows  = Receipts  (money arriving at the account holder)
                #
                # Under the sign-normalized convention (see
                # TRANSACTION_REPROCESS_PLAN.md §3.0.1), direction is encoded by
                # sign: negative = outgoing/Payment, positive = incoming/Receipt.
                # Legacy all-positive cases will therefore show Payments=$0 and
                # Receipts=full volume until they are reprocessed — accepted
                # trade-off per §5 Q5 option (b).
                summary_query = f"""
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    {where_a}
                    WITH n,
                         toFloat(replace(replace(replace(replace(
                           trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS rawAmt
                    WITH n, CASE WHEN rawAmt IS NOT NULL AND rawAmt = rawAmt THEN rawAmt ELSE 0 END AS amt
                    RETURN
                        count(n) AS total,
                        sum(abs(amt)) AS total_volume,
                        avg(abs(amt)) AS avg_amount,
                        count(DISTINCT coalesce(n.from_entity_key, n.from_entity_name)) +
                        count(DISTINCT coalesce(n.to_entity_key, n.to_entity_name)) AS unique_entity_refs,
                        sum(CASE WHEN amt < 0 THEN abs(amt) ELSE 0 END) AS total_outflows,
                        sum(CASE WHEN amt >= 0 THEN abs(amt) ELSE 0 END) AS total_inflows
                """
                sr = session.run(summary_query, **params_a).single()
                summary = {
                    "transaction_count": sr["total"] or 0,
                    "total_volume": safe_float(sr["total_volume"]),
                    "avg_amount": safe_float(sr["avg_amount"]),
                    "unique_entities": sr["unique_entity_refs"] or 0,
                    "total_inflows": safe_float(sr["total_inflows"]),
                    "total_outflows": safe_float(sr["total_outflows"]),
                    "net_flow": safe_float(sr["total_inflows"]) - safe_float(sr["total_outflows"]),
                }

                # Entity-mode directional flow summary + per-entity breakdown
                # When entities are selected, classify flows relative to those entities:
                #   - Selected entity appears as from_entity → money leaving = OUTFLOW
                #   - Selected entity appears as to_entity → money arriving = INFLOW
                # When user selected FROM entities, perspective = from_entity_keys
                # When user selected TO entities, perspective = to_entity_keys
                # This matches the old client-side logic exactly.
                if has_entity_selection and summary["transaction_count"] > 0:
                    params_flow = {"case_id": case_id}
                    where_flow = self._build_financial_where(params_flow, **filter_kw)

                    # Compute per-entity breakdown of inflows and outflows
                    # from_entity perspective: entity is sender → outflow; entity is receiver → inflow
                    # to_entity perspective: entity is receiver → inflow; entity is sender → outflow
                    if from_entity_keys:
                        params_flow["perspective_keys"] = from_entity_keys
                    else:
                        params_flow["perspective_keys"] = to_entity_keys

                    flow_query = f"""
                        MATCH (n)
                        WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                        {where_flow}
                        WITH n,
                             toFloat(replace(replace(replace(replace(
                               trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS rawAmt,
                             coalesce(n.from_entity_key, n.from_entity_name) AS fk,
                             coalesce(n.to_entity_key, n.to_entity_name) AS tk,
                             n.from_entity_name AS fn,
                             n.to_entity_name AS tn
                        WITH n, abs(CASE WHEN rawAmt IS NOT NULL AND rawAmt = rawAmt THEN rawAmt ELSE 0 END) AS amt, fk, tk, fn, tn,
                             CASE WHEN fk IN $perspective_keys THEN true ELSE false END AS is_outflow,
                             CASE WHEN tk IN $perspective_keys THEN true ELSE false END AS is_inflow
                        RETURN
                            sum(CASE WHEN is_inflow THEN amt ELSE 0 END) AS entity_inflows,
                            sum(CASE WHEN is_outflow THEN amt ELSE 0 END) AS entity_outflows,
                            collect(CASE WHEN is_outflow THEN {{key: coalesce(tk, 'Unknown'), name: coalesce(tn, tk, 'Unknown'), amount: amt}} END) AS outflow_details,
                            collect(CASE WHEN is_inflow THEN {{key: coalesce(fk, 'Unknown'), name: coalesce(fn, fk, 'Unknown'), amount: amt}} END) AS inflow_details
                    """
                    fr = session.run(flow_query, **params_flow).single()
                    entity_inflows = safe_float(fr["entity_inflows"])
                    entity_outflows = safe_float(fr["entity_outflows"])
                    summary["total_inflows"] = entity_inflows
                    summary["total_outflows"] = entity_outflows
                    summary["net_flow"] = entity_inflows - entity_outflows

                    # Build per-entity breakdown (aggregate amounts by entity key)
                    def aggregate_entity_list(details):
                        """Aggregate a list of {key, name, amount} dicts by key."""
                        by_key = {}
                        for d in details:
                            if d is None:
                                continue
                            k = d.get("key", "Unknown")
                            n = d.get("name", k)
                            a = safe_float(d.get("amount", 0))
                            if k in by_key:
                                by_key[k]["amount"] += a
                            else:
                                by_key[k] = {"name": n, "amount": a}
                        return sorted(by_key.values(), key=lambda x: x["amount"], reverse=True)

                    summary["inflow_entities"] = aggregate_entity_list(fr["inflow_details"])
                    summary["outflow_entities"] = aggregate_entity_list(fr["outflow_details"])

            # ═══════════════════════════════════════════════════════════
            # Query B: Paginated rows
            # ═══════════════════════════════════════════════════════════
            logger.info("[FinQuery] Phase B: Paginated rows (offset=%d, limit=%d)", offset, limit)
            # Pre-fetch parent keys so we can exclude children whose parent
            # is in the filtered dataset (they render as expanded sub-rows instead).
            params_pk = {"case_id": case_id}
            where_pk = self._build_financial_where(params_pk, **filter_kw)
            pk_query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                  AND n.is_parent = true
                {where_pk}
                RETURN collect(n.key) AS parent_keys
            """
            pk_result = session.run(pk_query, **params_pk).single()
            active_parent_keys = pk_result["parent_keys"] if pk_result else []

            # Count rows for pagination (same filter as page query — excludes children)
            params_cnt = {"case_id": case_id, "active_parent_keys": active_parent_keys}
            where_cnt = self._build_financial_where(params_cnt, **filter_kw)
            cnt_query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                {where_cnt}
                AND (n.parent_transaction_key IS NULL
                     OR NOT n.parent_transaction_key IN $active_parent_keys)
                RETURN count(n) AS total
            """
            total = session.run(cnt_query, **params_cnt).single()["total"] or 0

            params_b = {"case_id": case_id, "offset": offset, "limit": limit,
                        "active_parent_keys": active_parent_keys}
            where_b = self._build_financial_where(params_b, **filter_kw)

            page_query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                {where_b}
                AND (n.parent_transaction_key IS NULL
                     OR NOT n.parent_transaction_key IN $active_parent_keys)
                OPTIONAL MATCH (n)-[:MENTIONED_IN]->(source_doc:Document)
                WHERE source_doc.case_id = $case_id
                WITH n, collect(DISTINCT source_doc.name) AS source_document_names
                ORDER BY {order_expr} {order_dir}, n.key ASC
                SKIP $offset LIMIT $limit
                RETURN
                    n.key AS key,
                    n.ref_id AS ref_id,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.date AS date,
                    n.time AS time,
                    toFloat(replace(replace(replace(replace(
                      trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS amount,
                    n.amount AS raw_amount,
                    n.currency AS currency,
                    n.summary AS summary,
                    n.financial_category AS financial_category,
                    n.purpose AS purpose,
                    n.counterparty_details AS counterparty_details,
                    n.notes AS notes,
                    n.from_entity_key AS from_entity_key,
                    n.from_entity_name AS from_entity_name,
                    n.to_entity_key AS to_entity_key,
                    n.to_entity_name AS to_entity_name,
                    n.has_manual_from AS has_manual_from,
                    n.has_manual_to AS has_manual_to,
                    n.is_parent AS is_parent,
                    n.parent_transaction_key AS parent_transaction_key,
                    n.amount_corrected AS amount_corrected,
                    n.original_amount AS original_amount,
                    n.correction_reason AS correction_reason,
                    source_document_names
            """

            result_b = session.run(page_query, **params_b)
            transactions = []
            needs_rel_lookup = []

            for record in result_b:
                amount_val = safe_float(record["amount"])
                if amount_val == 0:
                    raw = record.get("raw_amount")
                    if raw is not None:
                        cleaned = re.sub(r'[^\d.\-]', '', str(raw))
                        amount_val = safe_float(cleaned)

                from_key = record["from_entity_key"]
                from_name = record["from_entity_name"]
                to_key = record["to_entity_key"]
                to_name = record["to_entity_name"]

                has_from = bool(record["has_manual_from"]) or from_key or from_name
                has_to = bool(record["has_manual_to"]) or to_key or to_name
                if not has_from or not has_to:
                    needs_rel_lookup.append(record["key"])

                txn = {
                    "key": record["key"],
                    "ref_id": record["ref_id"],
                    "name": record["name"],
                    "type": record["type"],
                    "date": record["date"],
                    "time": record["time"],
                    "amount": amount_val,
                    "currency": record["currency"],
                    "summary": record["summary"],
                    "category": record["financial_category"] or "Uncategorized",
                    "purpose": record["purpose"],
                    "counterparty_details": record["counterparty_details"],
                    "notes": record["notes"],
                    "from_entity": {"key": from_key, "name": from_name} if (from_key or from_name) else None,
                    "to_entity": {"key": to_key, "name": to_name} if (to_key or to_name) else None,
                    "has_manual_from": bool(record["has_manual_from"]),
                    "has_manual_to": bool(record["has_manual_to"]),
                    "is_parent": record["is_parent"] or False,
                    "parent_transaction_key": record["parent_transaction_key"],
                    "source_document": ", ".join(filter(None, record["source_document_names"])) or None,
                }
                if record["amount_corrected"]:
                    txn["amount_corrected"] = True
                    txn["original_amount"] = record["original_amount"]
                    txn["correction_reason"] = record["correction_reason"]

                transactions.append(txn)

            # Phase 2 relationship fallback (only for this page's unresolved rows)
            if needs_rel_lookup:
                rel_query = """
                    MATCH (n)
                    WHERE n.key IN $keys AND n.case_id = $case_id
                    OPTIONAL MATCH (n)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(to_entity)
                    WHERE to_entity.case_id = $case_id AND NOT to_entity:Document AND NOT to_entity:Case
                    OPTIONAL MATCH (from_entity)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(n)
                    WHERE from_entity.case_id = $case_id AND NOT from_entity:Document AND NOT from_entity:Case
                    OPTIONAL MATCH (n)-[:RECEIVED_FROM]->(rf_entity)
                    WHERE rf_entity.case_id = $case_id AND NOT rf_entity:Document AND NOT rf_entity:Case
                    OPTIONAL MATCH (n)<-[:MADE_PAYMENT|INITIATED]-(initiator)
                    WHERE initiator.case_id = $case_id AND NOT initiator:Document AND NOT initiator:Case
                    RETURN n.key AS key,
                        collect(DISTINCT to_entity.key)[0] AS rel_to_key,
                        collect(DISTINCT to_entity.name)[0] AS rel_to_name,
                        collect(DISTINCT from_entity.key)[0] AS rel_from_key,
                        collect(DISTINCT from_entity.name)[0] AS rel_from_name,
                        collect(DISTINCT rf_entity.key)[0] AS rf_key,
                        collect(DISTINCT rf_entity.name)[0] AS rf_name,
                        collect(DISTINCT initiator.key)[0] AS initiator_key,
                        collect(DISTINCT initiator.name)[0] AS initiator_name
                """
                rel_result = session.run(rel_query, keys=needs_rel_lookup, case_id=case_id)
                txn_by_key = {t["key"]: t for t in transactions}
                for r in rel_result:
                    txn = txn_by_key.get(r["key"])
                    if not txn:
                        continue
                    if not txn["from_entity"]:
                        fk = r["rel_from_key"] or r["initiator_key"]
                        fn = r["rel_from_name"] or r["initiator_name"]
                        if fk or fn:
                            txn["from_entity"] = {"key": fk, "name": fn}
                    if not txn["to_entity"]:
                        tk = r["rel_to_key"] or r["rf_key"]
                        tn = r["rel_to_name"] or r["rf_name"]
                        if tk or tn:
                            txn["to_entity"] = {"key": tk, "name": tn}

            # ═══════════════════════════════════════════════════════════
            # Query C: Entity flow + Query D: Charts
            # — skipped when skip_aggregations=True (sort/page only)
            # ═══════════════════════════════════════════════════════════
            from_entities = None
            to_entities = None
            volume_data = None
            category_breakdown = None

            if not skip_aggregations:
                logger.info("[FinQuery] Phase C: Entity flow aggregation")
                params_c = {"case_id": case_id}
                # Build WHERE without entity filter (base-filtered set)
                base_filter_kw = dict(
                    types=types, categories=categories,
                    start_date=start_date, end_date=end_date,
                    search=search, search_header=search_header,
                    from_entity_keys=None, to_entity_keys=None,
                )
                where_c = self._build_financial_where(params_c, **base_filter_kw)

                # From entities — cross-constrained by to_entity_keys
                from_cross = ""
                if to_entity_keys:
                    params_c["cross_to_keys"] = to_entity_keys
                    from_cross = "AND (coalesce(n.to_entity_key, n.to_entity_name) IN $cross_to_keys)"

                from_entity_query = f"""
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    {where_c}
                    AND (n.from_entity_key IS NOT NULL OR n.from_entity_name IS NOT NULL)
                    {from_cross}
                    WITH coalesce(n.from_entity_key, n.from_entity_name) AS ekey,
                         n.from_entity_name AS ename,
                         toFloat(replace(replace(replace(replace(
                           trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS rawAmt
                    WITH ekey, ename, CASE WHEN rawAmt IS NOT NULL AND rawAmt = rawAmt THEN rawAmt ELSE 0 END AS amt
                    RETURN ekey AS key,
                           collect(DISTINCT ename)[0] AS name,
                           count(*) AS count,
                           sum(abs(amt)) AS totalAmount
                    ORDER BY totalAmount DESC
                """
                from_entities = [
                    {"key": r["key"], "name": r["name"], "count": r["count"], "totalAmount": safe_float(r["totalAmount"])}
                    for r in session.run(from_entity_query, **params_c)
                ]

                # To entities — cross-constrained by from_entity_keys
                params_c2 = {"case_id": case_id}
                where_c2 = self._build_financial_where(params_c2, **base_filter_kw)
                to_cross = ""
                if from_entity_keys:
                    params_c2["cross_from_keys"] = from_entity_keys
                    to_cross = "AND (coalesce(n.from_entity_key, n.from_entity_name) IN $cross_from_keys)"

                to_entity_query = f"""
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    {where_c2}
                    AND (n.to_entity_key IS NOT NULL OR n.to_entity_name IS NOT NULL)
                    {to_cross}
                    WITH coalesce(n.to_entity_key, n.to_entity_name) AS ekey,
                         n.to_entity_name AS ename,
                         toFloat(replace(replace(replace(replace(
                           trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS rawAmt
                    WITH ekey, ename, CASE WHEN rawAmt IS NOT NULL AND rawAmt = rawAmt THEN rawAmt ELSE 0 END AS amt
                    RETURN ekey AS key,
                           collect(DISTINCT ename)[0] AS name,
                           count(*) AS count,
                           sum(abs(amt)) AS totalAmount
                    ORDER BY totalAmount DESC
                """
                to_entities = [
                    {"key": r["key"], "name": r["name"], "count": r["count"], "totalAmount": safe_float(r["totalAmount"])}
                    for r in session.run(to_entity_query, **params_c2)
                ]

                # Volume-over-time + category breakdown
                logger.info("[FinQuery] Phase D: Charts data")
                params_d = {"case_id": case_id}
                where_d = self._build_financial_where(params_d, **filter_kw)

                charts_query = f"""
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    {where_d}
                    WITH n.date AS date,
                         coalesce(n.financial_category, 'Uncategorized') AS category,
                         toFloat(replace(replace(replace(replace(
                           trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS rawAmt
                    WITH date, category, CASE WHEN rawAmt IS NOT NULL AND rawAmt = rawAmt THEN rawAmt ELSE 0 END AS amt
                    RETURN date, category,
                           sum(abs(amt)) AS total_amount,
                           count(*) AS count
                    ORDER BY date ASC, category ASC
                """
                volume_data = [
                    {"date": r["date"], "category": r["category"],
                     "total_amount": safe_float(r["total_amount"]), "count": r["count"]}
                    for r in session.run(charts_query, **params_d)
                ]

                # Category breakdown (aggregated from same filtered set)
                params_e = {"case_id": case_id}
                where_e = self._build_financial_where(params_e, **filter_kw)
                cat_query = f"""
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    {where_e}
                    WITH coalesce(n.financial_category, 'Uncategorized') AS category,
                         toFloat(replace(replace(replace(replace(
                           trim(toString(n.amount)), '$', ''), ',', ''), '€', ''), '£', '')) AS rawAmt
                    WITH category, CASE WHEN rawAmt IS NOT NULL AND rawAmt = rawAmt THEN rawAmt ELSE 0 END AS amt
                    RETURN category, count(*) AS count, sum(abs(amt)) AS amount
                    ORDER BY amount DESC
                """
                category_breakdown = {
                    r["category"]: {"count": r["count"], "amount": safe_float(r["amount"])}
                    for r in session.run(cat_query, **params_e)
                }

            logger.info("[FinQuery] Complete: %d txns, %d total, skip_agg=%s", len(transactions), total, skip_aggregations)

            return {
                "transactions": transactions,
                "total": total,
                "summary": summary,
                "from_entities": from_entities,
                "to_entities": to_entities,
                "volume_data": volume_data,
                "category_breakdown": category_breakdown,
            }

    def get_financial_transaction_types(self, case_id: str) -> List[str]:
        """Return all distinct transaction types (node labels) for a case."""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (n {case_id: $case_id}) WHERE n.amount IS NOT NULL "
                "RETURN DISTINCT labels(n)[0] AS type ORDER BY type",
                case_id=case_id,
            )
            return [r["type"] for r in result]

    def get_financial_entities(self, case_id: str) -> List[Dict]:
        """Return all non-transaction entities in a case for from/to entity pickers."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE NOT n:Document AND NOT n:Case
                  AND n.amount IS NULL
                  AND n.name IS NOT NULL
                RETURN DISTINCT n.key AS key, n.name AS name, labels(n)[0] AS type
                ORDER BY n.name
                """,
                case_id=case_id,
            )
            return [{"key": r["key"], "name": r["name"], "type": r["type"]} for r in result]

    def get_financial_summary(self, case_id: str, entity_key: str = None) -> Dict:
        """
        Get aggregated financial summary stats for a case.

        Args:
            case_id: REQUIRED - Case ID
            entity_key: Optional - If provided, compute inflows/outflows relative to this entity

        Returns:
            Dict with overview metrics (no entity) or entity-relative inflow/outflow metrics
        """
        with self._driver.session() as session:
            if entity_key:
                # Entity-relative mode: classify by relationship direction
                query = """
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    WITH n, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                    OPTIONAL MATCH (n)-[:FROM_ENTITY]->(fe) WHERE fe.case_id = $case_id
                    OPTIONAL MATCH (n)-[:TO_ENTITY]->(te) WHERE te.case_id = $case_id
                    OPTIONAL MATCH (n)<-[:MANUAL_FROM]-(mf) WHERE mf.case_id = $case_id
                    OPTIONAL MATCH (n)<-[:MANUAL_TO]-(mt) WHERE mt.case_id = $case_id
                    WITH n, amt,
                         coalesce(mf.key, fe.key) AS from_key,
                         coalesce(mt.key, te.key) AS to_key
                    WHERE from_key = $entity_key OR to_key = $entity_key
                    RETURN
                        count(n) AS transaction_count,
                        sum(CASE WHEN to_key = $entity_key THEN abs(amt) ELSE 0 END) AS total_inflows,
                        sum(CASE WHEN from_key = $entity_key THEN abs(amt) ELSE 0 END) AS total_outflows
                """
                record = session.run(query, case_id=case_id, entity_key=entity_key).single()
                if not record or record["transaction_count"] == 0:
                    return {"transaction_count": 0, "total_inflows": 0, "total_outflows": 0, "net_flow": 0}
                inflows = safe_float(record["total_inflows"])
                outflows = safe_float(record["total_outflows"])
                return {
                    "transaction_count": record["transaction_count"],
                    "total_inflows": inflows,
                    "total_outflows": outflows,
                    "net_flow": round(inflows - outflows, 2),
                }
            else:
                # Overview mode: total volume without directional classification
                query = """
                    MATCH (n)
                    WHERE n.amount IS NOT NULL AND n.case_id = $case_id
                    WITH n, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                    RETURN
                        count(n) AS transaction_count,
                        sum(abs(amt)) AS total_volume,
                        avg(abs(amt)) AS avg_amount,
                        max(abs(amt)) AS max_amount
                """
                record = session.run(query, case_id=case_id).single()
                if not record or record["transaction_count"] == 0:
                    return {"transaction_count": 0, "total_volume": 0, "avg_amount": 0, "max_amount": 0}
                return {
                    "transaction_count": record["transaction_count"],
                    "total_volume": safe_float(record["total_volume"]),
                    "avg_amount": safe_float(record["avg_amount"]),
                    "max_amount": safe_float(record["max_amount"]),
                }

    def get_financial_volume_over_time(self, case_id: str) -> List[Dict]:
        """
        Get transaction volume grouped by date and category for chart data.

        Args:
            case_id: REQUIRED - Case ID

        Returns:
            List of {date, category, total_amount, count}
        """
        with self._driver.session() as session:
            query = """
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id AND n.date IS NOT NULL
                WITH n.date AS date, coalesce(n.financial_category, 'Uncategorized') AS category, toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amt
                RETURN
                    date,
                    category,
                    sum(abs(amt)) AS total_amount,
                    count(*) AS count
                ORDER BY date ASC, category ASC
            """
            result = session.run(query, case_id=case_id)
            return [
                {
                    "date": record["date"],
                    "category": record["category"],
                    "total_amount": safe_float(record["total_amount"]),
                    "count": record["count"],
                }
                for record in result
            ]

    def update_transaction_category(self, node_key: str, category: str, case_id: str) -> Dict:
        """
        Set the financial_category on a transaction node.

        Args:
            node_key: The node key
            category: Category string to set
            case_id: REQUIRED - Case ID

        Returns:
            Dict with success status
        """
        with self._driver.session() as session:
            query = """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.financial_category = $category
                RETURN n.key AS key
            """
            record = session.run(query, key=node_key, case_id=case_id, category=category).single()
            if not record:
                return {"success": False, "error": "Node not found"}
            return {"success": True, "key": record["key"], "category": category}

    def update_transaction_from_to(
        self,
        node_key: str,
        case_id: str,
        from_key: Optional[str] = None,
        from_name: Optional[str] = None,
        to_key: Optional[str] = None,
        to_name: Optional[str] = None,
    ) -> Dict:
        """
        Set manual from/to entity overrides on a transaction node.

        Args:
            node_key: The node key
            case_id: REQUIRED - Case ID
            from_key: Key of the from entity (or None to clear)
            from_name: Display name of the from entity
            to_key: Key of the to entity (or None to clear)
            to_name: Display name of the to entity

        Returns:
            Dict with success status
        """
        with self._driver.session() as session:
            set_clauses = []
            params = {"key": node_key, "case_id": case_id}

            if from_key is not None or from_name is not None:
                set_clauses.append("n.from_entity_key = $from_key")
                set_clauses.append("n.from_entity_name = $from_name")
                set_clauses.append("n.has_manual_from = true")
                params["from_key"] = from_key
                params["from_name"] = from_name
            if to_key is not None or to_name is not None:
                set_clauses.append("n.to_entity_key = $to_key")
                set_clauses.append("n.to_entity_name = $to_name")
                set_clauses.append("n.has_manual_to = true")
                params["to_key"] = to_key
                params["to_name"] = to_name

            if not set_clauses:
                return {"success": False, "error": "No from/to data provided"}

            query = f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                SET {', '.join(set_clauses)}
                RETURN n.key AS key
            """
            record = session.run(query, **params).single()
            if not record:
                return {"success": False, "error": "Node not found"}
            return {"success": True, "key": record["key"]}

    def get_financial_categories(self, case_id: str) -> List[Dict]:
        """
        Get all financial categories for a case: predefined + persisted custom + orphaned from transactions.

        Args:
            case_id: REQUIRED - Case ID

        Returns:
            List of dicts with name, color, builtin keys
        """
        predefined = {
            "Uncategorized":      "#94a3b8",
            "Utility":            "#3b82f6",
            "Payroll/Salary":     "#22c55e",
            "Rent/Lease":         "#8b5cf6",
            "Reimbursement":      "#06b6d4",
            "Loan Payment":       "#ef4444",
            "Insurance":          "#f59e0b",
            "Subscription":       "#ec4899",
            "Transfer":           "#14b8a6",
            "Income":             "#10b981",
            "Personal":           "#f97316",
            "Legal/Professional": "#6366f1",
            "Other":              "#6b7280",
        }
        result_categories = [
            {"name": name, "color": color, "builtin": True}
            for name, color in predefined.items()
        ]
        seen_names = set(predefined.keys())

        with self._driver.session() as session:
            # Persisted custom FinancialCategory nodes for this case
            custom_query = """
                MATCH (c:FinancialCategory {case_id: $case_id})
                RETURN c.name AS name, c.color AS color
                ORDER BY c.name
            """
            custom_result = session.run(custom_query, case_id=case_id)
            for record in custom_result:
                name = record["name"]
                if name not in seen_names:
                    result_categories.append({"name": name, "color": record["color"] or "#6b7280", "builtin": False})
                    seen_names.add(name)

            # Orphaned categories on transaction nodes (no FinancialCategory node)
            orphan_query = """
                MATCH (n)
                WHERE n.amount IS NOT NULL AND n.case_id = $case_id AND n.financial_category IS NOT NULL
                RETURN DISTINCT n.financial_category AS category
            """
            orphan_result = session.run(orphan_query, case_id=case_id)
            for record in orphan_result:
                name = record["category"]
                if name not in seen_names:
                    result_categories.append({"name": name, "color": "#6b7280", "builtin": False})
                    seen_names.add(name)

        return result_categories

    def create_financial_category(self, name: str, color: str, case_id: str) -> Dict:
        """
        Create or update a custom FinancialCategory node for a case.

        Args:
            name: Category name
            color: Hex color string
            case_id: REQUIRED - Case ID

        Returns:
            Dict with success, name, color
        """
        with self._driver.session() as session:
            query = """
                MERGE (c:FinancialCategory {name: $name, case_id: $case_id})
                ON CREATE SET c.color = $color, c.created_at = datetime()
                ON MATCH SET c.color = $color
                RETURN c.name AS name, c.color AS color
            """
            record = session.run(query, name=name, color=color, case_id=case_id).single()
            if not record:
                return {"success": False, "error": "Failed to create category"}
            return {"success": True, "name": record["name"], "color": record["color"]}

    def update_transaction_details(
        self,
        node_key: str,
        case_id: str,
        purpose: Optional[str] = None,
        counterparty_details: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict:
        """
        Set purpose, counterparty_details, and/or notes on a transaction node.

        Args:
            node_key: The node key
            case_id: REQUIRED - Case ID
            purpose: Optional purpose text
            counterparty_details: Optional counterparty details text
            notes: Optional investigation notes

        Returns:
            Dict with success status
        """
        with self._driver.session() as session:
            set_clauses = []
            params = {"key": node_key, "case_id": case_id}

            if purpose is not None:
                set_clauses.append("n.purpose = $purpose")
                params["purpose"] = purpose
            if counterparty_details is not None:
                set_clauses.append("n.counterparty_details = $counterparty_details")
                params["counterparty_details"] = counterparty_details
            if notes is not None:
                set_clauses.append("n.notes = $notes")
                params["notes"] = notes

            if not set_clauses:
                return {"success": False, "error": "No details provided"}

            query = f"""
                MATCH (n {{key: $key, case_id: $case_id}})
                SET {', '.join(set_clauses)}
                RETURN n.key AS key
            """
            record = session.run(query, **params).single()
            if not record:
                return {"success": False, "error": "Node not found"}
            return {"success": True, "key": record["key"]}

    def batch_update_from_to(
        self,
        node_keys: List[str],
        case_id: str,
        from_key: Optional[str] = None,
        from_name: Optional[str] = None,
        to_key: Optional[str] = None,
        to_name: Optional[str] = None,
    ) -> Dict:
        """
        Set from/to entity on multiple transaction nodes at once.

        Args:
            node_keys: List of node keys to update
            case_id: REQUIRED - Case ID
            from_key: Key of the from entity
            from_name: Display name of the from entity
            to_key: Key of the to entity
            to_name: Display name of the to entity

        Returns:
            Dict with success count
        """
        results = []
        for key in node_keys:
            result = self.update_transaction_from_to(
                node_key=key,
                case_id=case_id,
                from_key=from_key,
                from_name=from_name,
                to_key=to_key,
                to_name=to_name,
            )
            results.append(result)
        success_count = sum(1 for r in results if r.get("success"))
        return {"success": True, "updated": success_count, "total": len(node_keys)}


    def update_entity_location(self, node_key: str, case_id: str, location_name: str, latitude: float, longitude: float) -> Dict:
        """Update the location properties of an entity node."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.location_name = $location_name,
                    n.location_formatted = $location_name,
                    n.latitude = $latitude,
                    n.longitude = $longitude
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
                location_name=location_name,
                latitude=latitude,
                longitude=longitude,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")
            return {
                "success": True,
                "node": {"key": record["key"], "name": record["name"], "type": record["type"]},
                "location": {"location_name": location_name, "latitude": latitude, "longitude": longitude},
            }

    def remove_entity_location(self, node_key: str, case_id: str) -> Dict:
        """Remove location properties from an entity node (node stays in graph)."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                REMOVE n.latitude, n.longitude, n.location_name, n.location_formatted,
                       n.location_raw, n.geocoding_confidence
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")
            return {
                "success": True,
                "node": {"key": record["key"], "name": record["name"], "type": record["type"]},
            }

    def get_case_entity_summary(self, case_id: str) -> list:
        """Get a structured summary of all key entities in a case."""
        with self._driver.session() as session:
            query = """
                MATCH (n {case_id: $case_id})
                WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
                  AND n.name IS NOT NULL
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.summary AS summary,
                       n.verified_facts AS verified_facts,
                       n.ai_insights AS ai_insights
                ORDER BY labels(n)[0], n.name
            """
            result = session.run(query, case_id=case_id)
            entities = []
            for record in result:
                vf = record["verified_facts"]
                ai = record["ai_insights"]
                if isinstance(vf, str):
                    try:
                        import json
                        vf = json.loads(vf)
                    except Exception:
                        vf = []
                if isinstance(ai, str):
                    try:
                        import json
                        ai = json.loads(ai)
                    except Exception:
                        ai = []
                entities.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "facts_count": len(vf) if isinstance(vf, list) else 0,
                    "insights_count": len(ai) if isinstance(ai, list) else 0,
                })
            return entities

    def update_transaction_amount(self, node_key: str, case_id: str, new_amount: float, correction_reason: str) -> Dict:
        """Update a transaction amount, preserving the original value for audit trail."""
        with self._driver.session() as session:
            # Single query: conditionally preserve original_amount on first correction
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.original_amount = CASE WHEN n.original_amount IS NULL THEN n.amount ELSE n.original_amount END,
                    n.amount = $new_amount,
                    n.amount_corrected = true,
                    n.correction_reason = $correction_reason
                RETURN n.key AS key, n.amount AS amount, n.original_amount AS original_amount
                """,
                key=node_key,
                case_id=case_id,
                new_amount=new_amount,
                correction_reason=correction_reason,
            ).single()
            if not result:
                raise ValueError(f"Node not found: {node_key} in case {case_id}")
            return {
                "success": True,
                "key": result["key"],
                "amount": result["amount"],
                "original_amount": result["original_amount"],
            }


    def link_sub_transaction(self, parent_key: str, child_key: str, case_id: str) -> Dict:
        """Link a child transaction to a parent transaction."""
        with self._driver.session() as session:
            check = session.run(
                """
                MATCH (parent {key: $parent_key, case_id: $case_id})
                MATCH (child {key: $child_key, case_id: $case_id})
                RETURN parent.key AS pk, child.key AS ck
                """,
                parent_key=parent_key, child_key=child_key, case_id=case_id,
            ).single()
            if not check:
                raise ValueError(f"One or both nodes not found in case {case_id}")

            session.run(
                """
                MATCH (parent {key: $parent_key, case_id: $case_id})
                MATCH (child {key: $child_key, case_id: $case_id})
                MERGE (child)-[:PART_OF]->(parent)
                SET child.parent_transaction_key = $parent_key,
                    parent.is_parent = true
                """,
                parent_key=parent_key, child_key=child_key, case_id=case_id,
            )
            return {"success": True, "parent_key": parent_key, "child_key": child_key}

    def unlink_sub_transaction(self, child_key: str, case_id: str) -> Dict:
        """Remove a child transaction from its parent group."""
        with self._driver.session() as session:
            parent_result = session.run(
                """
                MATCH (child {key: $child_key, case_id: $case_id})-[:PART_OF]->(parent)
                RETURN parent.key AS parent_key
                """,
                child_key=child_key, case_id=case_id,
            ).single()

            if not parent_result:
                raise ValueError(f"Child node {child_key} has no parent relationship")

            parent_key = parent_result["parent_key"]

            session.run(
                """
                MATCH (child {key: $child_key, case_id: $case_id})-[r:PART_OF]->(parent)
                DELETE r
                REMOVE child.parent_transaction_key
                """,
                child_key=child_key, case_id=case_id,
            )

            remaining = session.run(
                """
                MATCH (child)-[:PART_OF]->(parent {key: $parent_key, case_id: $case_id})
                RETURN count(child) AS count
                """,
                parent_key=parent_key, case_id=case_id,
            ).single()

            if remaining and remaining["count"] == 0:
                session.run(
                    "MATCH (n {key: $key, case_id: $case_id}) SET n.is_parent = false",
                    key=parent_key, case_id=case_id,
                )

            return {"success": True, "child_key": child_key, "parent_key": parent_key}

    def get_transaction_children(self, parent_key: str, case_id: str) -> list:
        """Get all child sub-transactions for a parent."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (child)-[:PART_OF]->(parent {key: $parent_key, case_id: $case_id})
                RETURN child.key AS key, child.name AS name, child.date AS date,
                       child.time AS time, child.amount AS amount, child.type AS type,
                       child.financial_category AS financial_category,
                       child.from_entity_name AS from_name, child.to_entity_name AS to_name,
                       child.purpose AS purpose, child.notes AS notes,
                       child.amount_corrected AS amount_corrected,
                       child.original_amount AS original_amount,
                       child.correction_reason AS correction_reason
                ORDER BY child.date
                """,
                parent_key=parent_key, case_id=case_id,
            )
            children = []
            for record in result:
                children.append({k: record[k] for k in record.keys()})
            return children

    def batch_update_entities(self, updates: list, case_id: str) -> int:
        """Batch update properties on multiple entity nodes.

        Args:
            updates: List of dicts with {key, property, value}
            case_id: Case ID for security validation
        Returns:
            Number of successfully updated entities
        """
        allowed_properties = {"name", "summary", "notes", "type", "description"}
        with self._driver.session() as session:
            count = 0
            for update in updates[:500]:
                prop = update.get("property")
                if prop not in allowed_properties:
                    continue
                result = session.run(
                    f"MATCH (n {{key: $key, case_id: $case_id}}) SET n.`{prop}` = $value RETURN n.key AS key",
                    key=update["key"],
                    case_id=case_id,
                    value=update["value"],
                )
                if result.single():
                    count += 1
            return count

    def get_entities_for_insights(self, case_id: str, max_entities: int = 10) -> list:
        """Get top entities with verified facts for insight generation."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE (n:Person OR n:Company OR n:Organisation OR n:Bank OR n:BankAccount)
                  AND n.name IS NOT NULL
                  AND n.verified_facts IS NOT NULL
                OPTIONAL MATCH (n)-[r]-(related)
                WHERE NOT related:Document AND related.case_id = $case_id
                WITH n, collect(DISTINCT {
                    name: related.name,
                    type: labels(related)[0],
                    relationship: type(r)
                })[..15] AS related_entities
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.summary AS summary, n.verified_facts AS verified_facts,
                       n.ai_insights AS ai_insights, related_entities
                ORDER BY size(COALESCE(n.verified_facts, '[]')) DESC
                LIMIT $max_entities
                """,
                case_id=case_id, max_entities=max_entities,
            )
            entities = []
            for record in result:
                entities.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "verified_facts": parse_json_field(record["verified_facts"]) or [],
                    "ai_insights": parse_json_field(record["ai_insights"]) or [],
                    "related_entities": [r for r in record["related_entities"] if r.get("name")],
                })
            return entities

    def save_entity_insights(self, node_key: str, case_id: str, new_insights: list) -> Dict:
        """Append new insights to an entity's ai_insights array."""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (n {key: $key, case_id: $case_id}) RETURN n.ai_insights AS ai_insights",
                key=node_key, case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key}")
            existing = parse_json_field(record["ai_insights"]) or []
            existing.extend(new_insights)
            session.run(
                "MATCH (n {key: $key, case_id: $case_id}) SET n.ai_insights = $insights",
                key=node_key, case_id=case_id, insights=json.dumps(existing),
            )
            return {"success": True, "total_insights": len(existing)}

    def reject_entity_insight(self, node_key: str, case_id: str, insight_index: int) -> Dict:
        """Remove an insight from the ai_insights array."""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (n {key: $key, case_id: $case_id}) RETURN n.ai_insights AS ai_insights",
                key=node_key, case_id=case_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key}")
            insights = parse_json_field(record["ai_insights"]) or []
            if insight_index < 0 or insight_index >= len(insights):
                raise ValueError(f"Invalid insight index: {insight_index}")
            removed = insights.pop(insight_index)
            session.run(
                "MATCH (n {key: $key, case_id: $case_id}) SET n.ai_insights = $insights",
                key=node_key, case_id=case_id, insights=json.dumps(insights),
            )
            return {"success": True, "removed": removed, "remaining": len(insights)}

    def get_all_pending_insights(self, case_id: str) -> list:
        """Get all pending insights across all entities in a case."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE n.ai_insights IS NOT NULL AND n.name IS NOT NULL
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.ai_insights AS ai_insights
                ORDER BY n.name
                """,
                case_id=case_id,
            )
            all_insights = []
            for record in result:
                insights = parse_json_field(record["ai_insights"]) or []
                for idx, insight in enumerate(insights):
                    if isinstance(insight, dict) and insight.get("status", "pending") == "pending":
                        all_insights.append({
                            "entity_key": record["key"],
                            "entity_name": record["name"],
                            "entity_type": record["type"],
                            "insight_index": idx,
                            **insight,
                        })
            return all_insights

    # -------------------------------------------------------------------------
    # Geo Rescan helpers
    # -------------------------------------------------------------------------

    def get_all_nodes(self, case_id: str) -> List[Dict]:
        """Return every non-Document node for a case with key properties."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {case_id: $case_id})
                WHERE NOT n:Document
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type,
                       n.latitude AS latitude, n.longitude AS longitude,
                       n.location_raw AS location_raw
                """,
                case_id=case_id,
            )
            return [dict(r) for r in result]

    def update_entity_location_full(
        self,
        node_key: str,
        case_id: str,
        location_raw: str,
        latitude: float,
        longitude: float,
        location_formatted: str,
        geocoding_confidence: str,
    ) -> Dict:
        """Set all location properties on an entity node."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key, case_id: $case_id})
                SET n.location_raw = $location_raw,
                    n.latitude = $latitude,
                    n.longitude = $longitude,
                    n.location_formatted = $location_formatted,
                    n.location_name = $location_formatted,
                    n.geocoding_status = 'success',
                    n.geocoding_confidence = $geocoding_confidence
                RETURN n.key AS key, n.name AS name, labels(n)[0] AS type
                """,
                key=node_key,
                case_id=case_id,
                location_raw=location_raw,
                latitude=latitude,
                longitude=longitude,
                location_formatted=location_formatted,
                geocoding_confidence=geocoding_confidence,
            )
            record = result.single()
            return dict(record) if record else {}

    def create_location_node(
        self,
        case_id: str,
        name: str,
        latitude: float,
        longitude: float,
        location_formatted: str,
        geocoding_confidence: str,
        context: str = "",
    ) -> Optional[str]:
        """Create a new Location node in the graph and return its key."""
        import uuid
        node_key = f"loc_{uuid.uuid4().hex[:12]}"
        with self._driver.session() as session:
            result = session.run(
                """
                CREATE (n:Location {
                    key: $key,
                    name: $name,
                    case_id: $case_id,
                    latitude: $latitude,
                    longitude: $longitude,
                    location_raw: $name,
                    location_formatted: $location_formatted,
                    location_name: $location_formatted,
                    geocoding_status: 'success',
                    geocoding_confidence: $geocoding_confidence,
                    summary: $context,
                    source: 'geo_rescan'
                })
                RETURN n.key AS key
                """,
                key=node_key,
                name=name,
                case_id=case_id,
                latitude=latitude,
                longitude=longitude,
                location_formatted=location_formatted,
                geocoding_confidence=geocoding_confidence,
                context=context,
            )
            record = result.single()
            return record["key"] if record else None

    def ensure_located_at_relationship(
        self,
        source_key: str,
        target_key: str,
        case_id: str,
        context: str = "",
    ) -> bool:
        """Create a LOCATED_AT relationship if it doesn't exist. Returns True if created."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (a {key: $source_key, case_id: $case_id})
                MATCH (b {key: $target_key, case_id: $case_id})
                WHERE NOT (a)-[:LOCATED_AT]->(b)
                CREATE (a)-[r:LOCATED_AT {context: $context, source: 'geo_rescan'}]->(b)
                RETURN type(r) AS rel_type
                """,
                source_key=source_key,
                target_key=target_key,
                case_id=case_id,
                context=context,
            )
            return result.single() is not None

    # -------------------------------------------------------------------------
    # Cellebrite Multi-Phone Analytics
    # -------------------------------------------------------------------------

    def get_cellebrite_reports(self, case_id: str) -> list:
        """Get all PhoneReport nodes for a case with owner info and stats."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id})
                OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person)

                // Count related nodes by label
                OPTIONAL MATCH (contact:Person {case_id: $case_id, cellebrite_report_key: r.key})
                  WHERE contact.source_type = 'cellebrite'
                    AND contact <> owner
                WITH r, owner, count(DISTINCT contact) AS contact_count

                OPTIONAL MATCH (call:PhoneCall {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, count(DISTINCT call) AS call_count

                OPTIONAL MATCH (msg:Communication {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, call_count, count(DISTINCT msg) AS message_count

                OPTIONAL MATCH (loc:Location {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, call_count, message_count, count(DISTINCT loc) AS location_count

                OPTIONAL MATCH (email:Email {case_id: $case_id, cellebrite_report_key: r.key})
                WITH r, owner, contact_count, call_count, message_count, location_count, count(DISTINCT email) AS email_count

                RETURN r, owner,
                       contact_count, call_count, message_count, location_count, email_count
                ORDER BY r.name
                """,
                case_id=case_id,
            )

            reports = []
            for record in result:
                r = dict(record["r"])
                owner = dict(record["owner"]) if record["owner"] else None
                reports.append({
                    "report_key": r.get("key", ""),
                    "report_name": r.get("name", ""),
                    "device_model": r.get("device_model", "Unknown Device"),
                    "phone_numbers": r.get("phone_numbers", ""),
                    "imei": r.get("imei", ""),
                    "extraction_type": r.get("extraction_type", ""),
                    "extraction_date": r.get("extraction_start", ""),
                    "examiner": r.get("examiner", ""),
                    "case_number": r.get("case_number", ""),
                    "evidence_number": r.get("evidence_number", ""),
                    "phone_owner_name": owner.get("name", "") if owner else "",
                    "phone_owner_key": owner.get("key", "") if owner else "",
                    "stats": {
                        "contacts": record["contact_count"],
                        "calls": record["call_count"],
                        "messages": record["message_count"],
                        "locations": record["location_count"],
                        "emails": record["email_count"],
                    },
                })
            return reports

    def get_cellebrite_cross_phone_graph(self, case_id: str) -> dict:
        """
        Get cross-phone graph showing shared entities across devices.

        Returns nodes and links in react-force-graph-2d format.
        """
        nodes = []
        links = []
        seen_nodes = set()

        with self._driver.session() as session:
            # 1. Get PhoneReport nodes
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id})
                OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person)
                RETURN r, owner
                """,
                case_id=case_id,
            )
            report_keys = []
            for record in result:
                r = dict(record["r"])
                rkey = r.get("key", "")
                report_keys.append(rkey)
                node_id = f"report-{rkey}"
                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    owner = dict(record["owner"]) if record["owner"] else None
                    nodes.append({
                        "id": node_id,
                        "name": r.get("device_model", "Unknown Device"),
                        "type": "PhoneReport",
                        "report_key": rkey,
                        "phone_owner": owner.get("name", "") if owner else "",
                        "val": 8,
                    })
                    # Link report to its owner
                    if owner:
                        owner_id = f"person-{owner.get('key', '')}"
                        links.append({
                            "source": node_id,
                            "target": owner_id,
                            "label": "BELONGS_TO",
                        })

            if len(report_keys) < 1:
                return {"nodes": nodes, "links": links}

            # 2. Find persons connected to PhoneReport nodes via relationships
            result = session.run(
                """
                MATCH (r:PhoneReport {case_id: $case_id})
                MATCH (p:Person {case_id: $case_id, source_type: 'cellebrite'})
                WHERE p.cellebrite_report_key = r.key
                WITH p, collect(DISTINCT r.key) AS device_keys,
                     count(DISTINCT r) AS device_count
                // Get communication counts
                OPTIONAL MATCH (p)-[rel]->()
                WHERE type(rel) IN ['CALLED', 'SENT_MESSAGE', 'EMAILED', 'PARTICIPATED_IN']
                WITH p, device_keys, device_count, count(rel) AS comm_count
                ORDER BY device_count DESC, comm_count DESC
                LIMIT 200
                RETURN p, device_keys, device_count, comm_count
                """,
                case_id=case_id,
            )

            for record in result:
                p = dict(record["p"])
                pkey = p.get("key", "")
                node_id = f"person-{pkey}"
                device_keys = list(record["device_keys"])
                device_count = record["device_count"]

                if node_id not in seen_nodes:
                    seen_nodes.add(node_id)
                    nodes.append({
                        "id": node_id,
                        "name": p.get("name", pkey),
                        "type": "Person",
                        "phone": p.get("phone", ""),
                        "device_count": device_count,
                        "shared": device_count > 1,
                        "comm_count": record["comm_count"],
                        "val": 3 + min(record["comm_count"], 10),
                    })

                # Link person to each device's report
                for dk in device_keys:
                    report_node_id = f"report-{dk}"
                    if report_node_id in seen_nodes:
                        links.append({
                            "source": report_node_id,
                            "target": node_id,
                            "label": "CONTAINS_CONTACT",
                        })

            # 3. Find direct communication links between persons
            result = session.run(
                """
                MATCH (a:Person {case_id: $case_id, source_type: 'cellebrite'})
                      -[rel]->(comm)
                      -[rel2]->(b:Person {case_id: $case_id})
                WHERE type(rel) IN ['CALLED', 'SENT_MESSAGE', 'EMAILED']
                  AND type(rel2) IN ['CALLED_TO', 'SENT_TO']
                  AND a <> b
                WITH a.key AS src, b.key AS tgt, type(rel) AS rel_type, count(*) AS cnt
                WHERE cnt >= 2
                RETURN src, tgt, rel_type, cnt
                ORDER BY cnt DESC
                LIMIT 300
                """,
                case_id=case_id,
            )

            for record in result:
                src_id = f"person-{record['src']}"
                tgt_id = f"person-{record['tgt']}"
                if src_id in seen_nodes and tgt_id in seen_nodes:
                    links.append({
                        "source": src_id,
                        "target": tgt_id,
                        "label": record["rel_type"],
                        "count": record["cnt"],
                    })

        return {"nodes": nodes, "links": links}

    def get_cellebrite_timeline(
        self,
        case_id: str,
        report_keys: list = None,
        start_date: str = None,
        end_date: str = None,
        event_types: list = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict:
        """Get chronological events across all phone reports."""
        # Build WHERE clause fragments
        where_parts = ["n.case_id = $case_id"]
        params = {"case_id": case_id, "limit": limit, "skip_count": offset}

        if report_keys:
            where_parts.append("n.cellebrite_report_key IN $report_keys")
            params["report_keys"] = report_keys

        if start_date:
            where_parts.append("n.timestamp >= $start_date")
            params["start_date"] = start_date

        if end_date:
            where_parts.append("n.timestamp <= $end_date")
            params["end_date"] = end_date

        where_clause = " AND ".join(where_parts)

        # Build UNION query across event types
        union_parts = []
        type_map = {
            "call": ("PhoneCall", "phone_number_to", "CALLED"),
            "message": ("Communication", "body", "SENT_MESSAGE"),
            "location": ("Location", "name", "WAS_AT"),
            "email": ("Email", "subject", "EMAILED"),
        }

        active_types = event_types if event_types else list(type_map.keys())

        for etype in active_types:
            if etype not in type_map:
                continue
            label, summary_field, _ = type_map[etype]
            union_parts.append(f"""
                MATCH (n:{label})
                WHERE {where_clause}
                  AND n.timestamp IS NOT NULL
                  AND n.source_type = 'cellebrite'
                RETURN n.timestamp AS timestamp,
                       '{etype}' AS event_type,
                       coalesce(n.{summary_field}, '') AS summary,
                       n.cellebrite_report_key AS report_key,
                       n.key AS node_key
            """)

        if not union_parts:
            return {"events": [], "total_estimate": 0}

        query = " UNION ALL ".join(union_parts)
        query += """
            ORDER BY timestamp
            SKIP $skip_count
            LIMIT $limit
        """

        with self._driver.session() as session:
            result = session.run(query, params)
            events = []
            for record in result:
                events.append({
                    "timestamp": record["timestamp"],
                    "event_type": record["event_type"],
                    "summary": record["summary"],
                    "report_key": record["report_key"],
                    "node_key": record["node_key"],
                })

        return {"events": events, "total_estimate": len(events)}

    def get_cellebrite_communication_network(self, case_id: str) -> dict:
        """Get contact frequency analysis and shared contacts across devices."""
        with self._driver.session() as session:
            # Get all persons with communication counts per report
            result = session.run(
                """
                MATCH (p:Person {case_id: $case_id, source_type: 'cellebrite'})
                OPTIONAL MATCH (p)-[:CALLED]->(call:PhoneCall {case_id: $case_id})
                WITH p, count(DISTINCT call) AS calls_made
                OPTIONAL MATCH ()-[:CALLED]->(call2:PhoneCall {case_id: $case_id})-[:CALLED_TO]->(p)
                WITH p, calls_made, count(DISTINCT call2) AS calls_received
                OPTIONAL MATCH (p)-[:SENT_MESSAGE]->(msg:Communication {case_id: $case_id})
                WITH p, calls_made, calls_received, count(DISTINCT msg) AS messages_sent
                OPTIONAL MATCH (p)-[:EMAILED]->(e:Email {case_id: $case_id})
                WITH p, calls_made, calls_received, messages_sent, count(DISTINCT e) AS emails_sent

                // Find which devices this person appears on
                WITH p, calls_made, calls_received, messages_sent, emails_sent,
                     CASE WHEN p.cellebrite_report_key IS NOT NULL
                          THEN [p.cellebrite_report_key]
                          ELSE [] END AS device_keys

                WHERE calls_made + calls_received + messages_sent + emails_sent > 0

                RETURN p.key AS person_key,
                       p.name AS name,
                       p.phone AS phone,
                       calls_made + calls_received AS call_count,
                       messages_sent AS message_count,
                       emails_sent AS email_count,
                       device_keys
                ORDER BY calls_made + calls_received + messages_sent + emails_sent DESC
                LIMIT 500
                """,
                case_id=case_id,
            )

            contacts = []
            shared_contacts = []
            for record in result:
                contact = {
                    "person_key": record["person_key"],
                    "name": record["name"] or record["person_key"],
                    "phone": record["phone"] or "",
                    "call_count": record["call_count"],
                    "message_count": record["message_count"],
                    "email_count": record["email_count"],
                    "devices": list(record["device_keys"]),
                }
                contacts.append(contact)

            # Find contacts appearing on multiple devices
            result = session.run(
                """
                MATCH (p:Person {case_id: $case_id, source_type: 'cellebrite'})
                WITH p, p.cellebrite_report_key AS rk
                WHERE rk IS NOT NULL
                WITH p.key AS person_key, p.name AS name, p.phone AS phone,
                     collect(DISTINCT rk) AS device_keys
                WHERE size(device_keys) > 1
                RETURN person_key, name, phone, device_keys
                ORDER BY size(device_keys) DESC, name
                """,
                case_id=case_id,
            )

            for record in result:
                shared_contacts.append({
                    "person_key": record["person_key"],
                    "name": record["name"] or record["person_key"],
                    "phone": record["phone"] or "",
                    "devices": list(record["device_keys"]),
                })

        return {"contacts": contacts, "shared_contacts": shared_contacts}

    # ------------------------------------------------------------------
    # Cellebrite Communication Center (Phase 3) queries
    # ------------------------------------------------------------------

    def get_cellebrite_comms_entities(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
    ) -> list:
        """
        Get all distinct Person entities for the Comms Center filter panels.

        Deduplicated by Person.key across devices. Returns counts of calls,
        messages, emails (as sender and as recipient), device membership.
        """
        params: Dict[str, Any] = {"case_id": case_id}
        report_filter = ""
        if report_keys:
            report_filter = "AND p.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        with self._driver.session() as session:
            query = f"""
                MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE p.key IS NOT NULL {report_filter}
                WITH p.key AS key,
                     collect(DISTINCT p) AS persons,
                     collect(DISTINCT p.cellebrite_report_key) AS device_keys,
                     collect(DISTINCT p.name) AS names,
                     collect(DISTINCT p.phone_numbers) AS phone_lists,
                     max(toString(coalesce(p.is_phone_owner, false))) AS is_owner_str

                // Count comms involving any of these person-instances
                UNWIND persons AS person
                OPTIONAL MATCH (person)-[:CALLED]->(c:PhoneCall)
                  WHERE (size($report_keys_list) = 0 OR c.cellebrite_report_key IN $report_keys_list)
                WITH key, device_keys, names, phone_lists, is_owner_str, persons,
                     collect(DISTINCT c.id) AS calls_out_ids

                UNWIND persons AS person
                OPTIONAL MATCH (c2:PhoneCall)-[:CALLED_TO]->(person)
                  WHERE (size($report_keys_list) = 0 OR c2.cellebrite_report_key IN $report_keys_list)
                WITH key, device_keys, names, phone_lists, is_owner_str, persons,
                     calls_out_ids, collect(DISTINCT c2.id) AS calls_in_ids

                UNWIND persons AS person
                OPTIONAL MATCH (person)-[:SENT_MESSAGE]->(m:Communication)
                  WHERE m.body IS NOT NULL
                    AND (size($report_keys_list) = 0 OR m.cellebrite_report_key IN $report_keys_list)
                WITH key, device_keys, names, phone_lists, is_owner_str,
                     calls_out_ids, calls_in_ids, persons,
                     collect(DISTINCT m.id) AS msgs_sent_ids

                UNWIND persons AS person
                OPTIONAL MATCH (person)-[:PARTICIPATED_IN]->(chat:Communication)
                  WHERE chat.chat_id IS NOT NULL
                    AND (size($report_keys_list) = 0 OR chat.cellebrite_report_key IN $report_keys_list)
                OPTIONAL MATCH (msg:Communication)-[:PART_OF]->(chat)
                  WHERE msg.body IS NOT NULL
                WITH key, device_keys, names, phone_lists, is_owner_str,
                     calls_out_ids, calls_in_ids, msgs_sent_ids, persons,
                     collect(DISTINCT msg.id) AS msgs_received_ids

                UNWIND persons AS person
                OPTIONAL MATCH (person)-[:EMAILED]->(e1:Email)
                  WHERE (size($report_keys_list) = 0 OR e1.cellebrite_report_key IN $report_keys_list)
                WITH key, device_keys, names, phone_lists, is_owner_str,
                     calls_out_ids, calls_in_ids, msgs_sent_ids, msgs_received_ids, persons,
                     collect(DISTINCT e1.id) AS emails_sent_ids

                UNWIND persons AS person
                OPTIONAL MATCH (e2:Email)-[:SENT_TO]->(person)
                  WHERE (size($report_keys_list) = 0 OR e2.cellebrite_report_key IN $report_keys_list)
                WITH key, device_keys, names, phone_lists, is_owner_str,
                     calls_out_ids, calls_in_ids, msgs_sent_ids, msgs_received_ids,
                     emails_sent_ids, collect(DISTINCT e2.id) AS emails_received_ids

                RETURN key,
                       head(names) AS name,
                       head(phone_lists) AS phone_numbers,
                       is_owner_str = 'true' AS is_owner,
                       device_keys,
                       size(device_keys) AS device_count,
                       size(calls_out_ids) + size(calls_in_ids) AS call_count,
                       size(msgs_sent_ids) + size(msgs_received_ids) AS message_count,
                       size(emails_sent_ids) + size(emails_received_ids) AS email_count,
                       size(calls_out_ids) + size(msgs_sent_ids) + size(emails_sent_ids) AS as_sender_count,
                       size(calls_in_ids) + size(msgs_received_ids) + size(emails_received_ids) AS as_recipient_count
                ORDER BY call_count + message_count + email_count DESC
            """
            params["report_keys_list"] = list(report_keys) if report_keys else []
            result = session.run(query, params)

            entities = []
            for record in result:
                entities.append({
                    "key": record["key"],
                    "name": record["name"] or record["key"],
                    "phone_numbers": record["phone_numbers"] or [],
                    "is_owner": bool(record["is_owner"]),
                    "device_keys": list(record["device_keys"] or []),
                    "device_count": int(record["device_count"] or 0),
                    "call_count": int(record["call_count"] or 0),
                    "message_count": int(record["message_count"] or 0),
                    "email_count": int(record["email_count"] or 0),
                    "as_sender_count": int(record["as_sender_count"] or 0),
                    "as_recipient_count": int(record["as_recipient_count"] or 0),
                })
            return entities

    def get_cellebrite_comms_source_apps(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
    ) -> list:
        """
        Get distinct source_app values (e.g. WhatsApp, Facebook Messenger, SMS, Gmail)
        that exist in the current (optionally report-filtered) universe, with counts.

        Returns: [{source_app, thread_type, count}, ...]  — thread_type is
        'chat' for messages, 'calls' for PhoneCall, 'emails' for Email.
        """
        params: Dict[str, Any] = {"case_id": case_id}
        rk_filter = ""
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        apps: list = []
        with self._driver.session() as session:
            # Messages / chats (Communication with body or chat_id)
            r = session.run(
                f"""
                MATCH (n:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE n.source_app IS NOT NULL
                  AND (n.body IS NOT NULL OR n.chat_id IS NOT NULL)
                  {rk_filter}
                RETURN n.source_app AS app, count(n) AS n
                ORDER BY n DESC
                """,
                params,
            )
            for rec in r:
                apps.append({"source_app": rec["app"], "thread_type": "chat", "count": int(rec["n"])})

            r = session.run(
                f"""
                MATCH (n:PhoneCall {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE n.source_app IS NOT NULL {rk_filter}
                RETURN n.source_app AS app, count(n) AS n
                ORDER BY n DESC
                """,
                params,
            )
            for rec in r:
                apps.append({"source_app": rec["app"], "thread_type": "calls", "count": int(rec["n"])})

            r = session.run(
                f"""
                MATCH (n:Email {{case_id: $case_id, source_type: 'cellebrite'}})
                WHERE n.source_app IS NOT NULL {rk_filter}
                RETURN n.source_app AS app, count(n) AS n
                ORDER BY n DESC
                """,
                params,
            )
            for rec in r:
                apps.append({"source_app": rec["app"], "thread_type": "emails", "count": int(rec["n"])})

        return apps

    def get_cellebrite_comms_threads(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        participant_keys: Optional[List[str]] = None,
        from_keys: Optional[List[str]] = None,
        to_keys: Optional[List[str]] = None,
        thread_types: Optional[List[str]] = None,
        source_apps: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list:
        """
        Get conversation threads — real chat threads + synthetic call/email threads per participant pair.

        thread_types controls which kinds to include: 'chat', 'calls', 'emails'.
        When from_keys/to_keys are provided, returns only threads involving those pairs.
        """
        active_types = set(thread_types) if thread_types else {"chat", "calls", "emails"}
        threads: list = []

        rk_filter_chat = ""
        rk_filter_call = ""
        rk_filter_email = ""
        params: Dict[str, Any] = {"case_id": case_id}
        if report_keys:
            rk_filter_chat = "AND chat.cellebrite_report_key IN $report_keys"
            rk_filter_call = "AND c.cellebrite_report_key IN $report_keys"
            rk_filter_email = "AND e.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        # Source-app filter (e.g. only WhatsApp + Facebook Messenger). Empty / None = all.
        app_filter_chat = ""
        app_filter_call = ""
        app_filter_email = ""
        if source_apps:
            app_filter_chat = "AND chat.source_app IN $source_apps"
            app_filter_call = "AND c.source_app IN $source_apps"
            app_filter_email = "AND e.source_app IN $source_apps"
            params["source_apps"] = list(source_apps)

        date_filter_chat = ""
        date_filter_call = ""
        date_filter_email = ""
        if start_date:
            date_filter_chat += " AND chat.last_activity >= $start_date"
            date_filter_call += " AND c.timestamp >= $start_date"
            date_filter_email += " AND e.timestamp >= $start_date"
            params["start_date"] = start_date
        if end_date:
            date_filter_chat += " AND chat.start_time <= $end_date"
            date_filter_call += " AND c.timestamp <= $end_date"
            date_filter_email += " AND e.timestamp <= $end_date"
            params["end_date"] = end_date

        with self._driver.session() as session:
            # ---- Chat threads (real Communication nodes with chat_id) ----
            if "chat" in active_types:
                search_clause = ""
                if search:
                    search_clause = " AND (toLower(chat.name) CONTAINS toLower($search) OR toLower(chat.source_app) CONTAINS toLower($search))"
                    params["search"] = search

                query = f"""
                    MATCH (chat:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE chat.chat_id IS NOT NULL {rk_filter_chat} {app_filter_chat} {date_filter_chat} {search_clause}
                    OPTIONAL MATCH (p:Person)-[:PARTICIPATED_IN]->(chat)
                    OPTIONAL MATCH (msg:Communication)-[:PART_OF]->(chat)
                      WHERE msg.body IS NOT NULL
                    WITH chat, collect(DISTINCT p) AS participants,
                         count(DISTINCT msg) AS msg_count,
                         sum(coalesce(msg.attachment_count, 0)) AS attach_count,
                         max(msg.timestamp) AS last_msg_ts,
                         min(msg.timestamp) AS first_msg_ts
                    RETURN chat, participants, msg_count, attach_count, last_msg_ts, first_msg_ts
                    ORDER BY coalesce(last_msg_ts, chat.last_activity) DESC
                """
                result = session.run(query, params)
                for record in result:
                    chat = dict(record["chat"])
                    participants = [dict(p) for p in record["participants"] if p is not None]

                    # Participant filter: if from_keys or to_keys provided, ensure at least one matches
                    if from_keys or to_keys:
                        pkeys = {p.get("key") for p in participants if p.get("key")}
                        if from_keys and not any(k in pkeys for k in from_keys):
                            continue
                        if to_keys and not any(k in pkeys for k in to_keys):
                            continue

                    threads.append({
                        "thread_id": chat.get("key"),
                        "thread_type": "chat",
                        "source_app": chat.get("source_app") or "",
                        "name": chat.get("name") or "Chat",
                        "participants": [
                            {
                                "key": p.get("key"),
                                "name": p.get("name") or p.get("key"),
                                "is_owner": bool(p.get("is_phone_owner")),
                            }
                            for p in participants
                        ],
                        "message_count": int(record["msg_count"] or chat.get("message_count") or 0),
                        "attachment_count": int(record["attach_count"] or 0),
                        "has_attachments": int(record["attach_count"] or 0) > 0,
                        "last_activity": record["last_msg_ts"] or chat.get("last_activity"),
                        "first_activity": record["first_msg_ts"] or chat.get("start_time"),
                        "report_key": chat.get("cellebrite_report_key"),
                    })

            # ---- Synthetic call threads (per participant pair + report) ----
            if "calls" in active_types:
                query = f"""
                    MATCH (a:Person {{case_id: $case_id, source_type: 'cellebrite'}})-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(b:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE a.key IS NOT NULL AND b.key IS NOT NULL {rk_filter_call} {app_filter_call} {date_filter_call}
                    WITH a, b, c.cellebrite_report_key AS rk,
                         collect(c) AS calls
                    RETURN a, b, rk,
                           size(calls) AS call_count,
                           reduce(s = 0, cc IN calls | s + coalesce(cc.attachment_count, 0)) AS attach_count,
                           [cc IN calls | cc.timestamp] AS timestamps
                """
                result = session.run(query, params)
                # Neo4j returns one row per (a,b) AND one per (b,a) when both
                # directions exist. We normalise to the sorted pair and merge
                # those two rows into a single thread.
                call_pairs: Dict[str, dict] = {}
                for record in result:
                    a = dict(record["a"])
                    b = dict(record["b"])
                    a_key, b_key = a.get("key"), b.get("key")
                    if not a_key or not b_key:
                        continue
                    # Participant filter
                    if from_keys or to_keys:
                        pkeys = {a_key, b_key}
                        if from_keys and not any(k in pkeys for k in from_keys):
                            continue
                        if to_keys and not any(k in pkeys for k in to_keys):
                            continue

                    pair_keys = tuple(sorted([a_key, b_key]))
                    thread_id = f"calls-{record['rk']}-{pair_keys[0]}-{pair_keys[1]}"
                    timestamps = [t for t in (record["timestamps"] or []) if t]
                    call_count = int(record["call_count"] or 0)
                    attach_count = int(record["attach_count"] or 0)

                    existing = call_pairs.get(thread_id)
                    if existing is None:
                        # Determine participants preserving person metadata
                        participants = [
                            {"key": a_key, "name": a.get("name") or a_key, "is_owner": bool(a.get("is_phone_owner"))},
                            {"key": b_key, "name": b.get("name") or b_key, "is_owner": bool(b.get("is_phone_owner"))},
                        ]
                        # Order participants to match pair_keys ordering
                        participants.sort(key=lambda p: p["key"])
                        name_parts = [p["name"] for p in participants]
                        call_pairs[thread_id] = {
                            "thread_id": thread_id,
                            "thread_type": "calls",
                            "source_app": "Calls",
                            "name": f"Calls: {name_parts[0]} ↔ {name_parts[1]}",
                            "participants": participants,
                            "message_count": call_count,
                            "attachment_count": attach_count,
                            "has_attachments": attach_count > 0,
                            "last_activity": max(timestamps) if timestamps else None,
                            "first_activity": min(timestamps) if timestamps else None,
                            "report_key": record["rk"],
                            "pair_keys": list(pair_keys),
                        }
                    else:
                        # Merge the reverse-direction row into the existing one
                        existing["message_count"] += call_count
                        existing["attachment_count"] += attach_count
                        existing["has_attachments"] = existing["attachment_count"] > 0
                        if timestamps:
                            ts_max = max(timestamps)
                            ts_min = min(timestamps)
                            if existing.get("last_activity") is None or ts_max > existing["last_activity"]:
                                existing["last_activity"] = ts_max
                            if existing.get("first_activity") is None or ts_min < existing["first_activity"]:
                                existing["first_activity"] = ts_min

                threads.extend(call_pairs.values())

            # ---- Synthetic email threads (per participant pair + report) ----
            if "emails" in active_types:
                query = f"""
                    MATCH (a:Person {{case_id: $case_id, source_type: 'cellebrite'}})-[:EMAILED]->(e:Email)-[:SENT_TO]->(b:Person {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE a.key IS NOT NULL AND b.key IS NOT NULL {rk_filter_email} {app_filter_email} {date_filter_email}
                    WITH a, b, e.cellebrite_report_key AS rk,
                         collect(e) AS emails
                    RETURN a, b, rk,
                           size(emails) AS email_count,
                           reduce(s = 0, ee IN emails | s + coalesce(ee.attachment_count, 0)) AS attach_count,
                           [ee IN emails | ee.timestamp] AS timestamps
                """
                result = session.run(query, params)
                # Same dedupe pattern as calls — merge bidirectional pairs
                email_pairs: Dict[str, dict] = {}
                for record in result:
                    a = dict(record["a"])
                    b = dict(record["b"])
                    a_key, b_key = a.get("key"), b.get("key")
                    if not a_key or not b_key:
                        continue
                    if from_keys or to_keys:
                        pkeys = {a_key, b_key}
                        if from_keys and not any(k in pkeys for k in from_keys):
                            continue
                        if to_keys and not any(k in pkeys for k in to_keys):
                            continue

                    pair_keys = tuple(sorted([a_key, b_key]))
                    thread_id = f"emails-{record['rk']}-{pair_keys[0]}-{pair_keys[1]}"
                    timestamps = [t for t in (record["timestamps"] or []) if t]
                    email_count = int(record["email_count"] or 0)
                    attach_count = int(record["attach_count"] or 0)

                    existing = email_pairs.get(thread_id)
                    if existing is None:
                        participants = [
                            {"key": a_key, "name": a.get("name") or a_key, "is_owner": bool(a.get("is_phone_owner"))},
                            {"key": b_key, "name": b.get("name") or b_key, "is_owner": bool(b.get("is_phone_owner"))},
                        ]
                        participants.sort(key=lambda p: p["key"])
                        name_parts = [p["name"] for p in participants]
                        email_pairs[thread_id] = {
                            "thread_id": thread_id,
                            "thread_type": "emails",
                            "source_app": "Email",
                            "name": f"Emails: {name_parts[0]} ↔ {name_parts[1]}",
                            "participants": participants,
                            "message_count": email_count,
                            "attachment_count": attach_count,
                            "has_attachments": attach_count > 0,
                            "last_activity": max(timestamps) if timestamps else None,
                            "first_activity": min(timestamps) if timestamps else None,
                            "report_key": record["rk"],
                            "pair_keys": list(pair_keys),
                        }
                    else:
                        existing["message_count"] += email_count
                        existing["attachment_count"] += attach_count
                        existing["has_attachments"] = existing["attachment_count"] > 0
                        if timestamps:
                            ts_max = max(timestamps)
                            ts_min = min(timestamps)
                            if existing.get("last_activity") is None or ts_max > existing["last_activity"]:
                                existing["last_activity"] = ts_max
                            if existing.get("first_activity") is None or ts_min < existing["first_activity"]:
                                existing["first_activity"] = ts_min

                threads.extend(email_pairs.values())

        # Merge duplicate synthetic threads (same pair, same report, both directions — already grouped by query)
        # Sort all threads by last_activity DESC
        threads.sort(key=lambda t: (t.get("last_activity") or ""), reverse=True)

        total = len(threads)
        # Apply pagination
        threads = threads[offset: offset + limit]
        return {"threads": threads, "total": total}

    def get_cellebrite_thread_detail(
        self,
        case_id: str,
        thread_id: str,
        thread_type: str,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """
        Get chronological items (messages/calls/emails) for a thread with sender
        attribution and attachment file IDs.
        """
        items: list = []

        with self._driver.session() as session:
            if thread_type == "chat":
                # Real chat thread — load parent + messages
                result = session.run(
                    """
                    MATCH (chat:Communication {case_id: $case_id, key: $thread_id})
                    OPTIONAL MATCH (p:Person)-[:PARTICIPATED_IN]->(chat)
                    RETURN chat, collect(DISTINCT p) AS participants
                    """,
                    case_id=case_id,
                    thread_id=thread_id,
                )
                record = result.single()
                if not record:
                    return {"thread": None, "items": [], "total": 0}
                chat = dict(record["chat"])
                participants = [dict(p) for p in record["participants"] if p is not None]

                msg_result = session.run(
                    """
                    MATCH (msg:Communication)-[:PART_OF]->(chat:Communication {case_id: $case_id, key: $thread_id})
                    WHERE msg.body IS NOT NULL
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(msg)
                    RETURN msg, sender
                    ORDER BY msg.timestamp
                    SKIP $offset LIMIT $limit
                    """,
                    case_id=case_id,
                    thread_id=thread_id,
                    offset=offset,
                    limit=limit,
                )
                for r in msg_result:
                    msg = dict(r["msg"])
                    sender = dict(r["sender"]) if r["sender"] else None
                    items.append({
                        "id": msg.get("id"),
                        "type": "message",
                        "timestamp": msg.get("timestamp"),
                        "date": msg.get("date"),
                        "time": msg.get("time"),
                        "source_app": msg.get("source_app"),
                        "message_type": msg.get("message_type"),
                        "body": msg.get("body") or "",
                        "deleted_state": msg.get("deleted_state"),
                        "attachment_file_ids": list(msg.get("attachment_file_ids") or []),
                        "sender": {
                            "key": sender.get("key") if sender else None,
                            "name": sender.get("name") if sender else None,
                            "is_owner": bool(sender.get("is_phone_owner")) if sender else False,
                        } if sender else None,
                    })

                # Total count for pagination
                total_r = session.run(
                    """
                    MATCH (msg:Communication)-[:PART_OF]->(chat:Communication {case_id: $case_id, key: $thread_id})
                    WHERE msg.body IS NOT NULL
                    RETURN count(msg) AS n
                    """,
                    case_id=case_id,
                    thread_id=thread_id,
                ).single()
                total = int(total_r["n"]) if total_r else 0

                return {
                    "thread": {
                        "thread_id": thread_id,
                        "thread_type": "chat",
                        "name": chat.get("name"),
                        "source_app": chat.get("source_app"),
                        "participants": [
                            {
                                "key": p.get("key"),
                                "name": p.get("name") or p.get("key"),
                                "is_owner": bool(p.get("is_phone_owner")),
                            }
                            for p in participants
                        ],
                        "report_key": chat.get("cellebrite_report_key"),
                    },
                    "items": items,
                    "total": total,
                }

            elif thread_type == "calls" or thread_type == "emails":
                # Parse thread_id "calls-{report_key}-{keyA}-{keyB}" or "emails-..."
                # Note: report_key may contain dashes; split on first & last 2 segments
                if not thread_id.startswith(f"{thread_type}-"):
                    return {"thread": None, "items": [], "total": 0}
                remainder = thread_id[len(thread_type) + 1:]
                # Participant keys are prefixed with phone-/email-/... and may contain dashes.
                # We split from the right: the last TWO tokens that start with a known person-key prefix
                # are the pair. Everything before = report_key.
                parts = remainder.split("-")
                # Reconstruct: scan from right until we have two person keys.
                # Person keys look like phone-XXXXXX, email-xxx, or app-slug-id.
                # Heuristic: split into report_key + keyA + keyB by scanning for prefix markers.
                # Simpler: store dashless separator would be cleaner; here we use known person-key prefixes.
                def find_person_key_start(tokens, start_idx):
                    prefixes = ("phone", "email", "fb", "ig", "wa", "tg", "snap", "twitter", "linkedin")
                    for i in range(start_idx, len(tokens)):
                        for pfx in prefixes:
                            if tokens[i] == pfx:
                                return i
                    return -1

                # Find two person-key start indices
                key_a_start = find_person_key_start(parts, 0)
                key_b_start = find_person_key_start(parts, key_a_start + 1) if key_a_start >= 0 else -1
                if key_a_start < 0 or key_b_start < 0:
                    return {"thread": None, "items": [], "total": 0}

                report_key = "-".join(parts[:key_a_start])
                key_a = "-".join(parts[key_a_start:key_b_start])
                key_b = "-".join(parts[key_b_start:])

                if thread_type == "calls":
                    query = """
                        MATCH (a:Person {case_id: $case_id, key: $key_a})
                        MATCH (b:Person {case_id: $case_id, key: $key_b})
                        MATCH (src:Person)-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(dst:Person)
                        WHERE c.cellebrite_report_key = $report_key
                          AND ((src = a AND dst = b) OR (src = b AND dst = a))
                        RETURN c, src, dst
                        ORDER BY c.timestamp
                        SKIP $offset LIMIT $limit
                    """
                    result = session.run(
                        query,
                        case_id=case_id,
                        key_a=key_a,
                        key_b=key_b,
                        report_key=report_key,
                        offset=offset,
                        limit=limit,
                    )
                    for r in result:
                        c = dict(r["c"])
                        src = dict(r["src"]) if r["src"] else None
                        dst = dict(r["dst"]) if r["dst"] else None
                        items.append({
                            "id": c.get("id"),
                            "type": "call",
                            "timestamp": c.get("timestamp"),
                            "date": c.get("date"),
                            "time": c.get("time"),
                            "source_app": c.get("source_app"),
                            "direction": c.get("direction"),
                            "duration": c.get("duration"),
                            "call_type": c.get("call_type"),
                            "video_call": bool(c.get("video_call")),
                            "deleted_state": c.get("deleted_state"),
                            "attachment_file_ids": list(c.get("attachment_file_ids") or []),
                            "sender": {
                                "key": src.get("key") if src else None,
                                "name": src.get("name") if src else None,
                                "is_owner": bool(src.get("is_phone_owner")) if src else False,
                            } if src else None,
                            "recipient": {
                                "key": dst.get("key") if dst else None,
                                "name": dst.get("name") if dst else None,
                                "is_owner": bool(dst.get("is_phone_owner")) if dst else False,
                            } if dst else None,
                        })
                else:  # emails
                    query = """
                        MATCH (a:Person {case_id: $case_id, key: $key_a})
                        MATCH (b:Person {case_id: $case_id, key: $key_b})
                        MATCH (src:Person)-[:EMAILED]->(e:Email)-[:SENT_TO]->(dst:Person)
                        WHERE e.cellebrite_report_key = $report_key
                          AND ((src = a AND dst = b) OR (src = b AND dst = a))
                        RETURN e, src, dst
                        ORDER BY e.timestamp
                        SKIP $offset LIMIT $limit
                    """
                    result = session.run(
                        query,
                        case_id=case_id,
                        key_a=key_a,
                        key_b=key_b,
                        report_key=report_key,
                        offset=offset,
                        limit=limit,
                    )
                    for r in result:
                        e = dict(r["e"])
                        src = dict(r["src"]) if r["src"] else None
                        dst = dict(r["dst"]) if r["dst"] else None
                        items.append({
                            "id": e.get("id"),
                            "type": "email",
                            "timestamp": e.get("timestamp"),
                            "date": e.get("date"),
                            "time": e.get("time"),
                            "source_app": e.get("source_app"),
                            "subject": e.get("subject"),
                            "body": e.get("body") or "",
                            "folder": e.get("folder"),
                            "email_status": e.get("email_status"),
                            "deleted_state": e.get("deleted_state"),
                            "attachment_file_ids": list(e.get("attachment_file_ids") or []),
                            "sender": {
                                "key": src.get("key") if src else None,
                                "name": src.get("name") if src else None,
                                "is_owner": bool(src.get("is_phone_owner")) if src else False,
                            } if src else None,
                            "recipient": {
                                "key": dst.get("key") if dst else None,
                                "name": dst.get("name") if dst else None,
                                "is_owner": bool(dst.get("is_phone_owner")) if dst else False,
                            } if dst else None,
                        })

                # Name lookup for thread metadata
                a_r = session.run(
                    "MATCH (p:Person {case_id: $case_id, key: $key}) RETURN p LIMIT 1",
                    case_id=case_id,
                    key=key_a,
                ).single()
                b_r = session.run(
                    "MATCH (p:Person {case_id: $case_id, key: $key}) RETURN p LIMIT 1",
                    case_id=case_id,
                    key=key_b,
                ).single()
                a = dict(a_r["p"]) if a_r else {}
                b = dict(b_r["p"]) if b_r else {}

                return {
                    "thread": {
                        "thread_id": thread_id,
                        "thread_type": thread_type,
                        "name": f"{a.get('name') or key_a} ↔ {b.get('name') or key_b}",
                        "source_app": "Calls" if thread_type == "calls" else "Email",
                        "participants": [
                            {"key": key_a, "name": a.get("name") or key_a, "is_owner": bool(a.get("is_phone_owner"))},
                            {"key": key_b, "name": b.get("name") or key_b, "is_owner": bool(b.get("is_phone_owner"))},
                        ],
                        "report_key": report_key,
                    },
                    "items": items,
                    "total": len(items),
                }

            else:
                return {"thread": None, "items": [], "total": 0}

    def get_cellebrite_comms_between(
        self,
        case_id: str,
        from_keys: Optional[List[str]] = None,
        to_keys: Optional[List[str]] = None,
        types: Optional[List[str]] = None,
        report_keys: Optional[List[str]] = None,
        source_apps: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """
        Get chronological cross-type comms where any from_keys participant
        communicated with any to_keys participant (AND semantics).

        types: subset of ['message', 'call', 'email'] — includes all if None.
        """
        active_types = set(types) if types else {"message", "call", "email"}

        params: Dict[str, Any] = {"case_id": case_id}
        params["from_keys"] = list(from_keys) if from_keys else []
        params["to_keys"] = list(to_keys) if to_keys else []
        rk_filter_msg = ""
        rk_filter_call = ""
        rk_filter_email = ""
        if report_keys:
            rk_filter_msg = "AND msg.cellebrite_report_key IN $report_keys"
            rk_filter_call = "AND c.cellebrite_report_key IN $report_keys"
            rk_filter_email = "AND e.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        app_filter_msg = ""
        app_filter_call = ""
        app_filter_email = ""
        if source_apps:
            app_filter_msg = "AND msg.source_app IN $source_apps"
            app_filter_call = "AND c.source_app IN $source_apps"
            app_filter_email = "AND e.source_app IN $source_apps"
            params["source_apps"] = list(source_apps)

        date_filter_msg = ""
        date_filter_call = ""
        date_filter_email = ""
        if start_date:
            date_filter_msg = " AND msg.timestamp >= $start_date"
            date_filter_call = " AND c.timestamp >= $start_date"
            date_filter_email = " AND e.timestamp >= $start_date"
            params["start_date"] = start_date
        if end_date:
            date_filter_msg += " AND msg.timestamp <= $end_date"
            date_filter_call += " AND c.timestamp <= $end_date"
            date_filter_email += " AND e.timestamp <= $end_date"
            params["end_date"] = end_date

        items: list = []

        with self._driver.session() as session:
            if "message" in active_types:
                # Messages: sender -> message -> chat <- participants (includes recipient)
                query = f"""
                    MATCH (sender:Person)-[:SENT_MESSAGE]->(msg:Communication)-[:PART_OF]->(chat:Communication)
                    WHERE msg.case_id = $case_id AND msg.body IS NOT NULL
                      AND (size($from_keys) = 0 OR sender.key IN $from_keys)
                      {rk_filter_msg} {app_filter_msg} {date_filter_msg}
                    MATCH (recipient:Person)-[:PARTICIPATED_IN]->(chat)
                    WHERE recipient <> sender
                      AND (size($to_keys) = 0 OR recipient.key IN $to_keys)
                    WITH msg, sender, chat,
                         collect(DISTINCT recipient) AS recipients
                    RETURN msg, sender, recipients, chat
                    ORDER BY msg.timestamp DESC
                    LIMIT $limit
                """
                result = session.run(query, {**params, "limit": limit + offset})
                for r in result:
                    msg = dict(r["msg"])
                    sender = dict(r["sender"]) if r["sender"] else None
                    chat = dict(r["chat"])
                    recipients = [dict(rp) for rp in r["recipients"] if rp is not None]
                    items.append({
                        "id": msg.get("id"),
                        "type": "message",
                        "timestamp": msg.get("timestamp"),
                        "source_app": msg.get("source_app"),
                        "message_type": msg.get("message_type"),
                        "body": msg.get("body") or "",
                        "attachment_file_ids": list(msg.get("attachment_file_ids") or []),
                        "thread_id": chat.get("key"),
                        "thread_type": "chat",
                        "sender": {
                            "key": sender.get("key"),
                            "name": sender.get("name") or sender.get("key"),
                            "is_owner": bool(sender.get("is_phone_owner")),
                        } if sender else None,
                        "recipients": [
                            {"key": rp.get("key"), "name": rp.get("name") or rp.get("key")}
                            for rp in recipients
                        ],
                        "report_key": msg.get("cellebrite_report_key"),
                    })

            if "call" in active_types:
                query = f"""
                    MATCH (src:Person)-[:CALLED]->(c:PhoneCall)-[:CALLED_TO]->(dst:Person)
                    WHERE c.case_id = $case_id
                      AND (
                          (size($from_keys) = 0 OR src.key IN $from_keys)
                          AND (size($to_keys) = 0 OR dst.key IN $to_keys)
                      )
                      {rk_filter_call} {app_filter_call} {date_filter_call}
                    RETURN c, src, dst
                    ORDER BY c.timestamp DESC
                    LIMIT $limit
                """
                result = session.run(query, {**params, "limit": limit + offset})
                for r in result:
                    c = dict(r["c"])
                    src = dict(r["src"]) if r["src"] else None
                    dst = dict(r["dst"]) if r["dst"] else None
                    items.append({
                        "id": c.get("id"),
                        "type": "call",
                        "timestamp": c.get("timestamp"),
                        "source_app": c.get("source_app"),
                        "direction": c.get("direction"),
                        "duration": c.get("duration"),
                        "call_type": c.get("call_type"),
                        "video_call": bool(c.get("video_call")),
                        "attachment_file_ids": list(c.get("attachment_file_ids") or []),
                        "thread_id": None,
                        "thread_type": "calls",
                        "sender": {
                            "key": src.get("key"),
                            "name": src.get("name") or src.get("key"),
                            "is_owner": bool(src.get("is_phone_owner")),
                        } if src else None,
                        "recipients": [
                            {"key": dst.get("key"), "name": dst.get("name") or dst.get("key")}
                        ] if dst else [],
                        "report_key": c.get("cellebrite_report_key"),
                    })

            if "email" in active_types:
                query = f"""
                    MATCH (src:Person)-[:EMAILED]->(e:Email)-[:SENT_TO]->(dst:Person)
                    WHERE e.case_id = $case_id
                      AND (
                          (size($from_keys) = 0 OR src.key IN $from_keys)
                          AND (size($to_keys) = 0 OR dst.key IN $to_keys)
                      )
                      {rk_filter_email} {app_filter_email} {date_filter_email}
                    RETURN e, src, dst
                    ORDER BY e.timestamp DESC
                    LIMIT $limit
                """
                result = session.run(query, {**params, "limit": limit + offset})
                for r in result:
                    e = dict(r["e"])
                    src = dict(r["src"]) if r["src"] else None
                    dst = dict(r["dst"]) if r["dst"] else None
                    items.append({
                        "id": e.get("id"),
                        "type": "email",
                        "timestamp": e.get("timestamp"),
                        "source_app": e.get("source_app"),
                        "subject": e.get("subject"),
                        "body": e.get("body") or "",
                        "folder": e.get("folder"),
                        "attachment_file_ids": list(e.get("attachment_file_ids") or []),
                        "thread_id": None,
                        "thread_type": "emails",
                        "sender": {
                            "key": src.get("key"),
                            "name": src.get("name") or src.get("key"),
                            "is_owner": bool(src.get("is_phone_owner")),
                        } if src else None,
                        "recipients": [
                            {"key": dst.get("key"), "name": dst.get("name") or dst.get("key")}
                        ] if dst else [],
                        "report_key": e.get("cellebrite_report_key"),
                    })

        # Dedupe — the same message can be returned multiple times when a
        # chat has many participants and the from/to filters overlap. Keep the
        # first occurrence (keys in the Python dict preserve insertion order).
        seen_ids = set()
        deduped = []
        for it in items:
            key = it.get("id") or it.get("node_key")
            if key is None:
                deduped.append(it)
                continue
            if key in seen_ids:
                continue
            seen_ids.add(key)
            deduped.append(it)
        items = deduped

        # Sort & paginate
        items.sort(key=lambda i: (i.get("timestamp") or ""), reverse=True)
        total = len(items)
        items = items[offset: offset + limit]
        return {"items": items, "total": total}

    # ------------------------------------------------------------------
    # Cellebrite Location & Event Center (Phase 4) queries
    # ------------------------------------------------------------------

    def _build_event_filters(
        self,
        report_keys: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
        source_apps: Optional[List[str]],
        prefix: str = "n",
    ) -> Tuple[str, Dict[str, Any]]:
        """Build a shared WHERE fragment for event queries."""
        parts = [f"{prefix}.case_id = $case_id"]
        params: Dict[str, Any] = {}
        if report_keys:
            parts.append(f"{prefix}.cellebrite_report_key IN $report_keys")
            params["report_keys"] = list(report_keys)
        if start_date:
            parts.append(f"{prefix}.timestamp >= $start_date")
            params["start_date"] = start_date
        if end_date:
            parts.append(f"{prefix}.timestamp <= $end_date")
            params["end_date"] = end_date
        if source_apps:
            parts.append(f"{prefix}.source_app IN $source_apps")
            params["source_apps"] = list(source_apps)
        return " AND ".join(parts), params

    def get_cellebrite_events(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        event_types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        only_geolocated: bool = False,
        source_apps: Optional[List[str]] = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> dict:
        """
        Unified event feed for the Location & Event Center.
        Returns chronologically-sortable event rows with optional geolocation.
        """
        active = set(event_types) if event_types else {
            "location", "cell_tower", "wifi", "call", "message", "email",
            "power", "device_event", "app_session", "search", "visit", "meeting",
        }

        events: list = []
        with self._driver.session() as session:
            # Helper to accumulate results from one cypher
            def _add(cypher: str, params: dict, event_type: str, projector):
                r = session.run(cypher, params)
                for rec in r:
                    row = projector(rec)
                    if row:
                        row["event_type"] = event_type
                        events.append(row)

            where, p = self._build_event_filters(report_keys, start_date, end_date, source_apps)
            base_params = {"case_id": case_id, **p}

            if "location" in active:
                extra = "" if not only_geolocated else "AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL"
                cypher = f"""
                    MATCH (n:Location {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    RETURN n
                """
                _add(cypher, base_params, "location", lambda rec: _project_event(rec["n"], "location"))

            if "cell_tower" in active:
                extra = "" if not only_geolocated else "AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL"
                cypher = f"""
                    MATCH (n:CellTower {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    RETURN n
                """
                _add(cypher, base_params, "cell_tower", lambda rec: _project_event(rec["n"], "cell_tower"))

            if "wifi" in active:
                cypher = f"""
                    MATCH (n:WirelessNetwork {{source_type:'cellebrite'}})
                    WHERE {where} AND n.timestamp IS NOT NULL
                    RETURN n
                """
                _add(cypher, base_params, "wifi", lambda rec: _project_event(rec["n"], "wifi"))

            if "call" in active:
                extra = "" if not only_geolocated else \
                    "AND (n.latitude IS NOT NULL OR n.nearest_location_lat IS NOT NULL)"
                cypher = f"""
                    MATCH (n:PhoneCall {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    OPTIONAL MATCH (src:Person)-[:CALLED]->(n)
                    OPTIONAL MATCH (n)-[:CALLED_TO]->(dst:Person)
                    RETURN n, src, dst
                """
                _add(cypher, base_params, "call",
                     lambda rec: _project_call(rec["n"], rec["src"], rec["dst"]))

            if "message" in active:
                extra = "" if not only_geolocated else \
                    "AND (n.latitude IS NOT NULL OR n.nearest_location_lat IS NOT NULL)"
                cypher = f"""
                    MATCH (n:Communication {{source_type:'cellebrite'}})
                    WHERE {where} AND n.body IS NOT NULL {extra}
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(n)
                    OPTIONAL MATCH (n)-[:PART_OF]->(chat:Communication)
                    RETURN n, sender, chat
                """
                _add(cypher, base_params, "message",
                     lambda rec: _project_message(rec["n"], rec["sender"], rec["chat"]))

            if "email" in active:
                extra = "" if not only_geolocated else \
                    "AND (n.latitude IS NOT NULL OR n.nearest_location_lat IS NOT NULL)"
                cypher = f"""
                    MATCH (n:Email {{source_type:'cellebrite'}})
                    WHERE {where} {extra}
                    OPTIONAL MATCH (src:Person)-[:EMAILED]->(n)
                    OPTIONAL MATCH (n)-[:SENT_TO]->(dst:Person)
                    RETURN n, src, dst
                """
                _add(cypher, base_params, "email",
                     lambda rec: _project_email(rec["n"], rec["src"], rec["dst"]))

            if "power" in active or "device_event" in active:
                cypher = f"""
                    MATCH (n:DeviceEvent {{source_type:'cellebrite'}})
                    WHERE {where}
                    RETURN n
                """
                r = session.run(cypher, base_params)
                for rec in r:
                    n = dict(rec["n"])
                    etype = "power" if n.get("event_type") == "power" else "device_event"
                    if etype in active:
                        row = _project_event(n, etype)
                        if row:
                            row["event_type"] = etype
                            events.append(row)

            if "app_session" in active:
                cypher = f"""
                    MATCH (n:AppSession {{source_type:'cellebrite'}})
                    WHERE {where}
                    RETURN n
                """
                _add(cypher, base_params, "app_session", lambda rec: _project_event(rec["n"], "app_session"))

            if "search" in active:
                cypher = f"""
                    MATCH (n:SearchedItem {{source_type:'cellebrite'}})
                    WHERE {where} AND n.timestamp IS NOT NULL
                    RETURN n
                """
                _add(cypher, base_params, "search", lambda rec: _project_event(rec["n"], "search"))

            if "visit" in active:
                cypher = f"""
                    MATCH (n:VisitedPage {{source_type:'cellebrite'}})
                    WHERE {where} AND n.timestamp IS NOT NULL
                    RETURN n
                """
                _add(cypher, base_params, "visit", lambda rec: _project_event(rec["n"], "visit"))

            if "meeting" in active:
                cypher = f"""
                    MATCH (n:Meeting {{case_id:$case_id, source_type:'cellebrite'}})
                    WHERE {where.replace('n.case_id = $case_id', 'true')} AND n.timestamp IS NOT NULL
                    RETURN n
                """
                # Meetings may not have all filter fields; simpler filter
                r = session.run(
                    "MATCH (n:Meeting {case_id:$case_id}) WHERE n.timestamp IS NOT NULL RETURN n",
                    case_id=case_id,
                )
                for rec in r:
                    row = _project_event(rec["n"], "meeting")
                    if row:
                        row["event_type"] = "meeting"
                        events.append(row)

        # Sort by timestamp ascending; apply limit+offset
        events.sort(key=lambda e: (e.get("timestamp") or ""))
        total = len(events)
        events = events[offset: offset + limit]
        return {"events": events, "total": total}

    def get_cellebrite_event_types(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
    ) -> list:
        """Counts per event type (all + geolocated), powering the filter UI."""
        rk_filter = ""
        params: Dict[str, Any] = {"case_id": case_id}
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        out: list = []
        with self._driver.session() as session:
            def _count(label: str, extra_where: str, event_type: str, human: str):
                r = session.run(
                    f"""
                    MATCH (n:{label} {{case_id:$case_id, source_type:'cellebrite'}})
                    WHERE 1=1 {rk_filter} {extra_where}
                    RETURN count(n) AS total,
                           count(CASE WHEN coalesce(n.latitude, n.nearest_location_lat) IS NOT NULL THEN 1 END) AS geo
                    """,
                    params,
                ).single()
                if r and r["total"] > 0:
                    out.append({
                        "event_type": event_type,
                        "label": human,
                        "count": int(r["total"]),
                        "geolocated": int(r["geo"]),
                    })

            _count("Location", "", "location", "Locations / places")
            _count("CellTower", "", "cell_tower", "Cell towers")
            _count("WirelessNetwork", "AND n.timestamp IS NOT NULL", "wifi", "WiFi networks")
            _count("PhoneCall", "", "call", "Calls")
            _count("Communication", "AND n.body IS NOT NULL", "message", "Messages")
            _count("Email", "", "email", "Emails")
            _count("DeviceEvent", "AND n.event_type = 'power'", "power", "Power events")
            _count("DeviceEvent", "AND (n.event_type IS NULL OR n.event_type <> 'power')",
                   "device_event", "Device events")
            _count("AppSession", "", "app_session", "App sessions")
            _count("SearchedItem", "AND n.timestamp IS NOT NULL", "search", "Searches")
            _count("VisitedPage", "AND n.timestamp IS NOT NULL", "visit", "Page visits")

            # Meeting — separate (not always source_type cellebrite)
            r = session.run(
                "MATCH (n:Meeting {case_id:$case_id}) WHERE n.timestamp IS NOT NULL RETURN count(n) AS total",
                case_id=case_id,
            ).single()
            if r and r["total"] > 0:
                out.append({
                    "event_type": "meeting",
                    "label": "Meetings",
                    "count": int(r["total"]),
                    "geolocated": 0,
                })
        return out

    def get_cellebrite_event_tracks(
        self,
        case_id: str,
        report_keys: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        simplify: bool = True,
    ) -> dict:
        """
        Per-device chronologically-ordered location tracks for map polylines.
        Sourced from Location + CellTower + any event with coordinates.
        """
        rk_filter = ""
        params: Dict[str, Any] = {"case_id": case_id}
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)
        date_filter = ""
        if start_date:
            date_filter += " AND n.timestamp >= $start_date"
            params["start_date"] = start_date
        if end_date:
            date_filter += " AND n.timestamp <= $end_date"
            params["end_date"] = end_date

        points_by_device: Dict[str, list] = {}
        with self._driver.session() as session:
            def _collect(cypher: str, source: str):
                r = session.run(cypher, params)
                for rec in r:
                    rk = rec["rk"]
                    if rk is None:
                        continue
                    points_by_device.setdefault(rk, []).append({
                        "timestamp": rec["ts"],
                        "lat": float(rec["lat"]),
                        "lon": float(rec["lon"]),
                        "source": source,
                    })

            _collect(
                f"""
                MATCH (n:Location {{case_id:$case_id, source_type:'cellebrite'}})
                WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                  AND n.timestamp IS NOT NULL
                  {rk_filter} {date_filter}
                RETURN n.cellebrite_report_key AS rk, n.timestamp AS ts,
                       n.latitude AS lat, n.longitude AS lon
                """,
                "location",
            )
            _collect(
                f"""
                MATCH (n:CellTower {{case_id:$case_id, source_type:'cellebrite'}})
                WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                  AND n.timestamp IS NOT NULL
                  {rk_filter} {date_filter}
                RETURN n.cellebrite_report_key AS rk, n.timestamp AS ts,
                       n.latitude AS lat, n.longitude AS lon
                """,
                "cell_tower",
            )
            # Also include backfilled nearest_location points from comms so tracks are denser
            for label, src in (("PhoneCall", "call"), ("Communication", "message"), ("Email", "email")):
                body_filter = "AND n.body IS NOT NULL" if label == "Communication" else ""
                _collect(
                    f"""
                    MATCH (n:{label} {{case_id:$case_id, source_type:'cellebrite'}})
                    WHERE coalesce(n.latitude, n.nearest_location_lat) IS NOT NULL
                      AND coalesce(n.longitude, n.nearest_location_lon) IS NOT NULL
                      AND n.timestamp IS NOT NULL
                      {rk_filter} {date_filter} {body_filter}
                    RETURN n.cellebrite_report_key AS rk, n.timestamp AS ts,
                           coalesce(n.latitude, n.nearest_location_lat) AS lat,
                           coalesce(n.longitude, n.nearest_location_lon) AS lon
                    """,
                    f"nearest_{src}",
                )

            # Fetch device metadata (device_model, phone_owner_name, color_hint)
            device_meta: Dict[str, dict] = {}
            r = session.run(
                """
                MATCH (r:PhoneReport {case_id:$case_id})
                OPTIONAL MATCH (r)-[:BELONGS_TO]->(owner:Person)
                RETURN r.key AS key, r.device_model AS model, owner.name AS owner
                """,
                case_id=case_id,
            )
            palette = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777"]
            for i, rec in enumerate(r):
                k = rec["key"]
                if k:
                    device_meta[k] = {
                        "device_model": rec["model"] or "Device",
                        "phone_owner_name": rec["owner"] or "",
                        "color_hint": palette[i % len(palette)],
                    }

        # Sort each device's points chronologically + optional simplify
        tracks = []
        for rk, pts in points_by_device.items():
            pts.sort(key=lambda p: p["timestamp"] or "")
            if simplify:
                pts = _simplify_points(pts, min_dist_m=50, min_time_s=60)
            meta = device_meta.get(rk, {"device_model": "Device", "phone_owner_name": "", "color_hint": "#2563eb"})
            tracks.append({
                "device_report_key": rk,
                "device_model": meta["device_model"],
                "phone_owner_name": meta["phone_owner_name"],
                "color_hint": meta["color_hint"],
                "points": pts,
            })

        return {"tracks": tracks}

    def get_cellebrite_event_detail(self, case_id: str, node_key: str) -> Optional[dict]:
        """Fetch one event's full properties (for the detail drawer)."""
        with self._driver.session() as session:
            # Try each label that might own this key
            for label in ("Location", "CellTower", "WirelessNetwork", "PhoneCall",
                          "Communication", "Email", "DeviceEvent", "AppSession",
                          "SearchedItem", "VisitedPage", "Meeting"):
                r = session.run(
                    f"MATCH (n:{label} {{case_id:$case_id, key:$key}}) RETURN properties(n) AS p LIMIT 1",
                    case_id=case_id, key=node_key,
                ).single()
                if r:
                    props = dict(r["p"])
                    props["_label"] = label
                    return props
        return None

    # ------------------------------------------------------------------
    # Phase 8: Overview drill-down detail queries
    # Each is scoped to a single (case_id, report_key) pair and paginates.
    # ------------------------------------------------------------------

    def get_overview_contacts(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All Person nodes from one device, with interaction counts."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(p.name, '')) CONTAINS toLower($search) "
                "OR any(num IN coalesce(p.phone_numbers, []) WHERE toLower(num) CONTAINS toLower($search)))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE p.key IS NOT NULL {search_clause}
                RETURN count(p) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (p:Person {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE p.key IS NOT NULL {search_clause}
                OPTIONAL MATCH (p)-[r1:CALLED|CALLED_TO]-(c:PhoneCall)
                WITH p, count(DISTINCT c) AS calls
                OPTIONAL MATCH (p)-[r2:SENT_MESSAGE]-(m:Communication)
                WITH p, calls, count(DISTINCT m) AS msgs_out
                OPTIONAL MATCH (p)-[:PARTICIPATED_IN]->(chat:Communication)
                OPTIONAL MATCH (msg:Communication)-[:PART_OF]->(chat)
                WHERE msg.body IS NOT NULL
                WITH p, calls, msgs_out, count(DISTINCT msg) AS msgs_chat
                OPTIONAL MATCH (p)-[:EMAILED|SENT_TO]-(e:Email)
                WITH p, calls, msgs_out, msgs_chat, count(DISTINCT e) AS emails
                RETURN p.key AS key,
                       p.name AS name,
                       p.phone_numbers AS phone_numbers,
                       p.is_phone_owner AS is_phone_owner,
                       p.cellebrite_id AS cellebrite_id,
                       p.all_identifiers AS all_identifiers,
                       calls,
                       msgs_out + msgs_chat AS messages,
                       emails,
                       calls + msgs_out + msgs_chat + emails AS interactions
                ORDER BY interactions DESC, name
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                rows.append({
                    "key": rec["key"],
                    "name": rec["name"] or rec["key"],
                    "phone_numbers": list(rec["phone_numbers"] or []),
                    "is_phone_owner": bool(rec["is_phone_owner"]),
                    "cellebrite_id": rec["cellebrite_id"],
                    "all_identifiers": list(rec["all_identifiers"] or []),
                    "calls": int(rec["calls"] or 0),
                    "messages": int(rec["messages"] or 0),
                    "emails": int(rec["emails"] or 0),
                    "interactions": int(rec["interactions"] or 0),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_calls(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All PhoneCalls from one device with parties resolved."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(c.source_app, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(c.direction, '')) CONTAINS toLower($search))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (c:PhoneCall {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN count(c) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (c:PhoneCall {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                OPTIONAL MATCH (src:Person)-[:CALLED]->(c)
                OPTIONAL MATCH (c)-[:CALLED_TO]->(dst:Person)
                RETURN c, src, dst
                ORDER BY c.timestamp DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                c = dict(rec["c"])
                src = dict(rec["src"]) if rec["src"] else None
                dst = dict(rec["dst"]) if rec["dst"] else None
                rows.append({
                    "key": c.get("key"),
                    "id": c.get("id"),
                    "node_key": c.get("key"),
                    "timestamp": c.get("timestamp"),
                    "date": c.get("date"),
                    "time": c.get("time"),
                    "direction": c.get("direction"),
                    "call_type": c.get("call_type"),
                    "duration": c.get("duration"),
                    "video_call": bool(c.get("video_call")),
                    "source_app": c.get("source_app"),
                    "deleted_state": c.get("deleted_state"),
                    "from_name": (src.get("name") if src else None),
                    "from_key": (src.get("key") if src else None),
                    "to_name": (dst.get("name") if dst else None),
                    "to_key": (dst.get("key") if dst else None),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_messages(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All individual messages (Communication with body) from one device."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = " AND toLower(coalesce(m.body, '')) CONTAINS toLower($search)"
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (m:Communication {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE m.body IS NOT NULL {search_clause}
                RETURN count(m) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (m:Communication {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE m.body IS NOT NULL {search_clause}
                OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(m)
                OPTIONAL MATCH (m)-[:PART_OF]->(chat:Communication)
                RETURN m, sender, chat
                ORDER BY m.timestamp DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                m = dict(rec["m"])
                sender = dict(rec["sender"]) if rec["sender"] else None
                chat = dict(rec["chat"]) if rec["chat"] else None
                body = m.get("body") or ""
                rows.append({
                    "key": m.get("key"),
                    "id": m.get("id"),
                    "node_key": m.get("key"),
                    "timestamp": m.get("timestamp"),
                    "date": m.get("date"),
                    "time": m.get("time"),
                    "source_app": m.get("source_app"),
                    "message_type": m.get("message_type"),
                    "body": body,
                    "body_preview": body[:160],
                    "deleted_state": m.get("deleted_state"),
                    "attachment_count": int(m.get("attachment_count") or 0),
                    "sender_name": (sender.get("name") if sender else None),
                    "sender_key": (sender.get("key") if sender else None),
                    "thread_id": (chat.get("key") if chat else None),
                    "thread_name": (chat.get("name") if chat else None),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_locations(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All Locations from one device."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(l.name, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(l.location_type, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(l.source_app, '')) CONTAINS toLower($search))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (l:Location {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN count(l) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (l:Location {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN l
                ORDER BY coalesce(l.timestamp, '') DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                l = dict(rec["l"])
                rows.append({
                    "key": l.get("key"),
                    "id": l.get("id"),
                    "node_key": l.get("key"),
                    "name": l.get("name"),
                    "location_type": l.get("location_type"),
                    "source_app": l.get("source_app"),
                    "latitude": l.get("latitude"),
                    "longitude": l.get("longitude"),
                    "timestamp": l.get("timestamp"),
                    "date": l.get("date"),
                    "time": l.get("time"),
                    "deleted_state": l.get("deleted_state"),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_emails(
        self,
        case_id: str,
        report_key: str,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        """All Emails from one device with sender + first recipient resolved."""
        params: Dict[str, Any] = {
            "case_id": case_id,
            "rk": report_key,
            "limit": int(limit),
            "offset": int(offset),
        }
        search_clause = ""
        if search:
            search_clause = (
                " AND (toLower(coalesce(e.subject, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(e.body, '')) CONTAINS toLower($search) "
                "OR toLower(coalesce(e.folder, '')) CONTAINS toLower($search))"
            )
            params["search"] = search

        with self._driver.session() as session:
            total = session.run(
                f"""
                MATCH (e:Email {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                RETURN count(e) AS n
                """,
                params,
            ).single()
            total_count = int(total["n"]) if total else 0

            result = session.run(
                f"""
                MATCH (e:Email {{case_id: $case_id, source_type: 'cellebrite', cellebrite_report_key: $rk}})
                WHERE 1=1 {search_clause}
                OPTIONAL MATCH (src:Person)-[:EMAILED]->(e)
                OPTIONAL MATCH (e)-[:SENT_TO]->(dst:Person)
                WITH e, src, collect(DISTINCT dst) AS dsts
                RETURN e, src, dsts
                ORDER BY e.timestamp DESC
                SKIP $offset LIMIT $limit
                """,
                params,
            )
            rows = []
            for rec in result:
                e = dict(rec["e"])
                src = dict(rec["src"]) if rec["src"] else None
                dsts = [dict(d) for d in rec["dsts"] if d is not None]
                first_dst = dsts[0] if dsts else None
                rows.append({
                    "key": e.get("key"),
                    "id": e.get("id"),
                    "node_key": e.get("key"),
                    "timestamp": e.get("timestamp"),
                    "date": e.get("date"),
                    "time": e.get("time"),
                    "subject": e.get("subject"),
                    "source_app": e.get("source_app"),
                    "folder": e.get("folder"),
                    "email_status": e.get("email_status"),
                    "from_name": (src.get("name") if src else None),
                    "from_key": (src.get("key") if src else None),
                    "to_name": (first_dst.get("name") if first_dst else None),
                    "to_key": (first_dst.get("key") if first_dst else None),
                    "to_count": len(dsts),
                    "attachment_count": int(e.get("attachment_count") or 0),
                    "deleted_state": e.get("deleted_state"),
                })
            return {"rows": rows, "total": total_count}

    def get_overview_contact_detail(
        self,
        case_id: str,
        report_key: str,
        contact_key: str,
        recent_limit: int = 50,
    ) -> Optional[dict]:
        """Fetch a single contact + their most recent comms with the phone owner."""
        with self._driver.session() as session:
            rec = session.run(
                """
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                RETURN p
                """,
                case_id=case_id,
                contact_key=contact_key,
            ).single()
            if not rec:
                return None
            p = dict(rec["p"])

            # Recent calls and messages involving this contact, on this device
            calls_rs = session.run(
                """
                MATCH (c:PhoneCall {case_id: $case_id, cellebrite_report_key: $rk})
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                WHERE (p)-[:CALLED]->(c) OR (c)-[:CALLED_TO]->(p)
                RETURN c
                ORDER BY c.timestamp DESC
                LIMIT $lim
                """,
                case_id=case_id,
                rk=report_key,
                contact_key=contact_key,
                lim=int(recent_limit),
            )
            recent_calls = [dict(r["c"]) for r in calls_rs]

            msgs_rs = session.run(
                """
                MATCH (m:Communication {case_id: $case_id, cellebrite_report_key: $rk})
                WHERE m.body IS NOT NULL
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                WHERE (p)-[:SENT_MESSAGE]->(m)
                   OR EXISTS { MATCH (m)-[:PART_OF]->(chat:Communication)<-[:PARTICIPATED_IN]-(p) }
                RETURN m
                ORDER BY m.timestamp DESC
                LIMIT $lim
                """,
                case_id=case_id,
                rk=report_key,
                contact_key=contact_key,
                lim=int(recent_limit),
            )
            recent_messages = [dict(r["m"]) for r in msgs_rs]

            return {
                "contact": {
                    "key": p.get("key"),
                    "name": p.get("name"),
                    "phone_numbers": list(p.get("phone_numbers") or []),
                    "is_phone_owner": bool(p.get("is_phone_owner")),
                    "cellebrite_id": p.get("cellebrite_id"),
                    "all_identifiers": list(p.get("all_identifiers") or []),
                },
                "recent_calls": [
                    {
                        "key": c.get("key"),
                        "timestamp": c.get("timestamp"),
                        "direction": c.get("direction"),
                        "call_type": c.get("call_type"),
                        "duration": c.get("duration"),
                        "source_app": c.get("source_app"),
                    }
                    for c in recent_calls
                ],
                "recent_messages": [
                    {
                        "key": m.get("key"),
                        "timestamp": m.get("timestamp"),
                        "source_app": m.get("source_app"),
                        "body": (m.get("body") or "")[:300],
                    }
                    for m in recent_messages
                ],
            }

    # ------------------------------------------------------------------
    # Phase 9: Communications drill-down per contact
    # ------------------------------------------------------------------

    def get_contact_comms_feed(
        self,
        case_id: str,
        contact_key: str,
        report_keys: Optional[List[str]] = None,
        types: Optional[List[str]] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """
        Chronological feed of every comm event involving a single Person,
        across all (or selected) devices. Used by the Communications tab
        drill-down drawer.

        types: subset of ['call', 'message', 'email'] — defaults to all three.
        """
        active = set(types) if types else {"call", "message", "email"}

        rk_filter = ""
        params: Dict[str, Any] = {"case_id": case_id, "contact_key": contact_key}
        if report_keys:
            rk_filter = "AND n.cellebrite_report_key IN $report_keys"
            params["report_keys"] = list(report_keys)

        items: list = []

        # Look up the contact for the header
        with self._driver.session() as session:
            contact_rec = session.run(
                """
                MATCH (p:Person {case_id: $case_id, key: $contact_key})
                RETURN p LIMIT 1
                """,
                case_id=case_id,
                contact_key=contact_key,
            ).single()
            contact = dict(contact_rec["p"]) if contact_rec else {}

            # Calls — either direction
            if "call" in active:
                rs = session.run(
                    f"""
                    MATCH (p:Person {{case_id: $case_id, key: $contact_key}})
                    MATCH (n:PhoneCall {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE ((p)-[:CALLED]->(n) OR (n)-[:CALLED_TO]->(p))
                      {rk_filter}
                    OPTIONAL MATCH (src:Person)-[:CALLED]->(n)
                    OPTIONAL MATCH (n)-[:CALLED_TO]->(dst:Person)
                    RETURN n, src, dst
                    ORDER BY n.timestamp DESC
                    LIMIT 2000
                    """,
                    params,
                )
                for rec in rs:
                    n = dict(rec["n"])
                    src = dict(rec["src"]) if rec["src"] else None
                    dst = dict(rec["dst"]) if rec["dst"] else None
                    items.append({
                        "id": n.get("id"),
                        "node_key": n.get("key"),
                        "type": "call",
                        "timestamp": n.get("timestamp"),
                        "source_app": n.get("source_app"),
                        "direction": n.get("direction"),
                        "call_type": n.get("call_type"),
                        "duration": n.get("duration"),
                        "video_call": bool(n.get("video_call")),
                        "deleted_state": n.get("deleted_state"),
                        "report_key": n.get("cellebrite_report_key"),
                        "attachment_file_ids": list(n.get("attachment_file_ids") or []),
                        "sender": {
                            "key": (src.get("key") if src else None),
                            "name": (src.get("name") if src else None),
                            "is_owner": bool(src.get("is_phone_owner")) if src else False,
                        } if src else None,
                        "recipient": {
                            "key": (dst.get("key") if dst else None),
                            "name": (dst.get("name") if dst else None),
                            "is_owner": bool(dst.get("is_phone_owner")) if dst else False,
                        } if dst else None,
                    })

            # Messages — either as sender, or as participant in a chat
            if "message" in active:
                rs = session.run(
                    f"""
                    MATCH (p:Person {{case_id: $case_id, key: $contact_key}})
                    MATCH (n:Communication {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE n.body IS NOT NULL
                      AND (
                        (p)-[:SENT_MESSAGE]->(n)
                        OR EXISTS {{
                          MATCH (n)-[:PART_OF]->(chat:Communication)<-[:PARTICIPATED_IN]-(p)
                        }}
                      )
                      {rk_filter}
                    OPTIONAL MATCH (sender:Person)-[:SENT_MESSAGE]->(n)
                    OPTIONAL MATCH (n)-[:PART_OF]->(chat:Communication)
                    RETURN n, sender, chat
                    ORDER BY n.timestamp DESC
                    LIMIT 4000
                    """,
                    params,
                )
                for rec in rs:
                    n = dict(rec["n"])
                    sender = dict(rec["sender"]) if rec["sender"] else None
                    chat = dict(rec["chat"]) if rec["chat"] else None
                    body = n.get("body") or ""
                    items.append({
                        "id": n.get("id"),
                        "node_key": n.get("key"),
                        "type": "message",
                        "timestamp": n.get("timestamp"),
                        "source_app": n.get("source_app"),
                        "message_type": n.get("message_type"),
                        "body": body,
                        "deleted_state": n.get("deleted_state"),
                        "report_key": n.get("cellebrite_report_key"),
                        "attachment_file_ids": list(n.get("attachment_file_ids") or []),
                        "thread_id": (chat.get("key") if chat else None),
                        "thread_name": (chat.get("name") if chat else None),
                        "sender": {
                            "key": (sender.get("key") if sender else None),
                            "name": (sender.get("name") if sender else None),
                            "is_owner": bool(sender.get("is_phone_owner")) if sender else False,
                        } if sender else None,
                    })

            # Emails — sent or received
            if "email" in active:
                rs = session.run(
                    f"""
                    MATCH (p:Person {{case_id: $case_id, key: $contact_key}})
                    MATCH (n:Email {{case_id: $case_id, source_type: 'cellebrite'}})
                    WHERE ((p)-[:EMAILED]->(n) OR (n)-[:SENT_TO]->(p))
                      {rk_filter}
                    OPTIONAL MATCH (src:Person)-[:EMAILED]->(n)
                    OPTIONAL MATCH (n)-[:SENT_TO]->(dst:Person)
                    WITH n, src, collect(DISTINCT dst) AS dsts
                    RETURN n, src, dsts
                    ORDER BY n.timestamp DESC
                    LIMIT 1000
                    """,
                    params,
                )
                for rec in rs:
                    n = dict(rec["n"])
                    src = dict(rec["src"]) if rec["src"] else None
                    dsts = [dict(d) for d in rec["dsts"] if d is not None]
                    first_dst = dsts[0] if dsts else None
                    items.append({
                        "id": n.get("id"),
                        "node_key": n.get("key"),
                        "type": "email",
                        "timestamp": n.get("timestamp"),
                        "source_app": n.get("source_app"),
                        "subject": n.get("subject"),
                        "body": n.get("body") or "",
                        "folder": n.get("folder"),
                        "email_status": n.get("email_status"),
                        "deleted_state": n.get("deleted_state"),
                        "report_key": n.get("cellebrite_report_key"),
                        "attachment_file_ids": list(n.get("attachment_file_ids") or []),
                        "sender": {
                            "key": (src.get("key") if src else None),
                            "name": (src.get("name") if src else None),
                            "is_owner": bool(src.get("is_phone_owner")) if src else False,
                        } if src else None,
                        "recipient": {
                            "key": (first_dst.get("key") if first_dst else None),
                            "name": (first_dst.get("name") if first_dst else None),
                            "is_owner": bool(first_dst.get("is_phone_owner")) if first_dst else False,
                        } if first_dst else None,
                        "recipient_count": len(dsts),
                    })

        # Sort newest-first, paginate
        items.sort(key=lambda i: (i.get("timestamp") or ""), reverse=True)
        total = len(items)
        items = items[offset: offset + limit]

        return {
            "contact": {
                "key": contact.get("key"),
                "name": contact.get("name"),
                "phone_numbers": list(contact.get("phone_numbers") or []),
                "is_phone_owner": bool(contact.get("is_phone_owner")),
                "all_identifiers": list(contact.get("all_identifiers") or []),
            } if contact else None,
            "items": items,
            "total": total,
        }


# ---------------------------------------------------------------------------
# Helpers for event projections (used by get_cellebrite_events)
# ---------------------------------------------------------------------------


def _project_event(node, event_type: str) -> Optional[dict]:
    """Base projection for event-like nodes into the unified shape."""
    if not node:
        return None
    n = dict(node)
    lat = n.get("latitude") if n.get("latitude") is not None else n.get("nearest_location_lat")
    lon = n.get("longitude") if n.get("longitude") is not None else n.get("nearest_location_lon")
    is_geo = lat is not None and lon is not None
    direct_geo = n.get("latitude") is not None and n.get("longitude") is not None
    loc_source = "direct" if direct_geo else ("nearest" if is_geo else "none")

    label = n.get("name") or event_type.title()
    return {
        "id": n.get("id") or n.get("key"),
        "node_key": n.get("key"),
        "label": label,
        "summary": (n.get("body") or n.get("summary") or n.get("name") or "")[:200],
        "timestamp": n.get("timestamp"),
        "latitude": lat,
        "longitude": lon,
        "source_app": n.get("source_app"),
        "direction": n.get("direction"),
        "duration": n.get("duration") or n.get("duration_s"),
        "device_report_key": n.get("cellebrite_report_key"),
        "counterpart": None,
        "thread_id": None,
        "is_geolocated": bool(is_geo),
        "location_source": loc_source,
        "attachment_count": int(n.get("attachment_count") or 0),
        "state": n.get("state"),
        "app_name": n.get("app_name"),
    }


def _project_call(node, src, dst) -> Optional[dict]:
    row = _project_event(node, "call")
    if not row:
        return None
    n = dict(node)
    label = "Call"
    if n.get("direction"):
        label = f"Call ({n['direction']})"
    if n.get("call_type") and n.get("call_type") != "Regular":
        label += f" — {n['call_type']}"
    row["label"] = label
    counter_node = dst if (src is None or (src and dict(src).get("is_phone_owner"))) else src
    if counter_node:
        c = dict(counter_node)
        row["counterpart"] = {"key": c.get("key"), "name": c.get("name") or c.get("key")}
    return row


def _project_message(node, sender, chat) -> Optional[dict]:
    row = _project_event(node, "message")
    if not row:
        return None
    n = dict(node)
    row["label"] = (n.get("source_app") or "Message") + " message"
    row["summary"] = (n.get("body") or "")[:200]
    if sender:
        s = dict(sender)
        row["counterpart"] = {"key": s.get("key"), "name": s.get("name") or s.get("key")}
    if chat:
        row["thread_id"] = dict(chat).get("key")
    return row


def _project_email(node, src, dst) -> Optional[dict]:
    row = _project_event(node, "email")
    if not row:
        return None
    n = dict(node)
    row["label"] = "Email"
    row["summary"] = (n.get("subject") or n.get("body") or "")[:200]
    counter_node = dst if (src is None or (src and dict(src).get("is_phone_owner"))) else src
    if counter_node:
        c = dict(counter_node)
        row["counterpart"] = {"key": c.get("key"), "name": c.get("name") or c.get("key")}
    return row


def _simplify_points(points: List[dict], min_dist_m: float = 50.0, min_time_s: float = 60.0) -> List[dict]:
    """Drop consecutive points closer than (min_dist_m AND min_time_s) to the previous kept point."""
    import math
    if not points:
        return points
    def haversine(a, b):
        R = 6371000.0
        lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
        dlat = lat2 - lat1
        dlon = math.radians(b["lon"] - a["lon"])
        h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return 2 * R * math.asin(math.sqrt(h))
    def _ts_sec(p):
        try:
            from datetime import datetime
            return datetime.fromisoformat((p["timestamp"] or "").replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0
    out = [points[0]]
    last = points[0]
    last_t = _ts_sec(last)
    for p in points[1:]:
        t = _ts_sec(p)
        if haversine(last, p) < min_dist_m and abs(t - last_t) < min_time_s:
            continue
        out.append(p)
        last = p
        last_t = t
    return out


# ---------------------------------------------------------------------------
# Phase 5 — Files Explorer helpers (attach parent-entity context to files)
# ---------------------------------------------------------------------------


def resolve_file_parents(
    driver,
    case_id: str,
    model_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    For a batch of Cellebrite model_ids, return a map model_id -> {label, name, source_app, key}.
    Used by the Files Explorer to show "this attachment belongs to Chat (WhatsApp)".
    """
    if not model_ids:
        return {}
    ids = [m for m in model_ids if m]
    if not ids:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with driver.session() as session:
        rs = session.run(
            """
            MATCH (n {case_id: $case_id, source_type: 'cellebrite'})
            WHERE n.cellebrite_id IN $ids
            RETURN n.cellebrite_id AS mid,
                   labels(n)[0] AS label,
                   n.name AS name,
                   n.source_app AS source_app,
                   n.key AS key,
                   n.body AS body,
                   n.subject AS subject,
                   n.timestamp AS timestamp
            """,
            case_id=case_id,
            ids=ids,
        )
        for rec in rs:
            mid = rec["mid"]
            if not mid:
                continue
            out[mid] = {
                "label": rec["label"],
                "name": rec["name"] or rec["subject"] or (rec["body"] or "")[:60],
                "source_app": rec["source_app"],
                "key": rec["key"],
                "timestamp": rec["timestamp"],
            }
    return out


# Singleton instance
neo4j_service = Neo4jService()
