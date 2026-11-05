"""Gate for cb-readcarry on the 14 server reports: what Email direction (04 decision 54) and the Harvested kind (04
decision 53) change. Run with the backend on sys.path; counts only, nothing from a record is written.

usage: nice -n 15 ionice -c3 python pol_readcarry_gate.py <backend> <corpus.json> <out.json> [P01,P02,...]

email: per report, direction before (the From mark alone) and after (services.phone.comms.email_direction after it).
       A mail that had a direction before and has another after is a loss and is counted in ``changed``.
stays: per report, stays_of over Location records with a GPS accuracy, before (Harvested as presence) and after
       (Harvested out). Only Location records with a radius enter, as in routine.presence: WiFi fixes and photos are not
       in this measure. A stay present before and overlapped by no stay after is lost; ``lost_with_gps`` holds those
       with at least one non-Harvested point.
"""
import collections
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

backend = sys.argv[1]
sys.path.insert(0, backend)
from services.pattern_of_life import routine  # noqa: E402
from services.phone import comms  # noqa: E402

FIELDS = ("Folder", "Status", "IsPhoneOwner", "TimeStamp", "Latitude", "Longitude", "Type", "GpsHorizontalAccuracy")
GREP = ["grep", "-a", "-E", "-A1", "--no-group-separator",
        r'<model type=|</model>|<(multiM|m)odelField name=|</(multiM|m)odelField>|<field name="(%s)"' % "|".join(FIELDS)]
MODEL = re.compile(r'<model type="([^"]+)"')
FIELD = re.compile(r'<field name="([^"]+)"')
CONT = re.compile(r'<(?:multiM|m)odelField name="([^"]+)"(.*)$')
VALUE = re.compile(r"<value[^>]*>(?:<!\[CDATA\[)?([^<]*?)(?:\]\]>)?</value>")


def records(xml):
    env = dict(os.environ, LC_ALL="C")
    p = subprocess.Popen(GREP + [xml], stdout=subprocess.PIPE, env=env, encoding="utf-8", errors="replace")
    stack, conts, pending = [], [], None
    for line in p.stdout:
        if pending:
            m = VALUE.search(line)
            if m and stack:
                stack[-1]["f"].setdefault(pending, m.group(1))
            pending = None
            continue
        f = FIELD.search(line)
        if f and "<field " in line:
            pending = f.group(1) if f.group(1) in FIELDS else None
            continue
        c = CONT.search(line)
        if c:
            if not c.group(2).rstrip().endswith("/>"):
                conts.append(c.group(1))
            continue
        if "odelField>" in line and "</" in line:
            if conts:
                conts.pop()
            continue
        m = MODEL.search(line)
        if m:
            r = {"t": m.group(1), "f": {}, "kids": [], "cont": conts[-1] if conts else None}
            if stack:
                stack[-1]["kids"].append(r)
            stack.append(r)
        elif "</model>" in line and stack:
            done = stack.pop()
            if done["t"] in ("Email", "Location"):
                yield done
    p.wait()


def stamp(t):
    try:
        d = datetime.fromisoformat((t or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def num(t):
    try:
        return float(t)
    except (TypeError, ValueError):
        return None


def measure(xml):
    mail = collections.Counter()
    pts = []
    for r in records(xml):
        f = r["f"]
        if r["t"] == "Email":
            frm = next((k for k in r["kids"] if k["cont"] == "From"), None)
            mark = frm["f"].get("IsPhoneOwner") if frm else None
            before = {"True": "outgoing", "False": "incoming"}.get(mark, "unknown")
            to_owner = any(k["cont"] in ("To", "Cc", "Bcc") and k["f"].get("IsPhoneOwner") == "True" for k in r["kids"])
            after, basis = (before, "sender_owner_flag") if before != "unknown" else comms.email_direction(
                f.get("Status"), f.get("Folder"), to_owner)
            mail["total"] += 1
            mail["before:%s" % before] += 1
            mail["after:%s" % after] += 1
            mail["basis:%s" % basis] += 1
            if before != "unknown" and before != after:
                mail["changed"] += 1
            if before != "unknown" and frm is not None and to_owner and before == "outgoing":
                mail["from_and_to_both_owner"] += 1
            continue
        if f.get("Type") == "Searched":
            continue
        co = next((k for k in r["kids"] if k["t"] == "Coordinate"), None)
        cf = co["f"] if co else {}
        la, lo, t = num(cf.get("Latitude")), num(cf.get("Longitude")), stamp(f.get("TimeStamp"))
        acc = num(f.get("GpsHorizontalAccuracy")) or num(cf.get("GpsHorizontalAccuracy"))
        if la is None or lo is None or t is None or (la == 0 and lo == 0):
            continue
        harvested = f.get("Type") == "Harvested"
        mail["location_harvested" if harvested else "location_other"] += 1
        if acc and acc > 0:
            mail["location_harvested_with_gps_accuracy" if harvested else "location_other_with_gps_accuracy"] += 1
            if 2 * acc <= routine.PARAMS["stay_max_radius_m"]:
                pts.append((t, la, lo, 2 * acc, "x", t, harvested))
    pts.sort(key=lambda p: p[0])
    before = routine.stays_of([p[:6] for p in pts])
    kept = [p for p in pts if not p[6]]
    after = routine.stays_of([p[:6] for p in kept])
    spans = [(s["start"], s["end"]) for s in after]
    lost = gps = 0
    for s in before:
        if any(a < s["end"] and b > s["start"] for a, b in spans):
            continue
        lost += 1
        if any(not p[6] and s["start"] <= p[0] <= s["end"] for p in pts):
            gps += 1
    return {"email": dict(mail), "stays": {"points_before": len(pts), "points_after": len(kept), "before": len(before),
                                           "after": len(after), "lost": lost, "lost_with_gps": gps}}


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    out = argv[1]
    labels = argv[2].split(",") if len(argv) > 2 else sorted(corpus)
    res = json.load(open(out)) if os.path.exists(out) else {"measure": "cb-readcarry gate, pol_readcarry_gate.py",
                                                            "reports": {}}
    for label in labels:
        spec = corpus[label]
        res["reports"][label] = measure(os.path.join(spec["root"], spec["report"]))
        print(label, json.dumps(res["reports"][label]["stays"]), flush=True)
        json.dump(res, open(out + ".tmp", "w"), indent=1, sort_keys=True)
        os.replace(out + ".tmp", out)
    print("finished", flush=True)


if __name__ == "__main__":
    main(sys.argv[2:])
