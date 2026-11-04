"""M5 (04 section 13), the columns stage A3 did not split: Location affiliation per Source.

usage: python3 -I pol_m5_places.py <corpus.json> <out.json> [P01,P02,...]

Stage A3 (`a3_extract.py`, results in `measurements/a3/P*.json`) already holds M5's other columns: count per
(Source, Type, Category), nested Coordinate, GpsHorizontalAccuracy quantiles, Precision, Confidence, TimeStamp and
EndTime presence, WirelessNetwork, CellTower, Journey nesting and BSSIDs with a GPS observation. It counted the
DeviceLocationAffiliation x AccountLocationAffiliation x Origin cross-tab over the whole report only. The
`affiliation_unknown` rule (04 decision 22) needs it per Location Source, which this script writes:

  m5_affiliation_by_source        Source | nesting | DeviceLocationAffiliation | AccountLocationAffiliation | Origin
  m5_affiliation_by_source_timed  the same, only Locations with a TimeStamp value (the ones that become events)
  m5_account_presence_by_source   Source | Account present or absent (presence only, never the value)

The Source of a nested Location is its own, else its top-level record's (as the projection reads it). Counts only,
under the 04 section 13 guard (a String value is written only if it matches GUARD_RE and occurs at least 3 times in
the report for that measure, else `<other>`). The result for each label replaces that label's entry in <out.json>.
"""
import collections
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")


def ln(t):
    return t.rsplit("}", 1)[-1]


def conv(m):
    r = {"t": m.get("type"), "f": {}, "m": {}}
    for c in m:
        tag = ln(c.tag)
        if tag in ("field", "multiField"):
            r["f"][c.get("name")] = [v.text or "" for v in c if ln(v.tag) == "value"]
        elif tag in ("modelField", "multiModelField"):
            r["m"][c.get("name")] = [conv(x) for x in c if ln(x.tag) == "model"]
    return r


def fv(r, name):
    v = r["f"].get(name)
    return v[0] if v else None


def walk(r, parent=None, field=None):
    yield r, parent, field
    for name, kids in r["m"].items():
        for k in kids:
            yield from walk(k, r, name)


class Guarded:
    def __init__(self):
        self.c = collections.defaultdict(collections.Counter)

    def add(self, measure, *parts):
        self.c[measure][parts] += 1

    def out(self):
        res = {}
        for measure, cnt in self.c.items():
            occ = collections.Counter()
            for parts, n in cnt.items():
                for p in parts:
                    if isinstance(p, str):
                        occ[p] += n
            g = collections.Counter()
            for parts, n in cnt.items():
                key = []
                for p in parts:
                    if p is None:
                        key.append("<absent>")
                    elif p.startswith("\x01"):
                        key.append(p[1:])
                    elif GUARD_RE.match(p) and occ[p] >= 3:
                        key.append(p)
                    else:
                        key.append("<other>")
                g[" | ".join(key)] += n
            res[measure] = dict(sorted(g.items()))
        return res


def measure(xml):
    g = Guarded()
    stack, els = [], []
    started = time.monotonic()
    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                stack.append(tag)
                els.append(el)
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "model" and parent == "modelType":
                if el.get("type") == "Location" or any(x.get("type") == "Location" for x in el.iter()
                                                       if ln(x.tag) == "model"):
                    one(conv(el), g)
                el.clear()
                els[-1].remove(el)
            elif tag in ("modelType", "taggedFiles", "decodedData"):
                el.clear()
            elif parent in ("taggedFiles", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
                els[-1].remove(el)
    out = g.out()
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def one(rec, g):
    root_source = fv(rec, "Source")
    for r, p, f in walk(rec):
        if r["t"] != "Location":
            continue
        nest = "\x01top" if p is None else "\x01%s.%s" % (p["t"], f)
        src = fv(r, "Source") or root_source
        key = (src, nest, fv(r, "DeviceLocationAffiliation"), fv(r, "AccountLocationAffiliation"), fv(r, "Origin"))
        g.add("m5_affiliation_by_source", *key)
        if (fv(r, "TimeStamp") or "").strip():
            g.add("m5_affiliation_by_source_timed", *key)
        g.add("m5_account_presence_by_source", src, "\x01Account present" if (fv(r, "Account") or "").strip()
              else "\x01Account absent")


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    out_path = argv[1]
    labels = argv[2].split(",") if len(argv) > 2 else sorted(corpus)
    res = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    res.setdefault("measure", "M5 affiliation per Source (04 section 13), pol_m5_places.py; counts only; other M5 "
                              "columns in measurements/a3/P*.json")
    res.setdefault("reports", {})
    for label in labels:
        spec = corpus[label]
        out = measure(os.path.join(spec["root"], spec["report"]))
        res["reports"][label] = out
        res["reports"] = dict(sorted(res["reports"].items()))
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
        os.replace(tmp, out_path)
        print(json.dumps({"label": label, "seconds": out["seconds"]}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
