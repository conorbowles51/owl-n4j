"""Together and apart (04 section 8.4, unit U9).

``verdict`` is the one implementation of the pair rule; 05 approach 5 calls it (C10), so a pair can never be
"together" on one screen and "apart" on another. For two observations ``a`` and ``b``:

- ``dt`` = the gap between their time intervals (0 when they overlap); pairs further apart than ``window_s`` are not
  compared;
- ``R`` = ``r_a + r_b``; an unknown radius is replaced by the run's ``assumed_radius_m`` and the pair is ``assumed``;
- ``compatible`` when ``d <= R`` (tight when ``R <= 150 m``, otherwise broad: never called "together");
  ``separated`` when ``d - R > v * dt`` with ``v = max_speed_mps``; otherwise ``undetermined``.
- An observation without a stated offset never makes a pair ``separated`` (it is ``undetermined``, flagged) and is
  flagged on a ``compatible`` pair.

Beyond coordinates: the same BSSID seen by both within the window is ``compatible`` (basis ``shared_bssid``, radius the
anchor's or 150 m); the same full cell key within 15 minutes is ``compatible``, broad (basis ``shared_cell``). The SSID
is never used. Nothing is capped; a run whose estimated pairs exceed ``BACKGROUND_PAIRS`` runs in the background and
every page carries the total.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from collections import deque
from datetime import timedelta

from sqlalchemy import text

from services.pattern_of_life.places import ROUTINE_KINDS, haversine_m

log = logging.getLogger(__name__)

DEFAULT_PARAMS = {"window_s": 300, "assumed_radius_m": 1000.0, "max_speed_mps": 40.0, "tight_radius_m": 150.0,
                  "episode_gap_s": 1800, "cell_window_s": 900, "unanchored_bssid_radius_m": 150.0,
                  "include_synced": False}
BACKGROUND_PAIRS = 2_000_000
PAGE = 1000


def verdict(a, b, params=None):
    """``a``, ``b``: dicts with lat, lon, radius_m (None = unknown), start, end, offset_status. Returns the verdict
    dict, or None when the pair is not compared (further apart in time than the window)."""
    p = dict(DEFAULT_PARAMS, **(params or {}))
    a_end, b_end = a.get("end") or a["start"], b.get("end") or b["start"]
    gap = max((b["start"] - a_end).total_seconds(), (a["start"] - b_end).total_seconds(), 0.0)
    if gap > p["window_s"]:
        return None
    assumed = a.get("radius_m") is None or b.get("radius_m") is None
    ra = a["radius_m"] if a.get("radius_m") is not None else p["assumed_radius_m"]
    rb = b["radius_m"] if b.get("radius_m") is not None else p["assumed_radius_m"]
    r = ra + rb
    d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    flags = []
    offset_absent = a.get("offset_status", "explicit") != "explicit" or b.get("offset_status", "explicit") != "explicit"
    if offset_absent:
        flags.append("offset_absent")
    if assumed:
        flags.append("assumed_radius")
    if d <= r:
        v = "compatible"
    elif d - r > p["max_speed_mps"] * gap and not offset_absent:
        v = "separated"
    else:
        v = "undetermined"
    return {"verdict": v, "distance_m": d, "radii_sum_m": r, "dt_s": gap, "assumed": assumed,
            "tight": v == "compatible" and r <= p["tight_radius_m"], "flags": flags, "basis": "coordinates"}


def _observations(conn, extraction_ids, start, end, include_synced):
    q = ("SELECT id, extraction_id, lat, lon, radius_m, start_utc AS start, end_utc AS \"end\", offset_status, "
         "attribution_flags FROM pol_place_observation WHERE extraction_id = ANY(CAST(:e AS uuid[])) AND "
         "kind = ANY(:k) AND start_utc < :b AND end_utc >= :a")
    if not include_synced:
        q += " AND NOT ('synced_from_account' = ANY(attribution_flags))"
    return [dict(r._mapping) for r in conn.execute(text(q + " ORDER BY start_utc, id"),
                                                    {"e": [str(x) for x in extraction_ids], "k": list(ROUTINE_KINDS),
                                                     "a": start, "b": end})]


def sweep_pairs(A, B, params=None):
    """Every compared pair of two time-ordered observation lists, two pointers over ``[start - W, end + W]``."""
    p = dict(DEFAULT_PARAMS, **(params or {}))
    w = timedelta(seconds=p["window_s"])
    out = []
    active = deque()
    j = 0
    for a in A:
        a_end = a.get("end") or a["start"]
        while j < len(B) and B[j]["start"] <= a_end + w:
            active.append(B[j])
            j += 1
        while active and (active[0].get("end") or active[0]["start"]) < a["start"] - w:
            active.popleft()
        for b in active:
            if (b.get("end") or b["start"]) < a["start"] - w:
                continue
            v = verdict(a, b, p)
            if v is not None:
                out.append((a, b, v))
    return out


def _bssid_pairs(conn, case_id, ea, eb, start, end, p):
    from services.pattern_of_life.places import _bssid_evidence
    ev = [x for x in _bssid_evidence(conn, case_id) if start <= x[2] < end]
    anchors = {r[0]: r[1] for r in conn.execute(text(
        "SELECT bssid_norm, radius_m FROM pol_wifi_anchor WHERE case_id = :c AND status = 'anchored'"), {"c": case_id})}
    sa = [x for x in ev if str(x[0]) in ea]
    sb = [x for x in ev if str(x[0]) in eb]
    out = []
    w = timedelta(seconds=p["window_s"])
    by_b = {}
    for x in sb:
        by_b.setdefault(x[1], []).append(x)
    for x in sa:
        for y in by_b.get(x[1], ()):
            if abs(x[2] - y[2]) <= w:
                r = 2 * anchors.get(x[1], p["unanchored_bssid_radius_m"])
                out.append(({"ref": "rec:%s" % x[3], "start": x[2]}, {"ref": "rec:%s" % y[3], "start": y[2]},
                            {"verdict": "compatible", "distance_m": None, "radii_sum_m": r,
                             "dt_s": abs((x[2] - y[2]).total_seconds()), "assumed": False,
                             "tight": r <= p["tight_radius_m"], "flags": [], "basis": "shared_bssid"}))
    return out


def _cell_pairs(conn, ea, eb, start, end, p):
    from services.pattern_of_life.places import tower_key
    from services.phone import ids
    towers = {}
    for e in list(ea) + list(eb):
        for doc, ordinal, body in conn.execute(text(
                "SELECT document_index, ordinal, body FROM phone_records WHERE extraction_id = :e AND model_type = "
                "'CellTower'"), {"e": e}):
            k = tower_key(body)
            if None in (k["mcc"], k["mnc"], k["lac"], k["cid"]):
                continue
            uid = ids.record_uid(e, doc, ordinal)
            t = conn.execute(text("SELECT instant_utc FROM pol_activity_event WHERE extraction_id = :e AND "
                                  "record_uid = :u ORDER BY instant_utc LIMIT 1"), {"e": e, "u": uid}).scalar()
            if t is None or not (start <= t < end):
                continue
            towers.setdefault(e, []).append(((k["radio"], k["mcc"], k["mnc"], k["lac"], k["cid"]), t, uid))
    out = []
    w = timedelta(seconds=p["cell_window_s"])
    for x_e in ea:
        for y_e in eb:
            for kx, tx, ux in towers.get(x_e, ()):
                for ky, ty, uy in towers.get(y_e, ()):
                    if kx == ky and abs(tx - ty) <= w:
                        out.append(({"ref": "rec:%s" % ux, "start": tx}, {"ref": "rec:%s" % uy, "start": ty},
                                    {"verdict": "compatible", "distance_m": None, "radii_sum_m": None,
                                     "dt_s": abs((tx - ty).total_seconds()), "assumed": False, "tight": False,
                                     "flags": ["broad"], "basis": "shared_cell"}))
    return out


def estimate_pairs(conn, ea, eb, start, end) -> int:
    """Pairs from hourly observation counts (an upper-bound estimate used only to choose a background run)."""
    rows = conn.execute(text(
        "SELECT date_trunc('hour', start_utc) AS h, sum(CASE WHEN extraction_id = ANY(CAST(:a AS uuid[])) THEN 1 ELSE 0 "
        "END) AS na, sum(CASE WHEN extraction_id = ANY(CAST(:b AS uuid[])) THEN 1 ELSE 0 END) AS nb FROM "
        "pol_place_observation WHERE start_utc < :y AND end_utc >= :x AND (extraction_id = ANY(CAST(:a AS uuid[])) OR "
        "extraction_id = ANY(CAST(:b AS uuid[]))) GROUP BY 1"), {"a": list(ea), "b": list(eb), "x": start, "y": end})
    return int(sum((r.na or 0) * (r.nb or 0) for r in rows))


def episodes(items, gap_s):
    """Consecutive compatible items (and consecutive separated items) less than ``gap_s`` apart merge."""
    out = []
    for it in sorted(items, key=lambda x: x["at_utc"]):
        if it["verdict"] == "undetermined":
            continue
        kind = "together" if it["verdict"] == "compatible" else "apart"
        last = out[-1] if out else None
        if last and last["kind"] == kind and (it["at_utc"] - last["end"]).total_seconds() < gap_s:
            last["end"] = max(last["end"], it["at_utc"])
            last["items"] += 1
            last["tight"] = last["tight"] and it["tight"] if kind == "together" else False
        else:
            out.append({"kind": kind, "start": it["at_utc"], "end": it["at_utc"], "items": 1,
                        "tight": bool(it["tight"]) if kind == "together" else False})
    for e in out:
        e["breadth"] = ("tight" if e["tight"] else "broad") if e["kind"] == "together" else None
    return out


def create_run(conn, case_id, subj_a, subj_b, ea, eb, start, end, params, requested_by) -> uuid.UUID:
    rid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_colocation_run (id, case_id, subjects, window_start, window_end, params, status, requested_by) "
        "VALUES (:i, :c, CAST(:s AS jsonb), :a, :b, CAST(:p AS jsonb), 'queued', :r)"),
        {"i": rid, "c": case_id, "s": json.dumps([dict(subj_a, extraction_ids=list(ea)),
                                                   dict(subj_b, extraction_ids=list(eb))]),
         "a": start, "b": end, "p": json.dumps(params), "r": requested_by})
    return rid


def execute_run(conn, run_id) -> dict:
    run = conn.execute(text("SELECT * FROM pol_colocation_run WHERE id = :i"), {"i": run_id}).mappings().one()
    p = dict(DEFAULT_PARAMS, **run["params"])
    conn.execute(text("UPDATE pol_colocation_run SET status = 'running' WHERE id = :i"), {"i": run_id})
    sa, sb = run["subjects"]
    ea, eb = [str(x) for x in sa["extraction_ids"]], [str(x) for x in sb["extraction_ids"]]
    A = _observations(conn, ea, run["window_start"], run["window_end"], p["include_synced"])
    B = _observations(conn, eb, run["window_start"], run["window_end"], p["include_synced"])
    pairs = sweep_pairs(A, B, p)
    pairs += _bssid_pairs(conn, run["case_id"], set(ea), set(eb), run["window_start"], run["window_end"], p)
    pairs += _cell_pairs(conn, ea, eb, run["window_start"], run["window_end"], p)
    items = []
    for n, (a, b, v) in enumerate(sorted(pairs, key=lambda x: (min(x[0]["start"], x[1]["start"]),
                                                               str(x[0].get("id") or x[0].get("ref")),
                                                               str(x[1].get("id") or x[1].get("ref"))))):
        items.append({"run_id": run_id, "ordinal": n, "a": a.get("id"), "b": b.get("id"), "ar": a.get("ref"),
                      "br": b.get("ref"), "at_utc": max(a["start"], b["start"]), "verdict": v["verdict"],
                      "d": v["distance_m"], "r": v["radii_sum_m"], "dt": v["dt_s"], "basis": v["basis"],
                      "tight": v["tight"], "assumed": v["assumed"], "flags": v["flags"]})
    for i in range(0, len(items), 5000):
        conn.execute(text(
            "INSERT INTO pol_colocation_item (run_id, ordinal, a_observation_id, b_observation_id, a_ref, b_ref, at_utc, "
            "verdict, distance_m, radii_sum_m, dt_s, basis, tight, assumed, flags) VALUES (:run_id, :ordinal, :a, :b, "
            ":ar, :br, :at_utc, :verdict, :d, :r, :dt, :basis, :tight, :assumed, :flags)"), items[i:i + 5000])
    counts = {"pairs": len(items), "observations_a": len(A), "observations_b": len(B)}
    for it in items:
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
        counts["basis:" + it["basis"]] = counts.get("basis:" + it["basis"], 0) + 1
    eps = episodes(items, p["episode_gap_s"])
    conn.execute(text("UPDATE pol_colocation_run SET status = 'done', finished_at = now(), counts = CAST(:c AS jsonb), "
                      "episodes = CAST(:e AS jsonb) WHERE id = :i"),
                 {"i": run_id, "c": json.dumps(counts), "e": json.dumps(eps, default=str)})
    return counts


def run_in_background(engine_factory, run_id):
    def work():
        engine = engine_factory()
        try:
            with engine.begin() as conn:
                execute_run(conn, run_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("together run %s failed", run_id)
            with engine.begin() as conn:
                conn.execute(text("UPDATE pol_colocation_run SET status = 'failed', error = :x, finished_at = now() "
                                  "WHERE id = :i"), {"i": run_id, "x": str(exc)[:2000]})
    t = threading.Thread(target=work, name="pol-together-%s" % run_id, daemon=True)
    t.start()
    return t


def read_run(conn, run_id, case_id, cursor=0, page=PAGE):
    run = conn.execute(text("SELECT * FROM pol_colocation_run WHERE id = :i AND case_id = :c"),
                       {"i": run_id, "c": case_id}).mappings().one_or_none()
    if run is None:
        return None
    total = conn.execute(text("SELECT count(*) FROM pol_colocation_item WHERE run_id = :i"), {"i": run_id}).scalar()
    items = [dict(r._mapping) for r in conn.execute(text(
        "SELECT * FROM pol_colocation_item WHERE run_id = :i AND ordinal >= :o ORDER BY ordinal LIMIT :l"),
        {"i": run_id, "o": cursor, "l": page})]
    nxt = cursor + len(items) if cursor + len(items) < total else None
    return dict(run, total=total, returned=len(items), next_cursor=nxt, page_size=page, items=items)
