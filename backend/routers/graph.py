"""
Graph Router - endpoints for graph visualization data.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.neo4j_service import neo4j_service

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
    This endpoint allows MERGE/CREATE operations for case restoration.
    
    Args:
        request: Request with Cypher queries to execute
    """
    if not request.cypher_queries or not request.cypher_queries.strip():
        raise HTTPException(status_code=400, detail="Cypher queries are required")
    
    try:
        # Split queries by double newline and execute each
        queries = [q.strip() for q in request.cypher_queries.split('\n\n') if q.strip()]
        executed = 0
        errors = []
        
        for query in queries:
            query = query.strip()
            if not query:
                continue
            try:
                # Use run_cypher which allows write operations
                neo4j_service.run_cypher(query, {})
                executed += 1
            except Exception as e:
                errors.append(f"Query failed: {str(e)}")
                # Continue with other queries
        
        return {
            "success": True,
            "executed": executed,
            "total": len(queries),
            "errors": errors if errors else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))