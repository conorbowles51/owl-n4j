"""Phone schema registry: seed, per-extraction observation and the review queue (02 section 3).

The registry is global and holds structure only (3.1). Functions take a SQLAlchemy ``Connection`` (or ``Session``)
and never commit: the caller owns the transaction, so a pass is all or nothing.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

from sqlalchemy import text

from services.phone import body as B

SEED_PATH = os.path.join(os.path.dirname(__file__), "data", "registry_seed_2026-10-29.json")
BASIC = B.BASIC_TYPES
PLACEHOLDERS = ("(empty)", "(none)")
VALUE_FIELD_KINDS = ("field", "multiField", "nodeField", "dataField")
SET_VALUE_CAP = 500
ATTRIBUTE_ELEMENTS = ("model", "extractionInfo", "project", "file", "value")
BATCH = 5000

FLAG_FOR_TABLE = {"types": "new_type", "fields": "new_field", "nesting": "new_nesting",
                  "set_values": "new_set_value", "attributes": "new_attribute"}
TRANSITIONS = {
    ("open", "acknowledged"), ("open", "mapping_needed"), ("mapping_needed", "mapped"),
    ("acknowledged", "open"), ("dismissed", "open"),
    ("open", "dismissed"), ("acknowledged", "dismissed"), ("mapping_needed", "dismissed"), ("mapped", "dismissed"),
}
PERSON_TRANSITIONS = TRANSITIONS - {("mapping_needed", "mapped")}


def load_seed(path=SEED_PATH) -> dict:
    with open(path) as fh:
        return json.load(fh)


# ---- seed ------------------------------------------------------------------------------------------------------

def apply_seed(conn, seed=None) -> dict:
    """Idempotent: inserts missing rows as ``seed`` and updates seed columns only (3.5)."""
    seed = seed or load_seed()
    for t in seed["types"]:
        conn.execute(text(
            "INSERT INTO phone_schema_types (type_name, origin, seed_report_count, seed_record_count) "
            "VALUES (:type_name, 'seed', :seed_report_count, :seed_record_count) ON CONFLICT (type_name) DO UPDATE "
            "SET seed_report_count = EXCLUDED.seed_report_count, seed_record_count = EXCLUDED.seed_record_count"), t)
    for f in seed["fields"]:
        conn.execute(text(
            "INSERT INTO phone_schema_fields (type_name, field_name, field_kind, value_type, is_named_set, origin, "
            "seed_value_count, seed_report_count) VALUES (:type_name, :field_name, :field_kind, :value_type, "
            ":is_named_set, 'seed', :seed_value_count, :seed_report_count) "
            "ON CONFLICT (type_name, field_name, field_kind, value_type) DO UPDATE SET "
            "seed_value_count = EXCLUDED.seed_value_count, seed_report_count = EXCLUDED.seed_report_count"),
            {k: f[k] for k in ("type_name", "field_name", "field_kind", "value_type", "is_named_set",
                               "seed_value_count", "seed_report_count")})
    for s in seed["set_values"]:
        conn.execute(text(
            "INSERT INTO phone_schema_set_values (set_name, value, note, origin) VALUES (:set_name, :value, :note, "
            "'seed') ON CONFLICT (set_name, value) DO UPDATE SET note = EXCLUDED.note"), s)
    for n in seed["nesting"]:
        conn.execute(text(
            "INSERT INTO phone_schema_nesting (parent_type, field_name, field_kind, child_type, origin) VALUES "
            "(:parent_type, :field_name, :field_kind, :child_type, 'seed') ON CONFLICT DO NOTHING"),
            {k: n[k] for k in ("parent_type", "field_name", "field_kind", "child_type")})
    for a in seed["attributes"]:
        conn.execute(text(
            "INSERT INTO phone_schema_attributes (element, attribute, origin) VALUES (:element, :attribute, 'seed') "
            "ON CONFLICT DO NOTHING"), a)
    for fl in seed["acknowledged_flags"]:
        rows = conn.execute(text(
            "SELECT id FROM phone_schema_fields WHERE type_name = :t AND field_name = :f AND field_kind = :k "
            "AND value_type = :v"), {"t": fl["type_name"], "f": fl["field_name"], "k": fl["field_kind"],
                                     "v": fl["value_type"]}).fetchall()
        if not rows:
            continue
        rid = rows[-1][0]
        fid = conn.execute(text(
            "INSERT INTO phone_schema_flags (flag_kind, registry_table, registry_id, severity, state, detail) "
            "VALUES (:kind, 'fields', :rid, 'info', 'acknowledged', CAST(:detail AS jsonb)) "
            "ON CONFLICT (flag_kind, registry_table, registry_id) DO NOTHING RETURNING id"),
            {"kind": fl["flag_kind"], "rid": rid, "detail": json.dumps({"seed": True, "previous": fl["previous"], "now": fl["value_type"]})}
        ).scalar()
        if fid is not None:
            conn.execute(text(
                "INSERT INTO phone_schema_flag_events (flag_id, from_state, to_state, reason, actor_name) "
                "VALUES (:fid, NULL, 'acknowledged', :reason, 'Registry seed')"), {"fid": fid, "reason": fl["reason"]})
    return registry_counts(conn)


def registry_counts(conn) -> dict:
    q = lambda sql: conn.execute(text(sql)).scalar()
    return {
        "types": q("SELECT count(*) FROM phone_schema_types"),
        "fields": q("SELECT count(*) FROM phone_schema_fields"),
        "typed_fields": q("SELECT count(*) FROM phone_schema_fields WHERE value_type NOT IN ('(empty)', '(none)')"),
        "set_values": q("SELECT count(*) FROM phone_schema_set_values"),
        "nesting": q("SELECT count(*) FROM phone_schema_nesting"),
        "attributes": q("SELECT count(*) FROM phone_schema_attributes"),
        "flags": q("SELECT count(*) FROM phone_schema_flags"),
    }
