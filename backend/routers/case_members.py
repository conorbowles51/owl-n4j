"""
Case Members Router - Collaborator management.

Handles adding, listing, updating, and removing case members with permission checks.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.case_service import (
    AlreadyMember,
    CannotModifyOwner,
    CaseAccessDenied,
    CaseNotFound,
    UserNotFound,
    add_case_member,
    list_case_members,
    remove_case_member,
    update_member_permissions,
)

router = APIRouter(prefix="/api/cases/{case_id}/members", tags=["case-members"])


# --- Pydantic Schemas ---


class MemberAddRequest(BaseModel):
    """Request model for adding a case member."""

    user_id: UUID
    preset: str | None = None  # 'viewer', 'editor'
    permissions: dict | None = None  # Custom permissions (overrides preset)
    role: CaseMembershipRole = CaseMembershipRole.collaborator


class MemberUpdateRequest(BaseModel):
    """Request model for updating a member's permissions."""

    preset: str | None = None  # 'viewer', 'editor'
    permissions: dict | None = None  # Custom permissions (overrides preset)


class MemberUserResponse(BaseModel):
    """Nested user info in member response."""

    id: UUID
    email: str
    name: str

    class Config:
        from_attributes = True


class MemberResponse(BaseModel):
    """Response model for a case member."""

    case_id: UUID
    user_id: UUID
    membership_role: CaseMembershipRole
    permissions: dict
    added_by_user_id: UUID
    created_at: datetime
    updated_at: datetime
    user: MemberUserResponse | None = None

    class Config:
        from_attributes = True


class MemberListResponse(BaseModel):
    """Response model for listing case members."""

    members: list[MemberResponse]
    total: int


# --- Helper Functions ---


def membership_to_response(membership: CaseMembership) -> MemberResponse:
    """Convert a CaseMembership to a MemberResponse with user info."""
    user_info = None
    if membership.user:
        user_info = MemberUserResponse(
            id=membership.user.id,
            email=membership.user.email,
            name=membership.user.name,
        )

    return MemberResponse(
        case_id=membership.case_id,
        user_id=membership.user_id,
        membership_role=membership.membership_role,
        permissions=membership.permissions,
        added_by_user_id=membership.added_by_user_id,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
        user=user_info,
    )


# --- Routes ---


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(
    case_id: UUID,
    request: MemberAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Add a new member to a case.

    Requires collaborators.invite permission.

    You can specify either:
    - `preset`: 'viewer' or 'editor' for predefined permission sets
    - `permissions`: Custom permissions dict

    If both are provided, `permissions` takes precedence.
    """
    try:
        membership = add_case_member(
            db=db,
            case_id=case_id,
            actor=current_user,
            target_user_id=request.user_id,
            permissions=request.permissions,
            preset=request.preset,
            role=request.role,
        )
        return membership_to_response(membership)
    except CaseNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - collaborators.invite permission required",
        )
    except UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    except AlreadyMember:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this case",
        )


@router.get("", response_model=MemberListResponse)
def list_members(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    List all members of a case.

    Requires case.view permission.
    """
    try:
        members = list_case_members(db=db, case_id=case_id, user=current_user)
        return MemberListResponse(
            members=[membership_to_response(m) for m in members],
            total=len(members),
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


@router.patch("/{user_id}", response_model=MemberResponse)
def update_member(
    case_id: UUID,
    user_id: UUID,
    request: MemberUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Update a member's permissions.

    Requires collaborators.invite permission. Cannot modify the case owner.

    You can specify either:
    - `preset`: 'viewer' or 'editor' for predefined permission sets
    - `permissions`: Custom permissions dict

    If both are provided, `permissions` takes precedence.
    """
    try:
        membership = update_member_permissions(
            db=db,
            case_id=case_id,
            actor=current_user,
            target_user_id=user_id,
            permissions=request.permissions,
            preset=request.preset,
        )
        return membership_to_response(membership)
    except CaseNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - collaborators.invite permission required",
        )
    except UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this case",
        )
    except CannotModifyOwner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify case owner's permissions",
        )


@router.get("/me", response_model=MemberResponse)
def get_my_membership(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Get the current user's membership/permissions for a case.

    Returns the membership record with permissions for the requesting user.
    """
    from services.case_service import get_membership, get_preset_from_membership, is_super_admin
    from postgres.permissions import OWNER_PERMISSIONS, clone_permissions

    try:
        # Check if case exists
        from postgres.models.case import Case
        case = db.query(Case).filter(Case.id == case_id).first()
        if not case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )

        # Super admins get synthetic owner membership
        if is_super_admin(current_user):
            # Return a synthetic membership with full permissions
            return MemberResponse(
                case_id=case_id,
                user_id=current_user.id,
                membership_role=CaseMembershipRole.owner,
                permissions=clone_permissions(OWNER_PERMISSIONS),
                added_by_user_id=current_user.id,
                created_at=case.created_at,
                updated_at=case.updated_at,
                user=MemberUserResponse(
                    id=current_user.id,
                    email=current_user.email,
                    name=current_user.name,
                ),
            )

        # Get the actual membership
        membership = get_membership(db, case_id, current_user.id)
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="You are not a member of this case",
            )

        return membership_to_response(membership)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    case_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Remove a member from a case.

    Requires collaborators.remove permission. Cannot remove the case owner.
    """
    try:
        remove_case_member(
            db=db,
            case_id=case_id,
            actor=current_user,
            target_user_id=user_id,
        )
    except CaseNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - collaborators.remove permission required",
        )
    except UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of this case",
        )
    except CannotModifyOwner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove case owner",
        )
