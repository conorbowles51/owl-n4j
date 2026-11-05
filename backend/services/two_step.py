"""Two-step sign-in: an authenticator app's six-digit code after the password, or a one-time recovery code.

Standard TOTP (RFC 6238: SHA-1, 6 digits, 30 seconds), written on the standard library. The secret is encrypted with
MFA_ENCRYPTION_KEY, which has no default: while it is unset or unusable nobody can enrol, and the reason says so.

Recovery codes are random (about 78 bits), so a plain salted hash is enough and a match is one indexed read, not a
bcrypt hash per stored code. Accepting a code is one conditional UPDATE, so two requests racing with the same code
cannot both win.

The token that carries a person between the password and the code has no ``sub`` and is signed with its own derived
key: verify_access_token and every other reader of sign-in tokens refuses it.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
import struct
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import config
import secret_check
from postgres.models.enums import GlobalRole
from postgres.models.two_step import LoginPolicy, UserRecoveryCode, UserTwoStep  # noqa: F401 (routers read UserTwoStep)
from services import qr_code

log = logging.getLogger(__name__)

ISSUER = "Loupe"
STEP_SECONDS = 30
DIGITS = 6
# One step either side: a phone clock a little out, or a code typed as it changes.
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
# No 0/O, 1/I/L or U: read off paper by a person.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LENGTH = 16
PENDING_MINUTES = 5
POLICY_CACHE_SECONDS = 30.0
ADMIN_ROLES = (GlobalRole.admin, GlobalRole.super_admin)
MUST_ENROL = "Administrators must use two-step sign-in. Turn it on in Settings, Security, then try again."
CHECK_UNAVAILABLE = ("This server cannot check authenticator codes at the moment (its encryption key is missing or "
                     "changed). Use a recovery code, or ask an administrator.")

_SIX_DIGITS = re.compile(r"^\d{6}$")
_NOT_CODE = re.compile(r"[^A-Z0-9]")


class Unavailable(Exception):
    """The encryption key is missing or does not open the stored secret."""


def key_refusal() -> str | None:
    """Why enrolment is refused on this server, in plain words, or None."""
    problem = secret_check.problem("MFA_ENCRYPTION_KEY", config.MFA_ENCRYPTION_KEY)
    return f"Two-step sign-in is not available on this server yet: {problem}." if problem else None


def _cipher() -> MultiFernet:
    keys = [config.MFA_ENCRYPTION_KEY] + ([config.MFA_ENCRYPTION_KEY_PREVIOUS] if config.MFA_ENCRYPTION_KEY_PREVIOUS else [])
    return MultiFernet([Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"loupe-two-step\0" + key.encode()).digest()))
                        for key in keys if key])


def _open(row: UserTwoStep) -> bytes:
    if secret_check.problem("MFA_ENCRYPTION_KEY", config.MFA_ENCRYPTION_KEY):
        raise Unavailable
    try:
        return _cipher().decrypt(row.secret_encrypted.encode("ascii"))
    except (InvalidToken, ValueError) as err:
        raise Unavailable from err


def rekey(db: Session) -> int:
    """Move every stored secret to MFA_ENCRYPTION_KEY. The caller commits."""
    rows = db.execute(select(UserTwoStep)).scalars().all()
    cipher = _cipher()
    for row in rows:
        row.secret_encrypted = cipher.rotate(row.secret_encrypted.encode("ascii")).decode("ascii")
    return len(rows)


def code_at(secret: bytes, step: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def _matching_step(secret: bytes, code: str, moment: float | None) -> int | None:
    current = int((time.time() if moment is None else moment) // STEP_SECONDS)
    found = None
    # Every step is compared, so the time taken does not say which matched.
    for step in range(current - DRIFT_STEPS, current + DRIFT_STEPS + 1):
        if hmac.compare_digest(code_at(secret, step), code):
            found = step
    return found


def _normal(code: str | None) -> str:
    return _NOT_CODE.sub("", (code or "").upper())


def new_code() -> str:
    """A random code, grouped for reading: ABCD-EFGH-JKMN-PQRS. It is shown once."""
    text = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(text[start:start + 4] for start in range(0, CODE_LENGTH, 4))


def code_hash(user_id, code: str) -> str:
    return hashlib.sha256(f"{user_id}:{_normal(code)}".encode()).hexdigest()


def enrolment_uri(email: str, secret_text: str) -> str:
    uri = (f"otpauth://totp/{ISSUER}:{quote(email, safe='')}?secret={secret_text}&issuer={ISSUER}"
           f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")
    # A very long email would not fit the code; the person's app then shows Loupe alone.
    return uri if len(uri) <= 200 else f"otpauth://totp/{ISSUER}?secret={secret_text}&issuer={ISSUER}"


def _row(db: Session, user_id) -> UserTwoStep | None:
    return db.get(UserTwoStep, user_id)


def is_enrolled(db: Session, user_id) -> bool:
    row = _row(db, user_id)
    return row is not None and row.confirmed_at is not None


def recovery_codes_left(db: Session, user_id) -> int:
    return len(db.execute(select(UserRecoveryCode.id).where(
        UserRecoveryCode.user_id == user_id, UserRecoveryCode.used_at.is_(None))).all())


def begin(db: Session, user) -> dict:
    """A new secret, unconfirmed until a code from it comes back. The caller has checked key_refusal and that the
    person is not already enrolled, and commits."""
    secret = secrets.token_bytes(20)
    secret_text = base64.b32encode(secret).decode("ascii")
    sealed = _cipher().encrypt(secret).decode("ascii")
    row = _row(db, user.id)
    if row is None:
        db.add(UserTwoStep(user_id=user.id, secret_encrypted=sealed))
    else:
        row.secret_encrypted, row.last_used_step = sealed, None
    uri = enrolment_uri(user.email, secret_text)
    return {"secret": secret_text, "uri": uri, "qr": qr_code.encode(uri)}


def replace_recovery_codes(db: Session, user_id) -> list[str]:
    """Ten new codes; every old one stops working. The caller commits, and shows these once."""
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user_id).delete(synchronize_session=False)
    codes = [new_code() for _ in range(RECOVERY_CODE_COUNT)]
    db.add_all(UserRecoveryCode(user_id=user_id, code_hash=code_hash(user_id, code)) for code in codes)
    return codes


def _claim_step(db: Session, user_id, step: int) -> bool:
    return db.execute(update(UserTwoStep).where(
        UserTwoStep.user_id == user_id,
        (UserTwoStep.last_used_step.is_(None)) | (UserTwoStep.last_used_step < step),
    ).values(last_used_step=step).execution_options(synchronize_session=False)).rowcount == 1


def confirm(db: Session, user, code: str, moment: float | None = None) -> list[str] | None:
    """The recovery codes when the code is right, else None. The code that confirms cannot also sign in."""
    row = _row(db, user.id)
    if row is None or row.confirmed_at is not None:
        return None
    step = _matching_step(_open(row), _normal(code), moment)
    if step is None or not _claim_step(db, user.id, step):
        return None
    row.confirmed_at = datetime.now(timezone.utc)
    return replace_recovery_codes(db, user.id)


def check_authenticator_code(db: Session, user, code: str, moment: float | None = None) -> bool:
    """Whether this is a current authenticator code, never accepted before."""
    row = _row(db, user.id)
    if row is None or row.confirmed_at is None:
        return False
    normal = _normal(code)
    if not _SIX_DIGITS.match(normal):
        return False
    step = _matching_step(_open(row), normal, moment)
    return step is not None and _claim_step(db, user.id, step)


def use_recovery_code(db: Session, user, code: str) -> bool:
    return db.execute(update(UserRecoveryCode).where(
        UserRecoveryCode.user_id == user.id, UserRecoveryCode.code_hash == code_hash(user.id, code),
        UserRecoveryCode.used_at.is_(None),
    ).values(used_at=datetime.now(timezone.utc)).execution_options(synchronize_session=False)).rowcount == 1


def second_step(db: Session, user, code: str, moment: float | None = None) -> str | None:
    """"authenticator", "recovery" or None; the caller commits. Raises Unavailable when a six-digit code cannot be
    checked: recovery codes do not need the key."""
    if _SIX_DIGITS.match(_normal(code)):
        return "authenticator" if check_authenticator_code(db, user, code, moment) else None
    return "recovery" if use_recovery_code(db, user, code) else None


def remove(db: Session, user_id) -> None:
    db.query(UserRecoveryCode).filter(UserRecoveryCode.user_id == user_id).delete(synchronize_session=False)
    db.query(UserTwoStep).filter(UserTwoStep.user_id == user_id).delete(synchronize_session=False)


def _pending_key() -> str:
    return hashlib.sha256(b"loupe-two-step-pending\0" + config.AUTH_SECRET_KEY.encode()).hexdigest()


def pending_token(email: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return jwt.encode({"two_step_for": email, "iat": now, "exp": now + timedelta(minutes=PENDING_MINUTES)},
                      _pending_key(), algorithm=config.AUTH_ALGORITHM)


def pending_person(token: str) -> tuple[str, int] | None:
    """(email, issued at) from a live pending token, else None."""
    try:
        payload = jwt.decode(token or "", _pending_key(), algorithms=[config.AUTH_ALGORITHM])
    except JWTError:
        return None
    email = payload.get("two_step_for")
    return (email, int(payload["iat"])) if email and payload.get("iat") else None


_policy_lock = threading.Lock()
_policy_cache: tuple[float, bool] | None = None


def forget_policy() -> None:
    global _policy_cache
    with _policy_lock:
        _policy_cache = None


def _read_policy() -> bool:
    from postgres.session import _get_session_local
    with _get_session_local()() as db:
        row = db.get(LoginPolicy, 1)
        return bool(row and row.require_two_step_for_admins is True)


def required_for_admins() -> bool:
    """The switch, read at most once every POLICY_CACHE_SECONDS per worker. A database that cannot answer leaves the
    requirement as last read: this check is not what decides whether a request can reach the database."""
    global _policy_cache
    with _policy_lock:
        cached = _policy_cache
    if cached is not None and time.monotonic() - cached[0] < POLICY_CACHE_SECONDS:
        return cached[1]
    try:
        value = _read_policy()
    except Exception:
        log.warning("Could not read the sign-in policy", exc_info=True)
        value = cached[1] if cached else False
    with _policy_lock:
        _policy_cache = (time.monotonic(), value)
    return value


def must_enrol(db: Session, user) -> bool:
    """An administrator who has not enrolled, while the switch is on. The first test keeps this free for everyone else."""
    return (getattr(user, "global_role", None) in ADMIN_ROLES and required_for_admins()
            and not is_enrolled(db, user.id))
