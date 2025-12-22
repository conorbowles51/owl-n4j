"""
Neo4j Service - handles all database operations for the investigation console.
"""

from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase
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

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    # -------------------------------------------------------------------------
    # Graph Visualization Data
    # -------------------------------------------------------------------------

    def get_full_graph(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, List]:
        """
        Get all nodes and relationships for visualization.
        
        Args:
            start_date: Filter to include nodes with date >= start_date (YYYY-MM-DD) or connected to such nodes
            end_date: Filter to include nodes with date <= end_date (YYYY-MM-DD) or connected to such nodes

        Returns:
            Dict with 'nodes' and 'links' arrays
        """
        with self._driver.session() as session:
            # Build date filter query
            if start_date or end_date:
                # Find nodes in date range and all nodes connected to them
                date_conditions = []
                params = {}
                
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
                    WHERE n.date IS NOT NULL
                    {date_filter}
                    
                    // Collect all nodes in range and their connections (up to 2 hops)
                    WITH collect(DISTINCT n) AS nodes_in_range
                    UNWIND nodes_in_range AS start_node
                    
                    // Find all nodes connected to nodes in range (up to 2 hops)
                    MATCH path = (start_node)-[*0..2]-(connected)
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
                # No date filter - get all nodes
                query = """
                    MATCH (n)
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
                params = {}
            
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
                rels_query = """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $node_keys AND b.key IN $node_keys
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                rels_result = session.run(rels_query, node_keys=keys_list)
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

    def get_node_with_neighbours(self, key: str, depth: int = 1) -> Dict[str, List]:
        """
        Get a node and its neighbours up to specified depth.

        Args:
            key: The node key
            depth: How many hops to traverse (default 1)

        Returns:
            Dict with 'nodes' and 'links' arrays
        """
        with self._driver.session() as session:
            # Get the central node and neighbours
            result = session.run(
                f"""
                MATCH path = (center {{key: $key}})-[*1..{depth}]-(neighbour)
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
                key=key,
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

            # Get relationships between these nodes
            if seen_keys:
                rels_result = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE a.key IN $keys AND b.key IN $keys
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                    """,
                    keys=list(seen_keys),
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

    def get_node_details(self, key: str) -> Optional[Dict]:
        """
        Get detailed information about a single node.

        Args:
            key: The node key

        Returns:
            Node details dict or None, including parsed verified_facts and ai_insights
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n {key: $key})
                OPTIONAL MATCH (n)-[r]-(connected)
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
                key=key,
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

    def search_nodes(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search nodes by name, key, summary, or notes.

        Args:
            query: Search string
            limit: Max results

        Returns:
            List of matching nodes
        """
        with self._driver.session() as session:
            # Use a more robust search that handles null values and text normalization
            # Normalize the search term to lowercase for case-insensitive matching
            search_lower = query.lower().strip()
            result = session.run(
                """
                MATCH (n)
                WHERE (
                    (n.name IS NOT NULL AND toLower(n.name) CONTAINS $search_lower)
                    OR (n.key IS NOT NULL AND toLower(n.key) CONTAINS $search_lower)
                    OR (n.summary IS NOT NULL AND toLower(n.summary) CONTAINS $search_lower)
                    OR (n.notes IS NOT NULL AND size(n.notes) > 0 AND toLower(n.notes) CONTAINS $search_lower)
                )
                RETURN 
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes
                LIMIT $limit
                """,
                search_lower=search_lower,
                limit=limit,
            )
            return [dict(r) for r in result]

    # -------------------------------------------------------------------------
    # Context for AI
    # -------------------------------------------------------------------------

    def get_graph_summary(self) -> Dict:
        """
        Get a summary of the entire graph for AI context.

        Returns:
            Dict with entity counts, types, and key entities
        """
        with self._driver.session() as session:
            # Count by type
            type_counts = session.run(
                """
                MATCH (n)
                RETURN labels(n)[0] AS type, count(*) AS count
                ORDER BY count DESC
                """
            )
            types = {r["type"]: r["count"] for r in type_counts}

            # Get all entities with summaries or notes (for AI context)
            entities_result = session.run(
                """
                MATCH (n)
                WHERE n.summary IS NOT NULL OR n.notes IS NOT NULL
                RETURN 
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary,
                    n.notes AS notes
                ORDER BY n.name
                """
            )
            entities = [dict(r) for r in entities_result]

            # Get relationship summary
            rel_counts = session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(*) AS count
                ORDER BY count DESC
                """
            )
            relationships = {r["type"]: r["count"] for r in rel_counts}

        return {
            "entity_types": types,
            "relationship_types": relationships,
            "total_nodes": sum(types.values()),
            "total_relationships": sum(relationships.values()),
            "entities": entities,
        }

    def get_context_for_nodes(self, keys: List[str]) -> Dict:
        """
        Get detailed context for specific nodes (for focused AI queries).

        Args:
            keys: List of node keys to get context for

        Returns:
            Dict with detailed information about selected nodes
        """
        with self._driver.session() as session:
            # Get selected nodes with their connections
            result = session.run(
                """
                MATCH (n)
                WHERE n.key IN $keys
                OPTIONAL MATCH (n)-[r]-(connected)
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
    ) -> List[Dict]:
        """
        Get all entities that have geocoded locations.
        
        Args:
            entity_types: Optional filter for specific entity types
            
        Returns:
            List of entities with lat/lng coordinates
        """
        with self._driver.session() as session:
            type_filter = ""
            params = {}
            
            if entity_types:
                type_filter = "AND labels(n)[0] IN $types"
                params["types"] = entity_types
            
            query = f"""
                MATCH (n)
                WHERE n.latitude IS NOT NULL 
                  AND n.longitude IS NOT NULL
                  AND NOT n:Document
                  {type_filter}
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE NOT connected:Document
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
    ) -> List[Dict]:
        """
        Get all nodes that have dates, sorted chronologically.
        
        Args:
            event_types: Filter by specific types (e.g., ['Transaction', 'Payment']).
                        If None, returns ALL entities with dates (not just event types).
            start_date: Filter events on or after this date (YYYY-MM-DD)
            end_date: Filter events on or before this date (YYYY-MM-DD)
        
        Returns:
            List of nodes with their connected entities, sorted by date
        """
        with self._driver.session() as session:
            # Build date filter conditions
            date_conditions = []
            params = {}
            
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
            
            query = f"""
                MATCH (n)
                WHERE n.date IS NOT NULL
                {type_filter}
                {date_filter}
                OPTIONAL MATCH (n)-[r]-(connected)
                WHERE NOT connected:Document AND NOT connected:Case
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
            
    def get_shortest_paths_subgraph(self, node_keys: List[str], max_depth: int = 10) -> Dict[str, List]:
        """
        Find shortest paths between all pairs of selected nodes and return as subgraph.
        
        For multiple nodes, finds shortest paths between all pairs and combines them.
        
        Args:
            node_keys: List of node keys to find paths between
            max_depth: Maximum path length to search (default 10)
        
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
                    
                    # Find shortest path between this pair
                    # Note: Neo4j doesn't support parameters in variable-length patterns,
                    # so we use string formatting for max_depth (validated as int)
                    result = session.run(
                        f"""
                        MATCH path = shortestPath((a {{key: $key1}})-[*..{int(max_depth)}]-(b {{key: $key2}}))
                        WHERE a.key = $key1 AND b.key = $key2
                        RETURN path
                        """,
                        key1=key1,
                        key2=key2
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
            
            # Get full node details for all nodes in paths
            if not all_nodes:
                return {"nodes": [], "links": []}
            
            nodes_query = """
                MATCH (n)
                WHERE n.key IN $keys
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
            
            nodes_result = session.run(nodes_query, keys=list(all_nodes))
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
        damping_factor: float = 0.85
    ) -> Dict:
        """
        Calculate PageRank for nodes and return top influential nodes as subgraph.
        
        Args:
            node_keys: Optional list of node keys to focus on (and their connections).
                      If None, runs on full graph.
            top_n: Number of top influential nodes to return
            iterations: Number of PageRank iterations
            damping_factor: Damping factor (typically 0.85)
        
        Returns:
            Dict with 'nodes' (sorted by PageRank score), 'links', and 'scores' (PageRank scores)
        """
        with self._driver.session() as session:
            # Step 1: Build the graph to analyze
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes
                    WITH collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
                    UNWIND allNodes AS node
                    RETURN DISTINCT node.key AS key
                """
                result = session.run(graph_query, node_keys=node_keys)
                focus_keys = [record["key"] for record in result if record["key"]]
                
                if not focus_keys:
                    return {"nodes": [], "links": [], "scores": {}}
                
                # Get all nodes and relationships in the focused subgraph
                nodes_query = """
                    MATCH (n)
                    WHERE n.key IN $keys
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
                    WHERE a.key IN $keys AND b.key IN $keys
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, keys=focus_keys)
                links_result = session.run(links_query, keys=focus_keys)
            else:
                # Use full graph
                nodes_query = """
                    MATCH (n)
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
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query)
                links_result = session.run(links_query)
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
        max_iterations: int = 10
    ) -> Dict:
        """
        Detect communities using Louvain modularity algorithm.
        
        Args:
            node_keys: Optional list of node keys to focus on (and their connections).
                      If None, runs on full graph.
            resolution: Resolution parameter for modularity (higher = more communities)
            max_iterations: Maximum number of iterations
        
        Returns:
            Dict with 'nodes' (with community_id), 'links', and 'communities' (community info)
        """
        with self._driver.session() as session:
            # Step 1: Build the graph to analyze
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes
                    WITH collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
                    UNWIND allNodes AS node
                    RETURN DISTINCT node.key AS key
                """
                result = session.run(graph_query, node_keys=node_keys)
                focus_keys = [record["key"] for record in result if record["key"]]
                
                if not focus_keys:
                    return {"nodes": [], "links": [], "communities": {}}
                
                # Get all nodes and relationships in the focused subgraph
                nodes_query = """
                    MATCH (n)
                    WHERE n.key IN $keys
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
                    WHERE a.key IN $keys AND b.key IN $keys
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, keys=focus_keys)
                links_result = session.run(links_query, keys=focus_keys)
            else:
                # Use full graph
                nodes_query = """
                    MATCH (n)
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
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query)
                links_result = session.run(links_query)
            
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
        normalized: bool = True
    ) -> Dict:
        """
        Calculate betweenness centrality for nodes.
        
        Betweenness centrality measures how often a node appears on the shortest path
        between other nodes. Nodes with high betweenness are important bridges.
        
        Args:
            node_keys: Optional list of node keys to focus on (and their connections).
                      If None, runs on full graph.
            top_n: Number of top nodes by betweenness to return
            normalized: Whether to normalize scores (divide by (n-1)(n-2)/2 for undirected)
        
        Returns:
            Dict with 'nodes' (sorted by betweenness), 'links', and 'scores'
        """
        from collections import deque, defaultdict
        
        with self._driver.session() as session:
            # Step 1: Build the graph to analyze
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes
                    WITH collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
                    UNWIND allNodes AS node
                    RETURN DISTINCT node.key AS key
                """
                result = session.run(graph_query, node_keys=node_keys)
                focus_keys = [record["key"] for record in result if record["key"]]
                
                if not focus_keys:
                    return {"nodes": [], "links": [], "scores": {}}
                
                # Get all nodes and relationships in the focused subgraph
                nodes_query = """
                    MATCH (n)
                    WHERE n.key IN $keys
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
                    WHERE a.key IN $keys AND b.key IN $keys
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query, keys=focus_keys)
                links_result = session.run(links_query, keys=focus_keys)
            else:
                # Use full graph
                nodes_query = """
                    MATCH (n)
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
                    RETURN 
                        a.key AS source,
                        b.key AS target,
                        type(r) AS type,
                        properties(r) AS properties
                """
                nodes_result = session.run(nodes_query)
                links_result = session.run(links_query)
            
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

    def pin_fact(self, node_key: str, fact_index: int, pinned: bool) -> Dict:
        """
        Toggle the pinned status of a verified fact.
        
        Args:
            node_key: The node's key
            fact_index: Index of the fact in the verified_facts array
            pinned: True to pin, False to unpin
            
        Returns:
            Updated verified_facts array
        """
        with self._driver.session() as session:
            # Get current verified_facts
            result = session.run(
                """
                MATCH (n {key: $key})
                RETURN n.verified_facts AS verified_facts
                """,
                key=node_key,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key}")
            
            verified_facts = parse_json_field(record["verified_facts"]) or []
            
            if fact_index < 0 or fact_index >= len(verified_facts):
                raise ValueError(f"Invalid fact index: {fact_index}")
            
            # Update the pinned status
            verified_facts[fact_index]["pinned"] = pinned
            
            # Save back to Neo4j
            session.run(
                """
                MATCH (n {key: $key})
                SET n.verified_facts = $verified_facts
                """,
                key=node_key,
                verified_facts=json.dumps(verified_facts),
            )
            
            return verified_facts

    def verify_insight(
        self, 
        node_key: str, 
        insight_index: int, 
        username: str,
        source_doc: Optional[str] = None,
        page: Optional[int] = None
    ) -> Dict:
        """
        Convert an AI insight to a verified fact with user attribution.
        
        Args:
            node_key: The node's key
            insight_index: Index of the insight in the ai_insights array
            username: Username of the verifying investigator
            source_doc: Optional source document for the verification
            page: Optional page number in the source document
            
        Returns:
            Dict with updated verified_facts and ai_insights arrays
        """
        from datetime import datetime
        
        with self._driver.session() as session:
            # Get current facts and insights
            result = session.run(
                """
                MATCH (n {key: $key})
                RETURN n.verified_facts AS verified_facts, n.ai_insights AS ai_insights
                """,
                key=node_key,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Node not found: {node_key}")
            
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
            
            # Save back to Neo4j
            session.run(
                """
                MATCH (n {key: $key})
                SET n.verified_facts = $verified_facts, n.ai_insights = $ai_insights
                """,
                key=node_key,
                verified_facts=json.dumps(verified_facts),
                ai_insights=json.dumps(ai_insights),
            )
            
            return {
                "verified_facts": verified_facts,
                "ai_insights": ai_insights,
            }


# Singleton instance
neo4j_service = Neo4jService()
