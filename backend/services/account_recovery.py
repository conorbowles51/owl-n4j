"""Account recovery with no email: one-time, expiring reset codes, and the commands for the box.

An administrator issues a reset code in the user screen and gives it to the person by a channel they trust; the box
command does the same for an administrator nobody else can reach. The code sets a new password and nothing else: a
person with two-step sign-in still needs their second step, unless it is removed separately. A reset by email waits
for the app to have a mail sender.

    python -m services.account_recovery reset <email> [--remove-two-step]
    python -m services.account_recovery require --check | --on | --off
    python -m services.account_recovery rekey

Run through deploy/account-recovery.sh on the box. A code is printed only to the person at the terminal.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

import config
import secret_check
from postgres.models.activity_event import ActivityEvent
from postgres.models.two_step import AccountResetCode, LoginPolicy
from postgres.models.user import User
from services import activity_trail, password_sessions, two_step

RESET_CODE_LIFETIME = timedelta(hours=1)
BOX = "box command"
SCRIPT_SIGN_IN_DAYS = 30


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def issue_reset_code(db: Session, user, issued_by: str, now: datetime | None = None) -> tuple[str, datetime]:
    """A new code for ``user``; an earlier unused one stops working. The caller records it and commits."""
    now = now or datetime.now(timezone.utc)
    db.execute(update(AccountResetCode).where(
        AccountResetCode.user_id == user.id, AccountResetCode.used_at.is_(None), AccountResetCode.revoked_at.is_(None),
    ).values(revoked_at=now).execution_options(synchronize_session=False))
    code = two_step.new_code()
    expires = now + RESET_CODE_LIFETIME
    db.add(AccountResetCode(user_id=user.id, code_hash=two_step.code_hash(user.id, code), issued_by=issued_by[:255],
                            expires_at=expires))
    return code, expires


def live_reset_code(db: Session, user, code: str, now: datetime | None = None) -> AccountResetCode | None:
    now = now or datetime.now(timezone.utc)
    row = db.execute(select(AccountResetCode).where(
        AccountResetCode.user_id == user.id, AccountResetCode.code_hash == two_step.code_hash(user.id, code),
        AccountResetCode.used_at.is_(None), AccountResetCode.revoked_at.is_(None),
    )).scalars().first()
    return row if row is not None and _aware(row.expires_at) > now else None


def spend_reset_code(db: Session, row: AccountResetCode, now: datetime | None = None) -> bool:
    """True for the one request that uses this code."""
    now = now or datetime.now(timezone.utc)
    return db.execute(update(AccountResetCode).where(
        AccountResetCode.id == row.id, AccountResetCode.used_at.is_(None), AccountResetCode.revoked_at.is_(None),
    ).values(used_at=now).execution_options(synchronize_session=False)).rowcount == 1


def set_new_password(db: Session, user, password: str) -> None:
    """Every sign-in of this user ends. The caller commits, then calls password_sessions.forget(user.email)."""
    from routers.users import hash_password
    user.password_hash = hash_password(password)
    password_sessions.stamp(user)


def _active_admins(db: Session) -> list[User]:
    return list(db.execute(select(User).where(User.global_role.in_(two_step.ADMIN_ROLES), User.is_active.is_(True))
                           .order_by(User.email)).scalars())


def readiness(db: Session) -> tuple[list[dict], list[str]]:
    """Each active administrator's state, and what refuses the switch (empty: it may go on)."""
    people = [{"email": user.email, "role": user.global_role.value, "enrolled": two_step.is_enrolled(db, user.id),
               "recovery_codes_left": two_step.recovery_codes_left(db, user.id)} for user in _active_admins(db)]
    refusals = [line for line in (secret_check.problem("AUTH_SECRET_KEY", config.AUTH_SECRET_KEY),
                                  secret_check.problem("MFA_ENCRYPTION_KEY", config.MFA_ENCRYPTION_KEY)) if line]
    if not people:
        refusals.append("there is no active administrator")
    refusals += [f"{person['email']} has not enrolled" for person in people if not person["enrolled"]]
    refusals += [f"{person['email']} has no recovery code left" for person in people
                 if person["enrolled"] and not person["recovery_codes_left"]]
    return people, refusals


def script_sign_ins(db: Session, now: datetime | None = None) -> list[tuple[str, str, int]]:
    """Administrators' sign-ins from something other than a browser in the last SCRIPT_SIGN_IN_DAYS days, as
    (email, client, count). Once one of them enrols, that script needs a person for the second step."""
    now = now or datetime.now(timezone.utc)
    admins = {user.email.lower() for user in _active_admins(db)}
    rows = db.execute(select(ActivityEvent.user_email, ActivityEvent.user_agent).where(
        ActivityEvent.action == "login_success", ActivityEvent.at >= now - timedelta(days=SCRIPT_SIGN_IN_DAYS))).all()
    counts: dict[tuple[str, str], int] = {}
    for email, agent in rows:
        if (email or "").lower() in admins and "Mozilla/" not in (agent or ""):
            key = (email, (agent or "no client named")[:60])
            counts[key] = counts.get(key, 0) + 1
    return [(email, agent, count) for (email, agent), count in sorted(counts.items())]


def set_requirement(db: Session, on: bool, changed_by: str, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    row = db.get(LoginPolicy, 1)
    if row is None:
        row = LoginPolicy(id=1)
        db.add(row)
    row.require_two_step_for_admins, row.changed_by, row.changed_at = on, changed_by, now
    activity_trail.record("two_step_requirement_changed", db=db, system=True, user_email=changed_by,
                          details=dict(required=on))
    db.commit()
    two_step.forget_policy()


def _reset(db: Session, email: str, remove_two_step: bool) -> int:
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    if user is None:
        print(f"No account for {email}.", file=sys.stderr)
        return 2
    if user.global_role not in two_step.ADMIN_ROLES:
        print("This command is for administrators. Anyone else gets a code from an administrator in the app.",
              file=sys.stderr)
        return 2
    if not user.is_active:
        print(f"{email} is deactivated; a reset code would not let them sign in.", file=sys.stderr)
        return 2
    code, expires = issue_reset_code(db, user, BOX)
    if remove_two_step:
        two_step.remove(db, user.id)
        activity_trail.record("two_step_removed", db=db, system=True, user_email=BOX, details=dict(person=user.email))
    activity_trail.record("reset_code_issued", db=db, system=True, user_email=BOX,
                          details=dict(person=user.email, expires_at=expires.isoformat()))
    db.commit()
    print(f"Reset code for {email}, usable once until {expires:%H:%M} UTC on {expires:%d %b}:\n\n    {code}\n")
    print("On the sign-in page choose 'I have a reset code'. Nothing is sent to them: pass it on yourself.")
    if not remove_two_step and two_step.is_enrolled(db, user.id):
        print("They keep two-step sign-in. If they lost that too, run this again with --remove-two-step.")
    return 0


def _require(db: Session, mode: str) -> int:
    people, refusals = readiness(db)
    row = db.get(LoginPolicy, 1)
    print(f"Required now: {'yes' if row and row.require_two_step_for_admins else 'no'}")
    for person in people:
        state = f"enrolled, {person['recovery_codes_left']} recovery codes left" if person["enrolled"] else "NOT enrolled"
        print(f"  {person['email']} ({person['role']}): {state}")
    scripts = script_sign_ins(db)
    print(f"Sign-ins by administrators from scripts, last {SCRIPT_SIGN_IN_DAYS} days: {len(scripts)}")
    for email, agent, count in scripts:
        print(f"  {email}: {count} from {agent}")
    print("Accounts that are not administrators, the shared jobs login among them, are not affected.")
    if mode == "off":
        set_requirement(db, False, BOX)
        print("Requirement is off.")
        return 0
    if refusals:
        print("Cannot turn on: " + "; ".join(refusals) + ".")
        return 1 if mode == "on" else 0
    if mode == "check":
        print("Ready: every administrator is enrolled and holds recovery codes.")
        return 0
    set_requirement(db, True, BOX)
    print("Requirement is on, within 30 seconds on every worker.")
    return 0


def _session_factory():
    from postgres.session import _get_session_local
    return _get_session_local()


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Account recovery on the box.")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset", help="a reset code for an administrator nobody else can help")
    reset.add_argument("email")
    reset.add_argument("--remove-two-step", action="store_true")
    require = commands.add_parser("require", help="whether administrators must use two-step sign-in")
    mode = require.add_mutually_exclusive_group(required=True)
    for name in ("check", "on", "off"):
        mode.add_argument(f"--{name}", dest="mode", action="store_const", const=name)
    commands.add_parser("rekey", help="move stored authenticator secrets to MFA_ENCRYPTION_KEY")
    options = parser.parse_args(arguments)
    with _session_factory()() as db:
        if options.command == "reset":
            return _reset(db, options.email, options.remove_two_step)
        if options.command == "require":
            return _require(db, options.mode)
        moved = two_step.rekey(db)
        db.commit()
        print(f"Moved {moved} stored secrets to the current key.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
