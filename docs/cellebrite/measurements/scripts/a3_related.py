"""Stage A3: models under `RelatedModels` (PA's related copies of a record). Read-only, counts only.

usage: python3 -I a3_related.py <corpus.json> <out_dir> <label>[,<label>...]

Per report: records carrying RelatedModels, related models per record, whether each related model's id equals
the id of any top-level record (a copy of another record) or is found nowhere else, whether its
deleted_state and source_index equal the parent's, and how many of the parent's fields have equal values
in the related model (equal / differing / only one side). Values are compared in memory and never written.
"""
import collections
import json
import os
import sys
import xml.etree.ElementTree as ET


def ln(t):
    return t.rsplit("}", 1)[-1]


def fields(m):
    out = {}
    for c in m:
        if ln(c.tag) in ("field", "multiField"):
            out[c.get("name")] = tuple((v.text or "") for v in c if ln(v.tag) == "value")
    return out


def run(label, spec):
    xml = os.path.join(spec["root"], spec["report"])
    top_ids = collections.Counter()
    pending = []
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
                top_ids[(el.get("type"), el.get("id"))] += 1
                for rm in el.iter():
                    if ln(rm.tag) != "RelatedModels":
                        continue
                    owner = None
                    for cand in el.iter():
                        if rm in list(cand):
                            owner = cand
                            break
                    pf = fields(owner) if owner is not None else {}
                    for r in rm:
                        if ln(r.tag) != "model":
                            continue
                        rf = fields(r)
                        eq = sum(1 for k in pf if k in rf and pf[k] == rf[k])
                        df = sum(1 for k in pf if k in rf and pf[k] != rf[k])
                        one = len(set(pf) ^ set(rf))
                        pending.append({
                            "owner_is_top": owner is el,
                            "type_same": owner is not None and r.get("type") == owner.get("type"),
                            "key": (r.get("type"), r.get("id")),
                            "deleted_same": owner is not None and r.get("deleted_state") == owner.get("deleted_state"),
                            "source_index_same": owner is not None and r.get("source_index") == owner.get("source_index"),
                            "isrelated": r.get("isrelated"),
                            "eq": eq, "df": df, "one": one,
                        })
                el.clear()
                els[-1].remove(el)
            elif tag in ("taggedFiles", "extraInfos"):
                el.clear()
            elif parent in ("taggedFiles", "extraInfos"):
                el.clear()
                els[-1].remove(el)
    c = collections.Counter()
    hist = collections.Counter()
    for p in pending:
        c["related models"] += 1
        c["owner is the top-level record" if p["owner_is_top"] else "owner is a nested model"] += 1
        c["same type as owner" if p["type_same"] else "different type from owner"] += 1
        c["id equals a top-level record id of the same type" if top_ids.get(p["key"]) else "id found on no top-level record"] += 1
        c["deleted_state equals owner" if p["deleted_same"] else "deleted_state differs"] += 1
        c["source_index equals owner" if p["source_index_same"] else "source_index differs"] += 1
        c["isrelated=" + str(p["isrelated"])] += 1
        c["all shared fields equal" if p["df"] == 0 else "some shared field differs"] += 1
        hist["fields equal %s / differing %s / one side only %s" % (bucket(p["eq"]), bucket(p["df"]), bucket(p["one"]))] += 1
    return {"label": label, "counts": dict(sorted(c.items())), "field_comparison": dict(sorted(hist.items()))}


def bucket(n):
    return str(n) if n < 5 else ("5-9" if n < 10 else "10+")


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    os.makedirs(argv[1], exist_ok=True)
    for label in argv[2].split(","):
        res = run(label, corpus[label])
        with open(os.path.join(argv[1], label + ".related.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(json.dumps({"label": label, "related": res["counts"].get("related models", 0)}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
