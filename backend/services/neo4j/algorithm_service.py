"""
Algorithm Service — graph algorithm operations: shortest paths, PageRank,
Louvain community detection, and betweenness centrality.
"""

import logging
import math
import random
from typing import Any, Dict, List, Optional

from services.neo4j.driver import driver, parse_json_field

logger = logging.getLogger(__name__)


class AlgorithmService:

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

        with driver.session() as session:
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
                          AND all(node IN nodes(path) WHERE node.case_id = $case_id
                            AND NOT node:RecycleBin AND NOT node:RecycleBinItem
                            AND coalesce(node.system_node, false) <> true)
                          AND all(rel IN relationships(path) WHERE rel.case_id = $case_id)
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
                  AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                  AND coalesce(n.system_node, false) <> true
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
        with driver.session() as session:
            # Step 1: Build the graph to analyze - always filter by case_id
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys AND n.case_id = $case_id
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes AND connected.case_id = $case_id
                      AND NOT connected:RecycleBin AND NOT connected:RecycleBinItem
                      AND coalesce(connected.system_node, false) <> true
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
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
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
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
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
                      AND NOT a:RecycleBin AND NOT a:RecycleBinItem
                      AND NOT b:RecycleBin AND NOT b:RecycleBinItem
                      AND coalesce(a.system_node, false) <> true
                      AND coalesce(b.system_node, false) <> true
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
        with driver.session() as session:
            # Step 1: Build the graph to analyze - always filter by case_id
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys AND n.case_id = $case_id
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes AND connected.case_id = $case_id
                      AND NOT connected:RecycleBin AND NOT connected:RecycleBinItem
                      AND coalesce(connected.system_node, false) <> true
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
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
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
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
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
                      AND NOT a:RecycleBin AND NOT a:RecycleBinItem
                      AND NOT b:RecycleBin AND NOT b:RecycleBinItem
                      AND coalesce(a.system_node, false) <> true
                      AND coalesce(b.system_node, false) <> true
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

        with driver.session() as session:
            # Step 1: Build the graph to analyze - always filter by case_id
            if node_keys and len(node_keys) > 0:
                # Focus on selected nodes and their connections (2 hops)
                graph_query = """
                    MATCH (n)
                    WHERE n.key IN $node_keys AND n.case_id = $case_id
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
                    WITH collect(n) AS startNodes
                    MATCH path = (start)-[*..2]-(connected)
                    WHERE start IN startNodes AND connected.case_id = $case_id
                      AND NOT connected:RecycleBin AND NOT connected:RecycleBinItem
                      AND coalesce(connected.system_node, false) <> true
                    With collect(DISTINCT start) + collect(DISTINCT connected) AS allNodes
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
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
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
                      AND NOT n:RecycleBin AND NOT n:RecycleBinItem
                      AND coalesce(n.system_node, false) <> true
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
                      AND NOT a:RecycleBin AND NOT a:RecycleBinItem
                      AND NOT b:RecycleBin AND NOT b:RecycleBinItem
                      AND coalesce(a.system_node, false) <> true
                      AND coalesce(b.system_node, false) <> true
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


algorithm_service = AlgorithmService()
