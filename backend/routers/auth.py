"""
Authentication router

Provides login/logout and current-user endpoints backed by JWT.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from postgres.session import get_db
from services.auth_service import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str  # Actually email, kept as 'username' for frontend compatibility
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str  # Actually email, kept as 'username' for frontend compatibility
    name: str


class MeResponse(BaseModel):
    email: str
    name: str
    username: str  # Backwards compatibility (same as email)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    if request:
        return request.cookies.get("access_token")
    return None


def get_current_user(
    token: str = Depends(_extract_token),
) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        data = auth_service["verify_access_token"](token)
        return data
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)) from err


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Login endpoint - authenticates user and returns JWT token."""
    try:
        # username field is actually the email
        user = auth_service["authenticate_from_db"](db, request.username, request.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Use email as the subject in the token
        token = auth_service["create_access_token"]({"sub": user.email})
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            samesite="lax",
        )

        return TokenResponse(access_token=token, username=user.email, name=user.name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login error: {str(e)}"
        )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    from postgres.models.user import User

    email = user["username"]
    db_user = db.query(User).filter(User.email == email).first()

    if not db_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return MeResponse(email=db_user.email, name=db_user.name, username=db_user.email)


