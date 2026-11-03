"""Gate measurements of the approaches (docs/cellebrite/05 sections 4.7 to 16c, "Measurement first"; 05-S1).

Each measure is a read-only function over one case: counts only, never content, never identifiers. ``record`` runs
an approach's measure and stores it in ``phone_analysis_measurements`` with the gate computed from the thresholds in
the approach's section. ``MEASURES`` maps an approach code to ``(version, fn(conn, case_id) -> (result, gate))``.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from services.phone_analysis.framework import AnalysisError

MEASURES: dict = {}


def measure(code, version):
    def wrap(fn):
        MEASURES[code] = (version, fn)
        return fn
    return wrap


def run(conn, case_id, code) -> tuple:
    if code not in MEASURES:
        raise AnalysisError("There is no measurement for %s yet." % code)
    version, fn = MEASURES[code]
    result, gate = fn(conn, str(case_id))
    return version, result, gate


def record(conn, scope, case_id, code, by) -> dict:
    version, result, gate = run(conn, case_id, code)
    mid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_analysis_measurements (id, scope, case_id, approach, measure_version, result, gate, "
        "recorded_by) VALUES (:i, :s, :c, :a, :v, CAST(:r AS jsonb), :g, :b)"),
        {"i": mid, "s": scope, "c": str(case_id) if case_id else None, "a": code, "v": version,
         "r": json.dumps(result, sort_keys=True, default=str), "g": gate, "b": by})
    return {"id": str(mid), "scope": scope, "case_id": str(case_id) if case_id else None, "approach": code,
            "measure_version": version, "result": result, "gate": gate}


def rows(conn, case_id=None, code=None) -> list:
    q, p = "SELECT * FROM phone_analysis_measurements WHERE true", {}
    if case_id:
        q += " AND case_id = :c"
        p["c"] = str(case_id)
    else:
        q += " AND scope = 'corpus'"
    if code:
        q += " AND approach = :a"
        p["a"] = code
    return [{"id": str(r.id), "scope": r.scope, "case_id": str(r.case_id) if r.case_id else None,
             "approach": r.approach, "measure_version": r.measure_version, "result": r.result, "gate": r.gate,
             "recorded_at": r.recorded_at.isoformat(), "recorded_by": r.recorded_by}
            for r in conn.execute(text(q + " ORDER BY recorded_at DESC, id"), p)]


# ---- the measures (05-S1): counts only, read-only, per case ---------------------------------------------------------
# Each returns (result, gate). Gates follow the thresholds of the approach's "Measurement first" section; a count that
# needs a part not built yet is reported under ``not_counted`` with the reason, and the gate is then ``inconclusive``
# unless the counted parts already decide it.

def _phones(conn, case_id) -> dict:
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    return {str(r[0]): labels.get(str(r[0])) for r in conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' ORDER BY id"), {"c": case_id})}


def _per_phone(conn, case_id, sql, **params) -> dict:
    phones = _phones(conn, case_id)
    out = {label: 0 for label in phones.values()}
    for r in conn.execute(text(sql), dict(params, c=case_id)):
        if str(r[0]) in phones:
            out[phones[str(r[0])]] = int(r[1] or 0)
    return out


def _ledger_rows(conn, case_id) -> int:
    return int(conn.execute(text("SELECT count(*) FROM financial_transactions WHERE case_id = :c AND ledger_status = "
                                 "'admitted' AND superseded_by_id IS NULL"), {"c": case_id}).scalar() or 0)


@measure("money_signals", "m1.1")
def m1(conn, case_id):
    """M-1a to M-1e (05 4.7). Gate: build if at least 20 readings bind to an account or a no-statement lead of class
    transactional or account exists; not measurable when the case holds no ledger."""
    from services.phone_analysis import institutions as INST
    from services.phone_analysis import money_signals as MS
    d = INST.load()
    reviewed_pkgs = {p for e in d["reviewed"] for p in e.get("app_packages") or []}
    draft_pkgs = {p for e in d["entries"] for p in e.get("app_packages") or []}
    phones = _phones(conn, case_id)
    m1a = {}
    for label in phones.values():
        m1a[label] = {"notifications": 0, "distinct_service_identifiers": 0, "in_reviewed_directory": 0,
                      "in_directory_including_drafts": 0}
    for r in conn.execute(text(
            "SELECT r.extraction_id, x.value, count(*) FROM pv_record r LEFT JOIN pv_text x ON x.record_uid = "
            "r.record_uid AND x.field_path = 'ServiceIdentifier' AND x.value_index = 0 WHERE r.case_id = :c AND "
            "r.model_type = 'Notification' GROUP BY 1, 2"), {"c": case_id}):
        label = phones.get(str(r[0]))
        if label is None:
            continue
        m = m1a[label]
        m["notifications"] += int(r[2])
        if r[1]:
            m["distinct_service_identifiers"] += 1
            m["in_reviewed_directory"] += int(r[1] in reviewed_pkgs)
            m["in_directory_including_drafts"] += int(r[1] in draft_pkgs)
    params = {k: v["default"] for k, v in MS.PARAMETERS.items()}
    results, counts = MS.analyse(conn, case_id, params)
    m1b = {}
    for r in results:
        if r["kind"] == "money_reading" and r["measures"]["currency"] and r["measures"]["amount_minor"] is not None:
            key = "%s|%s" % (r["measures"]["phone_label"], r["measures"]["signal"])
            m1b[key] = m1b.get(key, 0) + 1
    ledger = _ledger_rows(conn, case_id)
    bound = counts["binding"].get("bound", 0)
    leads = counts.get("leads", {})
    strong_leads = sum(n for k, n in leads.items() if k.startswith("no_statement_found:") and
                       k.split(":")[1] in ("transactional", "account"))
    result = {"m1a": m1a, "m1b_readings_with_amount_and_currency": m1b,
              "m1c_binding": counts["binding"], "m1d_outcome": counts["outcome"], "m1d_lag_days": counts["lag_days"],
              "m1e_leads": leads, "ledger_rows": ledger, "directory": counts["directory"]}
    if ledger == 0:
        result["note"] = "not measurable: the case holds no ledger"
        return result, "inconclusive"
    return result, ("build" if bound >= 20 or strong_leads >= 1 else "do_not_build")


@measure("message_reconciliation", "m2.1")
def m2(conn, case_id):
    """M-2a to M-2d (05 5.6) over each pair of phones in the case: owner identities seen on the other phone, shared
    parties, message pairs with an equal body of at least 10 characters within 300 seconds (by app), their median gap,
    and pairs whose deleted states differ. Gate: build if at least 100 such pairs in total or 10 differing."""
    phones = _phones(conn, case_id)
    ids = sorted(phones)
    pairs = []
    total = differing = 0
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            owner_cross = conn.execute(text(
                "SELECT count(DISTINCT o.identity_key) FROM pv_owner_candidate o JOIN pv_comm_party p ON p.identity_key "
                "= o.identity_key AND p.extraction_id = :b WHERE o.extraction_id = :a"), {"a": a, "b": b}).scalar()
            shared = conn.execute(text(
                "SELECT count(*) FROM (SELECT identity_key FROM pv_comm_party WHERE extraction_id = :a AND identity_key "
                "IS NOT NULL INTERSECT SELECT identity_key FROM pv_comm_party WHERE extraction_id = :b AND identity_key "
                "IS NOT NULL) s"), {"a": a, "b": b}).scalar()
            rows = conn.execute(text(
                "SELECT coalesce(x.app, ''), count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(extract(epoch "
                "FROM x.sort_instant - y.sort_instant))), count(*) FILTER (WHERE x.deleted_state IS DISTINCT FROM "
                "y.deleted_state) FROM pv_comm_event x JOIN pv_comm_event y ON y.extraction_id = :b AND y.kind = "
                "'message' AND md5(y.body) = md5(x.body) AND abs(extract(epoch FROM x.sort_instant - y.sort_instant)) "
                "<= 300 WHERE x.extraction_id = :a AND x.kind = 'message' AND length(x.body) >= 10 GROUP BY 1"),
                {"a": a, "b": b}).fetchall()
            n = sum(int(r[1]) for r in rows)
            d = sum(int(r[3]) for r in rows)
            total, differing = total + n, differing + d
            pairs.append({"phones": [phones[a], phones[b]], "m2a_owner_identities_seen_on_other": int(owner_cross or 0),
                          "m2a_shared_parties": int(shared or 0),
                          "m2b_body_time_pairs_by_app": {r[0] or "unknown": int(r[1]) for r in rows},
                          "m2c_median_gap_seconds": {r[0] or "unknown": float(r[2]) for r in rows if r[2] is not None},
                          "m2d_deleted_state_differs": d})
    result = {"pairs": pairs, "body_time_pairs": total, "deleted_state_differs": differing,
              "not_counted": {"tiers": "matched_strong needs approach 2's tiers (not built)"}}
    if len(ids) < 2:
        result["note"] = "not measurable: the case holds fewer than two phones"
        return result, "inconclusive"
    return result, ("build" if total >= 100 or differing >= 10 else "inconclusive")


@measure("deletion_timeline", "m3.2")
def m3(conn, case_id):
    """M-3a to M-3e (05 6.6), read from the captured bodies for the named sets (m3.1 read them from the text table,
    which holds String fields only, so M-3b and M-3c were always 0). Gate: build if at least 3 phones have 50 or more
    deleted messages or M-3d is non-zero on any phone."""
    from services.phone_analysis import deletion_timeline as D
    from services.phone_analysis import fields as FV
    phones = _phones(conn, case_id)
    deleted = _per_phone(conn, case_id, "SELECT extraction_id, count(*) FROM pv_comm_event WHERE case_id = :c AND kind = "
                         "'message' AND deleted_state IS NOT NULL AND deleted_state NOT IN ('Intact', 'Unknown') GROUP BY 1")
    by_type = {}
    for r in conn.execute(text(
            "SELECT extraction_id, model_type, deleted_state, count(*) FROM pv_record WHERE case_id = :c AND "
            "parent_record_uid IS NULL GROUP BY 1, 2, 3"), {"c": case_id}):
        if str(r[0]) in phones:
            by_type.setdefault(phones[str(r[0])], {}).setdefault(r[1], {})[r[2] or "none"] = int(r[3])
    labels, reasons, self_destruct, wipes = {}, {}, {}, {}
    params = {k: v["default"] for k, v in D.PARAMETERS.items()}
    absent, holes, convs = {}, {}, {}
    for ext, label in phones.items():
        vals = FV.field_values(conn, ext, ("InstantMessage",), ("Label", "DeletionReason", "SelfDestructDuration"))
        for v in vals.values():
            for x in v["values"].get("Label", ()):
                labels[x] = labels.get(x, 0) + 1
            for x in v["values"].get("DeletionReason", ()):
                reasons[x] = reasons.get(x, 0) + 1
            if any(D.timespan_seconds(x) for x in v["values"].get("SelfDestructDuration", ())):
                self_destruct[label] = self_destruct.get(label, 0) + 1
        ev = FV.field_values(conn, ext, ("DeviceEvent",), ("EventType",))
        wipes[label] = sum(1 for v in ev.values() if "Wipe" in v["values"].get("EventType", ()))
        counts = {"references": 0, "referenced_absent": 0, "references_without_id": 0, "deleted_records": 0,
                  "conversations_tested": 0, "selective_clearing": 0, "holes": 0, "gaps_without_app_data": 0,
                  "concealment_apps": 0, "apps_removed": 0, "wipes": 0, "power_offs": 0, "scrambled": 0,
                  "by_explanation": {}}
        from collections import defaultdict
        c2 = defaultdict(int, counts)
        c2["by_explanation"] = defaultdict(int)
        D.analyse_phone(conn, ext, label, params, c2)
        absent[label] = c2["referenced_absent"]
        holes[label] = c2["holes"]
        convs[label] = int(conn.execute(text(
            "SELECT count(*) FROM pv_thread t WHERE t.extraction_id = :e AND t.event_count >= 20 AND EXISTS (SELECT 1 "
            "FROM pv_comm_event e WHERE e.thread_key = t.thread_key AND e.deleted_state IN ('Deleted', 'Trash'))"),
            {"e": ext}).scalar() or 0)
    result = {"m3a_deleted_messages": deleted, "m3a_by_type": by_type, "m3b_labels": labels,
              "m3b_self_destruct_nonzero": self_destruct, "m3c_deletion_reasons": reasons, "m3c_wipes": wipes,
              "m3d_referenced_absent": absent, "m3e_conversations_20_plus_with_deletion": convs, "m3e_holes": holes}
    passed = sum(1 for n in deleted.values() if n >= 50) >= 3 or any(absent.values())
    return result, ("build" if passed else "inconclusive")


def _type_counts(conn, case_id, types):
    phones = _phones(conn, case_id)
    out = {label: {t: 0 for t in types} for label in phones.values()}
    for r in conn.execute(text("SELECT extraction_id, model_type, count(*) FROM pv_record WHERE case_id = :c AND "
                               "model_type = ANY(:t) GROUP BY 1, 2"), {"c": case_id, "t": list(types)}):
        if str(r[0]) in phones:
            out[phones[str(r[0])]][r[1]] = int(r[2])
    return out


@measure("awareness", "m4.1")
def m4(conn, case_id):
    """M-4a, M-4c (05 7.6): incoming messages with a read time; timed ChatActivity. Gate: build read-and-latency if 5
    phones have read times on 20 percent of incoming messages."""
    phones = _phones(conn, case_id)
    share = {}
    for r in conn.execute(text(
            "SELECT e.extraction_id, count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM pv_comm_party p WHERE "
            "p.event_uid = e.event_uid AND p.is_phone_owner AND p.date_read IS NOT NULL)) FROM pv_comm_event e WHERE "
            "e.case_id = :c AND e.kind = 'message' AND e.direction = 'incoming' GROUP BY 1"), {"c": case_id}):
        if str(r[0]) in phones:
            share[phones[str(r[0])]] = {"incoming": int(r[1]), "owner_read": int(r[2])}
    activity = _per_phone(conn, case_id, "SELECT extraction_id, count(*) FROM pv_comm_event WHERE case_id = :c AND kind "
                          "= 'chat_activity' AND sort_instant IS NOT NULL GROUP BY 1")
    enough = sum(1 for v in share.values() if v["incoming"] and v["owner_read"] * 5 >= v["incoming"])
    return ({"m4a_read_times": share, "m4c_timed_chat_activity": activity,
             "not_counted": {"m4b": "reply pairs need approach 4's pairing (not built)"}},
            "build" if enough >= 5 else "inconclusive")


@measure("device_users", "m5.1")
def m5(conn, case_id):
    """M-5a (05 8.6): per phone pair, 15-minute bins where both phones have a location point."""
    phones = _phones(conn, case_id)
    ids = sorted(phones)
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            n = conn.execute(text(
                "SELECT count(*) FROM (SELECT DISTINCT floor(extract(epoch FROM instant) / 900) b FROM pv_location_point "
                "WHERE extraction_id = :a AND instant IS NOT NULL INTERSECT SELECT DISTINCT floor(extract(epoch FROM "
                "instant) / 900) FROM pv_location_point WHERE extraction_id = :b AND instant IS NOT NULL) s"),
                {"a": a, "b": b}).scalar()
            pairs.append({"phones": [phones[a], phones[b]], "m5a_bins_both_placed": int(n or 0)})
    best = max((p["m5a_bins_both_placed"] for p in pairs), default=0)
    return ({"pairs": pairs, "not_counted": {"m5b": "markers need approach 5", "m5c": "interaction days need 04"}},
            "build" if best >= 200 else "inconclusive")


@measure("other_devices", "m6.1")
def m6(conn, case_id):
    """M-6a (05 9.6): per phone, records of the types that name other devices and accounts."""
    return ({"m6a_records": _type_counts(conn, case_id, ("WirelessNetwork", "BluetoothDevice", "UserAccount", "Cookie",
                                                         "Password", "DeviceConnectivity")),
             "not_counted": {"m6b": "shared keys need approach 6's key extraction"}}, "inconclusive")


@measure("typed_words", "m7.1")
def m7(conn, case_id):
    """M-7a (05 10.6): dictionary and autofill records per phone; vocabulary hits need the case vocabulary."""
    return ({"m7a_records": _type_counts(conn, case_id, ("DictionaryWord", "Autofill")),
             "not_counted": {"vocabulary_hits": "the case vocabulary is approach 7's input (not built)"}}, "inconclusive")


@measure("media_spread", "m8.1")
def m8(conn, case_id):
    """M-8a, M-8b (05 11.6): attachment-linked files with an MD5 per phone; exact MD5 groups spanning phones. Gate:
    build the exact tier at 25 or more groups."""
    linked = _per_phone(conn, case_id, "SELECT f.extraction_id, count(DISTINCT f.file_uid) FROM pv_file f JOIN "
                        "pv_attachment_link a ON a.file_uid = f.file_uid WHERE f.case_id = :c AND f.md5 IS NOT NULL GROUP BY 1")
    groups = conn.execute(text(
        "SELECT count(*) FROM (SELECT f.md5 FROM pv_file f JOIN pv_attachment_link a ON a.file_uid = f.file_uid WHERE "
        "f.case_id = :c AND f.md5 IS NOT NULL GROUP BY f.md5 HAVING count(DISTINCT f.extraction_id) >= 2) g"),
        {"c": case_id}).scalar()
    return ({"m8a_attachment_linked_with_md5": linked, "m8b_exact_groups_spanning_phones": int(groups or 0),
             "not_counted": {"m8c": "the perceptual sample needs approach 2's both-sides media messages (not built)"}},
            "build" if (groups or 0) >= 25 else "inconclusive")


@measure("intent", "m9.1")
def m9(conn, case_id):
    """M-9a (05 12.6): searches and visited pages per phone."""
    return ({"m9a_records": _type_counts(conn, case_id, ("SearchedItem", "VisitedPage", "WebBookmark")),
             "not_counted": {"m9b": "vocabulary hits need the case vocabulary"}}, "inconclusive")


@measure("plans", "m10.1")
def m10(conn, case_id):
    """M-10a (05 13.6): calendar entries, check-ins and notes per phone."""
    return ({"m10a_records": _type_counts(conn, case_id, ("CalendarEntry", "Note", "Location")),
             "not_counted": {"m10b": "placed check-ins need approach 10's place join"}}, "inconclusive")


@measure("relationships", "m11.2")
def m11(conn, case_id):
    """M-11a to M-11c (05 14.6): contacts and contacts with a saved time per phone; identities with 20 or more
    communications on a phone; people named differently on two phones. Gate: build if 3 phones have created times and
    10 identities have 20 communications."""
    from services.phone_analysis import relationships as R
    contacts = _type_counts(conn, case_id, ("Contact",))
    created = _per_phone(conn, case_id, "SELECT t.extraction_id, count(DISTINCT t.record_uid) FROM pv_time t JOIN "
                         "pv_record r ON r.record_uid = t.record_uid WHERE t.case_id = :c AND r.model_type = 'Contact' "
                         "AND t.field_path = 'TimeCreated' AND t.instant IS NOT NULL GROUP BY 1")
    busy = int(conn.execute(text(
        "SELECT count(*) FROM (SELECT p.extraction_id, p.identity_key FROM pv_comm_party p WHERE p.case_id = :c AND "
        "p.identity_key IS NOT NULL AND NOT p.is_phone_owner GROUP BY 1, 2 HAVING count(DISTINCT p.event_uid) >= 20) s"),
        {"c": case_id}).scalar() or 0)
    _, counts = R.analyse(conn, case_id, {k: v["default"] for k, v in R.PARAMETERS.items()})
    with_created = sum(1 for v in created.values() if v)
    return ({"m11a_contacts": contacts, "m11a_created_times": created, "m11b_identities_20_plus": busy,
             "m11c_named_differently": counts.get("named_differently", 0)},
            "build" if with_created >= 3 and busy >= 10 else "inconclusive")


@measure("extraction_comparison", "m12.1")
def m12(conn, case_id):
    """M-12c (05 15.6): per phone pair, equal Cellebrite record ids (a second extraction of one device shares ids)."""
    phones = _phones(conn, case_id)
    ids = sorted(phones)
    pairs = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            n = conn.execute(text(
                "SELECT count(*) FROM (SELECT cellebrite_id FROM pv_record WHERE extraction_id = :a AND cellebrite_id IS "
                "NOT NULL INTERSECT SELECT cellebrite_id FROM pv_record WHERE extraction_id = :b AND cellebrite_id IS "
                "NOT NULL) s"), {"a": a, "b": b}).scalar()
            pairs.append({"phones": [phones[a], phones[b]], "m12c_equal_record_ids": int(n or 0)})
    return ({"pairs": pairs}, "inconclusive")


@measure("incident_window", "m13.1")
def m13(conn, case_id):
    """M-13a (05 16.6): per phone, records with an event time; the window default was set by cb-pol."""
    return ({"m13a_timed_entries": _per_phone(conn, case_id, "SELECT extraction_id, count(*) FROM pv_timeline_entry "
                                              "WHERE case_id = :c AND is_event_time GROUP BY 1")}, "inconclusive")


def main(argv=None) -> int:
    """``python -m services.phone_analysis.measurements --case <id> [--case <id>] [--approach <code>] --by <email>``:
    run and record (counts only)."""
    import argparse
    from postgres.session import _get_engine as get_engine
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", action="append", required=True)
    ap.add_argument("--approach", action="append")
    ap.add_argument("--by", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    engine = get_engine()
    for case in a.case:
        for code in a.approach or sorted(MEASURES):
            with engine.begin() as c:
                c.execute(text("SET LOCAL statement_timeout = '15min'"))
                if a.dry_run:
                    version, result, gate = run(c, case, code)
                    out = {"approach": code, "gate": gate, "result": result}
                else:
                    out = record(c, "case", case, code, a.by)
            print(json.dumps({"case": case, "approach": code, "gate": out["gate"], "result": out["result"]},
                             sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
