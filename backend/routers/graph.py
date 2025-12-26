"""
Graph Router - endpoints for graph visualization data.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.neo4j_service import neo4j_service
from services.last_graph_storage import last_graph_storage

router = APIRouter(prefix="/api/graph", tags=["graph"])


class ShortestPathsRequest(BaseModel):
    """Request model for shortest paths endpoint."""
    node_keys: List[str]
    max_depth: int = 10


class PageRankRequest(BaseModel):
    """Request model for PageRank endpoint."""
    node_keys: Optional[List[str]] = None  # If None, runs on full graph
    top_n: int = 20  # Number of top influential nodes to return
    iterations: int = 20  # Number of PageRank iterations
    damping_factor: float = 0.85  # Damping factor for PageRank


class LouvainRequest(BaseModel):
    """Request model for Louvain community detection endpoint."""
    node_keys: Optional[List[str]] = None  # If None, runs on full graph
    resolution: float = 1.0  # Resolution parameter for modularity (higher = more communities)
    max_iterations: int = 10  # Maximum number of iterations


class BetweennessCentralityRequest(BaseModel):
    """Request model for Betweenness Centrality endpoint."""
    node_keys: Optional[List[str]] = None  # If None, runs on full graph
    top_n: int = 20  # Number of top nodes by betweenness centrality to return
    normalized: bool = True  # Whether to normalize the scores


class CaseLoadRequest(BaseModel):
    """Request model for loading a case (executing Cypher queries)."""
    cypher_queries: str


class SingleQueryRequest(BaseModel):
    """Request model for executing a single Cypher query (for case loading with progress)."""
    query: str


class LastGraphResponse(BaseModel):
    cypher: Optional[str] = None
    saved_at: Optional[str] = None


class CreateNodeRequest(BaseModel):
    """Request model for creating a node."""
    name: str
    type: str
    description: Optional[str] = None
    summary: Optional[str] = None


class CreateNodeResponse(BaseModel):
    """Response model for node creation."""
    success: bool
    node_key: str
    cypher: str
    error: Optional[str] = None


class UpdateNodeRequest(BaseModel):
    """Request model for updating a node."""
    name: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None


class UpdateNodeResponse(BaseModel):
    """Response model for node update."""
    success: bool
    cypher: str
    error: Optional[str] = None


class PinFactRequest(BaseModel):
    """Request model for pinning/unpinning a fact."""
    fact_index: int
    pinned: bool


class VerifyInsightRequest(BaseModel):
    """Request model for verifying an AI insight."""
    insight_index: int
    username: str
    source_doc: Optional[str] = None
    page: Optional[int] = None


class RelationshipRequest(BaseModel):
    """Request model for creating a relationship."""
    from_key: str
    to_key: str
    type: str
    notes: Optional[str] = None


class CreateRelationshipsRequest(BaseModel):
    """Request model for creating multiple relationships."""
    relationships: List[RelationshipRequest]


class CreateRelationshipsResponse(BaseModel):
    """Response model for relationship creation."""
    success: bool
    cypher: str
    error: Optional[str] = None


@router.get("/entity-types")
async def get_entity_types():
    """
    Get all entity types in the graph with their counts.
    
    Returns a list of all entity types that exist in the database,
    regardless of whether they're currently visible in the graph view.
    """
    try:
        summary = neo4j_service.get_graph_summary()
        entity_types = summary.get("entity_types", {})
        
        # Convert to list format
        types_list = [
            {"type": type_name, "count": count}
            for type_name, count in entity_types.items()
        ]
        
        # Sort by count descending, then by type name
        types_list.sort(key=lambda x: (-x["count"], x["type"]))
        
        return {"entity_types": types_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_graph(
    start_date: Optional[str] = Query(None, description="Filter start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter end date (YYYY-MM-DD)"),
):
    """
    Get the full graph for visualization.

    Returns all nodes and relationships. Optionally filter by date range.
    Nodes included if they have a date in range or are connected to nodes with dates in range.
    """
    try:
        return neo4j_service.get_full_graph(start_date=start_date, end_date=end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/node/{key}")
async def get_node_details(key: str):
    """
    Get detailed information about a specific node.

    Args:
        key: The node's unique key
    """
    try:
        node = neo4j_service.get_node_details(key)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node not found: {key}")
        return node
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/node/{key}/neighbours")
async def get_node_neighbours(
    key: str,
    depth: int = Query(default=1, ge=1, le=3),
):
    """
    Get a node and its neighbours for expansion.

    Args:
        key: The node's unique key
        depth: How many hops to traverse (1-3)
    """
    try:
        return neo4j_service.get_node_with_neighbours(key, depth)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Search nodes by name or key.

    Args:
        q: Search query
        limit: Maximum results to return
    """
    try:
        return neo4j_service.search_nodes(q, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_graph_summary():
    """
    Get a summary of the graph (counts, types).
    """
    try:
        return neo4j_service.get_graph_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locations")
async def get_entities_with_locations(
    types: Optional[str] = Query(None, description="Comma-separated entity types to filter"),
):
    """
    Get all entities that have geocoded locations for map display.
    
    Returns entities with latitude, longitude, and connection information.
    """
    try:
        entity_types = None
        if types:
            entity_types = [t.strip() for t in types.split(",")]
        return neo4j_service.get_entities_with_locations(entity_types)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/shortest-paths")
async def get_shortest_paths_subgraph(request: ShortestPathsRequest):
    """
    Get subgraph containing shortest paths between selected nodes.
    
    Args:
        request: Request with node_keys list and optional max_depth
    """
    if len(request.node_keys) < 2:
        raise HTTPException(
            status_code=400, 
            detail="At least 2 node keys required for shortest path"
        )
    
    if request.max_depth < 1 or request.max_depth > 20:
        raise HTTPException(
            status_code=400,
            detail="max_depth must be between 1 and 20"
        )
    
    try:
        return neo4j_service.get_shortest_paths_subgraph(
            request.node_keys, 
            request.max_depth
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pagerank")
async def get_pagerank(request: PageRankRequest):
    """
    Get influential nodes using PageRank algorithm.
    
    Can run on:
    - Selected nodes and their connections (if node_keys provided)
    - Full graph (if node_keys is None or empty)
    
    Args:
        request: Request with optional node_keys, top_n, iterations, and damping_factor
    """
    if request.top_n < 1 or request.top_n > 100:
        raise HTTPException(
            status_code=400,
            detail="top_n must be between 1 and 100"
        )
    
    if request.iterations < 1 or request.iterations > 100:
        raise HTTPException(
            status_code=400,
            detail="iterations must be between 1 and 100"
        )
    
    if request.damping_factor < 0 or request.damping_factor > 1:
        raise HTTPException(
            status_code=400,
            detail="damping_factor must be between 0 and 1"
        )
    
    try:
        return neo4j_service.get_pagerank_subgraph(
            node_keys=request.node_keys if request.node_keys else None,
            top_n=request.top_n,
            iterations=request.iterations,
            damping_factor=request.damping_factor
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/louvain")
async def get_louvain_communities(request: LouvainRequest):
    """
    Get communities using Louvain modularity algorithm.
    
    Can run on:
    - Selected nodes and their connections (if node_keys provided)
    - Full graph (if node_keys is None or empty)
    
    Args:
        request: Request with optional node_keys, resolution, and max_iterations
    """
    if request.resolution < 0.1 or request.resolution > 10.0:
        raise HTTPException(
            status_code=400,
            detail="resolution must be between 0.1 and 10.0"
        )
    
    if request.max_iterations < 1 or request.max_iterations > 50:
        raise HTTPException(
            status_code=400,
            detail="max_iterations must be between 1 and 50"
        )
    
    try:
        return neo4j_service.get_louvain_communities(
            node_keys=request.node_keys if request.node_keys else None,
            resolution=request.resolution,
            max_iterations=request.max_iterations
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/betweenness-centrality")
async def get_betweenness_centrality(request: BetweennessCentralityRequest):
    """
    Get nodes with highest betweenness centrality.
    
    Can run on:
    - Selected nodes and their connections (if node_keys provided)
    - Full graph (if node_keys is None or empty)
    
    Args:
        request: Request with optional node_keys, top_n, and normalized
    """
    if request.top_n < 1 or request.top_n > 100:
        raise HTTPException(
            status_code=400,
            detail="top_n must be between 1 and 100"
        )
    
    try:
        return neo4j_service.get_betweenness_centrality(
            node_keys=request.node_keys if request.node_keys else None,
            top_n=request.top_n,
            normalized=request.normalized
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load-case")
async def load_case(request: CaseLoadRequest):
    """
    Load a case by executing Cypher queries.

    The incoming `cypher_queries` string may contain multiple Cypher
    statements separated by blank lines. Each statement is executed
    individually so that a failure in one query does not prevent other
    valid queries from running. Errors are collected and returned to
    the client, and the caller can still proceed to load the graph.

    Args:
        request: Request with Cypher queries to execute
    """
    if not request.cypher_queries or not request.cypher_queries.strip():
        raise HTTPException(status_code=400, detail="Cypher queries are required")

    cypher = request.cypher_queries.strip()
    # Split by double newlines into individual statements and trim empties
    queries = [q.strip() for q in cypher.split("\n\n") if q.strip()]

    executed = 0
    errors: list[str] = []
    
    # Separate node queries (MERGE nodes) from relationship queries (MATCH + MERGE relationships)
    # Execute node queries first, then relationship queries
    node_queries = []
    rel_queries = []
    
    for q in queries:
        q_upper = q.upper()
        # Relationship queries start with MATCH and contain MERGE with a relationship pattern
        if q_upper.startswith("MATCH") and "MERGE" in q_upper and ("-[r:" in q_upper or "-[:" in q_upper):
            rel_queries.append(q)
        else:
            node_queries.append(q)
    
    # Execute node queries first
    for idx, q in enumerate(node_queries):
        try:
            neo4j_service.run_cypher(q, {})
            executed += 1
        except Exception as e:
            error_msg = str(e)
            query_preview = q[:100] + "..." if len(q) > 100 else q
            errors.append(f"Node query {idx + 1} failed: {error_msg}\nQuery: {query_preview}")
    
    # Then execute relationship queries
    for idx, q in enumerate(rel_queries):
        try:
            neo4j_service.run_cypher(q, {})
            executed += 1
        except Exception as e:
            error_msg = str(e)
            query_preview = q[:100] + "..." if len(q) > 100 else q
            errors.append(f"Relationship query {idx + 1} failed: {error_msg}\nQuery: {query_preview}")

    return {
        "success": len(errors) == 0,
        "executed": executed,
        "total": len(queries),
        "errors": errors or None,
    }


@router.post("/execute-single-query")
async def execute_single_query(request: SingleQueryRequest):
    """
    Execute a single Cypher query (for case loading with progress tracking).
    
    This endpoint is used when loading case versions to execute queries
    one at a time and track progress.
    
    Args:
        request: Request with a single Cypher query to execute
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query is required")

    query = request.query.strip()
    
    try:
        neo4j_service.run_cypher(query, {})
        return {
            "success": True,
            "error": None,
        }
    except Exception as e:
        error_msg = str(e)
        query_preview = query[:100] + "..." if len(query) > 100 else query
        return {
            "success": False,
            "error": f"{error_msg}\nQuery: {query_preview}",
        }


@router.post("/clear-graph", response_model=LastGraphResponse)
async def clear_graph():
    """
    Clear the current graph, after first saving its Cypher to 'last graph'
    storage so it can be reloaded later from the UI.
    """
    try:
        # Get full graph and generate Cypher
        graph_data = neo4j_service.get_full_graph()

        # Use the same generator as case saving
        from services.cypher_generator import generate_cypher_from_graph

        cypher = generate_cypher_from_graph(graph_data)
        record = last_graph_storage.set(cypher)

        # Clear the graph
        neo4j_service.clear_graph()

        return LastGraphResponse(cypher=record["cypher"], saved_at=record["saved_at"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last-graph", response_model=LastGraphResponse)
async def get_last_graph():
    """
    Get the last-cleared graph Cypher, if available.
    """
    data = last_graph_storage.get()
    if not data:
        return LastGraphResponse(cypher=None, saved_at=None)
    return LastGraphResponse(cypher=data.get("cypher"), saved_at=data.get("saved_at"))


@router.post("/create-node", response_model=CreateNodeResponse)
async def create_node(request: CreateNodeRequest):
    """
    Create a new node in the graph with description and summary.
    
    Generates Cypher query and executes it to add the node to Neo4j.
    
    Args:
        request: Node creation request with name, type, description, and summary
    """
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Node name is required")
    
    if not request.type or not request.type.strip():
        raise HTTPException(status_code=400, detail="Node type is required")
    
    try:
        # Generate a unique key from the name
        import re
        node_key = re.sub(r'[^a-z0-9]+', '-', request.name.strip().lower()).strip('-')
        
        # Ensure key is not empty
        if not node_key:
            node_key = f"node-{abs(hash(request.name)) % 1000000}"
        
        # Create node data structure
        node_data = {
            "key": node_key,
            "name": request.name.strip(),
            "type": request.type.strip(),
            "id": node_key,
            "summary": request.summary.strip() if request.summary else None,
            "notes": request.description.strip() if request.description else None,
        }
        
        # Generate Cypher using the cypher generator
        from services.cypher_generator import generate_cypher_from_graph
        
        graph_data = {
            "nodes": [node_data],
            "links": []
        }
        
        node_cypher = generate_cypher_from_graph(graph_data)
        
        # Execute the Cypher query to create the node
        neo4j_service.run_cypher(node_cypher, {})
        
        return CreateNodeResponse(
            success=True,
            node_key=node_key,
            cypher=node_cypher
        )
    except Exception as e:
        return CreateNodeResponse(
            success=False,
            node_key="",
            cypher="",
            error=str(e)
        )


@router.post("/relationships", response_model=CreateRelationshipsResponse)
async def create_relationships(request: CreateRelationshipsRequest):
    """
    Create relationships between nodes.
    
    Args:
        request: Request containing list of relationships to create
    """
    if not request.relationships or len(request.relationships) == 0:
        raise HTTPException(status_code=400, detail="At least one relationship is required")
    
    try:
        from services.cypher_generator import generate_cypher_from_graph
        
        # Build links data for Cypher generation
        links_data = []
        for rel in request.relationships:
            if not rel.from_key or not rel.to_key or not rel.type:
                continue  # Skip invalid relationships
            
            link = {
                "source": rel.from_key,
                "target": rel.to_key,
                "type": rel.type,
                "properties": {}
            }
            
            if rel.notes:
                link["properties"]["notes"] = rel.notes
            
            links_data.append(link)
        
        if not links_data:
            raise HTTPException(status_code=400, detail="No valid relationships provided")
        
        # Generate Cypher for relationships
        relationship_graph_data = {
            "nodes": [],  # No new nodes, just relationships
            "links": links_data
        }
        
        cypher = generate_cypher_from_graph(relationship_graph_data)
        
        # Execute the Cypher queries (split by double newline and execute separately)
        # This avoids issues with WITH clauses between MERGE and MATCH
        queries = [q.strip() for q in cypher.split("\n\n") if q.strip()]
        for query in queries:
            if query:
                # Execute each query separately in its own transaction
                neo4j_service.run_cypher(query, {})
        
        return CreateRelationshipsResponse(
            success=True,
            cypher=cypher
        )
    except HTTPException:
        raise
    except Exception as e:
        return CreateRelationshipsResponse(
            success=False,
            cypher="",
            error=str(e)
        )


@router.post("/analyze-relationships/{node_key}")
async def analyze_node_relationships(node_key: str):
    """
    Analyze relationships for a specific node.
    
    Args:
        node_key: The key of the node to analyze
        
    Returns:
        Dict with success status and list of potential relationships
    """
    try:
        # Get the node details
        node_details = neo4j_service.get_node_details(node_key)
        if not node_details:
            raise HTTPException(status_code=404, detail=f"Node with key '{node_key}' not found")
        
        # Get all existing nodes from the graph (excluding the target node)
        existing_graph = neo4j_service.get_full_graph()
        existing_nodes = existing_graph.get("nodes", [])
        
        # Filter out the node we're analyzing
        existing_nodes = [n for n in existing_nodes if n.get("key") != node_key]
        
        if not existing_nodes:
            return {
                "success": True,
                "relationships": [],
                "message": "No other nodes found in the graph to analyze relationships with."
            }
        
        # Use relationship analyzer to find relationships
        from services.relationship_analyzer import analyze_node_relationships
        
        relationships = analyze_node_relationships(
            node_name=node_details.get("name", ""),
            node_type=node_details.get("type", ""),
            node_key=node_key,
            node_description=node_details.get("notes"),
            node_summary=node_details.get("summary"),
            existing_nodes=existing_nodes
        )
        
        # Enhance relationships with node names for display
        enhanced_relationships = []
        for rel in relationships:
            from_node = next((n for n in existing_nodes if n.get("key") == rel["from_key"]), None)
            to_node = next((n for n in existing_nodes if n.get("key") == rel["to_key"]), None)
            
            enhanced_rel = {
                "from_key": rel["from_key"],
                "to_key": rel["to_key"],
                "from_name": from_node.get("name") if from_node else rel["from_key"],
                "to_name": to_node.get("name") if to_node else rel["to_key"],
                "type": rel["type"],
                "notes": rel.get("notes", "")
            }
            enhanced_relationships.append(enhanced_rel)
        
        return {
            "success": True,
            "relationships": enhanced_relationships
        }
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "relationships": [],
            "error": str(e)
        }


@router.put("/node/{node_key}", response_model=UpdateNodeResponse)
async def update_node(node_key: str, request: UpdateNodeRequest):
    """
    Update properties of an existing node.
    
    Args:
        node_key: The key of the node to update
        request: Update request with optional summary and notes
        
    Returns:
        Response with success status and generated Cypher
    """
    try:
        # Verify node exists
        node_details = neo4j_service.get_node_details(node_key)
        if not node_details:
            raise HTTPException(status_code=404, detail=f"Node with key '{node_key}' not found")
        
        # Build SET clause for properties to update
        set_clauses = []
        
        if request.name is not None:
            # Escape single quotes in name
            escaped_name = request.name.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            set_clauses.append(f"n.name = '{escaped_name}'")
        
        if request.summary is not None:
            # Escape single quotes in summary
            escaped_summary = request.summary.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            set_clauses.append(f"n.summary = '{escaped_summary}'")
        
        if request.notes is not None:
            # Escape single quotes in notes
            escaped_notes = request.notes.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            set_clauses.append(f"n.notes = '{escaped_notes}'")
        
        if not set_clauses:
            raise HTTPException(status_code=400, detail="At least one field (name, summary, or notes) must be provided")
        
        # Generate Cypher query to update the node
        # Find the node by key and update properties
        # Escape the node_key for use in Cypher string
        escaped_key = node_key.replace('\\', '\\\\').replace("'", "\\'")
        cypher = f"MATCH (n {{key: '{escaped_key}'}})\n"
        cypher += f"SET {', '.join(set_clauses)}"
        
        # Execute the update
        neo4j_service.run_cypher(cypher, {})
        
        return UpdateNodeResponse(
            success=True,
            cypher=cypher
        )
    except HTTPException:
        raise
    except Exception as e:
        return UpdateNodeResponse(
            success=False,
            cypher="",
            error=str(e)
        )


@router.put("/node/{node_key}/pin-fact")
async def pin_fact(node_key: str, request: PinFactRequest):
    """
    Toggle the pinned status of a verified fact.
    
    Args:
        node_key: The key of the node
        request: Request with fact_index and pinned status
        
    Returns:
        Updated verified_facts array
    """
    try:
        updated_facts = neo4j_service.pin_fact(
            node_key=node_key,
            fact_index=request.fact_index,
            pinned=request.pinned
        )
        return {
            "success": True,
            "verified_facts": updated_facts
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/node/{node_key}/verify-insight")
async def verify_insight(node_key: str, request: VerifyInsightRequest):
    """
    Convert an AI insight to a verified fact with user attribution.
    
    Args:
        node_key: The key of the node
        request: Request with insight_index, username, and optional source info
        
    Returns:
        Updated verified_facts and ai_insights arrays
    """
    try:
        result = neo4j_service.verify_insight(
            node_key=node_key,
            insight_index=request.insight_index,
            username=request.username,
            source_doc=request.source_doc,
            page=request.page
        )
        return {
            "success": True,
            "verified_facts": result["verified_facts"],
            "ai_insights": result["ai_insights"]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))