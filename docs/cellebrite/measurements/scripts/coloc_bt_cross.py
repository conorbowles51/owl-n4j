"""cb-coloc-rest item A, pass 2: counts only, across the phones of each case."""
import collections, json, os, pickle, sys
from datetime import datetime, timedelta
D = "/mnt/owl-data/cellebrite-corpus/coloc"
corpus = json.load(open("/mnt/owl-data/cellebrite-corpus/corpus.json"))
F = {l: pickle.load(open(os.path.join(D, l + ".bt.pkl"), "rb")) for l in corpus}
def own(f):
    names = set().union(*[v for k, v in f["header"].items() if k.startswith("bt_name:")] or [set()])
    return f["header"].get("bt_mac", set()), names
def ts(t):
    try: return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None
    except ValueError: return None
rows = []
for l, f in sorted(F.items()):
    addr, names = own(f)
    bt = [p for p in f["peers"] if p["method"] == "Bluetooth"]
    nat = collections.Counter(p["nature"] or "none" for p in bt)
    others = [o for o in corpus if o != l and corpus[o]["case"] == corpus[l]["case"]]
    by_a = by_n = by_n_timed = 0; per_other = collections.Counter(); natm = collections.Counter()
    for o in others:
        oa, on = own(F[o])
        for p in bt:
            if p["mac"] and p["mac"] in oa: by_a += 1; per_other[o] += 1; natm[p["nature"]] += 1
            elif p["name"] and p["name"] in on:
                by_n += 1; per_other[o] += 1; natm[p["nature"]] += 1
                by_n_timed += bool(ts(p.get("t")))
        for r in f["recognized"]:
            if r["name"] and r["name"] in on: per_other[o + "(recognized, untimed)"] += 1
    mccs = {m for _, m in f["imsi_mcc"]}
    rows.append({"phone": l, "case": corpus[l]["case"], "own_bt_address": len(addr), "own_bt_names": len(names),
                 "own_name_items": sorted(k for k in f["header"] if k.startswith("bt_name:")),
                 "bt_peer_records": len(bt), "by_nature": dict(nat), "peer_name_mac_shaped": sum(1 for p in bt if p["mac"]),
                 "recognized": len(f["recognized"]),
                 "match_other_by_address": by_a, "match_other_by_name": by_n, "match_by_name_timed": by_n_timed,
                 "matches_per_other": dict(per_other), "match_natures": dict(natm),
                 "celltower": f["cells"]["total"], "no_mcc": f["cells"]["no_mcc"],
                 "no_mcc_rest_complete": f["cells"]["no_mcc_rest_complete"], "sim_mccs": len(mccs),
                 "would_infer": f["cells"]["no_mcc_rest_complete"] if len(mccs) == 1 else 0})
# same full cell key within 15 min, before (MCC as recorded) and after (MCC inferred from the SIM when exactly one)
def keys(l, infer):
    f = F[l]; mccs = {m for _, m in f["imsi_mcc"]}; out = []
    for c in f.get("cell_obs", []):
        m = c["mcc"] or (next(iter(mccs)) if infer and len(mccs) == 1 else None)
        if m and ts(c["t"]): out.append(((m, c["rest"]), ts(c["t"])))
    return out
pairs = []
for case in sorted({v["case"] for v in corpus.values()}):
    ls = sorted(l for l in corpus if corpus[l]["case"] == case)
    for i, a in enumerate(ls):
        for b in ls[i + 1:]:
            res = {}
            for infer in (False, True):
                ka, kb = keys(a, infer), keys(b, infer)
                byk = collections.defaultdict(list)
                for k, t in kb: byk[k].append(t)
                res["after" if infer else "before"] = sum(1 for k, t in ka for u in byk.get(k, ()) if abs(t - u) <= timedelta(minutes=15))
            if any(res.values()) or keys(a, True) and keys(b, True): pairs.append({"pair": a + "-" + b, "shared_cell_15min": res})
for r in rows: print(json.dumps(r))
for p in pairs: print(json.dumps(p))
