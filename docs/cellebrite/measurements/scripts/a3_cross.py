"""Stage A3 server measurement batch, pass 2: cross-phone measures within each case (05 X1-X11, M-2a, M-5a/b/c,
M-6b, M-8b, M-12a/b/c; 04 M10 without its Bluetooth part).

usage: python3 -I a3_cross.py <corpus.json> <facts_dir> <out.json>

Reads the private <label>.facts.pkl files written by a3_extract.py (salted keys, instants, positions) and writes
counts only. Positions are used for distances inside this process and never written. Source-app labels pass the
guard (04 section 13) or become `<other>`.
"""
import bisect
import collections
import itertools
import json
import math
import os
import pickle
import re
import statistics
import sys

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")
BIN = 900
V_MAX = 40.0           # m/s movement allowance (04 section 8.4)
ASSUMED_RADIUS = 1000.0  # metres, stated assumption for points without accuracy; such pairs are marked assumed


def haversine(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def guard_counter(cnt):
    out = collections.Counter()
    for k, n in cnt.items():
        out[k if (k and GUARD_RE.match(k) and n >= 3) else "<other>"] += n
    return dict(sorted(out.items()))


class Facts:
    def __init__(self, d):
        self.dir = d
        self.cache = collections.OrderedDict()

    def get(self, label):
        if label not in self.cache:
            with open(os.path.join(self.dir, label + ".facts.pkl"), "rb") as fh:
                self.cache[label] = pickle.load(fh)
            while len(self.cache) > 3:
                self.cache.popitem(last=False)
        self.cache.move_to_end(label)
        return self.cache[label]


def presence(f):
    """Placed observations (Synced excluded): sorted (t, lat, lon, radius or None)."""
    return sorted(((t, lat, lon, (2 * a) if a is not None else None) for t, lat, lon, a, aff in f["loc"] if aff != "Synced"), key=lambda p: p[0])


def verdict(p, q):
    d = haversine(p[1], p[2], q[1], q[2])
    assumed = p[3] is None or q[3] is None
    r = (p[3] if p[3] is not None else ASSUMED_RADIUS) + (q[3] if q[3] is not None else ASSUMED_RADIUS)
    if d <= r:
        return "together", assumed, d, r
    if d - r > V_MAX * abs(p[0] - q[0]):
        return "apart", assumed, d, r
    return "indeterminate", assumed, d, r


def band(x, edges, names):
    for e, n in zip(edges, names):
        if x <= e:
            return n
    return names[-1]


def colocation(fa, fb):
    pa, pb = presence(fa), presence(fb)
    res = {"placed_observations": [len(pa), len(pb)]}
    # 04 M10: observation pairs within 5 minutes, by radius-sum band and distance band
    tb = [p[0] for p in pb]
    rad = collections.Counter()
    dist = collections.Counter()
    for p in pa:
        i = bisect.bisect_left(tb, p[0] - 300)
        while i < len(pb) and pb[i][0] <= p[0] + 300:
            q = pb[i]
            if p[3] is None or q[3] is None:
                rad["unknown"] += 1
            else:
                rad[band(p[3] + q[3], (150, 1000), ("<=150 m", "<=1 km", ">1 km"))] += 1
            dist[band(haversine(p[1], p[2], q[1], q[2]), (50, 150, 1000, 10000), ("<=50 m", "<=150 m", "<=1 km", "<=10 km", ">10 km"))] += 1
            i += 1
    res["m10_pairs_within_5min_by_radius_sum"] = dict(rad)
    res["m10_pairs_within_5min_by_distance"] = dict(dist)
    # 05 M-5a: 15-minute bins where both are placed, with the verdict per bin
    ba, bb = collections.defaultdict(list), collections.defaultdict(list)
    for p in pa:
        ba[int(p[0] // BIN)].append(p)
    for q in pb:
        bb[int(q[0] // BIN)].append(q)
    both = set(ba) & set(bb)
    v = collections.Counter()
    for b in both:
        vs = [verdict(p, q) for p in ba[b] for q in bb[b]]
        if any(x[0] == "together" for x in vs):
            k = "together" + (" (assumed radius)" if all(x[1] for x in vs if x[0] == "together") else "")
        elif all(x[0] == "apart" for x in vs):
            k = "apart" + (" (assumed radius)" if any(x[1] for x in vs) else "")
        else:
            k = "indeterminate"
        v[k] += 1
    # WiFi: same BSSID within the bin counts as together
    wa = {(h, int(t // BIN)) for h, t in fa["bssid_obs"]}
    wb = {(h, int(t // BIN)) for h, t in fb["bssid_obs"]}
    wifi_bins = {b for h, b in wa & wb}
    res["m5a_bins_both_placed"] = len(both)
    res["m5a_verdicts"] = dict(v)
    res["m5a_wifi_together_bins"] = len(wifi_bins)
    res["m5a_wifi_together_bins_not_placed_by_location"] = len(wifi_bins - both)
    # 04 M10: shared BSSID within 5 minutes; shared full cell key within 15 minutes
    res["m10_shared_bssid_within_5min"] = within(fa["bssid_obs"], fb["bssid_obs"], 300)
    res["m10_shared_cell_within_15min"] = within(fa["cell_obs"], fb["cell_obs"], 900)
    res["m10_bluetooth"] = "skipped: needs the identity spec output naming each phone's own device (04 M10)"
    return res


def within(obs_a, obs_b, tol):
    """Observations on phone A with the same key on phone B within tol seconds; distinct keys involved."""
    by = collections.defaultdict(list)
    for h, t in obs_b:
        by[h].append(t)
    for v in by.values():
        v.sort()
    n = 0
    keys = set()
    for h, t in obs_a:
        v = by.get(h)
        if not v:
            continue
        i = bisect.bisect_left(v, t - tol)
        if i < len(v) and v[i] <= t + tol:
            n += 1
            keys.add(h)
    return {"observations": n, "distinct_keys": len(keys)}


def messages(fa, fb):
    """X3-X7: equal normalised bodies (length >= 10)."""
    ca = collections.Counter(m[0] for m in fa["msgs"])
    cb = collections.Counter(m[0] for m in fb["msgs"])
    common = set(ca) & set(cb)
    distinct = {h for h in common if ca[h] <= 3 and cb[h] <= 3}
    res = {"x3_distinct_common_bodies": len(distinct), "x3_frequent_common_bodies": len(common - distinct),
           "x3_short_bodies": "not cross-matched (under 10 characters); per-phone counts in s05_x3_short_bodies"}
    ia = collections.defaultdict(list)
    for m in fa["msgs"]:
        if m[0] in distinct:
            ia[m[0]].append(m)
    pairs = []
    for m in fb["msgs"]:
        if m[0] in distinct:
            best = min(ia[m[0]], key=lambda x: abs(x[1] - m[1]))
            if abs(best[1] - m[1]) <= 300:
                pairs.append((best, m))
    res["x4_pairs_within_300s"] = len(pairs)
    comp = sum(1 for a, b in pairs if {a[2], b[2]} == {"outgoing", "incoming"})
    res["x5_direction_complementary"] = comp
    res["x6_deleted_state_differs"] = sum(1 for a, b in pairs if a[3] != b[3])
    diffs = [abs(a[1] - b[1]) for a, b in pairs]
    if diffs:
        med = statistics.median(diffs)
        res["x7_seconds_median_mad_zero"] = [round(med, 3), round(statistics.median(abs(d - med) for d in diffs), 3),
                                             sum(1 for d in diffs if d == 0)]
        res["x7_by_message_type"] = dict(collections.Counter(a[4] if a[4] == b[4] else "mixed" for a, b in pairs))
    return res


def strong_kinds():
    return {"owner_e164": "strong", "sim": "strong", "header_ICCID": "strong", "header_IMSI": "strong",
            "header_MSISDN": "strong", "account_username": "medium", "saved_login_account": "medium",
            "bssid": "weak", "bluetooth_name": "weak", "ssid": "weak", "cookie_domain": "weak",
            "remote_session_user_agent": "weak"}


def marker_sets(f):
    out = {"owner_e164": {k for k in f["owner_keys_e164"]}} if "owner_keys_e164" in f else {}
    out["sim"] = set(f["sim"])
    for name in ("ICCID", "IMSI", "MSISDN"):
        out["header_" + name] = set(f["ident"].get(name, ()))
    for k, v in f["keys"].items():
        out[k] = set(v)
    return out


def pair(la, lb, fa, fb):
    res = {"pair": [la, lb]}
    oa, ob = fa["owner_keys"], fb["owner_keys"]
    res["x1_owner_of_first_as_party_on_second"] = [len(oa & fb["party_keys"]), len(oa)]
    res["x1_owner_of_second_as_party_on_first"] = [len(ob & fa["party_keys"]), len(ob)]
    res["x2_party_identifiers_in_common"] = len(fa["party_keys"] & fb["party_keys"])
    res.update(messages(fa, fb))
    by_src = collections.Counter()
    sb = collections.defaultdict(set)
    for src, h in fb["msg_ident"]:
        sb[src].add(h)
    for src, h in fa["msg_ident"]:
        if h in sb.get(src, ()):
            by_src[src] += 1
    res["x8_message_identifier_equal_by_source"] = guard_counter(by_src)
    res["x9_chat_id_equal"] = len(set(fa["chat_ids"]) & set(fb["chat_ids"]))
    shared = set(fa["md5_all"]) & set(fb["md5_all"])
    res["x10_shared_md5_all_files"] = len(shared)
    res["x10_by_category"] = guard_counter(collections.Counter(fa["md5_all"][h] for h in shared))
    res["x11_shared_md5_attachment_linked"] = len(fa["md5_attach"] & fb["md5_attach"])
    pop_a = fa["md5_attach"] | fa["md5_camera"]
    pop_b = fb["md5_attach"] | fb["md5_camera"]
    res["m8b_shared_md5_attachment_or_camera"] = len(pop_a & pop_b)
    # M-5b markers
    ma, mb = marker_sets(fa), marker_sets(fb)
    sk = strong_kinds()
    res["m5b_shared_markers"] = {k: [len(ma.get(k, set()) & mb.get(k, set())), sk.get(k, "weak")] for k in sorted(set(ma) | set(mb))}
    res["m5b_any_strong"] = any(len(ma.get(k, set()) & mb.get(k, set())) for k, s in sk.items() if s == "strong")
    res.update(colocation(fa, fb))
    da, db = fa["interaction_days"], fb["interaction_days"]
    res["m5c_overlapping_interaction_days"] = len(da & db)
    ba, bb = fa.get("interaction_bins", set()), fb.get("interaction_bins", set())
    res["m5c_bins_both_interacting"] = len(ba & bb)
    return res


def same_device(fa, fb):
    """M-12a/b/c between two extractions (values never written)."""
    res = {"m12a_identifiers": {}}
    for name in sorted(set(fa["ident"]) | set(fb["ident"])):
        a, b = fa["ident"].get(name, set()), fb["ident"].get(name, set())
        res["m12a_identifiers"][name] = ("absent in both" if not a and not b else "absent in one" if not a or not b
                                         else "equal" if a == b else "overlapping" if a & b else "different")
    for name in ("IMEI", "ICCID", "IMSI", "MSISDN", "DeviceInfoAndroidID", "Bluetooth MAC Address", "Mac Address", "Factory number"):
        res["m12a_identifiers"].setdefault(name, "absent in both")
    m = {}
    for t in sorted(set(fa["markers"]) | set(fb["markers"])):
        a, b = fa["markers"].get(t, set()), fb["markers"].get(t, set())
        inter = len(a & b)
        union = len(a | b)
        if union:
            m[t] = {"first": len(a), "second": len(b), "equal": inter, "jaccard": round(inter / union, 4)}
    res["m12b_content_markers_by_type"] = m
    tot_i = sum(x["equal"] for x in m.values())
    tot_u = sum(x["first"] + x["second"] - x["equal"] for x in m.values())
    res["m12b_overall_jaccard"] = round(tot_i / tot_u, 4) if tot_u else None
    ia, ib = fa["model_ids"], fb["model_ids"]
    res["m12c_record_ids"] = {"first": len(ia), "second": len(ib), "equal": len(ia & ib)}
    res["sim_identifiers_shared"] = len(set(fa["sim"]) & set(fb["sim"]))
    return res


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    facts = Facts(argv[1])
    cases = collections.defaultdict(list)
    for label, spec in sorted(corpus.items()):
        if os.path.exists(os.path.join(argv[1], label + ".facts.pkl")):
            cases[spec["case"]].append(label)
    out = {"what": "Stage A3 cross-phone measures (counts only; salted joins; positions never written)",
           "assumed_radius_m": ASSUMED_RADIUS, "bin_seconds": BIN, "cases": {}}
    for case, labels in sorted(cases.items()):
        c = {"phones": labels, "pairs": []}
        shared = collections.defaultdict(collections.Counter)
        for la in labels:
            for k, v in marker_sets(facts.get(la)).items():
                for h in v:
                    shared[k][h] += 1
        sk = strong_kinds()
        c["m6b_keys_on_two_or_more_phones"] = {k: [sum(1 for n in v.values() if n >= 2), sk.get(k, "weak")] for k, v in sorted(shared.items())}
        c["m8b_groups_spanning_phones"] = 0
        pop = collections.Counter()
        for la in labels:
            f = facts.get(la)
            for h in f["md5_attach"] | f["md5_camera"]:
                pop[h] += 1
        c["m8b_groups_spanning_phones"] = sum(1 for n in pop.values() if n >= 2)
        for la, lb in itertools.combinations(labels, 2):
            fa, fb = facts.get(la), facts.get(lb)
            c["pairs"].append(pair(la, lb, fa, fb))
            print(json.dumps({"case": case, "pair": [la, lb]}), flush=True)
        out["cases"][case] = c
    if "P03" in corpus and "P10" in corpus and all(os.path.exists(os.path.join(argv[1], x + ".facts.pkl")) for x in ("P03", "P10")):
        out["m12_P03_P10"] = same_device(facts.get("P03"), facts.get("P10"))
    with open(argv[2], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
