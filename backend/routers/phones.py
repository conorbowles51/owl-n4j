"""Phone interpretation API, prefix ``/api/phones`` (02; placement fixed by 03 section 4.1).

Registry review queue (02 section 3.4): admin only, because the registry is global. Coverage map (02 section 7)
and the readings queue (02 sections 6.8, 6.10): anyone who can view the case; deciding needs case edit.
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user, require_admin
from services.financial.quarantine_row import ActorError, actor_from_user
from services.phone import coverage, identities, identity_decisions, readings, registry

router = APIRouter(prefix="/api/phones", tags=["phones"])

FlagState = Literal["open", "acknowledged", "mapping_needed", "mapped", "dismissed"]


class FlagTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: Literal["open", "acknowledged", "mapping_needed", "dismissed"]
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/registry/flags")
def list_registry_flags(state: Optional[FlagState] = None, db: Session = Depends(get_db),
                        _: User = Depends(require_admin)):
    flags = registry.list_flags(db, state)
    return {"total": len(flags), "flags": [dict(f, raised_at=f["raised_at"].isoformat(),
                                                raised_by_extraction_id=(str(f["raised_by_extraction_id"])
                                                                         if f["raised_by_extraction_id"] else None))
                                           for f in flags]}


@router.post("/registry/flags/{flag_id}/transition")
def transition_registry_flag(flag_id: int, body: FlagTransition, db: Session = Depends(get_db),
                             user: User = Depends(require_admin)):
    try:
        out = registry.transition_flag(db, flag_id, body.to, body.reason, actor_name=user.name,
                                       actor_email=user.email, actor_user_id=user.id)
    except registry.TransitionRefused as exc:
        db.rollback()
        raise HTTPException(status_code=409 if "cannot become" in str(exc) else 422, detail=str(exc))
    db.commit()
    return out


@router.get("/{extraction_id}/coverage")
def extraction_coverage(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                        user: User = Depends(get_current_db_user)):
    """What Loupe reads of one phone, per type and field, beside the production's own selection statement."""
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return coverage.compute(db.connection(), extraction_id, case_id)
    except coverage.NotFound:
        raise HTTPException(status_code=404, detail="Phone extraction not found in this case")


class ConfirmReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    viewed: list[str] = Field(default_factory=list, max_length=200)
    opened: Optional[list[str]] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=4000)
    expected_status: Literal["open", "confirmed", "corrected"] = "open"


class CorrectReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    choice: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=4000)
    scope: Literal["this_phone", "same_format"] = "this_phone"
    note: Optional[str] = Field(default=None, max_length=4000)
    expected_status: Literal["open", "confirmed", "corrected"] = "open"


def _actor(user):
    try:
        return actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _reading_error(db, exc):
    db.rollback()
    raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/readings")
def list_readings(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The system's readings of the case's phones as plain sentences, most records first (07 J-8)."""
    authorize_case(db, case_id, user, ("case", "view"))
    return readings.queue(db.connection(), case_id)


@router.get("/readings/progress")
def readings_progress(case_id: UUID = Query(...), db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    return {"phones": readings.progress(db.connection(), case_id)}


@router.get("/readings/{judgement_id}/examples")
def reading_examples(judgement_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return readings.examples(db.connection(), case_id, judgement_id)
    except readings.ReadingError as exc:
        _reading_error(db, exc)


@router.post("/readings/{judgement_id}/confirm")
def confirm_reading(judgement_id: UUID, body: ConfirmReading, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = readings.confirm(db, body.case_id, judgement_id, viewed=body.viewed, opened=body.opened,
                               note=body.note, actor=_actor(user), expected_status=body.expected_status)
    except readings.ReadingError as exc:
        _reading_error(db, exc)
    db.commit()
    return out


@router.post("/readings/{judgement_id}/correct")
def correct_reading(judgement_id: UUID, body: CorrectReading, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = readings.correct(db, body.case_id, judgement_id, choice_id=body.choice, reason=body.reason,
                               scope=body.scope, note=body.note, actor=_actor(user),
                               expected_status=body.expected_status)
    except readings.ReadingError as exc:
        _reading_error(db, exc)
    db.commit()
    return out


class IdentityDecision(BaseModel):
    """02 section 8.8 endpoint (spec 03 section 10.4)."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    decision: Literal["link_phone_identity", "unlink_phone_identity", "split", "reject_phone_identity_link",
                      "restore_phone_identity_link"]
    identity_keys: list[str] = Field(min_length=1, max_length=500)
    dossier_id: Optional[UUID] = None
    new_person_name: Optional[str] = Field(default=None, max_length=255)
    target_identity_key: Optional[str] = Field(default=None, max_length=600)
    reason: Optional[str] = Field(default=None, max_length=4000)
    note: Optional[str] = Field(default=None, max_length=4000)
    reasons_shown: Optional[list[dict]] = Field(default=None, max_length=20)
    expected_revision: Optional[str] = Field(default=None, max_length=64)


@router.get("/identity-suggestions")
def identity_suggestions(case_id: UUID = Query(...), db: Session = Depends(get_db),
                         user: User = Depends(get_current_db_user)):
    """Suggested links, recomputed from the current sightings, links and dossier contacts (8.7)."""
    authorize_case(db, case_id, user, ("case", "view"))
    conn = db.connection()
    identity_decisions.compute_suggestions(conn, case_id)
    out = identity_decisions.suggestions(conn, case_id)
    db.commit()
    return {"case_id": str(case_id), "total": len(out), "suggestions": out}


@router.get("/identities/{identity_key:path}")
def identity_detail(identity_key: str, case_id: UUID = Query(...), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """One identity: its value, each phone's names, its link and the revision a decision must name."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    conn = db.connection()
    row = conn.execute(sql("SELECT id, identity_key, kind, subkind, value_display, sighting_count, phone_count FROM "
                           "phone_identities WHERE case_id = :c AND identity_key = :k"),
                       {"c": case_id, "k": identity_key}).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="This identity is not in this case")
    labels = readings.phone_labels(conn, case_id)
    names = [{"phone": labels.get(str(n.extraction_id)), "name": n.name, "basis": n.basis,
              "occurrences": n.occurrences, "is_phone_name": n.is_phone_name}
             for n in conn.execute(sql("SELECT extraction_id, name, basis, occurrences, is_phone_name FROM "
                                       "pv_identity_name WHERE identity_id = :i ORDER BY is_phone_name DESC, "
                                       "occurrences DESC, name"), {"i": row.id})]
    link = conn.execute(sql("SELECT l.dossier_id, p.display_name FROM phone_identity_links l LEFT JOIN case_profiles p "
                            "ON p.id = l.dossier_id WHERE l.identity_id = :i"), {"i": row.id}).one_or_none()
    return {"id": str(row.id), "identity_key": row.identity_key, "kind": row.kind, "subkind": row.subkind,
            "value_display": row.value_display, "sightings": row.sighting_count, "phones": row.phone_count,
            "names": names, "linked_dossier": {"id": str(link[0]), "name": link[1]} if link else None,
            "can_be_a_person": not (row.kind == "other" and row.subkind == "group"),
            "expected_revision": identity_decisions.links_revision(conn, [row.id])}


@router.post("/identity-decisions")
def identity_decision(body: IdentityDecision, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = identity_decisions.decide(
            db, case_id=body.case_id, decision=body.decision, identity_keys=body.identity_keys, actor=_actor(user),
            user=user, dossier_id=body.dossier_id, new_person_name=body.new_person_name, reason=body.reason,
            note=body.note, reasons_shown=body.reasons_shown, expected_revision=body.expected_revision,
            target_identity_key=body.target_identity_key)
    except identity_decisions.IdentityDecisionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return out


@router.get("/{extraction_id}/owner")
def extraction_owner(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    """The owner of one phone: computed with every candidate, and a person's decision when there is one (8.6)."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    if not db.connection().execute(sql("SELECT 1 FROM phone_extractions WHERE id = :e AND case_id = :c"),
                                   {"e": extraction_id, "c": case_id}).scalar():
        raise HTTPException(status_code=404, detail="Phone extraction not found in this case")
    out = identities.owner(db.connection(), extraction_id)
    for cnd in out["candidates"]:
        cnd["identity_id"] = str(cnd["identity_id"]) if cnd["identity_id"] else None
    return out
