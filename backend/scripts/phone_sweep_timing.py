"""02 decision 46: time one phone's reading as the sweep worker runs it, with a read probe on another phone's rows.

    DATABASE_URL=<scratch database, never live> python scripts/phone_sweep_timing.py <extraction> <probe extraction> \
        <pace> [<samples file>]

Every stage the worker installs, its pace, and the probe's latency split by phase (observe, generic, each applier,
purge of the previous generation), plus WAL written. The phone is marked stale first, so it is read again (a new
generation). Prints counts and timings only. Run it on a scratch copy: it writes a generation.

The probe reads only the probe extraction, which should be a phone of another case (decision 46's reverse-if). An
earlier probe also counted the phone being read; at its second generation that count alone cost 254 ms at p50
before the pass started, so the rise it showed was partly the probe's own work. Each probe query runs under EXPLAIN
(ANALYZE, BUFFERS) so a change of plan or blocks read from outside the buffer cache show beside its time, and each
sample carries the host's CPU and I/O pressure, because the box's other load moves the probe as much as the pass
does: the p95 is also given over the samples taken at low CPU pressure, before, during and after the pass.
Samples are written to the samples file as they are taken, so a pass stopped part way keeps them.
"""
import json
import os
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the probe: both queries on the probe extraction only (:x), never the extraction being read
PROBE_QUERIES = {
    "timeline": "SELECT count(*) FROM pv_timeline_entry WHERE extraction_id = :x",
    "comm_events": "SELECT count(*) FROM pv_comm_event WHERE extraction_id = :x",
}
LOW_CPU_PRESSURE = 5.0  # /proc/pressure/cpu "some avg10" below this counts as a quiet sample
BASELINE_SECONDS = 120


def pressure(kind):
    try:
        with open("/proc/pressure/" + kind) as f:
            return float(f.readline().split()[1].split("=")[1])
    except OSError:
        return None


def plan_shape(node):
    name = node.get("Index Name") or node.get("Relation Name")
    me = node["Node Type"] + ("(%s)" % name if name else "")
    kids = node.get("Plans") or []
    return me + ("[%s]" % ",".join(plan_shape(k) for k in kids) if kids else "")


def pct(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return {"n": len(xs), "p50_ms": round(statistics.median(xs) * 1000, 1),
            "p95_ms": round(xs[int(0.95 * (len(xs) - 1))] * 1000, 1)}


def summary(samples):
    if not samples:
        return None
    out = {"all": pct([s["total"] for s in samples]),
           "quiet": pct([s["total"] for s in samples if s["cpu"] is not None and s["cpu"] < LOW_CPU_PRESSURE])}
    for k in PROBE_QUERIES:
        out[k] = {"hit_blocks_mean": round(statistics.mean(s[k]["hit"] for s in samples), 1),
                  "read_blocks_mean": round(statistics.mean(s[k]["read"] for s in samples), 1),
                  "plans": sorted({s[k]["plan"] for s in samples})}
    cpus = [s["cpu"] for s in samples if s["cpu"] is not None]
    out["cpu_pressure_mean"] = round(statistics.mean(cpus), 1) if cpus else None
    return out


def main(argv):
    ext, other, pace = argv[1], argv[2], float(argv[3])
    if ext == other:
        raise SystemExit("the probe extraction must be another phone, not the one being read")
    from sqlalchemy import create_engine, text
    from services.phone import generic, identities, mappings, registry, sweep
    mappings.install()
    identities.install()
    from services.phone import readings
    readings.install()
    url = os.environ["DATABASE_URL"]
    eng = create_engine(url)
    sink = open(argv[4], "w") if len(argv) > 4 else None
    generic.PACE["factor"] = pace
    spans = []

    def timed(name, fn):
        def w(*a, **k):
            t = time.monotonic()
            try:
                return fn(*a, **k)
            finally:
                spans.append((name, t, time.monotonic()))
        return w

    registry.observe_extraction = timed("observe", registry.observe_extraction)
    generic.interpret = timed("generic", generic.interpret)
    generic.purge_generations_before = timed("purge", generic.purge_generations_before)
    sweep._hooks["apply"] = [timed("apply:%s.%s" % (f.__module__.rsplit(".", 1)[-1], f.__name__), f)
                             for f in sweep._hooks["apply"]]

    def probe(stop, out, phase):
        e2 = create_engine(url)
        with e2.connect() as c:
            while not stop.is_set():
                s = {"t": time.monotonic(), "phase": phase, "cpu": pressure("cpu"), "io": pressure("io"), "total": 0.0}
                for k, sql in PROBE_QUERIES.items():
                    t = time.monotonic()
                    plan = c.execute(text("EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) " + sql),
                                     {"x": other}).scalar()[0]["Plan"]
                    took = time.monotonic() - t
                    s[k] = {"seconds": took, "hit": plan.get("Shared Hit Blocks", 0),
                            "read": plan.get("Shared Read Blocks", 0), "plan": plan_shape(plan)}
                    s["total"] += took
                c.rollback()
                out.append(s)
                if sink:
                    sink.write(json.dumps(s) + "\n")
                    sink.flush()
                stop.wait(1.0)
        e2.dispose()

    def probed(phase, fn):
        stop, out = threading.Event(), []
        th = threading.Thread(target=probe, args=(stop, out, phase))
        th.start()
        try:
            res = fn()
        finally:
            stop.set()
            th.join()
        return res, out

    _, before = probed("baseline_before", lambda: time.sleep(BASELINE_SECONDS))
    print(json.dumps({"baseline_before": summary(before)}), flush=True)
    with eng.begin() as c:
        c.execute(text("UPDATE phone_interpretation_state SET interpreter_version = 'old' WHERE extraction_id = :e"),
                  {"e": ext})
    with eng.connect() as c:
        lsn0 = c.execute(text("SELECT pg_current_wal_lsn()")).scalar()
    t0 = time.monotonic()
    res, during = probed("pass", lambda: sweep.interpret_one(eng, ext))
    secs = time.monotonic() - t0
    with eng.connect() as c:
        wal = c.execute(text("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), :l)"), {"l": lsn0}).scalar()
    _, after = probed("baseline_after", lambda: time.sleep(BASELINE_SECONDS))
    by = {name: dict(seconds=round(b - a, 1), **(summary([s for s in during if a <= s["t"] < b]) or {}))
          for name, a, b in spans}
    print(json.dumps({"status": res.get("status"), "generation": res.get("generation"), "seconds": round(secs, 1),
                      "wal_mb": round(float(wal) / 1e6, 1), "pace": generic.PACE["factor"],
                      "baseline_before": summary(before), "whole_pass": summary(during), "by_phase": by,
                      "baseline_after": summary(after),
                      "applied": {k: v for k, v in res.items()
                                  if k.startswith("applied:") and not k.startswith("applied:comms")}},
                     default=str), flush=True)
    if sink:
        sink.close()


if __name__ == "__main__":
    main(sys.argv)
