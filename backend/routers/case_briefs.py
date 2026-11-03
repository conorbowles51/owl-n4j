"""Case briefs API, prefix ``/api/case-briefs`` (services/agent/briefs.py).

Viewing needs case view. Asking for a brief now needs case edit; it is written by the host sweep within a minute (the
request is marked as already waited for), never inside the web request. A brief of another case is 404.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services.agent import briefs as B

router = APIRouter(prefix="/api/case-briefs", tags=["case-briefs"])


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


@router.get("/latest")
def latest(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The newest brief with ``out_of_date`` against the case's newest evidence, and whether one is being prepared."""
    authorize_case(db, case_id, user, ("case", "view"))
    conn = db.connection()
    pending = conn.execute(text("SELECT last_requested_at FROM case_brief_requests WHERE case_id = :c"),
                           {"c": str(case_id)}).scalar()
    return {"brief": B.latest(conn, case_id), "requested_at": B._iso(pending)}


@router.get("")
def history(case_id: UUID = Query(...), offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
            db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    return B.history(db.connection(), case_id, offset=offset, limit=limit)


@router.post("/run", status_code=202)
def run(body: RunBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    db.execute(text(
        "INSERT INTO case_brief_requests (case_id, first_requested_at, last_requested_at, reason) VALUES (:c, "
        "now() - make_interval(secs => :d), now() - make_interval(secs => :q), 'asked') ON CONFLICT (case_id) DO "
        "UPDATE SET first_requested_at = now() - make_interval(secs => :d), last_requested_at = now() - "
        "make_interval(secs => :q), reason = 'asked'"),
        {"c": str(body.case_id), "d": B.MAX_DEFER_SECONDS, "q": B.QUIET_SECONDS})
    db.commit()
    return {"requested": True, "sentence": "A new brief is being prepared; it appears here within a minute or two."}
