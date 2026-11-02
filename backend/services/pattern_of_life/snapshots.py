"""Frozen pattern results, collected as ``phone_analysis`` links (07 section 6.4 item 13; 04 section 9.6).

A person who wants to keep what a pattern view showed (a Day view, a window, a Pattern grid, Places over time) freezes
it: the server recomputes the result from the stored projections (never from what the browser sends), and stores the
snapshot that lx-collect's registry requires: kind, subject, window, parameters, the mapping versions behind it, the
record ids behind the result and summary counts. The id is the snapshot's hash (``phone_analysis_snapshot_id``), so
freezing the same result twice gives the same id and a recompute on changed readings gives a new one. A snapshot is
never updated; reading it says whether the phones' readings have moved since ("stale").

Together and the statement check are not frozen here: a Together run and a statement-check evaluation are already
stored rows with their own ids (``pol_colocation_run``, the ``statement_check`` link type).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life import day as day_view
from services.pattern_of_life import grid as grid_mod

KINDS = ("day", "window", "grid", "places")
KIND_WORDS = {"day": "Day view", "window": "Window", "grid": "Pattern grid", "places": "Places over time"}
MAX_SPAN = timedelta(days=92)


class SnapshotError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def mapping_versions(conn, case_id, extraction_ids) -> dict:
    """Per extraction: the interpretation generation and the projection's mapping versions and signature; plus the
    case's cell dataset. The same set the statement check fingerprints (evaluation.inputs)."""
    out = {}
    for e in sorted(str(x) for x in extraction_ids):
        gen = conn.execute(text("SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e"),
                           {"e": e}).scalar()
        p = conn.execute(text(
            "SELECT interpretation_generation, activity_mapping_version, meaning_mapping_version, "
            "attribution_mapping_version, signature FROM pol_projection_state WHERE extraction_id = :e"),
            {"e": e}).mappings().first()
        out[e] = {"generation": gen, "projection": json.loads(json.dumps(dict(p), default=str)) if p else None}
    ds = conn.execute(text("SELECT dataset_id FROM pol_case_cell_dataset WHERE case_id = :c"), {"c": case_id}).scalar()
    return {"extractions": out, "cell_dataset_id": str(ds) if ds else None}


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).isoformat()


def _event_records(conn, exts, a, b, where="", params=None) -> list:
    return [r[0] for r in conn.execute(text(
        "SELECT DISTINCT record_uid::text FROM pol_activity_event_v WHERE extraction_id = ANY(CAST(:e AS uuid[])) AND "
        "instant_utc >= :a AND instant_utc < :b AND record_uid IS NOT NULL" + where + " ORDER BY 1"),
        dict(params or {}, e=[str(x) for x in exts], a=a, b=b))]


def _result(conn, case_id, kind, exts, labels, a, b, zone, zname, parameters):
    """(record_ids, summary_counts) for one kind, from the stored projections."""
    if kind in ("day", "window"):
        w = day_view.window(conn, exts, labels, a, b, include_passive=True)
        counts = {k: int(v) for k, v in w["totals"].items() if isinstance(v, int)}
        records = _event_records(conn, exts, a, b)
        place = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT record_uid::text FROM pol_place_observation WHERE extraction_id = ANY(CAST(:e AS uuid[])) "
            "AND start_utc < :b AND end_utc >= :a AND record_uid IS NOT NULL"),
            {"e": [str(x) for x in exts], "a": a, "b": b})]
        return sorted(set(records) | set(place)), counts
    if kind == "grid":
        ms = parameters.get("min_strength", "moderate")
        classes = tuple(parameters.get("classes") or ("interaction",))
        include_physical = bool(parameters.get("include_physical", False))
        if ms not in grid_mod.STRENGTH_ORDER or not set(classes) <= {"interaction", "device_state"}:
            raise SnapshotError("min_strength is weak, moderate or strong; classes are interaction and device_state.")
        g = grid_mod.grid(conn, exts, labels, a.astimezone(zone).date(), (b - timedelta(seconds=1)).astimezone(zone).date(),
                          zname, ms, classes, include_physical)
        counts = {"days": len(g["days"]), "breaks": len(g.get("breaks") or []),
                  "not_observed": len(g.get("not_observed") or [])}
        for d in g["days"]:
            for h in d["hours"]:
                counts["hours_" + h["state"]] = counts.get("hours_" + h["state"], 0) + 1
        allowed = list(grid_mod.STRENGTH_ORDER[grid_mod.STRENGTH_ORDER.index(ms):])
        records = _event_records(conn, exts, a, b, " AND activity_class = ANY(:k) AND strength = ANY(:s)",
                                 {"k": list(classes), "s": allowed})
        return records, counts
    rows = conn.execute(text(
        "SELECT source_kind, record_uid::text FROM pol_place_observation WHERE extraction_id = ANY(CAST(:e AS uuid[])) "
        "AND start_utc < :b AND end_utc >= :a"), {"e": [str(x) for x in exts], "a": a, "b": b}).fetchall()
    counts = {"observations": len(rows)}
    for sk, _ in rows:
        counts["source_" + sk] = counts.get("source_" + sk, 0) + 1
    return sorted({r for _, r in rows if r}), counts


def freeze(db, case_id, *, kind, subject, extraction_ids, labels, start: datetime, end: datetime, zone, zname,
           parameters=None, user=None) -> dict:
    from postgres import link_types
    if kind not in KINDS:
        raise SnapshotError("A pattern result is a day, window, grid or places.")
    if end <= start:
        raise SnapshotError("The end must be after the start.")
    if end - start > MAX_SPAN:
        raise SnapshotError("A frozen result covers at most 92 days.")
    if not extraction_ids:
        raise SnapshotError("This subject has no phone in the case.", 422)
    parameters = dict(parameters or {})
    conn = db.connection()
    records, counts = _result(conn, case_id, kind, extraction_ids, labels, start, end, zone, zname, parameters)
    snap = {"kind": kind, "subject": subject,
            "window": {"start": _iso(start), "end": _iso(end), "zone": zname},
            "parameters": parameters, "mapping_versions": mapping_versions(conn, case_id, extraction_ids),
            "record_ids": records, "summary_counts": counts}
    snap = link_types.validate_phone_analysis_snapshot(snap)
    sid = link_types.phone_analysis_snapshot_id(snap)
    names = ", ".join(sorted({labels.get(str(e)) or "Phone" for e in extraction_ids}))
    label = "%s, %s, %s to %s (%s)" % (KIND_WORDS[kind], names, snap["window"]["start"][:16].replace("T", " "),
                                       snap["window"]["end"][:16].replace("T", " "), zname)
    db.execute(text(
        "INSERT INTO pol_analysis_snapshot (id, case_id, kind, label, snapshot, record_count, created_by_user_id, "
        "created_by_name) VALUES (:i, :c, :k, :l, CAST(:s AS jsonb), :n, :u, :un) ON CONFLICT (id) DO NOTHING"),
        {"i": sid, "c": case_id, "k": kind, "l": label[:512], "s": json.dumps(snap, default=str), "n": len(records),
         "u": getattr(user, "id", None), "un": getattr(user, "name", None) or getattr(user, "email", None)})
    return read(conn, case_id, sid)


def read(conn, case_id, sid) -> dict | None:
    row = conn.execute(text("SELECT id, kind, label, snapshot, record_count, created_by_name, created_at FROM "
                            "pol_analysis_snapshot WHERE id = :i AND case_id = :c"), {"i": sid, "c": case_id}).mappings().first()
    if row is None:
        return None
    snap = row["snapshot"]
    exts = list((snap["mapping_versions"].get("extractions") or {}).keys())
    now = mapping_versions(conn, case_id, exts)
    return {"id": row["id"], "kind": row["kind"], "label": row["label"], "snapshot": snap,
            "record_count": row["record_count"], "created_by_name": row["created_by_name"],
            "created_at": row["created_at"], "stale": now != snap["mapping_versions"],
            "stale_words": ("The phones' readings changed after this result was frozen; the frozen result is kept as it "
                            "was." if now != snap["mapping_versions"] else None)}


def resolve_phone_analysis(db, case_id, target_id):
    from postgres import link_types
    row = db.execute(text("SELECT label, snapshot FROM pol_analysis_snapshot WHERE id = :i AND case_id = :c"),
                     {"i": str(target_id), "c": case_id}).mappings().first()
    if row is None:
        return None
    snap = row["snapshot"]
    return link_types.PhoneTarget(label=row["label"], mapping_versions=snap["mapping_versions"],
                                  members=tuple(snap["record_ids"]), metadata={"snapshot": snap})


def register():
    from postgres import link_types
    link_types.register_phone_resolver("phone_analysis", resolve_phone_analysis)
