"""Approach 5: who used which phone (docs/cellebrite/05 section 8; units 05-S8 and cb-gated-aware).

Built, every step of 8.3:

- 8.3 step 1, shared identity markers between two phones, by kind and strength;
- 8.3 step 3, complementary use: per 15-minute bin, whether each phone's owner did something (04 class
  ``interaction``, actor ``owner``), over the days both phones hold such data; ``both``, ``only_X``, ``only_Y``,
  ``neither``, the phi coefficient and the switching rate (only_X to only_Y or back within one hour, per day);
- 8.3 step 5, signs of more than one user on one phone, listed and never scored;
- 8.3 step 2, co-location: per 15-minute bin where both phones are placed (04 presence observations, Synced points
  left out unless ``include_synced``), together, apart or indeterminate from 04's ``colocation.verdict``, the one
  implementation (C10); a bin where both phones report the same WiFi BSSID is together. ``C = together / (together +
  apart)`` with n, for every pair with at least one co-placed bin;
- 8.3 step 4, use while apart: the apart bins in which one phone's owner did something, with both phones' records.

Steps 2 and 4 are graded on the app's one scale (``grading``): substantiation from the decided bins (20 some, 200
well; 200 is the plan's figure in 8.6), fit from whether the radii were stated or assumed. Both counts are rules of
thumb with no measurement behind them; a pair with one co-placed bin is listed, weak or faint, never dropped. The
coverage notes give the true counts (phones placed, co-placed bins per pair).

Values are compared inside the backend; a result shows counts by kind and the records on each side, never the
value itself. The approach reports the numbers, not who used the phones (05 3.5).

Decisions (05 section 19, 19.S8-a to 19.S8-c):

- 19.S8-a "Bins where both phones have data" are the bins of days on which both phones hold at least one owner
  interaction event: 04's availability bands come from observing streams only, and the live reference phones hold
  none, so a band test would drop every bin. The day rule is the one M-5c measured. Reverse if 04's bands cover the
  phones of a case.
- 19.S8-b Every pair that shares at least one such day is listed for complementary use, graded on the one scale
  (Neil 2026-11-04: no cutoff hides a candidate): substantiation from the shared days (``USE_SOME`` 3, ``USE_WELL``
  14, the old gate's figure; rules of thumb), fit from the mapping level of the interaction records on both phones
  (``grading.fit_of_levels``). Reverse if a measured error rate for few shared days exists.
- 19.S8-c Marker strength: same owner number, ICCID or IMSI strong; same account username on one service or same
  saved-login account on one service moderate (the one scale's word); same WiFi BSSID weak (families share networks).
- 19.S8-f An observation is in the bin of its start time (the M-5a rule). Within a bin every observation of X is
  compared with every observation of Y, with the verdict's time window set to the bin; the bin is together when some
  pair is compatible and none separated, apart when some pair is separated and none compatible, and indeterminate
  otherwise (also when they conflict, counted as such). Reverse if 04 defines a per-bin verdict.
- 19.S8-g Fit for steps 2 and 4: 2 when no decided bin rests on an assumed radius, 1 when some do, 0 when all do
  (or no bin is decided). Reverse if a measured error rate for assumed radii exists.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict

from sqlalchemy import text

from services.phone_analysis import fields as FV
from services.phone_analysis import grading as G

CODE = "device_users"
VERSION = "5.4-graded-use"
VERSION_SOURCES = ("grading",)
PARAMETERS = {
    "bin_minutes": {"default": 15, "choices": [15]},
    "include_synced": {"default": False, "choices": [False, True]},
    "assumed_radius_m": {"default": 1000, "min": 10, "max": 50000},
}
KINDS = ("shared_markers", "complementary_use", "more_than_one_user", "co_location", "use_while_apart")
SUPPORTS = ("marker_strong", "marker_moderate", "marker_weak", "use_counts", "indicator", "bins_compared",
            "used_while_apart", "strength_rule")
UNDERCUTS = ("shared_network_weak", "interaction_mapping", "clock_offset_small", "selective_extraction",
             "synced_attribution", "sim_moved", "app_accounts_counted_once", "sparse_location", "assumed_radius",
             "broad_radius", "few_records", "offset_absent")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
STRENGTH = {"owner_number": "strong", "iccid": "strong", "imsi": "strong", "account": "moderate",
            "saved_login": "moderate", "wifi_bssid": "weak"}
KIND_WORDS = {"owner_number": ("owner phone number", "owner phone numbers"),
              "iccid": ("SIM card number (ICCID)", "SIM card numbers (ICCID)"),
              "imsi": ("SIM subscriber number (IMSI)", "SIM subscriber numbers (IMSI)"),
              "account": ("account username on one service", "account usernames on one service"),
              "saved_login": ("saved-login account on one service", "saved-login accounts on one service"),
              "wifi_bssid": ("WiFi access point (BSSID)", "WiFi access points (BSSID)")}
SIGNALS = [
    {"code": "interaction", "label": "Records of the owner using the phone"},
    {"code": "markers", "label": "Numbers, SIMs, accounts or WiFi networks"},
    {"code": "places", "label": "Place observations"},
]
COLOC_SOME, COLOC_WELL = 20, 200
APART_SOME, APART_WELL = 3, 10
USE_SOME, USE_WELL = 3, 14
USE_FIT_WORDS = {2: "Every use record was read through a reviewed or applied mapping of the app",
                 1: "Some use records were read through generic interpretation, not a mapping of the app",
                 0: "No mapping of the app behind the use records"}
_last = {"counts": {}}
_BSSID = re.compile(r"[^0-9a-f]")


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


def _norm(kind, v):
    v = str(v or "").strip()
    if not v:
        return None
    if kind == "wifi_bssid":
        h = _BSSID.sub("", v.lower())
        return ":".join(h[i:i + 2] for i in range(0, 12, 2)) if len(h) == 12 and h != "0" * 12 else None
    if kind in ("iccid", "imsi"):
        d = re.sub(r"\D", "", v)
        return d or None
    return v.casefold()


def markers(conn, ext) -> dict:
    """``{(kind, digest): [record_uid or None]}`` for one phone; digests only, so values never leave this function."""
    out = defaultdict(list)

    def add(kind, value, uid):
        n = _norm(kind, value)
        if n:
            out[(kind, hashlib.sha256(("%s|%s" % (kind, n)).encode()).hexdigest())].append(uid)
    # 19.S8-e: the phone's numbers as 02 computes its owner: header (tier 1) numbers, else tier 2's top
    cands = conn.execute(text(
        "SELECT identity_key, tier FROM pv_owner_candidate WHERE extraction_id = :e AND candidate_kind = 'number' AND "
        "identity_key LIKE 'phone:+%' ORDER BY tier, occurrences DESC, identity_key"), {"e": ext}).fetchall()
    tier1 = [r[0] for r in cands if r[1] == 1]
    for key in tier1 or [r[0] for r in cands if r[1] == 2][:1]:
        add("owner_number", key, None)
    try:
        from services.phone import identities
        items = identities.header_items(conn, ext)
    except Exception:  # noqa: BLE001 - a skeleton without metadata has no header identifiers
        items = {}
    for name, kind in (("ICCID", "iccid"), ("IMSI", "imsi")):
        v = items.get(name)
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            add(kind, x, None)
    sims = FV.field_values(conn, ext, ("SIMData",), ("Name", "Value"))
    for uid, v in sims.items():
        name = " ".join(v["values"].get("Name", ())).upper()
        for kind in ("iccid", "imsi"):
            if kind.upper() in name:
                for x in v["values"].get("Value", ()):
                    add(kind, x, uid)
    acc = FV.field_values(conn, ext, ("UserAccount",), ("ServiceType", "ServiceIdentifier", "Username"))
    for uid, v in acc.items():
        svc = (v["values"].get("ServiceIdentifier") or v["values"].get("ServiceType") or [""])[0]
        for u in v["values"].get("Username", ()):
            if svc:
                add("account", "%s|%s" % (svc.casefold(), u), uid)
    logins = FV.field_values(conn, ext, ("Password",), ("Service", "Account"))
    for uid, v in logins.items():
        svc = (v["values"].get("Service") or [""])[0]
        for a in v["values"].get("Account", ()):
            if svc:
                add("saved_login", "%s|%s" % (svc.casefold(), a), uid)
    wifi = FV.field_values(conn, ext, ("WirelessNetwork",), ("BSSId",))
    for uid, v in wifi.items():
        for b in v["values"].get("BSSId", ()):
            add("wifi_bssid", b, uid)
    return out


def _interaction_bins(conn, ext, minutes=15):
    """``{day: set(bin index)}`` of owner interaction events."""
    out = defaultdict(set)
    for r in conn.execute(text(
            "SELECT instant_utc FROM pol_activity_event WHERE extraction_id = :e AND activity_class = 'interaction' "
            "AND actor = 'owner' AND instant_utc IS NOT NULL"), {"e": ext}):
        t = r[0]
        out[t.date()].add((t.hour * 60 + t.minute) // minutes)
    return out


def _interaction_levels(conn, ext) -> list:
    """The mapping levels of the phone's owner interaction records (the fit of complementary use, 19.S8-b)."""
    return [r[0] for r in conn.execute(text(
        "SELECT DISTINCT class_level FROM pol_activity_event WHERE extraction_id = :e AND activity_class = "
        "'interaction' AND actor = 'owner' AND instant_utc IS NOT NULL"), {"e": ext})]


def complementary(bx: dict, by: dict, minutes=15) -> dict:
    """8.3 step 3 over the days both phones hold owner interaction (19.S8-a)."""
    days = sorted(set(bx) & set(by))
    per_day = 24 * 60 // minutes
    both = only_x = only_y = neither = 0
    switches = 0
    window = 60 // minutes
    for d in days:
        seq = []
        for b in range(per_day):
            x, y = b in bx[d], b in by[d]
            if x and y:
                both += 1
                seq.append("b")
            elif x:
                only_x += 1
                seq.append("x")
            elif y:
                only_y += 1
                seq.append("y")
            else:
                neither += 1
                seq.append("n")
        # a switch: an only_X bin followed within one hour by an only_Y bin (or the reverse), counted once per pair of
        # consecutive single-phone bins
        last_single, last_at = None, None
        for i, s in enumerate(seq):
            if s in ("x", "y"):
                if last_single and s != last_single and i - last_at <= window:
                    switches += 1
                last_single, last_at = s, i
    n = both + only_x + only_y + neither
    a, b, c, dd = both, only_x, only_y, neither
    den = math.sqrt((a + b) * (c + dd) * (a + c) * (b + dd)) if n else 0.0
    phi = ((a * dd - b * c) / den) if den else None
    return {"days": len(days), "bins": n, "both": both, "only_x": only_x, "only_y": only_y, "neither": neither,
            "phi": round(phi, 4) if phi is not None else None,
            "switches_per_day": round(switches / len(days), 3) if days else None,
            "first_day": days[0].isoformat() if days else None, "last_day": days[-1].isoformat() if days else None}


def coverage(conn, case_id) -> dict:
    phones = {}
    obs = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        n = int(conn.execute(text("SELECT count(*) FROM pol_activity_event WHERE extraction_id = :e AND activity_class "
                                  "= 'interaction' AND actor = 'owner'"), {"e": ext}).scalar() or 0)
        m = len(markers(conn, ext))
        obs[ext] = _observations(conn, ext, False)
        phones[ext] = {"label": label, "signals": {
            "interaction": {"carries_signal": n > 0, "records": n},
            "markers": {"carries_signal": m > 0, "records": m},
            "places": {"carries_signal": bool(obs[ext]), "records": len(obs[ext])}}}
    ids_ = sorted(phones, key=lambda e: (str(phones[e]["label"]), e))
    pairs = []
    for i, x in enumerate(ids_):
        bx = {_bin(o["start"]) for o in obs[x]}
        for y in ids_[i + 1:]:
            pairs.append(((phones[x]["label"], phones[y]["label"]), len(bx & {_bin(o["start"]) for o in obs[y]})))
    totals = {"phones": len(phones), "phones_placed": sum(1 for e in obs if obs[e]),
              "observations": sum(len(v) for v in obs.values()), "pairs": len(pairs),
              "pairs_co_placed": sum(1 for _, n in pairs if n), "co_placed_bins": sum(n for _, n in pairs),
              "most_co_placed_bins": max((n for _, n in pairs), default=0)}
    return {"phones": phones, "signals": SIGNALS, "totals": totals, "notes": notes(totals, pairs)}


def _fmt(v):
    return "{:,}".format(int(v or 0))


def notes(t, pairs) -> list:
    """The thin-data lines (cb-gated-aware D): the true counts behind steps 2 and 4, and the plan's figure as a rule
    of thumb that hides nothing."""
    if not t.get("phones"):
        return []
    best = max(pairs, key=lambda p: p[1], default=None)
    most = (" (most for one pair: %s, %s and %s)" % (_fmt(best[1]), best[0][0], best[0][1])
            if best and best[1] else "")
    return [
        "Place observations on %s of %s phones (%s observations, Synced points left out). Quarter hours in which both "
        "phones of a pair have a place observation: %s over %s of %s pairs%s. A quarter hour in which both report "
        "the same WiFi network also counts in the results." % (_fmt(t["phones_placed"]), _fmt(t["phones"]), _fmt(t["observations"]), _fmt(t["co_placed_bins"]),
                   _fmt(t["pairs_co_placed"]), _fmt(t["pairs"]), most),
        "Rule of thumb (no measurement behind it): the plan asked for 200 such quarter hours for a pair before "
        "comparing places; the most here is %s. Every pair with a shared quarter hour is listed whatever the count, "
        "with its strength: strong, moderate, weak or faint, set by a stated rule, never by a model."
        % _fmt(t["most_co_placed_bins"]),
    ]


# ---- steps 2 and 4: together, apart, and use while apart -----------------------------------------------------------

BIN_S = 900


def _bin(t):
    return int(t.timestamp() // BIN_S)


def _observations(conn, ext, include_synced, start=None, end=None):
    """04 presence observations of one phone, in time order (Synced points left out unless asked for); ``start`` and
    ``end`` (UTC instants) keep those that start in the window (the agent's comparison over a period)."""
    q = ("SELECT id, record_uid::text AS record_uid, lat, lon, radius_m, start_utc AS start, end_utc AS \"end\", "
         "offset_status, attribution_flags FROM pol_place_observation WHERE extraction_id = :e AND kind = 'presence'")
    params = {"e": ext}
    if not include_synced:
        q += " AND NOT ('synced_from_account' = ANY(attribution_flags))"
    if start is not None:
        q += " AND start_utc >= :a"
        params["a"] = start
    if end is not None:
        q += " AND start_utc <= :b"
        params["b"] = end
    return [dict(r._mapping) for r in conn.execute(text(q + " ORDER BY start_utc, id"), params)]


def bin_verdicts(ox, oy, params, wifi=()) -> dict:
    """8.3 step 2 for one pair: ``{bin: {verdict, basis, assumed, tight, distance_m, x, y}}`` over the bins where both
    are placed. ``wifi``: bins where both phones report the same BSSID (together, no position needed)."""
    from services.pattern_of_life.colocation import verdict
    vp = {"window_s": BIN_S, "assumed_radius_m": float(params.get("assumed_radius_m", 1000)),
          "include_synced": bool(params.get("include_synced", False))}
    bx, by = defaultdict(list), defaultdict(list)
    for o in ox:
        bx[_bin(o["start"])].append(o)
    for o in oy:
        by[_bin(o["start"])].append(o)
    out = {}
    for b in sorted(set(bx) & set(by)):
        vs = [verdict(a, c, vp) for a in bx[b] for c in by[b]]
        vs = [v for v in vs if v is not None]
        comp = [v for v in vs if v["verdict"] == "compatible"]
        sep = [v for v in vs if v["verdict"] == "separated"]
        if comp and not sep:
            best = min(comp, key=lambda v: v["distance_m"])
            kind = "together"
        elif sep and not comp:
            best = max(sep, key=lambda v: v["distance_m"] - v["radii_sum_m"])
            kind = "apart"
        else:
            best = min(vs, key=lambda v: v["distance_m"]) if vs else None
            kind = "indeterminate"
        out[b] = {"verdict": kind, "basis": "coordinates", "conflict": bool(comp and sep),
                  "assumed": bool(best and best["assumed"]), "tight": bool(best and best["tight"]),
                  "distance_m": round(best["distance_m"], 1) if best else None,
                  "x": [o["record_uid"] for o in bx[b] if o.get("record_uid")],
                  "y": [o["record_uid"] for o in by[b] if o.get("record_uid")]}
    for b, (ux, uy) in sorted(dict(wifi).items()):
        cur = out.get(b)
        if cur is None or cur["verdict"] == "indeterminate":
            out[b] = {"verdict": "together", "basis": "shared_bssid", "conflict": False, "assumed": False,
                      "tight": True, "distance_m": None, "x": list(ux), "y": list(uy)}
    return out


def _wifi_bins(conn, case_id, exts):
    """``{(x, y): {bin: ([x uids], [y uids])}}``: bins where both phones report the same BSSID."""
    from services.pattern_of_life.places import _bssid_evidence
    seen = defaultdict(lambda: defaultdict(list))
    for e, b, inst, uid in _bssid_evidence(conn, str(case_id)):
        if str(e) in exts and inst is not None:
            seen[(_bin(inst), b)][str(e)].append(str(uid))
    out = defaultdict(dict)
    for (bn, _), per in sorted(seen.items()):
        for x in per:
            for y in per:
                if x != y:
                    ux, uy = out[(x, y)].get(bn, ([], []))
                    out[(x, y)][bn] = (ux + per[x], uy + per[y])
    return out


def _interactions(conn, ext):
    """``{bin: [record_uid]}`` of owner interaction events."""
    out = defaultdict(list)
    for r in conn.execute(text(
            "SELECT instant_utc, record_uid::text FROM pol_activity_event WHERE extraction_id = :e AND activity_class = "
            "'interaction' AND actor = 'owner' AND instant_utc IS NOT NULL ORDER BY instant_utc, record_uid"),
            {"e": ext}):
        out[_bin(r[0])].append(r[1])
    return out


def _bin_iso(b):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(b * BIN_S, tz=timezone.utc).isoformat()


FIT_WORDS = {2: "Every decided quarter hour rests on stated accuracy radii",
             1: "Some decided quarter hours rest on an assumed radius",
             0: "Every decided quarter hour rests on an assumed radius, or none is decided"}


def _fit(bins):
    decided = [b for b in bins if b["verdict"] in ("together", "apart")]
    if not decided:
        return 0
    assumed = sum(1 for b in decided if b["assumed"])
    return 2 if assumed == 0 else 1 if assumed < len(decided) else 0


def _graded(kind, n, noun, some, well, fit, supports, undercuts, measures, recs, start, end):
    subst = G.substantiation(n, some, well)
    lv = G.level(subst, fit)
    supports = supports + [_d("strength_rule", G.reasons(n, noun, some, well, fit, FIT_WORDS))]
    if subst == 0:
        undercuts = undercuts + [_d("few_records", "Only %d %s behind it." % (n, noun[0] if n == 1 else noun[1]))]
    return {"kind": kind, "strength": lv, "measures": dict(measures, strength_basis={"count": n, "substantiation":
                                                                                         subst, "fit": fit}),
            "directions": {"supports": supports, "undercuts": undercuts}, "period_start": start, "period_end": end,
            "records": recs}


def place_results(x, y, phones, verdicts, inter, counts) -> list:
    """Steps 2 and 4 for the pair (x, y) from its bin verdicts."""
    if not verdicts:
        return []
    out = []
    bins = sorted(verdicts)
    vals = [verdicts[b] for b in bins]
    tog = sum(1 for v in vals if v["verdict"] == "together")
    apart = sum(1 for v in vals if v["verdict"] == "apart")
    ind = len(vals) - tog - apart
    fit = _fit(vals)
    counts["pairs_co_placed"] += 1
    counts["co_placed_bins"] += len(vals)
    undercuts = [_d("sparse_location", "Only quarter hours in which both phones have a place observation count: %d "
                    "here." % len(vals)),
                 _d("clock_offset_small", "The two phones' clocks may differ; at quarter-hour bins that is mostly "
                    "negligible.")]
    if any(v["assumed"] for v in vals):
        undercuts.append(_d("assumed_radius", "%d quarter hours rest on an assumed accuracy radius." %
                            sum(1 for v in vals if v["assumed"])))
    broad = sum(1 for v in vals if v["verdict"] == "together" and not v["tight"])
    if broad:
        undercuts.append(_d("broad_radius", "%d of the together quarter hours are within a broad radius only (over "
                            "150 metres), compatible with being together, not shown to be." % broad))
    recs = []
    for v in vals:
        recs += [{"extraction_id": x, "record_uid": u, "field_path": "together:%s" % y, "role": "place_x"}
                 for u in v["x"]]
        recs += [{"extraction_id": y, "record_uid": u, "field_path": "together:%s" % x, "role": "place_y"}
                 for u in v["y"]]
    recs = list({(r["extraction_id"], r["record_uid"], r["field_path"]): r for r in recs}.values())
    m = {"phones": [phones[x], phones[y]], "bins_both_placed": len(vals), "together": tog, "apart": apart,
         "indeterminate": ind, "C": round(tog / (tog + apart), 4) if tog + apart else None,
         "together_tight": tog - broad, "together_by_wifi": sum(1 for v in vals if v["basis"] == "shared_bssid"),
         "bins": [{"start": _bin_iso(b), "verdict": verdicts[b]["verdict"], "basis": verdicts[b]["basis"],
                   "distance_m": verdicts[b]["distance_m"], "assumed": verdicts[b]["assumed"],
                   "conflict": verdicts[b]["conflict"]} for b in bins]}
    if recs:
        out.append(_graded(
            "co_location", tog + apart, ("decided quarter hour", "decided quarter hours"), COLOC_SOME, COLOC_WELL, fit,
            [_d("bins_compared", "%d quarter hours with both placed: %d together, %d apart, %d undecided." %
                (len(vals), tog, apart, ind))], undercuts, m, recs, _bin_iso(bins[0]), _bin_iso(bins[-1])))
    for a, b in ((x, y), (y, x)):
        used = [bn for bn in bins if verdicts[bn]["verdict"] == "apart" and inter[a].get(bn)]
        if not used:
            continue
        counts["use_while_apart_bins"] += len(used)
        side = "x" if a == x else "y"
        other = "y" if side == "x" else "x"
        r2 = []
        for bn in used:
            r2 += [{"extraction_id": a, "record_uid": u, "field_path": "apart:%s" % b, "role": "used"}
                   for u in inter[a][bn]]
            r2 += [{"extraction_id": a, "record_uid": u, "field_path": "apart:%s" % b, "role": "place_used"}
                   for u in verdicts[bn][side]]
            r2 += [{"extraction_id": b, "record_uid": u, "field_path": "apart:%s" % a, "role": "place_other"}
                   for u in verdicts[bn][other]]
        r2 = list({(r["extraction_id"], r["record_uid"], r["field_path"], r["role"]): r for r in r2}.values())
        ub = [verdicts[bn] for bn in used]
        out.append(_graded(
            "use_while_apart", len(used), ("quarter hour", "quarter hours"), APART_SOME, APART_WELL, _fit(ub),
            [_d("used_while_apart", "%s was used in %d quarter hours while %s was elsewhere." %
                (phones[a], len(used), phones[b]))],
            [_d("interaction_mapping", "What counts as use depends on 04's activity mapping.")] +
            ([_d("assumed_radius", "%d of them rest on an assumed accuracy radius." % sum(1 for v in ub if v["assumed"]))]
             if any(v["assumed"] for v in ub) else []),
            {"phones": [phones[x], phones[y]], "used_phone": phones[a], "other_phone": phones[b],
             "bins": [{"start": _bin_iso(bn), "distance_m": verdicts[bn]["distance_m"],
                       "interactions": len(inter[a][bn])} for bn in used]},
            r2, _bin_iso(used[0]), _bin_iso(used[-1])))
    return out


def _indicators(conn, ext) -> dict:
    owners = int(conn.execute(text("SELECT count(DISTINCT identity_key) FROM pv_owner_candidate WHERE extraction_id "
                                   "= :e AND tier = 1 AND identity_key LIKE 'phone:+%'"), {"e": ext}).scalar() or 0)
    users = FV.field_values(conn, ext, ("User",), ("UserType", "Name", "Identifier"))
    acc = FV.field_values(conn, ext, ("UserAccount",), ("ServiceType", "ServiceIdentifier", "Username"))
    per_service = defaultdict(set)
    for v in acc.values():
        svc = (v["values"].get("ServiceIdentifier") or v["values"].get("ServiceType") or [""])[0]
        for u in v["values"].get("Username", ()):
            if svc and u:
                per_service[svc.casefold()].add(u.casefold())
    sims = defaultdict(set)
    for v in FV.field_values(conn, ext, ("SIMData",), ("Name", "Value")).values():
        name = " ".join(v["values"].get("Name", ())).upper()
        for kind in ("ICCID", "IMSI"):
            if kind in name:
                sims[kind].update(re.sub(r"\D", "", x) for x in v["values"].get("Value", ()) if x)
    return {"owner_numbers": owners, "user_records": len(users),
            "services_with_several_usernames": sum(1 for s in per_service.values() if len(s) > 1),
            "sim_iccids": len(sims["ICCID"]), "sim_imsis": len(sims["IMSI"]),
            "user_record_uids": sorted(users)}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    ids_ = sorted(phones, key=lambda e: (str(phones[e]), e))  # pairs read in label order (C1 before C2)
    mk = {e: markers(conn, e) for e in ids_}
    bins = {e: _interaction_bins(conn, e, params["bin_minutes"]) for e in ids_}
    use_levels = {e: _interaction_levels(conn, e) for e in ids_ if bins[e]}
    include_synced = bool(params.get("include_synced", False))
    obs = {e: _observations(conn, e, include_synced) for e in ids_}
    inter = {e: _interactions(conn, e) for e in ids_}
    wifi = _wifi_bins(conn, case_id, set(ids_))
    out = []
    for i, x in enumerate(ids_):
        if ctx is not None:
            ctx.progress(i, len(ids_), phones[x])
            if ctx.cancelled():
                break
        # step 5, per phone
        ind = _indicators(conn, x)
        signs = []
        if ind["owner_numbers"] > 1:
            signs.append("%d owner phone numbers" % ind["owner_numbers"])
        if ind["user_records"] > 1:
            signs.append("%d device user records" % ind["user_records"])
        if ind["services_with_several_usernames"]:
            signs.append("%d services with more than one username" % ind["services_with_several_usernames"])
        if ind["sim_iccids"] > 1 or ind["sim_imsis"] > 1:
            signs.append("more than one SIM recorded")
        if signs:
            counts["phones_with_indicators"] += 1
            uids = ind.pop("user_record_uids")
            recs = [{"extraction_id": x, "record_uid": u, "field_path": None, "role": "user_record"} for u in uids]
            if not recs:
                rec = next(iter(conn.execute(text("SELECT record_uid::text FROM pv_record WHERE extraction_id = :e "
                                                  "ORDER BY ordinal LIMIT 1"), {"e": x})), None)
                if rec is None:
                    continue
                recs = [{"extraction_id": x, "record_uid": rec[0], "field_path": "phone:indicators",
                         "role": "phone"}]
            out.append({
                "kind": "more_than_one_user", "strength": "indicators",
                "measures": dict(ind, phone_label=phones[x], signs=signs),
                "directions": {"supports": [_d("indicator", s) for s in signs],
                               "undercuts": [_d("app_accounts_counted_once", "Only phone numbers count as owner "
                                                "numbers; app accounts are left out."),
                                             _d("sim_moved", "A SIM can move between phones, and one person can "
                                                "hold several numbers.")]},
                "period_start": None, "period_end": None, "records": recs})
        for y in ids_[i + 1:]:
            shared = sorted(set(mk[x]) & set(mk[y]))
            if shared:
                by_kind = defaultdict(int)
                recs = []
                for k in shared:
                    by_kind[k[0]] += 1
                    for e, src in ((x, mk[x]), (y, mk[y])):
                        for uid in src[k]:
                            if uid:
                                recs.append({"extraction_id": e, "record_uid": uid, "field_path": k[0],
                                             "role": "marker_" + k[0]})
                best = min((STRENGTH[k] for k in by_kind), key=["strong", "moderate", "weak"].index)
                # the pair's own anchor always: two pairs can rest on one phone's same marker record (19.S8-d)
                for e in (x, y):
                    rec = next(iter(conn.execute(text("SELECT record_uid::text FROM pv_record WHERE extraction_id "
                                                      "= :e ORDER BY ordinal LIMIT 1"), {"e": e})), None)
                    if rec:
                        recs.append({"extraction_id": e, "record_uid": rec[0], "field_path": "pair:markers:%s"
                                     % (x if e == y else y), "role": "phone"})
                if recs:
                    counts["pairs_with_markers"] += 1
                    out.append({
                        "kind": "shared_markers", "strength": best,
                        "measures": {"phones": [phones[x], phones[y]], "by_kind": dict(by_kind),
                                     "strength_by_kind": {k: STRENGTH[k] for k in by_kind}},
                        "directions": {"supports": [_d("marker_" + STRENGTH[k], "%d %s in common." %
                                                       (n, KIND_WORDS[k][0 if n == 1 else 1]))
                                                    for k, n in sorted(by_kind.items())],
                                       "undercuts": ([_d("shared_network_weak", "People who live or work together "
                                                         "share WiFi networks.")] if "wifi_bssid" in by_kind else [])},
                        "period_start": None, "period_end": None, "records": recs})
            c = complementary(bins[x], bins[y], params["bin_minutes"])
            if c["days"] >= 1:  # every pair with a shared day, graded (19.S8-b)
                counts["pairs_with_use"] += 1
                anchor = []
                for e in (x, y):
                    rec = next(iter(conn.execute(text(
                        "SELECT record_uid::text FROM pol_activity_event WHERE extraction_id = :e AND activity_class = "
                        "'interaction' AND actor = 'owner' ORDER BY instant_utc, record_uid LIMIT 1"), {"e": e})), None)
                    if rec:
                        anchor.append({"extraction_id": e, "record_uid": rec[0], "field_path": "pair:use:%s" %
                                       (y if e == x else x), "role": "first_interaction"})
                fit = G.fit_of_levels(use_levels.get(x, []) + use_levels.get(y, []))
                subst = G.substantiation(c["days"], USE_SOME, USE_WELL)
                undercuts = [_d("interaction_mapping", "What counts as use depends on 04's activity mapping."),
                             _d("clock_offset_small", "The two phones' clocks may differ; at quarter-hour bins that is "
                                "mostly negligible.")]
                if subst == 0:
                    undercuts.append(_d("few_records", "Only %d %s with activity on both." %
                                        (c["days"], "day" if c["days"] == 1 else "days")))
                out.append({
                    "kind": "complementary_use", "strength": G.level(subst, fit),
                    "measures": dict(c, phones=[phones[x], phones[y]],
                                     strength_basis={"count": c["days"], "substantiation": subst, "fit": fit}),
                    "directions": {"supports": [_d("use_counts", "Over %d %s with activity on both: %d quarter hours "
                                                   "with both in use, %d only %s, %d only %s." %
                                                   (c["days"], "day" if c["days"] == 1 else "days", c["both"],
                                                    c["only_x"], phones[x], c["only_y"], phones[y])),
                                                _d("strength_rule", G.reasons(c["days"], ("shared day", "shared days"),
                                                                              USE_SOME, USE_WELL, fit,
                                                                              USE_FIT_WORDS))],
                                   "undercuts": undercuts},
                    "period_start": None, "period_end": None, "records": anchor})
            out.extend(place_results(x, y, phones, bin_verdicts(obs[x], obs[y], params, wifi.get((x, y), {})),
                                     inter, counts))
    for r in out:
        if r["kind"] in ("shared_markers", "complementary_use", "co_location", "use_while_apart"):
            counts["%s_%s" % (r["kind"], r["strength"])] += 1
    if ctx is not None:
        ctx.progress(len(ids_), len(ids_))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]

