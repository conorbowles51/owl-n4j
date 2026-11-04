"""
Case service with centralized permission logic.

Provides CRUD operations for cases and member management with permission checks.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, CaseStatus, GlobalRole
from postgres.models.user import User
from postgres.permissions import (
    OWNER_PERMISSIONS,
    EDITOR_PERMISSIONS,
    VIEWER_PERMISSIONS,
    clone_permissions,
)
from services.system_log_service import LogOrigin, LogType, system_log_service


_UNSET = object()


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
    title: str | object = _UNSET,
    description: str | None | object = _UNSET,
    status: CaseStatus | str | object = _UNSET,
) -> Case:
    """
    Update a case's metadata and write its audit record in the same transaction.

    Args:
        db: Database session
        case_id: The case ID
        user: The user performing the update
        title: New title (optional)
        description: New description, including ``None`` to clear it (optional)
        status: New case workflow status (optional)

    Returns:
        The updated Case object

    Raises:
        CaseNotFound: If the case doesn't exist
        CaseAccessDenied: If the user doesn't have edit permission
    """
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "edit"))

    changes: dict[str, dict[str, str | None]] = {}

    if title is not _UNSET and title != case.title:
        changes["title"] = {"from": case.title, "to": title}
        case.title = title
    if description is not _UNSET and description != case.description:
        changes["description"] = {"from": case.description, "to": description}
        case.description = description

    if status is not _UNSET:
        status_value = status.value if isinstance(status, CaseStatus) else status
        if status_value != case.status:
            changes["status"] = {"from": case.status, "to": status_value}
            case.status = status_value

    if not changes:
        return case

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.BACKEND,
        action="Update Case Metadata",
        details={"case_id": str(case_id), "changes": changes},
        user=user.email,
        success=True,
        db=db,
    )

    db.commit()
    db.refresh(case)

    return case


# A deleted case waits this long in Deleted items before it is purged (lx-casebin decision 1).
DELETED_RETENTION_DAYS = 30


class CaseNotDeleted(Exception):
    """Raised when restoring a case that is not in Deleted items."""


def delete_case(db: Session, case_id: UUID, user: User) -> None:
    """
    Move a case to Deleted items. Nothing is removed: the case and everything in it are hidden from every screen,
    search, agent, export and background job (postgres/soft_delete.py) until the owner or an admin restores it,
    or until it is purged DELETED_RETENTION_DAYS later (purge_case, the delete used before).

    Raises:
        CaseNotFound: If the case doesn't exist (or is already deleted)
        CaseAccessDenied: If the user doesn't have delete permission
    """
    from datetime import datetime, timezone
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "delete"))
    now = datetime.now(timezone.utc)
    details = dict(case_title=case.title,
                   case_created_at=case.created_at.isoformat() if case.created_at else None,
                   owner_user_id=str(case.owner_user_id) if case.owner_user_id else None,
                   records_held=_case_record_counts(db, case_id),
                   purge_after=_purge_after(now).isoformat())
    case.deleted_at = now
    case.deleted_by_user_id = user.id
    # The audit row goes in the same transaction: it commits only if the case is really moved to Deleted items.
    from services import activity_trail
    activity_trail.record("case_deleted", db=db, user=user, case_id=case_id, details=details)
    db.commit()
    from postgres import soft_delete
    soft_delete.forget()


def _purge_after(deleted_at):
    from datetime import timedelta
    return deleted_at + timedelta(days=DELETED_RETENTION_DAYS)


def can_restore_case(case: Case, user: User) -> bool:
    """The case owner or an admin restores a deleted case (decision 1)."""
    return is_super_admin(user) or case.owner_user_id == user.id


def _deleted_case(db: Session, case_id: UUID) -> Case:
    from postgres.soft_delete import showing_deleted
    with showing_deleted(db):
        case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise CaseNotFound(f"Case {case_id} not found")
    if case.deleted_at is None:
        raise CaseNotDeleted(f"Case {case_id} is not deleted")
    return case


def list_deleted_cases(db: Session, user: User) -> list[dict]:
    """The deleted cases this user may restore, newest first, with who deleted them, when, what they hold and the
    days left before the purge."""
    from datetime import datetime, timezone
    from postgres.soft_delete import showing_deleted
    with showing_deleted(db):
        query = db.query(Case).filter(Case.deleted_at.is_not(None))
        if not is_super_admin(user):
            query = query.filter(Case.owner_user_id == user.id)
        cases = query.order_by(Case.deleted_at.desc()).all()
        people = {u.id: u for u in db.query(User).filter(User.id.in_(
            {c.deleted_by_user_id for c in cases if c.deleted_by_user_id} | {c.owner_user_id for c in cases})).all()}
    now = datetime.now(timezone.utc)
    rows = []
    for case in cases:
        purge_at = _purge_after(case.deleted_at)
        deleter = people.get(case.deleted_by_user_id)
        owner = people.get(case.owner_user_id)
        rows.append(dict(
            id=str(case.id), title=case.title,
            deleted_at=case.deleted_at.isoformat(),
            deleted_by=dict(id=str(deleter.id), name=deleter.name, email=deleter.email) if deleter else None,
            owner=dict(id=str(owner.id), name=owner.name, email=owner.email) if owner else None,
            purge_at=purge_at.isoformat(),
            days_left=max(0, (purge_at - now).days),
            holds=_case_record_counts(db, case.id),
        ))
    return rows


def restore_case(db: Session, case_id: UUID, user: User) -> Case:
    """Bring a deleted case back exactly as it was: only the deleted marker is cleared.

    Raises:
        CaseNotFound: no such case (or already purged)
        CaseNotDeleted: the case is not in Deleted items
        CaseAccessDenied: the user is neither the case owner nor an admin
    """
    case = _deleted_case(db, case_id)
    if not can_restore_case(case, user):
        raise CaseAccessDenied("Only the case owner or an admin can restore a deleted case")
    deleted_at, deleted_by = case.deleted_at, case.deleted_by_user_id
    case.deleted_at = None
    case.deleted_by_user_id = None
    from services import activity_trail
    activity_trail.record("case_restored", db=db, user=user, case_id=case_id, details=dict(
        case_title=case.title, deleted_at=deleted_at.isoformat(),
        deleted_by_user_id=str(deleted_by) if deleted_by else None,
        records_held=_case_record_counts(db, case_id)))
    db.commit()
    from postgres import soft_delete
    soft_delete.forget()
    db.refresh(case)
    return case


def purge_case(db: Session, case_id: UUID, *, reason: str = "retention") -> dict:
    """Remove a deleted case for good, with the delete used before Deleted items existed: its ChromaDB chunks and
    entities, then the case row (about 140 tables cascade). Only a case already in Deleted items is purged.
    Returns the audit details."""
    from postgres.soft_delete import showing_deleted
    case = _deleted_case(db, case_id)
    details = dict(case_title=case.title,
                   case_created_at=case.created_at.isoformat() if case.created_at else None,
                   owner_user_id=str(case.owner_user_id) if case.owner_user_id else None,
                   deleted_at=case.deleted_at.isoformat(),
                   deleted_by_user_id=str(case.deleted_by_user_id) if case.deleted_by_user_id else None,
                   reason=reason,
                   records_removed=_case_record_counts(db, case_id))

    # Clean up vector database entries for this case
    try:
        from services.vector_db_service import vector_db_service
        if vector_db_service:
            case_id_str = str(case_id)
            chunks_deleted = vector_db_service.delete_chunks_by_case(case_id_str)
            entities_deleted = vector_db_service.delete_entities_by_case(case_id_str)
            details.update(vector_chunks_removed=chunks_deleted, vector_entities_removed=entities_deleted)
            print(f"[CaseService] Cleaned up ChromaDB for case {case_id_str}: "
                  f"{chunks_deleted} chunks, {entities_deleted} entities")
    except Exception as e:
        details.update(vector_cleanup_error=str(e)[:200])
        print(f"[CaseService] Warning: ChromaDB cleanup failed for case {case_id}: {e}")
        # Don't block the purge if vector cleanup fails

    # The audit row goes in the same transaction as the delete: it commits only if the case is really gone, and
    # activity_events has no foreign key to cases, so the row outlives the case.
    from services import activity_trail
    activity_trail.record("case_purged", db=db, system=True, case_id=case_id, details=details)

    with showing_deleted(db):
        db.delete(case)
        db.commit()
    from postgres import soft_delete
    soft_delete.forget()
    # The case's graph goes only once its rows are gone for good (a failed purge keeps both; a case in Deleted items
    # keeps its graph for a restore). Before, a deleted case's nodes stayed in Neo4j: 7 deleted cases held 1,548
    # nodes on live, 3 Nov (followups m110323033215300).
    graph = remove_case_graph(str(case_id))
    activity_trail.record("case_graph_removed", db=db, commit=True, system=True, case_id=case_id, details=graph)
    details.update(graph)
    return details


def remove_case_graph(case_id: str) -> dict:
    """Delete every node and relationship of the case from the graph. Never raises: returns the counts, or the
    error, for the activity trail."""
    try:
        from services.neo4j import neo4j_service
        out = neo4j_service.delete_case_data(case_id)
        return dict(nodes_removed=out.get("nodes_deleted"), relationships_removed=out.get("relationships_deleted"))
    except Exception as exc:  # noqa: BLE001 - the case is already deleted; the trail says the graph was not
        print(f"[CaseService] Warning: graph cleanup failed for case {case_id}: {exc}")
        return dict(graph_cleanup_error=str(exc)[:200])


# Records a person would miss, counted just before a case is deleted (each table has an index on case_id; all
# ten together took 63 ms on the largest live case, 28,075 transactions). Not every table that cascades: the
# full list is about 140 tables.
CASE_DELETE_COUNTED_TABLES = (
    "case_memberships", "evidence_files", "financial_accounts", "financial_statement_periods",
    "financial_transactions", "adjudications", "financial_judgements", "phone_extractions", "phone_comm_events",
    "workspace_entries",
)


def _case_record_counts(db: Session, case_id: UUID) -> dict:
    from sqlalchemy import func, select
    from postgres.base import Base
    counts = {}
    for name in CASE_DELETE_COUNTED_TABLES:
        table = Base.metadata.tables.get(name)
        if table is None or "case_id" not in table.c:
            continue
        try:
            with db.begin_nested():
                counts[name] = db.scalar(select(func.count()).select_from(table).where(table.c.case_id == case_id))
        except Exception as e:  # a table missing from this database must not block the delete
            counts[name] = f"not counted: {type(e).__name__}"
    return counts


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
