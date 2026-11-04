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
anchor's or 150 m); the same full cell key within 15 minutes is ``compatible``, broad (basis ``shared_cell``; a key
whose MCC came from the SIM is flagged ``mcc_inferred``); one phone's Bluetooth peer record naming the other phone's own
Bluetooth address or name is ``compatible`` at radius 30 m (basis ``bluetooth``; ``name_match`` when by name, never
tight; ``nearby_not_connected`` when the record is a scan detection). The SSID is never used. Nothing is capped; a run whose estimated pairs exceed ``BACKGROUND_PAIRS`` runs in the background and
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
                  "include_synced": False, "bluetooth_radius_m": 30.0}
# Bumped when the pair rules change what a run returns; echoed in every run's counts.
# 2: Bluetooth basis, MCC inferred from the SIM on shared cells (cb-coloc-rest).
# 3: a phone's factory-default Bluetooth name is not compared (counted as not_compared:default_device_name).
ANALYSIS_VERSION = 3
COUNTED_FLAGS = ("mcc_inferred", "name_match", "nearby_not_connected")  # counted per run so the screen can say them
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


def _tower_obs(conn, extraction_ids, start, end):
    """Every resolved tower sighting in [start, end): ``[(key, instant, record uid, flags)]``. A tower with no MCC takes
    the SIM's (flag ``mcc_inferred``, places.resolve_tower_key); one still incomplete is not compared."""
    from services.pattern_of_life.places import tower_rows
    out = []
    for e in extraction_ids:
        for uid, k, flags, reason, ev in tower_rows(conn, e):
            if reason is not None or ev is None or not (start <= ev.instant_utc < end):
                continue
            out.append(((k["radio"], k["mcc"], k["mnc"], k["lac"], k["cid"]), ev.instant_utc, uid, flags))
    return out


def cell_matches(A, B, window_s):
    """Pairs of tower sightings with the same full key within ``window_s``: a keyed join, then a sorted range per key
    (O(n_a log n_b + pairs); it replaced a nested loop over both phones, cb-coloc-rest E). ``A``, ``B``:
    ``[(key, instant, uid, flags)]``; returns ``[(a, b)]`` in A's order, then B's time order."""
    import bisect
    w = timedelta(seconds=window_s)
    by_key = {}
    for y in B:
        by_key.setdefault(y[0], []).append(y)
    for ys in by_key.values():
        ys.sort(key=lambda y: (y[1], str(y[2])))
    times = {k: [y[1] for y in ys] for k, ys in by_key.items()}
    out = []
    for x in A:
        ys = by_key.get(x[0])
        if not ys:
            continue
        ts = times[x[0]]
        for y in ys[bisect.bisect_left(ts, x[1] - w):bisect.bisect_right(ts, x[1] + w)]:
            out.append((x, y))
    return out


def _cell_pairs(conn, ea, eb, start, end, p):
    out = []
    for (kx, tx, ux, fx), (ky, ty, uy, fy) in cell_matches(_tower_obs(conn, ea, start, end),
                                                        _tower_obs(conn, eb, start, end), p["cell_window_s"]):
        flags = ["broad"] + (["mcc_inferred"] if "mcc_inferred" in fx or "mcc_inferred" in fy else [])
        out.append(({"ref": "rec:%s" % ux, "start": tx}, {"ref": "rec:%s" % uy, "start": ty},
                    {"verdict": "compatible", "distance_m": None, "radii_sum_m": None,
                     "dt_s": abs((tx - ty).total_seconds()), "assumed": False, "tight": False,
                     "flags": flags, "basis": "shared_cell"}))
    return out


def bluetooth_peers(conn, extraction_id, start, end):
    """The phone's Bluetooth peer records with a time in [start, end): ``[(record uid, instant, (subkind, value),
    nature)]``. A peer's written name that is an address is compared as an address, otherwise as a name."""
    from services.phone import identifiers
    from services.phone_analysis import fields as FV
    recs = {uid: v for uid, v in FV.field_values(conn, extraction_id, ("DeviceConnectivity",),
                                                 ("DeviceName", "ConnectivityMethod", "ConnectivityNature")).items()
            if "Bluetooth" in v["values"].get("ConnectivityMethod", ()) and v["values"].get("DeviceName")}
    if not recs:
        return []
    times = {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT DISTINCT ON (record_uid) record_uid, instant_utc FROM pol_activity_event WHERE extraction_id = :e AND "
        "record_type = 'DeviceConnectivity' AND record_uid = ANY(CAST(:u AS uuid[])) ORDER BY record_uid, "
        "instant_utc"), {"e": str(extraction_id), "u": list(recs)})}
    out = []
    for uid, v in recs.items():
        t = times.get(uid)
        key = identifiers.bluetooth_peer(v["values"]["DeviceName"][0])
        if t is None or key is None or not (start <= t < end):
            continue
        out.append((uid, t, key, (v["values"].get("ConnectivityNature") or [None])[0]))
    return sorted(out, key=lambda x: (x[1], x[0]))


def _bt_item(peer, p):
    _uid, _t, (sub, _v), nature = peer
    by_name = sub == "bluetooth_name"
    flags = (["name_match"] if by_name else []) + (["nearby_not_connected"] if nature == "Detected" else [])
    flags += ["nature:%s" % nature.lower()] if nature else []
    r = p["bluetooth_radius_m"]
    return {"verdict": "compatible", "distance_m": None, "radii_sum_m": r, "dt_s": 0.0, "assumed": False,
            # a name is user-settable and not unique, so a match by name alone is never tight
            "tight": (not by_name) and r <= p["tight_radius_m"], "flags": flags, "basis": "bluetooth"}


def _bluetooth_pairs(conn, ea, eb, start, end, p, not_compared=None):
    """One phone's Bluetooth peer record whose name or address is the other phone's own Bluetooth identity
    (identities.own_bluetooth): ``compatible`` at that time, radius 30 m (04 8.4). Both directions are read.
    A phone's own name that is its factory default (identifiers.default_device_name) is not compared; each peer
    record that would have matched it is counted in ``not_compared["default_device_name"]``."""
    from services.phone.identifiers import default_device_name
    from services.phone.identities import device_models, own_bluetooth
    own = own_bluetooth(conn, list(ea) + list(eb))
    models = device_models(conn, [e for e in list(ea) + list(eb) if own.get(str(e))])
    out = []
    for side_from, side_to, a_is_peer in ((ea, eb, True), (eb, ea, False)):
        targets, defaults = {}, set()
        for y in side_to:
            for k, cite in own.get(str(y), {}).items():
                if k[0] == "bluetooth_name" and default_device_name(k[1], models.get(str(y), ())):
                    defaults.add(k)
                    continue
                targets.setdefault(k, []).append(cite)
        if not targets and not defaults:
            continue
        for x in side_from:
            for peer in bluetooth_peers(conn, x, start, end):
                if peer[2] in defaults and peer[2] not in targets and not_compared is not None:
                    not_compared["default_device_name"] = not_compared.get("default_device_name", 0) + 1
                for cite in targets.get(peer[2], ()):
                    rec = {"ref": "rec:%s" % peer[0], "start": peer[1]}
                    ident = {"ref": "ident:%s" % cite["sighting_uid"], "start": peer[1]}
                    a, b = (rec, ident) if a_is_peer else (ident, rec)
                    out.append((a, b, _bt_item(peer, p)))
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


def compute(conn, case_id, ea, eb, start, end, params, run_id=None) -> tuple:
    """Every compared pair of two subjects' phones in [start, end) by the pair rule, without writing anything:
    ``(items, counts, episodes)``. ``execute_run`` stores exactly these; the agent reads them directly."""
    p = dict(DEFAULT_PARAMS, **(params or {}))
    ea, eb = [str(x) for x in ea], [str(x) for x in eb]
    A = _observations(conn, ea, start, end, p["include_synced"])
    B = _observations(conn, eb, start, end, p["include_synced"])
    pairs = sweep_pairs(A, B, p)
    pairs += _bssid_pairs(conn, case_id, set(ea), set(eb), start, end, p)
    pairs += _cell_pairs(conn, ea, eb, start, end, p)
    not_compared = {}
    pairs += _bluetooth_pairs(conn, ea, eb, start, end, p, not_compared)
    items = []
    for n, (a, b, v) in enumerate(sorted(pairs, key=lambda x: (min(x[0]["start"], x[1]["start"]),
                                                               str(x[0].get("id") or x[0].get("ref")),
                                                               str(x[1].get("id") or x[1].get("ref"))))):
        items.append({"run_id": run_id, "ordinal": n, "a": a.get("id"), "b": b.get("id"), "ar": a.get("ref"),
                      "br": b.get("ref"), "at_utc": max(a["start"], b["start"]), "verdict": v["verdict"],
                      "d": v["distance_m"], "r": v["radii_sum_m"], "dt": v["dt_s"], "basis": v["basis"],
                      "tight": v["tight"], "assumed": v["assumed"], "flags": v["flags"]})
    counts = {"pairs": len(items), "observations_a": len(A), "observations_b": len(B),
              "analysis_version": ANALYSIS_VERSION}
    for k, n in not_compared.items():
        counts["not_compared:" + k] = n
    for it in items:
        counts[it["verdict"]] = counts.get(it["verdict"], 0) + 1
        counts["basis:" + it["basis"]] = counts.get("basis:" + it["basis"], 0) + 1
        for f in it["flags"]:
            if f in COUNTED_FLAGS:
                counts["flag:" + f] = counts.get("flag:" + f, 0) + 1
    return items, counts, episodes(items, p["episode_gap_s"])


def execute_run(conn, run_id) -> dict:
    run = conn.execute(text("SELECT * FROM pol_colocation_run WHERE id = :i"), {"i": run_id}).mappings().one()
    conn.execute(text("UPDATE pol_colocation_run SET status = 'running' WHERE id = :i"), {"i": run_id})
    sa, sb = run["subjects"]
    items, counts, eps = compute(conn, run["case_id"], sa["extraction_ids"], sb["extraction_ids"],
                                 run["window_start"], run["window_end"], run["params"], run_id=run_id)
    for i in range(0, len(items), 5000):
        conn.execute(text(
            "INSERT INTO pol_colocation_item (run_id, ordinal, a_observation_id, b_observation_id, a_ref, b_ref, at_utc, "
            "verdict, distance_m, radii_sum_m, dt_s, basis, tight, assumed, flags) VALUES (:run_id, :ordinal, :a, :b, "
            ":ar, :br, :at_utc, :verdict, :d, :r, :dt, :basis, :tight, :assumed, :flags)"), items[i:i + 5000])
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
