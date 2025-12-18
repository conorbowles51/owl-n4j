"""
Snapshots Router

Handles saving and retrieving investigation snapshots (saved subgraphs, timelines, notes, etc.)
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.snapshot_storage import snapshot_storage
from .auth import get_current_user

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


class SnapshotData(BaseModel):
    """Data structure for a snapshot."""
    id: str
    name: str
    subgraph: dict  # {nodes: [], links: []}
    timeline: Optional[List[dict]] = None
    overview: Optional[dict] = None
    chat_history: Optional[List[dict]] = None  # Questions and responses
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
    chat_history: Optional[List[dict]] = None


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
    case_id: Optional[str] = None  # Associated case ID
    case_version: Optional[int] = None  # Associated case version
    case_name: Optional[str] = None  # Associated case name


@router.post("", response_model=SnapshotResponse)
async def create_snapshot(snapshot: SnapshotCreate, user: dict = Depends(get_current_user)):
    """Create a new snapshot."""
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
        "chat_history": snapshot.chat_history or [],
        "timestamp": timestamp,
        "created_at": timestamp,
        "owner": user["username"],
    }
    
    # Save to persistent storage
    snapshot_storage.save(snapshot_id, snapshot_data)
    
    node_count = len(snapshot.subgraph.get("nodes", []))
    link_count = len(snapshot.subgraph.get("links", []))
    timeline_count = len(snapshot.timeline or [])
    
    return SnapshotResponse(
        id=snapshot_id,
        name=snapshot.name,
        notes=snapshot.notes,
        timestamp=timestamp,
        node_count=node_count,
        link_count=link_count,
        timeline_count=timeline_count,
        created_at=timestamp,
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
    snapshot = snapshot_storage.get(snapshot_id)
    
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if snapshot.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    
    return SnapshotData(
        id=snapshot["id"],
        name=snapshot["name"],
        subgraph=snapshot["subgraph"],
        timeline=snapshot["timeline"],
        overview=snapshot["overview"],
        chat_history=snapshot["chat_history"],
        notes=snapshot["notes"],
        timestamp=snapshot["timestamp"],
        created_at=snapshot["created_at"],
        case_id=snapshot.get("case_id"),
        case_version=snapshot.get("case_version"),
        case_name=snapshot.get("case_name"),
    )


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

