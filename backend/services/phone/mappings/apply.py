"""Applying the loaded ``type`` mappings to one extraction's generic rows (02 section 6.7).

Runs inside the sweep's transaction after the generic rows of generation n+1 are written (5.7). For each loaded
``type`` mapping whose type occurs in the extraction:

1. Suspension. A registry requirement absent from the registry, or a (type, field, kind) of a requirement that
   this extraction observed under an open ``new_value_type`` or ``blocks_mapping`` flag, suspends the mapping
   for this extraction only. Generic rows stand; ``phone_mapping_applications`` records the reason.
2. Otherwise each part of the mapping is a **rule** with its own id (``<name>.event_time``, ``<name>.end_time``,
   ``<name>.role.<From>``, ``<name>.text``, ``<name>.record``). The rule marks the generic rows it covers with
   ``mapping_version_id``, ``mapping_row_id`` and ``interpretation_level``: ``reviewed`` when the version is
   reviewed or a person confirmed this rule on this extraction, otherwise ``applied_unconfirmed``.
3. One judgement call per (extraction, rule, version) in ``phone_mapping_judgements`` (Neil, 2026-10-29): the
   rule in plain words, the records it touched (count and three sample record ids drawn across the set), and
   the evidence (the registry fields it rests on with this extraction's counts).

A person's correction (``correct_phone_reading``, 8.8) replaces the rule's choice for that extraction; the
applier reads it through ``register_reading_decisions`` and re-derives from the generic rows, never from a new
capture. Nothing here reads ``phone_mapping_proposals``.
"""
from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import text

from services.phone.mappings import loader

JUDGEMENT_NS = uuid.UUID("0d8f3b9a-4c55-4e0e-8a3b-7e1c2f6d9b40")
OPEN_FLAG_STATES = ("open", "mapping_needed")
_hooks = {"reading_decisions": None}


def register_reading_decisions(fn):
    """``fn(conn, extraction_id) -> {(rule_id, mapping_version_id): {"decision": "confirm"|"correct",
    "choice": ..., "decision_id": ..., "by": ..., "by_email": ..., "at": ..., "reason": ...}}``."""
    _hooks["reading_decisions"] = fn


def reading_decisions(conn, extraction_id):
    fn = _hooks["reading_decisions"]
    return fn(conn, extraction_id) if fn else {}


def words(name):
    """``TimeStamp`` -> ``time stamp``; ``InstantMessage`` -> ``instant message``."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|_", " ", name or "").lower().strip()


# ---- suspension -------------------------------------------------------------------------------------------------

def suspension_reasons(conn, m, extraction_id):
    reasons = []
    for t, f, k, vt in m.requirements:
        n = conn.execute(text("SELECT count(*) FROM phone_schema_fields WHERE type_name = :t AND field_name = :f AND "
                              "field_kind = :k AND value_type = :v"), {"t": t, "f": f, "k": k, "v": vt}).scalar()
        if not n:
            reasons.append({"reason": "requirement_absent", "requirement": [t, f, k, vt]})
        flagged = conn.execute(text(
            "SELECT fl.id, fl.flag_kind, fl.severity, sf.value_type FROM phone_schema_flags fl "
            "JOIN phone_schema_fields sf ON fl.registry_table = 'fields' AND sf.id = fl.registry_id "
            "JOIN phone_schema_observations o ON o.registry_table = 'fields' AND o.registry_id = sf.id "
            "AND o.extraction_id = :e WHERE sf.type_name = :t AND sf.field_name = :f AND sf.field_kind = :k "
            "AND fl.state = ANY(CAST(:states AS text[])) AND (fl.flag_kind = 'new_value_type' OR "
            "fl.severity = 'blocks_mapping') ORDER BY fl.id"),
            {"e": extraction_id, "t": t, "f": f, "k": k, "states": list(OPEN_FLAG_STATES)}).fetchall()
        for fid, kind, sev, value_type in flagged:
            reasons.append({"reason": "open_flag", "flag_id": fid, "flag_kind": kind, "severity": sev,
                            "requirement": [t, f, k, vt], "observed_value_type": value_type})
    return reasons


# ---- rules of a type mapping --------------------------------------------------------------------------------------

def rules_of(m):
    """[(rule_id, rule_part, table, where-sql, params, summary, choice, evidence fields)] for one type mapping."""
    b = loader.TypeBody.model_validate(m.body)
    t = b.applies_to
    tw = words(t)
    out = []
    if b.event_time.field:
        out.append({"rule_id": "%s.event_time" % m.name, "part": "event_time", "choice": b.event_time.field,
                    "summary": "The time shown as when each %s happened is its %s." % (tw, words(b.event_time.field)),
                    "fields": [b.event_time.field]})
    if b.end_time.field or b.end_time.duration_field:
        f = b.end_time.field or b.end_time.duration_field
        out.append({"rule_id": "%s.end_time" % m.name, "part": "end_time",
                    "choice": {"field": b.end_time.field, "duration_field": b.end_time.duration_field},
                    "summary": ("Each %s ends at its %s." % (tw, words(f))) if b.end_time.field else
                               ("Each %s ends at its start plus its %s (computed)." % (tw, words(f))),
                    "fields": [f]})
    for key, role in sorted(b.participants.role_map.items()):
        out.append({"rule_id": "%s.role.%s" % (m.name, key), "part": "role", "choice": role, "key": key,
                    "summary": "In each %s, the party marked %s is the %s." % (tw, words(key), words(role)),
                    "fields": list(b.participants.containers) or [key]})
    if b.text_fields:
        out.append({"rule_id": "%s.text" % m.name, "part": "text", "choice": list(b.text_fields),
                    "summary": "The words of each %s are its %s." % (tw, " and ".join(words(x) for x in b.text_fields)),
                    "fields": list(b.text_fields)})
    out.append({"rule_id": "%s.record" % m.name, "part": "record", "choice": b.comm_kind or "record",
                "summary": "Each %s is read as %s." % (tw, ("a %s" % words(b.comm_kind)) if b.comm_kind else
                                                       "a record of its own kind"),
                "fields": []})
    return t, b, out


def _mark(conn, table, where, params, rule_id, version_id, level, extraction_id, generation, sets=""):
    r = conn.execute(text(
        "UPDATE %s SET mapping_version_id = :mv, mapping_row_id = :rid, interpretation_level = :lvl%s "
        "WHERE extraction_id = :e AND generation = :g AND %s" % (table, sets, where)),
        dict(params, mv=version_id, rid=rule_id, lvl=level, e=extraction_id, g=generation))
    return r.rowcount


TABLE_OF_PART = {"event_time": "phone_time_values", "end_time": "phone_time_values", "role": "phone_participations",
                 "text": "phone_texts", "record": "phone_record_summaries"}


def _apply_rule(conn, rule, t, b, version_id, level, extraction_id, generation):
    part, choice = rule["part"], rule["choice"]
    if part == "event_time":
        conn.execute(text("UPDATE phone_time_values SET is_event_time = false WHERE extraction_id = :e AND "
                          "generation = :g AND model_type = :t"), {"e": extraction_id, "g": generation, "t": t})
        return _mark(conn, "phone_time_values", "model_type = :t AND field_name = :f", {"t": t, "f": choice},
                     rule["rule_id"], version_id, level, extraction_id, generation, ", is_event_time = true")
    if part == "end_time":
        if choice.get("field"):
            return _mark(conn, "phone_time_values", "model_type = :t AND field_name = :f",
                         {"t": t, "f": choice["field"]}, rule["rule_id"], version_id, level, extraction_id, generation)
        # A computed end (start plus duration) has no generic row of its own: the record's summary row belongs to
        # the ``record`` rule, and the comm event that carries the end (6.9) names this rule.
        return 0
    if part == "role":
        containers = list(b.participants.containers)
        if containers:
            where = "model_type = :t AND container_field = ANY(CAST(:cs AS text[])) AND role_in_record = :k"
        else:
            where = "model_type = :t AND container_field = :k"
        r = conn.execute(text(
            "UPDATE phone_participations SET mapping_version_id = :mv, mapping_row_id = :rid, "
            "interpretation_level = :lvl, role = :role, role_basis = 'mapping' WHERE extraction_id = :e AND "
            "generation = :g AND " + where),
            {"t": t, "k": rule["key"], "cs": containers, "mv": version_id, "rid": rule["rule_id"], "lvl": level,
             "role": choice, "e": extraction_id, "g": generation})
        return r.rowcount
    if part == "text":
        return _mark(conn, "phone_texts", "model_type = :t AND field_name = ANY(CAST(:fs AS text[]))",
                     {"t": t, "fs": list(choice)}, rule["rule_id"], version_id, level, extraction_id, generation)
    if part == "record":
        return _mark(conn, "phone_record_summaries", "model_type = :t", {"t": t}, rule["rule_id"], version_id,
                     level, extraction_id, generation)
    raise ValueError(part)


def _touched(conn, table, rule_id, extraction_id, generation, rule=None, type_name=None):
    if rule is not None and rule["part"] == "end_time" and not rule["choice"].get("field"):
        where = ("extraction_id = :e AND generation = :g AND model_type = :t AND duration_seconds IS NOT NULL")
        p = {"e": extraction_id, "g": generation, "t": type_name}
        n = conn.execute(text("SELECT count(*) FROM phone_record_summaries WHERE " + where), p).scalar()
        samples = [r[0] for r in conn.execute(text("SELECT record_uid FROM phone_record_summaries WHERE " + where +
                                                   " ORDER BY md5(record_uid::text) LIMIT 3"), p)]
        return n, samples
    n = conn.execute(text("SELECT count(DISTINCT record_uid) FROM %s WHERE extraction_id = :e AND generation = :g "
                          "AND mapping_row_id = :r" % table), {"e": extraction_id, "g": generation, "r": rule_id}).scalar()
    samples = [r[0] for r in conn.execute(text(
        "SELECT record_uid FROM (SELECT DISTINCT record_uid FROM %s WHERE extraction_id = :e AND generation = :g AND "
        "mapping_row_id = :r) s ORDER BY md5(record_uid::text) LIMIT 3" % table),
        {"e": extraction_id, "g": generation, "r": rule_id})]
    return n, samples


def _evidence(conn, t, fields, extraction_id):
    out = []
    for f in fields:
        for r in conn.execute(text(
                "SELECT sf.field_name, sf.field_kind, sf.value_type, sf.is_named_set, coalesce(o.record_count, 0), "
                "coalesce(o.value_count, 0) FROM phone_schema_fields sf LEFT JOIN phone_schema_observations o ON "
                "o.registry_table = 'fields' AND o.registry_id = sf.id AND o.extraction_id = :e WHERE sf.type_name = :t "
                "AND sf.field_name = :f ORDER BY sf.field_kind, sf.value_type"), {"e": extraction_id, "t": t, "f": f}):
            out.append({"type": t, "field": r[0], "kind": r[1], "value_type": r[2], "named_set": r[3],
                        "records_here": int(r[4]), "values_here": int(r[5])})
    return out


def judgement_id(extraction_id, rule_id, version_id):
    return uuid.uuid5(JUDGEMENT_NS, "%s|%s|%s" % (extraction_id, rule_id, version_id))


def apply_extraction(conn, extraction_id, generation, mappings=None) -> dict:
    """The sweep's applier hook (6.7)."""
    ms = loader.loaded() if mappings is None else mappings
    case_id = conn.execute(text("SELECT case_id FROM phone_extractions WHERE id = :e"), {"e": extraction_id}).scalar()
    present = {r[0]: r[1] for r in conn.execute(text(
        "SELECT model_type, count(*) FROM phone_record_summaries WHERE extraction_id = :e AND generation = :g "
        "GROUP BY model_type"), {"e": extraction_id, "g": generation})}
    decisions = reading_decisions(conn, extraction_id)
    stats = {"mappings_applied": 0, "mappings_suspended": 0, "rules": 0, "rows_marked": 0, "judgements_open": 0}
    for m in ms:
        if m.kind != "type":
            continue
        t, b, rules = rules_of(m)
        if t not in present:
            continue
        reasons = suspension_reasons(conn, m, extraction_id)
        if reasons:
            conn.execute(text(
                "INSERT INTO phone_mapping_applications (extraction_id, mapping_version_id, generation, records_matched, "
                "records_suspended, suspension_reasons) VALUES (:e, :mv, :g, 0, :n, CAST(:r AS jsonb))"),
                {"e": extraction_id, "mv": m.id, "g": generation, "n": present[t], "r": json.dumps(reasons)})
            stats["mappings_suspended"] += 1
            continue
        for rule in rules:
            d = decisions.get((rule["rule_id"], str(m.id)))
            if d and d["decision"] == "correct":
                rule = dict(rule, choice=d["choice"])
            level = "reviewed" if (m.status == "reviewed" or d) else "applied_unconfirmed"
            marked = _apply_rule(conn, rule, t, b, m.id, level, extraction_id, generation)
            stats["rows_marked"] += marked
            stats["rules"] += 1
            n, samples = _touched(conn, TABLE_OF_PART[rule["part"]], rule["rule_id"], extraction_id, generation,
                                  rule, t)
            status = "open"
            if m.status == "reviewed":
                status = "confirmed"
            if d:
                status = "confirmed" if d["decision"] == "confirm" else "corrected"
            evidence = {"fields": _evidence(conn, t, rule["fields"], extraction_id), "choice": rule["choice"],
                        "mapping": {"kind": m.kind, "name": m.name, "version": m.version, "status": m.status,
                                    "origin": m.origin, "basis": m.content["review"]["basis"]}}
            conn.execute(text(
                "INSERT INTO phone_mapping_judgements (id, case_id, extraction_id, mapping_version_id, mapping_kind, "
                "mapping_name, rule_id, type_name, rule_part, summary, strength, records_touched, sample_record_uids, "
                "evidence, status, resolved_by, resolved_by_email, resolved_at, resolution_reason, adjudication_id, "
                "generation) VALUES (:id, :c, :e, :mv, :k, :n, :r, :t, :p, :s, 'inferred', :cnt, "
                "CAST(:samples AS uuid[]), CAST(:ev AS jsonb), :st, :rb, :rbe, :ra, :rr, :adj, :g) "
                "ON CONFLICT (extraction_id, rule_id, mapping_version_id) DO UPDATE SET summary = EXCLUDED.summary, "
                "records_touched = EXCLUDED.records_touched, sample_record_uids = EXCLUDED.sample_record_uids, "
                "evidence = EXCLUDED.evidence, status = EXCLUDED.status, resolved_by = EXCLUDED.resolved_by, "
                "resolved_by_email = EXCLUDED.resolved_by_email, resolved_at = EXCLUDED.resolved_at, "
                "resolution_reason = EXCLUDED.resolution_reason, adjudication_id = EXCLUDED.adjudication_id, "
                "generation = EXCLUDED.generation, updated_at = now()"),
                {"id": judgement_id(extraction_id, rule["rule_id"], m.id), "c": case_id, "e": extraction_id,
                 "mv": m.id, "k": m.kind, "n": m.name, "r": rule["rule_id"], "t": t, "p": rule["part"],
                 "s": rule["summary"], "cnt": n, "samples": [str(x) for x in samples],
                 "ev": json.dumps(evidence, default=str), "st": status,
                 "rb": (d or {}).get("by"), "rbe": (d or {}).get("by_email"), "ra": (d or {}).get("at"),
                 "rr": (d or {}).get("reason"), "adj": (d or {}).get("decision_id"), "g": generation})
            if status == "open":
                stats["judgements_open"] += 1
        conn.execute(text(
            "INSERT INTO phone_mapping_applications (extraction_id, mapping_version_id, generation, records_matched, "
            "records_suspended, suspension_reasons) VALUES (:e, :mv, :g, :n, 0, '[]'::jsonb)"),
            {"e": extraction_id, "mv": m.id, "g": generation, "n": present[t]})
        stats["mappings_applied"] += 1
    return stats
