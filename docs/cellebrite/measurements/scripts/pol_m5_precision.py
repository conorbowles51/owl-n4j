"""M5 (04 section 13), the column left open: what `Location.Precision` holds and in what unit.

usage: nice -n 15 ionice -c3 python3 -I pol_m5_precision.py <corpus.json> <out.json> [P01,P02,...]

Read-only over the reports. Numbers are written only as histograms and quantiles (04 section 13: no exact reading,
coordinate or time is committed); text values go through the same guard as pol_m5_places.py.

  shape_by_source           Source | shape of the Precision text (digits replaced by <n>), absent included
  number_histogram          the number's decade per word ("Horizontal 10-99")
  number_quantiles          p10 p50 p90 p99 max per word and Source
  round_shares              whole numbers, multiples of 5 and of 10, per word and Source
  both_precision_and_gps    records with Precision and GpsHorizontalAccuracy, and how the two compare
  confidence_by_source      Source | has Precision | Confidence decade
  bare_number_records       the records with a number and no word: parent model, Type, Category, sign, position
  successive_fix_test       distance between successive bare-number fixes over the larger number
  distance_test_tight       distance_test at 15 s, reference accuracy 20 m, for numbers with no GPS accuracy
  distance_test             Precision read as metres against an independent position: for each Precision record
                            with a position and a time, the nearest-in-time record of ANOTHER Source with a GPS
                            accuracy of at most 50 m, within 120 s. Reports per Precision decade: pairs, median
                            distance, share of pairs with distance <= Precision, <= 2 x Precision.
"""
import bisect
import collections
import datetime
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def fnum(t):
    try:
        v = float(t)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def instant(t):
    try:
        return datetime.datetime.fromisoformat((t or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def decade(x):
    x = abs(x)
    if x < 1:
        return "<1"
    e = int(math.floor(math.log10(x)))
    return "%d-%d" % (10 ** e, 10 ** (e + 1) - 1)


def haversine(a, b):
    r = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def q(v, p):
    s = sorted(v)
    return s[min(len(s) - 1, max(0, math.ceil(p / 100.0 * len(s)) - 1))]


def source_word(s, occ):
    if s is None:
        return "<absent>"
    return s if GUARD_RE.match(s) and occ[s] >= 3 else "<other>"


FIELDS = ("Source", "Precision", "GpsHorizontalAccuracy", "Confidence", "TimeStamp", "Latitude", "Longitude", "Type",
          "Category")
GREP = ["grep", "-a", "-E", "-A1", "--no-group-separator",
        r'<model type=|</model>|<field name="(%s)"' % "|".join(FIELDS)]
MODEL = re.compile(r'<model type="([^"]+)"')
FIELD = re.compile(r'<field name="([^"]+)"')
VALUE = re.compile(r"<value[^>]*>(?:<!\[CDATA\[)?([^<]*?)(?:\]\]>)?</value>")


def rows_of(xml):
    """Location records with the fields this measure reads, from a C grep of the report (the reports are written one
    element per line): a stack of the model elements says whose field each one is."""
    env = dict(os.environ, LC_ALL="C")
    p = subprocess.Popen(GREP + [xml], stdout=subprocess.PIPE, env=env, encoding="utf-8", errors="replace")
    stack, names, pending = [], [], None
    for line in p.stdout:
        if pending:
            m = VALUE.search(line)
            if m and stack and stack[-1] is not None:
                stack[-1].setdefault(pending, m.group(1))
            pending = None
            continue
        f = FIELD.search(line)
        if f:
            pending = f.group(1) if f.group(1) in FIELDS else None
            continue
        m = MODEL.search(line)
        if m:
            t = m.group(1)
            rec = {"_t": t} if t in ("Location", "Coordinate") else None
            if t == "Location":
                rec["_parent"] = names[-1] if names else None
            names.append(t)
            if t == "Coordinate" and stack and stack[-1] is not None and stack[-1]["_t"] == "Location":
                stack[-1].setdefault("_coord", rec)
            stack.append(rec)
        elif "</model>" in line and stack:
            done = stack.pop()
            names.pop()
            if done is not None and done["_t"] == "Location":
                yield done
    p.wait()


def measure(xml):
    rows = []
    started = time.monotonic()
    for r in rows_of(xml):
        c = r.get("_coord") or {}
        acc = fnum(r.get("GpsHorizontalAccuracy"))
        if acc is None:
            acc = fnum(c.get("GpsHorizontalAccuracy"))
        la, lo = fnum(c.get("Latitude")), fnum(c.get("Longitude"))
        pos = (la, lo) if la is not None and lo is not None and not (la == 0 and lo == 0) else None
        rows.append({"src": r.get("Source"), "prec": r.get("Precision"), "acc": acc, "pos": pos,
                     "t": instant(r.get("TimeStamp")), "conf": fnum(r.get("Confidence")), "type": r.get("Type"),
                     "cat": r.get("Category"), "parent": r.get("_parent")})
    occ = collections.Counter(x["src"] for x in rows if x["src"])
    out = {"locations": len(rows), "with_precision": sum(1 for x in rows if x["prec"])}
    shape, hist, nums, both = collections.Counter(), collections.Counter(), collections.defaultdict(list), []
    conf, bare = collections.Counter(), collections.Counter()
    occ2 = collections.Counter(v for x in rows for v in (x["type"], x["cat"]) if v)
    for x in rows:
        s = source_word(x["src"], occ)
        p = x["prec"]
        sh = "<absent>" if not p else NUM.sub("<n>", p).strip()
        if sh != "<absent>" and not GUARD_RE.match(sh.replace("<n>", "n")):
            sh = "<other>"
        shape["%s | %s" % (s, sh)] += 1
        conf["%s | %s | %s" % (s, "precision" if p else "no precision",
                               "none" if x["conf"] is None else str(int(x["conf"] // 10 * 10)))] += 1
        if p:
            m = NUM.search(p)
            word = (p[:m.start()] if m else p).strip(" :") or "<none>"
            no_word = word == "<none>"
            if not GUARD_RE.match(word):
                word = "<none>" if no_word else "<other>"
            if m:
                v = float(m.group(0))
                x["num"] = v
                hist["%s %s" % (word, decade(v))] += 1
                nums["%s | %s" % (word, s)].append(v)
                if x["acc"] is not None:
                    both.append((v, x["acc"]))
                if no_word:
                    bare["%s | %s | %s | %s | %s" % (x["parent"], source_word(x["type"], occ2),
                                                     source_word(x["cat"], occ2), "negative" if v < 0 else "positive",
                                                     "position" if x["pos"] else "no position")] += 1
    out["shape_by_source"] = dict(sorted(shape.items()))
    out["number_histogram"] = dict(sorted(hist.items()))
    out["number_quantiles"] = {k: {"n": len(v), "p10": q(v, 10), "p50": q(v, 50), "p90": q(v, 90), "p99": q(v, 99),
                                   "max": max(v)} for k, v in sorted(nums.items())}
    out["round_shares"] = {k: {"n": len(v), "whole": round(sum(1 for a in v if a == int(a)) / len(v), 3),
                               "multiple_of_5": round(sum(1 for a in v if a % 5 == 0) / len(v), 3),
                               "multiple_of_10": round(sum(1 for a in v if a % 10 == 0) / len(v), 3)}
                           for k, v in sorted(nums.items())}
    out["both_precision_and_gps"] = {
        "records": len(both), "equal": sum(1 for a, b in both if a == b),
        "equal_within_0_1_percent": sum(1 for a, b in both if abs(a - b) <= 0.001 * max(abs(a), abs(b))),
        "median_ratio_precision_over_gps": statistics.median(a / b for a, b in both if b) if
        any(b for _, b in both) else None}
    out["confidence_by_source"] = dict(sorted(conf.items()))
    # the distance test: an independent position near in time, from another Source
    refs = sorted((x["t"], i) for i, x in enumerate(rows) if x["t"] is not None and x["pos"] and
                  x["acc"] is not None and 0 < x["acc"] <= 50)
    ts = [t for t, _ in refs]
    per = collections.defaultdict(list)
    tested = 0
    for x in rows:
        if "num" not in x or x["t"] is None or not x["pos"]:
            continue
        tested += 1
        best = None
        k = bisect.bisect_left(ts, x["t"] - 120)
        while k < len(ts) and ts[k] <= x["t"] + 120:
            o = rows[refs[k][1]]
            if o["src"] != x["src"]:
                gap = abs(ts[k] - x["t"])
                if best is None or gap < best[0]:
                    best = (gap, o)
            k += 1
        if best:
            per[decade(x["num"])].append((haversine(x["pos"], best[1]["pos"]), x["num"]))
    out["distance_test"] = {"precision_records_with_position_and_time": tested, "reference_points": len(refs),
                            "by_precision_decade": {k: {
                                "pairs": len(v), "median_distance_m": round(statistics.median(d for d, _ in v), 1),
                                "share_within_precision": round(sum(1 for d, p in v if d <= p) / len(v), 3),
                                "share_within_2x": round(sum(1 for d, p in v if d <= 2 * p) / len(v), 3)}
                                for k, v in sorted(per.items())}}
    out["bare_number_records"] = dict(sorted(bare.items()))
    # bare numbers against each other: successive fixes of one stream close in time. If a number is a radius in metres,
    # the distance between two such fixes of a phone at rest grows with the number, near one to one.
    timed = sorted((x for x in rows if x.get("num", -1) > 0 and x["t"] is not None and x["pos"] and x["acc"] is None),
                   key=lambda x: x["t"])
    steps = collections.defaultdict(list)
    for a, b in zip(timed, timed[1:]):
        if 0 < b["t"] - a["t"] <= 300:
            steps[decade(max(a["num"], b["num"]))].append(haversine(a["pos"], b["pos"]) / max(a["num"], b["num"]))
    out["successive_fix_test"] = {k: {"pairs": len(v), "median_distance_over_number": round(statistics.median(v), 3),
                                      "p90": round(q(v, 90), 3), "share_at_or_under_1": round(
                                          sum(1 for d in v if d <= 1) / len(v), 3)} for k, v in sorted(steps.items())}
    # the same independent-position test, tighter: within 15 s, reference accuracy at most 20 m, and only numbers
    # with no GPS accuracy of their own
    near = sorted((x["t"], i) for i, x in enumerate(rows) if x["t"] is not None and x["pos"] and x["acc"] is not None
                  and 0 < x["acc"] <= 20)
    tn = [t for t, _ in near]
    tight = collections.defaultdict(list)
    for x in rows:
        if x.get("num", -1) <= 0 or x["acc"] is not None or x["t"] is None or not x["pos"]:
            continue
        lo = bisect.bisect_left(tn, x["t"] - 15)
        hi = bisect.bisect_right(tn, x["t"] + 15)
        if lo < hi:
            k = min(range(lo, hi), key=lambda j: abs(tn[j] - x["t"]))
            tight[decade(x["num"])].append((haversine(x["pos"], rows[near[k][1]]["pos"]), x["num"]))
    out["distance_test_tight"] = {k: {"pairs": len(v), "median_distance_m": round(statistics.median(d for d, _ in v), 1),
                                      "share_within_number": round(sum(1 for d, p in v if d <= p) / len(v), 3),
                                      "share_within_2x": round(sum(1 for d, p in v if d <= 2 * p) / len(v), 3)}
                                  for k, v in sorted(tight.items())}
    out["seconds"] = round(time.monotonic() - started, 1)
    return out


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    out_path = argv[1]
    labels = argv[2].split(",") if len(argv) > 2 else sorted(corpus)
    res = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {
        "measure": "M5 Location.Precision (04 section 13), pol_m5_precision.py; histograms and quantiles only",
        "reports": {}}
    for label in labels:
        spec = corpus[label]
        res["reports"][label] = measure(os.path.join(spec["root"], spec["report"]))
        print(label, res["reports"][label]["with_precision"], res["reports"][label]["seconds"], flush=True)
        tmp = out_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
        os.replace(tmp, out_path)
    print("finished", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
