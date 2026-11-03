"""Keeping an approach result (05 section 3.4; 02 decision 50; J-14b).

A result is frozen the way a pattern view is (``pattern_of_life.snapshots``): a snapshot of kind
``analysis_result`` holding the approach, its version and the result's key and kind (subject), its period
(window), the run's parameters, the phones' mapping versions, the records behind it and its counts. The snapshot id
is a hash of that content, so keeping the same result twice gives the same id and a rerun that changes the result
gives a new one. It is linked as ``phone_analysis`` and resolved by the one ``phone_analysis`` resolver.
"""
from __future__ import annotations

import json

from sqlalchemy import text

from services.phone_analysis import framework as F

KIND = "analysis_result"


def keep(db, case_id, result_id, user=None) -> dict:
    from postgres import link_types
    from services.pattern_of_life import snapshots
    conn = db.connection()
    r = F.result_detail(conn, case_id, result_id)
    run = conn.execute(text("SELECT parameters, approach_version FROM phone_analysis_runs WHERE id = :r"),
                       {"r": r["run_id"]}).first()
    exts = sorted({x["extraction_id"] for x in r["records"] if x["extraction_id"]})
    record_ids = sorted({x["record_uid"] for x in r["records"] if x["record_uid"]})
    ledger = sorted({x["ledger_transaction_id"] for x in r["records"] if x["ledger_transaction_id"]})
    snap = {"kind": KIND,
            "subject": {"approach": r["approach"], "approach_version": run.approach_version,
                        "result_key": r["result_key"], "result_kind": r["kind"], "strength": r["strength"],
                        "ledger_transaction_ids": ledger},
            "window": {"start": r["period_start"], "end": r["period_end"]},
            "parameters": run.parameters if isinstance(run.parameters, dict) else json.loads(run.parameters or "{}"),
            "mapping_versions": snapshots.mapping_versions(conn, str(case_id), exts),
            "record_ids": record_ids,
            "summary_counts": {"records": len(record_ids), "ledger_rows": len(ledger)}}
    snap = link_types.validate_phone_analysis_snapshot(json.loads(json.dumps(snap, default=str)))
    sid = link_types.phone_analysis_snapshot_id(snap)
    label = keep_label(r)
    db.execute(text(
        "INSERT INTO pol_analysis_snapshot (id, case_id, kind, label, snapshot, record_count, created_by_user_id, "
        "created_by_name) VALUES (:i, :c, :k, :l, CAST(:s AS jsonb), :n, :u, :un) ON CONFLICT (id) DO NOTHING"),
        {"i": sid, "c": str(case_id), "k": KIND, "l": label[:512], "s": json.dumps(snap, default=str),
         "n": len(record_ids), "u": getattr(user, "id", None),
         "un": getattr(user, "name", None) or getattr(user, "email", None)})
    return snapshots.read(conn, str(case_id), sid)


def keep_label(r) -> str:
    """Words for the kept item: the analysis, the result kind and its phones; never a person's state of mind."""
    from services.phone_analysis.approaches import TITLES
    m = r.get("measures") or {}
    phones = m.get("phones") or ([m["phone_label"]] if m.get("phone_label") else [])
    return "%s: %s%s (%s)" % (TITLES.get(r["approach"], r["approach"]), r["kind"].replace("_", " "),
                              (", " + " and ".join(phones)) if phones else "", F.LEAD_LABEL)


def list_kept(conn, case_id, limit=50, offset=0) -> dict:
    """The case's kept analysis results, newest first, with the full count."""
    total = int(conn.execute(text("SELECT count(*) FROM pol_analysis_snapshot WHERE case_id = :c AND kind = :k"),
                             {"c": str(case_id), "k": KIND}).scalar() or 0)
    items = [{"id": r.id, "label": r.label, "approach": (r.snapshot or {}).get("subject", {}).get("approach"),
              "record_count": int(r.record_count or 0), "created_by_name": r.created_by_name,
              "created_at": r.created_at.isoformat() if r.created_at else None}
             for r in conn.execute(text(
                 "SELECT id, label, snapshot, record_count, created_by_name, created_at FROM pol_analysis_snapshot WHERE "
                 "case_id = :c AND kind = :k ORDER BY created_at DESC, id LIMIT :l OFFSET :o"),
                 {"c": str(case_id), "k": KIND, "l": int(limit), "o": int(offset)})]
    return {"total": total, "offset": offset, "limit": limit, "items": items}


def kept_records(conn, case_id, kept_id) -> tuple:
    """(record ids, label) of a kept result, as frozen."""
    r = conn.execute(text("SELECT label, snapshot FROM pol_analysis_snapshot WHERE id = :i AND case_id = :c AND kind = "
                          ":k"), {"i": str(kept_id), "c": str(case_id), "k": KIND}).first()
    if r is None:
        raise LookupError("That kept result is not in this case.")
    return [str(x) for x in (r.snapshot or {}).get("record_ids") or []], r.label
