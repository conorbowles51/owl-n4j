"""
User management router.

Provides CRUD operations for user accounts with role-based authorization.
"""

from datetime import datetime
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from postgres.models.enums import GlobalRole
from postgres.models.user import User
from postgres.session import get_db
from routers.auth import get_current_user

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

    return user


def require_admin(current_user: User = Depends(get_current_db_user)) -> User:
    """Dependency that requires the current user to be admin or super_admin."""
    if current_user.global_role not in (GlobalRole.admin, GlobalRole.super_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
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
    # - Admins can only create users with 'user' role
    # - Super admins can create any role
    if current_user.global_role == GlobalRole.admin:
        if requested_role != GlobalRole.user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins can only create users with 'user' role",
            )

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
):
    """List all users."""
    query = db.query(User)

    if not include_inactive:
        query = query.filter(User.is_active == True)

    users = query.order_by(User.created_at.desc()).all()
    total = len(users)

    return UserListResponse(users=users, total=total)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
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

    # Apply updates
    if user_data.name is not None:
        target_user.name = user_data.name
    if user_data.is_active is not None:
        target_user.is_active = user_data.is_active
    if user_data.role is not None:
        target_user.global_role = user_data.role
    if user_data.password is not None:
        target_user.password_hash = hash_password(user_data.password)

    db.commit()
    db.refresh(target_user)

    return target_user
