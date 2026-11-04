"""cb-coloc-rest item A: read-only counts per active phone (no values printed)."""
import re, sys, json
from collections import Counter, defaultdict
sys.path.insert(0, sys.argv[1])
from sqlalchemy import create_engine, text
url = [l.split("=",1)[1].strip().strip('"') for l in open("/home/conorbowles51/app-v3/owl-n4j/.env") if l.startswith("DATABASE_URL=")][0]
eng = create_engine(url.replace("+psycopg2", "+psycopg"))
from services.phone import identities
from services.phone_analysis import fields as FV
from services.pattern_of_life.places import tower_key
MAC = re.compile(r"^[0-9a-f]{2}([:\-]?[0-9a-f]{2}){5}$", re.I)
def norm_mac(v):
    h = re.sub(r"[^0-9a-f]", "", (v or "").lower())
    return h if len(h) == 12 else None
out = []
with eng.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    cases = [r[0] for r in conn.execute(text("SELECT DISTINCT case_id FROM phone_extractions WHERE standing='active' ORDER BY 1"))]
    for c in cases:
        exts = [str(r[0]) for r in conn.execute(text("SELECT id FROM phone_extractions WHERE case_id=:c AND standing='active' ORDER BY id"), {"c": c})]
        own = {}
        peers = {}
        for e in exts:
            h = identities.header_items(conn, e)
            addrs = {norm_mac(x) for k in ("Bluetooth MAC Address", "DeviceInfoBluetoothDeviceAddress") for x in h.get(k, []) if norm_mac(x)}
            names = {x.strip().casefold() for x in h.get("DeviceInfoBluetoothDeviceName", []) if x.strip()}
            imsis = set(re.sub(r"\D", "", x) for x in h.get("IMSI", []))
            for v in FV.field_values(conn, e, ("SIMData",), ("Name", "Value")).values():
                if "IMSI" in " ".join(v["values"].get("Name", ())).upper():
                    imsis.update(re.sub(r"\D", "", x) for x in v["values"].get("Value", ()))
            mccs = {i[:3] for i in imsis if len(i) >= 6}
            dc = FV.field_values(conn, e, ("DeviceConnectivity",), ("DeviceName", "ConnectivityMethod", "ConnectivityNature", "DeviceIdentifier", "MacAddress", "Address"))
            bt = [v for v in dc.values() if "Bluetooth" in v["values"].get("ConnectivityMethod", ())]
            nat = Counter(tuple(sorted(set(v["values"].get("ConnectivityNature", ())))) or ("none",) for v in bt)
            rd = FV.field_values(conn, e, ("RecognizedDevice",), ("Name",))
            towers = [tower_key(b) for (b,) in conn.execute(text("SELECT body FROM phone_records WHERE extraction_id=:e AND model_type='CellTower'"), {"e": e})]
            own[e] = (addrs, names)
            peers[e] = (bt, rd)
            out.append({"case": str(c)[:8], "phone": e[:8], "own_bt_address": len(addrs), "own_bt_name": len(names),
                        "header_keys_bt": sorted(k for k in h if "luetooth" in k),
                        "bt_connectivity": len(bt), "bt_by_nature": {"/".join(k): n for k, n in nat.items()},
                        "bt_name_mac_shaped": sum(1 for v in bt for n in v["values"].get("DeviceName", ()) if MAC.match(n.strip())),
                        "recognized_devices": len(rd),
                        "celltower": len(towers), "celltower_no_mcc": sum(1 for k in towers if k["mcc"] is None),
                        "celltower_no_mcc_rest_complete": sum(1 for k in towers if k["mcc"] is None and None not in (k["mnc"], k["lac"], k["cid"])),
                        "sim_imsi": len(imsis), "sim_mccs": len(mccs)})
        for row in out:
            if row["case"] != str(c)[:8]:
                continue
            e = [x for x in exts if x.startswith(row["phone"])][0]
            bt, rd = peers[e]
            by_addr = by_name = 0
            for o in exts:
                if o == e: continue
                oa, on = own[o]
                for v in bt:
                    for n in v["values"].get("DeviceName", ()):
                        if norm_mac(n) and norm_mac(n) in oa: by_addr += 1
                        elif n.strip().casefold() in on: by_name += 1
                for v in rd.values():
                    for n in v["values"].get("Name", ()):
                        if n.strip().casefold() in on: by_name += 1
            row["peers_matching_other_phone_by_address"] = by_addr
            row["peers_matching_other_phone_by_name"] = by_name
            row["phones_in_case"] = len(exts)
for r in out:
    print(json.dumps(r))
