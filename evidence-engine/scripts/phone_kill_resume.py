"""Kill and resume (docs/cellebrite/01-intake-capture-storage.md unit 2.4). Prints counts and digests only.

Runs the real capture (``app.phone.runner.run_capture``) in a child process and SIGKILLs it ``--kills`` times. Kill k
uses seed ``--seed + k``. Targets run in stage order, an equal share of the kills each: verifying_container,
counting, capturing, reconciling, indexing_files (a resumed capture skips stages already finished, so an earlier
target could not be reached after a later one). The seed draws, within a share of that stage's duration in the uninterrupted run, how long after the child reports that stage the kill lands. A child that
has already passed its target is killed in the stage it is in, and the stage actually killed is recorded. After the
kills the capture runs to the end, and its row digest (``app.phone.digest``) is compared with an uninterrupted
capture of the same report in a second case.

    python -m scripts.phone_kill_resume --url postgresql://... --data-root /data --report-root /path/to/report \
        --label C3 --kills 20 --seed 1000 --out result.json
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import random
import signal
import subprocess
import sys
import threading
import time
import uuid

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ENGINE)  # run with -I, which leaves the script's own directory off the path

STAGES = ("verifying_container", "counting", "capturing", "reconciling", "indexing_files")
ORDER = ("verifying_container", "detecting", "counting", "capturing", "reconciling", "indexing_files", "finishing")
# The delay after a stage starts is drawn from [0, SHARE x that stage's duration in the uninterrupted run]: a resumed
# stage continues from its cursor and is shorter, so the draw stays well inside it.
SHARE = 0.4
DURATION = {}


def child(args):
    from app.phone import runner, store
    conn = store.connect(args.url)

    class Say(runner.Reporter):
        last = None

        def stage(self, name, progress, message="", counts=None):
            if name != self.last:
                self.last = name
                print("STAGE %s %.1f" % (name, time.time()), flush=True)

    res = runner.run_capture(conn, data_root=args.data_root, case_id=args.case, container_path=args.label,
                             root_path="", original_name=args.label, reporter=Say())
    print("RESULT " + json.dumps({k: res.get(k) for k in ("state", "extraction_id", "records", "files",
                                                           "already_in_case")}), flush=True)


def _case(conn, title):
    cur = conn.execute("SELECT id FROM users ORDER BY created_at LIMIT 1").fetchone()
    cid = uuid.uuid4()
    conn.execute("INSERT INTO cases (id,title,status,archived,created_by_user_id,owner_user_id,created_at,updated_at) "
                 "VALUES (%s,%s,'active',false,%s,%s,now(),now())", (cid, title, cur[0], cur[0]))
    link = os.path.join(ARGS.data_root, str(cid))
    os.makedirs(link, exist_ok=True)
    os.symlink(ARGS.report_root, os.path.join(link, ARGS.label))
    return cid


def _spawn(case):
    cmd = [sys.executable, "-I", os.path.abspath(__file__), "--child", "--url", ARGS.url, "--data-root",
           ARGS.data_root, "--case", str(case), "--label", ARGS.label]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, cwd=ENGINE)
    lines = queue.Queue()

    def pump():
        for line in p.stdout:
            lines.put(line.rstrip("\n"))
        lines.put(None)
    threading.Thread(target=pump, daemon=True).start()
    return p, lines


def _run_to_end(case):
    t0 = time.time()
    p, lines = _spawn(case)
    out = list(iter(lines.get, None))
    p.wait()
    result = next((json.loads(line[7:]) for line in out if line.startswith("RESULT ")), None)
    if p.returncode or result is None:
        raise SystemExit("capture did not finish (exit %s)" % p.returncode)
    marks = [(line.split()[1], float(line.split()[2])) for line in out if line.startswith("STAGE ")]
    marks.append(("end", time.time()))
    stages = {name: round(marks[i + 1][1] - at, 1) for i, (name, at) in enumerate(marks[:-1])}
    return result, round(time.time() - t0, 1), stages


def _kill_once(case, k):
    """One child, killed once. Returns the record of the kill, or None if it finished first."""
    seed = ARGS.seed + k
    rng = random.Random(seed)
    target = STAGES[k * len(STAGES) // ARGS.kills]
    delay = rng.uniform(0.0, max(0.05, SHARE * DURATION.get(target, 1.0)) * ARGS.delay_scale)
    p, lines = _spawn(case)
    current, due, t0 = None, None, time.time()
    while True:
        try:
            line = lines.get(timeout=0.05)
        except queue.Empty:
            line = ""
        if line is None:
            p.wait()
            raise SystemExit("child exited %s before kill %d" % (p.returncode, k))
        if line.startswith("STAGE "):
            current = line.split()[1]
            if due is None and current in ORDER and ORDER.index(current) >= ORDER.index(target):
                due = time.time() + delay
        if line.startswith("RESULT "):
            p.wait()
            return {"kill": k, "seed": seed, "target": target, "killed_in": None, "finished": True}
        if due is not None and time.time() >= due:
            os.kill(p.pid, signal.SIGKILL)
            p.wait()
            return {"kill": k, "seed": seed, "target": target, "delay_s": round(delay, 2), "killed_in": current,
                    "after_s": round(time.time() - t0, 1)}


def main():
    from app.phone import store
    from app.phone.digest import extraction_digest, reconciliation_runs
    conn = store.connect(ARGS.url)
    reference_case, killed_case = _case(conn, "kill-resume reference"), _case(conn, "kill-resume killed")
    reference, reference_s, stages = _run_to_end(reference_case)
    DURATION.update(stages)
    kills = []
    for k in range(ARGS.kills):
        record = _kill_once(killed_case, k)
        kills.append(record)
        print(json.dumps(record), flush=True)
        if record.get("finished"):
            break
    final, final_s, _ = _run_to_end(killed_case)
    a, b = extraction_digest(conn, reference["extraction_id"]), extraction_digest(conn, final["extraction_id"])
    out = {"label": ARGS.label, "seed": ARGS.seed, "delay_scale": ARGS.delay_scale, "kills_requested": ARGS.kills,
           "kills_landed": sum(1 for r in kills if r.get("killed_in")),
           "killed_in": {s: sum(1 for r in kills if r.get("killed_in") == s) for s in ORDER},
           "reference": {"seconds": reference_s, "stage_seconds": stages, **reference}, "final": {"seconds_last_run": final_s, **final},
           "digest_equal": a == b, "tables_differing": [t for t in a if a[t] != b[t]],
           "rows": {t: a[t]["rows"] for t in a}, "reconciliation_runs_after_kills": reconciliation_runs(conn, final["extraction_id"]),
           "kills": kills, "cases": [str(reference_case), str(killed_case)]}
    json.dump(out, open(ARGS.out, "w"), indent=1)
    print("SUMMARY " + json.dumps({k: out[k] for k in ("label", "kills_landed", "killed_in", "digest_equal",
                                                       "tables_differing", "rows")}), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--report-root")
    ap.add_argument("--case")
    ap.add_argument("--kills", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1000)
    ap.add_argument("--out")
    ap.add_argument("--delay-scale", type=float, default=1.0, help="multiplies each stage's delay bound (small reports)")
    ap.add_argument("--child", action="store_true")
    ARGS = ap.parse_args()
    child(ARGS) if ARGS.child else main()
