"""A person corrects or confirms machine-generated text from phone media (03 8.3; 07 4.6 and 5 Media; M-6, M-7).

- **Correct**: the person types the right text and a reason. The machine text stays exactly as it was and stays
  visible beside the correction; only the corrected text is searched, quoted and exported as the text (07 4.6,
  "Corrected by <name> on <date>: <reason>"). Another correction replaces the previous one (the ledger keeps both).
- **Confirm**: the person checked the text against the original (listened, or looked at the image) and it stands
  ("Confirmed by <name> on <date>"). The reason is a standard reason built from what was shown (02 8.8).

Each is a decision in the case ledger (``decisions.record``, subject ``phone_derived_text``) and a manual change
(``services.manual_changes``, ``source='phone'``: the inbox line carries ids and kinds only, never the text), in
the same transaction as the save (CB-INDEX rule 11).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from services.phone import fold as F

KIND = "phone_machine_text"
SHOWN = {"transcript": "Confirmed after the audio was shown with the transcript",
         "ocr": "Confirmed after the image was shown with the text read from it"}


class MachineTextError(ValueError):
    status = 422


def _row(db, case_id, derived_id):
    from postgres.models.phone_derived import PhoneDerivedText
    try:
        ident = uuid.UUID(str(derived_id))
    except (ValueError, TypeError):
        raise LookupError("This machine-generated text is not in this case.") from None
    row = db.get(PhoneDerivedText, ident)
    if row is None or str(row.case_id) != str(case_id):
        raise LookupError("This machine-generated text is not in this case.")
    if row.state != "done":
        raise MachineTextError("This text is not finished yet, so it cannot be corrected or confirmed.")
    return row


def _actor(user):
    from services.financial.decisions import Actor
    return Actor(name=getattr(user, "name", None) or getattr(user, "email", "") or "unknown",
                 email=getattr(user, "email", "") or "", user_id=getattr(user, "id", None))


def effective_text(row) -> str:
    return row.corrected_text if row.corrected_text is not None else (row.text or "")


def _digest(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def correct(db, *, case_id, derived_id, text: str, reason: str, user) -> dict:
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from services import manual_changes
    from services.financial import decisions
    row = _row(db, case_id, derived_id)
    text = (text or "").strip()
    if not text:
        raise MachineTextError("Type the corrected text. To say the original is right, confirm it instead.")
    if not reason or not reason.strip():
        raise MachineTextError("A correction needs a reason in your own words.")
    before = effective_text(row)
    if text == before:
        raise MachineTextError("The text is unchanged. To say it is right, confirm it instead.")
    actor = _actor(user)
    # the ledger holds digests and lengths, not the evidence text itself; the text is in this row
    event = decisions.record(db, case_id=row.case_id, subject=row, subject_type=AdjudicationSubject.phone_derived_text,
                             decision=AdjudicationDecision.correct_machine_text, reason=reason.strip(), actor=actor,
                             before={"text_sha256": _digest(before), "chars": len(before),
                                     "corrected": row.corrected_text is not None},
                             after={"text_sha256": _digest(text), "chars": len(text), "corrected": True})
    row.corrected_text = text
    row.corrected_text_folded = F.fold(text)
    row.corrected_at = datetime.now(timezone.utc)
    row.corrected_by_name = actor.name
    row.corrected_by_user_id = getattr(user, "id", None)
    row.correction_reason = reason.strip()
    row.correction_decision_id = event.id
    manual_changes.record_change(
        db, KIND, row.case_id, {"type": "phone_derived_text", "id": str(row.id)}, {"text": before}, {"text": text},
        user, reason.strip(), pattern_key=manual_changes.make_pattern_key(KIND, "text", row.model or "", row.kind),
        source="phone")
    db.flush()
    return {"id": str(row.id), "decision_id": str(event.id)}


def confirm(db, *, case_id, derived_id, user, note: str = "") -> dict:
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from services import manual_changes
    from services.financial import decisions
    row = _row(db, case_id, derived_id)
    current = effective_text(row)
    stands = row.confirmed_at is not None and (row.corrected_at is None or row.confirmed_at >= row.corrected_at)
    reason = SHOWN.get(row.kind, "Confirmed after the original was shown")
    if note and note.strip():
        reason += ". Note: " + note.strip()
    actor = _actor(user)
    event = decisions.record(db, case_id=row.case_id, subject=row, subject_type=AdjudicationSubject.phone_derived_text,
                             decision=AdjudicationDecision.confirm_machine_text, reason=reason, actor=actor,
                             # confirming text that already stands confirmed is a review, not a change (02 8.8)
                             before=None if stands else {"confirmed": False, "text_sha256": _digest(current)},
                             after=None if stands else {"confirmed": True, "text_sha256": _digest(current)},
                             reason_kind="standard")
    row.confirmed_at = datetime.now(timezone.utc)
    row.confirmed_by_name = actor.name
    row.confirmed_by_user_id = getattr(user, "id", None)
    row.confirm_decision_id = event.id
    manual_changes.record_confirmation(
        db, KIND, row.case_id, {"type": "phone_derived_text", "id": str(row.id)}, {"text_sha256": _digest(current)},
        user, reason, pattern_key=manual_changes.make_pattern_key(KIND, "text", row.model or "", row.kind),
        source="phone")
    db.flush()
    return {"id": str(row.id), "decision_id": str(event.id)}


def is_confirmed(row_mapping) -> bool:
    """A text counts as confirmed when a person confirmed it after its latest correction, or corrected it (the
    corrected text is that person's own reading)."""
    d = row_mapping
    if d.get("corrected_at") is not None and (d.get("confirmed_at") is None
                                              or d["confirmed_at"] < d["corrected_at"]):
        return True
    return d.get("confirmed_at") is not None


def accept_into_assessment(db, *, case_id, derived_id, dossier_id, category: str, user) -> dict:
    """CO-18: a person accepts machine text into a dossier assessment. The assessment is stored ``ai_assisted``,
    names the text it came from, links the original file, and shows "Read by <model>, accepted by <name>". The text
    keeps its own mark: accepting it is not confirming it (07 4.6)."""
    from postgres.models.case_profile import CaseProfile
    from services import dossier_service
    row = _row(db, case_id, derived_id)
    dossier = db.get(CaseProfile, dossier_id)
    if dossier is None or str(dossier.case_id) != str(row.case_id):
        raise LookupError("This dossier is not in this case.")
    content = effective_text(row).strip()
    if not content:
        raise MachineTextError("No text was found in this file, so there is nothing to accept.")
    out = dossier_service.create_assessment(db, dossier_id=dossier_id, user=user, commit=False, data={
        "category": category, "content": content, "provenance_type": "ai_assisted", "derived_text_id": row.id,
        "supporting_links": [{"target_type": "phone_file", "target_id": str(row.file_uid),
                              "source_anchor": {"derived_text_id": str(row.id)}}]})
    return out
