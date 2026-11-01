"""
Authentication service for the Investigation Console.

Provides JWT generation and verification plus credential validation.
"""

import os
from datetime import datetime, timedelta

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import AUTH_SECRET_KEY, AUTH_ALGORITHM, AUTH_TOKEN_EXPIRE_MINUTES

ACCESS_TOKEN_EXPIRE_MINUTES = AUTH_TOKEN_EXPIRE_MINUTES


def authenticate_from_db(db: Session, email: str, password: str):
    """
    Authenticate a user against the database.

    Returns the User object if credentials are valid, None otherwise.
    """
    from postgres.models.user import User
    from routers.users import verify_password

    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None

    if not verify_password(password, user.password_hash):
        return None

    if not user.is_active:
        return None

    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    # When it was issued: a token from before its user's last password change is refused (password_sessions).
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def verify_access_token(token: str) -> dict:
    """Verify the provided JWT token and return the payload."""
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise JWTError("Missing subject in token")
        issued = payload.get("iat")
        if issued is None and payload.get("exp") is not None:
            # Issued before tokens carried iat: only sign-in issues tokens, with the default lifetime.
            issued = int(payload["exp"]) - ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return {"username": username, "issued_at": int(issued) if issued is not None else None}
    except JWTError as exc:
        raise exc


# Singleton helpers
auth_service = {
    "authenticate_from_db": authenticate_from_db,
    "create_access_token": create_access_token,
    "verify_access_token": verify_access_token,
}

