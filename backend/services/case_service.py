"""
Case service with centralized permission logic.

Provides CRUD operations for cases and member management with permission checks.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.user import User
from postgres.permissions import (
    OWNER_PERMISSIONS,
    EDITOR_PERMISSIONS,
    VIEWER_PERMISSIONS,
    clone_permissions,
)


# --- Custom Exceptions ---


class CaseNotFound(Exception):
    """Raised when a case is not found."""

    pass


class CaseAccessDenied(Exception):
    """Raised when a user does not have permission to access a case."""

    pass


class UserNotFound(Exception):
    """Raised when a user is not found."""

    pass


class AlreadyMember(Exception):
    """Raised when trying to add a user who is already a member."""

    pass


class CannotModifyOwner(Exception):
    """Raised when trying to modify or remove the case owner."""

    pass


# --- Permission Functions ---


def is_super_admin(user: User) -> bool:
    """Check if a user is a super admin."""
    return user.global_role == GlobalRole.super_admin


def get_membership(db: Session, case_id: UUID, user_id: UUID) -> CaseMembership | None:
    """Get the membership record for a user in a case."""
    return (
        db.query(CaseMembership)
        .filter(CaseMembership.case_id == case_id, CaseMembership.user_id == user_id)
        .first()
    )


def has_permission(membership: CaseMembership | None, category: str, action: str) -> bool:
    """
    Check if a membership has a specific permission.

    Args:
        membership: The case membership record (can be None)
        category: Permission category (e.g., 'case', 'collaborators', 'evidence')
        action: Permission action (e.g., 'view', 'edit', 'delete', 'invite', 'remove')

    Returns:
        True if the permission is granted, False otherwise.
    """
    if membership is None:
        return False

    permissions = membership.permissions or {}
    category_perms = permissions.get(category, {})
    return category_perms.get(action, False)


def check_case_access(
    db: Session,
    case_id: UUID,
    user: User,
    required_permission: tuple[str, str] | None = None,
) -> tuple[Case, CaseMembership | None]:
    """
    Check if a user has access to a case.

    Args:
        db: Database session
        case_id: The case ID
        user: The user attempting access
        required_permission: Optional (category, action) tuple for specific permission check

    Returns:
        Tuple of (Case, CaseMembership or None)

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the user doesn't have the required permission
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise CaseNotFound(f"Case {case_id} not found")

    # Super admins have full access
    if is_super_admin(user):
        # Return a synthetic "owner-like" membership for super admins
        membership = get_membership(db, case_id, user.id)
        return case, membership

    # Get user's membership
    membership = get_membership(db, case_id, user.id)

    # If specific permission required, check it
    if required_permission:
        category, action = required_permission
        if not has_permission(membership, category, action):
            raise CaseAccessDenied(
                f"User does not have {category}.{action} permission for case {case_id}"
            )

    # If no specific permission required, just need membership
    elif membership is None:
        raise CaseAccessDenied(f"User is not a member of case {case_id}")

    return case, membership


def get_case_if_allowed(db: Session, case_id: UUID, user: User) -> Case:
    """
    Get a case if the user has view permission.

    Args:
        db: Database session
        case_id: The case ID
        user: The user attempting access

    Returns:
        The Case object

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the user doesn't have view permission
    """
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "view"))
    return case


# --- Case CRUD Operations ---


def create_case(
    db: Session,
    creator: User,
    title: str,
    description: str | None = None,
) -> Case:
    """
    Create a new case and add the creator as owner.

    Args:
        db: Database session
        creator: The user creating the case
        title: Case title
        description: Optional case description

    Returns:
        The created Case object
    """
    # Create the case
    case = Case(
        title=title,
        description=description,
        created_by_user_id=creator.id,
        owner_user_id=creator.id,
    )
    db.add(case)
    db.flush()  # Get the case ID

    # Create owner membership
    membership = CaseMembership(
        case_id=case.id,
        user_id=creator.id,
        membership_role=CaseMembershipRole.owner,
        permissions=clone_permissions(OWNER_PERMISSIONS),
        added_by_user_id=creator.id,
    )
    db.add(membership)
    db.commit()
    db.refresh(case)

    return case


def get_user_role_for_case(
    membership: CaseMembership | None, is_super_admin_user: bool
) -> str:
    """
    Determine the user's role string for display purposes.

    Args:
        membership: The case membership record (can be None)
        is_super_admin_user: Whether the user is a super admin

    Returns:
        'owner', 'editor', 'viewer', or 'admin_access'
    """
    if membership is None:
        if is_super_admin_user:
            return "admin_access"
        return "none"

    if membership.membership_role == CaseMembershipRole.owner:
        return "owner"

    # Check permissions to determine editor vs viewer
    permissions = membership.permissions or {}
    if permissions.get("evidence", {}).get("upload", False):
        return "editor"

    return "viewer"


def list_cases_for_user(
    db: Session, user: User, include_all: bool = False
) -> list[tuple[Case, CaseMembership | None, User | None]]:
    """
    List all cases a user has access to with enriched data.

    Args:
        db: Database session
        user: The user requesting the list
        include_all: If True and user is super admin, return all cases.
                    If False, only return cases user is a member of.

    Returns:
        List of tuples (Case, CaseMembership or None, Owner User or None)
    """
    user_is_super_admin = is_super_admin(user)

    if user_is_super_admin and include_all:
        # Super admin viewing all cases - get all cases with owner info
        cases = db.query(Case).order_by(Case.updated_at.desc()).all()
        result = []
        for case in cases:
            # Get user's membership (if any)
            membership = get_membership(db, case.id, user.id)
            # Get case owner
            owner = db.query(User).filter(User.id == case.owner_user_id).first()
            result.append((case, membership, owner))
        return result

    # For regular users OR super admins with include_all=False:
    # Only show cases where user is a member
    memberships = (
        db.query(CaseMembership)
        .filter(CaseMembership.user_id == user.id)
        .all()
    )

    case_ids = [m.case_id for m in memberships]
    if not case_ids:
        return []

    cases = (
        db.query(Case)
        .filter(Case.id.in_(case_ids))
        .order_by(Case.updated_at.desc())
        .all()
    )

    # Build lookup for memberships
    membership_by_case = {m.case_id: m for m in memberships}

    result = []
    for case in cases:
        membership = membership_by_case.get(case.id)
        # Get case owner
        owner = db.query(User).filter(User.id == case.owner_user_id).first()
        result.append((case, membership, owner))

    return result


def update_case(
    db: Session,
    case_id: UUID,
    user: User,
    title: str | None = None,
    description: str | None = None,
) -> Case:
    """
    Update a case's title and/or description.

    Args:
        db: Database session
        case_id: The case ID
        user: The user performing the update
        title: New title (optional)
        description: New description (optional)

    Returns:
        The updated Case object

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the user doesn't have edit permission
    """
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "edit"))

    if title is not None:
        case.title = title
    if description is not None:
        case.description = description

    db.commit()
    db.refresh(case)

    return case


def delete_case(db: Session, case_id: UUID, user: User) -> None:
    """
    Delete a case and all associated memberships.

    Args:
        db: Database session
        case_id: The case ID
        user: The user performing the deletion

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the user doesn't have delete permission
    """
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "delete"))

    # Memberships will be cascade deleted due to FK constraint
    db.delete(case)
    db.commit()


# --- Member Management ---


def get_permissions_for_preset(preset: str) -> dict:
    """
    Get permissions dict for a preset name.

    Args:
        preset: One of 'viewer', 'editor', or 'owner'

    Returns:
        Cloned permissions dict
    """
    presets = {
        "viewer": VIEWER_PERMISSIONS,
        "editor": EDITOR_PERMISSIONS,
        "owner": OWNER_PERMISSIONS,
    }
    template = presets.get(preset, VIEWER_PERMISSIONS)
    return clone_permissions(template)


def get_preset_from_membership(membership: CaseMembership) -> str:
    """
    Derive UI preset from membership role and permissions.

    Args:
        membership: The case membership record

    Returns:
        'owner', 'editor', or 'viewer'
    """
    if membership.membership_role == CaseMembershipRole.owner:
        return "owner"

    permissions = membership.permissions or {}
    if permissions.get("evidence", {}).get("upload", False):
        return "editor"

    return "viewer"


def add_case_member(
    db: Session,
    case_id: UUID,
    actor: User,
    target_user_id: UUID,
    permissions: dict | None = None,
    preset: str | None = None,
    role: CaseMembershipRole = CaseMembershipRole.collaborator,
) -> CaseMembership:
    """
    Add a new member to a case.

    Args:
        db: Database session
        case_id: The case ID
        actor: The user performing the action
        target_user_id: The user to add
        permissions: Custom permissions dict (optional)
        preset: Permission preset ('viewer', 'editor') - used if permissions not provided
        role: The membership role (default: collaborator)

    Returns:
        The created CaseMembership object

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the actor doesn't have invite permission
        UserNotFound: If the target user doesn't exist
        AlreadyMember: If the target user is already a member
    """
    # Check actor has invite permission
    case, _ = check_case_access(
        db, case_id, actor, required_permission=("collaborators", "invite")
    )

    # Check target user exists
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise UserNotFound(f"User {target_user_id} not found")

    # Check not already a member
    existing = get_membership(db, case_id, target_user_id)
    if existing:
        raise AlreadyMember(f"User {target_user_id} is already a member of case {case_id}")

    # Determine permissions
    if permissions is None:
        permissions = get_permissions_for_preset(preset or "viewer")

    membership = CaseMembership(
        case_id=case_id,
        user_id=target_user_id,
        membership_role=role,
        permissions=permissions,
        added_by_user_id=actor.id,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return membership


def list_case_members(db: Session, case_id: UUID, user: User) -> list[CaseMembership]:
    """
    List all members of a case.

    Args:
        db: Database session
        case_id: The case ID
        user: The user requesting the list

    Returns:
        List of CaseMembership objects

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the user doesn't have view permission
    """
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "view"))

    return (
        db.query(CaseMembership)
        .filter(CaseMembership.case_id == case_id)
        .all()
    )


def update_member_permissions(
    db: Session,
    case_id: UUID,
    actor: User,
    target_user_id: UUID,
    permissions: dict | None = None,
    preset: str | None = None,
) -> CaseMembership:
    """
    Update a member's permissions.

    Args:
        db: Database session
        case_id: The case ID
        actor: The user performing the update
        target_user_id: The user whose permissions to update
        permissions: New permissions dict (optional)
        preset: Permission preset ('viewer', 'editor') - used if permissions not provided

    Returns:
        The updated CaseMembership object

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the actor doesn't have invite permission
        UserNotFound: If the target user is not a member
        CannotModifyOwner: If trying to modify the owner's permissions
    """
    case, _ = check_case_access(
        db, case_id, actor, required_permission=("collaborators", "invite")
    )

    # Get the membership
    membership = get_membership(db, case_id, target_user_id)
    if not membership:
        raise UserNotFound(f"User {target_user_id} is not a member of case {case_id}")

    # Cannot modify owner's permissions
    if membership.membership_role == CaseMembershipRole.owner:
        raise CannotModifyOwner("Cannot modify case owner's permissions")

    # Determine new permissions
    if permissions is not None:
        membership.permissions = permissions
    elif preset is not None:
        membership.permissions = get_permissions_for_preset(preset)

    db.commit()
    db.refresh(membership)

    return membership


def remove_case_member(
    db: Session,
    case_id: UUID,
    actor: User,
    target_user_id: UUID,
) -> None:
    """
    Remove a member from a case.

    Args:
        db: Database session
        case_id: The case ID
        actor: The user performing the removal
        target_user_id: The user to remove

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the actor doesn't have remove permission
        UserNotFound: If the target user is not a member
        CannotModifyOwner: If trying to remove the owner
    """
    case, _ = check_case_access(
        db, case_id, actor, required_permission=("collaborators", "remove")
    )

    # Get the membership
    membership = get_membership(db, case_id, target_user_id)
    if not membership:
        raise UserNotFound(f"User {target_user_id} is not a member of case {case_id}")

    # Cannot remove owner
    if membership.membership_role == CaseMembershipRole.owner:
        raise CannotModifyOwner("Cannot remove case owner")

    db.delete(membership)
    db.commit()
