"""
Cases Router

Handles saving and retrieving investigation cases with versioning.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.case_storage import case_storage
from services.cypher_generator import generate_cypher_from_graph

router = APIRouter(prefix="/api/cases", tags=["cases"])


class CaseCreate(BaseModel):
    """Request model for creating/saving a case version."""
    case_id: Optional[str] = None  # None to create new case
    case_name: str
    graph_data: dict  # {nodes: [], links: []}
    snapshots: List[dict] = []  # Full snapshot data, not just IDs
    save_notes: str = ""


class CaseVersionData(BaseModel):
    """Data structure for a case version."""
    version: int
    cypher_queries: str
    snapshots: List[dict]  # Full snapshot data
    save_notes: str
    timestamp: str


class CaseData(BaseModel):
    """Data structure for a case."""
    id: str
    name: str
    created_at: str
    updated_at: str
    versions: List[CaseVersionData]


class CaseResponse(BaseModel):
    """Response model for case listing."""
    id: str
    name: str
    created_at: str
    updated_at: str
    version_count: int
    latest_version: int


@router.post("", response_model=dict)
async def save_case(case: CaseCreate):
    """Save a new version of a case."""
    try:
        # Generate Cypher queries from graph data
        cypher_queries = generate_cypher_from_graph(case.graph_data)
        
        # Save case version
        result = case_storage.save_case_version(
            case_id=case.case_id,
            case_name=case.case_name,
            cypher_queries=cypher_queries,
            snapshots=case.snapshots,
            save_notes=case.save_notes,
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save case: {str(e)}")


@router.get("", response_model=List[CaseResponse])
async def list_cases():
    """List all cases."""
    cases = []
    all_cases = case_storage.get_all()
    
    for case_id, case_data in all_cases.items():
        versions = case_data.get("versions", [])
        latest_version = max([v.get("version", 0) for v in versions], default=0)
        
        cases.append(CaseResponse(
            id=case_data["id"],
            name=case_data["name"],
            created_at=case_data["created_at"],
            updated_at=case_data.get("updated_at", case_data["created_at"]),
            version_count=len(versions),
            latest_version=latest_version,
        ))
    
    # Sort by updated_at descending (most recently updated first)
    cases.sort(key=lambda x: x.updated_at, reverse=True)
    return cases


@router.get("/{case_id}", response_model=CaseData)
async def get_case(case_id: str):
    """Get a specific case with all versions."""
    case = case_storage.get_case(case_id)
    
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Convert versions to CaseVersionData
    versions = [
        CaseVersionData(
            version=v.get("version", 0),
            cypher_queries=v.get("cypher_queries", ""),
            snapshots=v.get("snapshots", []),  # Full snapshot data
            save_notes=v.get("save_notes", ""),
            timestamp=v.get("timestamp", ""),
        )
        for v in case.get("versions", [])
    ]
    
    return CaseData(
        id=case["id"],
        name=case["name"],
        created_at=case["created_at"],
        updated_at=case.get("updated_at", case["created_at"]),
        versions=versions,
    )


@router.get("/{case_id}/versions/{version}", response_model=CaseVersionData)
async def get_case_version(case_id: str, version: int):
    """Get a specific version of a case."""
    case = case_storage.get_case(case_id)
    
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    
    versions = case.get("versions", [])
    version_data = next((v for v in versions if v.get("version") == version), None)
    
    if version_data is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    
    return CaseVersionData(
        version=version_data.get("version", 0),
        cypher_queries=version_data.get("cypher_queries", ""),
        snapshots=version_data.get("snapshots", []),  # Full snapshot data
        save_notes=version_data.get("save_notes", ""),
        timestamp=version_data.get("timestamp", ""),
    )


@router.delete("/{case_id}")
async def delete_case(case_id: str):
    """Delete a case."""
    if not case_storage.delete_case(case_id):
        raise HTTPException(status_code=404, detail="Case not found")
    
    return {"status": "deleted", "id": case_id}

