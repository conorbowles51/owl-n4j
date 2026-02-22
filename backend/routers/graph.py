"""
Graph Router - endpoints for graph visualization data.
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
import json
import asyncio
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.neo4j_service import neo4j_service
from services.last_graph_storage import last_graph_storage
from services.insights_service import generate_entity_insights
from services.llm_service import LLMService
from services.geo_rescan_service import rescan_case_locations
from services.system_log_service import system_log_service, LogType, LogOrigin
from services.rejected_pairs_service import RejectedPairsService
from routers.auth import get_current_user
from postgres.session import get_db

router = APIRouter(prefix="/api/graph", tags=["graph"])


class ShortestPathsRequest(BaseModel):
    """Request model for shortest paths endpoint."""
    case_id: str  # REQUIRED: Filter to case-specific paths
    node_keys: List[str]
    max_depth: int = 10


class ExpandNodesRequest(BaseModel):
    """Request model for expanding nodes endpoint."""
    node_keys: List[str]
    depth: int = 1
    case_id: str  # REQUIRED: Filter to case-specific data


class PageRankRequest(BaseModel):
    """Request model for PageRank endpoint."""
    case_id: str  # REQUIRED: Filter to case-specific data
    node_keys: Optional[List[str]] = None  # If None, runs on full graph (filtered by case_id)
    top_n: int = 20  # Number of top influential nodes to return
    iterations: int = 20  # Number of PageRank iterations
    damping_factor: float = 0.85  # Damping factor for PageRank


class LouvainRequest(BaseModel):
    """Request model for Louvain community detection endpoint."""
    case_id: str  # REQUIRED: Filter to case-specific data
    node_keys: Optional[List[str]] = None  # If None, runs on full graph (filtered by case_id)
    resolution: float = 1.0  # Resolution parameter for modularity (higher = more communities)
    max_iterations: int = 10  # Maximum number of iterations


class BetweennessCentralityRequest(BaseModel):
    """Request model for Betweenness Centrality endpoint."""
    case_id: str  # REQUIRED: Filter to case-specific data
    node_keys: Optional[List[str]] = None  # If None, runs on full graph (filtered by case_id)
    top_n: int = 20  # Number of top nodes by betweenness centrality to return
    normalized: bool = True  # Whether to normalize the scores


class DeleteNodeRequest(BaseModel):
    """Request model for deleting a node."""
    node_key: str


class FindSimilarEntitiesRequest(BaseModel):
    """Request model for finding similar entities."""
    case_id: str
    entity_types: Optional[List[str]] = None
    name_similarity_threshold: float = 0.7
    max_results: int = 50


class MergeEntitiesRequest(BaseModel):
    """Request model for merging entities."""
    case_id: str  # REQUIRED: Verify both entities belong to this case
    source_key: str
    target_key: str
    merged_data: Dict[str, Any]  # name, summary, notes, type, properties


class CaseLoadRequest(BaseModel):
    """Request model for loading a case (executing Cypher queries)."""
    cypher_queries: str


class SingleQueryRequest(BaseModel):
    """Request model for executing a single Cypher query (for case loading with progress)."""
    query: str


class BatchQueryRequest(BaseModel):
    """Request model for executing multiple Cypher queries in batches (for faster case loading)."""
    queries: List[str]
    batch_size: int = 50  # Number of queries to execute per batch


class LastGraphResponse(BaseModel):
    cypher: Optional[str] = None
    saved_at: Optional[str] = None


class CreateNodeRequest(BaseModel):
    """Request model for creating a node."""
    name: str
    type: str
    case_id: str  # REQUIRED: Associate node with case
    description: Optional[str] = None
    summary: Optional[str] = None
    properties: Optional[Dict[str, Any]] = None  # Additional type-specific properties


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
    properties: Optional[Dict[str, Any]] = None  # Additional type-specific properties


class UpdateNodeResponse(BaseModel):
    """Response model for node update."""
    success: bool
    cypher: str
    error: Optional[str] = None


class PinFactRequest(BaseModel):
    """Request model for pinning/unpinning a fact."""
    case_id: str  # REQUIRED: Verify node belongs to this case
    fact_index: int
    pinned: bool


class VerifyInsightRequest(BaseModel):
    """Request model for verifying an AI insight."""
    case_id: str  # REQUIRED: Verify node belongs to this case
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
    case_id: str  # REQUIRED: Associate relationships with case


class CreateRelationshipsResponse(BaseModel):
    """Response model for relationship creation."""
    success: bool
    cypher: str
    error: Optional[str] = None


@router.get("/entity-types")
async def get_entity_types(
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
):
    """
    Get all entity types in the graph with their counts.

    Returns a list of all entity types that exist in the database for this case,
    regardless of whether they're currently visible in the graph view.
    """
    try:
        summary = neo4j_service.get_graph_summary(case_id=case_id)
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
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
    start_date: Optional[str] = Query(None, description="Filter start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter end date (YYYY-MM-DD)"),
    user: dict = Depends(get_current_user),
):
    """
    Get the full graph for visualization.

    Returns all nodes and relationships for the specified case. Optionally filter by date range.
    Nodes included if they have a date in range or are connected to nodes with dates in range.
    """
    try:
        result = neo4j_service.get_full_graph(case_id=case_id, start_date=start_date, end_date=end_date)
        
        # Log the filter operation if dates are provided
        if start_date or end_date:
            system_log_service.log(
                log_type=LogType.GRAPH_OPERATION,
                origin=LogOrigin.FRONTEND,
                action="Filter Graph by Date Range",
                details={
                    "start_date": start_date,
                    "end_date": end_date,
                    "nodes_count": len(result.get("nodes", [])) if isinstance(result, dict) else 0,
                    "links_count": len(result.get("links", [])) if isinstance(result, dict) else 0,
                },
                user=user.get("username", "unknown"),
                success=True,
            )
        
        return result
    except Exception as e:
        # Log the error
        if start_date or end_date:
            system_log_service.log(
                log_type=LogType.GRAPH_OPERATION,
                origin=LogOrigin.FRONTEND,
                action="Filter Graph Failed",
                details={
                    "start_date": start_date,
                    "end_date": end_date,
                    "error": str(e),
                },
                user=user.get("username", "unknown"),
                success=False,
                error=str(e),
            )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/node/{key}")
async def get_node_details(
    key: str,
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
):
    """
    Get detailed information about a specific node.

    Args:
        key: The node's unique key
        case_id: REQUIRED - Filter to case-specific connections
    """
    try:
        node = neo4j_service.get_node_details(key, case_id=case_id)
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
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
):
    """
    Get a node and its neighbours for expansion.

    Args:
        key: The node's unique key
        depth: How many hops to traverse (1-3)
        case_id: REQUIRED - Filter to case-specific neighbours
    """
    try:
        return neo4j_service.get_node_with_neighbours(key, depth, case_id=case_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/expand-nodes")
async def expand_nodes(
    request: ExpandNodesRequest,
    user: dict = Depends(get_current_user),
):
    """
    Expand multiple nodes by N hops.

    Args:
        request: Request with node_keys list, depth (number of hops), and optional case_id
    """
    if not request.node_keys:
        raise HTTPException(status_code=400, detail="No node keys provided")

    if request.depth < 1 or request.depth > 5:
        raise HTTPException(status_code=400, detail="Depth must be between 1 and 5")

    try:
        result = neo4j_service.expand_nodes(request.node_keys, request.depth, case_id=request.case_id)
        
        # Log the expansion operation
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Expand Nodes",
            details={
                "node_keys": request.node_keys,
                "depth": request.depth,
                "nodes_found": len(result.get("nodes", [])),
                "links_found": len(result.get("links", [])),
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return result
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Expand Nodes Failed",
            details={
                "node_keys": request.node_keys,
                "depth": request.depth,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
    user: dict = Depends(get_current_user),
):
    """
    Search nodes by name or key.

    Args:
        q: Search query
        limit: Maximum results to return
        case_id: REQUIRED - Filter to case-specific nodes
        user: Current authenticated user
    """
    try:
        results = neo4j_service.search_nodes(q, limit, case_id=case_id)
        
        # Log the search operation
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Search Nodes: {q[:50]}",
            details={
                "query": q,
                "limit": limit,
                "results_count": len(results.get("nodes", [])) if isinstance(results, dict) else 0,
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return results
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Search Nodes Failed: {q[:50]}",
            details={
                "query": q,
                "limit": limit,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_graph_summary(
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
):
    """
    Get a summary of the graph (counts, types) for a specific case.
    """
    try:
        return neo4j_service.get_graph_summary(case_id=case_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/locations")
async def get_entities_with_locations(
    types: Optional[str] = Query(None, description="Comma-separated entity types to filter"),
    case_id: str = Query(..., description="REQUIRED: Filter by case ID"),
):
    """
    Get all entities that have geocoded locations for map display.

    Returns entities with latitude, longitude, and connection information for the specified case.
    """
    try:
        entity_types = None
        if types:
            entity_types = [t.strip() for t in types.split(",")]
        return neo4j_service.get_entities_with_locations(entity_types, case_id=case_id)
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
            request.max_depth,
            case_id=request.case_id
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
            damping_factor=request.damping_factor,
            case_id=request.case_id
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
            max_iterations=request.max_iterations,
            case_id=request.case_id
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
            normalized=request.normalized,
            case_id=request.case_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load-case")
async def load_case(request: CaseLoadRequest, user: dict = Depends(get_current_user)):
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

    success = len(errors) == 0
    
    # Log the operation
    system_log_service.log(
        log_type=LogType.CASE_MANAGEMENT,
        origin=LogOrigin.FRONTEND,
        action="Load Case",
        details={
            "queries_count": len(queries),
            "executed": executed,
            "errors_count": len(errors),
        },
        user=user.get("username", "unknown"),
        success=success,
        error=f"{len(errors)} errors" if errors else None,
    )
    
    return {
        "success": success,
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


@router.post("/execute-batch-queries")
async def execute_batch_queries(request: BatchQueryRequest):
    """
    Execute multiple Cypher queries in batches for faster case loading.
    
    This endpoint executes queries in batches within a single transaction,
    which is much faster than executing them one at a time. Use this for
    loading large cases with >100 queries.
    
    Args:
        request: Request with list of queries and batch size
    """
    if not request.queries or len(request.queries) == 0:
        raise HTTPException(status_code=400, detail="Queries are required")
    
    if request.batch_size < 1 or request.batch_size > 200:
        raise HTTPException(status_code=400, detail="batch_size must be between 1 and 200")

    queries = [q.strip() for q in request.queries if q.strip()]
    if not queries:
        raise HTTPException(status_code=400, detail="No valid queries provided")

    executed = 0
    errors: List[str] = []
    batch_size = request.batch_size
    
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
    
    # Execute node queries in batches
    for batch_start in range(0, len(node_queries), batch_size):
        batch = node_queries[batch_start:batch_start + batch_size]
        try:
            # Execute all queries in the batch within a single transaction
            with neo4j_service._driver.session() as session:
                def work(tx):
                    for q in batch:
                        tx.run(q, {})
                session.execute_write(work)
            executed += len(batch)
        except Exception as e:
            error_msg = str(e)
            # If batch fails, try executing individually to identify the problematic query
            for idx, q in enumerate(batch):
                try:
                    neo4j_service.run_cypher(q, {})
                    executed += 1
                except Exception as e2:
                    query_preview = q[:100] + "..." if len(q) > 100 else q
                    errors.append(f"Node query {batch_start + idx + 1} failed: {str(e2)}\nQuery: {query_preview}")
    
    # Execute relationship queries in batches
    for batch_start in range(0, len(rel_queries), batch_size):
        batch = rel_queries[batch_start:batch_start + batch_size]
        try:
            # Execute all queries in the batch within a single transaction
            with neo4j_service._driver.session() as session:
                def work(tx):
                    for q in batch:
                        tx.run(q, {})
                session.execute_write(work)
            executed += len(batch)
        except Exception as e:
            error_msg = str(e)
            # If batch fails, try executing individually to identify the problematic query
            for idx, q in enumerate(batch):
                try:
                    neo4j_service.run_cypher(q, {})
                    executed += 1
                except Exception as e2:
                    query_preview = q[:100] + "..." if len(q) > 100 else q
                    errors.append(f"Relationship query {batch_start + idx + 1} failed: {str(e2)}\nQuery: {query_preview}")
    
    return {
        "success": len(errors) == 0,
        "executed": executed,
        "total": len(queries),
        "errors": errors or None,
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
async def create_node(request: CreateNodeRequest, user: dict = Depends(get_current_user)):
    """
    Create a new node in the graph with description and summary.

    Generates Cypher query and executes it to add the node to Neo4j.

    Args:
        request: Node creation request with name, type, case_id (required), description, and summary
    """
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Node name is required")

    if not request.type or not request.type.strip():
        raise HTTPException(status_code=400, detail="Node type is required")

    if not request.case_id or not request.case_id.strip():
        raise HTTPException(status_code=400, detail="case_id is required")

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
        
        # Add type-specific properties if provided
        if request.properties:
            # Put additional properties into a properties dict
            # The cypher_generator will merge these with standard properties
            node_data["properties"] = {}
            for key, value in request.properties.items():
                # Skip standard fields that are already handled
                if key not in ['key', 'id', 'name', 'type', 'summary', 'notes', 'case_id']:
                    node_data["properties"][key] = value

        # Generate Cypher using the cypher generator (with case_id)
        from services.cypher_generator import generate_cypher_from_graph

        graph_data = {
            "nodes": [node_data],
            "links": []
        }

        node_cypher = generate_cypher_from_graph(graph_data, case_id=request.case_id)
        
        # Execute the Cypher query to create the node
        neo4j_service.run_cypher(node_cypher, {})
        
        # Log the operation
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Create Node: {request.name}",
            details={
                "node_name": request.name,
                "node_type": request.type,
                "node_key": node_key,
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return CreateNodeResponse(
            success=True,
            node_key=node_key,
            cypher=node_cypher
        )
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Create Node Failed: {request.name}",
            details={
                "node_name": request.name,
                "node_type": request.type,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        
        return CreateNodeResponse(
            success=False,
            node_key="",
            cypher="",
            error=str(e)
        )


@router.post("/relationships", response_model=CreateRelationshipsResponse)
async def create_relationships(request: CreateRelationshipsRequest, user: dict = Depends(get_current_user)):
    """
    Create relationships between nodes.

    Args:
        request: Request containing list of relationships to create and case_id
    """
    if not request.relationships or len(request.relationships) == 0:
        raise HTTPException(status_code=400, detail="At least one relationship is required")

    if not request.case_id or not request.case_id.strip():
        raise HTTPException(status_code=400, detail="case_id is required")

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

        # Generate Cypher for relationships (with case_id)
        relationship_graph_data = {
            "nodes": [],  # No new nodes, just relationships
            "links": links_data
        }

        cypher = generate_cypher_from_graph(relationship_graph_data, case_id=request.case_id)
        
        # Execute the Cypher queries (split by double newline and execute separately)
        # This avoids issues with WITH clauses between MERGE and MATCH
        queries = [q.strip() for q in cypher.split("\n\n") if q.strip()]
        for query in queries:
            if query:
                # Execute each query separately in its own transaction
                neo4j_service.run_cypher(query, {})
        
        # Log the operation
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Create Relationships: {len(links_data)} relationships",
            details={
                "relationships_count": len(links_data),
                "relationship_types": list(set([link.get("type") for link in links_data])),
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return CreateRelationshipsResponse(
            success=True,
            cypher=cypher
        )
    except HTTPException:
        raise
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Create Relationships Failed",
            details={
                "relationships_count": len(request.relationships),
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        
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
async def update_node(node_key: str, request: UpdateNodeRequest, user: dict = Depends(get_current_user)):
    """
    Update properties of an existing node.
    
    Args:
        node_key: The key of the node to update
        request: Update request with optional summary and notes
        user: Current authenticated user
        
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
        updated_fields = []
        
        if request.name is not None:
            # Escape single quotes in name
            escaped_name = request.name.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            set_clauses.append(f"n.name = '{escaped_name}'")
            updated_fields.append("name")
        
        if request.summary is not None:
            # Escape single quotes in summary
            escaped_summary = request.summary.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            set_clauses.append(f"n.summary = '{escaped_summary}'")
            updated_fields.append("summary")
        
        if request.notes is not None:
            # Escape single quotes in notes
            escaped_notes = request.notes.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
            set_clauses.append(f"n.notes = '{escaped_notes}'")
            updated_fields.append("notes")
        
        # Add type-specific properties if provided
        if request.properties:
            from services.cypher_generator import format_properties
            # Format properties for Cypher (escape values)
            for key, value in request.properties.items():
                # Skip standard fields that are handled above
                if key in ['name', 'summary', 'notes']:
                    continue
                # Escape property key if needed
                if not key.replace("_", "").replace("-", "").isalnum() or (key and key[0].isdigit()):
                    escaped_key = f"`{key.replace('`', '``')}`"
                else:
                    escaped_key = key
                # Format value based on type
                if isinstance(value, str):
                    escaped_value = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
                    set_clauses.append(f"n.{escaped_key} = '{escaped_value}'")
                elif isinstance(value, bool):
                    set_clauses.append(f"n.{escaped_key} = {str(value).lower()}")
                elif isinstance(value, (int, float)):
                    set_clauses.append(f"n.{escaped_key} = {value}")
                elif value is None:
                    set_clauses.append(f"n.{escaped_key} = null")
                else:
                    # For other types, convert to string
                    escaped_value = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
                    set_clauses.append(f"n.{escaped_key} = '{escaped_value}'")
                updated_fields.append(key)
        
        if not set_clauses:
            raise HTTPException(status_code=400, detail="At least one field must be provided")
        
        # Generate Cypher query to update the node
        # Find the node by key and update properties
        # Escape the node_key for use in Cypher string
        escaped_key = node_key.replace('\\', '\\\\').replace("'", "\\'")
        cypher = f"MATCH (n {{key: '{escaped_key}'}})\n"
        cypher += f"SET {', '.join(set_clauses)}"
        
        # Execute the update
        neo4j_service.run_cypher(cypher, {})
        
        # Log the operation
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Update Node: {node_key}",
            details={
                "node_key": node_key,
                "node_name": node_details.get("name", "unknown"),
                "updated_fields": updated_fields,
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return UpdateNodeResponse(
            success=True,
            cypher=cypher
        )
    except HTTPException:
        raise
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action=f"Update Node Failed: {node_key}",
            details={
                "node_key": node_key,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        
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
        request: Request with case_id, fact_index and pinned status

    Returns:
        Updated verified_facts array
    """
    try:
        updated_facts = neo4j_service.pin_fact(
            node_key=node_key,
            fact_index=request.fact_index,
            pinned=request.pinned,
            case_id=request.case_id
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
        request: Request with case_id, insight_index, username, and optional source info

    Returns:
        Updated verified_facts and ai_insights arrays
    """
    try:
        result = neo4j_service.verify_insight(
            node_key=node_key,
            insight_index=request.insight_index,
            username=request.username,
            source_doc=request.source_doc,
            page=request.page,
            case_id=request.case_id
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

class FindSimilarEntitiesRequest(BaseModel):
    """Request model for finding similar entities."""
    case_id: str
    entity_types: Optional[List[str]] = None
    name_similarity_threshold: float = 0.7
    max_results: int = 50


class MergeEntitiesRequest(BaseModel):
    """Request model for merging entities."""
    case_id: str  # REQUIRED: Verify both entities belong to this case
    source_key: str
    target_key: str
    merged_data: Dict[str, Any]  # name, summary, notes, type, properties


@router.post("/find-similar-entities")
async def find_similar_entities(
    request: FindSimilarEntitiesRequest,
    user: dict = Depends(get_current_user),
):
    """
    Find entities that might be duplicates based on name similarity.
    """
    try:
        result = neo4j_service.find_similar_entities(
            case_id=request.case_id,
            entity_types=request.entity_types,
            name_similarity_threshold=request.name_similarity_threshold,
            max_results=request.max_results,
        )
        
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Find Similar Entities",
            details={
                "entity_types": request.entity_types,
                "similarity_threshold": request.name_similarity_threshold,
                "pairs_found": len(result),
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return {"similar_pairs": result}
    except Exception as e:
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Find Similar Entities Failed",
            details={"error": str(e)},
            user=user.get("username", "unknown"),
            success=False,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/find-similar-entities/stream")
async def find_similar_entities_stream(
    request: Request,
    case_id: str = Query(..., description="REQUIRED: Case ID to scan"),
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types to filter"),
    name_similarity_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Minimum name similarity threshold"),
    max_results: int = Query(1000, ge=1, le=5000, description="Maximum number of results to return"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Stream similar entities search with progress updates via Server-Sent Events (SSE).

    This endpoint streams progress updates for large cases that would otherwise timeout.
    Previously rejected pairs are automatically filtered out.

    SSE Events:
    - start: Initial metadata (total_entities, entity_types, total_comparisons)
    - type_start: Starting comparison for a specific entity type
    - progress: Progress update with comparisons_done and pairs_found
    - type_complete: Finished comparing a specific entity type
    - complete: Scan finished successfully with all results
    - cancelled: Client disconnected
    - error: An error occurred
    """
    # Parse entity_types from comma-separated string
    types_list = None
    if entity_types:
        types_list = [t.strip() for t in entity_types.split(",") if t.strip()]

    # Fetch rejected pairs for this case to filter them out
    rejected_pairs_service = RejectedPairsService(db)
    try:
        rejected_pairs = rejected_pairs_service.get_rejected_pairs_set(UUID(case_id))
    except ValueError:
        rejected_pairs = set()  # Invalid UUID, use empty set

    async def event_generator():
        """Generate SSE events from the streaming similarity search."""
        try:
            async for event in neo4j_service.find_similar_entities_streaming(
                case_id=case_id,
                entity_types=types_list,
                name_similarity_threshold=name_similarity_threshold,
                max_results=max_results,
                rejected_pairs=rejected_pairs,
            ):
                # Check if client disconnected
                if await request.is_disconnected():
                    yield f"event: cancelled\ndata: {json.dumps({'message': 'Client disconnected'})}\n\n"
                    return

                event_type = event.get("event", "message")
                event_data = json.dumps(event.get("data", {}))
                yield f"event: {event_type}\ndata: {event_data}\n\n"

        except asyncio.CancelledError:
            yield f"event: cancelled\ndata: {json.dumps({'message': 'Request cancelled'})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            system_log_service.log(
                log_type=LogType.GRAPH_OPERATION,
                origin=LogOrigin.FRONTEND,
                action="Find Similar Entities Stream Failed",
                details={"error": str(e)},
                user=user.get("username", "unknown"),
                success=False,
            )

    # Log the start of the streaming operation
    system_log_service.log(
        log_type=LogType.GRAPH_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Find Similar Entities Stream Started",
        details={
            "case_id": case_id,
            "entity_types": types_list,
            "similarity_threshold": name_similarity_threshold,
        },
        user=user.get("username", "unknown"),
        success=True,
    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.post("/merge-entities")
async def merge_entities(
    request: MergeEntitiesRequest,
    user: dict = Depends(get_current_user),
):
    """
    Merge two entities into one.
    """
    try:
        # Validate merged_data is not None
        if request.merged_data is None:
            raise HTTPException(status_code=400, detail="merged_data cannot be None")
        if not isinstance(request.merged_data, dict):
            raise HTTPException(status_code=400, detail=f"merged_data must be a dict, got {type(request.merged_data)}")
        
        result = neo4j_service.merge_entities(
            source_key=request.source_key,
            target_key=request.target_key,
            merged_data=request.merged_data,
            case_id=request.case_id,
        )
        
        # Validate result is not None
        if result is None:
            raise HTTPException(status_code=500, detail="Merge operation returned None")
        if not isinstance(result, dict):
            raise HTTPException(status_code=500, detail=f"Merge operation returned invalid type: {type(result)}")
        
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Merge Entities",
            details={
                "source_key": request.source_key,
                "target_key": request.target_key,
                "relationships_updated": result.get("relationships_updated", 0),
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return result
    except ValueError as e:
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Merge Entities Failed",
            details={
                "source_key": request.source_key,
                "target_key": request.target_key,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Merge Entities Failed",
            details={
                "source_key": request.source_key,
                "target_key": request.target_key,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
        )
        raise HTTPException(status_code=500, detail=str(e))


# --- Rejected Merge Pairs Endpoints ---

class RejectMergeRequest(BaseModel):
    """Request model for rejecting a merge pair."""
    case_id: str
    entity_key_1: str
    entity_key_2: str


class RejectedPairResponse(BaseModel):
    """Response model for a rejected merge pair."""
    id: str
    case_id: str
    entity_key_1: str
    entity_key_2: str
    rejected_at: str
    rejected_by_user_id: Optional[str] = None


@router.post("/reject-merge")
async def reject_merge_pair(
    request: RejectMergeRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Reject a pair of entities as a false positive (not actually duplicates).

    The rejected pair will be filtered out from future similar-entities scans.

    Args:
        request: Request with case_id, entity_key_1, and entity_key_2
        user: Current authenticated user
        db: Database session

    Returns:
        The created rejection record
    """
    try:
        rejected_pairs_service = RejectedPairsService(db)
        user_id = UUID(user.get("id")) if user.get("id") else None

        rejection = rejected_pairs_service.reject_pair(
            case_id=UUID(request.case_id),
            key1=request.entity_key_1,
            key2=request.entity_key_2,
            user_id=user_id,
        )

        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Reject Merge Pair",
            details={
                "case_id": request.case_id,
                "entity_key_1": rejection.entity_key_1,
                "entity_key_2": rejection.entity_key_2,
            },
            user=user.get("username", "unknown"),
            success=True,
        )

        return RejectedPairResponse(
            id=str(rejection.id),
            case_id=str(rejection.case_id),
            entity_key_1=rejection.entity_key_1,
            entity_key_2=rejection.entity_key_2,
            rejected_at=rejection.created_at.isoformat(),
            rejected_by_user_id=str(rejection.rejected_by_user_id) if rejection.rejected_by_user_id else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Reject Merge Pair Failed",
            details={
                "case_id": request.case_id,
                "entity_key_1": request.entity_key_1,
                "entity_key_2": request.entity_key_2,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rejected-merges")
async def get_rejected_merges(
    case_id: str = Query(..., description="REQUIRED: Case ID to get rejected pairs for"),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all rejected merge pairs for a case.

    Args:
        case_id: The case ID to get rejections for
        user: Current authenticated user
        db: Database session

    Returns:
        List of rejected pairs with total count
    """
    try:
        rejected_pairs_service = RejectedPairsService(db)
        rejections = rejected_pairs_service.get_rejected_pairs(UUID(case_id))

        pairs = [
            RejectedPairResponse(
                id=str(r.id),
                case_id=str(r.case_id),
                entity_key_1=r.entity_key_1,
                entity_key_2=r.entity_key_2,
                rejected_at=r.created_at.isoformat(),
                rejected_by_user_id=str(r.rejected_by_user_id) if r.rejected_by_user_id else None,
            )
            for r in rejections
        ]

        return {
            "rejected_pairs": pairs,
            "total": len(pairs),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rejected-merges/{rejection_id}")
async def undo_rejection(
    rejection_id: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Undo a rejection (remove it from the rejected list).

    The pair will appear again in future similar-entities scans.

    Args:
        rejection_id: The ID of the rejection to undo
        user: Current authenticated user
        db: Database session

    Returns:
        Success status
    """
    try:
        rejected_pairs_service = RejectedPairsService(db)
        success = rejected_pairs_service.undo_rejection(
            rejection_id=UUID(rejection_id),
            user_id=UUID(user.get("id")) if user.get("id") else None,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Rejection not found")

        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Undo Merge Rejection",
            details={"rejection_id": rejection_id},
            user=user.get("username", "unknown"),
            success=True,
        )

        return {"success": True}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Undo Merge Rejection Failed",
            details={"rejection_id": rejection_id, "error": str(e)},
            user=user.get("username", "unknown"),
            success=False,
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/node/{node_key}")
async def delete_node(
    node_key: str,
    case_id: str = Query(..., description="REQUIRED: Verify node belongs to this case"),
    user: dict = Depends(get_current_user)
):
    """
    Delete a node and all its relationships from the graph.

    Args:
        node_key: Key of the node to delete
        case_id: REQUIRED - Verify node belongs to this case
        user: Current authenticated user

    Returns:
        Dict with success status and deletion info
    """
    try:
        result = neo4j_service.delete_node(node_key, case_id=case_id)
        
        # Log the deletion
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Node Deleted",
            details={
                "node_key": node_key,
                "node_name": result.get("deleted_node", {}).get("name"),
                "node_type": result.get("deleted_node", {}).get("type"),
                "relationships_deleted": result.get("relationships_deleted", 0),
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Node Deletion Failed",
            details={
                "node_key": node_key,
                "error": str(e),
            },
            user=user.get("username", "unknown"),
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


# --- Location management endpoints ---

class UpdateLocationRequest(BaseModel):
    case_id: str
    location_name: str
    latitude: float
    longitude: float


@router.put("/node/{node_key}/location")
async def update_entity_location(
    node_key: str,
    request: UpdateLocationRequest,
    user: dict = Depends(get_current_user),
):
    """Update the location of an entity node on the map."""
    try:
        result = neo4j_service.update_entity_location(
            node_key=node_key,
            case_id=request.case_id,
            location_name=request.location_name,
            latitude=request.latitude,
            longitude=request.longitude,
        )
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Location Updated",
            details={
                "node_key": node_key,
                "location_name": request.location_name,
                "latitude": request.latitude,
                "longitude": request.longitude,
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/node/{node_key}/location")
async def remove_entity_location(
    node_key: str,
    case_id: str = Query(..., description="REQUIRED: Verify node belongs to this case"),
    user: dict = Depends(get_current_user),
):
    """Remove location data from an entity node (node stays in graph)."""
    try:
        result = neo4j_service.remove_entity_location(node_key=node_key, case_id=case_id)
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Location Removed",
            details={"node_key": node_key, "case_id": case_id},
            user=user.get("username", "unknown"),
            success=True,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/entity-summary")
async def get_case_entity_summary(case_id: str):
    """Get structured entity summary for the case dashboard."""
    try:
        entities = neo4j_service.get_case_entity_summary(case_id)
        return {"entities": entities, "total": len(entities)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BatchUpdateRequest(BaseModel):
    case_id: str
    updates: list  # [{key, property, value}]


@router.put("/batch-update")
async def batch_update_entities(
    request: BatchUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Batch update properties on multiple entity nodes."""
    if len(request.updates) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 updates per call")
    allowed = {"name", "summary", "notes", "type", "description"}
    for u in request.updates:
        if u.get("property") not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Property '{u.get('property')}' not allowed",
            )
    try:
        count = neo4j_service.batch_update_entities(request.updates, request.case_id)
        system_log_service.log(
            log_type=LogType.GRAPH_OPERATION,
            origin=LogOrigin.FRONTEND,
            action="Batch Update",
            details={
                "case_id": request.case_id,
                "updates_requested": len(request.updates),
                "updates_applied": count,
            },
            user=user.get("username", "unknown"),
            success=True,
        )
        return {"success": True, "updated": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/generate-insights")
async def generate_insights(
    case_id: str,
    max_entities: int = Query(10, description="Maximum entities to process"),
    user: dict = Depends(get_current_user),
):
    """Generate AI insights for top entities in a case."""
    try:
        llm = LLMService()
        entities = neo4j_service.get_entities_for_insights(case_id, max_entities)

        total_insights = 0
        entities_processed = 0

        for entity in entities:
            new_insights = generate_entity_insights(
                entity_data={"name": entity["name"], "type": entity["type"], "summary": entity.get("summary")},
                verified_facts=entity.get("verified_facts", []),
                related_entities=entity.get("related_entities", []),
                llm_call_fn=llm.call,
            )
            if new_insights:
                neo4j_service.save_entity_insights(entity["key"], case_id, new_insights)
                total_insights += len(new_insights)
            entities_processed += 1

        return {"entities_processed": entities_processed, "insights_generated": total_insights}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/node/{node_key}/insights/{insight_index}")
async def reject_insight(
    node_key: str,
    insight_index: int,
    case_id: str = Query(..., description="REQUIRED: Case ID"),
    user: dict = Depends(get_current_user),
):
    """Reject (delete) an insight from an entity."""
    try:
        result = neo4j_service.reject_entity_insight(node_key, case_id, insight_index)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}/insights")
async def get_case_insights(case_id: str):
    """Get all pending insights across a case."""
    try:
        insights = neo4j_service.get_all_pending_insights(case_id)
        return {"insights": insights, "total": len(insights)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cases/{case_id}/rescan-locations")
async def rescan_locations(
    case_id: str,
    force_regeocode: bool = Query(False, description="Re-geocode entities that already have coordinates"),
    user: dict = Depends(get_current_user),
):
    """
    Rescan all document chunks for a case, extract geographic locations
    using GPT-5.2, geocode them, and link them to graph entities.
    """
    try:
        result = rescan_case_locations(case_id, force_regeocode=force_regeocode)

        if result.get("success"):
            system_log_service.log(
                case_id=case_id,
                log_type=LogType.GRAPH_UPDATE,
                message=f"Geo-location rescan completed: {result.get('locations_geocoded', 0)} locations geocoded, "
                        f"{result.get('entities_updated', 0)} entities updated, "
                        f"{result.get('location_nodes_created', 0)} new location nodes, "
                        f"{result.get('relationships_created', 0)} relationships created",
                origin=LogOrigin.AI_SERVICE,
                details=result,
                user=user.get("username", "unknown"),
                success=True,
            )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
