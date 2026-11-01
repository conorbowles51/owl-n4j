"""Phone reports of a case, and Replace / Retire (docs/cellebrite/01-intake-capture-storage.md section 10.7).

Replace never deletes. The newer report must be read in full (``captured`` or ``captured_incomplete``) and active;
the older one must be active in the same case. One transaction locks both rows, records the typed reason in the
case decision ledger against the older report, marks it superseded and points the newer one at it. The older
report's records stay readable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.phone_extraction import CAPTURED_STATES, PhoneExtraction, PhoneExtractionContainer, PhoneTimestamp
from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user
from services import activity_trail
from services.financial import decisions
from services.financial.quarantine_row import ActorError, actor_from_user

router = APIRouter(prefix="/api/phone-extractions", tags=["phone-extractions"])

REASON_REQUIRED = "Type the reason for replacing this report."
NOT_READ_IN_FULL = "The newer report has not been read in full yet. Replace it once it is ready."
NOT_ACTIVE = "Only a report the case currently stands on can be replaced."
SAME_REPORT = "A report cannot replace itself."
OTHER_CASE = "Both reports must belong to the same case."
EXTRACTION_START = "DeviceInfoExtractionStartDateTime"


class Supersede(BaseModel):
    previous_id: UUID
    reason: str = Field(..., max_length=4000)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _extracted(db: Session, ids: list[UUID]) -> dict[UUID, tuple]:
    """Earliest and latest extraction start the report itself states (skeleton timestamps with an instant)."""
    if not ids:
        return {}
    rows = db.execute(select(PhoneTimestamp.extraction_id, func.min(PhoneTimestamp.instant), func.max(PhoneTimestamp.instant))
                      .where(PhoneTimestamp.extraction_id.in_(ids), PhoneTimestamp.owner_kind == "skeleton",
                             PhoneTimestamp.field_name == EXTRACTION_START, PhoneTimestamp.instant.is_not(None))
                      .group_by(PhoneTimestamp.extraction_id))
    return {r[0]: (r[1], r[2]) for r in rows}


def describe(db: Session, extractions: list[PhoneExtraction]) -> list[dict]:
    ids = [e.id for e in extractions]
    names = dict(db.execute(select(PhoneExtractionContainer.id, PhoneExtractionContainer.original_name)
                            .where(PhoneExtractionContainer.id.in_([e.first_container_id for e in extractions]))).all()) if ids else {}
    extracted = _extracted(db, ids)
    people = {}
    users = {e.superseded_by_user_id for e in extractions if e.superseded_by_user_id}
    if users:
        people = {u.id: (u.name or u.email) for u in db.scalars(select(User).where(User.id.in_(users)))}
    label = {e.id: names.get(e.first_container_id) or "Phone report" for e in extractions}
    out = []
    for e in extractions:
        first, last = extracted.get(e.id, (None, None))
        flags = e.flags or {}
        out.append(dict(
            id=str(e.id), case_id=str(e.case_id), label=label[e.id], standing=e.standing, capture_state=e.capture_state,
            form=e.form, extraction_type=e.extraction_type, producer_version=e.producer_version,
            record_count=e.record_count, file_count=e.file_count, created_at=_iso(e.created_at),
            captured_at=_iso(e.captured_at), extracted_from=_iso(first), extracted_to=_iso(last),
            supersedes_id=str(e.supersedes_id) if e.supersedes_id else None,
            superseded_at=_iso(e.superseded_at), superseded_reason=e.superseded_reason,
            superseded_by=people.get(e.superseded_by_user_id),
            replaced_by_id=next((str(o.id) for o in extractions if o.supersedes_id == e.id), None),
            possible_same_device=[dict(extraction_id=str(p.get("extraction_id")), name=p.get("name"))
                                  for p in flags.get("possible_same_device") or []],
        ))
    return out


@router.get("")
def list_phone_extractions(case_id: UUID = Query(...), user: User = Depends(get_current_db_user),
                           db: Session = Depends(get_db)):
    authorize_case(db, case_id, user, ("case", "view"))
    rows = list(db.scalars(select(PhoneExtraction).where(PhoneExtraction.case_id == case_id)
                           .order_by(PhoneExtraction.created_at, PhoneExtraction.id)))
    return describe(db, rows)


@router.post("/{new_id}/supersede")
def supersede(new_id: UUID, body: Supersede, user: User = Depends(get_current_db_user), db: Session = Depends(get_db)):
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(422, REASON_REQUIRED)
    if body.previous_id == new_id:
        raise HTTPException(409, SAME_REPORT)
    probe = db.get(PhoneExtraction, new_id)
    if probe is None:
        raise HTTPException(404, "Phone report not found")
    authorize_case(db, probe.case_id, user, ("evidence", "upload"))
    try:
        actor = actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Both rows locked in one order, so two Replace requests over the same pair cannot interleave.
    locked = {e.id: e for e in db.scalars(select(PhoneExtraction).where(PhoneExtraction.id.in_([new_id, body.previous_id]))
                                           .order_by(PhoneExtraction.id).with_for_update().execution_options(populate_existing=True))}
    new, previous = locked.get(new_id), locked.get(body.previous_id)
    if new is None or previous is None:
        raise HTTPException(404, "Phone report not found")
    if previous.case_id != new.case_id:
        raise HTTPException(409, OTHER_CASE)
    if new.capture_state not in CAPTURED_STATES:
        raise HTTPException(409, NOT_READ_IN_FULL)
    if new.standing != "active" or previous.standing != "active":
        raise HTTPException(409, NOT_ACTIVE)
    now = datetime.now(timezone.utc)
    decisions.record(db, case_id=previous.case_id, subject=previous, subject_type=AdjudicationSubject.phone_extraction,
                     decision=AdjudicationDecision.supersede_phone_extraction, reason=reason, actor=actor,
                     before={"standing": "active", "replaced_by": None},
                     after={"standing": "superseded", "replaced_by": str(new.id)})
    previous.standing = "superseded"
    previous.superseded_at = now
    previous.superseded_by_user_id = user.id
    previous.superseded_reason = reason
    new.supersedes_id = previous.id
    activity_trail.record("phone_extraction_superseded", db=db, user=user, case_id=previous.case_id,
                          details={"replaced": str(previous.id), "by": str(new.id)})
    db.commit()
    return describe(db, [previous, new])
