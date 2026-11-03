"""Sensitive values (docs/cellebrite/05 section 3.8, 02 section 5.5): captured in full, shown masked until a person
presses Reveal, and every Reveal logged (actor, time, locator, field) in the append-only ``phone_sensitive_reveals``.

The set is the interpreter's built-in list plus the ``sensitive_fields`` mapping (``sweep.sensitive_fields``): a
mapping can add a sensitive field, never remove one. Card and account numbers show their last four characters.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

MASK = "••••"
SHOW_LAST_FOUR = frozenset({("CreditCard", "CreditCardNumber")})


class RevealError(ValueError):
    status = 422


def fields() -> frozenset:
    from services.phone import sweep
    return sweep.sensitive_fields()


def is_sensitive(model_type, field_name) -> bool:
    return (model_type, field_name) in fields()


def masked(model_type, field_name, value) -> str:
    v = "" if value is None else str(value)
    if (model_type, field_name) in SHOW_LAST_FOUR:
        digits = "".join(ch for ch in v if ch.isalnum())
        return MASK + digits[-4:] if len(digits) > 4 else MASK
    return MASK


def mask_detail(node: dict) -> dict:
    """Mask every sensitive value in a ``records.record_detail`` tree, in place; each masked value says so."""
    if not node:
        return node
    for f in node.get("fields") or []:
        if is_sensitive(node.get("model_type"), f.get("name")):
            for v in f.get("values") or []:
                if v.get("text") not in (None, ""):
                    v["text"] = masked(node.get("model_type"), f.get("name"), v["text"])
                    v["masked"] = True
            f["sensitive"] = True
        for child in f.get("children") or []:
            mask_detail(child)
    return node


def reveal(db, case_id, record_uid, field_name, value_index, actor) -> dict:
    """The value, logged first. 404 when the record is not in the case; 422 when the field is not sensitive (it is
    shown already)."""
    from services.phone import body as B
    from services.phone import ids
    conn = db.connection()
    row = conn.execute(text(
        "SELECT s.extraction_id, s.document_index, s.ordinal, s.model_type FROM phone_record_summaries s JOIN "
        "phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation JOIN "
        "phone_extractions e ON e.id = s.extraction_id WHERE s.record_uid = CAST(:u AS uuid) AND e.case_id = :c"),
        {"u": str(record_uid), "c": str(case_id)}).first()
    if row is None:
        raise LookupError("That record is not in this case.")
    if not is_sensitive(row.model_type, field_name):
        raise RevealError("That field is not a sensitive field; it is shown in full already.")
    body = conn.execute(text("SELECT body FROM phone_records WHERE extraction_id = :e AND document_index = :d AND "
                             "ordinal = :o"), {"e": row.extraction_id, "d": row.document_index, "o": row.ordinal}).scalar()
    value = None
    for fv in B.fields(body):
        if fv.name == field_name:
            for v in fv.values:
                if v.index == value_index:
                    value = v.text
    if value is None:
        raise RevealError("That record has no such value.")
    conn.execute(text(
        "INSERT INTO phone_sensitive_reveals (id, case_id, record_uid, extraction_id, field_path, value_index, "
        "actor_user_id, actor_email, actor_name) VALUES (:i, :c, :u, :e, :f, :x, :uid, :em, :nm)"),
        {"i": uuid.uuid4(), "c": str(case_id), "u": str(record_uid), "e": row.extraction_id, "f": field_name,
         "x": value_index, "uid": getattr(actor, "user_id", None), "em": actor.email, "nm": actor.name})
    return {"record_uid": str(record_uid), "field_path": field_name, "value_index": value_index, "value": value,
            "logged": True}


def reveals(conn, case_id, record_uid=None) -> list:
    q = ("SELECT record_uid, field_path, value_index, actor_name, actor_email, revealed_at FROM phone_sensitive_reveals "
         "WHERE case_id = :c")
    p = {"c": str(case_id)}
    if record_uid:
        q += " AND record_uid = CAST(:u AS uuid)"
        p["u"] = str(record_uid)
    return [{"record_uid": str(r.record_uid), "field_path": r.field_path, "value_index": r.value_index,
             "by": r.actor_name, "email": r.actor_email, "at": r.revealed_at.isoformat()}
            for r in conn.execute(text(q + " ORDER BY revealed_at, record_uid"), p)]
