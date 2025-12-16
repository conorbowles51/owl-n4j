"""
Authentication router

Provides login/logout and current-user endpoints backed by JWT.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from services.auth_service import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


def _extract_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None,
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
def login(request: LoginRequest, response: Response):
    if not auth_service["authenticate"](request.username, request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = auth_service["create_access_token"]({"sub": request.username})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
    )

    return TokenResponse(access_token=token, username=request.username)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"username": user["username"]}

