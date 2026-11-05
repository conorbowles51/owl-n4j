"""Two-step sign-in, recovery codes, reset codes and the administrators' switch, over the real routes."""
from __future__ import annotations

import ast
import hashlib
import logging
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import config
from postgres.models.activity_event import ActivityEvent
from postgres.models.enums import GlobalRole
from postgres.models.two_step import AccountResetCode, LoginPolicy, UserRecoveryCode, UserTwoStep
from postgres.models.user import User
from postgres.session import get_db
from routers import auth, users
from services import account_recovery, activity_trail, login_limit, password_sessions, qr_code, two_step
from services.auth_service import auth_service

KEY = "k" * 40
PASSWORD = "correct horse battery"
NEW_PASSWORD = "a brand new long passphrase"
BACKEND = Path(__file__).resolve().parents[1]


@compiles(BigInteger, "sqlite")
def _bigint_on_sqlite(element, compiler, **kw):
    return "INTEGER"


def _person(db, email, role=GlobalRole.user, active=True):
    user = User(email=email, name=email.split("@")[0], global_role=role, is_active=active,
                password_hash=bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(4)).decode())
    db.add(user)
    db.commit()
    return user


class World:
    def __init__(self, db, client):
        self.db = db
        self.client = client

    def sign_in(self, email, password=PASSWORD):
        return self.client.post("/api/auth/login", json={"username": email, "password": password})

    def second(self, token, code):
        return self.client.post("/api/auth/login/second-step", json={"two_step_token": token, "code": code})

    def bearer(self, email):
        """A session for this person, as sign-in would make."""
        return {"Authorization": "Bearer " + auth_service["create_access_token"]({"sub": email})}

    def enrol(self, email):
        headers = self.bearer(email)
        started = self.client.post("/api/auth/two-step/start", json={"password": PASSWORD}, headers=headers)
        assert started.status_code == 200, started.text
        secret = started.json()["secret"]
        confirmed = self.client.post("/api/auth/two-step/confirm", json={"code": self.code(secret)}, headers=headers)
        assert confirmed.status_code == 200, confirmed.text
        self.db.expire_all()
        return secret, confirmed.json()["recovery_codes"]

    @staticmethod
    def code(secret, at=None):
        import base64
        step = int((time.time() if at is None else at) // two_step.STEP_SECONDS)
        return two_step.code_at(base64.b32decode(secret), step)

    def later_code(self, secret, steps=1):
        """A code a step later than any used so far, still inside the allowed drift."""
        return self.code(secret, time.time() + steps * two_step.STEP_SECONDS)

    def actions(self, action):
        self.db.expire_all()
        return list(self.db.execute(select(ActivityEvent).where(ActivityEvent.action == action)).scalars())


@pytest.fixture
def world(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (User, UserTwoStep, UserRecoveryCode, AccountResetCode, LoginPolicy, ActivityEvent):
        model.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    db = factory()

    def read_changed(email):
        with factory() as own:
            moment = own.execute(select(User.password_changed_at).where(User.email == email)).scalar()
        return moment.replace(tzinfo=timezone.utc).timestamp() if moment else None

    def read_policy():
        with factory() as own:
            row = own.get(LoginPolicy, 1)
            return bool(row and row.require_two_step_for_admins)

    def session():
        with factory() as own:
            yield own

    monkeypatch.setattr(password_sessions, "_read_changed_at", read_changed)
    monkeypatch.setattr(two_step, "_read_policy", read_policy)
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY", KEY)
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY_PREVIOUS", "")
    password_sessions._cache.clear()
    two_step.forget_policy()

    app = FastAPI()
    app.add_middleware(activity_trail.ActivityContextMiddleware)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.dependency_overrides[get_db] = session

    @app.get("/api/check-admin-screen")
    def admin_screen(user=Depends(users.require_admin)):
        return {"ok": True}

    with TestClient(app) as client:
        yield World(db, client)
    db.close()
    password_sessions._cache.clear()
    two_step.forget_policy()


# --- TOTP and the QR code -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("moment,expected", [(59, "287082"), (1111111109, "081804"), (1234567890, "005924")])
def test_codes_match_the_rfc_6238_vectors(moment, expected):
    assert two_step.code_at(b"12345678901234567890", moment // 30) == expected


# Each equal, bit for bit, to Nayuki qrcodegen at error level M. segno differs on purpose-free padding: it adds a zero
# byte after the terminator when the data ends on a byte boundary.
QR_PINS = {
    "hello": "52a7aa67e7296ede539d6be86579c7180e3b6d417445712ae8bd314c1818458a",
    "otpauth://totp/Loupe:someone%40example.org?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=Loupe&algorithm=SHA1"
    "&digits=6&period=30": "e2a88358a803134540f8720087d7960940aa195a13398ec05febb69b32ed30f5",
}


@pytest.mark.parametrize("text,pin", QR_PINS.items())
def test_the_qr_code_is_the_one_a_standard_encoder_makes(text, pin):
    rows = qr_code.encode(text)
    assert all(len(row) == len(rows) for row in rows)
    assert hashlib.sha256("\n".join(rows).encode()).hexdigest() == pin


def test_a_text_too_long_for_the_code_is_refused_and_a_long_email_still_fits():
    with pytest.raises(ValueError):
        qr_code.encode("x" * 400)
    qr_code.encode(two_step.enrolment_uri("a" * 250 + "@example.org", "A" * 32))


# --- B: enrolment ---------------------------------------------------------------------------------------------------

def test_the_key_has_no_default_in_the_code():
    tree = ast.parse((BACKEND / "config.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and node.args
             and getattr(node.args[0], "value", None) == "MFA_ENCRYPTION_KEY"]
    assert calls and all(getattr(call.args[1], "value", None) == "" for call in calls)


@pytest.mark.parametrize("value,reason", [("", "is not set"), ("abc123", "shorter"),
                                          ("loupe-development-ai-credentials-change-me", "shipped")])
def test_enrolment_is_refused_with_the_reason_while_the_key_is_unusable(world, monkeypatch, value, reason):
    _person(world.db, "a@example.org")
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY", value)
    refused = world.client.post("/api/auth/two-step/start", json={"password": PASSWORD},
                                headers=world.bearer("a@example.org"))
    assert refused.status_code == 503
    assert "MFA_ENCRYPTION_KEY" in refused.json()["detail"] and reason in refused.json()["detail"]
    assert value == "" or value not in refused.json()["detail"]
    status = world.client.get("/api/auth/two-step", headers=world.bearer("a@example.org")).json()
    assert status["unavailable_reason"] and not status["enrolled"]
    assert world.db.execute(select(UserTwoStep)).first() is None


def test_enrolment_needs_the_password_and_a_right_code(world):
    _person(world.db, "a@example.org")
    headers = world.bearer("a@example.org")
    assert world.client.post("/api/auth/two-step/start", json={"password": "wrong"},
                             headers=headers).status_code == 400
    started = world.client.post("/api/auth/two-step/start", json={"password": PASSWORD}, headers=headers)
    assert started.headers["cache-control"] == "no-store"
    body = started.json()
    assert body["uri"].startswith("otpauth://totp/Loupe:a%40example.org?secret=" + body["secret"])
    assert len(body["qr"]) == len(body["qr"][0]) and set("".join(body["qr"])) == {"0", "1"}
    assert world.client.post("/api/auth/two-step/confirm", json={"code": "000000"}, headers=headers).status_code == 400
    # Not enrolled until a code came back: the password alone still signs in.
    assert world.sign_in("a@example.org").json()["access_token"]
    world.db.expire_all()
    stored = world.db.execute(select(UserTwoStep)).scalars().one()
    assert stored.confirmed_at is None and body["secret"] not in stored.secret_encrypted


def test_recovery_codes_are_shown_once_and_stored_hashed(world):
    _person(world.db, "a@example.org")
    _, codes = world.enrol("a@example.org")
    assert len(set(codes)) == 10
    stored = list(world.db.execute(select(UserRecoveryCode.code_hash)).scalars())
    assert len(stored) == 10 and not set(codes) & set(stored)
    plain = {code.replace("-", "") for code in codes}
    assert not plain & set(stored)
    status = world.client.get("/api/auth/two-step", headers=world.bearer("a@example.org")).json()
    assert status["enrolled"] and status["recovery_codes_left"] == 10
    assert "recovery_codes" not in status
    assert len(world.actions("two_step_enrolled")) == 1


def test_a_second_enrolment_is_refused_and_keeps_the_first(world):
    _person(world.db, "a@example.org")
    world.enrol("a@example.org")
    again = world.client.post("/api/auth/two-step/start", json={"password": PASSWORD},
                              headers=world.bearer("a@example.org"))
    assert again.status_code == 409


# --- C: the second step ---------------------------------------------------------------------------------------------

def test_someone_not_enrolled_signs_in_exactly_as_before(world):
    # The shared jobs login and every fleet script: password only, the same fields.
    _person(world.db, "jobs@example.org")
    answer = world.sign_in("jobs@example.org")
    assert answer.status_code == 200
    assert answer.json()["access_token"] and answer.json()["username"] == "jobs@example.org"
    assert "access_token" in answer.cookies
    assert "two_step_required" not in answer.json()


def test_the_password_alone_opens_nothing_for_someone_enrolled(world):
    _person(world.db, "a@example.org")
    world.enrol("a@example.org")
    answer = world.sign_in("a@example.org")
    assert answer.status_code == 200 and answer.json()["two_step_required"] is True
    assert "access_token" not in answer.json() and "access_token" not in answer.cookies
    token = answer.json()["two_step_token"]
    with pytest.raises(Exception):
        auth_service["verify_access_token"](token)
    world.client.cookies.clear()
    assert world.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_a_right_code_signs_in_and_the_trail_says_how(world):
    _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    token = world.sign_in("a@example.org").json()["two_step_token"]
    world.client.cookies.clear()
    done = world.second(token, world.later_code(secret))
    assert done.status_code == 200 and done.json()["username"] == "a@example.org"
    assert "access_token" in done.cookies
    assert world.client.get("/api/auth/me").status_code == 200
    assert world.actions("login_success")[-1].details == {"second_step": "authenticator"}


def test_wrong_code_is_refused_and_rate_limited_through_the_same_limit(world):
    _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    token = world.sign_in("a@example.org").json()["two_step_token"]
    for _ in range(login_limit.ACCOUNT_AT_ADDRESS_LIMIT):
        assert world.second(token, "000000").status_code == 401
    refused = world.second(token, world.later_code(secret))  # right, but too late
    assert refused.status_code == 429 and "Too many" in refused.json()["detail"]
    assert int(refused.headers["retry-after"]) > 0
    assert len(world.actions("login_failure")) == login_limit.ACCOUNT_AT_ADDRESS_LIMIT
    assert len(world.actions("login_rate_limited")) == 1
    # The password step counts the same failures.
    assert world.sign_in("a@example.org").status_code == 429


def test_a_replayed_code_is_refused(world):
    _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    code = world.later_code(secret)
    token = world.sign_in("a@example.org").json()["two_step_token"]
    assert world.second(token, code).status_code == 200
    assert world.second(world.sign_in("a@example.org").json()["two_step_token"], code).status_code == 401


def test_the_code_that_confirmed_enrolment_cannot_sign_in(world):
    _person(world.db, "a@example.org")
    headers = world.bearer("a@example.org")
    secret = world.client.post("/api/auth/two-step/start", json={"password": PASSWORD}, headers=headers).json()["secret"]
    code = world.code(secret)
    assert world.client.post("/api/auth/two-step/confirm", json={"code": code}, headers=headers).status_code == 200
    assert world.second(world.sign_in("a@example.org").json()["two_step_token"], code).status_code == 401


def test_a_code_too_old_or_too_early_is_refused(world):
    _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    token = world.sign_in("a@example.org").json()["two_step_token"]
    assert world.second(token, world.code(secret, time.time() - 120)).status_code == 401
    assert world.second(token, world.code(secret, time.time() + 120)).status_code == 401


def test_a_recovery_code_works_once_however_it_is_typed(world):
    _person(world.db, "a@example.org")
    _, codes = world.enrol("a@example.org")
    done = world.second(world.sign_in("a@example.org").json()["two_step_token"], codes[0].lower().replace("-", " "))
    assert done.status_code == 200
    assert world.actions("login_success")[-1].details == {"second_step": "recovery"}
    assert world.actions("recovery_code_used")[-1].details == {"codes_left": 9}
    assert world.second(world.sign_in("a@example.org").json()["two_step_token"], codes[0]).status_code == 401
    assert world.client.get("/api/auth/two-step", headers=world.bearer("a@example.org")).json()["recovery_codes_left"] == 9


def test_one_persons_recovery_code_does_not_open_another_account(world):
    _person(world.db, "a@example.org")
    _person(world.db, "b@example.org")
    _, codes = world.enrol("a@example.org")
    world.enrol("b@example.org")
    assert world.second(world.sign_in("b@example.org").json()["two_step_token"], codes[0]).status_code == 401


def test_an_expired_pending_token_is_refused(world):
    _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    old = two_step.pending_token("a@example.org", datetime.now(timezone.utc) - timedelta(minutes=6))
    assert world.second(old, world.later_code(secret)).status_code == 401


def test_a_pending_sign_in_dies_with_a_password_change(world):
    user = _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    old = two_step.pending_token("a@example.org", datetime.now(timezone.utc) - timedelta(minutes=1))
    user.password_changed_at = datetime.now(timezone.utc)
    world.db.commit()
    password_sessions.forget("a@example.org")
    assert world.second(old, world.later_code(secret)).status_code == 401


def test_without_the_key_a_six_digit_code_is_explained_and_a_recovery_code_still_works(world, monkeypatch):
    _person(world.db, "a@example.org")
    secret, codes = world.enrol("a@example.org")
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY", "")
    token = world.sign_in("a@example.org").json()["two_step_token"]
    refused = world.second(token, world.later_code(secret))
    assert refused.status_code == 503 and "recovery code" in refused.json()["detail"]
    assert world.second(token, codes[0]).status_code == 200


def test_a_changed_key_is_refused_plainly_and_rekey_moves_secrets_across(world, monkeypatch):
    _person(world.db, "a@example.org")
    secret, _ = world.enrol("a@example.org")
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY", "n" * 40)
    token = world.sign_in("a@example.org").json()["two_step_token"]
    assert world.second(token, world.later_code(secret)).status_code == 503
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY_PREVIOUS", KEY)
    assert two_step.rekey(world.db) == 1
    world.db.commit()
    monkeypatch.setattr(config, "MFA_ENCRYPTION_KEY_PREVIOUS", "")
    assert world.second(token, world.later_code(secret)).status_code == 200


def test_turning_off_and_replacing_codes_need_password_and_code(world):
    _person(world.db, "a@example.org")
    secret, codes = world.enrol("a@example.org")
    headers = world.bearer("a@example.org")
    assert world.client.post("/api/auth/two-step/recovery-codes", json={"password": "no", "code": "000000"},
                             headers=headers).status_code == 400
    new = world.client.post("/api/auth/two-step/recovery-codes",
                            json={"password": PASSWORD, "code": world.later_code(secret)}, headers=headers)
    assert new.status_code == 200 and new.headers["cache-control"] == "no-store"
    assert world.second(world.sign_in("a@example.org").json()["two_step_token"], codes[0]).status_code == 401
    assert world.client.post("/api/auth/two-step/turn-off", json={"password": PASSWORD, "code": "000000"},
                             headers=headers).status_code == 400
    world.db.expire_all()
    world.db.execute(select(UserTwoStep)).scalars().one().last_used_step = 0  # as if a minute had passed
    world.db.commit()
    assert world.client.post("/api/auth/two-step/turn-off", json={"password": PASSWORD, "code": world.code(secret)},
                             headers=headers).status_code == 200
    assert "access_token" in world.sign_in("a@example.org").json()
    assert len(world.actions("two_step_turned_off")) == 1


def test_an_administrator_sees_who_has_enrolled_and_nobody_else_does(world):
    admin = _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    _person(world.db, "b@example.org")
    user_id = str(user.id)
    world.enrol("a@example.org")
    seen = world.client.get("/api/users/two-step", headers=world.bearer("admin@example.org"))
    assert seen.status_code == 200, seen.text
    assert [(p["user_id"], p["recovery_codes_left"]) for p in seen.json()["people"]] == [(user_id, 10)]
    assert seen.json()["required_for_admins"] is False
    assert admin.id
    assert world.client.get("/api/users/two-step", headers=world.bearer("a@example.org")).status_code == 403


# --- E: reset codes -------------------------------------------------------------------------------------------------

def _issue(world, by, target_id):
    return world.client.post(f"/api/users/{target_id}/reset-code", headers=world.bearer(by))


def _redeem(world, email, code, password=NEW_PASSWORD):
    return world.client.post("/api/auth/reset-with-code", json={"email": email, "code": code, "new_password": password})


def test_a_reset_code_sets_a_new_password_once_and_ends_sessions(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    issued = _issue(world, "admin@example.org", user.id)
    assert issued.status_code == 200 and issued.headers["cache-control"] == "no-store"
    code = issued.json()["code"]
    old_session = {"Authorization": "Bearer " + auth_service["create_access_token"](
        {"sub": "a@example.org"}, expires_delta=timedelta(hours=1))}
    time.sleep(1.1)  # whole seconds: a token from the same second as the change is kept
    assert _redeem(world, "a@example.org", code).status_code == 200
    assert world.sign_in("a@example.org", NEW_PASSWORD).status_code == 200
    assert world.sign_in("a@example.org", PASSWORD).status_code == 401
    world.client.cookies.clear()
    assert world.client.get("/api/auth/me", headers=old_session).status_code == 401
    assert _redeem(world, "a@example.org", code, "yet another long passphrase").status_code == 400
    stored = world.db.execute(select(AccountResetCode)).scalars().one()
    assert stored.code_hash != code and stored.issued_by == "admin@example.org" and stored.used_at
    issued_row = world.actions("reset_code_issued")[-1]
    assert issued_row.user_email == "admin@example.org" and issued_row.details["person"] == "a@example.org"
    assert code not in str(issued_row.details)
    assert world.actions("password_reset_with_code")[-1].details == {"issued_by": "admin@example.org"}


def test_a_reset_code_expires(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    code = _issue(world, "admin@example.org", user.id).json()["code"]
    row = world.db.execute(select(AccountResetCode)).scalars().one()
    assert row.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc) <= account_recovery.RESET_CODE_LIFETIME
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    world.db.commit()
    assert _redeem(world, "a@example.org", code).status_code == 400
    assert world.sign_in("a@example.org").status_code == 200


def test_a_new_reset_code_ends_the_old_one_and_a_wrong_person_cannot_use_it(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    other = _person(world.db, "b@example.org")
    first = _issue(world, "admin@example.org", user.id).json()["code"]
    second = _issue(world, "admin@example.org", user.id).json()["code"]
    assert _issue(world, "admin@example.org", other.id).status_code == 200
    assert _redeem(world, "a@example.org", first).status_code == 400
    assert _redeem(world, "b@example.org", second).status_code == 400
    assert _redeem(world, "a@example.org", second).status_code == 200


def test_a_refused_new_password_leaves_the_code_usable(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    code = _issue(world, "admin@example.org", user.id).json()["code"]
    refused = _redeem(world, "a@example.org", code, "short")
    assert refused.status_code == 400 and "12 characters" in refused.json()["detail"]
    assert _redeem(world, "a@example.org", code).status_code == 200


def test_wrong_reset_codes_are_rate_limited(world):
    _person(world.db, "a@example.org")
    for _ in range(login_limit.ACCOUNT_AT_ADDRESS_LIMIT):
        assert _redeem(world, "a@example.org", "AAAA-BBBB-CCCC-DDDD").status_code == 400
    assert _redeem(world, "a@example.org", "AAAA-BBBB-CCCC-DDDD").status_code == 429


def test_a_reset_does_not_get_past_two_step_and_removal_is_separate(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    world.enrol("a@example.org")
    code = _issue(world, "admin@example.org", user.id).json()["code"]
    assert _redeem(world, "a@example.org", code).status_code == 200
    assert world.sign_in("a@example.org", NEW_PASSWORD).json()["two_step_required"] is True
    removed = world.client.post(f"/api/users/{user.id}/two-step/remove", headers=world.bearer("admin@example.org"))
    assert removed.status_code == 200
    assert "access_token" in world.sign_in("a@example.org", NEW_PASSWORD).json()
    assert world.actions("two_step_removed")[-1].details == {"person": "a@example.org"}


def test_who_may_recover_whom(world):
    admin = _person(world.db, "admin@example.org", GlobalRole.admin)
    peer = _person(world.db, "peer@example.org", GlobalRole.admin)
    top = _person(world.db, "top@example.org", GlobalRole.super_admin)
    user = _person(world.db, "a@example.org")
    gone = _person(world.db, "gone@example.org", active=False)
    assert _issue(world, "admin@example.org", admin.id).status_code == 400  # never oneself
    assert _issue(world, "top@example.org", top.id).status_code == 400
    assert _issue(world, "admin@example.org", peer.id).status_code == 403
    assert _issue(world, "admin@example.org", top.id).status_code == 403
    assert _issue(world, "a@example.org", admin.id).status_code == 403
    assert _issue(world, "admin@example.org", gone.id).status_code == 400
    assert _issue(world, "top@example.org", peer.id).status_code == 200
    assert _issue(world, "admin@example.org", user.id).status_code == 200
    assert world.client.post(f"/api/users/{user.id}/reset-code").status_code == 401


def test_a_right_reset_code_works_for_someone_who_locked_themselves_out(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    for _ in range(login_limit.ACCOUNT_AT_ADDRESS_LIMIT):
        assert world.sign_in("a@example.org", "a wrong password").status_code == 401
    assert world.sign_in("a@example.org").status_code == 429
    code = _issue(world, "admin@example.org", user.id).json()["code"]
    assert _redeem(world, "a@example.org", code).status_code == 200


def test_wrong_enrolment_codes_do_not_lock_the_person_out_of_signing_in(world):
    _person(world.db, "a@example.org")
    headers = world.bearer("a@example.org")
    world.client.post("/api/auth/two-step/start", json={"password": PASSWORD}, headers=headers)
    for _ in range(login_limit.ACCOUNT_AT_ADDRESS_LIMIT + 1):
        assert world.client.post("/api/auth/two-step/confirm", json={"code": "000000"}, headers=headers).status_code == 400
    assert world.sign_in("a@example.org").status_code == 200


def test_wrong_current_passwords_at_change_password_are_counted_and_limited(world):
    _person(world.db, "a@example.org")
    headers = world.bearer("a@example.org")
    body = {"current_password": "not it", "new_password": NEW_PASSWORD}
    for _ in range(login_limit.ACCOUNT_AT_ADDRESS_LIMIT):
        refused = world.client.put("/api/auth/change-password", json=body, headers=headers)
        assert refused.status_code == 400 and refused.json()["detail"] == "Current password is incorrect"
    assert world.client.put("/api/auth/change-password", json=body, headers=headers).status_code == 429


def test_someone_who_lost_their_device_uses_a_recovery_code_to_turn_off_and_enrol_again(world):
    _person(world.db, "a@example.org")
    _, codes = world.enrol("a@example.org")
    headers = world.bearer("a@example.org")
    fresh = world.client.post("/api/auth/two-step/recovery-codes", json={"password": PASSWORD, "code": codes[0]},
                              headers=headers)
    assert fresh.status_code == 200
    assert world.client.post("/api/auth/two-step/turn-off", json={"password": PASSWORD, "code": fresh.json()["recovery_codes"][0]},
                             headers=headers).status_code == 200
    world.enrol("a@example.org")


def test_a_right_password_stopped_at_the_second_step_is_in_the_trail(world):
    _person(world.db, "a@example.org")
    world.enrol("a@example.org")
    world.sign_in("a@example.org")
    assert len(world.actions("login_password_accepted")) == 1
    assert not world.actions("login_success")


def test_the_older_password_field_keeps_the_same_rules_and_is_audited(world):
    admin = _person(world.db, "admin@example.org", GlobalRole.admin)
    peer = _person(world.db, "peer@example.org", GlobalRole.admin)
    _person(world.db, "top@example.org", GlobalRole.super_admin)
    user = _person(world.db, "a@example.org")
    body = {"password": NEW_PASSWORD}
    assert world.client.patch(f"/api/users/{admin.id}", json=body, headers=world.bearer("admin@example.org")).status_code == 400
    assert world.client.patch(f"/api/users/{peer.id}", json=body, headers=world.bearer("admin@example.org")).status_code == 403
    assert world.client.patch(f"/api/users/{peer.id}", json=body, headers=world.bearer("top@example.org")).status_code == 200
    assert world.client.patch(f"/api/users/{user.id}", json=body, headers=world.bearer("admin@example.org")).status_code == 200
    assert [(row.user_email, row.details["person"]) for row in world.actions("password_set_by_admin")] == [
        ("top@example.org", "peer@example.org"), ("admin@example.org", "a@example.org")]


# --- D: the administrators' switch, and last-administrator lockout ---------------------------------------------------

def test_the_last_super_admin_cannot_be_demoted_or_deactivated(world):
    top = _person(world.db, "top@example.org", GlobalRole.super_admin)
    other = _person(world.db, "other@example.org", GlobalRole.super_admin)
    headers = world.bearer("other@example.org")
    assert world.client.patch(f"/api/users/{top.id}", json={"is_active": False}, headers=headers).status_code == 200
    answer = world.client.patch(f"/api/users/{other.id}", json={"role": "user"}, headers=headers)
    assert answer.status_code == 400 and "last super_admin" in answer.json()["detail"]


def test_the_switch_is_refused_until_every_administrator_is_ready_and_stays_off(world, monkeypatch, capsys):
    monkeypatch.setattr(account_recovery, "_session_factory", lambda: sessionmaker(bind=world.db.get_bind()))
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "s" * 40)
    _person(world.db, "admin@example.org", GlobalRole.admin)
    _person(world.db, "top@example.org", GlobalRole.super_admin)
    assert account_recovery.main(["require", "--on"]) == 1
    printed = capsys.readouterr().out
    assert "admin@example.org has not enrolled" in printed and "top@example.org has not enrolled" in printed
    assert world.db.get(LoginPolicy, 1) is None
    world.enrol("admin@example.org")
    world.enrol("top@example.org")
    world.db.expire_all()
    assert account_recovery.readiness(world.db)[1] == []
    world.db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == world.db.execute(
        select(User.id).where(User.email == "top@example.org")).scalar()).delete()
    world.db.commit()
    assert account_recovery.main(["require", "--on"]) == 1
    assert "top@example.org has no recovery code left" in capsys.readouterr().out
    assert world.db.get(LoginPolicy, 1) is None


@pytest.mark.parametrize("name,value,words", [("AUTH_SECRET_KEY", "supersecretchange", "shipped"),
                                              ("MFA_ENCRYPTION_KEY", "", "not set")])
def test_the_switch_is_refused_on_a_shipped_signing_key_or_no_encryption_key(world, monkeypatch, name, value, words):
    monkeypatch.setattr(config, "AUTH_SECRET_KEY", "s" * 40)
    monkeypatch.setattr(config, name, value)
    refusals = account_recovery.readiness(world.db)[1]
    assert any(name in line and words in line for line in refusals)


def _switch_on(world):
    world.db.add(LoginPolicy(id=1, require_two_step_for_admins=True))
    world.db.commit()
    two_step.forget_policy()


def test_with_the_switch_on_an_administrator_who_has_not_enrolled_must_enrol_first(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    _person(world.db, "a@example.org")
    _switch_on(world)
    answer = world.sign_in("admin@example.org")
    assert answer.json()["two_step_setup_required"] is True
    world.client.cookies.clear()
    headers = world.bearer("admin@example.org")
    refused = world.client.get("/api/check-admin-screen", headers=headers)
    assert refused.status_code == 403 and "two-step" in refused.json()["detail"]
    world.enrol("admin@example.org")
    assert world.client.get("/api/check-admin-screen", headers=headers).status_code == 200
    # Someone who is not an administrator is untouched.
    plain = world.sign_in("a@example.org")
    assert plain.json()["access_token"] and plain.json()["two_step_setup_required"] is False


def test_with_the_switch_on_an_administrator_cannot_turn_two_step_off(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    secret, _ = world.enrol("admin@example.org")
    _switch_on(world)
    refused = world.client.post("/api/auth/two-step/turn-off", json={"password": PASSWORD, "code": world.code(secret)},
                                headers=world.bearer("admin@example.org"))
    assert refused.status_code == 403


def test_the_box_command_recovers_an_administrator_and_is_audited(world, monkeypatch, capsys):
    monkeypatch.setattr(account_recovery, "_session_factory", lambda: sessionmaker(bind=world.db.get_bind()))
    _person(world.db, "last@example.org", GlobalRole.super_admin)
    world.enrol("last@example.org")
    assert account_recovery.main(["reset", "last@example.org", "--remove-two-step"]) == 0
    printed = capsys.readouterr().out
    code = next(word for word in printed.split() if word.count("-") == 3)
    assert _redeem(world, "last@example.org", code).status_code == 200
    assert "access_token" in world.sign_in("last@example.org", NEW_PASSWORD).json()
    issued = world.actions("reset_code_issued")[-1]
    assert issued.source_address == activity_trail.SYSTEM_ADDRESS and code not in str(issued.details)
    assert len(world.actions("two_step_removed")) == 1


def test_the_box_command_refuses_anyone_but_an_active_administrator(world, monkeypatch, capsys):
    monkeypatch.setattr(account_recovery, "_session_factory", lambda: sessionmaker(bind=world.db.get_bind()))
    _person(world.db, "a@example.org")
    _person(world.db, "gone@example.org", GlobalRole.admin, active=False)
    assert account_recovery.main(["reset", "a@example.org"]) == 2
    assert account_recovery.main(["reset", "gone@example.org"]) == 2
    assert account_recovery.main(["reset", "nobody@example.org"]) == 2
    assert world.db.execute(select(AccountResetCode)).first() is None


def test_the_switch_check_lists_administrators_script_sign_ins(world):
    _person(world.db, "admin@example.org", GlobalRole.admin)
    _person(world.db, "a@example.org")
    now = datetime.now(timezone.utc)
    for email, agent in (("admin@example.org", "python-requests/2.32"), ("admin@example.org", "Mozilla/5.0 Chrome"),
                         ("a@example.org", "python-requests/2.32")):
        world.db.add(ActivityEvent(action="login_success", user_email=email, user_agent=agent, at=now, details={}))
    world.db.commit()
    assert account_recovery.script_sign_ins(world.db) == [("admin@example.org", "python-requests/2.32", 1)]


def test_the_box_script_runs_the_module_from_the_backend_folder(tmp_path):
    (tmp_path / "backend").mkdir()
    fake = tmp_path / "python"
    fake.write_text('#!/bin/sh\necho "$PWD|$*"\n')
    fake.chmod(0o755)
    done = subprocess.run(["bash", str(BACKEND.parent / "deploy" / "account-recovery.sh"), "require", "--check"],
                          env={"ROOT_DIR": str(tmp_path), "PYTHON_BIN": str(fake), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"{tmp_path}/backend|-m services.account_recovery require --check"


# --- Secrets never reach the logs ------------------------------------------------------------------------------------

def test_no_secret_or_code_is_logged_or_kept_in_the_trail(world, caplog):
    caplog.set_level(logging.DEBUG)
    _person(world.db, "admin@example.org", GlobalRole.admin)
    user = _person(world.db, "a@example.org")
    secret, codes = world.enrol("a@example.org")
    login = world.sign_in("a@example.org").json()["two_step_token"]
    assert world.second(login, codes[1]).status_code == 200
    reset = _issue(world, "admin@example.org", user.id).json()["code"]
    assert _redeem(world, "a@example.org", reset).status_code == 200
    world.db.expire_all()
    trail = " ".join(str(row.details) for row in world.db.execute(select(ActivityEvent)).scalars())
    for value in (secret, reset, *codes):
        assert value not in caplog.text and value not in trail
