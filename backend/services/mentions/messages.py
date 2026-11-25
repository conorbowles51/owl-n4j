"""The texts a phone holds that can carry a mention: messages and e-mails, and its notes and calendar entries.

Each text comes with who wrote it (the speaker, whose "I" it is) and who it was written to, as person keys from the
Corroborate store, so "I'll drive up Friday" is about the sender and "before you head up" about the recipient. Texts
are read in order of (time, record id), so a run can stop and carry on from the last one it finished.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.corroborate import model as M

PAGE = 200
NOTE_TYPES = ("Note", "CalendarEntry")


def texts(db, case_id, extraction_id, people, after=None, limit=PAGE) -> list[dict]:
    """Up to ``limit`` texts of the phone after the cursor ``after`` = (instant, record uid)."""
    owner = next((p["key"] for p in people if str(extraction_id) in p["phones"]), None)
    params = {"c": str(case_id), "e": str(extraction_id), "lim": limit}
    cond = ""
    if after:
        cond = " AND (c.sort_instant, c.record_uid::text) > (CAST(:at AS timestamptz), :uid)"
        params.update(at=after[0], uid=str(after[1]))
    rows = db.execute(text(
        "SELECT c.record_uid, c.kind, c.sort_instant, c.body, c.direction, c.app, c.thread_key FROM phone_comm_events c "
        "WHERE c.case_id = :c AND c.extraction_id = :e AND c.kind IN ('message', 'email') AND c.sort_instant IS NOT NULL "
        "AND COALESCE(c.body, '') <> ''" + cond + " ORDER BY c.sort_instant, c.record_uid::text LIMIT :lim"), params).fetchall()
    parts = defaultdict(list)
    if rows:
        for uid, raw, role, own in db.execute(text(
                "SELECT record_uid, identifier_raw, role, COALESCE(is_phone_owner, false) FROM phone_participations WHERE "
                "case_id = :c AND record_uid = ANY(CAST(:u AS uuid[]))"),
                {"c": str(case_id), "u": [str(r[0]) for r in rows]}):
            parts[str(uid)].append((raw, role, own))
    out = []
    for uid, kind, at, body, direction, app, thread in rows:
        others = [(raw, role) for raw, role, own in parts.get(str(uid), []) if not own and raw]
        keys = [k for k in (M.person_for_value(people, raw) for raw, _ in others) if k and k != owner]
        if direction == "outgoing":
            speaker, addressee = owner, list(dict.fromkeys(keys))
        else:
            sender = next((M.person_for_value(people, raw) for raw, role in others if role in ("sender", "from")), None)
            speaker = sender or (keys[0] if len(keys) == 1 else None)
            addressee = [owner] if owner else []
        out.append({"record_uid": str(uid), "kind": kind, "at": M.as_utc(at), "body": body, "direction": direction,
                    "app": app, "thread": thread, "speaker": speaker, "addressee": addressee,
                    "counterpart_values": [raw for raw, _ in others][:5]})
    return out


def notes(db, case_id, extraction_id, people, limit=2000):
    """The phone's notes and calendar entries, read in one pass after its messages."""
    owner = next((p["key"] for p in people if str(extraction_id) in p["phones"]), None)
    rows = db.execute(text(
        "SELECT r.record_uid, r.model_type, r.first_instant, string_agg(t.value, ' · ' ORDER BY t.field_path) FROM pv_record r "
        "JOIN pv_text t ON t.record_uid = r.record_uid AND t.field_path IN ('Title', 'Body', 'Summary', 'Details', 'Subject', "
        "'Location') WHERE r.case_id = :c AND r.extraction_id = :e AND r.model_type = ANY(:t) AND r.first_instant IS NOT NULL "
        "GROUP BY 1, 2, 3 ORDER BY 3 LIMIT :lim"), {"c": str(case_id), "e": str(extraction_id), "t": list(NOTE_TYPES),
                                                    "lim": limit}).fetchall()
    return [{"record_uid": str(uid), "kind": "note" if mt == "Note" else "calendar", "at": M.as_utc(at), "body": body or "",
             "direction": None, "app": None, "thread": None, "speaker": owner, "addressee": [], "counterpart_values": []} for uid, mt, at, body in rows if body]


def count(db, case_id, extraction_id) -> int:
    return int(db.execute(text(
        "SELECT count(*) FROM phone_comm_events WHERE case_id = :c AND extraction_id = :e AND kind IN ('message', 'email') "
        "AND sort_instant IS NOT NULL AND COALESCE(body, '') <> ''"), {"c": str(case_id), "e": str(extraction_id)}).scalar() or 0)
