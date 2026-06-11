"""
Testing-hub authentication — a small, self-contained login scoped ONLY to the
QA testing hub.

Deliberately separate from the main app's user accounts: these three testers
(neil / alex / conor) get hub-only access so it's clear who wrote each note,
and the hub isn't public — but logging in here grants NO access to the rest of
the application (the token carries a `hub: "testing"` claim and the app's
auth dependencies don't accept it).

Passwords are bcrypt-hashed at import (never stored in plaintext). Tokens are
signed with the app's existing JWT secret/algorithm via python-jose, so we
reuse proven crypto rather than rolling our own.
"""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from config import AUTH_SECRET_KEY, AUTH_ALGORITHM

# The testers. Same shared password ("testing") per the brief — but each logs in
# under their own username so authorship of every note is attributable.
_TESTERS = {
    "neil": "Neil",
    "alex": "Alex",
    "conor": "Conor",
    "arturo": "Arturo",
}
_PASSWORD = "testing"

# Per-tester email, used by Docket's notifier (Needs Info / PR ready / User
# Review / Stalled). An empty string just means "no email channel for this
# person yet" (in-app badge still fires).
_EMAILS = {
    "neil": "neil.byrne@gmail.com",
    "alex": "asolorzano@owlconsultancygroup.com",
    "conor": "conorbowles51@gmail.com",
    "arturo": "",
}

# Hash the password per-user at import so no plaintext sits in memory longer
# than needed and the stored secret is a bcrypt digest.
_HASHES = {
    username: bcrypt.hashpw(_PASSWORD.encode("utf-8"), bcrypt.gensalt())
    for username in _TESTERS
}

# Token lifetime — generous so a tester isn't kicked out mid-session.
_TOKEN_TTL = timedelta(days=7)
_HUB_CLAIM = "testing"


def authenticate(username: str, password: str) -> Optional[str]:
    """Return the tester's display name on success, else None."""
    if not username or not password:
        return None
    uname = username.strip().lower()
    h = _HASHES.get(uname)
    if not h:
        return None
    try:
        if bcrypt.checkpw(password.encode("utf-8"), h):
            return _TESTERS[uname]
    except (ValueError, TypeError):
        return None
    return None


def make_token(username: str) -> str:
    """Issue a hub-scoped JWT for the given (already-authenticated) username."""
    uname = username.strip().lower()
    payload = {
        "sub": uname,
        "name": _TESTERS.get(uname, uname),
        "hub": _HUB_CLAIM,
        "exp": datetime.utcnow() + _TOKEN_TTL,
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify a hub token. Returns {username, name} or None.

    Rejects tokens that aren't hub-scoped (so a stray main-app token can't be
    used here, and vice-versa).
    """
    if not token:
        return None
    try:
        data = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
    except JWTError:
        return None
    if data.get("hub") != _HUB_CLAIM:
        return None
    uname = data.get("sub")
    if uname not in _TESTERS:
        return None
    return {"username": uname, "name": data.get("name") or _TESTERS[uname]}


def verify_username(username: str) -> bool:
    """True if this is a known tester username."""
    return (username or "").strip().lower() in _TESTERS


def tester_email(username: str) -> str:
    """Email for a tester username, or '' if none on file."""
    return _EMAILS.get((username or "").strip().lower(), "")


def all_testers() -> list:
    """[{username, name, email}] for every tester — used by Docket assignee pickers."""
    return [
        {"username": u, "name": n, "email": _EMAILS.get(u, "")}
        for u, n in _TESTERS.items()
    ]
