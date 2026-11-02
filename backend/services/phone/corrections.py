"""Corrections on phone data (02 section 10): one captured value, and a device clock offset for a period.

A correction is a decision first (``correct_phone_value`` on the record, ``set_phone_clock_offset`` on the phone,
both with the person's own reason), then a row (``phone_value_corrections``) in the same transaction. Nothing
captured is changed: the next reading of the phone writes the corrected value as the effective one beside the
machine value, and every screen, search, thread document and count reads the effective one. An undo is a
correction back to the machine text; the chain stays.

What can be corrected here: a time (``TimeStamp``) and a text value (``String``: a body, a name, a number as
written). A phone's saved names are evidence of that phone and are not corrected; a case label is set instead
(``set_phone_identity_label``).
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

NS = uuid.UUID("0b8e3f41-7c2d-4a9e-b1f6-5e3a9d0c7b12")
MAX_OFFSET_SECONDS = 7 * 24 * 3600


class CorrectionError(ValueError):
    status = 422


class StaleCorrection(CorrectionError):
    status = 409


def parse_instant(value: str):
    """An ISO 8601 time with its offset (``2023-03-14T15:07:12-04:00`` or ``...Z``). A time without an offset is
    refused: which moment it names is the question being corrected."""
    s = (value or "").strip()
    if not s:
        raise CorrectionError("Enter the corrected time.")
    try:
        t = datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s)
    except ValueError as exc:
        raise CorrectionError("Write the time as 2023-03-14T15:07:12-04:00, with its offset from UTC.") from exc
    if t.tzinfo is None:
        raise CorrectionError("Include the offset from UTC (for example -04:00), so the time names one moment.")
    return t.astimezone(timezone.utc)


def current(conn, extraction_id) -> dict:
    """``{(record_uid, field_path, value_index): (corrected_text, value_type)}`` in effect on a phone."""
    return {(r[0], r[1], r[2]): (r[3], r[4]) for r in conn.execute(text(
        "SELECT record_uid, field_path, value_index, corrected_text, value_type FROM phone_value_corrections WHERE "
        "extraction_id = :e AND superseded_by_id IS NULL AND corrected_text IS DISTINCT FROM machine_text"),
        {"e": extraction_id})}


def _offset_periods(conn, extraction_id) -> dict:
    """``{(from, to): (seconds, decision_id)}`` as written, the latest decision per period."""
    latest = {}
    for did, after in conn.execute(text(
            "SELECT id, after FROM adjudications WHERE subject_type = 'phone_extraction' AND subject_id = :e AND "
            "decision = 'set_phone_clock_offset' ORDER BY subject_sequence"), {"e": extraction_id}):
        a = after or {}
        if "offset_seconds" in a:
            latest[(a.get("from"), a.get("to"))] = (int(a["offset_seconds"]), did)
    return latest


def clock_offsets(conn, extraction_id) -> list:
    """``[(start, end, seconds, decision_id)]`` from ``set_phone_clock_offset``; for one period the latest decision
    stands, and an offset of 0 ends it."""
    out = [(parse_instant(a) if a else None, parse_instant(b) if b else None, secs, did)
           for (a, b), (secs, did) in _offset_periods(conn, extraction_id).items() if secs]
    return sorted(out, key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)))


def effective_instant(machine, corrected_text, offsets):
    """(instant, basis): the corrected time, else the machine time moved by a clock offset whose period holds it,
    else the machine time."""
    if corrected_text is not None:
        return parse_instant(corrected_text), "corrected"
    if machine is not None:
        for start, end, secs, _ in offsets:
            if (start is None or machine >= start) and (end is None or machine < end):
                return machine + timedelta(seconds=secs), "clock_offset"
    return machine, ("report" if machine is not None else None)


def _machine(conn, record_uid, field_path, value_index):
    """The current reading of one value: (extraction_id, case_id, value_type, machine_text, instant)."""
    t = conn.execute(text(
        "SELECT v.extraction_id, v.case_id, v.original_text, v.instant FROM phone_time_values v JOIN "
        "phone_interpretation_state s ON s.extraction_id = v.extraction_id AND s.generation = v.generation WHERE "
        "v.record_uid = :r AND v.field_path = :f AND v.value_index = :i"),
        {"r": record_uid, "f": field_path, "i": value_index}).first()
    if t is not None:
        return t[0], t[1], "TimeStamp", t[2], t[3]
    x = conn.execute(text(
        "SELECT x.extraction_id, x.case_id, x.value, x.is_sensitive FROM phone_texts x JOIN phone_interpretation_state s "
        "ON s.extraction_id = x.extraction_id AND s.generation = x.generation WHERE x.record_uid = :r AND "
        "x.field_path = :f AND x.value_index = :i"), {"r": record_uid, "f": field_path, "i": value_index}).first()
    if x is not None:
        return x[0], x[1], "String", x[2], None
    return None


def chain(conn, record_uid, field_path=None, value_index=None) -> list:
    """Every correction of a record's values, oldest first, with who decided and why."""
    q = ("SELECT c.id, c.field_path, c.value_index, c.value_type, c.machine_text, c.corrected_text, "
         "c.superseded_by_id, c.created_at, a.actor_name, a.reason FROM phone_value_corrections c JOIN adjudications a "
         "ON a.id = c.decision_id WHERE c.record_uid = :r")
    p = {"r": record_uid}
    if field_path is not None:
        q += " AND c.field_path = :f AND c.value_index = :i"
        p.update(f=field_path, i=value_index or 0)
    return [{"id": str(r[0]), "field_path": r[1], "value_index": r[2], "value_type": r[3], "machine_text": r[4],
             "corrected_text": r[5], "current": r[6] is None, "at": r[7].isoformat() if r[7] else None,
             "by": r[8], "reason": r[9], "is_undo": r[5] == r[4]}
            for r in conn.execute(text(q + " ORDER BY c.created_at, c.id"), p)]


def revision(conn, record_uid, field_path, value_index) -> str:
    rows = [c["id"] for c in chain(conn, record_uid, field_path, value_index)]
    return hashlib.sha256("|".join(rows).encode()).hexdigest()[:32]


def correct_value(db, *, case_id, record_uid, field_path, value_index=0, corrected_text, reason, actor,
                  expected_revision=None) -> dict:
    """Record a correction of one captured value. The phone re-reads with it; the original stays visible."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_identity import PhoneRecordSubject
    from services.financial import decisions
    if not reason or not reason.strip():
        raise CorrectionError("A correction needs a reason in your own words.")
    conn = db.connection()
    found = _machine(conn, record_uid, field_path, value_index)
    if found is None or str(found[1]) != str(case_id):
        raise CorrectionError("That value is not in this case.")
    ext, _, value_type, machine_text, _ = found
    if expected_revision is not None and expected_revision != revision(conn, record_uid, field_path, value_index):
        raise StaleCorrection("Someone else corrected this value while you were looking. Their change is shown. "
                              "Your correction was not saved.")
    corrected = corrected_text if corrected_text is not None else ""
    if value_type == "TimeStamp":
        parse_instant(corrected)
        corrected = corrected.strip()
    elif not corrected.strip():
        raise CorrectionError("Enter the corrected value. To go back to what the phone recorded, undo the correction.")
    prior = conn.execute(text(
        "SELECT id, corrected_text FROM phone_value_corrections WHERE record_uid = :r AND field_path = :f AND "
        "value_index = :i AND superseded_by_id IS NULL"), {"r": record_uid, "f": field_path, "i": value_index}).first()
    was = prior[1] if prior is not None else machine_text
    if corrected == was:
        raise CorrectionError("That is already the value in effect.")
    subject = db.get(PhoneRecordSubject, record_uid)
    if subject is None:
        doc, ordinal = conn.execute(text(
            "SELECT document_index, ordinal FROM phone_record_summaries r JOIN phone_interpretation_state s ON "
            "s.extraction_id = r.extraction_id AND s.generation = r.generation WHERE r.record_uid = :r"),
            {"r": record_uid}).one()
        subject = PhoneRecordSubject(id=record_uid, case_id=case_id, extraction_id=ext, document_index=doc,
                                     ordinal=ordinal)
        db.add(subject)
        db.flush()
    key = "%s#%d" % (field_path, value_index)
    row = decisions.record(db, case_id=case_id, subject=subject, subject_type=AdjudicationSubject.phone_record,
                           decision=AdjudicationDecision.correct_phone_value, reason=reason.strip(), actor=actor,
                           before={key: was}, after={key: corrected})
    new_id = uuid.uuid4()
    if prior is not None:
        # one current row per value (unique index): the earlier row is retired first, then points at its successor
        conn.execute(text("UPDATE phone_value_corrections SET superseded_by_id = id WHERE id = :p"), {"p": prior[0]})
    conn.execute(text(
        "INSERT INTO phone_value_corrections (id, case_id, extraction_id, record_uid, field_path, value_index, "
        "value_type, machine_text, corrected_text, decision_id) VALUES (:id, :c, :e, :r, :f, :i, :t, :m, :v, :d)"),
        {"id": new_id, "c": case_id, "e": ext, "r": record_uid, "f": field_path, "i": value_index, "t": value_type,
         "m": machine_text, "v": corrected, "d": row.id})
    if prior is not None:
        conn.execute(text("UPDATE phone_value_corrections SET superseded_by_id = :n WHERE id = :p"),
                     {"n": new_id, "p": prior[0]})
    return {"decision_id": str(row.id), "correction_id": str(new_id), "extraction_id": str(ext),
            "machine_text": machine_text, "corrected_text": corrected, "is_undo": corrected == machine_text,
            "revision": revision(conn, record_uid, field_path, value_index)}


def set_clock_offset(db, *, case_id, extraction_id, offset_seconds, start=None, end=None, reason, actor) -> dict:
    """A device clock that was off by ``offset_seconds`` (added to the machine time) between ``start`` and ``end``
    (open ends allowed). An offset of 0 for the same period ends it."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_extraction import PhoneExtraction
    from services.financial import decisions
    if not reason or not reason.strip():
        raise CorrectionError("A clock offset needs a reason in your own words.")
    if not isinstance(offset_seconds, int) or abs(offset_seconds) > MAX_OFFSET_SECONDS:
        raise CorrectionError("The offset is a whole number of seconds, at most seven days either way.")
    for v in (start, end):
        if v:
            parse_instant(v)
    if start and end and parse_instant(start) >= parse_instant(end):
        raise CorrectionError("The period must end after it starts.")
    ext = db.get(PhoneExtraction, extraction_id)
    if ext is None or str(ext.case_id) != str(case_id):
        raise CorrectionError("That phone is not in this case.")
    before = _offset_periods(db.connection(), extraction_id).get((start, end), (0, None))[0]
    row = decisions.record(db, case_id=case_id, subject=ext, subject_type=AdjudicationSubject.phone_extraction,
                           decision=AdjudicationDecision.set_phone_clock_offset, reason=reason.strip(), actor=actor,
                           before={"offset_seconds": before, "from": start, "to": end},
                           after={"offset_seconds": offset_seconds, "from": start, "to": end})
    return {"decision_id": str(row.id), "offset_seconds": offset_seconds}


def record_decision_ids(conn, extraction_id) -> list:
    """Value corrections on this phone's records, for the decision revision (a correction re-derives the phone)."""
    return [str(r[0]) for r in conn.execute(text(
        "SELECT decision_id FROM phone_value_corrections WHERE extraction_id = :e ORDER BY created_at, id"),
        {"e": extraction_id})]
