"""
Snapshots Router

Handles saving and retrieving investigation snapshots (saved subgraphs, timelines, notes, etc.)
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.snapshot_storage import snapshot_storage
from services.snapshot_chunk_storage import save_chunk, reassemble_chunks
from .auth import get_current_user

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


class SnapshotData(BaseModel):
    """Data structure for a snapshot."""
    id: str
    name: str
    subgraph: dict  # {nodes: [], links: []}
    timeline: Optional[List[dict]] = None
    overview: Optional[dict] = None
    citations: Optional[dict] = None  # Citations and references to source documents
    chat_history: Optional[List[dict]] = None  # Questions and responses
    ai_overview: Optional[str] = None  # AI-generated overview of the snapshot
    notes: str
    timestamp: str
    created_at: str
    case_id: Optional[str] = None  # Associated case ID
    case_version: Optional[int] = None  # Associated case version
    case_name: Optional[str] = None  # Associated case name


class SnapshotCreate(BaseModel):
    """Request model for creating a snapshot."""
    name: str
    notes: str
    subgraph: dict
    timeline: Optional[List[dict]] = None
    overview: Optional[dict] = None
    citations: Optional[dict] = None  # Citations and references to source documents
    chat_history: Optional[List[dict]] = None
    ai_overview: Optional[str] = None  # AI-generated overview of the snapshot


class SnapshotChunkCreate(BaseModel):
    """Request model for creating a snapshot chunk (for large snapshots)."""
    snapshot_id: str
    chunk_index: int
    chunk_data: dict  # Partial snapshot data
    is_last_chunk: bool = False


class SnapshotResponse(BaseModel):
    """Response model for a snapshot."""
    id: str
    name: str
    notes: str
    timestamp: str
    node_count: int
    link_count: int
    timeline_count: int
    created_at: str
    ai_overview: Optional[str] = None  # AI-generated overview
    case_id: Optional[str] = None  # Associated case ID
    case_version: Optional[int] = None  # Associated case version
    case_name: Optional[str] = None  # Associated case name


@router.post("", response_model=SnapshotResponse)
async def create_snapshot(snapshot: SnapshotCreate, user: dict = Depends(get_current_user)):
    """
    Create a new snapshot.
    
    Automatically handles chunking for large snapshots that exceed JavaScript's
    string length limits. The storage service will chunk the data if needed.
    """
    snapshot_id = f"snapshot_{datetime.now().isoformat().replace(':', '-').replace('.', '-')}"
    timestamp = datetime.now().isoformat()
    
    # Store the full snapshot data
    snapshot_data = {
        "id": snapshot_id,
        "name": snapshot.name,
        "notes": snapshot.notes,
        "subgraph": snapshot.subgraph,
        "timeline": snapshot.timeline or [],
        "overview": snapshot.overview or {},
        "citations": snapshot.citations or {},
        "chat_history": snapshot.chat_history or [],
        "ai_overview": snapshot.ai_overview,  # Include AI overview
        "timestamp": timestamp,
        "created_at": timestamp,
        "owner": user["username"],
        "case_id": getattr(snapshot, "case_id", None),  # Include case info if provided
        "case_version": getattr(snapshot, "case_version", None),
        "case_name": getattr(snapshot, "case_name", None),
    }
    
    # Save to persistent storage (will automatically chunk if too large)
    try:
        snapshot_storage.save(snapshot_id, snapshot_data)
    except Exception as e:
        # If save fails, it might be due to size - the storage service should handle chunking
        # But if it still fails, raise the error
        raise HTTPException(status_code=500, detail=f"Failed to save snapshot: {str(e)}")
    
    # Get the saved snapshot to check if it was chunked
    saved_snapshot = snapshot_storage.get(snapshot_id)
    if saved_snapshot is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve saved snapshot")
    
    node_count = len(saved_snapshot.get("subgraph", {}).get("nodes", []))
    link_count = len(saved_snapshot.get("subgraph", {}).get("links", []))
    timeline_count = len(saved_snapshot.get("timeline", []))
    
    return SnapshotResponse(
        id=snapshot_id,
        name=saved_snapshot["name"],
        notes=saved_snapshot["notes"],
        timestamp=saved_snapshot["timestamp"],
        node_count=node_count,
        link_count=link_count,
        timeline_count=timeline_count,
        created_at=saved_snapshot["created_at"],
        ai_overview=saved_snapshot.get("ai_overview"),  # Include AI overview
        case_id=saved_snapshot.get("case_id"),
        case_version=saved_snapshot.get("case_version"),
        case_name=saved_snapshot.get("case_name"),
    )


@router.get("", response_model=List[SnapshotResponse])
async def list_snapshots(user: dict = Depends(get_current_user)):
    """List all snapshots for the current user."""
    snapshots = []
    all_snapshots = snapshot_storage.get_all()
    
    for snapshot_id, snapshot_data in all_snapshots.items():
        # Enforce ownership
        if snapshot_data.get("owner") != user["username"]:
            continue

        node_count = len(snapshot_data.get("subgraph", {}).get("nodes", []))
        link_count = len(snapshot_data.get("subgraph", {}).get("links", []))
        timeline_count = len(snapshot_data.get("timeline", []))
        
        snapshots.append(SnapshotResponse(
            id=snapshot_data["id"],
            name=snapshot_data["name"],
            notes=snapshot_data["notes"],
            timestamp=snapshot_data["timestamp"],
            node_count=node_count,
            link_count=link_count,
            timeline_count=timeline_count,
            created_at=snapshot_data["created_at"],
            ai_overview=snapshot_data.get("ai_overview"),
            case_id=snapshot_data.get("case_id"),
            case_version=snapshot_data.get("case_version"),
            case_name=snapshot_data.get("case_name"),
        ))
    
    # Sort by created_at descending (newest first)
    snapshots.sort(key=lambda x: x.created_at, reverse=True)
    return snapshots


@router.get("/{snapshot_id}", response_model=SnapshotData)
async def get_snapshot(snapshot_id: str, user: dict = Depends(get_current_user)):
    """Get a specific snapshot by ID."""
    try:
        snapshot = snapshot_storage.get(snapshot_id)
        
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        if snapshot.get("owner") != user["username"]:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        # Ensure all required fields have defaults for backward compatibility
        return SnapshotData(
            id=snapshot.get("id", snapshot_id),
            name=snapshot.get("name", "Unnamed Snapshot"),
            subgraph=snapshot.get("subgraph", {"nodes": [], "links": []}),
            timeline=snapshot.get("timeline", []),
            overview=snapshot.get("overview", {}),
            citations=snapshot.get("citations", {}),
            chat_history=snapshot.get("chat_history", []),
            ai_overview=snapshot.get("ai_overview"),
            notes=snapshot.get("notes", ""),
            timestamp=snapshot.get("timestamp", datetime.now().isoformat()),
            created_at=snapshot.get("created_at", snapshot.get("timestamp", datetime.now().isoformat())),
            case_id=snapshot.get("case_id"),
            case_version=snapshot.get("case_version"),
            case_name=snapshot.get("case_name"),
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting snapshot {snapshot_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to retrieve snapshot: {str(e)}")


@router.delete("/{snapshot_id}")
async def delete_snapshot(snapshot_id: str, user: dict = Depends(get_current_user)):
    """Delete a snapshot."""
    snapshot = snapshot_storage.get(snapshot_id)
    if snapshot is None or snapshot.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    if not snapshot_storage.delete(snapshot_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    return {"status": "deleted", "id": snapshot_id}


@router.post("/restore")
async def restore_snapshot(snapshot_data: dict, user: dict = Depends(get_current_user)):
    """
    Restore a snapshot from case data.
    This endpoint accepts full snapshot data and saves it directly.
    """
    snapshot_id = snapshot_data.get("id")
    if not snapshot_id:
        raise HTTPException(status_code=400, detail="Snapshot ID is required")
    
    # Save the snapshot data directly, overriding owner to current user
    snapshot_data["owner"] = user["username"]
    snapshot_storage.save(snapshot_id, snapshot_data)
    
    return {"status": "restored", "id": snapshot_id}


# In-memory storage for assembling chunks during upload
_chunk_upload_cache = {}


@router.post("/upload-chunk")
async def upload_snapshot_chunk(
    chunk: SnapshotChunkCreate,
    user: dict = Depends(get_current_user)
):
    """
    Upload a chunk of snapshot data (for very large snapshots that can't be stringified in frontend).
    
    The frontend sends chunks sequentially, and the backend reassembles them.
    Call this endpoint multiple times with chunk_index incrementing, and set is_last_chunk=True on the final chunk.
    """
    snapshot_id = chunk.snapshot_id
    
    # Initialize cache for this snapshot if first chunk
    if snapshot_id not in _chunk_upload_cache:
        _chunk_upload_cache[snapshot_id] = {
            "chunks": {},
            "owner": user["username"],
        }
    
    # Store this chunk
    _chunk_upload_cache[snapshot_id]["chunks"][chunk.chunk_index] = chunk.chunk_data
    
    # If this is the last chunk, reassemble and save
    if chunk.is_last_chunk:
        try:
            # Reassemble all chunks
            all_chunks = _chunk_upload_cache[snapshot_id]["chunks"]
            sorted_indices = sorted(all_chunks.keys())
            
            # Start with first chunk (has metadata)
            first_chunk = all_chunks[sorted_indices[0]]
            assembled = {
                "id": snapshot_id,
                "name": first_chunk.get("name", ""),
                "notes": first_chunk.get("notes", ""),
                "timestamp": first_chunk.get("timestamp", datetime.now().isoformat()),
                "created_at": first_chunk.get("created_at", datetime.now().isoformat()),
                "owner": user["username"],
                "subgraph": {"nodes": [], "links": []},
                "timeline": [],
                "overview": {},
                "chat_history": [],
                "ai_overview": first_chunk.get("ai_overview"),  # Include AI overview from first chunk
                "citations": first_chunk.get("citations", {}),
                "case_id": first_chunk.get("case_id"),  # Include case info from first chunk
                "case_version": first_chunk.get("case_version"),
                "case_name": first_chunk.get("case_name"),
            }
            
            # Merge all chunks
            for idx in sorted_indices:
                chunk_data = all_chunks[idx]
                
                # Merge subgraph nodes
                if "subgraph" in chunk_data:
                    subgraph = chunk_data["subgraph"]
                    if "nodes" in subgraph:
                        assembled["subgraph"]["nodes"].extend(subgraph["nodes"])
                    if "links" in subgraph and subgraph["links"]:
                        assembled["subgraph"]["links"] = subgraph["links"]  # Links only from first chunk
                
                # Merge timeline
                if "timeline" in chunk_data:
                    assembled["timeline"].extend(chunk_data["timeline"])
                
                # Merge overview (last one wins, or merge if dict)
                if "overview" in chunk_data:
                    if isinstance(assembled["overview"], dict) and isinstance(chunk_data["overview"], dict):
                        assembled["overview"].update(chunk_data["overview"])
                    else:
                        assembled["overview"] = chunk_data["overview"]
                
                # Merge chat_history
                if "chat_history" in chunk_data:
                    assembled["chat_history"].extend(chunk_data["chat_history"])
            
            # Save the assembled snapshot
            snapshot_storage.save(snapshot_id, assembled)
            
            # Clean up cache
            del _chunk_upload_cache[snapshot_id]
            
            node_count = len(assembled.get("subgraph", {}).get("nodes", []))
            link_count = len(assembled.get("subgraph", {}).get("links", []))
            timeline_count = len(assembled.get("timeline", []))
            
            return {
                "status": "completed",
                "id": snapshot_id,
                "node_count": node_count,
                "link_count": link_count,
                "timeline_count": timeline_count,
            }
        except Exception as e:
            # Clean up cache on error
            if snapshot_id in _chunk_upload_cache:
                del _chunk_upload_cache[snapshot_id]
            raise HTTPException(status_code=500, detail=f"Failed to assemble chunks: {str(e)}")
    
    return {"status": "chunk_received", "chunk_index": chunk.chunk_index}

