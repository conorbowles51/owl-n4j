"""Run the element-level counter (01 unit 0.2) over corpus reports: lxml twice, expat once, each in its own
process so wall time and peak memory are per run. Full outputs (per-path counts and hash sums, which are
derived from content) stay in the private corpus folder; only the summary written with --summary is meant
for the repository: totals, parse state, stability, agreement and timings. No path, name or value of a
report appears in it.

usage:
  python3 -I counter_corpus.py <engine_dir> <corpus.json> <out_dir> <labels,comma-separated>
          [--repeat P06,P09,P02] [--summary <path>]
  python3 -I counter_corpus.py --one <engine_dir> <lxml|expat> <xml> <out.json>   (internal)
"""
import json
import os
import resource
import subprocess
import sys
import time


def one(engine_dir, kind, xml, out):
    sys.path.insert(0, engine_dir)
    if kind == "lxml":
        from app.phone import counter as mod
    else:
        from app.phone import counter_expat as mod
    t0 = time.monotonic()
    res = mod.count_file(xml)
    dt = time.monotonic() - t0
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, sort_keys=True)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB on Linux
    print(json.dumps({"seconds": round(dt, 1), "peak_rss_mib": round(rss / 1024, 1)}))


def run_one(engine_dir, kind, xml, out):
    p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), "--one", engine_dir, kind, xml, out],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("%s counter failed: %s" % (kind, p.stderr.strip().splitlines()[-1:]))
    return json.loads(p.stdout.strip().splitlines()[-1])


def main(argv):
    if argv[0] == "--one":
        return one(*argv[1:5])
    engine_dir, corpus_path, out_dir, labels = argv[0], argv[1], argv[2], argv[3].split(",")
    repeat = set(argv[argv.index("--repeat") + 1].split(",")) if "--repeat" in argv else set()
    summary_path = argv[argv.index("--summary") + 1] if "--summary" in argv else None
    sys.path.insert(0, engine_dir)
    from app.phone.counts import compare

    corpus = json.load(open(corpus_path, encoding="utf-8"))
    os.makedirs(out_dir, exist_ok=True)
    summary_file = os.path.join(out_dir, "summary.json")
    results = json.load(open(summary_file)) if os.path.exists(summary_file) else {}
    for label in labels:
        spec = corpus[label]
        xml = os.path.join(spec["root"], spec["report"])
        runs = {}
        outs = {}
        kinds = ["lxml", "expat"] + (["lxml2"] if label in repeat else [])
        for kind in kinds:
            outs[kind] = os.path.join(out_dir, "%s-%s.json" % (label, kind))
            runs[kind] = run_one(engine_dir, "lxml" if kind == "lxml2" else kind, xml, outs[kind])
            print(json.dumps({"label": label, "run": kind, **runs[kind]}), flush=True)
        a = json.load(open(outs["lxml"], encoding="utf-8"))
        b = json.load(open(outs["expat"], encoding="utf-8"))
        diffs = compare(a, b)
        entry = {
            "label": label,
            "parse_state": a["document"]["parse_state"],
            "open_path_at_error": (a["document"]["error"] or {}).get("open_path"),
            "totals": a["totals"],
            "root_model_count": a["root_attributes"].get("ModelCount"),
            "root_node_count": a["root_attributes"].get("NodeCount"),
            "expat_totals_equal": a["totals"] == b["totals"],
            "expat_paths_equal": a["paths"] == b["paths"],
            "expat_digest_equal": a["document"]["sha256"] == b["document"]["sha256"],
            "expat_difference_count": len(diffs),
            "runs": runs,
        }
        if "lxml2" in outs:
            c = json.load(open(outs["lxml2"], encoding="utf-8"))
            entry["lxml_rerun_identical"] = (a == c)
        results[label] = entry
        with open(summary_file, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=1, sort_keys=True)
    if summary_path:
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump({"what": "Element-level counter (01 unit 0.2) on the server corpus: totals, stability, "
                               "expat agreement, timings. Per-path counts and hash sums stay on the server.",
                       "reports": results}, fh, indent=1, sort_keys=True)
            fh.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
