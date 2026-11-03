"""Captured records for the approach tests (05): bodies with named sets, nested records, summaries, texts and
instants, written the way capture and interpretation would. Invented data only."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from services.phone import ids
from tests.phone_streams_fixture import GEN


def add_fields(c, ext, ordinal, *fields):
    """Append captured fields to a record's body (named sets, TimeSpans: not in phone_texts)."""
    body = c.execute(text("SELECT body FROM phone_records WHERE extraction_id = :e AND ordinal = :o"),
                     {"e": ext, "o": ordinal}).scalar()
    for name, vtype, value in fields:
        body[3].append(["field", {"name": name}, None, [["value", {"type": vtype}, value, None]]])
    c.execute(text("UPDATE phone_records SET body = CAST(:b AS jsonb) WHERE extraction_id = :e AND ordinal = :o"),
              {"e": ext, "o": ordinal, "b": json.dumps(body)})


def record(c, case, ext, ordinal, model_type, fields=(), parent=None, deleted="Intact", times=(), texts=(), top=None):
    """A captured record (top-level or nested) with its summary, string texts and instants."""
    body = ["model", {"type": model_type, "id": str(uuid.uuid4()), "deleted_state": deleted,
                      "decoding_confidence": "High"}, None,
            [["field", {"name": n}, None, [["value", {"type": t}, v, None]]] for n, t, v in fields]]
    top_o = top if top is not None else (parent if parent is not None else ordinal)
    c.execute(text(
        "INSERT INTO phone_records (extraction_id, document_index, ordinal, parent_ordinal, top_ordinal, depth, "
        "model_type, source_model_id, deleted_state, is_partial, body) VALUES (:e, 0, :o, :p, :t, :d, :mt, :sid, :ds, "
        "false, CAST(:b AS jsonb))"),
        {"e": ext, "o": ordinal, "p": parent, "t": top_o,
         "d": 0 if parent is None else 1, "mt": model_type, "sid": body[1]["id"], "ds": deleted, "b": json.dumps(body)})
    uid = ids.record_uid(ext, 0, ordinal)
    root = ids.record_uid(ext, 0, top_o)
    base = {"c": case, "e": ext, "o": ordinal, "u": uid, "r": root, "loc": "%s/0/r%d" % (ext, ordinal), "mt": model_type,
            "g": GEN}
    c.execute(text(
        "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, parent_record_uid, locator, model_type, generation, is_top_level, title, has_time, has_point, "
        "deleted_state) VALUES (:c, :e, 0, :o, :u, :r, :pu, :loc, :mt, :g, :top, 'synthetic', false, false, :ds)"),
        dict(base, pu=ids.record_uid(ext, 0, parent) if parent is not None else None, top=parent is None, ds=deleted))
    for field, value in texts:
        c.execute(text(
            "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
            "locator, model_type, generation, text_uid, body_path, field_name, field_path, value_index, value, "
            "value_folded, effective_value) VALUES (:c, :e, 0, :o, :u, :r, :loc, :mt, :g, :tu, '0', :f, :fp, 0, :v, :vf, "
            ":ve)"), dict(base, tu=uuid.uuid5(uid, field), f=field, fp=field, v=value, vf=value, ve=value))
    for field, instant in times:
        c.execute(text(
            "INSERT INTO phone_time_values (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, time_uid, body_path, field_name, field_path, "
            "value_index, instant, effective_instant, original_text, offset_state, offset_present) VALUES (:c, :e, 0, "
            ":o, :u, :r, :loc, :mt, :g, :tu, '0', :f, :fp, 0, :i, :i, :t, 'explicit', true)"),
            dict(base, tu=uuid.uuid5(uid, "t" + field), f=field, fp=field, i=instant, t=instant.isoformat()))
    return str(uid)
