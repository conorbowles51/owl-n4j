"""Links to a record of a replaced phone report (07 CO-9a and CO-9b; 05 section 15.4; 01 section 10.7).

A Workspace or dossier link keeps the record it was made on. When that record's report is later replaced, the link
says "from a replaced copy" and offers the record of the report the case now stands on that has the equal natural key
(approach 12's keys, 05 section 15.3 step 3: a message by its kind, app, sender, time and text; a call by its people,
time, direction and duration; any other record by its type and its non-volatile fields). Records sharing one key are
paired in time order, as approach 12 pairs them. When no record of the newer report has the equal key the link says
so and offers none: a record is never offered on a guess.

Nothing is moved: the link stays on the record it was made on, and following the offer is the person's choice.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

MAX_RECORDS = 500

REPLACED = "From a replaced copy."
NEWER_HOLDS = "The report that replaced it holds the same record."
NEWER_LACKS = ("The report that replaced it holds no record with the same content, time and people, so none is "
               "offered.")
NOT_KEYED = ("It is part of another record, and such parts are not matched between reports, so none is offered; "
             "open the record it is part of.")
NONE_IN_USE = "The report that replaced it is not in use in this case either, so no record is offered."


class TooMany(ValueError):
    pass


def keys_any(conn, ext) -> dict:
    """Approach 12's natural keys (``extraction_comparison._keys``) of one report whatever its standing: the case
    views hold only the reports in use, so this reads the tables at the report's current interpretation. A test
    holds the two equal on a report in use."""
    from services.phone_analysis.extraction_comparison import VOLATILE
    out = defaultdict(list)
    seen = set()
    cur = "JOIN phone_interpretation_state st ON st.extraction_id = %s.extraction_id AND st.generation = %s.generation"
    for r in conn.execute(text(
            "SELECT DISTINCT ON (e.record_uid) e.record_uid::text AS uid, e.kind, e.app, e.direction, e.sort_instant, "
            "e.body, e.call_duration_s, e.status, e.deleted_state, e.model_type, (SELECT string_agg(coalesce("
            "p.identity_key, ''), ',' ORDER BY p.identity_key) FROM phone_participations p WHERE p.record_uid = "
            "e.record_uid AND p.generation = e.generation AND NOT coalesce(p.is_phone_owner, false)) AS others, "
            "(SELECT min(p.identity_key) FROM phone_participations p WHERE p.record_uid = e.record_uid AND "
            "p.generation = e.generation AND (p.role IN ('sender', 'caller', 'From') OR p.implied_role = 'sender')) "
            "AS sender FROM phone_comm_events e " + cur % ("e", "e") + " WHERE e.extraction_id = :e ORDER BY "
            "e.record_uid, e.event_uid"), {"e": ext}).mappings():
        seen.add(r["uid"])
        at = r["sort_instant"].isoformat() if r["sort_instant"] else ""
        if r["kind"] == "call":
            key = ("call", r["others"] or "", at, r["direction"] or "", str(r["call_duration_s"] or ""))
        else:
            key = (r["kind"], r["app"] or "", r["sender"] or r["others"] or "", at,
                   hashlib.sha256((r["body"] or "").encode()).hexdigest()[:16])
        out[key].append((r["sort_instant"], r["uid"], r["model_type"], r["deleted_state"], r["status"]))
    fields = defaultdict(list)
    for r in conn.execute(text(
            "SELECT t.record_uid::text, t.field_path, t.effective_value FROM phone_texts t " + cur % ("t", "t") +
            " JOIN phone_record_summaries p ON p.record_uid = t.record_uid AND p.generation = t.generation WHERE "
            "t.extraction_id = :e AND p.parent_record_uid IS NULL AND NOT coalesce(t.is_sensitive, false)"),
            {"e": ext}):
        if r[0] not in seen and r[1].split(".")[-1].split("[")[0] not in VOLATILE:
            fields[r[0]].append((r[1], r[2] or ""))
    for r in conn.execute(text(
            "SELECT t.record_uid::text, t.model_type, t.deleted_state, t.first_instant FROM phone_record_summaries t "
            + cur % ("t", "t") + " WHERE t.extraction_id = :e AND t.parent_record_uid IS NULL"), {"e": ext}):
        if r[0] in seen:
            continue
        key = ("record", r[1], hashlib.sha256(repr(sorted(fields.get(r[0], ()))).encode()).hexdigest()[:24])
        out[key].append((r[3], r[0], r[1], r[2], None))
    for v in out.values():
        v.sort(key=lambda e: (e[0] is None, e[0] or datetime.min.replace(tzinfo=timezone.utc), e[1]))
    return dict(out)


def aligned(keys_a: dict, keys_b: dict):
    """``(key, a_entry | None, b_entry | None)`` for every key of either side, records sharing one key paired in
    time order (as approach 12's diff pairs them)."""
    for key in sorted(set(keys_a) | set(keys_b), key=repr):
        a, b = keys_a.get(key, []), keys_b.get(key, [])
        for j in range(max(len(a), len(b))):
            yield key, (a[j] if j < len(a) else None), (b[j] if j < len(b) else None)


def replacements(conn, case_id, record_uids) -> dict:
    """``{record_uid: {"replaced": bool, "words": str | None, "newer_extraction_id", "newer_record_uid",
    "newer_record_type"}}`` for each record of the case asked about; a record of a report in use is not replaced."""
    uids = sorted({str(u) for u in record_uids or [] if u})
    if len(uids) > MAX_RECORDS:
        raise TooMany("At most %d records can be checked at once; %d were asked." % (MAX_RECORDS, len(uids)))
    if not uids:
        return {}
    rows = conn.execute(text(
        "SELECT r.record_uid::text AS uid, r.extraction_id::text AS ext, e.standing FROM phone_record_summaries r "
        "JOIN phone_interpretation_state st ON st.extraction_id = r.extraction_id AND st.generation = r.generation "
        "JOIN phone_extractions e ON e.id = r.extraction_id WHERE e.case_id = CAST(:c AS uuid) AND "
        "r.record_uid::text = ANY(:u)"), {"c": str(case_id), "u": uids}).fetchall()
    out = {r.uid: {"replaced": False, "words": None, "newer_extraction_id": None, "newer_record_uid": None,
                   "newer_record_type": None} for r in rows}
    old = [r for r in rows if r.standing != "active"]
    if not old:
        return out
    newer_of, standing = {}, {}
    for r in conn.execute(text("SELECT id::text, supersedes_id::text, standing FROM phone_extractions WHERE "
                               "case_id = CAST(:c AS uuid)"), {"c": str(case_id)}):
        standing[r[0]] = r[2]
        if r[1]:
            newer_of[r[1]] = r[0]
    keys = {}

    def keys_of(ext):
        if ext not in keys:
            keys[ext] = keys_any(conn, ext)
        return keys[ext]
    for r in old:
        ext, seen = r.ext, set()
        while ext in newer_of and ext not in seen and standing.get(ext) != "active":
            seen.add(ext)
            ext = newer_of[ext]
        o = out[r.uid]
        o["replaced"] = True
        if standing.get(ext) != "active" or ext == r.ext:
            o["words"] = "%s %s" % (REPLACED, NONE_IN_USE)
            continue
        if not any(e[1] == r.uid for vs in keys_of(r.ext).values() for e in vs):
            o["words"] = "%s %s" % (REPLACED, NOT_KEYED)
            continue
        uid, hop = r.uid, r.ext
        # follow the chain one Replace at a time, so each step pairs a report with the one that replaced it
        chain, cur = [], r.ext
        while cur != ext:
            chain.append((cur, newer_of[cur]))
            cur = newer_of[cur]
        for a, b in chain:
            found = None
            for _key, ea, eb in aligned(keys_of(a), keys_of(b)):
                if ea is not None and ea[1] == uid:
                    found = eb
                    break
            if found is None:
                uid = None
                break
            uid, hop = found[1], b
        if uid is None:
            o["words"] = "%s %s" % (REPLACED, NEWER_LACKS)
            continue
        mt = next((e[2] for vs in keys_of(hop).values() for e in vs if e[1] == uid), None)
        o.update(words="%s %s" % (REPLACED, NEWER_HOLDS), newer_extraction_id=hop, newer_record_uid=uid,
                 newer_record_type=mt)
    return out
