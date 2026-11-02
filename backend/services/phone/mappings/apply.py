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
    if b.comm_kind not in (None, "thread") and b.thread.strategy != "none":
        how = {"parent_chat": "the chat it sits in" + (", or the set of other parties when it is not in a chat"
                                                       if b.thread.fallback == "counterpart_set" else ""),
               "counterpart_set": "the set of other parties and the app",
               "field": "its %s and its subject without reply and forward prefixes" % words(b.thread.group_field),
               "self": "one list per phone"}[b.thread.strategy]
        out.append({"rule_id": "%s.thread" % m.name, "part": "thread", "choice": b.thread.model_dump(),
                    "summary": "Each %s is grouped into a conversation by %s." % (tw, how),
                    "fields": [f for f in (b.thread.group_field,) if f]})
    if b.comm_kind in ("message", "call", "email"):
        side = ("the caller of an outgoing call and the callee of an incoming one" if b.comm_kind == "call" else
                "the sender of an outgoing %s and a recipient of an incoming one" % tw)
        out.append({"rule_id": "%s.owner_implicit" % m.name, "part": "owner_implicit", "choice": "direction",
                    "summary": "When a %s lists no party as the phone's owner, the owner is taken as %s." % (tw, side),
                    "fields": [f for f in (b.participants.direction_field,) if f]})
    out.append({"rule_id": "%s.record" % m.name, "part": "record", "choice": b.comm_kind or "record",
                "summary": "Each %s is read as %s." % (tw, ("a %s" % words(b.comm_kind)) if b.comm_kind else
                                                       "a record of its own kind"),
                "fields": []})
    return t, b, out


TABLE_OF_PART = {"event_time": "phone_time_values", "end_time": "phone_time_values", "role": "phone_participations",
                 "text": "phone_texts", "record": "phone_record_summaries", "thread": "phone_comm_events",
                 "owner_implicit": "phone_participations"}


def _touched(conn, table, rule_id, extraction_id, generation, rule=None, type_name=None, version_id=None):
    special = None
    if rule is not None and rule["part"] == "end_time" and not rule["choice"].get("field"):
        special = ("phone_record_summaries", "model_type = :t AND duration_seconds IS NOT NULL")
    elif rule is not None and rule["part"] == "thread":
        special = ("phone_comm_events", "model_type = :t AND mapping_version_id = :mv AND thread_key IS NOT NULL")
    if special:
        where = "extraction_id = :e AND generation = :g AND " + special[1]
        p = {"e": extraction_id, "g": generation, "t": type_name, "mv": version_id}
        n = conn.execute(text("SELECT count(*) FROM %s WHERE %s" % (special[0], where)), p).scalar()
        samples = [r[0] for r in conn.execute(text("SELECT record_uid FROM %s WHERE %s ORDER BY md5(record_uid::text) "
                                                   "LIMIT 3" % (special[0], where)), p)]
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


def _level(m, d):
    return "reviewed" if (m.status == "reviewed" or d) else "applied_unconfirmed"


_region_hook = {"decided": None}


def register_region_decision(fn):
    """``fn(conn, extraction_id) -> region or None``: the current ``set_phone_default_region`` decision (8.8)."""
    _region_hook["decided"] = fn


def default_region(conn, extraction_id):
    """(region, basis) for numbers written without + (02 section 8.3): the extraction's decision, then the case
    setting, then US."""
    fn = _region_hook["decided"]
    decided = fn(conn, extraction_id) if fn else None
    if decided:
        return decided, "decided"
    case_region = conn.execute(text(
        "SELECT c.phone_default_region FROM cases c JOIN phone_extractions e ON e.case_id = c.id WHERE e.id = :e"),
        {"e": extraction_id}).scalar()
    if case_region:
        return case_region, "case_setting"
    return "US", "assumed_default"


def _present_types(conn, extraction_id):
    """Record counts per type from this extraction's registry observations (written by the observation pass
    that runs before interpretation, 3.3). A type's registry id is derived from its name (``registry._type_rid``)."""
    from services.phone import registry
    by_rid = {registry._type_rid(conn, n): n for (n,) in conn.execute(text("SELECT type_name FROM phone_schema_types"))}
    return {by_rid[rid]: n for rid, n in conn.execute(text(
        "SELECT registry_id, record_count FROM phone_schema_observations WHERE extraction_id = :e AND "
        "registry_table = 'types'"), {"e": extraction_id}) if rid in by_rid}


def plan(conn, extraction_id, mappings=None) -> dict:
    """What the loaded type mappings decide for one extraction, before its rows are written: suspensions, each
    rule's (possibly corrected) choice and level, and the marks the generic pass stamps on rows as it writes."""
    ms = loader.loaded() if mappings is None else mappings
    present = _present_types(conn, extraction_id)
    decisions = reading_decisions(conn, extraction_id)
    out = {"present": present, "applied": [], "suspended": [], "levels": {}, "row_mappings": [],
           "marks": {"time": {}, "text": {}, "party": {}, "record": {}, "region": default_region(conn, extraction_id)}}
    marks = out["marks"]
    for m in ms:
        if m.kind != "type":
            continue
        t, b, rules = rules_of(m)
        if t not in present:
            continue
        reasons = suspension_reasons(conn, m, extraction_id)
        if reasons:
            out["suspended"].append((m, t, reasons))
            continue
        done = []
        for rule in rules:
            d = decisions.get((rule["rule_id"], str(m.id)))
            if d and d["decision"] == "correct":
                rule = dict(rule, choice=d["choice"])
            lvl = out["levels"][rule["rule_id"]] = _level(m, d)
            mk = (m.id, rule["rule_id"], lvl)
            part, choice = rule["part"], rule["choice"]
            if part == "event_time":
                marks["time"][(t, choice)] = mk + (True,)
            elif part == "end_time" and choice.get("field"):
                marks["time"].setdefault((t, choice["field"]), mk + (False,))
            elif part == "role":
                containers = list(b.participants.containers)
                for cname in containers or [rule["key"]]:
                    marks["party"][(t, cname, rule["key"] if containers else "*")] = mk + (choice,)
            elif part == "text":
                for f in choice:
                    marks["text"][(t, f)] = mk
            elif part == "record":
                marks["record"][t] = mk
            done.append((rule, d))
        out["applied"].append((m, t, done))
    for m in ms:  # timestamp-meaning rows (04 section 2.3) are stamped on each time value as it is written
        if m.kind != "timestamp_meaning":
            continue
        prefix = row_rule_prefix(m)
        by_key = {}
        for r in m.body["rows"]:
            by_key.setdefault((r["type"], r["field"]), []).append(r)
        levels, corrected = {}, {}
        for r in m.body["rows"]:
            rid = prefix + r["row_id"]
            d = decisions.get((rid, str(m.id)))
            levels[rid] = _level(m, d)
            if d and d["decision"] == "correct":
                corrected[rid] = d["choice"]
        for key, rws in by_key.items():
            if key[0] in present:
                marks.setdefault("meaning", {}).setdefault(key, []).append((m.id, rws, prefix, levels, corrected))
        out["row_mappings"].append((m, prefix, decisions))
    return out


def row_rule_prefix(m):
    """Rule ids of row-table rows are ``<kind>/<name>/<row_id>`` so they are unique across mappings."""
    return "%s/%s/" % (m.kind, m.name)


def _marked_counts(conn, extraction_id, generation):
    """{rule_id: (records touched, three sample record uids)} for every rule-marked table, one query each."""
    out = {}
    for table in ("phone_time_values", "phone_participations", "phone_texts", "phone_record_summaries"):
        for rid, n, samples in conn.execute(text(
                "SELECT mapping_row_id, count(*), (array_agg(record_uid ORDER BY h))[1:3] FROM (SELECT DISTINCT "
                "mapping_row_id, record_uid, md5(record_uid::text) AS h FROM %s WHERE extraction_id = :e AND "
                "generation = :g AND mapping_row_id IS NOT NULL) s GROUP BY mapping_row_id" % table),
                {"e": extraction_id, "g": generation}):
            out[rid] = (n, list(samples or []))
    return out


def apply_extraction(conn, extraction_id, generation, the_plan) -> dict:
    """The sweep's applier hook (6.7). The plan's marks were stamped as the generic rows were written
    (``generic.interpret(marks=...)``); here: suspensions recorded, comm events and threads, then one judgement call
    per rule and per meaning row that touched this extraction."""
    from services.phone import comms
    p = the_plan
    case_id = conn.execute(text("SELECT case_id FROM phone_extractions WHERE id = :e"), {"e": extraction_id}).scalar()
    stats = {"mappings_applied": 0, "mappings_suspended": 0, "rules": 0, "judgements_open": 0}
    for m, t, reasons in p["suspended"]:
        conn.execute(text(
            "INSERT INTO phone_mapping_applications (extraction_id, mapping_version_id, generation, records_matched, "
            "records_suspended, suspension_reasons) VALUES (:e, :mv, :g, 0, :n, CAST(:r AS jsonb))"),
            {"e": extraction_id, "mv": m.id, "g": generation, "n": p["present"][t], "r": json.dumps(reasons)})
        stats["mappings_suspended"] += 1
    stats["rules"] = sum(len(done) for _, _, done in p["applied"])
    if p["applied"]:
        for k, v in comms.build(conn, extraction_id, case_id, generation, [m for m, _, _ in p["applied"]],
                                p["levels"]).items():
            stats["comms:" + k] = v
    counts = _marked_counts(conn, extraction_id, generation)
    for m, t, done in p["applied"]:
        for rule, d in done:
            if rule["part"] == "thread" or (rule["part"] == "end_time" and not rule["choice"].get("field")):
                n, samples = _touched(conn, TABLE_OF_PART[rule["part"]], rule["rule_id"], extraction_id, generation,
                                      rule, t, m.id)
            else:
                n, samples = counts.get(rule["rule_id"], (0, []))
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
            {"e": extraction_id, "mv": m.id, "g": generation, "n": p["present"][t]})
        stats["mappings_applied"] += 1
    for m, prefix, decisions in p.get("row_mappings", []):
        stats["meaning_calls"] = stats.get("meaning_calls", 0) + _meaning_calls(conn, m, prefix, decisions, case_id,
                                                                                 extraction_id, generation)
    return stats


SEMANTICS_WORDS = {"event_instant": "the moment it happened", "interval_start": "the start of something that lasted",
                   "interval_end": "the end of something that lasted", "aggregate_bucket": "a counting period",
                   "latest_of_many": "the latest of several times; earlier ones are lost",
                   "first_record": "when the record was first created", "last_modified": "when it was last changed",
                   "service_observed": "when a service last saw it", "counterpart_action": "an action by the other person",
                   "scheduled": "a planned time", "expiry": "an end of validity", "duration": "a length of time",
                   "unknown": "not established"}


def _meaning_calls(conn, m, prefix, decisions, case_id, extraction_id, generation):
    """One judgement call per timestamp-meaning row that touched this extraction's time values."""
    rows_by_id = {prefix + r["row_id"]: r for r in m.body["rows"]}
    n_calls = 0
    for rid, n, samples in conn.execute(text(
            "SELECT rid, count(*), (array_agg(record_uid ORDER BY h))[1:3] FROM (SELECT DISTINCT meaning_mapping_row_id "
            "AS rid, record_uid, md5(record_uid::text) AS h FROM phone_time_values WHERE extraction_id = :e AND "
            "generation = :g AND meaning_mapping_version_id = :mv) s GROUP BY 1"),
            {"e": extraction_id, "g": generation, "mv": m.id}):
        r = rows_by_id.get(rid)
        if r is None:
            continue
        d = decisions.get((rid, str(m.id)))
        status = "confirmed" if m.status == "reviewed" else "open"
        if d:
            status = "confirmed" if d["decision"] == "confirm" else "corrected"
        cond = "" if not (r.get("predicates") or r.get("context")) else " when %s" % ", ".join(
            "%s %s%s" % (words(p.get("field") or p.get("name")), p["op"],
                         "" if p.get("value") is None else " %s" % p["value"]) for p in (r["predicates"] + r["context"]))
        summary = "The %s of a %s%s is read as %s: %s." % (words(r["field"]), words(r["type"]), cond,
                                                         SEMANTICS_WORDS.get(r["outputs"].get("semantics"), "not established"),
                                                         r["outputs"].get("meaning"))
        evidence = {"fields": _evidence(conn, r["type"], [r["field"]] + [p["field"] for p in r["predicates"]],
                                        extraction_id),
                    "row": {k: r[k] for k in ("predicates", "context", "outputs", "basis", "reasoning", "would_change")},
                    "mapping": {"kind": m.kind, "name": m.name, "version": m.version, "status": m.status,
                                "origin": m.origin, "basis": m.content["review"]["basis"]}}
        conn.execute(text(
            "INSERT INTO phone_mapping_judgements (id, case_id, extraction_id, mapping_version_id, mapping_kind, "
            "mapping_name, rule_id, type_name, rule_part, summary, strength, records_touched, sample_record_uids, "
            "evidence, status, resolved_by, resolved_by_email, resolved_at, resolution_reason, adjudication_id, "
            "generation) VALUES (:id, :c, :e, :mv, :k, :n, :r, :t, 'meaning', :s, 'inferred', :cnt, "
            "CAST(:samples AS uuid[]), CAST(:ev AS jsonb), :st, :rb, :rbe, :ra, :rr, :adj, :g) "
            "ON CONFLICT (extraction_id, rule_id, mapping_version_id) DO UPDATE SET summary = EXCLUDED.summary, "
            "records_touched = EXCLUDED.records_touched, sample_record_uids = EXCLUDED.sample_record_uids, "
            "evidence = EXCLUDED.evidence, status = EXCLUDED.status, resolved_by = EXCLUDED.resolved_by, "
            "resolved_by_email = EXCLUDED.resolved_by_email, resolved_at = EXCLUDED.resolved_at, "
            "resolution_reason = EXCLUDED.resolution_reason, adjudication_id = EXCLUDED.adjudication_id, "
            "generation = EXCLUDED.generation, updated_at = now()"),
            {"id": judgement_id(extraction_id, rid, m.id), "c": case_id, "e": extraction_id, "mv": m.id, "k": m.kind,
             "n": m.name, "r": rid, "t": r["type"], "s": summary, "cnt": n, "samples": [str(x) for x in samples],
             "ev": json.dumps(evidence, default=str), "st": status, "rb": (d or {}).get("by"),
             "rbe": (d or {}).get("by_email"), "ra": (d or {}).get("at"), "rr": (d or {}).get("reason"),
             "adj": (d or {}).get("decision_id"), "g": generation})
        n_calls += 1
    return n_calls
