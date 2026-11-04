"""
Snapshots Router

Handles saving and retrieving investigation snapshots (saved subgraphs, timelines, notes, etc.)
"""

import asyncio
import time
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, get_case_if_allowed
from services.snapshot_storage import snapshot_storage
from services import snapshot_report
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


def _own_removed(db, user):
    from postgres.models.removed_record import RemovedRecord
    from sqlalchemy import select
    rows = db.scalars(select(RemovedRecord).where(RemovedRecord.kind == "snapshot", RemovedRecord.restored_at.is_(None))
                      .order_by(RemovedRecord.removed_at.desc())).all()
    return [r for r in rows if ((r.data or {}).get("rows") or [{}])[0].get("values", {}).get("owner") == user["username"]]


@router.get("/removed")
def list_removed_snapshots(user: dict = Depends(get_current_user)):
    """The person's own removed snapshots that can be put back (followups m11032229063349)."""
    from postgres.session import _get_session_local
    from services import removed_records
    with _get_session_local()() as db:
        return {"items": [removed_records.as_dict(r) for r in _own_removed(db, user)]}


@router.post("/removed/{removed_id}/restore")
def restore_removed_snapshot(removed_id: str, user: dict = Depends(get_current_user)):
    """Put a removed snapshot back exactly as it was. Only its owner may."""
    from postgres.session import _get_session_local
    from services import removed_records
    with _get_session_local()() as db:
        if removed_id not in {str(r.id) for r in _own_removed(db, user)}:
            raise HTTPException(status_code=404, detail="Removed snapshot not found")
        try:
            out = removed_records.restore(db, removed_records.load(db, removed_id), user=user)
        except removed_records.RemovedRecordError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc))
        db.commit()
        return out


def _case_for(db: Session, case_id: str | None, db_user: User):
    if not case_id:
        return None
    try:
        return get_case_if_allowed(db=db, case_id=UUID(str(case_id)), user=db_user)
    except (CaseNotFound, ValueError):
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail="You do not have access to this case")


def snapshot_events(db: Session, case_id: str, subgraph: dict) -> list[dict]:
    """The timeline events among the snapshot's own entities, frozen as they read now (never the whole case's)."""
    from services.timeline_view_service import _fetch_current_events

    keys = []
    for node in subgraph.get("nodes") or []:
        key = str((node or {}).get("key") or (node or {}).get("id") or "")
        if key and key not in keys:
            keys.append(key)
    if not keys:
        return []
    return snapshot_report.frozen_events(_fetch_current_events(db, case_id, keys, require_all=False))


class SnapshotReportRequest(BaseModel):
    privilege_marking: str = "unmarked"


@router.post("", response_model=SnapshotResponse)
def create_snapshot(
    snapshot: SnapshotCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    db_user: User = Depends(get_current_db_user),
):
    """
    Create a new snapshot.
    
    Automatically handles chunking for large snapshots that exceed JavaScript's
    string length limits. The storage service will chunk the data if needed.
    """
    snapshot_id = f"snapshot_{datetime.now().isoformat().replace(':', '-').replace('.', '-')}"
    timestamp = datetime.now().isoformat()
    case = _case_for(db, snapshot.case_id, db_user)
    timeline = snapshot.timeline
    if timeline is None and case is not None:
        # Saved from the graph: the snapshot keeps the events among its own entities, so its report prints
        # those and only those (BUG-012: the old report printed every event in the case).
        try:
            timeline = snapshot_events(db, str(case.id), snapshot.subgraph or {})
        except Exception as exc:  # the graph store being unreachable must not lose the snapshot itself
            print(f"Snapshot {snapshot_id}: events not captured ({exc}); saved without events")
            timeline = []
    
    # Store the full snapshot data
    snapshot_data = {
        "id": snapshot_id,
        "name": snapshot.name,
        "notes": snapshot.notes,
        "subgraph": snapshot.subgraph,
        "timeline": timeline or [],
        "overview": snapshot.overview or {},
        "citations": snapshot.citations or {},
        "chat_history": snapshot.chat_history or [],
        "ai_overview": snapshot.ai_overview,  # Include AI overview
        "work_state": snapshot.work_state or {},  # Include complete work state
        "timestamp": timestamp,
        "created_at": timestamp,
        "owner": user["username"],
        "case_id": snapshot.case_id,
        "case_version": snapshot.case_version,
        "case_name": snapshot.case_name or (case.title if case is not None else None),
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
def list_snapshots(user: dict = Depends(get_current_user), case_id: Optional[str] = Query(None)):
    """List all snapshots for the current user."""
    snapshots = []
    all_snapshots = snapshot_storage.get_all()
    
    for snapshot_id, snapshot_data in all_snapshots.items():
        # Enforce ownership
        if snapshot_data.get("owner") != user["username"]:
            continue
        if case_id and str(snapshot_data.get("case_id") or "") != case_id:
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


@router.post("/{snapshot_id}/report")
def snapshot_report_pdf(
    snapshot_id: str,
    request: SnapshotReportRequest,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    db_user: User = Depends(get_current_db_user),
):
    """The snapshot as a PDF: its graph, its own events with their sources, and the chosen privilege marking."""
    snapshot = snapshot_storage.get(snapshot_id)
    if snapshot is None or snapshot.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    case = _case_for(db, snapshot.get("case_id"), db_user)
    try:
        content = snapshot_report.render_snapshot_report_pdf(
            snapshot,
            case_name=(case.title if case is not None else snapshot.get("case_name")) or "",
            generated_by=db_user.name or db_user.email,
            privilege_marking=request.privilege_marking,
        )
    except snapshot_report.SnapshotReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    filename = snapshot_report.report_filename(snapshot)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename)}'},
    )


@router.get("/{snapshot_id}", response_model=SnapshotData)
def get_snapshot(snapshot_id: str, user: dict = Depends(get_current_user)):
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
def delete_snapshot(snapshot_id: str, user: dict = Depends(get_current_user)):
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
    
    if snapshot_data is None or snapshot_data.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    if not snapshot_storage.delete(snapshot_id, removed_by=user):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return {"status": "deleted", "id": snapshot_id}


@router.delete("")
def delete_all_snapshots(user: dict = Depends(get_current_user)):
    """Delete all snapshots owned by the current user."""
    all_snapshots = snapshot_storage.get_all()
    user_snapshot_ids = []
    
    for snapshot_id, snapshot_data in all_snapshots.items():
        if snapshot_data.get("owner") == user["username"]:
            user_snapshot_ids.append(snapshot_id)
            # Also get the id field if different
            snapshot_id_field = snapshot_data.get("id")
            if snapshot_id_field and snapshot_id_field != snapshot_id:
                user_snapshot_ids.append(snapshot_id_field)
    
    deleted_count = 0
    for snapshot_id in user_snapshot_ids:
        try:
            if snapshot_storage.delete(snapshot_id, removed_by=user):
                deleted_count += 1
        except Exception as e:
            print(f"Error deleting snapshot {snapshot_id}: {e}")

    return {"status": "deleted", "count": deleted_count}


@router.post("/restore")
def restore_snapshot(snapshot_data: dict, user: dict = Depends(get_current_user)):
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
_CHUNK_CACHE_TTL_SECONDS = 30 * 60  # 30 minutes


async def _cleanup_stale_chunks():
    """Background task that periodically removes orphaned chunk cache entries."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        now = time.monotonic()
        stale_ids = [
            sid for sid, entry in _chunk_upload_cache.items()
            if now - entry.get("_created_at", now) > _CHUNK_CACHE_TTL_SECONDS
        ]
        for sid in stale_ids:
            print(f"[chunk-cache] Evicting stale entry: {sid}")
            del _chunk_upload_cache[sid]


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
            "_created_at": time.monotonic(),
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
            await run_in_threadpool(snapshot_storage.save, snapshot_id, assembled)
            
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

