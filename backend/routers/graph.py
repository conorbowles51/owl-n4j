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