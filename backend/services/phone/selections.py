"""Frozen phone selections (07 section 6.1; the ``phone_selection`` link type of lx-collect's registry).

``freeze`` stores every record the filter matches now, every copy of a collapsed group included, so a whole
filtered result goes through Add to… as one link and nothing in it is silently missing. The selection keeps the
filter, its sentence, the counts and the reading generation of each phone it covers; it is never rewritten.
``resolve`` is the link resolver: a selection of another case is not found, and a selection over a phone report
that has since been replaced is refused with the reason.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from postgres import link_types
from services.phone import streams
from services.phone.filters import StreamFilter

REPLACED = ("This selection includes a phone report that was replaced in this case; make the selection again on the "
            "report the case stands on")


class SelectionError(ValueError):
    pass


def freeze(db, f: StreamFilter, user, words: str) -> dict:
    conn = db.connection()
    q, _ = streams._query(conn, f)
    rows = conn.execute(text(
        "WITH m AS (%s) SELECT record_uid::text AS r, copy_rank, extraction_id FROM m ORDER BY sort_instant NULLS "
        "LAST, event_uid" % q.matched_sql()), q.params).fetchall()
    if not rows:
        raise SelectionError("Nothing matches this filter, so there is nothing to add.")
    records = list(dict.fromkeys(r.r for r in rows))
    events = sum(1 for r in rows if r.copy_rank == 1) if f.collapse_copies else len(rows)
    phones = sorted({str(r.extraction_id) for r in rows})
    versions = [dict(r._mapping) for r in conn.execute(text(
        "SELECT st.extraction_id::text AS extraction_id, st.generation, st.mapping_set_id::text AS mapping_set_id, "
        "st.interpreter_version FROM phone_interpretation_state st WHERE st.extraction_id::text = ANY(:p) "
        "ORDER BY 1"), {"p": phones})]
    sid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_selections (id, case_id, filter, words, record_uids, record_count, event_count, "
        "mapping_versions, created_by_user_id) VALUES (:i, :c, CAST(:f AS jsonb), :w, :r, :n, :e, CAST(:v AS jsonb), "
        ":u)"), {"i": sid, "c": f.case_id, "f": f.model_dump_json(), "w": words.strip() or "A phone selection",
                 "r": records, "n": len(records), "e": events, "v": json.dumps({"phones": versions}),
                 "u": getattr(user, "id", None)})
    db.commit()
    return {"id": str(sid), "record_count": len(records), "event_count": events, "words": words.strip()}


def resolve(db, case_id, target_id):
    try:
        sid, case = uuid.UUID(str(target_id)), uuid.UUID(str(case_id))
    except (TypeError, ValueError, AttributeError):
        return None
    row = db.execute(text(
        "SELECT words, record_uids, record_count, event_count, mapping_versions FROM phone_selections WHERE id = :i "
        "AND case_id = :c"), {"i": sid, "c": case}).first()
    if row is None:
        return None
    phones = [p["extraction_id"] for p in (row.mapping_versions or {}).get("phones", [])]
    if phones:
        current = db.execute(text(
            "SELECT count(*) FROM phone_interpretation_state st JOIN phone_extractions e ON e.id = st.extraction_id "
            "WHERE e.case_id = :c AND e.standing = 'active' AND st.extraction_id::text = ANY(:p)"),
            {"c": case, "p": phones}).scalar()
        if current != len(phones):
            raise link_types.LinkTargetError(REPLACED)
    return link_types.PhoneTarget(
        label=row.words, mapping_versions=dict(row.mapping_versions or {}), members=tuple(row.record_uids),
        metadata={"record_count": row.record_count, "event_count": row.event_count})
