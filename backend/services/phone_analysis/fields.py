"""Reading captured field values for the approaches (05 section 3.1 "Captured record read").

``phone_texts`` holds only String fields. Named-set values (``DeletionReason``, ``Label``, ``EventType``,
``Categories``), TimeSpans and Booleans are read from the captured record body (01's lossless JSON tree:
``["model", attrs, null, [children]]``, each child ``["field"|"multiField", {"name": ...}, null, [["value", {...},
value, null], ...]]``). Times are never parsed here: they come from ``pv_time`` (01/04 instants).
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone import ids

_FIELDS_SQL = (
    "SELECT r.document_index, r.ordinal, r.parent_ordinal, r.model_type, r.deleted_state, f->1->>'name' AS name, "
    "v->>2 AS value, r.body->1->>'isrelated' AS related FROM phone_records r "
    "CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(r.body->3) = 'array' THEN r.body->3 ELSE "
    "'[]'::jsonb END) f "
    "CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(f->3) = 'array' THEN f->3 ELSE '[]'::jsonb END) v "
    "WHERE r.extraction_id = :e AND r.model_type = ANY(:t) AND f->>0 IN ('field', 'multiField') AND "
    "f->1->>'name' = ANY(:n) AND v->>0 = 'value'")


def field_values(conn, extraction_id, model_types, names) -> dict:
    """``{record_uid: {"model_type", "deleted_state", "parent_uid", "values": {name: [value, ...]}}}`` for the
    records of ``model_types`` on one extraction that carry any of ``names``. A copy from another source that says
    nothing its owner does not (02 decision 39) is left out: it is the owner's fact, not a second record of it."""
    out = {}
    copies = []
    for r in conn.execute(text(_FIELDS_SQL), {"e": str(extraction_id), "t": list(model_types), "n": list(names)}):
        uid = str(ids.record_uid(extraction_id, r.document_index, r.ordinal))
        item = out.get(uid)
        if item is None:
            parent = (str(ids.record_uid(extraction_id, r.document_index, r.parent_ordinal))
                      if r.parent_ordinal is not None else None)
            item = out[uid] = {"model_type": r.model_type, "deleted_state": r.deleted_state, "parent_uid": parent,
                               "values": defaultdict(list)}
            if r.related == "True":
                copies.append(uid)
        if r.value is not None:
            item["values"][r.name].append(r.value)
    for uid in copies:
        owner = out.get(out[uid]["parent_uid"])
        if owner is not None and all(set(v) <= set(owner["values"].get(k, ())) for k, v in out[uid]["values"].items()):
            del out[uid]
    return out


def type_counts(conn, extraction_id, model_types) -> dict:
    """Records of each type, a copy from another source not counted as another record (02 decision 39)."""
    return {r[0]: int(r[1]) for r in conn.execute(text(
        "SELECT s.model_type, count(*) FROM phone_record_summaries s JOIN phone_interpretation_state st ON "
        "st.extraction_id = s.extraction_id AND st.generation = s.generation WHERE s.extraction_id = :e AND "
        "s.model_type = ANY(:t) AND NOT ('related_copy' = ANY(s.flags)) GROUP BY 1"),
        {"e": str(extraction_id), "t": list(model_types)})}


def active_phones(conn, case_id) -> dict:
    """``{extraction_id: label}`` for the case's active phones, in a stable order."""
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, str(case_id))
    return {str(r[0]): labels.get(str(r[0])) or str(r[0])[:8] for r in conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' ORDER BY id"),
        {"c": str(case_id)})}


def times_for(conn, extraction_id, record_uids, field_names=None) -> dict:
    """``{record_uid: {field_path: instant}}`` (first value) from 01/04's instants."""
    if not record_uids:
        return {}
    q = ("SELECT record_uid, field_path, min(instant) FROM pv_time WHERE extraction_id = :e AND record_uid = "
         "ANY(CAST(:u AS uuid[])) AND instant IS NOT NULL")
    p = {"e": str(extraction_id), "u": list(record_uids)}
    if field_names:
        q += " AND field_path = ANY(:f)"
        p["f"] = list(field_names)
    out = defaultdict(dict)
    for r in conn.execute(text(q + " GROUP BY 1, 2"), p):
        out[str(r[0])][r[1]] = r[2]
    return out
