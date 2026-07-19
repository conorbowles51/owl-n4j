"""Case-wide Significant manifest endpoints."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access, get_case_if_allowed
from services.neo4j_service import neo4j_service
from services.significant_service import (
    add_significant_entities,
    clear_significant_entities,
    list_significant_entities,
    normalize_entity_keys,
    remove_significant_entities,
)


router = APIRouter(prefix="/api/significant", tags=["significant"])

AdditionSource = Literal["manual", "selection", "spotlight", "agent", "migration"]


class SignificantItemResponse(BaseModel):
    id: str
    case_id: str
    entity_key: str
    addition_source: str
    context: dict[str, Any] = Field(default_factory=dict)
    added_by_user_id: str | None = None
    added_by_name: str | None = None
    added_by_email: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SignificantManifestResponse(BaseModel):
    case_id: str
    entity_keys: list[str] = Field(default_factory=list)
    items: list[SignificantItemResponse] = Field(default_factory=list)
    count: int
    added_count: int | None = None
    already_significant_count: int | None = None
    missing_count: int | None = None
    added_entity_keys: list[str] | None = None
    missing_entity_keys: list[str] | None = None
    removed_count: int | None = None
    not_significant_count: int | None = None
    removed_entity_keys: list[str] | None = None


class SignificantBatchAddRequest(BaseModel):
    entity_keys: list[str] = Field(..., min_length=1, max_length=10_000)
    source: AdditionSource = "manual"
    context: dict[str, Any] = Field(default_factory=dict)


class SignificantBatchRemoveRequest(BaseModel):
    entity_keys: list[str] = Field(..., min_length=1, max_length=10_000)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, CaseNotFound):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found") from exc
    if isinstance(exc, CaseAccessDenied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied") from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/{case_id}", response_model=SignificantManifestResponse)
def get_significant_manifest(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        get_case_if_allowed(db=db, case_id=case_id, user=current_user)
        return list_significant_entities(db, case_id=case_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/{case_id}/entities:batch", response_model=SignificantManifestResponse)
def add_entities_to_significant(
    case_id: UUID,
    request: SignificantBatchAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(
            db=db,
            case_id=case_id,
            user=current_user,
            required_permission=("case", "edit"),
        )
        requested_keys = normalize_entity_keys(request.entity_keys)
        existing_keys = neo4j_service.get_existing_node_keys(
            str(case_id),
            requested_keys,
        )
        existing_key_set = set(existing_keys)
        missing_keys = [key for key in requested_keys if key not in existing_key_set]
        result = add_significant_entities(
            db,
            case_id=case_id,
            current_user=current_user,
            entity_keys=existing_keys,
            addition_source=request.source,
            context=request.context,
        )
        return {
            **result,
            "missing_count": len(missing_keys),
            "missing_entity_keys": missing_keys,
        }
    except Exception as exc:
        db.rollback()
        _handle_error(exc)


@router.post("/{case_id}/entities:remove", response_model=SignificantManifestResponse)
def remove_entities_from_significant(
    case_id: UUID,
    request: SignificantBatchRemoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(
            db=db,
            case_id=case_id,
            user=current_user,
            required_permission=("case", "edit"),
        )
        return remove_significant_entities(
            db,
            case_id=case_id,
            current_user=current_user,
            entity_keys=request.entity_keys,
        )
    except Exception as exc:
        db.rollback()
        _handle_error(exc)


@router.delete("/{case_id}", response_model=SignificantManifestResponse)
def clear_significant_manifest(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(
            db=db,
            case_id=case_id,
            user=current_user,
            required_permission=("case", "edit"),
        )
        return clear_significant_entities(
            db,
            case_id=case_id,
            current_user=current_user,
        )
    except Exception as exc:
        db.rollback()
        _handle_error(exc)
