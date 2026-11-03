"""Activity events (04 sections 3, 4 and 7.2; unit U2) and the projection's state and staleness (7.1).

One ``pol_activity_event`` row per (record, time field) whose time meaning is an activity: every time value of the
current interpretation generation except the scheduled, expiry and generic-timeline-only times of 3.3. The time
meaning comes from the timestamp-meaning row already stamped on the time value (04-U1); the class, actor and
physical qualifier from the reviewed activity-strength rows (3.2, match discipline 3.4); flags from the attribution
rows and the event's context (4.2, ``attribution.py``). An interval's end (``EndTime``, ``DateEnded``, ``To``) is the
``end_utc`` of its start's event, never an event of its own; an end with no start is its own event.

Records are addressed by ``record_uid`` (02 section 1.2) and ``time_field``; nothing re-reads the report.
Strength is computed by the view ``pol_activity_event_v``, never stored.

A new activity or attribution mapping version, or a person's confirm or correction of one of their rows,
re-classifies from the stored ``match_facts`` without reading records again (``reclassify``); a new interpretation
generation rebuilds (``build``). ``project_stale`` is the phone worker's after-pass step.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from datetime import timezone
from itertools import groupby

from sqlalchemy import text

from services.pattern_of_life import attribution as A

log = logging.getLogger(__name__)

# 3.3: never in the activity lanes
EXCLUDED_SEMANTICS = frozenset({"scheduled", "expiry", "duration"})
EXCLUDED_KEYS = frozenset({("ForwardedMessageData", "TimeCreated"), ("Chat", "StartTime"), ("Chat", "LastActivity"),
                           ("UserAccount", "TimeCreated"), ("MobileCard", "PurchaseTime"),
                           ("MobileCard", "ModifyTime"), ("DeviceInfoEntry", "TimeStamp")})
EXCLUDED_TYPE_PREFIXES = ("CoreFileSystem",)  # tagged file times feed media places (6.2), never activity

# start field -> the end field that closes it on the same record
END_OF = {"StartTime": "EndTime", "DateStarted": "DateEnded", "From": "To", "DateSampled": "DateEnded",
          "TimeStamp": "EndTime"}
END_SEMANTICS = frozenset({"interval_end", "aggregate_bucket"})

# 5.2 families, by record type (a Party by the record it sits in)
FAMILY = {
    "DeviceEvent": "device_events", "PoweringEvent": "power", "AppsUsageLog": "app_usage",
    "ApplicationUsage": "app_usage", "InstalledApplication": "app_usage", "NetworkUsage": "network_usage",
    "InstantMessage": "messages", "Chat": "messages", "ChatActivity": "messages", "Call": "calls",
    "Voicemail": "calls", "VisitedPage": "web", "Cookie": "web", "WebBookmark": "web", "FileDownload": "web",
    "FileUpload": "web", "Autofill": "web", "Password": "web", "SearchedItem": "search", "Location": "locations",
    "Journey": "locations", "WirelessNetwork": "wifi", "CellTower": "cell", "DeviceConnectivity": "connectivity",
    "ActivitySensorData": "sensors", "ActivitySensorDataSample": "sensors", "Notification": "notifications",
    "LogEntry": "logs", "Email": "email", "SocialMediaActivity": "social",
}
COMM_TYPES = ("InstantMessage", "Call", "Email", "Voicemail", "ChatActivity")

ALWAYS_FACT_FIELDS = ("Source", "UserMapping")
EXTRA_FACT_FIELDS = {"DeviceEvent": ("EventType", "Value"), "PoweringEvent": ("Event", "Element"),  # power (5.3 step 5)
                     "Location": ("Type", "Category", "Origin")}  # place kind (6.1, 6.2)

COLUMNS = ("case_id", "extraction_id", "record_uid", "root_record_uid", "record_type", "time_field", "field_path",
           "end_field", "instant_utc", "end_utc", "offset_status", "instant_basis", "original", "time_semantics",
           "meaning_mapping_row", "stream_key", "family", "value_key", "activity_class", "class_basis", "class_level",
           "activity_mapping_row", "activity_mapping_version", "actor", "physical", "attribution_flags",
           "attribution_mapping_rows", "deleted_state", "decoding_confidence", "source_app", "match_facts")


# ---- mappings ----------------------------------------------------------------------------------------------------

class RowIndex:
    """The loaded activity-strength and attribution rows, with each row's level and any person's correction."""

    def __init__(self, conn, extraction_id, mappings=None):
        from services.phone.mappings import apply, loader
        ms = loader.loaded() if mappings is None else mappings
        decisions = apply.reading_decisions(conn, extraction_id) if conn is not None else {}
        self.kinds = {"activity_strength": [], "attribution": []}
        self.versions = {}
        self.fields = defaultdict(set)
        for m in ms:
            if m.kind not in self.kinds:
                continue
            prefix = apply.row_rule_prefix(m)
            by_key = defaultdict(list)
            levels, corrected = {}, {}
            for r in m.body["rows"]:
                by_key[(r["type"], r["field"])].append(r)
                rid = prefix + r["row_id"]
                d = decisions.get((rid, str(m.id)))
                levels[rid] = "reviewed" if (m.status == "reviewed" or d) else "applied_unconfirmed"
                if d and d["decision"] == "correct":
                    corrected[rid] = d["choice"]
                for p in r.get("predicates") or []:
                    self.fields[r["type"]].add(p["field"])
            self.kinds[m.kind].append((m, prefix, by_key, levels, corrected))
            self.versions.setdefault(m.kind, m.id)
        for t, extra in EXTRA_FACT_FIELDS.items():
            self.fields[t].update(extra)

    def fact_fields(self, type_name):
        return self.fields.get(type_name, set()) | set(ALWAYS_FACT_FIELDS)

    def classify(self, type_name, field, facts):
        from services.phone.mappings import rows as R
        for m, prefix, by_key, levels, corrected in self.kinds["activity_strength"]:
            cands = by_key.get((type_name, field))
            if not cands:
                continue
            r = R.match(cands, type_name, field, facts)
            if r is None:
                continue
            rid = prefix + r["row_id"]
            out = dict(corrected.get(rid) or r["outputs"])
            if r["basis"] == "not_established" and rid not in corrected:
                out = {"class": "unknown", "actor": "unknown", "physical": out.get("physical")}
            vk = ";".join("%s=%s" % (p["field"], _first(facts["fields"].get(p["field"])))
                          for p in r.get("predicates") or [])
            return {"row": rid, "version": m.id, "level": levels[rid], "class": out.get("class") or "unknown",
                    "actor": out.get("actor") or "unknown", "physical": bool(out.get("physical")),
                    "value_key": vk[:160] or None}
        return None

    def attribution(self, type_name, field, facts):
        from services.phone.mappings import rows as R
        flags, rows = [], []
        for m, prefix, by_key, levels, corrected in self.kinds["attribution"]:
            cands = by_key.get((type_name, field))
            if not cands:
                continue
            r = R.match(cands, type_name, field, facts)
            if r is None:
                continue
            rid = prefix + r["row_id"]
            out = corrected.get(rid) or r["outputs"]
            if out.get("flag"):
                flags.append(out["flag"])
                rows.append(rid)
        return flags, rows

    def activity_versions(self) -> dict:
        """{"<kind>/<name>/": version id} of the loaded activity-strength mappings: an event's version is the one for
        its mapping row's prefix."""
        return {prefix: str(m.id) for m, prefix, *_ in self.kinds["activity_strength"]}

    def signature(self, decisions_rev=""):
        return "|".join("%s=%s" % (k, self.versions.get(k)) for k in sorted(self.kinds)) + "|" + decisions_rev


def _first(vals):
    for v in vals or ():
        if v not in (None, ""):
            return v
    return None


# ---- classification of one event ----------------------------------------------------------------------------------

def classify_event(idx, ev):
    """Fill class, actor, physical, flags and value key on ``ev`` (a dict carrying ``record_type``, ``time_field``
    (the base field name), ``time_semantics``, ``offset_status``, ``deleted_state``, ``decoding_confidence`` and
    ``match_facts``)."""
    facts = ev["match_facts"]
    c = idx.classify(ev["record_type"], ev["base_field"], facts)
    if c is None:
        ev.update(activity_class="unknown", class_basis="default_unknown", class_level=None,
                  activity_mapping_row=None, activity_mapping_version=None, actor="unknown", physical=False,
                  value_key=None)
    else:
        ev.update(activity_class=c["class"], class_basis="reviewed_mapping", class_level=c["level"],
                  activity_mapping_row=c["row"], activity_mapping_version=c["version"], actor=c["actor"],
                  physical=c["physical"], value_key=c["value_key"])
    flags, rows = idx.attribution(ev["record_type"], ev["base_field"], facts)
    flags += A.context_flags(semantics=ev["time_semantics"], offset_status=ev["offset_status"],
                             deleted_state=ev["deleted_state"], decoding_confidence=ev["decoding_confidence"],
                             actor=ev["actor"], user_mapping=_first(facts["fields"].get("UserMapping")))
    seen = []
    for f in flags:
        if f not in seen:
            seen.append(f)
    ev["attribution_flags"] = seen
    ev["attribution_mapping_rows"] = rows
    return ev


# ---- build -------------------------------------------------------------------------------------------------------

def _zone(name):
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - an unknown zone name places nothing
        return None


def _field_values(body, wanted):
    from services.phone import body as B
    out = {}
    for f in B.fields(body):
        if f.name in wanted and f.kind not in B.MODEL_FIELD_KINDS:
            vals = [v.text for v in f.real_values if v.text not in (None, "")]
            if vals:
                out.setdefault(f.name, []).extend(vals)
    return out


def _party_owner(body):
    from services.phone import body as B
    from services.phone import values as V
    return V.parse_boolean(B.first_text(body, "IsPhoneOwner"))


def current_generation(conn, extraction_id):
    return conn.execute(text(
        "SELECT s.generation, s.device_zone, s.case_id, s.status FROM phone_interpretation_state s JOIN phone_extractions e "
        "ON e.id = s.extraction_id WHERE s.extraction_id = :e"), {"e": extraction_id}).one_or_none()


def build(conn, extraction_id, mappings=None) -> dict:
    """Rebuild the extraction's activity events from its current interpretation generation (no commit)."""
    from services.phone import generic
    started = time.monotonic()
    st = current_generation(conn, extraction_id)
    if st is None or not st.generation:
        return {"status": "not_interpreted"}
    gen, zone_name, case_id = st.generation, st.device_zone, st.case_id
    zone = _zone(zone_name)
    idx = RowIndex(conn, extraction_id, mappings)
    _state(conn, extraction_id, case_id, "building")
    conn.execute(text("DELETE FROM pol_activity_event WHERE extraction_id = :e"), {"e": extraction_id})
    direction = {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT record_uid, direction FROM phone_comm_events WHERE extraction_id = :e AND generation = :g"),
        {"e": extraction_id, "g": gen})}
    rows = conn.execute(text(
        "SELECT t.record_uid, t.root_record_uid, t.document_index, t.ordinal, t.model_type, t.field_name, "
        "t.field_path, t.value_index, t.effective_instant, t.local_wall_time, t.offset_state, t.original_text, "
        "t.semantics, t.meaning_mapping_row_id, t.instant_basis, t.deleted_state, t.decoding_confidence, r.body, "
        "r.top_ordinal, CASE WHEN r.parent_ordinal IS NULL THEN NULL ELSE root.model_type END AS root_type "
        "FROM phone_time_values t "
        "JOIN phone_records r ON r.extraction_id = t.extraction_id AND r.document_index = t.document_index "
        "  AND r.ordinal = t.ordinal "
        "LEFT JOIN phone_records root ON root.extraction_id = r.extraction_id AND root.document_index = r.document_index "
        "  AND root.ordinal = r.top_ordinal AND r.parent_ordinal IS NOT NULL "
        "WHERE t.extraction_id = :e AND t.generation = :g "
        "ORDER BY t.document_index, t.ordinal, t.field_path, t.value_index").execution_options(
        stream_results=True, yield_per=5000), {"e": extraction_id, "g": gen})
    w = generic.Writer(conn, {"pol_activity_event": COLUMNS})
    stats = defaultdict(int)
    root_cache = {"key": None, "source": None}
    fields_used = defaultdict(set)
    for (doc, ordinal), grp in groupby(rows, key=lambda r: (r.document_index, r.ordinal)):
        grp = list(grp)
        first = grp[0]
        t = first.model_type
        if t.startswith(EXCLUDED_TYPE_PREFIXES):
            stats["skipped_type"] += len(grp)
            continue
        wanted = idx.fact_fields(t)
        fields_used[t].update(wanted)
        fvals = _field_values(first.body, wanted)
        if first.root_type is not None:
            # a nested record takes its root's Source. The root body is read once per root, not shipped on every
            # time value of every child (a chat's body repeated on each message's rows held gigabytes in the
            # fetch buffers on a 967,543-record report); rows arrive in record order, so a root's children are
            # contiguous and one lookup serves them all
            key = (doc, first.top_ordinal)
            if root_cache["key"] != key:
                root_body = conn.execute(text(
                    "SELECT body FROM phone_records WHERE extraction_id = :e AND document_index = :d AND ordinal = :o"),
                    {"e": extraction_id, "d": doc, "o": first.top_ordinal}).scalar()
                root_cache.update(key=key, source=_first(_field_values(root_body, {"Source"}).get("Source"))
                                  if root_body is not None else None)
            source = root_cache["source"]
        else:
            source = _first(fvals.get("Source"))
        if source is not None:
            fvals["Source"] = [source]
        ctx = {"direction": direction.get(str(first.record_uid)) if t in COMM_TYPES else None,
               "party_is_owner": _party_owner(first.body) if t == "Party" else None,
               "deleted_state": first.deleted_state, "decoding_confidence": first.decoding_confidence}
        by_field = {}
        for r in grp:
            by_field.setdefault(r.field_name, r)  # the first value of a multi-valued time field
            if r.value_index:
                stats["extra_values_in_field"] += 1
        ends_used = set()
        for fname, r in by_field.items():
            sem = r.semantics or "unknown"
            if sem in EXCLUDED_SEMANTICS or (t, fname) in EXCLUDED_KEYS:
                stats["excluded"] += 1
                continue
            end_name = END_OF.get(fname)
            if end_name in by_field and end_name != fname and (by_field[end_name].semantics or "") in END_SEMANTICS:
                ends_used.add(end_name)
        for fname, r in by_field.items():
            sem = r.semantics or "unknown"
            if sem in EXCLUDED_SEMANTICS or (t, fname) in EXCLUDED_KEYS or fname in ends_used:
                continue
            inst, basis, ostat = _instant(r, zone)
            if inst is None:
                stats["skipped_no_instant:%s" % r.offset_state] += 1
                continue
            end_name = END_OF.get(fname) if END_OF.get(fname) in ends_used else None
            end = _instant(by_field[end_name], zone)[0] if end_name else None
            family = FAMILY.get(first.root_type if t == "Party" and first.root_type else t, "other")
            if t == "DeviceEvent" and _first(fvals.get("EventType")) == "PowerEvent":
                family = "power"
            stream = "%s/%s" % (t, source or "-")
            if t == "DeviceEvent":
                stream += "/%s" % (_first(fvals.get("EventType")) or "-")
            ev = {"case_id": case_id, "extraction_id": extraction_id, "record_uid": r.record_uid,
                  "root_record_uid": r.root_record_uid, "record_type": t[:64],
                  "time_field": (fname if not r.value_index else "%s[%d]" % (fname, r.value_index))[:64],
                  "base_field": fname, "field_path": r.field_path, "end_field": end_name,
                  "instant_utc": inst, "end_utc": end, "offset_status": ostat, "instant_basis": basis,
                  "original": r.original_text, "time_semantics": sem, "meaning_mapping_row": r.meaning_mapping_row_id,
                  "stream_key": stream[:160], "family": family, "deleted_state": (r.deleted_state or None),
                  "decoding_confidence": r.decoding_confidence, "source_app": (source or None) and source[:128],
                  "match_facts": {"fields": {k: v for k, v in fvals.items()}, "context": dict(ctx, semantics=sem,
                                                                                              offset_state=ostat)}}
            classify_event(idx, ev)
            ev["match_facts"] = json.dumps(ev["match_facts"], sort_keys=True, default=str)
            w.add("pol_activity_event", ev)
            stats["events"] += 1
            stats["class:%s" % ev["activity_class"]] += 1
    w.flush()
    cp = _counterparts(conn, extraction_id, case_id, gen)
    stats.update(cp)
    calls = _judgement_calls(conn, idx, extraction_id, case_id, gen)
    stats["judgement_calls"] = calls
    stats["seconds"] = round(time.monotonic() - started, 1)
    _state(conn, extraction_id, case_id, "ready", gen=gen, idx=idx, sig=signature(conn, extraction_id, idx),
           facts_fields={k: sorted(v) for k, v in fields_used.items()}, counts=dict(stats),
           fams=families(conn, extraction_id))
    return dict(stats, status="ready")


def _instant(r, zone):
    """(instant, basis, offset status). An offset-less value is placed in the phone's own zone when the report
    gives one (8.0); with no zone it is not placed and counted (2.3)."""
    ostat = "explicit" if r.offset_state == "explicit" else "absent"
    if r.effective_instant is not None:
        return r.effective_instant, (r.instant_basis or "capture")[:24], ostat
    if r.local_wall_time is not None and zone is not None:
        return r.local_wall_time.replace(tzinfo=zone).astimezone(timezone.utc), "device_zone", "absent"
    return None, None, ostat


def _counterparts(conn, extraction_id, case_id, gen) -> dict:
    """The other person's identity on each event: a Party's own identity for read, played and delivered times; the
    first party not on the phone's own side for a communication (02 section 8; 3.1 actor ``counterpart``)."""
    from services.phone import identities as I
    owners = [k for k in (I.owner(conn, extraction_id).get("owner_identity_keys") or []) if k]
    n_party = conn.execute(text(
        "UPDATE pol_activity_event ev SET counterpart_identity_id = c.id FROM ("
        " SELECT DISTINCT ON (p.party_record_uid) p.party_record_uid AS uid, i.id FROM phone_participations p "
        " JOIN phone_identities i ON i.case_id = :c AND i.identity_key = p.identity_key "
        " WHERE p.extraction_id = :e AND p.generation = :g AND p.party_record_uid IS NOT NULL "
        "   AND coalesce(p.is_phone_owner, false) = false AND NOT (p.identity_key = ANY(:owners)) "
        " ORDER BY p.party_record_uid, p.ordinal) c "
        "WHERE ev.extraction_id = :e AND ev.record_type = 'Party' AND ev.record_uid = c.uid"),
        {"c": case_id, "e": extraction_id, "g": gen, "owners": owners}).rowcount
    n_comm = conn.execute(text(
        "UPDATE pol_activity_event ev SET counterpart_identity_id = c.id FROM ("
        " SELECT DISTINCT ON (p.record_uid) p.record_uid AS uid, i.id FROM phone_participations p "
        " JOIN phone_identities i ON i.case_id = :c AND i.identity_key = p.identity_key "
        " WHERE p.extraction_id = :e AND p.generation = :g AND p.role <> 'owner_implicit' "
        "   AND coalesce(p.is_phone_owner, false) = false AND NOT (p.identity_key = ANY(:owners)) "
        " ORDER BY p.record_uid, p.ordinal) c "
        "WHERE ev.extraction_id = :e AND ev.record_type <> 'Party' AND ev.record_uid = c.uid"),
        {"c": case_id, "e": extraction_id, "g": gen, "owners": owners}).rowcount
    return {"counterpart:party": n_party, "counterpart:communication": n_comm}


# ---- re-classification without re-reading records -----------------------------------------------------------------

def reclassify(conn, extraction_id, mappings=None) -> dict:
    """Apply the current activity and attribution rows to the stored events (3.4 item 4). Falls back to ``build``
    when a row matches on a field the stored facts do not hold."""
    started = time.monotonic()
    st = current_generation(conn, extraction_id)
    if st is None:
        return {"status": "not_interpreted"}
    idx = RowIndex(conn, extraction_id, mappings)
    held = conn.execute(text("SELECT facts_fields FROM pol_projection_state WHERE extraction_id = :e"),
                        {"e": extraction_id}).scalar() or {}
    for t, have in held.items():
        if not idx.fact_fields(t) <= set(have):
            return dict(build(conn, extraction_id, mappings), fallback="new_fact_field")
    # an event's class depends only on these inputs, and a phone's events share few distinct sets of them (231 on a
    # 542,091-event report), so each set is classified once and one set-based UPDATE writes the rows whose result
    # changed (a row-by-row UPDATE of every event took 177 s there; the target is 60 s, 04 section 11)
    n = changed = 0
    sets = []
    for row in conn.execute(text(
            "SELECT " + _inputs_key() + " AS k, count(*) AS n, min(record_type) AS record_type, "
            "min(time_field) AS time_field, min(time_semantics) AS time_semantics, "
            "min(offset_status) AS offset_status, "
            "min(deleted_state) AS deleted_state, min(decoding_confidence) AS decoding_confidence, "
            "(array_agg(match_facts))[1] AS match_facts FROM pol_activity_event WHERE extraction_id = :e GROUP BY 1"),
            {"e": extraction_id}):
        ev = {"record_type": row.record_type, "base_field": row.time_field.split("[")[0],
              "time_semantics": row.time_semantics, "offset_status": row.offset_status,
              "deleted_state": row.deleted_state, "decoding_confidence": row.decoding_confidence,
              "match_facts": row.match_facts}
        classify_event(idx, ev)
        sets.append({"k": row.k, "ac": ev["activity_class"], "cb": ev["class_basis"], "cl": ev["class_level"],
                     "ar": ev["activity_mapping_row"], "av": ev["activity_mapping_version"], "ac2": ev["actor"],
                     "ph": ev["physical"], "fl": ev["attribution_flags"], "fr": ev["attribution_mapping_rows"],
                     "vk": ev["value_key"]})
        n += row.n
    if sets:
        changed = _apply_sets(conn, extraction_id, sets)
    # counterparts are not touched: they come from the generation's participations (``_counterparts``, run by the
    # build), which a re-apply never changes; clearing and setting them again here took 12 to 15 s on P14 and left
    # them as they were
    calls = _judgement_calls(conn, idx, extraction_id, st.case_id, st.generation)
    _state(conn, extraction_id, st.case_id, "ready", gen=st.generation, idx=idx,
           sig=signature(conn, extraction_id, idx), facts_fields=held,
           counts={"reclassified": n, "changed": changed, "judgement_calls": calls,
                   "seconds": round(time.monotonic() - started, 1)})
    return {"status": "ready", "reclassified": n, "changed": changed, "judgement_calls": calls}


# the inputs classify_event reads from a stored event, as one unambiguous key (nulls stay distinct from values)
_INPUTS = ("record_type", "time_field", "time_semantics", "offset_status", "deleted_state", "decoding_confidence",
           "match_facts")


def _inputs_key(alias=""):
    return "md5(jsonb_build_array(%s)::text)" % ", ".join(alias + c for c in _INPUTS)


def _apply_sets(conn, extraction_id, sets) -> int:
    """Write each input set's result to the events holding that set whose result differs; the number written. The
    mapping version is not written per event: the view reads it from the projection state (``activity_versions``),
    so a new version alone moves no row."""
    conn.execute(text("DROP TABLE IF EXISTS pg_temp.pol_reclass"))
    conn.execute(text(
        "CREATE TEMP TABLE pol_reclass (k text PRIMARY KEY, ac varchar, cb varchar, cl varchar, ar varchar, av uuid, "
        "ac2 varchar, ph boolean, fl text[], fr text[], vk varchar) ON COMMIT DROP"))
    conn.execute(text("INSERT INTO pol_reclass VALUES (:k, :ac, :cb, :cl, :ar, CAST(:av AS uuid), :ac2, :ph, :fl, "
                      ":fr, :vk)"), sets)
    return conn.execute(text(
        "UPDATE pol_activity_event e SET activity_class = x.ac, class_basis = x.cb, class_level = x.cl, "
        "activity_mapping_row = x.ar, actor = x.ac2, physical = x.ph, "
        "attribution_flags = x.fl, attribution_mapping_rows = x.fr, value_key = x.vk "
        "FROM pol_reclass x WHERE e.extraction_id = :e AND " + _inputs_key("e.") + " = x.k AND "
        "(e.activity_class, e.class_basis, e.class_level, e.activity_mapping_row, e.actor, e.physical, "
        "e.attribution_flags, e.attribution_mapping_rows, e.value_key) "
        "IS DISTINCT FROM (x.ac, x.cb, x.cl, x.ar, x.ac2, x.ph, x.fl, x.fr, x.vk)"),
        {"e": extraction_id}).rowcount


# ---- judgement calls (02 section 6.10; 04 decision 18) ---------------------------------------------------------

def _judgement_calls(conn, idx, extraction_id, case_id, gen) -> int:
    """One judgement call per activity or attribution row that touched this extraction's events."""
    from services.phone.mappings import apply, loader
    loader.record_versions(conn, [m for k in idx.kinds.values() for m, *_ in k])  # a version loaded since start-up
    n_calls = 0
    for kind, col in (("activity_strength", "activity_mapping_row"), ("attribution", "attribution_mapping_rows")):
        if not idx.kinds[kind]:
            continue
        expr = col if kind == "activity_strength" else "unnest(%s)" % col
        touched = {r[0]: (r[1], list(r[2] or [])) for r in conn.execute(text(
            "SELECT rid, count(*), (array_agg(record_uid ORDER BY h))[1:3] FROM (SELECT DISTINCT %s AS rid, "
            "record_uid, md5(record_uid::text) AS h FROM pol_activity_event WHERE extraction_id = :e) s "
            "WHERE rid IS NOT NULL GROUP BY 1" % expr), {"e": extraction_id})}
        decisions = apply.reading_decisions(conn, extraction_id)
        for m, prefix, by_key, levels, corrected in idx.kinds[kind]:
            for rws in by_key.values():
                for r in rws:
                    rid = prefix + r["row_id"]
                    if rid not in touched:
                        continue
                    cnt, samples = touched[rid]
                    d = decisions.get((rid, str(m.id)))
                    status = "confirmed" if m.status == "reviewed" else "open"
                    if d:
                        status = "confirmed" if d["decision"] == "confirm" else "corrected"
                    summary = _summary(kind, r)
                    evidence = {"row": {k: r.get(k) for k in ("predicates", "context", "outputs", "basis", "reasoning",
                                                              "would_change")},
                                "mapping": {"kind": m.kind, "name": m.name, "version": m.version, "status": m.status,
                                            "origin": m.origin, "basis": m.content["review"]["basis"]}}
                    conn.execute(text(
                        "INSERT INTO phone_mapping_judgements (id, case_id, extraction_id, mapping_version_id, "
                        "mapping_kind, mapping_name, rule_id, type_name, rule_part, summary, strength, records_touched, "
                        "sample_record_uids, evidence, status, resolved_by, resolved_by_email, resolved_at, "
                        "resolution_reason, adjudication_id, generation) VALUES (:id, :c, :e, :mv, :k, :n, :r, :t, "
                        ":part, :s, 'inferred', :cnt, CAST(:samples AS uuid[]), CAST(:ev AS jsonb), :st, :rb, :rbe, "
                        ":ra, :rr, :adj, :g) ON CONFLICT (extraction_id, rule_id, mapping_version_id) DO UPDATE SET "
                        "summary = EXCLUDED.summary, records_touched = EXCLUDED.records_touched, "
                        "sample_record_uids = EXCLUDED.sample_record_uids, evidence = EXCLUDED.evidence, "
                        "status = EXCLUDED.status, resolved_by = EXCLUDED.resolved_by, "
                        "resolved_by_email = EXCLUDED.resolved_by_email, resolved_at = EXCLUDED.resolved_at, "
                        "resolution_reason = EXCLUDED.resolution_reason, adjudication_id = EXCLUDED.adjudication_id, "
                        "generation = EXCLUDED.generation, updated_at = now()"),
                        {"id": apply.judgement_id(extraction_id, rid, m.id), "c": case_id, "e": extraction_id,
                         "mv": m.id, "k": m.kind, "n": m.name, "r": rid, "t": r["type"],
                         "part": "activity" if kind == "activity_strength" else "attribution", "s": summary,
                         "cnt": cnt, "samples": [str(x) for x in samples], "ev": json.dumps(evidence, default=str),
                         "st": status, "rb": (d or {}).get("by"), "rbe": (d or {}).get("by_email"),
                         "ra": (d or {}).get("at"), "rr": (d or {}).get("reason"),
                         "adj": (d or {}).get("decision_id"), "g": gen})
                    n_calls += 1
    return n_calls


CLASS_WORDS = {"interaction": "a person using the phone", "device_state": "a change of device state",
               "passive": "recorded without any action by the owner", "unknown": "not established"}
ACTOR_WORDS = {"owner": "the phone's owner", "counterpart": "the other person", "other_device": "another device",
               "account": "the account", "unknown": "not established"}


def _summary(kind, r):
    from services.phone.mappings.apply import words
    cond = "" if not (r.get("predicates") or r.get("context")) else " when %s" % ", ".join(
        "%s %s%s" % (words(p.get("field") or p.get("name")), p["op"], "" if p.get("value") is None else
                     " %s" % p["value"]) for p in (r.get("predicates") or []) + (r.get("context") or []))
    o = r["outputs"]
    if kind == "attribution":
        return "The %s of a %s%s is flagged: %s" % (words(r["field"]), words(r["type"]), cond,
                                                    A.UI_COPY.get(o.get("flag"), o.get("flag")))
    return "The %s of a %s%s is read as %s, by %s%s." % (
        words(r["field"]), words(r["type"]), cond, CLASS_WORDS.get(o.get("class"), o.get("class")),
        ACTOR_WORDS.get(o.get("actor"), o.get("actor")), "; the phone moved" if o.get("physical") else "")


# ---- state and staleness -----------------------------------------------------------------------------------------

def signature(conn, extraction_id, idx=None) -> str:
    """What the projection depends on beyond the generation: activity and attribution versions and the decisions
    on their rows."""
    idx = idx or RowIndex(conn, extraction_id)
    from services.phone.mappings import apply
    d = apply.reading_decisions(conn, extraction_id)
    mine = sorted("%s:%s:%s" % (k[0], k[1], v.get("decision_id")) for k, v in d.items()
                  if str(k[0]).startswith(("activity_strength/", "attribution/")))
    return hashlib.sha256(idx.signature("|".join(mine)).encode()).hexdigest()


def families(conn, extraction_id) -> list:
    """Per family: events, first and last instant (ISO), as /subjects lists them. Kept on the projection state at
    build time: the aggregate reads every event of the phone (4.1 s on a 542,091-event phone)."""
    return [{"family": f, "events": int(n), "first": a.isoformat() if a else None, "last": b.isoformat() if b else None}
            for f, n, a, b in conn.execute(text(
                "SELECT family, count(*), min(instant_utc), max(instant_utc) FROM pol_activity_event WHERE "
                "extraction_id = :e GROUP BY family ORDER BY family"), {"e": extraction_id})]


def _state(conn, extraction_id, case_id, status, gen=None, idx=None, sig=None, facts_fields=None, counts=None,
           fams=None):
    if status == "building":
        conn.execute(text(
            "INSERT INTO pol_projection_state (extraction_id, case_id, status) VALUES (:e, :c, 'building') "
            "ON CONFLICT (extraction_id) DO UPDATE SET status = 'building', error = NULL"),
            {"e": extraction_id, "c": case_id})
        return
    n = conn.execute(text("SELECT count(*) FROM pol_activity_event WHERE extraction_id = :e"),
                     {"e": extraction_id}).scalar()
    meaning = conn.execute(text(
        "SELECT meaning_mapping_version_id FROM phone_time_values WHERE extraction_id = :e AND generation = :g AND "
        "meaning_mapping_version_id IS NOT NULL LIMIT 1"), {"e": extraction_id, "g": gen}).scalar()
    conn.execute(text(
        "INSERT INTO pol_projection_state (extraction_id, case_id, interpretation_generation, activity_mapping_version, "
        "meaning_mapping_version, attribution_mapping_version, signature, facts_fields, built_at, event_count, counts, "
        "status, error, families, activity_versions) VALUES (:e, :c, :g, :av, :mv, :tv, :sig, CAST(:ff AS jsonb), now(), "
        ":n, CAST(:cn AS jsonb), :st, NULL, CAST(:fm AS jsonb), CAST(:avs AS jsonb)) ON CONFLICT (extraction_id) "
        "DO UPDATE SET interpretation_generation = EXCLUDED.interpretation_generation, "
        "activity_mapping_version = EXCLUDED.activity_mapping_version, meaning_mapping_version = "
        "EXCLUDED.meaning_mapping_version, attribution_mapping_version = EXCLUDED.attribution_mapping_version, "
        "signature = EXCLUDED.signature, facts_fields = EXCLUDED.facts_fields, built_at = now(), "
        "event_count = EXCLUDED.event_count, counts = EXCLUDED.counts, status = EXCLUDED.status, error = NULL, "
        "families = coalesce(EXCLUDED.families, pol_projection_state.families), "
        "activity_versions = EXCLUDED.activity_versions"),
        {"e": extraction_id, "c": case_id, "g": gen, "av": idx.versions.get("activity_strength") if idx else None,
         "mv": meaning, "tv": idx.versions.get("attribution") if idx else None, "sig": sig,
         "ff": json.dumps(facts_fields or {}), "n": n, "cn": json.dumps(counts or {}, default=str), "st": status,
         "fm": json.dumps(fams) if fams is not None else None,
         # each event's activity mapping version is read from here by the view (pol_activity_event_v)
         "avs": json.dumps(idx.activity_versions()) if idx else None})


def stale(conn) -> list:
    """[(extraction id, 'build' | 'reclassify')] for active, interpreted extractions whose projection is missing,
    from an older generation, or built under other rows or decisions."""
    out = []
    for e, gen, pgen, sig, status in conn.execute(text(
            "SELECT s.extraction_id, s.generation, p.interpretation_generation, p.signature, p.status FROM "
            "phone_interpretation_state s JOIN phone_extractions e ON e.id = s.extraction_id AND e.standing = 'active' "
            "LEFT JOIN pol_projection_state p ON p.extraction_id = s.extraction_id "
            "WHERE s.status = 'done' AND s.generation > 0 ORDER BY s.updated_at")):
        if pgen is None or pgen != gen or status in ("building", "failed", "stale"):
            out.append((e, "build"))
        elif sig != signature(conn, e):
            out.append((e, "reclassify"))
    return out


def project_stale(engine) -> dict:
    """The phone worker's after-pass step: one extraction per transaction."""
    done = {}
    with engine.connect() as conn:
        todo = stale(conn)
    for e, how in todo:
        try:
            with engine.begin() as conn:
                if not conn.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('pol_projection'), hashtext(:e))"),
                                    {"e": str(e)}).scalar():
                    continue
                done[str(e)] = (build if how == "build" else reclassify)(conn, e)
            _after_activity(engine, e)
        except Exception as exc:  # noqa: BLE001
            log.exception("pattern projection failed for %s", e)
            with engine.begin() as conn:
                conn.execute(text("UPDATE pol_projection_state SET status = 'failed', error = :x WHERE "
                                  "extraction_id = :e"), {"e": e, "x": str(exc)[:2000]})
            done[str(e)] = {"status": "failed", "error": str(exc)}
    return done


_after = []


def register_after_activity(fn):
    """Later stages (availability, places) run after the activity events of an extraction are written."""
    if fn not in _after:
        _after.append(fn)


def _after_activity(engine, extraction_id):
    for fn in _after:
        with engine.begin() as conn:
            fn(conn, extraction_id)


def install():
    """Called by the phone sweep worker after the interpretation stages."""
    from services.phone import sweep
    sweep.register_after_pass(project_stale)
