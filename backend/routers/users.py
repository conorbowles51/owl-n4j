"""
User management router.

Provides CRUD operations for user accounts with role-based authorization.
"""

from datetime import datetime
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.enums import GlobalRole
from postgres.models.user import User
from postgres.session import get_db
from routers.auth import get_current_user
from services import account_recovery, activity_trail, password_rule, password_sessions, two_step

router = APIRouter(prefix="/api/users", tags=["users"])


# --- Pydantic Schemas ---

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: GlobalRole | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    role: GlobalRole | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    global_role: GlobalRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


# --- Helper Functions ---

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def get_current_db_user(
    token_data: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Fetch the full User record from the database based on JWT token."""
    username = token_data.get("username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = db.query(User).filter(User.email == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    if two_step.must_enrol(db, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=two_step.MUST_ENROL)

    return user


def require_admin(current_user: User = Depends(get_current_db_user)) -> User:
    """Dependency that requires the current user to be admin or super_admin."""
    if current_user.global_role not in (GlobalRole.admin, GlobalRole.super_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


def require_super_admin(current_user: User = Depends(get_current_db_user)) -> User:
    """Dependency for billing-sensitive, deployment-wide secret management."""
    if current_user.global_role != GlobalRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super administrator privileges required",
        )
    return current_user


# --- Routes ---

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new user. Requires admin or super_admin role."""
    # Check for duplicate email
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Determine the role to assign
    requested_role = user_data.role or GlobalRole.user

    # Enforce role creation rules:
    # - Admins can only create users with 'user' or 'guest' role
    # - Super admins can create any role
    if current_user.global_role == GlobalRole.admin:
        if requested_role not in (GlobalRole.user, GlobalRole.guest):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins can only create users with 'user' or 'guest' role",
            )

    password_rule.require_acceptable(user_data.password, email=user_data.email, name=user_data.name)

    new_user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=hash_password(user_data.password),
        global_role=requested_role,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.get("", response_model=UserListResponse)
def list_users(
    include_inactive: bool = Query(False, description="Include inactive users"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """List all users. Requires admin or super_admin role."""
    query = db.query(User)

    if not include_inactive:
        query = query.filter(User.is_active == True)

    users = query.order_by(User.created_at.desc()).all()
    total = len(users)

    return UserListResponse(users=users, total=total)


@router.get("/two-step")
def two_step_overview(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Who has enrolled, and how many recovery codes each has left. One read of each table, whatever the user count."""
    from postgres.models.two_step import UserRecoveryCode, UserTwoStep

    enrolled = dict(db.execute(select(UserTwoStep.user_id, UserTwoStep.confirmed_at)
                               .where(UserTwoStep.confirmed_at.is_not(None))).all())
    left = dict(db.execute(select(UserRecoveryCode.user_id, func.count(UserRecoveryCode.id))
                           .where(UserRecoveryCode.used_at.is_(None)).group_by(UserRecoveryCode.user_id)).all())
    return {
        "required_for_admins": two_step.required_for_admins(),
        "people": [{"user_id": str(user_id), "enrolled_at": confirmed.isoformat(),
                    "recovery_codes_left": left.get(user_id, 0)} for user_id, confirmed in enrolled.items()],
    }


def _recoverable(db: Session, user_id: UUID, current_user: User) -> User:
    """The person an administrator may recover. Never themselves: a stolen sign-in must not be able to replace its
    own password without the current one. An administrator nobody else can reach has the box command."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You cannot recover your own account here. Use change password, or the box command.")
    if current_user.global_role != GlobalRole.super_admin and target.global_role in two_step.ADMIN_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only a super admin can recover an administrator's account.")
    if not target.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account is deactivated.")
    return target


@router.post("/{user_id}/reset-code")
def issue_reset_code(user_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """A one-time, expiring code for this person to set a new password. It is shown here once and held only as a hash."""
    target = _recoverable(db, user_id, current_user)
    code, expires = account_recovery.issue_reset_code(db, target, current_user.email)
    activity_trail.record("reset_code_issued", db=db, user=current_user,
                          details=dict(person=target.email, expires_at=expires.isoformat()))
    db.commit()
    return JSONResponse({"code": code, "expires_at": expires.isoformat()}, headers={"Cache-Control": "no-store"})


@router.post("/{user_id}/two-step/remove")
def remove_two_step(user_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """For a person who lost their device and their recovery codes. They sign in with the password alone until they
    enrol again."""
    target = _recoverable(db, user_id, current_user)
    two_step.remove(db, target.id)
    activity_trail.record("two_step_removed", db=db, user=current_user, details=dict(person=target.email))
    db.commit()
    return {"success": True}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get a single user by ID. Requires admin or super_admin role."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update a user. Requires admin or super_admin role."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Admins cannot modify super_admin users
    if (
        current_user.global_role == GlobalRole.admin
        and target_user.global_role == GlobalRole.super_admin
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot modify super_admin users",
        )

    # Prevent self-deactivation
    if user_data.is_active is False and target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account",
        )

    # Only super_admins can change admin-level roles
    if user_data.role is not None:
        is_admin_level_change = (
            user_data.role in (GlobalRole.admin, GlobalRole.super_admin)
            or target_user.global_role in (GlobalRole.admin, GlobalRole.super_admin)
        )
        if is_admin_level_change and current_user.global_role != GlobalRole.super_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super_admins can change admin-level roles",
            )

    # Protect last super_admin from demotion/deactivation
    if target_user.global_role == GlobalRole.super_admin:
        will_demote = user_data.role is not None and user_data.role != GlobalRole.super_admin
        will_deactivate = user_data.is_active is False

        if will_demote or will_deactivate:
            super_admin_count = db.query(func.count(User.id)).filter(
                User.global_role == GlobalRole.super_admin,
                User.is_active == True,
            ).scalar()

            if super_admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote or deactivate the last super_admin",
                )

    if user_data.password is not None:
        # The same rules as a reset code. No screen sets a password here; it stays for an administrator's script.
        if target_user.id == current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Change your own password in Settings, Security: it needs the current one.")
        if current_user.global_role != GlobalRole.super_admin and target_user.global_role in two_step.ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Only a super admin can set an administrator's password.")
        password_rule.require_acceptable(user_data.password, email=target_user.email,
                                         name=user_data.name or target_user.name)

    # Apply updates
    if user_data.name is not None:
        target_user.name = user_data.name
    if user_data.is_active is not None:
        target_user.is_active = user_data.is_active
    if user_data.role is not None:
        target_user.global_role = user_data.role
    if user_data.password is not None:
        target_user.password_hash = hash_password(user_data.password)
        # The user's existing sign-ins end (password_sessions).
        password_sessions.stamp(target_user)
        activity_trail.record("password_set_by_admin", db=db, user=current_user, details=dict(person=target_user.email))

    db.commit()
    if user_data.password is not None:
        password_sessions.forget(target_user.email)
    db.refresh(target_user)

    return target_user
