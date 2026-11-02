"""Whether a phone's material may go to an external service (02 sections 8.8 and 9.8; plan standing decision 8).

Embeddings, transcription, translation, image search and geocoding of phone material need a recorded
``allow_phone_external_processing`` decision on the phone report, with a typed reason. With no decision the answer
is no. Chat retrieval, the agent's phone tools, Workspace AI, theory analysis and statement drafting read phone
records in full through the existing model policy and do not consult this (Neil, 2026-11-01; 9.8).

``check`` is what ``services.phone_files.register_external_processing_check`` takes: a phone file used as evidence
is processed only when its own phone report allows it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

DECISION = "allow_phone_external_processing"


class ExternalProcessingError(ValueError):
    status = 422


def allowed(conn, case_id, extraction_id) -> bool:
    """The latest decision on this phone report, else False."""
    row = conn.execute(text(
        "SELECT after FROM adjudications WHERE case_id = :c AND subject_type = 'phone_extraction' AND subject_id = :e "
        "AND decision = :d ORDER BY subject_sequence DESC LIMIT 1"),
        {"c": case_id, "e": extraction_id, "d": DECISION}).first()
    return bool(row and (row[0] or {}).get("external_processing") is True)


def state(conn, case_id, extraction_id) -> dict:
    row = conn.execute(text(
        "SELECT after, actor_name, created_at, reason FROM adjudications WHERE case_id = :c AND subject_type = "
        "'phone_extraction' AND subject_id = :e AND decision = :d ORDER BY subject_sequence DESC LIMIT 1"),
        {"c": case_id, "e": extraction_id, "d": DECISION}).first()
    if row is None:
        return {"external_processing": False, "decided_by": None, "decided_at": None, "reason": None}
    return {"external_processing": (row[0] or {}).get("external_processing") is True, "decided_by": row[1],
            "decided_at": row[2].isoformat() if row[2] else None, "reason": row[3]}


def check(db, case_id, evidence_file) -> bool:
    """For ``phone_files.register_external_processing_check``: the file's phone report must allow it."""
    meta = getattr(evidence_file, "metadata_", None) or {}
    try:
        extraction_id = uuid.UUID(str(meta.get("extraction_id")))
    except (ValueError, TypeError):
        return False  # a phone file with no phone report named cannot be shown to be allowed
    return allowed(db.connection(), case_id, extraction_id)


def decide(db, *, case_id, extraction_id, allow: bool, reason: str, actor) -> dict:
    """Record the decision on the phone report. A typed reason is required either way (8.8)."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_extraction import PhoneExtraction
    from services.financial import decisions
    if not reason or not reason.strip():
        raise ExternalProcessingError("This decision needs a reason in your own words.")
    ext = db.get(PhoneExtraction, extraction_id)
    if ext is None or ext.case_id != case_id:
        raise ExternalProcessingError("That phone report is not in this case.")
    before = allowed(db.connection(), case_id, extraction_id)
    row = decisions.record(db, case_id=case_id, subject=ext, subject_type=AdjudicationSubject.phone_extraction,
                           decision=AdjudicationDecision.allow_phone_external_processing, reason=reason.strip(),
                           actor=actor, before={"external_processing": before},
                           after={"external_processing": bool(allow)})
    from services import manual_changes
    manual_changes.record_change(db, "phone_external_processing", case_id,
                                 {"type": "phone_extraction", "id": str(extraction_id)},
                                 {"external_processing": before}, {"external_processing": bool(allow)}, actor,
                                 reason.strip(), pattern_key=manual_changes.make_pattern_key("phone_external_processing"))
    return {"decision_id": str(row.id), "external_processing": bool(allow)}


def install() -> None:
    """Called once at backend start (cb-capture m110114384716005)."""
    from services import phone_files
    phone_files.register_external_processing_check(check)
