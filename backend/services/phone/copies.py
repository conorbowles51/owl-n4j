"""Copies of one event (03 section 3.4, rule version 1; D-9; test C-13).

Two events on one phone are copies when kind, direction, the sender's key, the sorted set of recipient keys, the
content and the instant are all equal. The content is ``sha256(NFC(body))``; for an email the subject and body; for
a call the duration and status. Two emails are copies only when their header thread is the same too (D-34): copies
of one email carry the same Message-ID and References, so a different header thread means a different email. An
event with no instant never matches. Equal-to-the-instant is the settled
precision (20.1 measured near copies a second apart and kept them apart).

The group id is written to ``phone_comm_events.dup_group_uid`` with ``dup_rule_version = 1``; the lists show one
row per group with "Found N times" and ``Show every copy`` lists every record (streams). A person's ``Not a copy``
decision (02 section 8.8 ``mark_not_duplicate``, after ``{"dup_group_uid": null}``) takes that record out of its
group; another ``mark_not_duplicate`` with the group restores it. Decisions are recorded through
``services.financial.decisions`` and ``manual_changes.record_change`` (CB-INDEX rule 11).
"""
from __future__ import annotations

from sqlalchemy import text

from services.phone.labels import RECIPIENT_ROLES, SENDER_ROLES

RULE_VERSION = 1


def _excluded_sql():
    """Records whose latest ``mark_not_duplicate`` decision says they are not a copy."""
    return ("SELECT DISTINCT ON (a.subject_id) a.subject_id::text AS record_uid, a.after "
            "FROM adjudications a WHERE a.subject_type = 'phone_record' AND a.decision = 'mark_not_duplicate' "
            "AND a.subject_id::text IN (SELECT record_uid::text FROM phone_comm_events WHERE extraction_id = :e AND "
            "generation = :g) ORDER BY a.subject_id, a.subject_sequence DESC")


def assign(conn, ext, gen) -> dict:
    """Recompute every copy group of one phone's generation. Returns ``{"groups": n, "records": n}``."""
    conn.execute(text(
        "UPDATE phone_comm_events SET dup_group_uid = NULL, dup_rule_version = :v WHERE extraction_id = :e AND "
        "generation = :g"), {"e": ext, "g": gen, "v": RULE_VERSION})
    conn.execute(text(
        "WITH x AS (" + _excluded_sql() + "), "
        "ev AS (SELECT ev.event_uid, ev.record_uid, ev.kind, ev.direction, ev.sort_instant, ev.body, ev.subject, "
        "ev.call_duration_s, ev.call_status, ev.thread_key FROM phone_comm_events ev WHERE ev.extraction_id = :e AND "
        "ev.generation = :g AND ev.sort_instant IS NOT NULL AND ev.record_uid::text NOT IN (SELECT record_uid FROM x "
        "WHERE (after ->> 'dup_group_uid') IS NULL)), "
        "pk AS (SELECT p.record_uid, CASE WHEN p.role = ANY(CAST(:sr AS text[])) THEN 's' WHEN p.role = "
        "ANY(CAST(:rr AS text[])) THEN 'r' END AS side, coalesce(p.identity_key, CASE WHEN p.role = 'owner_implicit' "
        "OR p.is_phone_owner IS TRUE THEN 'owner' END, 'raw:' || coalesce(p.identifier_raw, '')) AS k "
        "FROM phone_participations p WHERE p.extraction_id = :e AND p.generation = :g), "
        "keyed AS (SELECT ev.event_uid, encode(sha256(convert_to(concat_ws('|', ev.kind, coalesce(ev.direction, ''), "
        "to_char(ev.sort_instant AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US'), "
        "(SELECT string_agg(k, ',' ORDER BY k) FROM pk WHERE pk.record_uid = ev.record_uid AND side = 's'), "
        "(SELECT string_agg(DISTINCT k, ',' ORDER BY k) FROM pk WHERE pk.record_uid = ev.record_uid AND side = 'r'), "
        "CASE WHEN ev.kind = 'call' THEN coalesce(ev.call_duration_s::text, '') || '/' || coalesce(ev.call_status, '') "
        "WHEN ev.kind = 'email' THEN coalesce(ev.thread_key, '') || '/' || encode(sha256(convert_to(normalize("
        "coalesce(ev.subject, '') || chr(10) || coalesce(ev.body, ''), NFC), 'UTF8')), 'hex') "
        "ELSE encode(sha256(convert_to(normalize(coalesce(ev.body, ''), NFC), 'UTF8')), 'hex') END), 'UTF8')), "
        "'hex') AS grp FROM ev), "
        "groups AS (SELECT grp FROM keyed GROUP BY grp HAVING count(*) > 1) "
        "UPDATE phone_comm_events t SET dup_group_uid = k.grp FROM keyed k JOIN groups USING (grp) "
        "WHERE t.event_uid = k.event_uid AND t.extraction_id = :e AND t.generation = :g"),
        {"e": ext, "g": gen, "sr": list(SENDER_ROLES), "rr": list(RECIPIENT_ROLES)})
    row = conn.execute(text(
        "SELECT count(DISTINCT dup_group_uid), count(dup_group_uid) FROM phone_comm_events WHERE extraction_id = :e "
        "AND generation = :g"), {"e": ext, "g": gen}).one()
    return {"groups": int(row[0]), "records": int(row[1])}


class CopyDecisionError(ValueError):
    pass


def mark_not_a_copy(db, *, case_id, record_uid, reason, actor, restore=False) -> dict:
    """Record a person's ``Not a copy`` (or, with ``restore``, put the record back in its group) and recompute the
    phone's groups. The decision keeps who, when, the reason and the group it applied to."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_identity import PhoneRecordSubject
    from services import manual_changes
    from services.financial import decisions
    conn = db.connection()
    ev = conn.execute(text(
        "SELECT ev.extraction_id, ev.generation, ev.dup_group_uid, ev.document_index, ev.ordinal FROM "
        "phone_comm_events ev JOIN phone_interpretation_state st ON st.extraction_id = ev.extraction_id AND "
        "st.generation = ev.generation JOIN phone_extractions e ON e.id = ev.extraction_id WHERE "
        "ev.record_uid = CAST(:r AS uuid) AND e.case_id = :c"), {"r": str(record_uid), "c": case_id}).first()
    if ev is None:
        raise CopyDecisionError("This record is not a message, call or email in this case.")
    if not reason or not reason.strip():
        raise CopyDecisionError("Give a reason.")
    last = conn.execute(text(
        "SELECT before, after FROM adjudications WHERE subject_type = 'phone_record' AND subject_id::text = :r AND "
        "decision = 'mark_not_duplicate' ORDER BY subject_sequence DESC LIMIT 1"), {"r": str(record_uid)}).first()
    if restore:
        group = (last.before or {}).get("dup_group_uid") if last and (last.after or {}).get("dup_group_uid") is None \
            else None
        if not group:
            raise CopyDecisionError("This record has no Not a copy decision to undo.")
        before, after = {"dup_group_uid": None}, {"dup_group_uid": group}
    else:
        if not ev.dup_group_uid:
            raise CopyDecisionError("This record is not grouped with any copy.")
        before, after = {"dup_group_uid": ev.dup_group_uid}, {"dup_group_uid": None}
    subject = db.get(PhoneRecordSubject, record_uid)
    if subject is None:
        subject = PhoneRecordSubject(id=record_uid, case_id=case_id, extraction_id=ev.extraction_id,
                                     document_index=ev.document_index, ordinal=ev.ordinal)
        db.add(subject)
        db.flush()
    row = decisions.record(db, case_id=case_id, subject=subject, subject_type=AdjudicationSubject.phone_record,
                           decision=AdjudicationDecision.mark_not_duplicate, reason=reason.strip(), actor=actor,
                           before=before, after=after)
    manual_changes.record_change(db, "phone_copy", case_id, {"type": "phone_record", "id": str(record_uid)},
                                 before, after, actor, reason.strip(), field="dup_group_uid",
                                 link="/cases/%s/conversations" % case_id, change_type="change",
                                 pattern_key=manual_changes.make_pattern_key("phone_copy", "dup_group_uid"))
    counts = assign(conn, ev.extraction_id, ev.generation)
    db.commit()
    return {"decision_id": str(row.id), "restored": restore, "groups": counts["groups"]}
