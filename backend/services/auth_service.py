"""
Authentication service for the Investigation Console.

Provides JWT generation and verification plus credential validation.
"""

import os
from datetime import datetime, timedelta

from jose import JWTError, jwt

from config import AUTH_USERNAME, AUTH_PASSWORD, AUTH_SECRET_KEY, AUTH_ALGORITHM, AUTH_TOKEN_EXPIRE_MINUTES

ACCESS_TOKEN_EXPIRE_MINUTES = AUTH_TOKEN_EXPIRE_MINUTES


def authenticate(username: str, password: str) -> bool:
    """Validate provided credentials."""
    return username == AUTH_USERNAME and password == AUTH_PASSWORD


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def verify_access_token(token: str) -> dict:
    """Verify the provided JWT token and return the payload."""
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise JWTError("Missing subject in token")
        return {"username": username}
    except JWTError as exc:
        raise exc


# Singleton helpers
auth_service = {
    "authenticate": authenticate,
    "create_access_token": create_access_token,
    "verify_access_token": verify_access_token,
}

