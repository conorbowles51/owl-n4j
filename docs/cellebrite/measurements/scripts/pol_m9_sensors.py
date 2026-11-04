"""M9 (04 section 13): sensor records, which device recorded them.

usage: python3 -I pol_m9_sensors.py <corpus.json> <out.json> [P01,P02,...]

<corpus.json> maps a label to {"root", "report"} (the private corpus map; never committed). Each named report is
streamed with iterparse, one at a time; only top-level models whose subtree holds a sensor type are converted.
The result for each label replaces that label's entry in <out.json> (other labels are kept), so a run can be split.

Counts only (04 section 13 guards): a String value is written only if it matches GUARD_RE and occurs at least 3 times
in the report for that measure, else `<other>`; DeviceName is never written, only token booleans (`Watch`, `iPhone`,
`Phone`, and the extra tokens below) and presence; times become gap histograms. Cellebrite's own type, field and
enum names are schema, not case content.
"""
import collections
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")
TS_RE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(\.(\d+))?(Z|[+-]\d\d:\d\d)?$")
SENSOR = ("ActivitySensorData", "ActivitySensorDataMeasurement", "ActivitySensorDataSample")
# 04 section 13 names Watch, iPhone and Phone; the others are brand words for wrist and ring devices, counted the
# same way (booleans only) so a wearable named without "Watch" is not missed
TOKENS = ("Watch", "iPhone", "Phone", "iPad", "Fitbit", "Garmin", "Band", "Ring", "Galaxy")


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


def ts(text):
    m = TS_RE.match((text or "").strip())
    if not m or not m.group(9):
        return None
    import calendar
    secs = calendar.timegm(tuple(int(m.group(i)) for i in range(1, 7)) + (0, 0, 0))
    secs += float("0." + m.group(8)) if m.group(8) else 0.0
    off = m.group(9)
    if off != "Z":
        secs -= (1 if off[0] == "+" else -1) * (int(off[1:3]) * 3600 + int(off[4:6]) * 60)
    return secs


def log_bucket(x):
    if x is None:
        return "none"
    if x < 0:
        return "<0"
    if x < 1:
        return "0"
    if x < 2:
        return "1"
    e = int(math.floor(math.log10(x)))
    return "%d-%d" % (10 ** e if e else 2, 10 ** (e + 1) - 1)


def tokens(name):
    if name is None:
        return "\x01<no DeviceName>"
    if not name.strip():
        return "\x01<empty DeviceName>"
    low = name.lower()
    hit = [t for t in TOKENS if t.lower() in low]
    return "\x01" + (" ".join(hit) if hit else "<no token>")


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
    c = collections.defaultdict(collections.Counter)
    sampled = collections.defaultdict(list)  # MeasuredVariableType -> DateSampled instants
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
                if el.get("type") in SENSOR or any(x.get("type") in SENSOR for x in el.iter() if ln(x.tag) == "model"):
                    one(conv(el), g, c, sampled)
                el.clear()
                els[-1].remove(el)
            elif tag in ("modelType", "taggedFiles", "decodedData"):
                el.clear()
            elif parent in ("taggedFiles", "extraInfos", "carvedFiles", "infectedFiles"):
                el.clear()
                els[-1].remove(el)
    gaps = {}
    for mvt, xs in sampled.items():
        xs.sort()
        h = collections.Counter(log_bucket(b - a) for a, b in zip(xs, xs[1:]))
        gaps[mvt] = (sum(h.values()), h)
    # the variable name is a guarded value: route it through the guard as a one-part measure per gap bucket
    for mvt, (n, h) in gaps.items():
        for b, k in h.items():
            g.c["m9_sample_interval_by_variable"][(mvt, "\x01" + b)] += k
    out = g.out()
    out.update({k: dict(sorted(v.items())) for k, v in c.items()})
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def one(rec, g, c, sampled):
    root_dev = {}
    for r, p, f in walk(rec):
        t = r["t"]
        if t not in SENSOR:
            continue
        where = "top" if p is None else "%s.%s" % (p["t"], f)
        c["m9_nesting"]["%s -> %s" % (where, t)] += 1
        for name in r["f"]:
            c["m9_fields_present"]["%s.%s" % (t, name)] += 1
        dn = fv(r, "DeviceName")
        sdt = fv(r, "SourceDeviceType")
        src = fv(r, "Source")
        if dn is not None or t == "ActivitySensorData":
            g.add("m9_devicename_tokens", "\x01" + t, tokens(dn))
        g.add("m9_sourcedevicetype", "\x01" + t, sdt)
        g.add("m9_source", "\x01" + t, src)
        g.add("m9_usermapping", "\x01" + t, fv(r, "UserMapping"))
        if t == "ActivitySensorData":
            root_dev = {"sdt": sdt, "tok": tokens(dn), "src": src}
            g.add("m9_record_sourcedevicetype_x_tokens_x_source", sdt, tokens(dn), src)
            a, b = ts(fv(r, "From")), ts(fv(r, "To"))
            c["m9_record_to_minus_from"][log_bucket(b - a) if a is not None and b is not None else "none"] += 1
            nm = sum(len(k) for k in r["m"].values())
            c["m9_measurements_per_record"][log_bucket(nm)] += 1
        elif t == "ActivitySensorDataMeasurement":
            g.add("m9_measuredvariabletype", fv(r, "MeasuredVariableType"))
            g.add("m9_measurement_devicename_tokens_x_parent_tokens", tokens(dn), root_dev.get("tok", "\x01<no parent>"))
        elif t == "ActivitySensorDataSample":
            mvt = fv(p, "MeasuredVariableType") if p else None
            g.add("m9_sample_parent_variable", mvt)
            # how many samples a rule on the parent record's device fields would reach
            g.add("m9_samples_by_root_sourcedevicetype_x_tokens", root_dev.get("sdt"),
                  root_dev.get("tok", "\x01<no parent>"))
            s = ts(fv(r, "DateSampled"))
            if s is not None:
                sampled[mvt or "<absent>"].append(s)
            e = ts(fv(r, "DateEnded"))
            c["m9_sample_ended_minus_sampled"][log_bucket(e - s) if s is not None and e is not None else "none"] += 1


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    out_path = argv[1]
    labels = argv[2].split(",") if len(argv) > 2 else sorted(corpus)
    res = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    res.setdefault("measure", "M9 (04 section 13), pol_m9_sensors.py; counts only")
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
