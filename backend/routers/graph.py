"""
Graph Router - endpoints for graph visualization data.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from services.neo4j_service import neo4j_service

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("")
async def get_graph():
    """
    Get the full graph for visualization.

    Returns all nodes and relationships.
    """
    try:
        return neo4j_service.get_full_graph()
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
