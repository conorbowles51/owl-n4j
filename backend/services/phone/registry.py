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
# The sentence the test-phone builder (evidence-engine/tests/phone/fixture_builder.py) writes into every report's
# case notes. A value invented for a test is not vocabulary a phone was seen to use (3.3).
INVENTED_REPORT_MARK = "SYNTHETIC: invented data, no real case material"
INVENTED_ACTOR = "Registry clean-up"
INVENTED_REASON = ("Value of an invented test report (its case notes carry the invented-data mark); no real report "
                   "holds it.")

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


# ---- observation pass (3.3) --------------------------------------------------------------------------------------

class NotCaptured(RuntimeError):
    pass


def _walk_elements(node, tag_names):
    """Yield (tag, attrs) of skeleton elements whose tag is in ``tag_names`` (markers skipped)."""
    stack = [node]
    while stack:
        el = stack.pop()
        if not isinstance(el, list) or not el or not isinstance(el[0], str) or el[0][:1] == "@":
            continue
        if el[0] in tag_names:
            yield el[0], (el[1] or {})
        for c in el[3] or () if len(el) > 3 else ():
            stack.append(c)


class Accumulator:
    """Bounded by the registry's size, not the phone's (3.3 step 2)."""

    def __init__(self):
        self.types = defaultdict(lambda: {"records": 0, "top": False, "nested": False})
        self.fields = defaultdict(lambda: {"records": 0, "values": 0, "empties": 0, "max": 0})
        self.empty_only = defaultdict(lambda: {"records": 0, "empties": 0})   # (t, f, k) with no typed value here
        self.nesting = defaultdict(int)
        self.sets = defaultdict(int)
        self.attributes = set()

    def add_record(self, model_type, is_top, body, child_type_of):
        t = self.types[model_type]
        t["records"] += 1
        t["top"] = t["top"] or is_top
        t["nested"] = t["nested"] or not is_top
        attrs = B.model_attrs(body)
        for a in attrs:
            self.attributes.add(("model", a))
        dc = attrs.get("decoding_confidence")
        if dc is not None:
            self.sets[("@decoding_confidence", dc)] += 1
        seen_in_record = set()
        for i, el in enumerate(body[3] or ()):
            if isinstance(el, list) and el and el[0] not in B.FIELD_KINDS and not B.is_marker(el):
                kids = [c[1] for c in (el[3] or ()) if B.is_marker(c) and c[0] == B.RECORD_MARK]
                if kids:  # e.g. RelatedModels: a container element holding record copies (02 decision 39)
                    name = (el[1] or {}).get("name") or el[0]
                    for o in kids:
                        self.nesting[(model_type, name, el[0], child_type_of(o))] += 1
        for f in B.fields(body):
            if f.kind in B.MODEL_FIELD_KINDS:
                for o in f.children:
                    self.nesting[(model_type, f.name, f.kind, child_type_of(o))] += 1
                continue
            real = f.real_values
            empties = len(f.values) - len(real)
            if not real:
                key = (model_type, f.name, f.kind)
                e = self.empty_only[key]
                if key not in seen_in_record:
                    e["records"] += 1
                e["empties"] += empties
                seen_in_record.add(key)
                continue
            by_type = defaultdict(int)
            for v in real:
                by_type[v.type or "(none)"] += 1
                for a in v.attrs:
                    self.attributes.add(("value", a))
                if v.type and v.type not in BASIC and v.text is not None:
                    self.sets[(v.type, v.text)] += 1
            for i, (vt, n) in enumerate(sorted(by_type.items())):
                key = (model_type, f.name, f.kind, vt)
                acc = self.fields[key]
                if key not in seen_in_record:
                    acc["records"] += 1
                    seen_in_record.add(key)
                acc["values"] += n
                if i == 0:
                    acc["empties"] += empties
                acc["max"] = max(acc["max"], len(real))


def _child_types(conn, extraction_id):
    """document -> ordinal -> model_type, as compact arrays (ordinals are dense from 0, 01 section 6.3)."""
    from array import array
    names, index, docs = [], {}, {}
    rows = conn.execute(text(
        "SELECT document_index, ordinal, model_type FROM phone_records WHERE extraction_id = :e "
        "ORDER BY document_index, ordinal").execution_options(stream_results=True, yield_per=BATCH),
        {"e": extraction_id})
    for d, o, t in rows:
        arr = docs.setdefault(d, array("H"))
        while len(arr) < o:
            arr.append(0xFFFF)
        if t not in index:
            index[t] = len(names)
            names.append(t)
        arr.append(index[t])
    return docs, names


def accumulate(conn, extraction_id) -> Accumulator:
    acc = Accumulator()
    docs, names = _child_types(conn, extraction_id)
    for (d, skel) in conn.execute(text(
            "SELECT document_index, skeleton FROM phone_extraction_documents WHERE extraction_id = :e "
            "ORDER BY document_index"), {"e": extraction_id}):
        for tag, attrs in _walk_elements(skel or [], ("project", "extractionInfo")):
            for a in attrs:
                acc.attributes.add((tag, a))
    for (a,) in conn.execute(text(
            "SELECT DISTINCT jsonb_object_keys(body->1) FROM phone_files WHERE extraction_id = :e "
            "AND jsonb_typeof(body->1) = 'object'"), {"e": extraction_id}):
        acc.attributes.add(("file", a))
    rows = conn.execute(text(
        "SELECT document_index, parent_ordinal, model_type, body FROM phone_records WHERE extraction_id = :e "
        "ORDER BY document_index, ordinal").execution_options(stream_results=True, yield_per=BATCH),
        {"e": extraction_id})
    for d, parent, mt, body in rows:
        arr = docs[d]
        acc.add_record(mt, parent is None, body, lambda o, arr=arr: names[arr[o]] if o < len(arr) and
                       arr[o] != 0xFFFF else "(unresolved)")
    return acc


def _extraction_meta(conn, extraction_id):
    row = conn.execute(text(
        "SELECT capture_state::text, report_version, producer_version FROM phone_extractions WHERE id = :e"),
        {"e": extraction_id}).one_or_none()
    if row is None:
        raise NotCaptured("extraction not found")
    if row[0] not in ("captured", "captured_incomplete"):
        raise NotCaptured("capture state is %s" % row[0])
    return {"report_version": row[1], "producer_version": row[2]}


def _invented_sql(extraction_column):
    return ("EXISTS (SELECT 1 FROM phone_extraction_documents d WHERE d.extraction_id = %s AND "
            "strpos(d.skeleton::text, :mark) > 0)" % extraction_column)


def is_invented_report(conn, extraction_id) -> bool:
    return bool(conn.execute(text("SELECT " + _invented_sql(":e")),
                             {"e": extraction_id, "mark": INVENTED_REPORT_MARK}).scalar())


def _insert(conn, table, cols: dict, conflict: str, meta, extraction_id):
    """Insert an observed row if absent; returns (id, inserted)."""
    keycols = list(cols)
    vals = dict(cols, e=extraction_id, rv=meta["report_version"], pv=meta["producer_version"])
    id_col = "type_name" if table == "phone_schema_types" else "id"
    new = conn.execute(text(
        "INSERT INTO %s (%s, origin, first_seen_extraction_id, first_seen_report_version, "
        "first_seen_producer_version) VALUES (%s, 'observed', :e, :rv, :pv) ON CONFLICT %s DO NOTHING RETURNING %s"
        % (table, ", ".join(keycols), ", ".join(":" + k for k in keycols), conflict, id_col)), vals).scalar()
    if new is not None:
        return new, True
    where = " AND ".join("%s = :%s" % (k, k) for k in keycols)
    return conn.execute(text("SELECT %s FROM %s WHERE %s" % (id_col, table, where)), cols).scalar(), False


def _flag(conn, kind, table, rid, extraction_id, detail, severity="info"):
    return conn.execute(text(
        "INSERT INTO phone_schema_flags (flag_kind, registry_table, registry_id, raised_by_extraction_id, severity, "
        "state, detail) VALUES (:k, :t, :r, :e, :s, 'open', CAST(:d AS jsonb)) "
        "ON CONFLICT (flag_kind, registry_table, registry_id) DO NOTHING RETURNING id"),
        {"k": kind, "t": table, "r": rid, "e": extraction_id, "s": severity, "d": json.dumps(detail)}).scalar()


def _type_rid(conn, type_name):
    """phone_schema_types is keyed by name (3.2); observations and flags carry a bigint registry_id, so a type's
    id there is a deterministic positive 63-bit number from its name (sha256 prefix)."""
    import hashlib
    return int.from_bytes(hashlib.sha256(type_name.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)


def observe_extraction(conn, extraction_id, named_by_mapping=frozenset()) -> dict:
    """Observation pass for one extraction (3.3). Idempotent; raises one flag per novelty.

    ``named_by_mapping`` holds registry keys a loaded mapping names (``("fields", (t, f, k))`` and
    ``("set_values", (set, value))``): a flag on one of them is ``blocks_mapping`` (3.3 step 6).
    """
    meta = _extraction_meta(conn, extraction_id)
    acc = accumulate(conn, extraction_id)
    invented = is_invented_report(conn, extraction_id)
    skipped_values = 0
    raised = []
    obs = {}  # (table, id) -> [records, values, empties]
    new_types = set()

    def sev(key):
        return "blocks_mapping" if key in named_by_mapping else "info"

    for t, a in sorted(acc.types.items()):
        _, ins = _insert(conn, "phone_schema_types", {"type_name": t}, "(type_name)", meta, extraction_id)
        rid = _type_rid(conn, t)
        if ins:
            new_types.add(t)
            fid = _flag(conn, "new_type", "types", rid, extraction_id, {"type": t, "records": a["records"]})
            raised.append(fid)
        conn.execute(text("UPDATE phone_schema_types SET seen_top_level = seen_top_level OR :top, "
                          "seen_nested = seen_nested OR :nested WHERE type_name = :t"),
                     {"top": a["top"], "nested": a["nested"], "t": t})
        obs[("types", rid)] = [a["records"], 0, 0]

    # empty-only combinations: attribute the empties to a typed row of the same (t, f, k) when one exists
    typed_here = {k[:3] for k in acc.fields}
    for (t, f, k), e in sorted(acc.empty_only.items()):
        if (t, f, k) in typed_here:
            first = min(vt for (tt, ff, kk, vt) in acc.fields if (tt, ff, kk) == (t, f, k))
            acc.fields[(t, f, k, first)]["empties"] += e["empties"]
            continue
        existing = conn.execute(text(
            "SELECT id FROM phone_schema_fields WHERE type_name = :t AND field_name = :f AND field_kind = :k "
            "ORDER BY (value_type IN ('(empty)', '(none)')), id LIMIT 1"), {"t": t, "f": f, "k": k}).scalar()
        if existing is not None:
            key = obs.setdefault(("fields", existing), [0, 0, 0])
            key[0] += e["records"]
            key[2] += e["empties"]
            continue
        vt = "(empty)" if k in ("field", "multiField") else "(none)"
        acc.fields[(t, f, k, vt)] = {"records": e["records"], "values": 0, "empties": e["empties"], "max": 0}

    for (t, f, k, vt), a in sorted(acc.fields.items()):
        prior = [r[0] for r in conn.execute(text(
            "SELECT value_type FROM phone_schema_fields WHERE type_name = :t AND field_name = :f AND field_kind = :k "
            "AND value_type <> :vt AND value_type NOT IN ('(empty)', '(none)')"),
            {"t": t, "f": f, "k": k, "vt": vt})]
        rid, ins = _insert(conn, "phone_schema_fields", {
            "type_name": t, "field_name": f, "field_kind": k, "value_type": vt,
            "is_named_set": vt not in BASIC and vt not in PLACEHOLDERS},
            "(type_name, field_name, field_kind, value_type)", meta, extraction_id)
        if ins and t not in new_types:
            if prior and vt not in PLACEHOLDERS:
                raised.append(_flag(conn, "new_value_type", "fields", rid, extraction_id,
                                    {"type": t, "field": f, "kind": k, "previous": sorted(prior), "now": vt},
                                    sev(("fields", (t, f, k)))))
            else:
                raised.append(_flag(conn, "new_field", "fields", rid, extraction_id,
                                    {"type": t, "field": f, "kind": k, "value_type": vt}, sev(("fields", (t, f, k)))))
        if a["max"] >= 2 and k == "field":
            raised.append(_flag(conn, "multi_value_field", "fields", rid, extraction_id,
                                {"type": t, "field": f, "max_values": a["max"]}))
        conn.execute(text("UPDATE phone_schema_fields SET max_values_in_one_field = GREATEST(max_values_in_one_field, "
                          ":m) WHERE id = :id"), {"m": a["max"], "id": rid})
        o = obs.setdefault(("fields", rid), [0, 0, 0])
        o[0] += a["records"]
        o[1] += a["values"]
        o[2] += a["empties"]

    for (p, f, k, c), n in sorted(acc.nesting.items()):
        rid, ins = _insert(conn, "phone_schema_nesting", {"parent_type": p, "field_name": f, "field_kind": k,
                                                           "child_type": c},
                           "(parent_type, field_name, field_kind, child_type)", meta, extraction_id)
        if ins and p not in new_types and c not in new_types:
            raised.append(_flag(conn, "new_nesting", "nesting", rid, extraction_id,
                                {"parent": p, "field": f, "kind": k, "child": c}))
        obs[("nesting", rid)] = [n, 0, 0]

    set_sizes = {}
    for (s, v), n in sorted(acc.sets.items()):
        exists = conn.execute(text("SELECT id FROM phone_schema_set_values WHERE set_name = :s AND value = :v"),
                              {"s": s, "v": v}).scalar()
        if exists is None and invented:
            skipped_values += 1
            continue
        if exists is None:
            size = set_sizes.get(s)
            if size is None:
                size = set_sizes[s] = conn.execute(text(
                    "SELECT count(*) FROM phone_schema_set_values WHERE set_name = :s"), {"s": s}).scalar()
            if size >= SET_VALUE_CAP:
                over = conn.execute(text(
                    "SELECT min(id) FROM phone_schema_set_values WHERE set_name = :s"), {"s": s}).scalar()
                raised.append(_flag(conn, "set_overflow", "set_values", over, extraction_id,
                                    {"set": s, "cap": SET_VALUE_CAP}))
                continue
            set_sizes[s] = size + 1
        rid, ins = _insert(conn, "phone_schema_set_values", {"set_name": s, "value": v[:512]},
                           "(set_name, value)", meta, extraction_id)
        new_set = ins and not conn.execute(text(
            "SELECT 1 FROM phone_schema_set_values WHERE set_name = :s AND id <> :id LIMIT 1"),
            {"s": s, "id": rid}).scalar()
        if ins and not new_set:
            raised.append(_flag(conn, "new_set_value", "set_values", rid, extraction_id, {"set": s},
                                sev(("set_values", (s, v)))))
        obs[("set_values", rid)] = [0, n, 0]

    for (el, at) in sorted(acc.attributes):
        rid, ins = _insert(conn, "phone_schema_attributes", {"element": el, "attribute": at},
                           "(element, attribute)", meta, extraction_id)
        if ins:
            raised.append(_flag(conn, "new_attribute", "attributes", rid, extraction_id,
                                {"element": el, "attribute": at}))
        obs[("attributes", rid)] = [0, 0, 0]

    previous = conn.execute(text(
        "SELECT registry_table, registry_id FROM phone_schema_observations WHERE extraction_id = :e"),
        {"e": extraction_id}).fetchall()
    conn.execute(text("DELETE FROM phone_schema_observations WHERE extraction_id = :e"), {"e": extraction_id})
    for (table, rid), (r, v, e) in obs.items():
        conn.execute(text(
            "INSERT INTO phone_schema_observations (extraction_id, registry_table, registry_id, record_count, "
            "value_count, empty_count) VALUES (:x, :t, :r, :rc, :vc, :ec)"),
            {"x": extraction_id, "t": table, "r": rid, "rc": r, "vc": v, "ec": e})
    _refresh_totals(conn)
    raised = [r for r in raised if r is not None]
    return {"flags_raised": len(raised), "flag_ids": raised, "types": len(acc.types), "fields": len(acc.fields),
            "nesting": len(acc.nesting), "set_values": len(acc.sets), "attributes": len(acc.attributes),
            "previous_observations": len(previous), "invented_values_skipped": skipped_values}


def forget_invented_values(conn, *, dry_run=False) -> dict:
    """Take out named-set values only invented test reports were seen to hold, with their observations, and dismiss
    their flags. A seed value, or a value any other report holds, stays. Each flag keeps the value in its detail and
    a dismissal event, so what was removed stays visible in the queue. Idempotent: runs with the seed."""
    params = {"mark": INVENTED_REPORT_MARK}
    rows = conn.execute(text(
        "SELECT s.id, s.set_name, s.value FROM phone_schema_set_values s WHERE s.origin = 'observed' "
        "AND s.first_seen_extraction_id IS NOT NULL AND " + _invented_sql("s.first_seen_extraction_id") +
        " AND NOT EXISTS (SELECT 1 FROM phone_schema_observations o WHERE o.registry_table = 'set_values' "
        "AND o.registry_id = s.id AND NOT " + _invented_sql("o.extraction_id") + ") ORDER BY s.id"), params).fetchall()
    ids = [r[0] for r in rows]
    overflow = conn.execute(text(
        "SELECT fl.id FROM phone_schema_flags fl WHERE fl.flag_kind = 'set_overflow' AND fl.state = 'open' "
        "AND fl.raised_by_extraction_id IS NOT NULL AND " + _invented_sql("fl.raised_by_extraction_id") +
        " ORDER BY fl.id"), params).scalars().all()
    flags = conn.execute(text(
        "SELECT id, registry_id FROM phone_schema_flags WHERE flag_kind = 'new_set_value' AND registry_table = "
        "'set_values' AND registry_id = ANY(:i) ORDER BY id"), {"i": ids}).fetchall()
    out = {"values": len(ids), "flags": len(flags) + len(overflow), "dry_run": dry_run}
    if dry_run or not (ids or overflow):
        return out
    value_of = {r[0]: r[2] for r in rows}
    for fid, rid in flags:
        conn.execute(text("UPDATE phone_schema_flags SET detail = detail || CAST(:d AS jsonb) WHERE id = :i"),
                     {"d": json.dumps({"value": value_of[rid]}), "i": fid})
    for fid in [f[0] for f in flags] + list(overflow):
        if conn.execute(text("SELECT state FROM phone_schema_flags WHERE id = :i"), {"i": fid}).scalar() != "dismissed":
            transition_flag(conn, fid, "dismissed", INVENTED_REASON, actor_name=INVENTED_ACTOR, automatic=True)
    conn.execute(text("DELETE FROM phone_schema_observations WHERE registry_table = 'set_values' AND "
                      "registry_id = ANY(:i)"), {"i": ids})
    conn.execute(text("DELETE FROM phone_schema_set_values WHERE id = ANY(:i)"), {"i": ids})
    _refresh_totals(conn)
    return out


def _refresh_totals(conn):
    """Observed totals are sums over phone_schema_observations, so re-running a pass never double counts."""
    conn.execute(text(
        "UPDATE phone_schema_fields f SET observed_value_count = COALESCE(o.v, 0), "
        "observed_empty_count = COALESCE(o.e, 0), observed_extraction_count = COALESCE(o.n, 0) "
        "FROM (SELECT f2.id, sum(o.value_count) v, sum(o.empty_count) e, count(o.extraction_id) n "
        "FROM phone_schema_fields f2 LEFT JOIN phone_schema_observations o ON o.registry_table = 'fields' "
        "AND o.registry_id = f2.id GROUP BY f2.id) o WHERE o.id = f.id"))
    conn.execute(text(
        "UPDATE phone_schema_nesting n SET observed_child_count = COALESCE(o.c, 0) FROM (SELECT n2.id, "
        "sum(o.record_count) c FROM phone_schema_nesting n2 LEFT JOIN phone_schema_observations o ON "
        "o.registry_table = 'nesting' AND o.registry_id = n2.id GROUP BY n2.id) o WHERE o.id = n.id"))
    conn.execute(text(
        "UPDATE phone_schema_set_values s SET observed_count = COALESCE(o.c, 0) FROM (SELECT s2.id, "
        "sum(o.value_count) c FROM phone_schema_set_values s2 LEFT JOIN phone_schema_observations o ON "
        "o.registry_table = 'set_values' AND o.registry_id = s2.id GROUP BY s2.id) o WHERE o.id = s.id"))
    for t in conn.execute(text("SELECT type_name FROM phone_schema_types")).scalars().all():
        rid = _type_rid(conn, t)
        r = conn.execute(text(
            "SELECT count(*), COALESCE(sum(record_count), 0) FROM phone_schema_observations WHERE "
            "registry_table = 'types' AND registry_id = :r"), {"r": rid}).one()
        conn.execute(text("UPDATE phone_schema_types SET observed_extraction_count = :n, observed_record_count = :c "
                          "WHERE type_name = :t"), {"n": r[0], "c": r[1], "t": t})


# ---- review queue (3.4) --------------------------------------------------------------------------------------------

class TransitionRefused(ValueError):
    pass


def transition_flag(conn, flag_id, to_state, reason, *, actor_name=None, actor_email=None, actor_user_id=None,
                    automatic=False) -> dict:
    """Write the event, then change the state (the rule of decisions.py:22-23). A person may not set ``mapped``."""
    if not (reason or "").strip():
        raise TransitionRefused("A reason is required.")
    row = conn.execute(text("SELECT state FROM phone_schema_flags WHERE id = :i FOR UPDATE"), {"i": flag_id}).one_or_none()
    if row is None:
        raise TransitionRefused("Flag not found.")
    allowed = TRANSITIONS if automatic else PERSON_TRANSITIONS
    if (row[0], to_state) not in allowed:
        raise TransitionRefused("A flag that is %s cannot become %s." % (row[0], to_state))
    eid = conn.execute(text(
        "INSERT INTO phone_schema_flag_events (flag_id, from_state, to_state, reason, actor_name, actor_email, "
        "actor_user_id) VALUES (:f, :fr, :to, :r, :n, :em, :u) RETURNING id"),
        {"f": flag_id, "fr": row[0], "to": to_state, "r": reason.strip(), "n": actor_name, "em": actor_email,
         "u": actor_user_id}).scalar()
    conn.execute(text("UPDATE phone_schema_flags SET state = :s WHERE id = :i"), {"s": to_state, "i": flag_id})
    return {"flag_id": flag_id, "from": row[0], "to": to_state, "event_id": eid}


def list_flags(conn, state=None) -> list:
    sql = ("SELECT id, flag_kind, registry_table, registry_id, raised_by_extraction_id, severity, state, detail, "
           "raised_at FROM phone_schema_flags")
    params = {}
    if state:
        sql += " WHERE state = :s"
        params["s"] = state
    return [dict(r._mapping) for r in conn.execute(text(sql + " ORDER BY id"), params)]


FLAG_STATES = ("open", "acknowledged", "mapping_needed", "mapped", "dismissed")
FLAG_PAGE_MAX = 200


def _flag_subject(r) -> dict:
    """What a flag is about, from the registry row it points at (structure only, 3.1)."""
    d = r.detail or {}
    t = r.registry_table
    if t == "types":
        return {"type": d.get("type")}
    if t == "fields":
        return {"type": d.get("type") or r.f_type, "field": d.get("field") or r.f_field,
                "kind": d.get("kind") or r.f_kind, "value_type": d.get("value_type") or r.f_value_type}
    if t == "nesting":
        return {"type": d.get("parent") or r.n_parent, "field": d.get("field") or r.n_field,
                "child": d.get("child") or r.n_child}
    if t == "set_values":
        return {"set": d.get("set") or r.s_set,
                "value": (r.s_value or d.get("value")) if r.flag_kind == "new_set_value" else None}
    if t == "attributes":
        return {"element": d.get("element") or r.a_element, "attribute": d.get("attribute") or r.a_attribute}
    return {}


def list_flags_page(conn, state=None, limit=100, offset=0) -> dict:
    """One page of flags in id order, the total for the state filter, the count per state, and for each flag what
    it is about, the raising phone (its case and label, for the link) and its last event."""
    from services.phone.readings import phone_labels
    limit = max(1, min(int(limit), FLAG_PAGE_MAX))
    offset = max(0, int(offset))
    params = {"lim": limit, "off": offset}
    w = ""
    if state:
        w = " WHERE fl.state = :s"
        params["s"] = state
    total = conn.execute(text("SELECT count(*) FROM phone_schema_flags fl" + w), params).scalar()
    counts = {s: 0 for s in FLAG_STATES}
    for s, n in conn.execute(text("SELECT state, count(*) FROM phone_schema_flags GROUP BY 1")):
        counts[s] = int(n)
    rows = conn.execute(text(
        "SELECT fl.id, fl.flag_kind, fl.registry_table, fl.registry_id, fl.raised_by_extraction_id, fl.severity, "
        "fl.state, fl.detail, fl.raised_at, f.type_name AS f_type, f.field_name AS f_field, "
        "f.field_kind AS f_kind, f.value_type AS f_value_type, n.parent_type AS n_parent, n.field_name AS n_field, "
        "n.child_type AS n_child, sv.set_name AS s_set, sv.value AS s_value, at.element AS a_element, "
        "at.attribute AS a_attribute, x.case_id AS ext_case_id, c.title AS case_title, "
        "ev.to_state AS last_to, ev.reason AS last_reason, ev.actor_name AS last_actor, ev.created_at AS last_at "
        "FROM phone_schema_flags fl "
        "LEFT JOIN phone_schema_fields f ON fl.registry_table = 'fields' AND f.id = fl.registry_id "
        "LEFT JOIN phone_schema_nesting n ON fl.registry_table = 'nesting' AND n.id = fl.registry_id "
        "LEFT JOIN phone_schema_set_values sv ON fl.registry_table = 'set_values' AND sv.id = fl.registry_id "
        "LEFT JOIN phone_schema_attributes at ON fl.registry_table = 'attributes' AND at.id = fl.registry_id "
        "LEFT JOIN phone_extractions x ON x.id = fl.raised_by_extraction_id "
        "LEFT JOIN cases c ON c.id = x.case_id "
        "LEFT JOIN LATERAL (SELECT to_state, reason, actor_name, created_at FROM phone_schema_flag_events e "
        "WHERE e.flag_id = fl.id ORDER BY e.id DESC LIMIT 1) ev ON true" + w +
        " ORDER BY fl.id LIMIT :lim OFFSET :off"), params).fetchall()
    labels = {}
    out = []
    for r in rows:
        raised = None
        if r.raised_by_extraction_id is not None and r.ext_case_id is not None:
            cid = str(r.ext_case_id)
            if cid not in labels:
                labels[cid] = phone_labels(conn, cid)
            eid = str(r.raised_by_extraction_id)
            raised = {"extraction_id": eid, "case_id": cid, "case_title": r.case_title,
                      "label": labels[cid].get(eid), "link": "/cases/%s/phones/%s" % (cid, eid)}
        elif r.raised_by_extraction_id is not None:
            raised = {"extraction_id": str(r.raised_by_extraction_id), "case_id": None, "case_title": None,
                      "label": None, "link": None}
        out.append({"id": r.id, "flag_kind": r.flag_kind, "registry_table": r.registry_table,
                    "registry_id": r.registry_id, "severity": r.severity, "state": r.state,
                    "detail": r.detail, "raised_at": r.raised_at.isoformat(), "subject": _flag_subject(r),
                    "raised_by_extraction_id": str(r.raised_by_extraction_id) if r.raised_by_extraction_id else None,
                    "raised_by": raised,
                    "last_event": ({"to": r.last_to, "reason": r.last_reason, "by": r.last_actor,
                                    "at": r.last_at.isoformat()} if r.last_to else None)})
    return {"total": int(total), "limit": limit, "offset": offset, "counts": counts, "flags": out}


def mapping_backlog(conn, extraction_id) -> dict:
    """Flags in ``mapping_needed`` that touch this phone (raised by it, or on a registry row it was observed to
    hold): the backlog 3.4 says the coverage map shows. Bounded by the registry's size; every item is returned."""
    rows = conn.execute(text(
        "SELECT DISTINCT fl.id, fl.flag_kind, fl.registry_table, fl.detail, f.type_name AS f_type, "
        "f.field_name AS f_field, f.field_kind AS f_kind, f.value_type AS f_value_type, n.parent_type AS n_parent, "
        "n.field_name AS n_field, n.child_type AS n_child, sv.set_name AS s_set, sv.value AS s_value, "
        "at.element AS a_element, at.attribute AS a_attribute "
        "FROM phone_schema_flags fl "
        "LEFT JOIN phone_schema_observations o ON o.extraction_id = :e AND o.registry_table = fl.registry_table "
        "AND o.registry_id = fl.registry_id "
        "LEFT JOIN phone_schema_fields f ON fl.registry_table = 'fields' AND f.id = fl.registry_id "
        "LEFT JOIN phone_schema_nesting n ON fl.registry_table = 'nesting' AND n.id = fl.registry_id "
        "LEFT JOIN phone_schema_set_values sv ON fl.registry_table = 'set_values' AND sv.id = fl.registry_id "
        "LEFT JOIN phone_schema_attributes at ON fl.registry_table = 'attributes' AND at.id = fl.registry_id "
        "WHERE fl.state = 'mapping_needed' AND (fl.raised_by_extraction_id = :e OR o.extraction_id IS NOT NULL) "
        "ORDER BY fl.id"), {"e": str(extraction_id)}).fetchall()
    items = [{"flag_id": r.id, "flag_kind": r.flag_kind, "subject": _flag_subject(r)} for r in rows]
    return {"total": len(items), "items": items}
