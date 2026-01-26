"""
Cases Router - PostgreSQL-backed implementation.

Handles CRUD operations for investigation cases with permission-based access control.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import (
    CaseAccessDenied,
    CaseNotFound,
    create_case,
    delete_case,
    list_cases_for_user,
    update_case,
    get_case_if_allowed,
    get_user_role_for_case,
    is_super_admin,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])


# --- Pydantic Schemas ---


class CaseCreateRequest(BaseModel):
    """Request model for creating a case."""

    title: str
    description: str | None = None


class CaseUpdateRequest(BaseModel):
    """Request model for updating a case."""

    title: str | None = None
    description: str | None = None


class CaseResponse(BaseModel):
    """Response model for a single case."""

    id: UUID
    title: str
    description: str | None
    created_by_user_id: UUID
    owner_user_id: UUID
    created_at: datetime
    updated_at: datetime
    # Enriched fields for display
    owner_name: str | None = None  # Display name of case owner
    user_role: str | None = None  # 'owner', 'editor', 'viewer', 'admin_access'
    is_owner: bool = False  # True ONLY if user is actual owner

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    """Response model for listing cases."""

    cases: list[CaseResponse]
    total: int


# --- Routes ---


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_new_case(
    request: CaseCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Create a new case.

    Any authenticated user can create a case (except guests). The creator becomes
    the owner with full permissions.
    """
    # Guests cannot create cases
    if current_user.global_role == GlobalRole.guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guests cannot create cases",
        )

    case = create_case(
        db=db,
        creator=current_user,
        title=request.title,
        description=request.description,
    )
    return case


@router.get("", response_model=CaseListResponse)
def list_cases(
    view_mode: str = Query("my_cases", description="'my_cases' or 'all_cases' (super admins only)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    List all cases accessible to the current user.

    Query params:
    - view_mode: 'my_cases' (default) shows only cases user is a member of.
                 'all_cases' shows all cases (super admins only).

    Response includes enriched fields:
    - owner_name: Display name of the case owner
    - user_role: 'owner', 'editor', 'viewer', or 'admin_access'
    - is_owner: True only if user is the actual owner (not synthetic admin access)
    """
    user_is_super_admin = is_super_admin(current_user)

    # Only super admins can use "all_cases" mode
    include_all = view_mode == "all_cases" and user_is_super_admin

    case_tuples = list_cases_for_user(db=db, user=current_user, include_all=include_all)

    # Build enriched response
    enriched_cases = []
    for case, membership, owner in case_tuples:
        user_role = get_user_role_for_case(membership, user_is_super_admin)
        is_actual_owner = (
            membership is not None
            and membership.membership_role.value == "owner"
        )

        enriched_case = CaseResponse(
            id=case.id,
            title=case.title,
            description=case.description,
            created_by_user_id=case.created_by_user_id,
            owner_user_id=case.owner_user_id,
            created_at=case.created_at,
            updated_at=case.updated_at,
            owner_name=owner.name if owner else None,
            user_role=user_role,
            is_owner=is_actual_owner,
        )
        enriched_cases.append(enriched_case)

    return CaseListResponse(cases=enriched_cases, total=len(enriched_cases))


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Get a specific case by ID.

    Requires case.view permission.
    """
    try:
        case = get_case_if_allowed(db=db, case_id=case_id, user=current_user)
        return case
    except CaseNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


@router.patch("/{case_id}", response_model=CaseResponse)
def update_existing_case(
    case_id: UUID,
    request: CaseUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Update a case's title and/or description.

    Requires case.edit permission.
    """
    try:
        case = update_case(
            db=db,
            case_id=case_id,
            user=current_user,
            title=request.title,
            description=request.description,
        )
        return case
    except CaseNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - case.edit permission required",
        )


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Delete a case.

    Requires case.delete permission. This will cascade-delete all memberships.
    """
    try:
        delete_case(db=db, case_id=case_id, user=current_user)
    except CaseNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - case.delete permission required",
        )
