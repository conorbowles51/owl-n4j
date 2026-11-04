"""cb-coloc-rest item A, pass 1: one lean read-only streaming pass per report. Writes salted hashes and counts
to a private pickle (never printed, never committed). usage: python3 -I bt_pass.py <corpus.json> <out_dir> <label>"""
import collections, hashlib, hmac, json, os, pickle, re, sys, time
import xml.etree.ElementTree as ET
WANT = {"DeviceConnectivity", "RecognizedDevice", "CellTower", "SIMData"}
def ln(t): return t.rsplit("}", 1)[-1]
def norm_mac(v):
    h = re.sub(r"[^0-9a-f]", "", (v or "").lower())
    return h if len(h) == 12 and re.fullmatch(r"[0-9a-f:\-\s]+", (v or "").strip().lower()) else None
def main(corpus, out_dir, label):
    spec = json.load(open(corpus))[label]
    salt_p = os.path.join(out_dir, "salt.bin")
    if not os.path.exists(salt_p):
        with open(salt_p, "wb") as fh: fh.write(os.urandom(32))
        os.chmod(salt_p, 0o600)
    salt = open(salt_p, "rb").read()
    H = lambda kind, v: hmac.new(salt, ("%s|%s" % (kind, v)).encode(), hashlib.sha256).hexdigest()[:24]
    f = {"header": collections.defaultdict(set), "peers": [], "recognized": [], "cells": collections.Counter(),
         "imsi_mcc": set(), "dc_fields": collections.Counter(), "rd_fields": collections.Counter()}
    t0 = time.monotonic()
    stack, els = [], []
    with open(os.path.join(spec["root"], spec["report"]), "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                stack.append(tag); els.append(el); continue
            stack.pop(); els.pop()
            parent = stack[-1] if stack else None
            if tag == "model" and parent == "modelType":
                t = el.get("type")
                if t in WANT:
                    vals = collections.defaultdict(list)
                    for fld in el:
                        if ln(fld.tag) not in ("field", "multiField"): continue
                        for v in fld.iter():
                            if ln(v.tag) == "value" and (v.text or "").strip():
                                vals[fld.get("name")].append(v.text.strip())
                    if t == "DeviceConnectivity":
                        for k in vals: f["dc_fields"][k] += 1
                        dn = (vals.get("DeviceName") or [""])[0]
                        f["peers"].append({"method": (vals.get("ConnectivityMethod") or [""])[0],
                                           "nature": (vals.get("ConnectivityNature") or [""])[0],
                                           "name": H("btname", dn.casefold()) if dn else None,
                                           "mac": H("btmac", norm_mac(dn)) if norm_mac(dn) else None,
                                           "timed": bool(vals.get("StartTime")), "t": (vals.get("StartTime") or [None])[0]})
                    elif t == "RecognizedDevice":
                        for k in vals: f["rd_fields"][k] += 1
                        n = (vals.get("Name") or [""])[0]
                        ids = [norm_mac(x) for x in vals.get("DeviceIdentifiers", []) + vals.get("Identifier", [])]
                        f["recognized"].append({"name": H("btname", n.casefold()) if n else None,
                                                "mac": [H("btmac", x) for x in ids if x], "timed": False})
                    elif t == "CellTower":
                        mcc = (vals.get("MCC") or [""])[0]
                        rest = all(vals.get(k) for k in ("MNC", "LAC", "CID"))
                        f["cells"]["total"] += 1
                        f["cells"]["no_mcc" if not mcc else "mcc"] += 1
                        if not mcc and rest: f["cells"]["no_mcc_rest_complete"] += 1
                        if mcc: f["cells"]["mcc_value:" + H("mcc", mcc)] += 1
                        if rest: f.setdefault("cell_obs", []).append({"mcc": H("mcc", mcc) if mcc else None, "rest": H("cellrest", "|".join(((vals.get("Type") or vals.get("CellTowerType") or [""])[0].upper(),) + tuple(vals[k][0] for k in ("MNC", "LAC", "CID")))), "t": (vals.get("TimeStamp") or [None])[0]})
                    elif t == "SIMData":
                        if "IMSI" in " ".join(vals.get("Name", [])).upper():
                            for x in vals.get("Value", []):
                                d = re.sub(r"\D", "", x)
                                if len(d) >= 6: f["imsi_mcc"].add(("simdata", d[:3]))
                el.clear(); els[-1].remove(el)
            elif tag == "item" and parent == "metadata" and "taggedFiles" not in stack and "decodedData" not in stack:
                name, v = el.get("name"), (el.text or "").strip()
                if v and name in ("Bluetooth MAC Address", "DeviceInfoBluetoothDeviceAddress"):
                    if norm_mac(v): f["header"]["bt_mac"].add(H("btmac", norm_mac(v)))
                    else: f["header"]["bt_mac_unparsed"].add(name)
                elif v and name in ("DeviceInfoBluetoothDeviceName", "DeviceInfoDeviceName"):
                    f["header"]["bt_name:" + name].add(H("btname", v.casefold()))
                elif v and name == "IMSI":
                    d = re.sub(r"\D", "", v)
                    if len(d) >= 6: f["imsi_mcc"].add(("header", d[:3]))
            elif tag in ("taggedFiles", "decodedData", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
            elif parent in ("taggedFiles", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear(); els[-1].remove(el)
    f["imsi_mcc"] = {(src, H("mcc", m)) for src, m in f["imsi_mcc"]}
    f["header"] = dict(f["header"])
    p = os.path.join(out_dir, label + ".bt.pkl")
    with open(p, "wb") as fh: pickle.dump(f, fh)
    os.chmod(p, 0o600)
    import resource
    print(json.dumps({"label": label, "peers": len(f["peers"]), "recognized": len(f["recognized"]), "cells": f["cells"]["total"],
                      "seconds": round(time.monotonic() - t0, 1), "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}), flush=True)
if __name__ == "__main__":
    main(*sys.argv[1:4])
