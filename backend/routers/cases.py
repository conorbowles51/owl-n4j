"""
Cases Router - PostgreSQL-backed implementation.

Handles CRUD operations for investigation cases with permission-based access control.
"""

from __future__ import annotations

from datetime import date, datetime
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
    check_case_access,
    create_case,
    delete_case,
    list_cases_for_user,
    update_case,
    get_case_if_allowed,
    get_user_role_for_case,
    is_super_admin,
)
from services.deadline_service import get_next_deadline_for_cases
from services.evidence_db_storage import EvidenceDBStorage
from services.processing_profile_service import (
    get_case_processing_config,
    get_processing_profile,
    normalize_instruction_list,
    normalize_special_entity_types,
    upsert_case_processing_config,
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
    # Deadline enrichment
    next_deadline_date: date | None = None
    next_deadline_name: str | None = None

    class Config:
        from_attributes = True


class CaseListResponse(BaseModel):
    """Response model for listing cases."""

    cases: list[CaseResponse]
    total: int


class SpecialEntityType(BaseModel):
    name: str
    description: str | None = None


class CaseProcessingProfileResponse(BaseModel):
    source_profile_name: str | None = None
    source_profile_exists: bool = False
    context_instructions: str | None = None
    mandatory_instructions: list[str] = []
    special_entity_types: list[SpecialEntityType] = []


class CaseProcessingProfileUpdateRequest(BaseModel):
    source_profile_name: str | None = None
    context_instructions: str | None = None
    mandatory_instructions: list[str] = []
    special_entity_types: list[SpecialEntityType] = []


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

    # Batch-fetch next deadlines for all cases
    case_ids = [case.id for case, _, _ in case_tuples]
    next_deadlines = get_next_deadline_for_cases(db, case_ids)

    # Build enriched response
    enriched_cases = []
    for case, membership, owner in case_tuples:
        user_role = get_user_role_for_case(membership, user_is_super_admin)
        is_actual_owner = (
            membership is not None
            and membership.membership_role.value == "owner"
        )

        deadline_info = next_deadlines.get(case.id)
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
            next_deadline_date=deadline_info[0] if deadline_info else None,
            next_deadline_name=deadline_info[1] if deadline_info else None,
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


@router.get("/{case_id}/processing-profile", response_model=CaseProcessingProfileResponse)
def get_case_processing_profile(
    case_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        get_case_if_allowed(db=db, case_id=case_id, user=current_user)
    except CaseNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    config = get_case_processing_config(db, case_id)
    if config is None:
        return CaseProcessingProfileResponse()

    source_profile_exists = False
    if config.source_profile_name_snapshot:
        source_profile_exists = (
            get_processing_profile(db, config.source_profile_name_snapshot) is not None
        )

    return CaseProcessingProfileResponse(
        source_profile_name=config.source_profile_name_snapshot,
        source_profile_exists=source_profile_exists,
        context_instructions=config.context_instructions,
        mandatory_instructions=normalize_instruction_list(config.mandatory_instructions),
        special_entity_types=normalize_special_entity_types(config.special_entity_types),
    )


@router.put("/{case_id}/processing-profile", response_model=CaseProcessingProfileResponse)
def update_case_processing_profile(
    case_id: UUID,
    request: CaseProcessingProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        check_case_access(db, case_id, current_user, required_permission=("case", "edit"))
    except CaseNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied - case.edit permission required",
        )

    try:
        config = upsert_case_processing_config(
            db,
            case_id=case_id,
            source_profile_name=request.source_profile_name,
            context_instructions=request.context_instructions,
            mandatory_instructions=request.mandatory_instructions,
            special_entity_types=[item.model_dump() for item in request.special_entity_types],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    EvidenceDBStorage.mark_case_files_stale(db, case_id)
    db.commit()
    db.refresh(config)

    return CaseProcessingProfileResponse(
        source_profile_name=config.source_profile_name_snapshot,
        source_profile_exists=bool(config.source_profile_name_snapshot),
        context_instructions=config.context_instructions,
        mandatory_instructions=normalize_instruction_list(config.mandatory_instructions),
        special_entity_types=normalize_special_entity_types(config.special_entity_types),
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
