"""
Case Entity Profiles Router (Phase 5)

REST API for creating and managing investigator-defined CaseEntity profiles
(Person, Address, Event, Device, Organisation, Vehicle, Other) and linking
them to graph nodes and evidence files.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services import case_entity_service
from services.case_service import get_case_if_allowed, CaseNotFound, CaseAccessDenied
from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user

router = APIRouter(prefix="/api/entities", tags=["entities"])


def _require_case_access(case_id: str, user: User, db: Session):
    try:
        get_case_if_allowed(db, case_id, user)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")


class EntityCreateRequest(BaseModel):
    case_id: str
    entity_type: str
    name: str
    # Free-form fields — values are forwarded to the service which filters.
    description: Optional[str] = None
    notes: Optional[str] = None
    aliases: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    phone_numbers: Optional[List[str]] = None
    emails: Optional[List[str]] = None
    address: Optional[str] = None
    coordinates_lat: Optional[float] = None
    coordinates_lon: Optional[float] = None
    date: Optional[str] = None
    device_model: Optional[str] = None
    imei: Optional[str] = None
    registration: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_color: Optional[str] = None
    date_of_birth: Optional[str] = None
    role: Optional[str] = None


class EntityUpdateRequest(BaseModel):
    case_id: str
    # All fields optional for PATCH
    entity_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    aliases: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    phone_numbers: Optional[List[str]] = None
    emails: Optional[List[str]] = None
    address: Optional[str] = None
    coordinates_lat: Optional[float] = None
    coordinates_lon: Optional[float] = None
    date: Optional[str] = None
    device_model: Optional[str] = None
    imei: Optional[str] = None
    registration: Optional[str] = None
    vehicle_make: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_color: Optional[str] = None
    date_of_birth: Optional[str] = None
    role: Optional[str] = None


class NodeLinkRequest(BaseModel):
    case_id: str
    node_key: str


class EvidenceLinkRequest(BaseModel):
    case_id: str
    evidence_ids: List[str]


@router.post("")
async def create_entity(
    body: EntityCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a new CaseEntity."""
    _require_case_access(body.case_id, current_user, db)
    try:
        patch = body.dict(exclude={"case_id", "entity_type", "name"}, exclude_none=True)
        created_by = getattr(current_user, "email", None) or getattr(current_user, "username", None)
        entity = case_entity_service.create_entity(
            case_id=body.case_id,
            entity_type=body.entity_type,
            name=body.name,
            patch=patch,
            created_by=created_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not entity:
        raise HTTPException(status_code=500, detail="Failed to create entity")
    return entity


@router.get("")
async def list_entities(
    case_id: str = Query(...),
    entity_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: str = Query("active"),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(case_id, current_user, db)
    return {
        "entities": case_entity_service.list_entities(
            case_id=case_id,
            entity_type=entity_type,
            search=search,
            status=status,
            limit=limit,
        )
    }


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(case_id, current_user, db)
    ent = case_entity_service.get_entity(case_id, entity_id)
    if not ent:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ent


@router.patch("/{entity_id}")
async def update_entity(
    entity_id: str,
    body: EntityUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(body.case_id, current_user, db)
    try:
        patch = body.dict(exclude={"case_id"}, exclude_none=True)
        updated = case_entity_service.update_entity(body.case_id, entity_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Entity not found")
    return updated


@router.post("/{entity_id}/archive")
async def archive_entity(
    entity_id: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(case_id, current_user, db)
    ok = case_entity_service.archive_entity(case_id, entity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"ok": True}


@router.delete("/{entity_id}")
async def delete_entity(
    entity_id: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(case_id, current_user, db)
    ok = case_entity_service.delete_entity(case_id, entity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {"ok": True}


@router.post("/{entity_id}/link/node")
async def link_node(
    entity_id: str,
    body: NodeLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(body.case_id, current_user, db)
    ok = case_entity_service.link_graph_node(body.case_id, entity_id, body.node_key)
    if not ok:
        raise HTTPException(status_code=404, detail="Entity or node not found")
    return {"ok": True}


@router.post("/{entity_id}/unlink/node")
async def unlink_node(
    entity_id: str,
    body: NodeLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(body.case_id, current_user, db)
    case_entity_service.unlink_graph_node(body.case_id, entity_id, body.node_key)
    return {"ok": True}


@router.post("/{entity_id}/link/evidence")
async def link_evidence(
    entity_id: str,
    body: EvidenceLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(body.case_id, current_user, db)
    updated = case_entity_service.link_evidence(body.case_id, entity_id, body.evidence_ids)
    return {"updated": updated, "entity_id": entity_id}


@router.post("/{entity_id}/unlink/evidence")
async def unlink_evidence(
    entity_id: str,
    body: EvidenceLinkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(body.case_id, current_user, db)
    updated = case_entity_service.unlink_evidence(body.case_id, entity_id, body.evidence_ids)
    return {"updated": updated, "entity_id": entity_id}


@router.get("/{entity_id}/context")
async def get_context(
    entity_id: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    _require_case_access(case_id, current_user, db)
    ctx = case_entity_service.get_entity_context(case_id, entity_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Entity not found")
    return ctx
