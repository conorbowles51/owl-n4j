"""Reference corpus manifest (01 unit 0.1) over the server's phone report folders.

usage: python3 -I corpus_manifest.py <corpus.json> <out_dir> [--no-cache] [--only P01,P02] [--summary <path>]

<corpus.json> (kept in the private corpus folder, never committed) maps each label to its report:
    {"P01": {"root": "<absolute report root>", "report": "<report xml path relative to root>",
             "case": "1-phone case", "spec05": "1P"}, ...}

Writes, in <out_dir> (the private corpus folder):
    manifest.d/<label>.json  one report each (paths, sizes, hashes, header values)
    manifest.json            all reports, assembled in label order
    hashcache.json           per-file sha256 keyed by (relative path, size, mtime_ns, inode)
--summary writes a structure-only summary (counts and versions, no paths, names, dates or hashes),
the only output meant for the repository.

Folder container hash (01 section 3, step 1): SHA-256 over the sorted manifest lines
"{sha256}  {size}  {relative path}\\n" of every non-skipped file. Skipped: AppleDouble `._*`, `.DS_Store`,
anything under `__MACOSX/`, and v1's `owl_ingest_report.json` at the report root (written by v1, not part of
the production; CB-INDEX rule 5). Skipped files are counted, never hashed into the container.

The output is a pure function of the bytes and the file listing: no run time or host value is written to
manifest.json, so a rerun on unchanged folders gives an identical file. The report folders are opened
read-only and nothing is written beside them. Nothing is printed except counts and labels.
"""
import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

CHUNK = 8 << 20
V1_FILE = "owl_ingest_report.json"
HEADER_ITEMS = (
    "UFED_PA_Version",
    "DeviceInfoCreationTime",
    "DeviceInfoExtractionStartDateTime",
    "DeviceInfoExtractionEndDateTime",
    "ExtractionType",
)
ROOT_ATTRS = ("reportVersion", "extractionType", "NodeCount", "ModelCount", "containsGarbage")


def ln(tag):
    return tag.rsplit("}", 1)[-1]


def skip_reason(rel):
    parts = rel.split("/")
    if "__MACOSX" in parts[:-1] or parts[0] == "__MACOSX":
        return "macosx"
    name = parts[-1]
    if name == ".DS_Store":
        return "ds_store"
    if name.startswith("._"):
        return "appledouble"
    if rel == V1_FILE:
        return "v1_owl_ingest_report"
    return None


def digest(path, want_md5=False):
    h = hashlib.sha256()
    m = hashlib.md5() if want_md5 else None
    n = 0
    with open(path, "rb") as fh:
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            h.update(b)
            if m is not None:
                m.update(b)
            n += len(b)
    return h.hexdigest(), (m.hexdigest() if m is not None else None), n


def list_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            out.append((rel, full))
    out.sort()
    return out


def header(xml_path):
    """Root attributes, metadata items in HEADER_ITEMS, and extractionInfo count, read up to the first
    taggedFiles or decodedData element (the header precedes both)."""
    root_attrs = {}
    items = {}
    extraction_infos = 0
    stack = []
    with open(xml_path, "rb") as fh:
        for ev, el in ET.iterparse(fh, events=("start", "end")):
            t = ln(el.tag)
            if ev == "start":
                if not stack:
                    root_attrs = {k: el.get(k) for k in ROOT_ATTRS if el.get(k) is not None}
                    root_attrs["root_element"] = t
                stack.append(t)
                if t in ("taggedFiles", "decodedData"):
                    break
                if t == "extractionInfo":
                    extraction_infos += 1
                continue
            stack.pop()
            if t == "item" and "metadata" in stack and el.get("name") in HEADER_ITEMS:
                items.setdefault(el.get("name"), []).append((el.text or "").strip())
    return root_attrs, items, extraction_infos


def build_one(label, spec, cache, use_cache, save=None):
    root = spec["root"]
    report_rel = spec["report"]
    files = list_files(root)
    lines = []
    skipped = {}
    total = 0
    hashed_now = 0
    for rel, full in files:
        reason = skip_reason(rel)
        st = os.stat(full)
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        key = "%s|%s|%d|%d|%d" % (label, rel, st.st_size, st.st_mtime_ns, st.st_ino)
        sha = cache.get(key) if use_cache else None
        if sha is None:
            sha, _, n = digest(full)
            if n != st.st_size:
                raise RuntimeError("%s: size changed while hashing a file" % label)
            cache[key] = sha
            hashed_now += 1
            if save is not None:
                save()
        lines.append("%s  %d  %s\n" % (sha, st.st_size, rel))
        total += st.st_size
    lines.sort()
    container = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    xml_full = os.path.join(root, report_rel)
    xml_sha, xml_md5, xml_size = digest(xml_full, want_md5=True)
    root_attrs, items, n_info = header(xml_full)
    rec = {
        "label": label,
        "case": spec.get("case"),
        "spec05_label": spec.get("spec05"),
        "root_path": root,
        "report_path": report_rel,
        "report_bytes": xml_size,
        "report_sha256": xml_sha,
        "report_md5": xml_md5,
        "container_form": "folder",
        "container_sha256": container,
        "container_hash_rule": "sha256 of sorted lines '{sha256}  {size}  {relative path}\\n' over non-skipped files (01 section 3)",
        "file_count": len(lines),
        "file_bytes": total,
        "skipped": skipped,
        "report_version": root_attrs.get("reportVersion"),
        "extraction_type": root_attrs.get("extractionType"),
        "root_element": root_attrs.get("root_element"),
        "contains_garbage": root_attrs.get("containsGarbage"),
        "node_count": int(root_attrs["NodeCount"]) if root_attrs.get("NodeCount") else None,
        "model_count": int(root_attrs["ModelCount"]) if root_attrs.get("ModelCount") else None,
        "producer": items.get("UFED_PA_Version", []),
        "extraction_info_count": n_info,
        "creation_time": items.get("DeviceInfoCreationTime", []),
        "extraction_start": items.get("DeviceInfoExtractionStartDateTime", []),
        "extraction_end": items.get("DeviceInfoExtractionEndDateTime", []),
        "metadata_extraction_type": items.get("ExtractionType", []),
    }
    return rec, hashed_now


def summary_of(manifest):
    out = []
    for r in manifest["reports"]:
        out.append({
            "label": r["label"],
            "case": r["case"],
            "spec05_label": r["spec05_label"],
            "report_version": r["report_version"],
            "producer": sorted(set(r["producer"])),
            "extraction_type": r["extraction_type"],
            "extraction_info_count": r["extraction_info_count"],
            "node_count": r["node_count"],
            "model_count": r["model_count"],
            "file_count": r["file_count"],
            "file_bytes": r["file_bytes"],
            "report_bytes": r["report_bytes"],
            "skipped": r["skipped"],
        })
    return {"what": "Structure-only summary of the reference corpus manifest (01 unit 0.1): the 14 server "
                    "report folders. Counts and versions only; the manifest itself stays on the server.",
            "reports": out}


def dump(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def main(argv):
    corpus_path, out_dir = argv[0], argv[1]
    use_cache = "--no-cache" not in argv
    only = None
    if "--only" in argv:
        only = set(argv[argv.index("--only") + 1].split(","))
    summary_path = argv[argv.index("--summary") + 1] if "--summary" in argv else None
    corpus = json.load(open(corpus_path, encoding="utf-8"))
    os.makedirs(os.path.join(out_dir, "manifest.d"), exist_ok=True)
    cache_path = os.path.join(out_dir, "hashcache.json")
    cache = json.load(open(cache_path)) if (use_cache and os.path.exists(cache_path)) else {}
    last = [time.monotonic()]

    def save(force=False):
        # the cache is saved at most once a minute, so a stopped run loses little work
        if use_cache and (force or time.monotonic() - last[0] > 60):
            dump(cache, cache_path)
            last[0] = time.monotonic()

    for label in sorted(corpus):
        if only and label not in only:
            continue
        rec, hashed = build_one(label, corpus[label], cache, use_cache, save)
        dump(rec, os.path.join(out_dir, "manifest.d", label + ".json"))
        save(force=True)
        print(json.dumps({"label": label, "files": rec["file_count"], "hashed_now": hashed,
                          "skipped": rec["skipped"]}), flush=True)
    reports = []
    for label in sorted(corpus):
        p = os.path.join(out_dir, "manifest.d", label + ".json")
        if os.path.exists(p):
            reports.append(json.load(open(p, encoding="utf-8")))
    manifest = {"what": "Reference corpus manifest (01 unit 0.1). Never committed.",
                "report_count": len(reports), "reports": reports}
    dump(manifest, os.path.join(out_dir, "manifest.json"))
    if summary_path:
        dump(summary_of(manifest), summary_path)
    print(json.dumps({"reports": len(reports)}))


if __name__ == "__main__":
    main(sys.argv[1:])
