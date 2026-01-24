"""
Cases Router - PostgreSQL-backed implementation.

Handles CRUD operations for investigation cases with permission-based access control.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.enums import CaseMembershipRole
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

    Any authenticated user can create a case. The creator becomes the owner
    with full permissions.
    """
    case = create_case(
        db=db,
        creator=current_user,
        title=request.title,
        description=request.description,
    )
    return case


@router.get("", response_model=CaseListResponse)
def list_cases(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    List all cases accessible to the current user.

    - Super admins see all cases
    - Regular users see cases they are members of
    """
    cases = list_cases_for_user(db=db, user=current_user)
    return CaseListResponse(cases=cases, total=len(cases))


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
