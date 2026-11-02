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
from routers.users import get_current_db_user, require_admin, require_super_admin
from services.financial.quarantine_row import ActorError, actor_from_user
from services.phone import corrections, coverage, external_processing, identities, identity_decisions, readings, registry

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


class ExternalProcessingDecision(BaseModel):
    """02 sections 8.8, 9.8: embeddings, transcription, translation, image search and geocoding of one phone."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    allow: bool
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/{extraction_id}/external-processing")
def get_external_processing(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                            user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    return external_processing.state(db.connection(), case_id, extraction_id)


@router.post("/{extraction_id}/external-processing")
def set_external_processing(extraction_id: UUID, body: ExternalProcessingDecision, db: Session = Depends(get_db),
                            user: User = Depends(require_super_admin)):
    """Sending a phone's material to a third-party service is decided by the system owner for a case (9.8)."""
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        out = external_processing.decide(db, case_id=body.case_id, extraction_id=extraction_id, allow=body.allow,
                                         reason=body.reason, actor=_actor(user))
    except external_processing.ExternalProcessingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    db.commit()
    return out


class ProjectionRebuild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


@router.post("/projection/rebuild")
def rebuild_projection(body: ProjectionRebuild, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Rebuild the case graph's phone layer from Postgres now (02 section 9.5)."""
    authorize_case(db, body.case_id, user, ("case", "edit"))  # derived data only; anyone who can edit the case
    from postgres.session import _get_engine
    from services.phone import graph_projection
    out = graph_projection.project_case(_get_engine(), body.case_id)
    return {"case_id": str(body.case_id), **{k: v for k, v in out.items()}}


class ValueCorrection(BaseModel):
    """02 section 10.4: one captured value, corrected with the person's own reason; the original stays visible."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    field_path: str = Field(min_length=1, max_length=400)
    value_index: int = Field(default=0, ge=0)
    corrected_text: str = Field(max_length=200000)
    reason: str = Field(min_length=1, max_length=4000)
    expected_revision: Optional[str] = Field(default=None, max_length=64)


def _correction_error(db, exc):
    db.rollback()
    raise HTTPException(status_code=exc.status, detail=str(exc))


@router.post("/records/{record_uid}/corrections")
def correct_value(record_uid: UUID, body: ValueCorrection, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.correct_value(db, case_id=body.case_id, record_uid=record_uid, field_path=body.field_path,
                                        value_index=body.value_index, corrected_text=body.corrected_text,
                                        reason=body.reason, actor=_actor(user),
                                        expected_revision=body.expected_revision)
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    return out


@router.get("/records/{record_uid}/corrections")
def value_corrections(record_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    """Every correction of a record's values, oldest first: the machine value, each correction, who and why."""
    authorize_case(db, case_id, user, ("case", "view"))
    rows = [c for c in corrections.chain(db.connection(), record_uid)]
    from sqlalchemy import text as sql
    if rows and not db.connection().execute(sql("SELECT 1 FROM phone_value_corrections WHERE record_uid = :r AND "
                                                "case_id = :c LIMIT 1"), {"r": record_uid, "c": case_id}).scalar():
        raise HTTPException(status_code=404, detail="This record is not in this case")
    return {"record_uid": str(record_uid), "corrections": rows}


class ClockOffset(BaseModel):
    """02 section 10.1: the device clock was off by ``offset_seconds`` (added to the recorded time) in a period."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    offset_seconds: int
    start: Optional[str] = Field(default=None, max_length=64)
    end: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/{extraction_id}/clock-offset")
def set_clock_offset(extraction_id: UUID, body: ClockOffset, db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.set_clock_offset(db, case_id=body.case_id, extraction_id=extraction_id,
                                           offset_seconds=body.offset_seconds, start=body.start, end=body.end,
                                           reason=body.reason, actor=_actor(user))
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    return out


# ---- screens: phone list, settings, streams, threads, record panel (03 sections 4 to 6) ----------------------------

import logging as _logging  # noqa: E402
import uuid as _uuid  # noqa: E402

from pydantic import ValidationError  # noqa: E402

from services.phone import records as phone_records  # noqa: E402
from services.phone import streams  # noqa: E402
from services.phone import time_display  # noqa: E402
from services.phone.filters import StreamFilter  # noqa: E402

_log = _logging.getLogger(__name__)
LIST_FAILED = "The message list could not be loaded."


def _failure(message: str, exc: Exception) -> HTTPException:
    """3.8: an unexpected failure says what failed and gives a reference to quote, never 'unknown error'."""
    ref = _uuid.uuid4().hex[:10]
    _log.exception("phone screen request failed, reference %s", ref, exc_info=exc)
    return HTTPException(status_code=500, detail={"message": message, "reference": ref,
                                                  "text": "%s Reference: %s." % (message, ref)})


def _filter(body: dict, db, user, permission=("case", "view")) -> StreamFilter:
    try:
        f = StreamFilter.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()])
    authorize_case(db, UUID(f.case_id), user, permission)
    return f


@router.get("")
def list_phones(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """``{"phones": [PhoneSummary]}`` (03 section 4.4). An empty list means the case has no phone; the sidebar's
    Phones group shows only when it is not empty (5.2)."""
    authorize_case(db, case_id, user, ("case", "view"))
    out = phone_records.phones(db.connection(), case_id)
    return {"case_id": str(case_id), "phones": out, "total": len(out),
            "case_zone": streams.case_zone(db.connection(), case_id)}


class DisplaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    time_zone: str = Field(min_length=1, max_length=64)


@router.get("/settings")
def get_settings(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The case time zone for phone data (4.6): the setting if one is saved, else the default and why."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    row = db.connection().execute(sql(
        "SELECT s.time_zone, s.updated_at, u.name FROM case_display_settings s LEFT JOIN users u ON u.id = s.updated_by "
        "WHERE s.case_id = :c"), {"c": case_id}).first()
    zone = streams.case_zone(db.connection(), case_id)
    return {"case_id": str(case_id), "time_zone": row.time_zone if row else None, "effective": zone,
            "updated_at": time_display.iso(row.updated_at) if row else None, "updated_by": row.name if row else None}


@router.put("/settings")
def put_settings(body: DisplaySettings, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Save the case time zone; the change is written to the audit log with the old and new values (4.6)."""
    authorize_case(db, body.case_id, user, ("case", "edit"))
    if not time_display.valid_zone(body.time_zone):
        raise HTTPException(status_code=422, detail="Not a time zone name Loupe knows (for example America/New_York).")
    from sqlalchemy import text as sql
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    old = conn.execute(sql("SELECT time_zone FROM case_display_settings WHERE case_id = :c"),
                       {"c": body.case_id}).scalar()
    conn.execute(sql(
        "INSERT INTO case_display_settings (case_id, time_zone, updated_by, updated_at) VALUES (:c, :z, :u, now()) "
        "ON CONFLICT (case_id) DO UPDATE SET time_zone = EXCLUDED.time_zone, updated_by = EXCLUDED.updated_by, "
        "updated_at = now()"), {"c": body.case_id, "z": body.time_zone, "u": user.id})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Set phone data time zone",
                           details={"case_id": str(body.case_id), "changes": {"time_zone": {"from": old,
                                                                                            "to": body.time_zone}}},
                           user=user.email, success=True, db=db)
    db.commit()
    return get_settings(case_id=body.case_id, db=db, user=user)


@router.post("/streams/index")
def stream_index(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """03 section 4.5: exact total, per-day counts in the display zone, the no-time count and a snapshot."""
    f = _filter(body, db, user)
    try:
        return streams.index_comm_events(db.connection(), f)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 3.8 error wording with a reference
        raise _failure(LIST_FAILED, exc)


class WindowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    day: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=streams.WINDOW_MAX)


@router.post("/streams/window")
def stream_window(body: WindowBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Rows of one day (or the no-time group, ``day`` null) by offset; 409 ``stale_snapshot`` when the data moved."""
    f = _filter(body.filter, db, user)
    try:
        return streams.window_comm_events(db.connection(), f, snapshot_token=body.snapshot, day=body.day,
                                          offset=body.offset, limit=body.limit)
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except Exception as exc:  # noqa: BLE001
        raise _failure("These messages could not be loaded.", exc)


class LocateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    event_uid: UUID


@router.post("/streams/locate")
def stream_locate(body: LocateBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    f = _filter(body.filter, db, user)
    try:
        return streams.locate_comm_event(db.connection(), f, snapshot_token=body.snapshot,
                                         event_uid=str(body.event_uid))
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except streams.NotInCase:
        raise HTTPException(status_code=404, detail="This message is not in the current list.")


@router.post("/conversations/threads")
def conversation_threads(body: dict, sort: str = Query("recent", pattern="^(recent|first|volume|unreviewed|name)$"),
                         db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Every thread with events under the filter, in one response (6.3, C-5), with its review mark."""
    f = _filter(body, db, user)
    try:
        return streams.thread_list(db.connection(), f, sort=sort)
    except Exception as exc:  # noqa: BLE001
        raise _failure("The conversation list could not be loaded.", exc)


@router.post("/conversations/participants")
def conversation_participants(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """People mode (6.3): every participant under the filter with counts, phones and apps, in one response."""
    f = _filter(body, db, user)
    try:
        return streams.participant_list(db.connection(), f)
    except Exception as exc:  # noqa: BLE001
        raise _failure("The list of people could not be loaded.", exc)


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    words: str = Field(min_length=1, max_length=2000)


@router.post("/selections")
def freeze_selection(body: SelectionBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Freeze every record the filter matches now as one ``phone_selection`` (07 section 6.1), for Add to… on a whole
    result. Needs edit access, because it is made to be added somewhere."""
    from services.phone import selections
    f = _filter(body.filter, db, user, ("case", "edit"))
    try:
        return selections.freeze(db, f, user, body.words)
    except selections.SelectionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


class ReviewMarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    thread_key: str = Field(min_length=1, max_length=512)
    scope: dict = Field(default_factory=dict)
    position: Optional[dict] = None


@router.post("/conversations/review")
def mark_thread_reviewed(body: ReviewMarkBody, db: Session = Depends(get_db),
                         user: User = Depends(get_current_db_user)):
    """Mark a thread reviewed (07 section 6.1, J-13). Needs edit access to the case."""
    from services.phone import review_marks
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return {"thread_key": body.thread_key,
                "review": review_marks.mark(db, body.case_id, body.thread_key, user, scope=body.scope,
                                            position=body.position)}
    except review_marks.ReviewMarkError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/conversations/review/undo")
def undo_thread_review(body: ReviewMarkBody, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """Undo the latest review mark on a thread; an earlier mark, if any, is current again."""
    from services.phone import review_marks
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        prev = review_marks.undo(db, body.case_id, body.thread_key, user)
    except review_marks.ReviewMarkError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    return {"thread_key": body.thread_key, "restored": bool(prev)}


class CopyDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    reason: str = Field(min_length=1, max_length=4000)
    restore: bool = False


@router.post("/records/{record_uid}/not-a-copy")
def record_not_a_copy(record_uid: UUID, body: CopyDecisionBody, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    """A person's Not a copy decision (03 section 3.4, C-13); ``restore`` puts the record back in its group."""
    from services.phone import copies
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return copies.mark_not_a_copy(db, case_id=body.case_id, record_uid=record_uid, reason=body.reason,
                                      actor=_actor(user), restore=body.restore)
    except copies.CopyDecisionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/records/{record_uid}")
def record_detail(record_uid: UUID, case_id: UUID = Query(...), zone: Optional[str] = Query(None, max_length=64),
                  db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The record panel (3.6). A record of another case is 404, never 403 (3.11)."""
    authorize_case(db, case_id, user, ("case", "view"))
    z = zone if zone and time_display.valid_zone(zone) else streams.case_zone(db.connection(), case_id)["name"]
    try:
        out = phone_records.record_detail(db.connection(), case_id, record_uid, zone=z)
    except phone_records.NotFound:
        raise HTTPException(status_code=404, detail="This record is not in this case.")
    out["as_text"] = phone_records.record_text(out)
    return out


@router.get("/identities")
def identity_picker(case_id: UUID = Query(...), q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=200),
                    cursor: int = Query(0, ge=0), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """The identity picker (4.4): search as you type over every identity by value or any phone's name, with each
    phone's names and the event count; ``total`` is exact."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    from services.phone import fold as phone_fold
    conn = db.connection()
    folded = phone_fold.fold(q.strip()) if q.strip() else ""
    digits = "".join(ch for ch in q if ch.isdigit())
    idents = conn.execute(sql(
        "SELECT i.identity_id, i.identity_key, i.kind, i.value_display, i.value_normalised, i.person_id, "
        "p.display_name AS person_name FROM pv_identity i LEFT JOIN case_profiles p ON p.id = i.person_id "
        "WHERE i.case_id = :c"), {"c": case_id}).fetchall()
    names = {}
    for n in conn.execute(sql("SELECT identity_id, extraction_id, name, basis, is_phone_name FROM pv_identity_name "
                              "WHERE case_id = :c ORDER BY extraction_id"), {"c": case_id}):
        names.setdefault(n.identity_id, []).append(n)

    def matches(r):
        # Folded as Search folds (11.3): "jose" finds "José"; three or more digits match the number's digits.
        if not q.strip():
            return True
        if not folded:
            return False  # punctuation only: nothing to match
        hay = [r.value_display, r.identity_key] + [n.name for n in names.get(r.identity_id, [])]
        if any(folded in phone_fold.fold(h) for h in hay if h):
            return True
        return len(digits) >= 3 and digits in "".join(ch for ch in (r.value_normalised or "") if ch.isdigit())

    hits = [r for r in idents if matches(r)]
    counts = {k: int(n) for k, n in conn.execute(sql(
        "SELECT identity_key, count(DISTINCT event_uid) FROM pv_comm_party WHERE case_id = :c AND identity_key = "
        "ANY(CAST(:k AS text[])) GROUP BY identity_key"), {"c": case_id, "k": [r.identity_key for r in hits]})}
    hits.sort(key=lambda r: (-counts.get(r.identity_key, 0), r.value_display or "", r.identity_key))
    total = len(hits)
    labels = readings.phone_labels(conn, case_id)
    items = []
    for r in hits[cursor:cursor + limit]:
        items.append({"identity_key": r.identity_key, "kind": r.kind, "value_display": r.value_display,
                      "names": [{"phone_label": labels.get(str(n.extraction_id)), "name": n.name, "basis": n.basis}
                                for n in names.get(r.identity_id, []) if n.is_phone_name],
                      "person": {"id": str(r.person_id), "display_name": r.person_name} if r.person_id else None,
                      "event_count": counts.get(r.identity_key, 0)})
    nxt = cursor + len(items)
    return {"case_id": str(case_id), "items": items, "total": int(total), "next_cursor": nxt if nxt < total else None}
