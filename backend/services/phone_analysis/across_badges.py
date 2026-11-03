"""Approach 2's per-message badge in Conversations (05 section 5.4): "Also on C2" or "Only on this phone" with the
reasons, read from the case's latest completed run of Messages across phones. Nothing is computed here: a message the
run did not judge gets no badge, and the screen says what the badges come from and whether the phones changed since.

A message can carry one badge per other phone (it can be on C2 and not on C3).
"""
from __future__ import annotations

from sqlalchemy import text

MAX_RECORDS = 500
CODE = "message_reconciliation"
KINDS = ("both_sides", "deleted_one_side", "one_side_only", "ambiguous_pair")


class TooMany(ValueError):
    pass


def latest_run(conn, case_id):
    return conn.execute(text(
        "SELECT id, finished_at, input_revision, approach_version FROM phone_analysis_runs WHERE case_id = "
        "CAST(:c AS uuid) AND approach = :a AND status = 'completed' ORDER BY finished_at DESC NULLS LAST, id DESC "
        "LIMIT 1"), {"c": str(case_id), "a": CODE}).first()


def _current(conn, case_id, run) -> bool:
    from services.phone_analysis import framework as F
    from services.phone_analysis import message_reconciliation as R
    return F.sha256(F.input_manifest(conn, case_id, R)) == run.input_revision


def _badge(kind, measures, role, other_label, other_uid, reasons, result_id):
    deleted_here = role == "deleted_copy"
    if kind in ("both_sides", "deleted_one_side"):
        words = "Also on %s" % other_label
        if kind == "deleted_one_side":
            words += (": deleted here, intact on %s" % other_label) if deleted_here else (
                ": deleted on %s, intact here" % other_label)
    elif kind == "one_side_only":
        words = "Only on this phone, not on %s" % other_label
    else:
        words = "Two copies on %s are equally close; neither is chosen" % other_label
    return {"kind": kind, "other_phone": other_label, "other_record_uid": other_uid, "tier": measures.get("tier"),
            "words": words, "reasons": reasons, "result_id": result_id}


def badges(conn, case_id, record_uids) -> dict:
    """``{"run": {...} | None, "items": {record_uid: [badge, ...]}}``; a message the latest run did not judge is
    not in ``items``."""
    uids = sorted({str(u) for u in record_uids or [] if u})
    if len(uids) > MAX_RECORDS:
        raise TooMany("At most %d messages can be checked at once; %d were asked." % (MAX_RECORDS, len(uids)))
    run = latest_run(conn, case_id)
    if run is None or not uids:
        return {"run": None if run is None else _run_out(conn, case_id, run), "items": {}}
    rows = conn.execute(text(
        "SELECT r.id::text AS result_id, r.kind, r.measures, r.directions, rr.record_uid::text AS uid, rr.role, "
        "rr.extraction_id::text AS ext FROM phone_analysis_result_records rr JOIN phone_analysis_results r ON "
        "r.id = rr.result_id WHERE r.run_id = :run AND r.kind = ANY(:k) AND rr.record_uid::text = ANY(:u)"),
        {"run": run.id, "k": list(KINDS), "u": uids}).fetchall()
    ids = sorted({r.result_id for r in rows})
    copies = {}
    if ids:
        for r in conn.execute(text(
                "SELECT result_id::text, record_uid::text, extraction_id::text FROM phone_analysis_result_records "
                "WHERE result_id::text = ANY(:i) AND record_uid IS NOT NULL"), {"i": ids}):
            copies.setdefault(r[0], []).append((r[1], r[2]))
    from services.phone import readings
    labels = readings.phone_labels(conn, str(case_id))
    items = {}
    for r in rows:
        m = r.measures or {}
        reasons = [d.get("detail") for d in (r.directions or {}).get("undercuts", []) if d.get("detail")] \
            if r.kind == "one_side_only" else []
        if r.kind == "one_side_only":
            other_label, other_uid = m.get("not_on"), None
        else:
            others = [(u, e) for u, e in copies.get(r.result_id, []) if u != r.uid and e != r.ext]
            if not others:
                continue
            other_uid, other_ext = others[0]
            other_label = labels.get(other_ext, "another phone")
            if r.kind == "ambiguous_pair":
                other_uid = None
        b = _badge(r.kind, m, r.role, other_label, other_uid, reasons, r.result_id)
        if b not in items.setdefault(r.uid, []):
            items[r.uid].append(b)
    for v in items.values():
        v.sort(key=lambda b: (b["other_phone"] or "", b["kind"]))
    return {"run": _run_out(conn, case_id, run), "items": items}


def _run_out(conn, case_id, run) -> dict:
    return {"id": str(run.id), "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "current": _current(conn, case_id, run)}


def clock_offsets(conn, case_id) -> dict:
    """Approach 2's clock offset readings per phone pair and family, from the latest completed run, for the incident
    window to state beside its times (05 sections 5.3.5 and 16). The offset is a reading about two phones' clocks;
    it never moves a time."""
    run = latest_run(conn, case_id)
    if run is None:
        return {"run": None, "items": []}
    items = [{"phones": (r.measures or {}).get("phones"), "family": (r.measures or {}).get("family"),
              "timestamp_class": r.strength, "offset_s": (r.measures or {}).get("offset_s"),
              "pairs": (r.measures or {}).get("n"), "words": (r.measures or {}).get("words")}
             for r in conn.execute(text(
                 "SELECT strength, measures FROM phone_analysis_results WHERE run_id = :r AND kind = 'clock_offset' "
                 "ORDER BY measures->>'phones', measures->>'family'"), {"r": run.id})]
    return {"run": _run_out(conn, case_id, run), "items": items}
