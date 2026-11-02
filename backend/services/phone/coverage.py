"""Coverage map of one extraction (docs/cellebrite/02 section 7).

Per extraction, per observed (type, field, kind, value type), per nesting (parent, field, child type) and per
record attribute, the level at which Loupe reads it:

- ``reviewed``: a loaded ``type`` mapping of the type names the field, is not suspended on this extraction, and is
  ``reviewed`` or every rule naming the field was confirmed (or corrected) by a person on this extraction (6.7).
- ``applied_unconfirmed``: as ``reviewed``, but a rule naming the field is still open here; shown as "Mapped by the
  system, not yet confirmed" (6.10).
- ``suspended``: a loaded mapping names it but is suspended on this extraction (6.7); the reason is listed.
- ``generic_role``: the value type, child type or field has a role in 5.2 other than text; ``level_detail`` says
  which (``time``, ``duration``, ``direction``, ``party_role``, ``owner_flag``, ``user_mapping``,
  ``affiliation``, ``file_reference``, ``party``, ``coordinate``, ``identifier``, ``address``).
- ``generic_text``: a String with no other role (searchable; ``sensitive`` when 5.5 excludes it from default
  search).
- ``captured_only``: anything else (Boolean, Int, Double, Guid, named sets with no role, empty-only fields).

Computed on read from ``phone_schema_observations``, the registry, the loaded mapping set, this extraction's
latest applications and its judgement calls; nothing is stored that could go stale (7.1). ``selection`` is the
production's own statement, verbatim from every ``extractionInfo`` element (7.2): strings as captured, ``None``
when absent.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

from services.phone.mappings import apply, loader

SELECTION_FLAGS = ("IsSelectiveExtraction", "IsPartialData", "IsStoppedByUser", "IsTriageExtraction")
INFO_KEYS = ("index", "name", "type")

ROLE_VALUE_TYPES = {"TimeStamp": "time", "TimeSpan": "duration", "ModelDirections": "direction",
                    "PartyRole": "party_role", "DecodingSourceOptions": "user_mapping"}
ROLE_FIELDS = {"IsPhoneOwner": "owner_flag", "UserMapping": "user_mapping", "DeviceLocationAffiliation": "affiliation",
               "AccountLocationAffiliation": "affiliation", "UrlCacheFile": "file_reference"}
ROLE_CHILD_TYPES = {"Party": "party", "Coordinate": "coordinate", "PhoneNumber": "identifier", "UserID": "identifier",
                    "EmailAddress": "identifier", "StreetAddress": "address"}
TEXT_CHILD_TYPES = {"WebAddress"}
ROLE_ATTRIBUTES = {"deleted_state", "decoding_confidence", "file_id"}
PLACEHOLDERS = ("(empty)", "(none)")
LEVELS = ("reviewed", "applied_unconfirmed", "suspended", "generic_role", "generic_text", "captured_only")


class NotFound(LookupError):
    pass


def generic_level(type_name, field_name, value_type, *, child=False, sensitive=frozenset()):
    """(level, detail) of 5.2 for a value no loaded mapping names."""
    if child:
        if value_type in ROLE_CHILD_TYPES:
            return "generic_role", ROLE_CHILD_TYPES[value_type]
        if value_type in TEXT_CHILD_TYPES:
            return "generic_text", "text"
        return "captured_only", "nested_record"  # the child's own fields are listed under its type
    if field_name in ROLE_FIELDS:
        return "generic_role", ROLE_FIELDS[field_name]
    if field_name.endswith("_extracted_path"):
        return "generic_role", "file_reference"
    if value_type in ROLE_VALUE_TYPES:
        return "generic_role", ROLE_VALUE_TYPES[value_type]
    if value_type == "String":
        return "generic_text", "sensitive" if (type_name, field_name) in sensitive else "text"
    return "captured_only", None


def named_fields(m):
    """{field name: [rule ids]} a ``type`` mapping names (any role, 7.1); a field no rule lists belongs to the
    mapping's ``record`` rule."""
    t, b, rules = apply.rules_of(m)
    out = defaultdict(list)
    for r in rules:
        for f in r["fields"]:
            if f:
                out[f].append(r["rule_id"])
    record = "%s.record" % m.name
    extra = [b.event_time.field, b.end_time.field, b.end_time.duration_field, b.participants.direction_field,
             b.thread.group_field, b.app_field, b.account_field, b.title]
    extra += list(b.participants.containers) + list(b.text_fields) + list(b.status_fields.values())
    extra += [o.get("field") for o in b.other_times if isinstance(o, dict)]
    extra += [v for v in (b.place or {}).values() if isinstance(v, str)]
    for f in extra:
        if f and f not in out:
            out[f].append(record)
    return t, dict(out)


def selection(conn, extraction_id):
    infos, flags = [], {k: [] for k in SELECTION_FLAGS}
    from services.phone import registry
    for (skel,) in conn.execute(text("SELECT skeleton FROM phone_extraction_documents WHERE extraction_id = :e "
                                     "ORDER BY document_index"), {"e": extraction_id}):
        for _, attrs in registry._walk_elements(skel or [], ("extractionInfo",)):
            infos.append(attrs)
    infos.sort(key=lambda a: (len(str(a.get("index", ""))), str(a.get("index", ""))))
    out = {}
    for k in SELECTION_FLAGS:
        seen = [a.get(k) for a in infos]
        distinct = list(dict.fromkeys(seen))
        # one value when every element states the same (None when none states it); the distinct values in
        # element order when they differ, so a disagreement is never folded into one answer
        out[k] = distinct[0] if len(distinct) == 1 else (None if not distinct else distinct)
    out["per_extraction_info"] = [dict({k: a.get(k) for k in INFO_KEYS},
                                       **{k: a[k] for k in SELECTION_FLAGS if k in a}) for a in infos]
    return out


def compute(conn, extraction_id, case_id=None, mappings=None) -> dict:
    ext = conn.execute(text("SELECT id, case_id FROM phone_extractions WHERE id = :e"), {"e": extraction_id}).one_or_none()
    if ext is None or (case_id is not None and str(ext[1]) != str(case_id)):
        raise NotFound("extraction not found")
    ms = [m for m in (loader.loaded() if mappings is None else mappings) if m.kind == "type"]
    sensitive = loader.sensitive_fields(mappings) if mappings is not None else loader.sensitive_fields()

    types = _types(conn, extraction_id)
    fields = conn.execute(text(
        "SELECT f.type_name, f.field_name, f.field_kind, f.value_type, o.record_count, o.value_count, o.empty_count "
        "FROM phone_schema_observations o JOIN phone_schema_fields f ON f.id = o.registry_id "
        "WHERE o.extraction_id = :e AND o.registry_table = 'fields' ORDER BY 1, 2, 3, 4"), {"e": extraction_id}).fetchall()
    nesting = conn.execute(text(
        "SELECT n.parent_type, n.field_name, n.field_kind, n.child_type, o.record_count FROM phone_schema_observations o "
        "JOIN phone_schema_nesting n ON n.id = o.registry_id WHERE o.extraction_id = :e AND "
        "o.registry_table = 'nesting' ORDER BY 1, 2, 3, 4"), {"e": extraction_id}).fetchall()
    attributes = conn.execute(text(
        "SELECT a.element, a.attribute FROM phone_schema_observations o JOIN phone_schema_attributes a ON "
        "a.id = o.registry_id WHERE o.extraction_id = :e AND o.registry_table = 'attributes' ORDER BY 1, 2"),
        {"e": extraction_id}).fetchall()

    gen = conn.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                       {"e": extraction_id}).scalar()
    suspended = {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT mapping_version_id, suspension_reasons FROM phone_mapping_applications WHERE extraction_id = :e "
        "AND generation = :g AND records_suspended > 0"), {"e": extraction_id, "g": gen})} if gen else {}
    resolved = {(r[0], str(r[1])): r[2] for r in conn.execute(text(
        "SELECT rule_id, mapping_version_id, status FROM phone_mapping_judgements WHERE extraction_id = :e"),
        {"e": extraction_id})}

    by_type = {}
    for m in ms:
        t, named = named_fields(m)
        if t in types:
            by_type[t] = (m, named)

    def mapped_level(t, f):
        if t not in by_type or f not in by_type[t][1]:
            return None
        m, named = by_type[t]
        if str(m.id) in suspended:
            return "suspended", {"reasons": suspended[str(m.id)]}
        rules = named[f]
        done = all(resolved.get((r, str(m.id))) in ("confirmed", "corrected") for r in rules)
        lvl = "reviewed" if (m.status == "reviewed" or done) else "applied_unconfirmed"
        return lvl, {"rules": rules}

    out_types = {t: {"type": t, "records": v["records"], "top_level": v["top"], "nested": v["nested"],
                     "level": "generic", "mapping_version_id": None, "mapping_name": None, "fields": []}
                 for t, v in sorted(types.items())}
    for t, (m, _) in by_type.items():
        ot = out_types[t]
        ot["mapping_version_id"], ot["mapping_name"] = str(m.id), m.name
        if str(m.id) in suspended:
            ot["level"] = "suspended"
            ot["suspension_reasons"] = suspended[str(m.id)]
        else:
            rules = {r for rr in by_type[t][1].values() for r in rr}
            done = all(resolved.get((r, str(m.id))) in ("confirmed", "corrected") for r in rules)
            ot["level"] = "reviewed" if (m.status == "reviewed" or done) else "applied_unconfirmed"

    counts = defaultdict(int)
    for t, f, k, vt, recs, vals, empties in fields:
        mapped = mapped_level(t, f)
        if vt in PLACEHOLDERS:
            lvl, detail = "captured_only", "empty_only"
        else:
            lvl, detail = generic_level(t, f, vt, sensitive=sensitive)
        row = {"field": f, "kind": k, "value_type": vt, "records": int(recs), "values": int(vals),
               "empties": int(empties), "level": lvl, "level_detail": detail}
        if mapped:
            row["generic_level"], row["level"] = lvl, mapped[0]
            row.update(mapped[1])
        counts[row["level"]] += 1
        out_types.setdefault(t, _absent_type(t))["fields"].append(row)
    for parent, f, k, child, recs in nesting:
        lvl, detail = generic_level(parent, f, child, child=True)
        row = {"field": f, "kind": k, "value_type": child, "records": int(recs), "values": int(recs), "empties": 0,
               "level": lvl, "level_detail": detail}
        mapped = mapped_level(parent, f)
        if mapped:
            row["generic_level"], row["level"] = lvl, mapped[0]
            row.update(mapped[1])
        counts[row["level"]] += 1
        out_types.setdefault(parent, _absent_type(parent))["fields"].append(row)

    records_by_level = defaultdict(int)
    for ot in out_types.values():
        records_by_level[ot["level"]] += ot["records"]
    plain = [r for r in fields if r[2] == "field" and r[3] not in PLACEHOLDERS]
    summary = {"types": len(types), "top_level_types": sum(1 for v in types.values() if v["top"]),
               "nested_only_types": sum(1 for v in types.values() if v["nested"] and not v["top"]),
               "fields": len(plain), "multi_fields": sum(1 for r in fields if r[2] == "multiField"),
               "empty_only_fields": sum(1 for r in fields if r[3] in PLACEHOLDERS), "nestings": len(nesting),
               "combinations_listed": len(fields) + len(nesting),
               **{lvl: counts.get(lvl, 0) for lvl in LEVELS},
               "records_by_level": dict(sorted(records_by_level.items())),
               "unconfirmed_calls": sum(1 for (r, mv), st in resolved.items() if st == "open"
                                        and any(str(m.id) == mv for m, _ in by_type.values()))}
    flags = [{"id": r[0], "flag_kind": r[1], "state": r[2], "severity": r[3],
              "type": (r[4] or {}).get("type"), "field": (r[4] or {}).get("field")}
             for r in conn.execute(text(
                 "SELECT DISTINCT fl.id, fl.flag_kind, fl.state, fl.severity, fl.detail FROM phone_schema_flags fl "
                 "LEFT JOIN phone_schema_observations o ON o.extraction_id = :e AND o.registry_table = fl.registry_table "
                 "AND o.registry_id = fl.registry_id WHERE fl.raised_by_extraction_id = :e OR o.extraction_id IS NOT NULL "
                 "ORDER BY fl.id"), {"e": extraction_id})]
    return {"extraction_id": str(extraction_id), "case_id": str(ext[1]), "generation": gen,
            "selection": selection(conn, extraction_id), "summary": summary,
            "attributes": [{"element": el, "attribute": a,
                            "level": "generic_role" if el == "model" and a in ROLE_ATTRIBUTES else "captured_only"}
                           for el, a in attributes],
            "types": list(out_types.values()), "flags": flags}


def _absent_type(t):
    return {"type": t, "records": 0, "top_level": False, "nested": False, "level": "generic",
            "mapping_version_id": None, "mapping_name": None, "fields": []}


def _types(conn, extraction_id):
    from services.phone import registry
    by_rid = {}
    for n, top, nested in conn.execute(text("SELECT type_name, seen_top_level, seen_nested FROM phone_schema_types")):
        by_rid[registry._type_rid(conn, n)] = (n, top, nested)
    top_here = {r[0]: (r[1], r[2]) for r in conn.execute(text(
        "SELECT model_type, bool_or(parent_ordinal IS NULL), bool_or(parent_ordinal IS NOT NULL) FROM phone_records "
        "WHERE extraction_id = :e GROUP BY 1"), {"e": extraction_id})}
    out = {}
    for rid, n in conn.execute(text("SELECT registry_id, record_count FROM phone_schema_observations WHERE "
                                    "extraction_id = :e AND registry_table = 'types'"), {"e": extraction_id}):
        if rid in by_rid:
            name = by_rid[rid][0]
            top, nested = top_here.get(name, (False, False))
            out[name] = {"records": int(n), "top": bool(top), "nested": bool(nested)}
    return out
