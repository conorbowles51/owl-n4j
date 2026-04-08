"""
Graph visualization service.

Provides methods for retrieving graph structure, node details, search,
and AI context from Neo4j.  Extracted from the monolithic neo4j_service.py
so that graph-related queries live in a dedicated module.
"""

from typing import Dict, List, Optional
import json
import logging

from services.neo4j.driver import driver, parse_json_field, safe_float

logger = logging.getLogger(__name__)


class GraphService:
    """Graph visualization, search, and AI-context queries."""

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
        with driver.session() as session:
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
        with driver.session() as session:
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
                           n.confidence AS confidence, properties(n) AS node_props
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
                            "mentioned": (record.get("node_props") or {}).get("mentioned"),
                        })

                links = []
                if node_keys:
                    rels_result = session.run(
                        """
                        MATCH (a)-[r]->(b)
                        WHERE a.key IN $node_keys AND b.key IN $node_keys
                          AND r.case_id = $case_id
                        RETURN a.key AS source, b.key AS target,
                               type(r) AS type, properties(r) AS rel_props
                        """,
                        node_keys=list(node_keys), case_id=case_id,
                    )
                    for record in rels_result:
                        links.append({
                            "source": record["source"],
                            "target": record["target"],
                            "type": record["type"],
                            "weight": (record.get("rel_props") or {}).get("weight"),
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
                        properties(node) AS node_props
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
                        properties(n) AS node_props
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
                        "mentioned": (record.get("node_props") or {}).get("mentioned"),
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
                        properties(r) AS rel_props
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
                    "weight": (record.get("rel_props") or {}).get("weight"),
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
        with driver.session() as session:
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

        with driver.session() as session:
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
        with driver.session() as session:
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
        with driver.session() as session:
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
        with driver.session() as session:
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
        with driver.session() as session:
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


graph_service = GraphService()
