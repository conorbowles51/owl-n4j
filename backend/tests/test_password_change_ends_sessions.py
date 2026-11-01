"""Changing a password ends the user's other sign-ins (found 1 Nov rotating the jobs login: a token taken before
the change stayed valid until it expired)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Response
from jose import jwt

from config import AUTH_ALGORITHM, AUTH_SECRET_KEY
from routers import auth
from services import auth_service as auth_module, password_sessions
from services.auth_service import auth_service


@pytest.fixture(autouse=True)
def stamps(monkeypatch):
    changed = {}
    reads = []
    password_sessions._cache.clear()
    monkeypatch.setattr(password_sessions, "_read_changed_at",
                        lambda email: reads.append(email) or changed.get(email))
    yield SimpleNamespace(changed=changed, reads=reads)
    password_sessions._cache.clear()


def _token(issued: datetime) -> str:
    return jwt.encode({"sub": "a@example.org", "iat": issued, "exp": issued + timedelta(hours=24)},
                      AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def _user(token):
    return asyncio.run(auth.get_current_user(token=token))


def test_a_token_from_before_the_change_is_refused_and_one_from_after_is_accepted(stamps):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamps.changed["a@example.org"] = now.timestamp()
    with pytest.raises(HTTPException) as refused:
        _user(_token(now - timedelta(minutes=5)))
    assert refused.value.status_code == 401
    password_sessions.forget("a@example.org")
    assert _user(_token(now)) == {"username": "a@example.org"}


def test_a_user_who_never_changed_keeps_every_sign_in_and_is_read_once_per_cache_window(stamps):
    token = _token(datetime.now(timezone.utc) - timedelta(hours=3))
    assert _user(token) == {"username": "a@example.org"}
    assert _user(token) == {"username": "a@example.org"}
    assert stamps.reads == ["a@example.org"]


def test_a_token_issued_before_iat_existed_is_dated_from_its_expiry():
    issued = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=2)
    legacy = jwt.encode({"sub": "a@example.org",
                         "exp": issued + timedelta(minutes=auth_module.ACCESS_TOKEN_EXPIRE_MINUTES)},
                        AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)
    assert auth_service["verify_access_token"](legacy)["issued_at"] == int(issued.timestamp())
    fresh = auth_service["create_access_token"]({"sub": "a@example.org"})
    assert abs(auth_service["verify_access_token"](fresh)["issued_at"] - datetime.now(timezone.utc).timestamp()) < 5


def test_changing_the_password_stamps_the_user_and_hands_this_sign_in_a_new_token(stamps, monkeypatch):
    from routers import users
    monkeypatch.setattr(users, "verify_password", lambda plain, hashed: plain == "old-secret")
    monkeypatch.setattr(users, "hash_password", lambda plain: "hashed:" + plain)
    person = SimpleNamespace(email="a@example.org", password_hash="x", password_changed_at=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = person
    before = _token(datetime.now(timezone.utc) - timedelta(minutes=10))
    response = Response()
    out = auth.change_password(auth.ChangePasswordRequest(current_password="old-secret", new_password="new-secret"),
                               response, user={"username": "a@example.org"}, db=db)
    db.commit.assert_called_once()
    assert person.password_hash == "hashed:new-secret"
    assert person.password_changed_at is not None
    stamps.changed["a@example.org"] = person.password_changed_at.timestamp()
    with pytest.raises(HTTPException):
        _user(before)
    assert _user(out["access_token"]) == {"username": "a@example.org"}
    assert "access_token=" in response.headers.get("set-cookie", "")


def test_an_administrator_setting_a_password_ends_that_users_sign_ins(monkeypatch):
    import inspect
    from routers import users
    source = inspect.getsource(users)
    assert "password_sessions.stamp(target_user)" in source


def test_a_database_that_cannot_answer_does_not_fail_the_request(monkeypatch):
    def down(email):
        raise RuntimeError("QueuePool limit reached")
    monkeypatch.setattr(password_sessions, "_read_changed_at", down)
    assert _user(_token(datetime.now(timezone.utc))) == {"username": "a@example.org"}


def test_the_cache_is_forgotten_only_after_the_change_is_committed(stamps, monkeypatch):
    from routers import users
    monkeypatch.setattr(users, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(users, "hash_password", lambda plain: "h")
    person = SimpleNamespace(email="a@example.org", password_hash="x", password_changed_at=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = person
    # A request between the stamp and the commit cached the old (empty) value.
    db.commit.side_effect = lambda: password_sessions._cache.__setitem__("a@example.org", (1e18, None))
    auth.change_password(auth.ChangePasswordRequest(current_password="a", new_password="new-secret"),
                         Response(), user={"username": "a@example.org"}, db=db)
    assert "a@example.org" not in password_sessions._cache
