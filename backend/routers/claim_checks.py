"""Claims ingestion left unchecked, prefix ``/api/claim-checks`` (lx-citeproof D).

Ingestion checks each claim it draws from a file (a fact about a person, a link between two) against the file's text
before the claim enters the graph. Claims left unchecked (before 15 Nov 2026 a file stopped at 250; now only the case's
AI spending limit stops it) stay out of the graph. Anyone who can view the case sees how many; anyone who can edit it
can ask for them to be checked, which spends from the case's AI budget.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services import ai_budget

router = APIRouter(prefix="/api/claim-checks", tags=["claim-checks"])


def unchecked_counts(db: Session, case_id: UUID) -> dict:
    if not inspect(db.connection()).has_table("evidence_claims"):
        return {"case_id": str(case_id), "unchecked": 0, "files": []}
    rows = db.execute(text(
        "SELECT c.evidence_file_id, f.original_filename, count(*) AS n FROM evidence_claims c LEFT JOIN "
        "evidence_files f ON f.id = c.evidence_file_id WHERE c.case_id = %s AND c.status = 'unreviewed' "
        "GROUP BY 1, 2 ORDER BY 3, 2" % ("CAST(:c AS uuid)" if db.get_bind().dialect.name == "postgresql" else ":c")),
        {"c": str(case_id)}).all()
    files = [{"evidence_file_id": str(UUID(str(r[0]))), "filename": r[1], "unchecked": int(r[2])} for r in rows]
    return {"case_id": str(case_id), "unchecked": sum(f["unchecked"] for f in files), "files": files}


@router.get("/{case_id}")
def counts(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    return unchecked_counts(db, case_id)


@router.post("/{case_id}/check")
async def check(case_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    from starlette.concurrency import run_in_threadpool

    def allowed():  # database work off the event loop
        authorize_case(db, case_id, user, ("case", "edit"))
        try:
            ai_budget.check(db, case_id, "this claim check")
        except ai_budget.BudgetRefused as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    await run_in_threadpool(allowed)
    from services import evidence_engine_client
    try:
        answer = await evidence_engine_client.check_unreviewed_claims(str(case_id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="The claim check could not be started. Try again later.") from exc
    return {"case_id": str(case_id), "queued": bool(answer.get("queued")),
            "message": ("Checking started: each claim is read against its file, and the count above goes down as "
                        "they are done. Checked claims are not yet added to the graph.") if answer.get("queued") else
                       "A claim check of this case is already running."}
