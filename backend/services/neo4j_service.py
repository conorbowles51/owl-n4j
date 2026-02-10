"""
Neo4j Service - handles all database operations for the investigation console.
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from neo4j import GraphDatabase
import math
import random
import json

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
            result = session.run(
                """
                MATCH (n)
                WHERE n.key IN $keys
                  AND n.case_id = $case_id
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE connected.case_id = $case_id
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes,
                    collect(DISTINCT {
                        key: connected.key,
                        name: connected.name,
                        type: labels(connected)[0],
                        summary: connected.summary,
                        relationship: type(r),
                        direction: CASE WHEN startNode(r) = n THEN 'outgoing' ELSE 'incoming' END
                    }) AS connections
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
            
            # Step 2: Louvain Algorithm
            # Initialize: each node in its own community
            community = {key: i for i, key in enumerate(all_nodes.keys())}
            node_to_community = {key: i for i, key in enumerate(all_nodes.keys())}
            
            # Calculate modularity
            def calculate_modularity(communities, adj, deg, m, gamma):
                """Calculate modularity with resolution parameter."""
                if m == 0:
                    return 0.0
                
                q = 0.0
                for node in communities.keys():
                    node_comm = communities[node]
                    for neighbor in adj.get(node, []):
                        if neighbor in communities:
                            neighbor_comm = communities[neighbor]
                            # A_ij - gamma * (k_i * k_j) / (2m)
                            a_ij = 1.0 if neighbor in adj.get(node, []) else 0.0
                            k_i = deg.get(node, 0)
                            k_j = deg.get(neighbor, 0)
                            if node_comm == neighbor_comm:
                                q += a_ij - gamma * (k_i * k_j) / (2.0 * m)
                return q / (2.0 * m)
            
            # Louvain iteration
            improved = True
            iteration = 0
            
            while improved and iteration < max_iterations:
                improved = False
                iteration += 1
                
                # Try moving each node to a neighboring community
                nodes_list = list(all_nodes.keys())
                random.shuffle(nodes_list)  # Randomize order for better convergence
                
                for node in nodes_list:
                    if node not in adjacency or len(adjacency[node]) == 0:
                        continue
                    
                    current_comm = node_to_community[node]
                    best_comm = current_comm
                    best_delta = 0.0
                    
                    # Check all neighboring communities
                    neighbor_communities = set()
                    for neighbor in adjacency[node]:
                        if neighbor in node_to_community:
                            neighbor_communities.add(node_to_community[neighbor])
                    
                    # Also check current community
                    neighbor_communities.add(current_comm)
                    
                    # Calculate delta modularity for each possible move
                    for new_comm in neighbor_communities:
                        if new_comm == current_comm:
                            continue
                        
                        # Simplified delta calculation
                        # Delta Q = (sum_in - sum_tot * k_i / (2m)) - (sum_in_old - sum_tot_old * k_i / (2m))
                        k_i = degree.get(node, 0)
                        if total_edges == 0:
                            continue
                        
                        # Count edges to new community
                        edges_to_new_comm = sum(
                            1 for neighbor in adjacency[node]
                            if neighbor in node_to_community and node_to_community[neighbor] == new_comm
                        )
                        
                        # Count edges to current community
                        edges_to_current_comm = sum(
                            1 for neighbor in adjacency[node]
                            if neighbor in node_to_community and node_to_community[neighbor] == current_comm
                        )
                        
                        # Simplified delta (approximation)
                        delta = (edges_to_new_comm - edges_to_current_comm) / total_edges
                        delta -= resolution * k_i * (
                            sum(degree.get(n, 0) for n, c in node_to_community.items() if c == new_comm) -
                            sum(degree.get(n, 0) for n, c in node_to_community.items() if c == current_comm)
                        ) / (2.0 * total_edges * total_edges)
                        
                        if delta > best_delta:
                            best_delta = delta
                            best_comm = new_comm
                    
                    # Move node if improvement found
                    if best_comm != current_comm and best_delta > 0:
                        node_to_community[node] = best_comm
                        improved = True
            
            # Step 3: Build result with community information
            # Renumber communities to be sequential
            unique_communities = sorted(set(node_to_community.values()))
            community_map = {old: new for new, old in enumerate(unique_communities)}
            final_communities = {key: community_map[node_to_community[key]] for key in all_nodes.keys()}
            
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
        name_similarity_threshold: float = 0.7,
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
        name_similarity_threshold: float = 0.7,
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
            
            # Delete source entity
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

    def get_financial_transactions(
        self,
        case_id: str,
        types: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        categories: Optional[List[str]] = None,
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

            extra_filter = (" AND " + " AND ".join(conditions)) if conditions else ""

            query = f"""
                MATCH (n)
                WHERE n.amount IS NOT NULL
                AND n.case_id = $case_id
                {extra_filter}
                OPTIONAL MATCH (n)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(to_entity)
                WHERE to_entity.case_id = $case_id AND NOT to_entity:Document AND NOT to_entity:Case
                OPTIONAL MATCH (from_entity)-[:TRANSFERRED_TO|SENT_TO|PAID_TO|ISSUED_TO]->(n)
                WHERE from_entity.case_id = $case_id AND NOT from_entity:Document AND NOT from_entity:Case
                OPTIONAL MATCH (n)-[:RECEIVED_FROM]->(rf_entity)
                WHERE rf_entity.case_id = $case_id AND NOT rf_entity:Document AND NOT rf_entity:Case
                OPTIONAL MATCH (n)<-[:MADE_PAYMENT|INITIATED]-(initiator)
                WHERE initiator.case_id = $case_id AND NOT initiator:Document AND NOT initiator:Case
                RETURN
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.date AS date,
                    n.time AS time,
                    toFloat(replace(replace(toString(n.amount), '$', ''), ',', '')) AS amount,
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
                    collect(DISTINCT to_entity.key)[0] AS rel_to_key,
                    collect(DISTINCT to_entity.name)[0] AS rel_to_name,
                    collect(DISTINCT from_entity.key)[0] AS rel_from_key,
                    collect(DISTINCT from_entity.name)[0] AS rel_from_name,
                    collect(DISTINCT rf_entity.key)[0] AS rf_key,
                    collect(DISTINCT rf_entity.name)[0] AS rf_name,
                    collect(DISTINCT initiator.key)[0] AS initiator_key,
                    collect(DISTINCT initiator.name)[0] AS initiator_name
                ORDER BY n.date ASC, n.time ASC
            """

            result = session.run(query, **params)
            transactions = []
            for record in result:
                # Resolve from entity: manual override > relationship-derived
                from_key = record["from_entity_key"] or record["rel_from_key"] or record["initiator_key"]
                from_name = record["from_entity_name"] or record["rel_from_name"] or record["initiator_name"]
                # Resolve to entity: manual override > relationship-derived
                to_key = record["to_entity_key"] or record["rel_to_key"] or record["rf_key"]
                to_name = record["to_entity_name"] or record["rel_to_name"] or record["rf_name"]

                amount_val = safe_float(record["amount"])

                transactions.append({
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "date": record["date"],
                    "time": record["time"],
                    "amount": amount_val,
                    "currency": record["currency"],
                    "summary": record["summary"],
                    "financial_category": record["financial_category"] or "Uncategorized",
                    "purpose": record["purpose"],
                    "counterparty_details": record["counterparty_details"],
                    "notes": record["notes"],
                    "from_entity": {"key": from_key, "name": from_name} if from_key else None,
                    "to_entity": {"key": to_key, "name": to_name} if to_key else None,
                    "has_manual_from": record["from_entity_key"] is not None,
                    "has_manual_to": record["to_entity_key"] is not None,
                })
            return transactions

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

            if from_key is not None:
                set_clauses.append("n.from_entity_key = $from_key")
                set_clauses.append("n.from_entity_name = $from_name")
                params["from_key"] = from_key
                params["from_name"] = from_name
            if to_key is not None:
                set_clauses.append("n.to_entity_key = $to_key")
                set_clauses.append("n.to_entity_name = $to_name")
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


# Singleton instance
neo4j_service = Neo4jService()
