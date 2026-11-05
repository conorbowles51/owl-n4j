"""
Authentication router

Provides login/logout and current-user endpoints backed by JWT.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from config import AUTH_TOKEN_EXPIRE_MINUTES, LOUPE_HTTPS
from postgres.session import get_db
from services.auth_service import auth_service
from services import activity_trail
from services import request_speed
from services import account_recovery, login_limit, password_rule, password_sessions, two_step

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)
_COOKIE_MAX_AGE = AUTH_TOKEN_EXPIRE_MINUTES * 60


def _set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=LOUPE_HTTPS,
        max_age=_COOKIE_MAX_AGE,
    )


class LoginRequest(BaseModel):
    username: str  # Actually email, kept as 'username' for frontend compatibility
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str  # Actually email, kept as 'username' for frontend compatibility
    name: str
    role: str | None = None
    # An administrator who must enrol before the administrator screens answer (the switch in services.two_step).
    two_step_setup_required: bool = False


class SecondStepNeeded(BaseModel):
    two_step_required: bool = True
    two_step_token: str
    username: str


class SecondStepRequest(BaseModel):
    two_step_token: str
    code: str


class MeResponse(BaseModel):
    email: str
    name: str
    username: str  # Backwards compatibility (same as email)
    role: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class PasswordOnly(BaseModel):
    password: str


class CodeOnly(BaseModel):
    code: str


class PasswordAndCode(BaseModel):
    password: str
    code: str


class ResetWithCodeRequest(BaseModel):
    email: str
    code: str
    new_password: str


# _extract_token and get_current_user are async on purpose: they read a header and check a JWT (no I/O), and as
# plain functions every request spent two thread-pool hops on them, queued behind slow handlers when the pool is busy.
async def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str | None:
    # "null": a page script that read the token browsers no longer keep. Its sign-in cookie, if any, still counts.
    if credentials and credentials.credentials and credentials.credentials not in {"null", "undefined"}:
        return credentials.credentials
    if request:
        return request.cookies.get("access_token")
    return None


async def get_current_user(
    token: str = Depends(_extract_token),
) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")

    try:
        data = auth_service["verify_access_token"](token)
    except Exception as err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(err)) from err
    if isinstance(data, dict):
        if await password_sessions.refused(data):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="This sign-in ended when the password was changed. Sign in again.")
        data = {key: value for key, value in data.items() if key != "issued_at"}
    request_speed.note_person(data.get("username") if isinstance(data, dict) else None)
    return data


def _refuse_if_limited(db: Session, email: str) -> None:
    # Before any hash or code, so refused attempts cost the server almost nothing.
    address = (activity_trail.current_context() or {}).get("address")
    limited = login_limit.refusal(db, email, address)
    if limited:
        login_limit.record_refusal(db, email, address, limited)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=limited.message,
                            headers={"Retry-After": str(limited.wait_seconds)})


def _count_failure(db: Session, email: str, reason: str) -> None:
    # The address and the name typed are kept; never the password or code. login_limit counts this row.
    db.rollback()
    activity_trail.record('login_failure', db=db, commit=True, user_email=(email or '')[:255],
                          details=dict(reason=reason))


def _no_store(body: dict) -> JSONResponse:
    """An answer holding a secret or code shown once: no browser or proxy keeps it."""
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


def _signed_in(db: Session, user, response: Response, **details) -> TokenResponse:
    token = auth_service["create_access_token"]({"sub": user.email})
    _set_access_cookie(response, token)
    activity_trail.record('login_success', db=db, commit=True, user=user, session=activity_trail.token_ref(token),
                          details=details or None)
    return TokenResponse(access_token=token, username=user.email, name=user.name, role=user.global_role.value,
                         two_step_setup_required=two_step.must_enrol(db, user))


@router.post("/login", response_model=TokenResponse | SecondStepNeeded)
def login(request: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Login endpoint - authenticates user and returns JWT token."""
    try:
        _refuse_if_limited(db, request.username)

        # username field is actually the email
        user = auth_service["authenticate_from_db"](db, request.username, request.password)
        if not user:
            # The address and the name typed are kept; never the password.
            activity_trail.record('login_failure', db=db, commit=True, user_email=(request.username or '')[:255],
                                  details=dict(reason='invalid_credentials_or_inactive'))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if two_step.is_enrolled(db, user.id):
            # No cookie and no sign-in token yet: the password alone opens nothing. The trail still shows it was right,
            # so a stolen password stopped at the code is visible. login_limit does not count this row.
            activity_trail.record('login_password_accepted', db=db, commit=True, user=user)
            return SecondStepNeeded(two_step_token=two_step.pending_token(user.email), username=user.email)

        return _signed_in(db, user, response)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login error: {str(e)}"
        )


@router.post("/login/second-step", response_model=TokenResponse)
def login_second_step(request: SecondStepRequest, response: Response, db: Session = Depends(get_db)):
    """The code after the password. Failures count towards the same limit as wrong passwords."""
    from postgres.models.user import User

    pending = two_step.pending_person(request.two_step_token)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This sign-in took too long. Enter your password again.")
    email, issued = pending
    _refuse_if_limited(db, email)
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active or password_sessions.issued_before_change(
            issued, password_sessions.changed_at(email)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This sign-in took too long. Enter your password again.")
    try:
        method = two_step.second_step(db, user, request.code)
    except two_step.Unavailable:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=two_step.CHECK_UNAVAILABLE)
    if method is None:
        _count_failure(db, email, 'wrong_second_step')
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="That code is not right, or it has been used already. Wait for the next one.")
    db.commit()
    if method == "recovery":
        activity_trail.record('recovery_code_used', db=db, commit=True, user=user,
                              details=dict(codes_left=two_step.recovery_codes_left(db, user.id)))
    return _signed_in(db, user, response, second_step=method)


@router.post("/reset-with-code")
def reset_with_code(request: ResetWithCodeRequest, db: Session = Depends(get_db)):
    """A new password from a reset code an administrator issued. Every sign-in of that person ends; two-step stays."""
    from postgres.models.user import User

    email = (request.email or "").strip()
    user = db.query(User).filter(User.email == email).first()
    row = account_recovery.live_reset_code(db, user, request.code) if user is not None and user.is_active else None
    if row is None:
        # Limited here, not before the read: a person who locked themselves out with wrong passwords is who a right
        # code is for, and about 78 random bits are not guessed by the attempts this lets through.
        _refuse_if_limited(db, email)
        _count_failure(db, email, 'wrong_reset_code')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="That reset code is not right, has expired, or has been used. Ask an administrator "
                                   "for a new one.")
    # Before the code is spent: a refused password leaves the code usable.
    password_rule.require_acceptable(request.new_password, email=user.email, name=user.name)
    if not account_recovery.spend_reset_code(db, row):
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That reset code has been used.")
    account_recovery.set_new_password(db, user, request.new_password)
    activity_trail.record('password_reset_with_code', db=db, user=user, details=dict(issued_by=row.issued_by))
    db.commit()
    password_sessions.forget(user.email)
    return {"success": True, "message": "Password set. Sign in with it."}


@router.post("/logout")
def logout(response: Response, token: str | None = Depends(_extract_token), db: Session = Depends(get_db)):
    person = None
    if token:
        try:
            person = auth_service["verify_access_token"](token)
        except Exception:
            person = None
    activity_trail.record('logout', db=db, commit=True, user_email=(person or {}).get('username'),
                          details={} if person else dict(signed_in=False))
    response.delete_cookie("access_token")
    return {"status": "ok"}


@router.get("/check", status_code=status.HTTP_204_NO_CONTENT)
def check(user: dict = Depends(get_current_user)) -> Response:
    """Whether the request is signed in: 204 or 401, no body and no database read.

    nginx asks this before serving each base-map file (/basemap/: tiles, fonts, sprites), so the map held on this
    server is behind the same sign-in as the app.
    """
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeResponse)
def me(
    response: Response,
    user: dict = Depends(get_current_user),
    token: str | None = Depends(_extract_token),
    db: Session = Depends(get_db),
):
    from postgres.models.user import User

    email = user["username"]
    db_user = db.query(User).filter(User.email == email).first()

    if not db_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Refresh the cookie so browser-loaded resources carry auth.
    if token:
        _set_access_cookie(response, token)

    return MeResponse(email=db_user.email, name=db_user.name, username=db_user.email, role=db_user.global_role.value)


@router.put("/change-password")
def change_password(
    request: ChangePasswordRequest,
    response: Response,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change password for the currently authenticated user."""
    from postgres.models.user import User
    from routers.users import hash_password

    email = user["username"]
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    _require_password(db, db_user, request.current_password, "Current password is incorrect")

    password_rule.require_acceptable(request.new_password, email=db_user.email, name=db_user.name)

    db_user.password_hash = hash_password(request.new_password)
    # Every other sign-in of this user ends; this one continues with a new token.
    password_sessions.stamp(db_user)
    activity_trail.record('password_changed', db=db, user=db_user)
    db.commit()
    password_sessions.forget(db_user.email)
    token = auth_service["create_access_token"]({"sub": db_user.email})
    _set_access_cookie(response, token)

    return {"success": True, "message": "Password updated successfully", "access_token": token}


def _account(db: Session, user: dict):
    from postgres.models.user import User
    db_user = db.query(User).filter(User.email == user["username"]).first()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return db_user


def _require_password(db: Session, account, password: str, refusal: str = "That password is not right.") -> None:
    """A signed-in browser left open is not enough to change how this account signs in, and it cannot guess its way
    there: wrong answers count in the same limit as wrong sign-ins."""
    from routers.users import verify_password
    _refuse_if_limited(db, account.email)
    if not verify_password(password, account.password_hash):
        _count_failure(db, account.email, 'wrong_current_password')
        raise HTTPException(status_code=400, detail=refusal)


def _require_code(db: Session, account, code: str) -> None:
    """An authenticator code, or a recovery code (which is then spent): someone who lost their device can still get
    new recovery codes or turn two-step off and enrol again."""
    try:
        accepted = two_step.second_step(db, account, code)
    except two_step.Unavailable:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=two_step.CHECK_UNAVAILABLE)
    if not accepted:
        _count_failure(db, account.email, 'wrong_second_step')
        raise HTTPException(status_code=400, detail="That code is not right, or it has been used already.")


@router.get("/two-step")
def two_step_status(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _account(db, user)
    row = db.get(two_step.UserTwoStep, account.id)
    enrolled = row is not None and row.confirmed_at is not None
    return {
        "enrolled": enrolled,
        "enrolled_at": row.confirmed_at.isoformat() if enrolled else None,
        "recovery_codes_left": two_step.recovery_codes_left(db, account.id) if enrolled else 0,
        "unavailable_reason": two_step.key_refusal(),
        "required": account.global_role in two_step.ADMIN_ROLES and two_step.required_for_admins(),
    }


@router.post("/two-step/start")
def two_step_start(request: PasswordOnly, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _account(db, user)
    reason = two_step.key_refusal()
    if reason:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=reason)
    _require_password(db, account, request.password)
    if two_step.is_enrolled(db, account.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-step sign-in is already on.")
    started = two_step.begin(db, account)
    db.commit()
    return _no_store(started)


@router.post("/two-step/confirm")
def two_step_confirm(request: CodeOnly, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _account(db, user)
    # Not in the sign-in limit: whoever is here already holds the secret, so there is nothing to guess, and a phone with
    # a wrong clock must not lock its owner out of signing in.
    try:
        codes = two_step.confirm(db, account, request.code)
    except two_step.Unavailable:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=two_step.CHECK_UNAVAILABLE)
    if codes is None:
        db.rollback()
        raise HTTPException(status_code=400, detail="That code is not right. Check the time on your device and try the next one.")
    activity_trail.record('two_step_enrolled', db=db, user=account)
    db.commit()
    return _no_store({"recovery_codes": codes})


@router.post("/two-step/recovery-codes")
def two_step_new_recovery_codes(request: PasswordAndCode, user: dict = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    account = _account(db, user)
    _require_password(db, account, request.password)
    _require_code(db, account, request.code)
    codes = two_step.replace_recovery_codes(db, account.id)
    activity_trail.record('recovery_codes_replaced', db=db, user=account)
    db.commit()
    return _no_store({"recovery_codes": codes})


@router.post("/two-step/turn-off")
def two_step_turn_off(request: PasswordAndCode, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    account = _account(db, user)
    if account.global_role in two_step.ADMIN_ROLES and two_step.required_for_admins():
        raise HTTPException(status_code=403, detail="Administrators must keep two-step sign-in on this server.")
    _require_password(db, account, request.password)
    _require_code(db, account, request.code)
    two_step.remove(db, account.id)
    activity_trail.record('two_step_turned_off', db=db, user=account)
    db.commit()
    return {"success": True}
