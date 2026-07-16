"""
Snapshots Router

Handles saving and retrieving investigation snapshots (saved subgraphs, timelines, notes, etc.)
"""

import asyncio
import time
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access
from services.export_security import parse_case_uuid
from services.snapshot_storage import snapshot_storage

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
    work_state: Optional[dict] = None  # Complete work state (graph, table, selections, etc.)
    case_id: Optional[str] = None
    case_version: Optional[int] = None
    case_name: Optional[str] = None


class SnapshotChunkCreate(BaseModel):
    """Request model for creating a snapshot chunk (for large snapshots)."""
    snapshot_id: str
    chunk_index: int
    chunk_data: dict  # Partial snapshot data
    is_last_chunk: bool = False
    case_id: Optional[str] = None


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


def _username(user: User) -> str:
    return user.email


def _require_case_view(db: Session, case_id: str, user: User) -> None:
    try:
        case_uuid = parse_case_uuid(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid case_id") from exc
    try:
        check_case_access(db, case_uuid, user, required_permission=("case", "view"))
    except CaseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _require_snapshot_case_view(db: Session, snapshot_data: dict, user: User) -> None:
    case_id = snapshot_data.get("case_id")
    if case_id:
        _require_case_view(db, str(case_id), user)


@router.post("", response_model=SnapshotResponse)
async def create_snapshot(
    snapshot: SnapshotCreate,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Create a new snapshot.
    
    Automatically handles chunking for large snapshots that exceed JavaScript's
    string length limits. The storage service will chunk the data if needed.
    """
    if not snapshot.case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    _require_case_view(db, snapshot.case_id, current_user)

    snapshot_id = f"snapshot_{uuid.uuid4()}"
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
        "work_state": snapshot.work_state or {},  # Include complete work state
        "timestamp": timestamp,
        "created_at": timestamp,
        "owner": _username(current_user),
        "case_id": snapshot.case_id,
        "case_version": snapshot.case_version,
        "case_name": snapshot.case_name,
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
async def list_snapshots(
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """List all snapshots for the current user."""
    snapshots = []
    all_snapshots = snapshot_storage.get_all()
    
    for snapshot_id, snapshot_data in all_snapshots.items():
        # Enforce ownership
        if snapshot_data.get("owner") != _username(current_user):
            continue
        try:
            _require_snapshot_case_view(db, snapshot_data, current_user)
        except HTTPException:
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
async def get_snapshot(
    snapshot_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Get a specific snapshot by ID."""
    try:
        snapshot = snapshot_storage.get(snapshot_id)
        
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        if snapshot.get("owner") != _username(current_user):
            raise HTTPException(status_code=404, detail="Snapshot not found")
        _require_snapshot_case_view(db, snapshot, current_user)
        
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
async def delete_snapshot(
    snapshot_id: str,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Delete a snapshot owned by the current user."""
    all_snapshots = snapshot_storage.get_all()
    snapshot_data = None
    for sid, data in all_snapshots.items():
        if sid == snapshot_id:
            snapshot_data = data
            break
    
    # If not found by key, try to find by id field (for backwards compatibility)
    if snapshot_data is None:
        for sid, data in all_snapshots.items():
            if data.get("id") == snapshot_id:
                snapshot_data = data
                snapshot_id = sid  # Use the storage key
                break
    
    if snapshot_data is None or snapshot_data.get("owner") != _username(current_user):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    _require_snapshot_case_view(db, snapshot_data, current_user)

    if not snapshot_storage.delete(snapshot_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return {"status": "deleted", "id": snapshot_id}


@router.delete("")
async def delete_all_snapshots(
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """Delete all snapshots owned by the current user."""
    all_snapshots = snapshot_storage.get_all()
    user_snapshot_ids = []
    
    for snapshot_id, snapshot_data in all_snapshots.items():
        if snapshot_data.get("owner") == _username(current_user):
            try:
                _require_snapshot_case_view(db, snapshot_data, current_user)
            except HTTPException:
                continue
            user_snapshot_ids.append(snapshot_id)
            # Also get the id field if different
            snapshot_id_field = snapshot_data.get("id")
            if snapshot_id_field and snapshot_id_field != snapshot_id:
                user_snapshot_ids.append(snapshot_id_field)
    
    deleted_count = 0
    for snapshot_id in user_snapshot_ids:
        try:
            if snapshot_storage.delete(snapshot_id):
                deleted_count += 1
        except Exception as e:
            print(f"Error deleting snapshot {snapshot_id}: {e}")

    return {"status": "deleted", "count": deleted_count}


@router.post("/restore")
async def restore_snapshot(
    snapshot_data: dict,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Restore a snapshot from case data.
    This endpoint accepts full snapshot data and saves it directly.
    """
    snapshot_id = snapshot_data.get("id")
    if not snapshot_id:
        raise HTTPException(status_code=400, detail="Snapshot ID is required")
    case_id = snapshot_data.get("case_id")
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    _require_case_view(db, str(case_id), current_user)
    
    # Save the snapshot data directly, overriding owner to current user
    existing = snapshot_storage.get(snapshot_id)
    if existing and (
        existing.get("owner") != _username(current_user)
        or str(existing.get("case_id")) != str(case_id)
    ):
        raise HTTPException(status_code=409, detail="Snapshot ID belongs to another owner or case")

    snapshot_data["owner"] = _username(current_user)
    snapshot_storage.save(snapshot_id, snapshot_data)
    
    return {"status": "restored", "id": snapshot_id}


# In-memory storage for assembling chunks during upload
_chunk_upload_cache = {}
_CHUNK_CACHE_TTL_SECONDS = 30 * 60  # 30 minutes


async def _cleanup_stale_chunks():
    """Background task that periodically removes orphaned chunk cache entries."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        now = time.monotonic()
        stale_keys = [
            key for key, entry in _chunk_upload_cache.items()
            if now - entry.get("_created_at", now) > _CHUNK_CACHE_TTL_SECONDS
        ]
        for key in stale_keys:
            print(f"[chunk-cache] Evicting stale entry: {key}")
            del _chunk_upload_cache[key]


@router.post("/upload-chunk")
async def upload_snapshot_chunk(
    chunk: SnapshotChunkCreate,
    current_user: User = Depends(get_current_db_user),
    db: Session = Depends(get_db),
):
    """
    Upload a chunk of snapshot data (for very large snapshots that can't be stringified in frontend).

    The frontend sends chunks sequentially, and the backend reassembles them.
    Call this endpoint multiple times with chunk_index incrementing, and set is_last_chunk=True on the final chunk.
    """
    snapshot_id = chunk.snapshot_id
    case_id = chunk.case_id or chunk.chunk_data.get("case_id")
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id is required")
    _require_case_view(db, str(case_id), current_user)
    cache_key = (_username(current_user), str(case_id), snapshot_id)

    # Initialize cache for this snapshot if first chunk
    if cache_key not in _chunk_upload_cache:
        if chunk.chunk_index > 0:
            raise HTTPException(status_code=409, detail="Missing initial chunk for snapshot upload")
        _chunk_upload_cache[cache_key] = {
            "chunks": {},
            "owner": _username(current_user),
            "case_id": str(case_id),
            "_created_at": time.monotonic(),
        }
    
    # Store this chunk
    _chunk_upload_cache[cache_key]["chunks"][chunk.chunk_index] = chunk.chunk_data
    
    # If this is the last chunk, reassemble and save
    if chunk.is_last_chunk:
        try:
            # Reassemble all chunks
            all_chunks = _chunk_upload_cache[cache_key]["chunks"]
            sorted_indices = sorted(all_chunks.keys())
            
            # Start with first chunk (has metadata)
            first_chunk = all_chunks[sorted_indices[0]]
            assembled = {
                "id": snapshot_id,
                "name": first_chunk.get("name", ""),
                "notes": first_chunk.get("notes", ""),
                "timestamp": first_chunk.get("timestamp", datetime.now().isoformat()),
                "created_at": first_chunk.get("created_at", datetime.now().isoformat()),
                "owner": _username(current_user),
                "subgraph": {"nodes": [], "links": []},
                "timeline": [],
                "overview": {},
                "chat_history": [],
                "ai_overview": first_chunk.get("ai_overview"),  # Include AI overview from first chunk
                "citations": first_chunk.get("citations", {}),
                "case_id": str(case_id),  # Include case info from authenticated request
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
            existing = snapshot_storage.get(snapshot_id)
            if existing and (
                existing.get("owner") != _username(current_user)
                or str(existing.get("case_id")) != str(case_id)
            ):
                raise HTTPException(status_code=409, detail="Snapshot ID belongs to another owner or case")
            snapshot_storage.save(snapshot_id, assembled)
            
            # Clean up cache
            del _chunk_upload_cache[cache_key]
            
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
            if cache_key in _chunk_upload_cache:
                del _chunk_upload_cache[cache_key]
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Failed to assemble chunks: {str(e)}")
    
    return {"status": "chunk_received", "chunk_index": chunk.chunk_index}
