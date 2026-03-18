"""
Case Deadlines Router - Deadline management for cases.

Handles CRUD operations for case deadlines with permission checks.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import CaseAccessDenied, CaseNotFound
from services.deadline_service import (
    DeadlineNotFound,
    create_deadline,
    delete_deadline,
    list_deadlines,
    update_deadline,
)

router = APIRouter(prefix="/api/cases/{case_id}/deadlines", tags=["case-deadlines"])


# --- Pydantic Schemas ---


class DeadlineCreateRequest(BaseModel):
    """Request model for creating a deadline."""

    name: str
    due_date: date


class DeadlineUpdateRequest(BaseModel):
    """Request model for updating a deadline."""

    name: str | None = None
    due_date: date | None = None


class DeadlineResponse(BaseModel):
    """Response model for a single deadline."""

    id: UUID
    case_id: UUID
    name: str
    due_date: date
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeadlineListResponse(BaseModel):
    """Response model for listing deadlines."""

    deadlines: list[DeadlineResponse]
    total: int


# --- Routes ---


@router.post("", response_model=DeadlineResponse, status_code=status.HTTP_201_CREATED)
def create_new_deadline(
    case_id: UUID,
    request: DeadlineCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Create a new deadline for a case. Requires case.edit permission."""
    try:
        deadline = create_deadline(
            db=db,
            case_id=case_id,
            user=current_user,
            name=request.name,
            due_date=request.due_date,
        )
        return deadline
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


@router.get("", response_model=DeadlineListResponse)
def list_case_deadlines(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List all deadlines for a case. Requires case.view permission."""
    try:
        deadlines = list_deadlines(db=db, case_id=case_id, user=current_user)
        return DeadlineListResponse(
            deadlines=[DeadlineResponse.model_validate(d) for d in deadlines],
            total=len(deadlines),
        )
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


@router.patch("/{deadline_id}", response_model=DeadlineResponse)
def update_existing_deadline(
    case_id: UUID,
    deadline_id: UUID,
    request: DeadlineUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Update a deadline. Requires case.edit permission."""
    try:
        deadline = update_deadline(
            db=db,
            deadline_id=deadline_id,
            case_id=case_id,
            user=current_user,
            name=request.name,
            due_date=request.due_date,
        )
        return deadline
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
    except DeadlineNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deadline not found",
        )


@router.delete("/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_deadline(
    case_id: UUID,
    deadline_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Delete a deadline. Requires case.edit permission."""
    try:
        delete_deadline(
            db=db,
            deadline_id=deadline_id,
            case_id=case_id,
            user=current_user,
        )
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
    except DeadlineNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deadline not found",
        )
