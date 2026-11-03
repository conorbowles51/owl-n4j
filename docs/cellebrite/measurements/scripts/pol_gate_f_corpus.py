"""Gate F corpus run (04 section 11; 06 row 52): the pattern-of-life performance targets on P14, and the
two-phone targets on P12 + P14 of the 3-phone case, in a scratch database. Outputs counts and timings only.

Run from backend/ with the backend venv, after P12 and P14 are captured into the scratch case:
    python pol_gate_f_corpus.py <database url> <case id> <P12 extraction> <P14 extraction> <out.json> [stage ...]
Stages: interpret, build, reclassify, http (default: all, in that order). Each stage appends to out.json.
The interpretation runs the worker's own stages except the graph and conversation-text stages (they write to
Neo4j and the search index, which a scratch run must not touch).
"""
from __future__ import annotations

import json
import os
import resource
import statistics
import subprocess
import sys
import time
import uuid

sys.path.insert(0, os.getcwd())

URL, CASE, P12, P14, OUT = sys.argv[1:6]
STAGES = sys.argv[6:] or ["interpret", "build", "reclassify", "http"]


def record(key, value):
    data = json.load(open(OUT)) if os.path.exists(OUT) else {}
    data[key] = value
    json.dump(data, open(OUT, "w"), indent=1, sort_keys=True, default=str)
    print(key, json.dumps(value, default=str)[:600], flush=True)


def pct(xs):
    xs = sorted(xs)
    return {"n": len(xs), "p50_ms": round(statistics.median(xs) * 1000, 1),
            "p95_ms": round(xs[max(0, int(0.95 * len(xs)) - 1)] * 1000, 1), "max_ms": round(xs[-1] * 1000, 1)}


def engine():
    from sqlalchemy import create_engine
    return create_engine(URL)


def interpret():
    from services.phone import generic, identities, mappings, readings, sweep
    mappings.install(); identities.install(); readings.install()
    generic.PACE["factor"] = 0.0
    eng = engine()
    for name, ext in (("P12", P12), ("P14", P14)):
        t = time.monotonic()
        sweep.interpret_one(eng, ext)
        record("interpret_%s_s" % name, round(time.monotonic() - t, 1))


def build():
    from services.pattern_of_life import activity, availability, places  # noqa: F401 (registers the after steps)
    availability.install(); places.install()
    for name, ext in (("P12", P12), ("P14", P14)):
        code = "\n".join([
            "import json, sys, time, resource",
            "sys.path.insert(0, '.')",
            "from sqlalchemy import create_engine",
            "from services.pattern_of_life import activity, availability, places",
            "availability.install(); places.install()",
            "e = create_engine(%r)" % URL,
            "t = time.monotonic()",
            "with e.begin() as c:",
            "    out = activity.build(c, %r)" % ext,
            "ta = time.monotonic() - t",
            "activity._after_activity(e, %r)" % ext,
            "tt = time.monotonic() - t",
            "print(json.dumps({'activity_s': round(ta, 1), 'total_s': round(tt, 1),",
            "    'peak_rss_mb': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),",
            "    'result': {k: v for k, v in (out or {}).items() if isinstance(v, (int, float, str))}}))",
        ])
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=os.getcwd())
        line = (p.stdout.strip().splitlines() or ["{}"])[-1]
        try:
            res = json.loads(line)
        except ValueError:
            res = {"error": (p.stderr or p.stdout)[-800:]}
        res["exit"] = p.returncode
        record("build_%s" % name, res)
    from sqlalchemy import text
    with engine().connect() as c:
        for name, ext in (("P12", P12), ("P14", P14)):
            record("rows_%s" % name, {t: c.execute(text("SELECT count(*) FROM %s WHERE extraction_id = :e" % t),
                                                    {"e": ext}).scalar()
                                      for t in ("pol_activity_event", "pol_place_observation", "pol_hourly_rollup")})


def reclassify():
    """Re-applying mappings to P14: once unchanged, then a new activity mapping version (the shipped catalogue with its
    version raised and one row changed, as the U2 test does), then back to the shipped one. The copy lives in a
    private scratch folder and is removed."""
    import shutil
    import tempfile
    from services.pattern_of_life import activity
    from services.phone.mappings import loader
    eng = engine()

    def once(label):
        loader.ensure_recorded(eng)
        t = time.monotonic()
        with eng.begin() as c:
            out = activity.reclassify(c, P14)
        record("reclassify_P14_%s" % label, {"seconds": round(time.monotonic() - t, 1), "result": {
            k: v for k, v in (out or {}).items() if isinstance(v, (int, float, str))}})

    src = os.path.join(os.getcwd(), "services", "phone", "mappings", "data")
    once("unchanged")
    scratch = tempfile.mkdtemp(prefix="pol-gatef-maps-")
    try:
        d = os.path.join(scratch, "data")
        shutil.copytree(src, d)
        path = os.path.join(d, "activity_strength", "catalogue.json")
        v2 = json.load(open(path))
        v2["version"] += 1
        for r in v2["body"]["rows"]:
            if r["row_id"] == "devev-display":
                r["outputs"]["class"] = "interaction"
        json.dump(v2, open(path, "w"))
        loader.use_data_dir(d)
        once("new_version")
    finally:
        loader.use_data_dir(src)
        shutil.rmtree(scratch, ignore_errors=True)
    once("shipped_again")


def http():
    from datetime import timedelta
    from sqlalchemy import text
    from routers.pattern_of_life import MAX_GRID_DAYS
    from services.pattern_of_life import subjects
    from tests.pattern_pg import api_client
    eng = engine()
    with eng.begin() as c:
        busiest = c.execute(text(
            "SELECT (hour_utc AT TIME ZONE 'UTC')::date AS d, sum(interaction_strong + interaction_moderate + "
            "interaction_weak + device_state + passive) AS n FROM pol_hourly_rollup WHERE extraction_id = :e "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 1"), {"e": P14}).first()
        raw = c.execute(text("SELECT min(instant_utc), max(instant_utc) FROM pol_activity_event WHERE extraction_id = :e"),
                        {"e": P14}).first()
        # "full extraction span" is the phone's usual span (04 decision 38): stray far-off dates are set apart
        usual = {name: subjects.usual_span(c, e) for name, e in (("P12", P12), ("P14", P14))}
        # the counterpart most often on the other side that day, for "no contact with"
        other = c.execute(text(
            "SELECT counterpart_identity_id FROM pol_activity_event WHERE extraction_id = :e AND counterpart_identity_id "
            "IS NOT NULL AND (instant_utc AT TIME ZONE 'UTC')::date = :d GROUP BY 1 ORDER BY count(*) DESC LIMIT 1"),
            {"e": P14, "d": busiest[0]}).scalar()
        # a scratch person holding both phones (timing fixture only): a dossier linked to each phone's owner identity
        from services.phone import identities as I
        dossier = c.execute(text("SELECT id FROM case_profiles WHERE case_id = :c AND display_name = 'Timing fixture'"),
                            {"c": CASE}).scalar()
        keys = {e: (I.owner(c, e).get("owner_identity_keys") or []) for e in (P12, P14)}
        if dossier is None and all(keys.values()):
            dossier = str(uuid.uuid4())
            uid = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": CASE}).scalar()
            c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, created_by_user_id) "
                           "VALUES (:d, :c, 'person', 'Timing fixture', :u)"), {"d": dossier, "c": CASE, "u": uid})
            for e, k in keys.items():
                c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) "
                               "SELECT :c, id, :d, :x FROM phone_identities WHERE identity_key = :k AND case_id = :c "
                               "ON CONFLICT DO NOTHING"), {"c": CASE, "d": dossier, "x": str(uuid.uuid4()), "k": k[0]})
    record("fixture", {"busiest_day_events": int(busiest[1]), "raw_span_days": (raw[1] - raw[0]).days + 1,
                       "usual_span_days": {k: (u["last"] - u["first"]).days + 1 for k, u in usual.items()},
                       "set_apart_events": {k: u["set_apart"] for k, u in usual.items()},
                       "two_phone_person": bool(dossier), "no_contact_counterpart": bool(other)})
    day = busiest[0].isoformat()
    s14 = json.dumps({"kind": "extraction", "extraction_id": P14})
    two = json.dumps({"kind": "dossier", "dossier_id": str(dossier)}) if dossier else None

    def timeit(client, method, url, n=20, **kw):
        """n timed requests after one untimed one: the section 11 targets are for a warm cache."""
        xs, status = [], None
        getattr(client, method)(url, **kw)
        for _ in range(n):
            t = time.monotonic()
            r = getattr(client, method)(url, **kw)
            xs.append(time.monotonic() - t)
            status = r.status_code
            if r.status_code != 200:
                return {"status": r.status_code, "detail": r.text[:300]}
        return dict(pct(xs), status=status)

    def grid_range(first, last):
        first = max(first, last - timedelta(days=MAX_GRID_DAYS - 1))
        return first.isoformat(), last.isoformat(), (last - first).days + 1

    with api_client(eng, CASE) as client:
        B = "/api/pattern/%s" % CASE
        record("t_day_passive_collapsed", timeit(client, "get", B + "/day", params={
            "subject": s14, "date": day, "zone": "UTC", "include_passive": "false"}))
        # "with all passive items": every passive item of the busiest day, page by page (Show all)
        xs, cur, total = [], 0, None
        while cur is not None:
            t = time.monotonic()
            r = client.get(B + "/events", params={"subject": s14, "start": "%sT00:00:00Z" % day,
                                                  "end": "%sT00:00:00Z" % (busiest[0] + timedelta(days=1)).isoformat(),
                                                  "classes": "passive", "cursor": cur})
            xs.append(time.monotonic() - t)
            if r.status_code != 200:
                xs = None
                record("t_day_all_passive_pages", {"status": r.status_code, "detail": r.text[:300]})
                break
            cur, total = r.json()["next_cursor"], r.json()["total"]
        if xs:
            record("t_day_all_passive_pages", dict(pct(xs), items=total))
        g1 = grid_range(usual["P14"]["first"], usual["P14"]["last"])
        g2 = grid_range(min(u["first"] for u in usual.values()), max(u["last"] for u in usual.values()))
        record("grid_range", {"P14_days": g1[2], "person_days": g2[2], "max_grid_days": MAX_GRID_DAYS})
        record("t_grid_P14", timeit(client, "get", B + "/grid", n=10, params={
            "subject": s14, "start_date": g1[0], "end_date": g1[1], "zone": "UTC"}))
        if two:
            record("t_grid_person_2_phones", timeit(client, "get", B + "/grid", n=10, params={
                "subject": two, "start_date": g2[0], "end_date": g2[1], "zone": "UTC"}))
        record("t_subjects", timeit(client, "get", B + "/subjects", n=10))
        record("t_routine_P14", timeit(client, "get", B + "/routine", n=3, params={"subject": s14, "zone": "UTC"}))
        # statement check, 24 h on the busiest day, every kind except together, for the two-phone person
        subj = json.loads(two) if two else json.loads(s14)
        start = "%sT00:00:00Z" % day
        end = "%sT00:00:00Z" % (busiest[0] + timedelta(days=1)).isoformat()
        kinds = {"inactive": {}, "active": {}, "at_place": {"place": {"lat": 0.0, "lon": 0.0, "radius_m": 500}}}
        if other:
            kinds["no_contact"] = {"counterpart": {"identity_ids": [str(other)]}}
        checks = {}
        for kind, extra in kinds.items():
            r = client.post(B + "/claims", json=dict({"kind": kind, "subject": subj, "window_start": start,
                                                      "window_end": end, "window_zone": "UTC",
                                                      "window_text": "timing"}, **extra))
            if r.status_code != 200:
                checks[kind] = {"status": r.status_code, "detail": r.text[:200]}
                continue
            cl = r.json()
            if cl["status"] != "confirmed":
                cr = client.post(B + "/claims/%s/confirm" % cl["id"], json={"expected_version": cl["version"]})
                if cr.status_code != 200:
                    checks[kind] = {"status": cr.status_code, "detail": cr.text[:200]}
                    continue
            res = timeit(client, "post", B + "/claims/%s/evaluate" % cl["id"], n=20)
            last = client.get(B + "/claims/%s/evaluations" % cl["id"]).json()
            res["items"] = (client.get(B + "/claims/%s/evaluations/%s" % (cl["id"], last["items"][0]["evaluation_id"]))
                            .json().get("total_items") if last.get("items") else None)
            checks[kind] = res
        record("t_statement_check_24h", {"subject": "person with 2 phones" if two else "P14", "kinds": checks})
        ts, te = min(u["first"] for u in usual.values()), max(u["last"] for u in usual.values()) + timedelta(days=1)
        t = time.monotonic()
        r = client.post(B + "/together", json={"subjects": [{"kind": "extraction", "extraction_id": P12},
                                                            {"kind": "extraction", "extraction_id": P14}],
                                               "start": "%sT00:00:00Z" % ts.isoformat(),
                                               "end": "%sT00:00:00Z" % te.isoformat()})
        out = r.json() if r.status_code in (200, 202) else {"status": r.status_code, "detail": r.text[:300]}
        rid = out.get("run_id") or out.get("id")
        while rid and out.get("status") not in ("done", "failed") and time.monotonic() - t < 1800:
            time.sleep(2)
            out = client.get(B + "/together/%s" % rid).json()
        record("t_together_P12_P14", {"seconds": round(time.monotonic() - t, 1), "status": out.get("status"),
                                      "span_days": (te - ts).days, "counts": out.get("counts"),
                                      "detail": out.get("detail")})


for st in STAGES:
    t0 = time.monotonic()
    {"interpret": interpret, "build": build, "reclassify": reclassify, "http": http}[st]()
    record("stage_%s_s" % st, round(time.monotonic() - t0, 1))
