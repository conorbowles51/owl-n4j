"""Gate for a message's direction read from the recipient's owner mark, on the 14 server reports. Counts only, nothing
from a record is written.

usage: nice -n 15 ionice -c3 python pol_message_direction_gate.py <corpus.json> <out.json> [P01,P02,...]

Per report, per InstantMessage: the From party's IsPhoneOwner (True, False, none) against whether a To party is marked
as the owner. From True with To marked is where "a marked recipient received it" would be wrong, so it is the measure
of the rule on records that state both sides. 'gained' is the count that goes from unknown to incoming.
"""
import collections
import json
import os
import re
import subprocess
import sys

GREP = ["grep", "-a", "-E", "-A1", "--no-group-separator",
        r'<model type=|</model>|<(multiM|m)odelField name=|</(multiM|m)odelField>|<field name="IsPhoneOwner"']
MODEL = re.compile(r'<model type="([^"]+)"')
FIELD = re.compile(r'<field name="([^"]+)"')
CONT = re.compile(r'<(?:multiM|m)odelField name="([^"]+)"(.*)$')
VALUE = re.compile(r"<value[^>]*>(?:<!\[CDATA\[)?([^<]*?)(?:\]\]>)?</value>")


def records(xml):
    p = subprocess.Popen(GREP + [xml], stdout=subprocess.PIPE, env=dict(os.environ, LC_ALL="C"), encoding="utf-8",
                         errors="replace")
    stack, conts, pending = [], [], False
    for line in p.stdout:
        if pending:
            m = VALUE.search(line)
            if m and stack:
                stack[-1]["f"].setdefault("IsPhoneOwner", m.group(1))
            pending = False
            continue
        f = FIELD.search(line)
        if f and "<field " in line:
            pending = f.group(1) == "IsPhoneOwner"
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
            if done["t"] == "InstantMessage":
                yield done
    p.wait()


def measure(xml):
    c = collections.Counter()
    for r in records(xml):
        frm = next((k for k in r["kids"] if k["cont"] == "From"), None)
        mark = (frm["f"].get("IsPhoneOwner") if frm else None) or "none"
        to = [k for k in r["kids"] if k["cont"] == "To"]
        owner_to = any(k["f"].get("IsPhoneOwner") == "True" for k in to)
        c["total"] += 1
        c["from_%s:to_owner_%s" % (mark, owner_to)] += 1
        if owner_to:
            c["from_%s:sole_to_%s" % (mark, len(to) == 1)] += 1
        c["to_parties_%s" % min(len(to), 3)] += 1
    return dict(c)


def main():
    corpus = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2]
    labels = sys.argv[3].split(",") if len(sys.argv) > 3 else sorted(corpus)
    res = json.load(open(out)) if os.path.exists(out) else {}
    for label in labels:
        if label in res:
            continue
        spec = corpus[label]
        res[label] = measure(os.path.join(spec["root"], spec["report"]))
        print(label, json.dumps(res[label]), flush=True)
        json.dump(res, open(out + ".tmp", "w"), indent=1, sort_keys=True)
        os.replace(out + ".tmp", out)
    print("finished", flush=True)


main()
