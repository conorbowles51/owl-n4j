"""M-13a (05 section 16.6): records per phone around anchors in the 10-report case; sets the window's default span.

Two stages, run one report at a time under the corpus read rules (06 section 5):

    extract <corpus.json> <label> <scratch_dir>   one report: every top-level record's own time values with an
                                                  explicit offset, as epoch seconds, written to a private scratch
                                                  file (no identifiers, no text, no record ids; deleted after)
    measure <scratch_dir> <out.json> [anchor ...] the counts; anchors are epoch seconds chosen by the investigator,
                                                  or, when none are given, chosen by the rule below

Anchor rule when no investigator has chosen (stated in the output as "rule", never as an investigator's choice):
the UTC hours at which the most phones of the case hold at least one record within 2 hours either side; ties go to
the hour with more records in total, then the earlier hour; anchors are at least 7 days apart, so the three sample
different moments. The output holds counts only: anchors are "anchor 1" to "anchor 3", no dates.

A record counts in a window when the range of its own time values (fields of value type TimeStamp with an offset,
first to last) overlaps it. Records nested in other records are counted with their top-level record.
"""
from __future__ import annotations

import array
import json
import os
import sys
import xml.etree.ElementTree as ET
from bisect import bisect_left

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from a3_extract import ln, ts  # noqa: E402

SPANS_H = (1, 2, 6, 24)


def _times(model, out):
    for c in model:
        tag = ln(c.tag)
        if tag in ("field", "multiField"):
            for v in c:
                if ln(v.tag) == "value" and v.get("type") == "TimeStamp":
                    secs, state = ts(v.text or "")
                    if state == "explicit":
                        out.append(secs)
        elif tag in ("modelField", "multiModelField"):
            for x in c:
                if ln(x.tag) == "model":
                    _times(x, out)


def extract(corpus_path, label, scratch):
    spec = json.load(open(corpus_path, encoding="utf-8"))[label]
    xml = os.path.join(spec["root"], spec["report"])
    starts = array.array("d")  # per record: earliest and latest own time (a record spans [first, last])
    ends = array.array("d")
    allt = array.array("d")    # every time value, for the anchor rule
    records = undated = 0
    stack, els = [], []
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
                t = []
                _times(el, t)
                records += 1
                if t:
                    starts.append(min(t))
                    ends.append(max(t))
                    allt.extend(t)
                else:
                    undated += 1
                el.clear()
                els[-1].remove(el)
            elif tag == "file" and parent == "taggedFiles":
                el.clear()
                els[-1].remove(el)
    os.makedirs(scratch, mode=0o700, exist_ok=True)
    path = os.path.join(scratch, "%s.bin" % label)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(json.dumps({"records": records, "undated": undated, "n": len(starts), "t": len(allt)}).encode() + b"\n")
        starts.tofile(f)
        ends.tofile(f)
        allt.tofile(f)
    print(json.dumps({"label": label, "records": records, "undated": undated}))


def _load(scratch, label):
    with open(os.path.join(scratch, "%s.bin" % label), "rb") as f:
        head = json.loads(f.readline())
        s, e, t = array.array("d"), array.array("d"), array.array("d")
        s.fromfile(f, head["n"])
        e.fromfile(f, head["n"])
        t.fromfile(f, head["t"])
    pairs = sorted(zip(s, e))
    return head, [p[0] for p in pairs], [p[1] for p in pairs], sorted(t)


def _count(starts, ends, a, b):
    """Records whose own time range [first, last] overlaps [a, b): those starting inside, plus those starting
    before a and ending at or after a."""
    i, j = bisect_left(starts, a), bisect_left(starts, b)
    return (j - i) + sum(1 for k in range(i) if ends[k] >= a)


def measure(scratch, out_path, anchors):
    labels = sorted(f[:-4] for f in os.listdir(scratch) if f.endswith(".bin"))
    data = {L: _load(scratch, L) for L in labels}
    basis = "investigator" if anchors else "rule"
    if not anchors:
        hours = {}
        for L, (_, _, _, t) in data.items():
            seen = set()
            for x in t:
                h = int(x // 3600)
                for k in range(h - 2, h + 3):
                    if k not in seen:
                        seen.add(k)
                        hours.setdefault(k, [0, 0])[0] += 1
                hours.setdefault(h, [0, 0])[1] += 1
        ranked = sorted(hours.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
        for h, _ in ranked:
            c = h * 3600.0 + 1800.0
            if all(abs(c - x) >= 7 * 86400 for x in anchors):
                anchors.append(c)
            if len(anchors) == 3:
                break
    out = {"measure": "M-13a", "case": "10-report case", "anchor_basis": basis, "phones": len(labels),
           "method": "05 section 16.6",
           "per_phone": {L: {"records": d[0]["records"], "undated": d[0]["undated"]} for L, d in data.items()},
           "anchors": []}
    for n, c in enumerate(anchors, 1):
        row = {"anchor": "anchor %d" % n, "spans": {}}
        for hspan in SPANS_H:
            a, b = c - hspan * 3600, c + hspan * 3600
            per = {L: _count(d[1], d[2], a, b) for L, d in data.items()}
            items = {L: bisect_left(d[3], b) - bisect_left(d[3], a) for L, d in data.items()}
            vals = sorted(per.values())
            iv = sorted(items.values())
            row["spans"]["±%d h" % hspan] = {
                "items_per_phone": items, "phones_with_items": sum(1 for v in iv if v), "items_total": sum(iv),
                "items_max_phone": iv[-1] if iv else 0, "items_median_phone": iv[len(iv) // 2] if iv else 0,
                "records_overlapping_per_phone": per, "records_overlapping_total": sum(vals)}
        out["anchors"].append(row)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(json.dumps({"anchors": len(out["anchors"]), "basis": basis}))


if __name__ == "__main__":
    if sys.argv[1] == "extract":
        extract(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        measure(sys.argv[2], sys.argv[3], [float(x) for x in sys.argv[4:]])
