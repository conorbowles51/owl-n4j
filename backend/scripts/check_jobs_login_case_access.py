"""Read-only check: which cases may the jobs login change?

07 section 12.1 item I: the jobs login may change only the verification case and the two
synthetic cases, through Loupe's own case-access mechanism. This evaluates the same
``check_case_access(..., ("case", "edit"))`` that every case write route uses, against the
live database, without writing anything. Output is counts and case ids of allowed cases only
(no titles: case names are case material).

Usage (from backend/): python scripts/check_jobs_login_case_access.py jobs-verify@loupe.invalid
Exit 0 when the allowed set equals ALLOWED exactly, 1 otherwise.
"""
from __future__ import annotations

import sys

ALLOWED = {
    "cded78d0-e659-44cc-940d-d8f8c8012760",  # Verification (automated checks)
    "4aa79795-1076-4c75-985f-784936abb71f",  # Phones-only check (synthetic)
    "6587637c-0dff-45fa-8852-a6e4f7131c0c",  # Phone training (synthetic)
}


def evaluate(db, email: str) -> tuple[set[str], int]:
    from postgres.models.case import Case
    from postgres.models.user import User
    from services.case_service import CaseAccessDenied, check_case_access

    user = db.query(User).filter(User.email == email).one()
    can_edit: set[str] = set()
    total = 0
    for (case_id,) in db.query(Case.id).all():
        total += 1
        try:
            check_case_access(db, case_id, user, required_permission=("case", "edit"))
        except CaseAccessDenied:
            continue
        can_edit.add(str(case_id))
    return can_edit, total


def main(argv: list[str]) -> int:
    from postgres.session import _get_session_local

    db = _get_session_local()()
    try:
        can_edit, total = evaluate(db, argv[1])
        db.rollback()
    finally:
        db.close()
    unexpected = sorted(can_edit - ALLOWED)
    missing = sorted(ALLOWED - can_edit)
    print(f"cases={total} can_edit={len(can_edit)} refused={total - len(can_edit)}")
    print(f"unexpected_edit={unexpected} missing_edit={missing}")
    return 0 if not unexpected and not missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
