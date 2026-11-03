"""Citation check, prefix ``/api/citations``: what each doc://, txn:// and rec:// link names in a case.

Anyone who can view the case. One request checks every link of an answer, report section or summary, so a link
whose target is not in the case renders as "not in this case" and a filename several files share offers a choice.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services import case_citations as C

router = APIRouter(prefix="/api/citations", tags=["citations"])

MAX_HREFS = 500


class ResolveRequest(BaseModel):
    case_id: UUID
    hrefs: list[str] = Field(default_factory=list, max_length=MAX_HREFS)


@router.post("/resolve")
def resolve(body: ResolveRequest, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "view"))
    parsed, unknown = [], []
    for href in dict.fromkeys(h for h in body.hrefs if isinstance(h, str) and len(h) <= 2048):
        citation = C.parse_citation(href)
        (parsed.append(citation) if citation else unknown.append(href))
    try:
        resolved = C.resolve_citations(db, body.case_id, parsed)
    except Exception as exc:  # noqa: BLE001 - the reader is told, never shown a link that may be wrong
        raise HTTPException(status_code=500, detail="The citations could not be checked against this case.") from exc
    return {"case_id": str(body.case_id), "items": [r.to_json() for r in resolved],
            "not_citations": unknown}
