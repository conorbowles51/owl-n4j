"""
Artifacts Router

Handles saving and retrieving investigation artifacts (saved subgraphs, timelines, notes, etc.)
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


class ArtifactData(BaseModel):
    """Data structure for an artifact."""
    id: str
    name: str
    subgraph: dict  # {nodes: [], links: []}
    timeline: Optional[List[dict]] = None
    overview: Optional[dict] = None
    chat_history: Optional[List[dict]] = None  # Questions and responses
    notes: str
    timestamp: str
    created_at: str


class ArtifactCreate(BaseModel):
    """Request model for creating an artifact."""
    name: str
    notes: str
    subgraph: dict
    timeline: Optional[List[dict]] = None
    overview: Optional[dict] = None
    chat_history: Optional[List[dict]] = None


class ArtifactResponse(BaseModel):
    """Response model for an artifact."""
    id: str
    name: str
    notes: str
    timestamp: str
    node_count: int
    link_count: int
    timeline_count: int
    created_at: str


# In-memory storage (in production, use a database)
artifacts_storage = {}


@router.post("", response_model=ArtifactResponse)
async def create_artifact(artifact: ArtifactCreate):
    """Create a new artifact."""
    artifact_id = f"artifact_{datetime.now().isoformat().replace(':', '-').replace('.', '-')}"
    timestamp = datetime.now().isoformat()
    
    # Store the full artifact data
    artifacts_storage[artifact_id] = {
        "id": artifact_id,
        "name": artifact.name,
        "notes": artifact.notes,
        "subgraph": artifact.subgraph,
        "timeline": artifact.timeline or [],
        "overview": artifact.overview or {},
        "chat_history": artifact.chat_history or [],
        "timestamp": timestamp,
        "created_at": timestamp,
    }
    
    node_count = len(artifact.subgraph.get("nodes", []))
    link_count = len(artifact.subgraph.get("links", []))
    timeline_count = len(artifact.timeline or [])
    
    return ArtifactResponse(
        id=artifact_id,
        name=artifact.name,
        notes=artifact.notes,
        timestamp=timestamp,
        node_count=node_count,
        link_count=link_count,
        timeline_count=timeline_count,
        created_at=timestamp,
    )


@router.get("", response_model=List[ArtifactResponse])
async def list_artifacts():
    """List all artifacts."""
    artifacts = []
    for artifact_id, artifact_data in artifacts_storage.items():
        node_count = len(artifact_data.get("subgraph", {}).get("nodes", []))
        link_count = len(artifact_data.get("subgraph", {}).get("links", []))
        timeline_count = len(artifact_data.get("timeline", []))
        
        artifacts.append(ArtifactResponse(
            id=artifact_data["id"],
            name=artifact_data["name"],
            notes=artifact_data["notes"],
            timestamp=artifact_data["timestamp"],
            node_count=node_count,
            link_count=link_count,
            timeline_count=timeline_count,
            created_at=artifact_data["created_at"],
        ))
    
    # Sort by created_at descending (newest first)
    artifacts.sort(key=lambda x: x.created_at, reverse=True)
    return artifacts


@router.get("/{artifact_id}", response_model=ArtifactData)
async def get_artifact(artifact_id: str):
    """Get a specific artifact by ID."""
    if artifact_id not in artifacts_storage:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    artifact = artifacts_storage[artifact_id]
    return ArtifactData(
        id=artifact["id"],
        name=artifact["name"],
        subgraph=artifact["subgraph"],
        timeline=artifact["timeline"],
        overview=artifact["overview"],
        chat_history=artifact["chat_history"],
        notes=artifact["notes"],
        timestamp=artifact["timestamp"],
        created_at=artifact["created_at"],
    )


@router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str):
    """Delete an artifact."""
    if artifact_id not in artifacts_storage:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    del artifacts_storage[artifact_id]
    return {"status": "deleted", "id": artifact_id}

