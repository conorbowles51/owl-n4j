"""Approach 5: who used which phone, complementary-use part (docs/cellebrite/05 section 8; unit 05-S8).

Built (the gate in 8.6 passed for complementary use, 43 pairs with 14 or more days of overlapping interaction data,
and failed for co-location, 43 co-placed bins at most against 200):

- 8.3 step 1, shared identity markers between two phones, by kind and strength;
- 8.3 step 3, complementary use: per 15-minute bin, whether each phone's owner did something (04 class
  ``interaction``, actor ``owner``), over the days both phones hold such data; ``both``, ``only_X``, ``only_Y``,
  ``neither``, the phi coefficient and the switching rate (only_X to only_Y or back within one hour, per day);
- 8.3 step 5, signs of more than one user on one phone, listed and never scored.

Not built: the co-location statistic (step 2) and use while apart (step 4), which rest on co-placed bins. Together and
apart stay 04's (C10): this module never computes a place verdict.

Values are compared inside the backend; a result shows counts by kind and the records on each side, never the
value itself. The approach reports the numbers, not who used the phones (05 3.5).

Decisions (05 section 19, 19.S8-a to 19.S8-c):

- 19.S8-a "Bins where both phones have data" are the bins of days on which both phones hold at least one owner
  interaction event: 04's availability bands come from observing streams only, and the live reference phones hold
  none, so a band test would drop every bin. The day rule is the one M-5c measured. Reverse if 04's bands cover the
  phones of a case.
- 19.S8-b A pair is listed for complementary use when it shares at least ``min_days`` such days (default 14, the
  gate's own figure).
- 19.S8-c Marker strength: same owner number, ICCID or IMSI strong; same account username on one service or same
  saved-login account on one service medium; same WiFi BSSID weak (families share networks).
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict

from sqlalchemy import text

from services.phone_analysis import fields as FV

CODE = "device_users"
VERSION = "5.1-use"
PARAMETERS = {
    "min_days": {"default": 14, "min": 1, "max": 365},
    "bin_minutes": {"default": 15, "choices": [15]},
}
KINDS = ("shared_markers", "complementary_use", "more_than_one_user")
SUPPORTS = ("marker_strong", "marker_medium", "marker_weak", "use_counts", "indicator")
UNDERCUTS = ("shared_network_weak", "interaction_mapping", "clock_offset_small", "selective_extraction",
             "synced_attribution", "sim_moved", "app_accounts_counted_once")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
STRENGTH = {"owner_number": "strong", "iccid": "strong", "imsi": "strong", "account": "medium",
            "saved_login": "medium", "wifi_bssid": "weak"}
KIND_WORDS = {"owner_number": "owner phone numbers", "iccid": "SIM card numbers (ICCID)",
              "imsi": "SIM subscriber numbers (IMSI)", "account": "account usernames on one service",
              "saved_login": "saved-login accounts on one service", "wifi_bssid": "WiFi access points (BSSID)"}
SIGNALS = [
    {"code": "interaction", "label": "Owner activity"},
    {"code": "markers", "label": "Numbers, SIMs, accounts or WiFi networks"},
]
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
    for ext, label in FV.active_phones(conn, case_id).items():
        n = int(conn.execute(text("SELECT count(*) FROM pol_activity_event WHERE extraction_id = :e AND activity_class "
                                  "= 'interaction' AND actor = 'owner'"), {"e": ext}).scalar() or 0)
        m = len(markers(conn, ext))
        phones[ext] = {"label": label, "signals": {
            "interaction": {"carries_signal": n > 0, "records": n},
            "markers": {"carries_signal": m > 0, "records": m}}}
    return {"phones": phones, "signals": SIGNALS}


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
                best = min((STRENGTH[k] for k in by_kind), key=["strong", "medium", "weak"].index)
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
                                                       (n, KIND_WORDS[k])) for k, n in sorted(by_kind.items())],
                                       "undercuts": ([_d("shared_network_weak", "People who live or work together "
                                                         "share WiFi networks.")] if "wifi_bssid" in by_kind else [])},
                        "period_start": None, "period_end": None, "records": recs})
            c = complementary(bins[x], bins[y], params["bin_minutes"])
            if c["days"] >= params["min_days"]:
                counts["pairs_with_use"] += 1
                anchor = []
                for e in (x, y):
                    rec = next(iter(conn.execute(text(
                        "SELECT record_uid::text FROM pol_activity_event WHERE extraction_id = :e AND activity_class = "
                        "'interaction' AND actor = 'owner' ORDER BY instant_utc, record_uid LIMIT 1"), {"e": e})), None)
                    if rec:
                        anchor.append({"extraction_id": e, "record_uid": rec[0], "field_path": "pair:use:%s" %
                                       (y if e == x else x), "role": "first_interaction"})
                out.append({
                    "kind": "complementary_use", "strength": "measured",
                    "measures": dict(c, phones=[phones[x], phones[y]]),
                    "directions": {"supports": [_d("use_counts", "Over %d days with activity on both: %d quarter hours "
                                                   "with both in use, %d only %s, %d only %s." %
                                                   (c["days"], c["both"], c["only_x"], phones[x], c["only_y"],
                                                    phones[y]))],
                                   "undercuts": [_d("interaction_mapping", "What counts as use depends on 04's "
                                                    "activity mapping."),
                                                 _d("clock_offset_small", "The two phones' clocks may differ; at "
                                                    "quarter-hour bins that is mostly negligible.")]},
                    "period_start": None, "period_end": None, "records": anchor})
    if ctx is not None:
        ctx.progress(len(ids_), len(ids_))
    return out, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]

