"""Sign-in hardening: refused default secrets, the failed sign-in limit, the password rule, HTTPS-only flags."""
from __future__ import annotations

import ast
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import secret_check
from postgres.models.activity_event import ActivityEvent
from routers import auth, setup, users
from services import activity_trail, https_headers, login_limit, password_rule, startup_secrets_warning

BACKEND = Path(__file__).resolve().parents[1]
GOOD = {"AUTH_SECRET_KEY": "k" * 40, "AI_CREDENTIAL_ENCRYPTION_KEY": "e" * 40, "EVIDENCE_ENGINE_API_KEY": "s" * 40}


# --- A: secrets -----------------------------------------------------------------------------------------------------

def _start(extra: dict[str, str]) -> subprocess.CompletedProcess:
    """Import config in a clean process, as a server start does."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"LOUPE_ENV", *GOOD}}
    # A .env beside the checkout must not decide the test.
    environment.update(extra, PYTHONDONTWRITEBYTECODE="1")
    code = "import dotenv; dotenv.load_dotenv = lambda *a, **k: False; import config; print('started')"
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=environment, capture_output=True, text=True,
                          timeout=180)


def test_production_refuses_the_shipped_secret_and_names_it_never_showing_it():
    done = _start({"LOUPE_ENV": "production", "AUTH_SECRET_KEY": "supersecretchange"})
    assert done.returncode != 0 and "started" not in done.stdout
    assert "AUTH_SECRET_KEY" in done.stderr
    assert "AI_CREDENTIAL_ENCRYPTION_KEY" in done.stderr  # missing, so named too
    assert "supersecretchange" not in done.stderr


def test_production_with_real_secrets_starts():
    done = _start({"LOUPE_ENV": "production", **GOOD})
    assert done.returncode == 0, done.stderr
    assert "started" in done.stdout


def test_development_and_test_still_start_without_any_secret():
    done = _start({})
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("value, reason", [
    ("", "not set"),
    ("loupe-development-ai-credentials-change-me", "shipped"),
    ("replace-with-a-long-random-encryption-secret", "shipped"),
    ("short-but-mine", "shorter"),
])
def test_each_kind_of_unusable_secret_has_its_reason(value, reason):
    found = secret_check.problems({**GOOD, "AI_CREDENTIAL_ENCRYPTION_KEY": value})
    assert len(found) == 1
    assert found[0].startswith("AI_CREDENTIAL_ENCRYPTION_KEY") and reason in found[0]
    if value:
        assert value not in found[0]


def test_the_engine_key_is_required_only_when_the_engine_is_used():
    without = {key: value for key, value in GOOD.items() if key != "EVIDENCE_ENGINE_API_KEY"}
    assert secret_check.problems({**without, "USE_EVIDENCE_ENGINE": "false"}) == []
    assert secret_check.problems(without) == ["EVIDENCE_ENGINE_API_KEY is not set"]


def test_an_unmarked_server_warns_by_name_and_a_production_one_has_nothing_to_warn(caplog):
    assert startup_secrets_warning.warn_when_not_enforced({}) != []
    assert "AUTH_SECRET_KEY" in caplog.text
    assert startup_secrets_warning.warn_when_not_enforced({"LOUPE_ENV": "production", **GOOD}) == []


# --- B: failed sign-in limit ----------------------------------------------------------------------------------------

@compiles(BigInteger, "sqlite")
def _bigint_on_sqlite(element, compiler, **kw):
    return "INTEGER"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    ActivityEvent.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def _failures(db, count, *, email="a@example.org", address="203.0.113.1", ago=timedelta(minutes=1)):
    for index in range(count):
        db.add(ActivityEvent(action="login_failure", user_email=email, source_address=address,
                             at=NOW - ago - timedelta(seconds=index), details={}))
    db.commit()


def test_under_the_limit_nothing_is_refused(db):
    _failures(db, login_limit.ACCOUNT_AT_ADDRESS_LIMIT - 1)
    assert login_limit.refusal(db, "a@example.org", "203.0.113.1", NOW) is None


def test_one_account_from_one_address_is_stopped_and_told_the_wait(db):
    _failures(db, login_limit.ACCOUNT_AT_ADDRESS_LIMIT)
    limited = login_limit.refusal(db, "A@Example.org", "203.0.113.1", NOW)
    assert limited.scope == "account_at_address"
    assert 13 * 60 < limited.wait_seconds <= 14 * 60 + 1
    assert limited.message == "Too many failed sign-ins. Wait 14 minutes and try again."


def test_one_address_sweeping_accounts_is_stopped(db):
    for index in range(login_limit.ADDRESS_LIMIT):
        _failures(db, 1, email=f"person{index}@example.org")
    assert login_limit.refusal(db, "new@example.org", "203.0.113.1", NOW).scope == "address"
    assert login_limit.refusal(db, "new@example.org", "203.0.113.2", NOW) is None


def test_one_outsider_cannot_lock_a_real_person_out_from_elsewhere(db):
    _failures(db, login_limit.ACCOUNT_AT_ADDRESS_LIMIT, address="198.51.100.9")
    assert login_limit.refusal(db, "a@example.org", "203.0.113.1", NOW) is None


def test_a_guess_spread_over_many_addresses_is_still_bounded(db):
    for index in range(login_limit.ACCOUNT_LIMIT):
        _failures(db, 1, address=f"198.51.{index // 250}.{index % 250}")
    assert login_limit.refusal(db, "a@example.org", "203.0.113.1", NOW).scope == "account"


def test_failures_older_than_the_window_do_not_count(db):
    _failures(db, 50, ago=login_limit.WINDOW + timedelta(seconds=1))
    assert login_limit.refusal(db, "a@example.org", "203.0.113.1", NOW) is None


def test_successes_never_count(db):
    for index in range(500):
        db.add(ActivityEvent(action="login_success", user_email="a@example.org", source_address="203.0.113.1",
                             at=NOW - timedelta(seconds=index), details={}))
    db.commit()
    assert login_limit.refusal(db, "a@example.org", "203.0.113.1", NOW) is None


def test_an_unreadable_trail_refuses_nobody():
    broken = MagicMock()
    broken.query.side_effect = RuntimeError("no trail")
    assert login_limit.refusal(broken, "a@example.org", "203.0.113.1", NOW) is None
    broken.rollback.assert_called_once()


def test_login_is_refused_before_the_password_is_hashed_with_the_wait_and_audited(db, monkeypatch):
    real_now = datetime.now(timezone.utc)
    for index in range(login_limit.ACCOUNT_AT_ADDRESS_LIMIT):
        db.add(ActivityEvent(action="login_failure", user_email="a@example.org", source_address="203.0.113.1",
                             at=real_now - timedelta(seconds=index + 1), details={}))
    db.commit()
    monkeypatch.setattr(auth.activity_trail, "current_context", lambda: {"address": "203.0.113.1"})
    monkeypatch.setitem(auth.auth_service, "authenticate_from_db",
                        lambda *args: pytest.fail("a limited attempt must not reach the password hash"))
    request = auth.LoginRequest(username="a@example.org", password="whatever")
    for _ in range(2):
        with pytest.raises(HTTPException) as refused:
            auth.login(request, Response(), db)
        assert refused.value.status_code == 429
        assert refused.value.headers["Retry-After"].isdigit()
        assert "Too many failed sign-ins. Wait " in refused.value.detail
    rows = db.query(ActivityEvent).filter(ActivityEvent.action == "login_rate_limited").all()
    assert len(rows) == 1  # one row a minute, however many attempts
    assert rows[0].user_email == "a@example.org"
    assert rows[0].details["limit"] == "account_at_address"
    assert activity_trail.ACTIONS["login_rate_limited"]


# --- C: password rule -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("password", [
    "short-one", "passwordpassword", "Password1234!", "p@ssw0rd12345", "qwerty123456", "1q2w3e4r5t6y", "123456789012",
    "aaaaaaaaaaaa", "abcabcabcabc", "abcdefghijkl", "qwertyuiopas", "administrator", "Administrator1", "loupe12345678",
    "owlinvestigates", "sunshine12345", "iloveyou1234",
])
def test_weak_passwords_are_refused(password):
    assert password_rule.refusal(password)


@pytest.mark.parametrize("password", ["a-long-new-phrase-9", "correct horse battery", "Tr7!vq2#Lp9$xZ", "river stone maple"])
def test_real_passwords_pass(password):
    assert password_rule.refusal(password) is None


def test_the_person_s_own_name_or_email_is_refused():
    assert password_rule.refusal("merrickson2024", email="merrickson@example.org")
    assert password_rule.refusal("Archibald1234!", name="Archibald Smith")
    assert password_rule.refusal("merrickson2024", email="other@example.org") is None


def test_a_password_bcrypt_cannot_take_is_refused_with_a_reason_not_a_crash():
    assert "at most" in password_rule.refusal("x7-" * 30)


def _db_with(user):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def test_change_password_refuses_a_weak_one_and_keeps_the_old_hash(monkeypatch):
    user = SimpleNamespace(email="a@example.org", name="A", password_hash=users.hash_password("the-old-one"))
    before = user.password_hash
    with pytest.raises(HTTPException) as refused:
        auth.change_password(auth.ChangePasswordRequest(current_password="the-old-one", new_password="password1234"),
                             Response(), {"username": "a@example.org"}, _db_with(user))
    assert refused.value.status_code == 400
    assert user.password_hash == before


def test_a_wrong_current_password_is_told_as_wrong_even_when_the_new_one_is_weak():
    user = SimpleNamespace(email="a@example.org", name="A", password_hash=users.hash_password("the-old-one"))
    with pytest.raises(HTTPException) as refused:
        auth.change_password(auth.ChangePasswordRequest(current_password="wrong", new_password="x"), Response(),
                             {"username": "a@example.org"}, _db_with(user))
    assert refused.value.detail == "Current password is incorrect"


def test_admin_create_and_set_refuse_a_weak_password():
    admin = SimpleNamespace(global_role=users.GlobalRole.super_admin, id="me")
    db = _db_with(None)
    with pytest.raises(HTTPException) as refused:
        users.create_user(users.UserCreate(email="a@example.org", name="A", password="password1234"), db, admin)
    assert refused.value.status_code == 400
    db.add.assert_not_called()
    target = SimpleNamespace(id="them", email="a@example.org", name="A", global_role=users.GlobalRole.user,
                             password_hash="kept")
    with pytest.raises(HTTPException):
        users.update_user("them", users.UserUpdate(password="short"), _db_with(target), admin)
    assert target.password_hash == "kept"


def test_first_time_setup_refuses_a_weak_password():
    db = MagicMock()
    db.query.return_value.scalar.return_value = 0
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as refused:
        setup.create_initial_user(setup.InitialUserRequest(email="a@example.org", name="A", password="password1234"), db)
    assert refused.value.status_code == 400
    db.add.assert_not_called()


def test_every_route_module_that_hashes_a_password_checks_the_rule_first():
    """A new path that sets a password has to come through here."""
    for path in sorted((BACKEND / "routers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name in {"hash_password", "verify_password"}:
                continue
            source = ast.unparse(node)
            if "hash_password(" in source:
                assert "password_rule.require_acceptable" in source, f"{path.name}: {node.name}"
                assert source.index("password_rule.require_acceptable") < source.index("hash_password(")


def test_an_existing_short_password_still_signs_in():
    assert users.verify_password("short", users.hash_password("short"))
    assert "password_rule" not in Path(BACKEND / "services" / "auth_service.py").read_text(encoding="utf-8")


# --- F: HTTPS-only flags --------------------------------------------------------------------------------------------

def _cookie_header(monkeypatch, https: bool) -> str:
    monkeypatch.setattr(auth, "LOUPE_HTTPS", https)
    response = Response()
    auth._set_access_cookie(response, "token")
    return response.headers["set-cookie"].lower()


def test_the_plain_http_address_gets_no_secure_flag_and_https_does(monkeypatch):
    assert "secure" not in _cookie_header(monkeypatch, False)
    assert "samesite=lax" in _cookie_header(monkeypatch, False)
    assert "secure" in _cookie_header(monkeypatch, True)


def _app(enabled: bool) -> TestClient:
    app = FastAPI()
    app.get("/x")(lambda: {"ok": True})
    assert https_headers.install(app, enabled) is enabled
    return TestClient(app)


def test_hsts_only_when_served_over_https():
    assert "strict-transport-security" not in _app(False).get("/x").headers
    assert _app(True).get("/x").headers["strict-transport-security"].startswith("max-age=")


# --- D: admin routes ------------------------------------------------------------------------------------------------

def test_someone_else_s_background_tasks_are_for_administrators(monkeypatch):
    from routers import background_tasks

    monkeypatch.setattr(background_tasks.background_task_storage, "list_tasks", lambda **kwargs: [])
    person = {"username": "a@example.org"}
    member = SimpleNamespace(global_role=users.GlobalRole.user, is_active=True)
    with pytest.raises(HTTPException) as refused:
        background_tasks.list_tasks(owner="b@example.org", user=person, db=_db_with(member))
    assert refused.value.status_code == 403
    assert background_tasks.list_tasks(owner="a@example.org", user=person, db=_db_with(member)).tasks == []
    assert background_tasks.list_tasks(user=person, db=_db_with(member)).tasks == []
    admin = SimpleNamespace(global_role=users.GlobalRole.admin, is_active=True)
    assert background_tasks.list_tasks(owner="b@example.org", user=person, db=_db_with(admin)).tasks == []


# --- Rotation -------------------------------------------------------------------------------------------------------

def test_stored_credentials_move_to_a_new_key_with_no_moment_unreadable():
    from postgres.models.runtime_state import AIProviderCredential
    from services.ai_provider_credentials import AIProviderCredentialStore, CredentialDecryptionError

    engine = create_engine("sqlite://")
    AIProviderCredential.__table__.create(engine)
    db = sessionmaker(bind=engine)()
    old = AIProviderCredentialStore(encryption_key="old-key")
    db.add(AIProviderCredential(provider="openai", encrypted_api_key=old._encrypt("sk-live"), status="connected",
                                source="database", revision=1))
    db.add(AIProviderCredential(provider="deepseek", encrypted_api_key=None, status="disconnected",
                                source="database", revision=1))
    db.commit()

    both = AIProviderCredentialStore(encryption_key="new-key", previous_encryption_key="old-key")
    assert both.get_api_key(db, "openai") == "sk-live"  # read during the change
    assert both.rekey_stored(db, apply=False) == ["openai"]
    assert old.get_api_key(db, "openai") == "sk-live"  # a dry run writes nothing

    assert both.rekey_stored(db, apply=True) == ["openai"]
    assert AIProviderCredentialStore(encryption_key="new-key").get_api_key(db, "openai") == "sk-live"
    with pytest.raises(CredentialDecryptionError):
        old.get_api_key(db, "openai")
    wrong = AIProviderCredentialStore(encryption_key="other")
    with pytest.raises(CredentialDecryptionError):
        wrong.rekey_stored(db, apply=True)


# --- E: the cookie alone -------------------------------------------------------------------------------------------

def _extract(header: str | None, cookie: str | None):
    from fastapi.security import HTTPAuthorizationCredentials

    request = SimpleNamespace(cookies={"access_token": cookie} if cookie else {})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=header) if header else None
    return asyncio.run(auth._extract_token(request, credentials))


def test_the_cookie_alone_signs_in_a_script_token_still_wins_and_an_empty_header_falls_back():
    assert _extract(None, "from-cookie") == "from-cookie"
    assert _extract("real.token.here", "from-cookie") == "real.token.here"
    assert _extract("null", "from-cookie") == "from-cookie"
    assert _extract("undefined", None) is None
