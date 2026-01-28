"""
Setup router for first-time application setup.

Provides endpoints for checking setup status and creating the initial admin user.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from postgres.models.enums import GlobalRole
from postgres.models.user import User
from postgres.session import get_db
from routers.users import hash_password

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatusResponse(BaseModel):
    needs_setup: bool


class InitialUserRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class InitialUserResponse(BaseModel):
    id: str
    email: str
    name: str
    global_role: GlobalRole

    class Config:
        from_attributes = True


@router.get("/status", response_model=SetupStatusResponse)
def get_setup_status(db: Session = Depends(get_db)):
    """
    Check if the application needs initial setup.

    Returns needs_setup=true if no users exist in the database.
    This endpoint is public and requires no authentication.
    """
    user_count = db.query(func.count(User.id)).scalar()
    return SetupStatusResponse(needs_setup=user_count == 0)


@router.post("/initial-user", response_model=InitialUserResponse, status_code=status.HTTP_201_CREATED)
def create_initial_user(
    user_data: InitialUserRequest,
    db: Session = Depends(get_db),
):
    """
    Create the initial super_admin user during first-time setup.

    This endpoint only works when no users exist in the database.
    Returns 403 Forbidden if any users already exist.
    """
    # Security check: only allow if zero users exist
    user_count = db.query(func.count(User.id)).scalar()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed. Initial user can only be created when no users exist.",
        )

    # Check for duplicate email (shouldn't happen if count is 0, but be safe)
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create the super_admin user
    new_user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=hash_password(user_data.password),
        global_role=GlobalRole.super_admin,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return InitialUserResponse(
        id=str(new_user.id),
        email=new_user.email,
        name=new_user.name,
        global_role=new_user.global_role,
    )
