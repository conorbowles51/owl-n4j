"""02 decision 46: time one phone's reading as the sweep worker runs it, with a read probe on another phone's rows.

    DATABASE_URL=<scratch database, never live> python scripts/phone_sweep_timing.py <extraction> <probe extraction> <pace>

Every stage the worker installs, its pace, and the probe's latency split by phase (observe, generic, each applier,
purge of the previous generation), plus WAL written. The phone is marked stale first, so it is read again (a new
generation). Prints counts and timings only. Run it on a scratch copy: it writes a generation.
"""
import json, os, statistics, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import create_engine, text
from services.phone import generic, identities, mappings, registry, sweep
mappings.install(); identities.install()
from services.phone import readings
readings.install()
URL = os.environ["DATABASE_URL"]
eng = create_engine(URL)
EXT, OTHER = sys.argv[1], sys.argv[2]
generic.PACE["factor"] = float(sys.argv[3])
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
sweep._hooks["apply"] = [timed("apply:%s.%s" % (f.__module__.rsplit(".", 1)[-1], f.__name__), f) for f in sweep._hooks["apply"]]

def probe(stop, out):
    e2 = create_engine(URL)
    with e2.connect() as c:
        while not stop.is_set():
            t = time.monotonic()
            c.execute(text("SELECT count(*) FROM pv_timeline_entry WHERE extraction_id = :o"), {"o": OTHER}).scalar()
            c.execute(text("SELECT count(*) FROM pv_comm_event WHERE extraction_id = :e"), {"e": EXT}).scalar()
            out["lat"].append((t, time.monotonic() - t))
            c.rollback()
            stop.wait(1.0)
    e2.dispose()

def pct(xs):
    xs = sorted(xs)
    return {"n": len(xs), "p50_ms": round(statistics.median(xs) * 1000, 1) if xs else None,
            "p95_ms": round(xs[int(0.95 * (len(xs) - 1))] * 1000, 1) if xs else None}

stop, out = threading.Event(), {"lat": []}
th = threading.Thread(target=probe, args=(stop, out)); th.start(); time.sleep(60); stop.set(); th.join()
print(json.dumps({"baseline": pct([l for _, l in out["lat"]])}), flush=True)
with eng.begin() as c:
    c.execute(text("UPDATE phone_interpretation_state SET interpreter_version = 'old' WHERE extraction_id = :e"), {"e": EXT})
with eng.connect() as c:
    lsn0 = c.execute(text("SELECT pg_current_wal_lsn()")).scalar()
stop, out = threading.Event(), {"lat": []}
th = threading.Thread(target=probe, args=(stop, out)); th.start()
t0 = time.monotonic()
res = sweep.interpret_one(eng, EXT)
secs = time.monotonic() - t0
stop.set(); th.join()
with eng.connect() as c:
    wal = c.execute(text("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), :l)"), {"l": lsn0}).scalar()
by = {}
for name, a, b in spans:
    by[name] = {"seconds": round(b - a, 1), **pct([l for t, l in out["lat"] if a <= t < b])}
print(json.dumps({"status": res.get("status"), "generation": res.get("generation"), "seconds": round(secs, 1),
                  "wal_mb": round(float(wal) / 1e6, 1), "pace": generic.PACE["factor"],
                  "whole_pass": pct([l for _, l in out["lat"]]), "by_phase": by,
                  "applied": {k: v for k, v in res.items() if k.startswith("applied:") and not k.startswith("applied:comms")}},
                 default=str), flush=True)
