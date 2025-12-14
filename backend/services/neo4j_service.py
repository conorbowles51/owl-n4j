"""
Neo4j Service - handles all database operations for the investigation console.
"""

from typing import Dict, List, Optional, Any
from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD


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
                    node = {
                        "neo4j_id": record["neo4j_id"],
                        "id": record["id"] or node_key,
                        "key": node_key,
                        "name": record["name"] or node_key,
                        "type": record["type"],
                        "summary": record["summary"],
                        "notes": record["notes"],
                        "properties": record["properties"],
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
            Node details dict or None
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
                return {
                    "id": record["id"],
                    "key": record["key"],
                    "name": record["name"],
                    "type": record["type"],
                    "summary": record["summary"],
                    "notes": record["notes"],
                    "properties": record["properties"],
                    "connections": [c for c in record["connections"] if c["key"]],
                }
        return None

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def search_nodes(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search nodes by name or key.

        Args:
            query: Search string
            limit: Max results

        Returns:
            List of matching nodes
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($search_term)
                   OR toLower(n.key) CONTAINS toLower($search_term)
                RETURN 
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary
                LIMIT $limit
                """,
                search_term=query,
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

            # Get all entities with summaries
            entities_result = session.run(
                """
                MATCH (n)
                WHERE n.summary IS NOT NULL
                RETURN 
                    n.key AS key,
                    n.name AS name,
                    labels(n)[0] AS type,
                    n.summary AS summary
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
            query: Cypher query string
            params: Query parameters

        Returns:
            List of result records as dicts
        """
        with self._driver.session() as session:
            result = session.run(query, params or {})
            return [dict(r) for r in result]
        

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


# Singleton instance
neo4j_service = Neo4jService()
