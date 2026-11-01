"""Stage A3: record-to-source information (`extraInfos`) and the 05 S17 gate, per report. Read-only, counts only.

usage: python3 -I a3_extrainfo.py <corpus.json> <out_dir> <label>[,<label>...]

For each report:
  - extraInfo elements, their `type` values (guarded), and how their `id` resolves: to a top-level record,
    to a nested model, or to nothing;
  - nodeInfo elements and which attributes they carry (id, path, tableName, offset, size);
  - how a nodeInfo resolves to a tagged file: by `id` equal to the file's id, else by `path` equal to the
    file's `path`;
  - for resolved files: tagged `Database`, present on disk, MD5 verified (files are hashed read-only);
  - 05 S17 gate: top-level records that resolve to a present, verified Database file, through an extraInfo
    (method b) or through a file jump target (method a), and the union.
Paths, names, table names and ids are never written.
"""
import collections
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

GUARD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./:()-]{0,40}$")


def ln(t):
    return t.rsplit("}", 1)[-1]


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(8 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def guard(cnt):
    out = collections.Counter()
    for k, n in cnt.items():
        out[k if (k and GUARD_RE.match(k) and n >= 3) else "<other>"] += n
    return dict(sorted(out.items()))


def run(label, spec):
    root = spec["root"]
    xml = os.path.join(root, spec["report"])
    files = {}          # file id -> (tags, local path, md5)
    by_path = {}        # device path -> file id
    top_of = {}         # model id -> set of top-level record indexes
    top_idx = -1
    stack, els = [], []
    c = collections.Counter()
    ei_types = collections.Counter()
    via_extra = collections.defaultdict(set)   # file id -> top-level records (method b)
    via_jump = collections.defaultdict(set)    # file id -> top-level records (method a)
    model_depth = 0
    with open(xml, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            tag = ln(el.tag)
            if ev == "start":
                parent = stack[-1] if stack else None
                stack.append(tag)
                els.append(el)
                if tag == "model" and "decodedData" in stack:
                    if parent == "modelType":
                        top_idx += 1
                        model_depth = 0
                    model_depth += 1
                    mid = el.get("id")
                    if mid:
                        top_of.setdefault(mid, set()).add(top_idx)
                continue
            stack.pop()
            els.pop()
            parent = stack[-1] if stack else None
            if tag == "file" and parent == "taggedFiles":
                items = {}
                for md in el:
                    if ln(md.tag) == "metadata":
                        for it in md:
                            if ln(it.tag) == "item":
                                items[it.get("name")] = (it.text or "").strip()
                fid = el.get("id")
                files[fid] = (items.get("Tags") or "", items.get("Local Path") or "", (items.get("MD5") or "").lower())
                if el.get("path"):
                    by_path.setdefault(el.get("path"), fid)
                el.clear()
                els[-1].remove(el)
            elif tag == "targetid" and "decodedData" in stack and el.get("ismodel") == "false":
                t = (el.text or "").strip()
                if t in files:
                    via_jump[t].add(top_idx)
            elif tag == "model" and parent == "modelType":
                el.clear()
                els[-1].remove(el)
            elif tag == "extraInfo" and parent == "extraInfos":
                c["extraInfo"] += 1
                ei_types[el.get("type") or ""] += 1
                eid = el.get("id")
                tops = top_of.get(eid)
                c["extraInfo id -> record or model" if tops else "extraInfo id -> nothing"] += 1
                nodes = [n for n in el.iter() if ln(n.tag) == "nodeInfo"]
                c["nodeInfo"] += len(nodes)
                for n in nodes:
                    for a in ("id", "path", "tableName", "offset", "size", "name"):
                        if n.get(a):
                            c["nodeInfo with " + a] += 1
                    fid = n.get("id") if n.get("id") in files else by_path.get(n.get("path") or "\x00")
                    how = "by id" if n.get("id") in files else ("by path" if fid else "unresolved")
                    c["nodeInfo resolves to a tagged file " + how] += 1
                    if fid and tops:
                        via_extra[fid].update(tops)
                el.clear()
                els[-1].remove(el)
    # files involved
    involved = set(via_extra) | set(via_jump)
    state = {}
    for fid in involved:
        tags, lp, md5 = files[fid]
        tagged_db = "Database" in [t.strip() for t in tags.split(",")]
        full = os.path.join(root, lp.replace("\\", "/")) if lp else None
        if not full or not os.path.isfile(full):
            st = "absent"
        elif os.path.getsize(full) == 0:
            st = "zero bytes"
        elif not md5:
            st = "no MD5 in report"
        else:
            st = "verified" if md5_of(full) == md5 else "MD5 differs"
        state[fid] = (tagged_db, st)
    files_out = collections.Counter("%s | %s" % ("Database" if db else "not Database", st) for db, st in state.values())
    ok = {f for f, (db, st) in state.items() if db and st == "verified"}
    rec_b = set().union(*(via_extra[f] for f in ok if f in via_extra)) if ok else set()
    rec_a = set().union(*(via_jump[f] for f in ok if f in via_jump)) if ok else set()
    rec_b_any = set().union(*via_extra.values()) if via_extra else set()
    out = {
        "label": label,
        "top_level_records": top_idx + 1,
        "counts": dict(sorted(c.items())),
        "extraInfo_types": guard(ei_types),
        "files_referenced_by_extraInfo": len(via_extra),
        "files_referenced_by_jump_target": len(via_jump),
        "referenced_files_by_kind_and_state": dict(sorted(files_out.items())),
        "records_with_an_extraInfo_resolving_to_any_tagged_file": len(rec_b_any),
        "s17_records_to_present_verified_database_via_extraInfo": len(rec_b),
        "s17_records_to_present_verified_database_via_jump_target": len(rec_a),
        "s17_records_to_present_verified_database_either": len(rec_a | rec_b),
    }
    return out


def main(argv):
    corpus = json.load(open(argv[0], encoding="utf-8"))
    os.makedirs(argv[1], exist_ok=True)
    for label in argv[2].split(","):
        res = run(label, corpus[label])
        with open(os.path.join(argv[1], label + ".extrainfo.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1, sort_keys=True)
            fh.write("\n")
        print(json.dumps({"label": label, "extraInfo": res["counts"].get("extraInfo", 0),
                          "s17_either": res["s17_records_to_present_verified_database_either"]}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
