"""Phone interpretation sweep (02 sections 1.3 and 5.7).

A backend thread, beside the financial identity sweep: one extraction at a time, each in one transaction that
observes the registry, writes generation n+1 of every derived row, applies the loaded mappings, deletes
generation n and records the state. A pass that fails or is killed leaves generation n readable and the state
unchanged, and the next pass starts again (interpretation is a pure function of the capture, the registry, the
mapping set and the extraction's decisions, so nothing needs pausing or resuming).

An extraction is (re)interpreted when its capture is read (``captured`` or ``captured_incomplete``), it stands
``pending`` or ``active``, and any of these differ from its state row: the interpreter version, the mapping set,
the capture revision, the decision revision.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone import generic, registry

log = logging.getLogger(__name__)

IDLE_SECONDS = 30
BACKOFF_SECONDS = (30, 60, 120, 300, 600)
_hooks = {"mapping_set": None, "apply": [], "decision_revision": None, "sensitive": None, "planner": None}


def register_mapping_set(fn):
    """``fn(conn) -> (mapping_set_id, named_keys)``; the mapping loader registers it (02 section 6.6)."""
    _hooks["mapping_set"] = fn


def register_applier(fn):
    """``fn(conn, extraction_id, generation, plan) -> dict`` runs after the generic rows are written (6.7); ``plan`` is
    the planner's result, or None when no planner is registered."""
    if fn not in _hooks["apply"]:
        _hooks["apply"].append(fn)


def register_decision_revision(fn):
    """``fn(conn, extraction_id) -> str`` (8.8: sha256 over the extraction's phone decisions)."""
    _hooks["decision_revision"] = fn


def register_planner(fn):
    """``fn(conn, extraction_id) -> plan``: what the mappings decide before the rows are written; the plan's
    ``marks`` are stamped by the generic pass and the plan is handed to every applier (02 section 6.7)."""
    _hooks["planner"] = fn


def register_sensitive_fields(fn):
    """``fn() -> frozenset((type, field))``; the loader's ``sensitive_fields`` mapping (5.5). The interpreter's
    built-in list is always kept as well, so a mapping change can add a sensitive field but never remove one."""
    _hooks["sensitive"] = fn


def sensitive_fields():
    fn = _hooks["sensitive"]
    return generic.SENSITIVE_DEFAULT | (fn() if fn else frozenset())


def mapping_set(conn):
    fn = _hooks["mapping_set"]
    return fn(conn) if fn else (None, frozenset())


def decision_revision(conn, extraction_id):
    fn = _hooks["decision_revision"]
    return fn(conn, extraction_id) if fn else None


def capture_revision(row) -> str:
    raw = "%s|%s|%s|%s" % (row["captured_at"].isoformat() if row["captured_at"] else "", row["record_count"],
                           row["capture_code_version"], row["capture_state"])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _now():
    return datetime.now(timezone.utc)


def _extraction(conn, extraction_id, lock=False):
    row = conn.execute(text(
        "SELECT id, case_id, capture_state::text AS capture_state, standing::text AS standing, captured_at, "
        "record_count, capture_code_version, device_zone, device_zone_source, flags FROM phone_extractions "
        "WHERE id = :e" + (" FOR SHARE" if lock else "")), {"e": extraction_id}).one_or_none()
    return dict(row._mapping) if row else None


def candidates(conn, limit=50, only=None):
    """Extractions whose derived rows are missing or stale, oldest capture first."""
    set_id, _ = mapping_set(conn)
    where = " AND e.id = :only" if only is not None else ""
    rows = conn.execute(text(
        "SELECT e.id, e.captured_at, e.record_count, e.capture_code_version, e.capture_state::text AS capture_state, "
        "s.interpreter_version, s.mapping_set_id, s.capture_revision, s.decision_revision, s.status "
        "FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id "
        "WHERE e.capture_state IN ('captured', 'captured_incomplete') AND e.standing IN ('pending', 'active')"
        + where + " ORDER BY e.captured_at NULLS LAST, e.id"), {"only": only} if only is not None else {}).fetchall()
    out = []
    for r in rows:
        m = r._mapping
        if m["interpreter_version"] is None:
            out.append(m["id"])
        elif (m["interpreter_version"] != generic.GENERIC_VERSION or str(m["mapping_set_id"] or "") != str(set_id or "")
              or m["capture_revision"] != capture_revision(m)
              or (m["decision_revision"] or None) != (decision_revision(conn, m["id"]) or None)):
            out.append(m["id"])
        if limit is not None and len(out) >= limit:
            break
    return out


def examiner_zone(flags):
    return ((flags or {}).get("examiner_selected_zone") or {}).get("zone")


def interpret_one(engine, extraction_id) -> dict:
    """One extraction in one transaction (5.7). Returns the state written."""
    started = time.monotonic()
    with engine.connect() as conn:
        with conn.begin():
            if not conn.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('phone_interpretation'), "
                                     "hashtext(:e))"), {"e": str(extraction_id)}).scalar():
                return {"status": "busy"}  # another worker holds this extraction
            ext = _extraction(conn, extraction_id, lock=True)
            if ext is None or ext["capture_state"] not in ("captured", "captured_incomplete"):
                return {"status": "skipped"}
            if str(extraction_id) not in [str(x) for x in candidates(conn, limit=None, only=extraction_id)]:
                return {"status": "current"}
            state = conn.execute(text(
                "SELECT generation FROM phone_interpretation_state WHERE extraction_id = :e FOR UPDATE"),
                {"e": extraction_id}).one_or_none()
            if state is None:
                conn.execute(text(
                    "INSERT INTO phone_interpretation_state (extraction_id, case_id, status) VALUES (:e, :c, 'pending') "
                    "ON CONFLICT DO NOTHING"), {"e": extraction_id, "c": ext["case_id"]})
                generation = 0
            else:
                generation = state[0]
            held = generic.held_documents(conn, extraction_id)
            if held:
                conn.execute(text(
                    "UPDATE phone_interpretation_state SET status = 'held', error = :err, updated_at = now(), "
                    "capture_revision = :cr WHERE extraction_id = :e"),
                    {"e": extraction_id, "cr": capture_revision(ext),
                     "err": "The check found differences in document %s; a person must accept them first."
                            % ", ".join(str(d) for d in held)})
                return {"status": "held", "documents": held}
            phase = {}

            def lap(name, t0=[started]):  # noqa: B006 - seconds per phase, kept in the state row's counts
                now = time.monotonic()
                phase["phase_seconds:" + name] = round(now - t0[0], 1)
                t0[0] = now

            set_id, named = mapping_set(conn)
            obs = registry.observe_extraction(conn, extraction_id, named)
            lap("observe")
            new_gen = generation + 1
            the_plan = _hooks["planner"](conn, extraction_id) if _hooks["planner"] else None
            lap("plan")
            prog = _progress(engine, extraction_id, ext.get("record_count"))
            counts = generic.interpret(conn, extraction_id, new_gen, sensitive=sensitive_fields(),
                                       marks=the_plan["marks"] if the_plan else None, progress=prog)
            lap("generic")
            applied = {}
            for fn in _hooks["apply"]:
                applied.update(fn(conn, extraction_id, new_gen, the_plan) or {})
            lap("apply")
            counts = dict(counts, flags_raised=obs["flags_raised"],
                          seconds=round(time.monotonic() - started, 1), **phase,
                          **{"applied:%s" % k: v for k, v in applied.items()})
            if generation:
                counts["purge_pending"] = True  # cleared by the purge below; a stopped process leaves it set
            conn.execute(text(
                "UPDATE phone_interpretation_state SET generation = :g, mapping_set_id = :ms, interpreter_version = :iv, "
                "capture_revision = :cr, decision_revision = :dr, registry_observed_at = now(), interpreted_at = now(), "
                "device_zone = :dz, device_zone_basis = :dzb, examiner_zone = :ez, status = 'done', error = NULL, "
                "counts = CAST(:counts AS jsonb), updated_at = now() WHERE extraction_id = :e"),
                {"g": new_gen, "ms": set_id, "iv": generic.GENERIC_VERSION, "cr": capture_revision(ext),
                 "dr": decision_revision(conn, extraction_id), "dz": ext["device_zone"],
                 "dzb": "device_setting_in_report" if ext["device_zone"] else "not_in_report",
                 "ez": examiner_zone(ext["flags"]), "counts": json.dumps(counts, default=str), "e": extraction_id})
    # The swap has committed: readers see generation new_gen. Earlier generations go in short paced transactions.
    t0 = time.monotonic()
    deleted = generic.purge_generations_before(engine, extraction_id, new_gen) if generation else {}
    done = {"deleted_previous": sum(deleted.values()), "phase_seconds:purge_previous": round(time.monotonic() - t0, 1)}
    _purged(engine, extraction_id, new_gen, done)
    prog(ext.get("record_count") or 0, finished=True)
    counts.pop("purge_pending", None)
    return dict(counts, status="done", generation=new_gen, **done)


def _progress(engine, extraction_id, total):
    """Records read so far, written on a connection of its own so readers see it while the pass runs (07 J-8)."""
    state = {"at": 0.0}

    def write(done, finished=False):
        now = time.monotonic()
        if not finished and now - state["at"] < 1.0:
            return
        state["at"] = now
        try:
            with engine.begin() as c:
                c.execute(text(
                    "INSERT INTO phone_interpretation_progress (extraction_id, records_total, records_done, started_at, "
                    "updated_at, finished_at) VALUES (:e, :t, :d, now(), now(), CASE WHEN :f THEN now() END) "
                    "ON CONFLICT (extraction_id) DO UPDATE SET records_total = EXCLUDED.records_total, records_done = "
                    "EXCLUDED.records_done, updated_at = now(), finished_at = EXCLUDED.finished_at, started_at = CASE "
                    "WHEN :d0 THEN now() ELSE phone_interpretation_progress.started_at END"),
                    {"e": extraction_id, "t": total or 0, "d": done, "f": finished, "d0": done == 0})
        except Exception:  # noqa: BLE001 - progress is a display aid; the pass stands
            log.warning("phone interpretation progress not written for %s", extraction_id, exc_info=True)

    write(0, False)
    return write


def _purged(engine, extraction_id, generation, done):
    with engine.begin() as conn:
        conn.execute(text("UPDATE phone_interpretation_state SET counts = (counts - 'purge_pending') || CAST(:d AS jsonb) "
                          "WHERE extraction_id = :e AND generation = :g"),
                     {"d": json.dumps(done), "e": extraction_id, "g": generation})


def purge_leftovers(engine) -> dict:
    """Finish the purges a stopped process left (``purge_pending`` still set): rows older than the current
    generation are invisible to readers but hold space until deleted."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT extraction_id, generation FROM phone_interpretation_state "
                                 "WHERE counts ? 'purge_pending'")).fetchall()
    out = {}
    for ext, gen in rows:
        t0 = time.monotonic()
        deleted = generic.purge_generations_before(engine, ext, gen)
        _purged(engine, ext, gen, {"deleted_previous": sum(deleted.values()),
                                   "phase_seconds:purge_previous": round(time.monotonic() - t0, 1)})
        out[str(ext)] = sum(deleted.values())
    return out


def record_failure(engine, extraction_id, exc):
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE phone_interpretation_state SET status = 'failed', error = :err, updated_at = now() "
                "WHERE extraction_id = :e"), {"e": extraction_id, "err": ("%s: %s" % (type(exc).__name__, exc))[:2000]})
    except Exception:  # noqa: BLE001 - the failure is logged; the previous generation stays readable
        log.exception("could not record phone interpretation failure")


def run_pass(engine, limit=50) -> list:
    with engine.connect() as conn:
        todo = candidates(conn, limit)
    results = []
    for ext in todo:
        if stop_requested():
            break
        try:
            results.append((ext, interpret_one(engine, ext)))
        except Exception as exc:  # noqa: BLE001
            log.exception("phone interpretation failed for %s", ext)
            record_failure(engine, ext, exc)
            results.append((ext, {"status": "failed", "error": str(exc)}))
    return results


_STOP = {"event": None}


def stop_requested():
    ev = _STOP["event"]
    return bool(ev and ev.is_set())


def seed_registry(engine):
    with engine.begin() as conn:
        return registry.apply_seed(conn)


async def run_phone_interpretation_forever():
    """Started by ``backend/main.py`` beside ``run_identity_graph_forever``: a thread runs the loop; on
    cancellation the stop event is set and the current extraction's transaction finishes or rolls back."""
    import asyncio

    from postgres.session import _get_background_engine
    stop = threading.Event()
    work = asyncio.create_task(asyncio.to_thread(sweep_forever, stop, _get_background_engine))
    try:
        await asyncio.shield(work)
    except asyncio.CancelledError:
        stop.set()
        await work
        raise


def sweep_forever(stop: threading.Event, engine_factory):
    failures = 0
    seeded = False
    _STOP["event"] = stop
    while not stop.is_set():
        try:
            engine = engine_factory()
            if not seeded:
                seed_registry(engine)
                purge_leftovers(engine)
                seeded = True
            results = run_pass(engine)
            failures = 0 if all(r.get("status") != "failed" for _, r in results) else failures + 1
            wait = IDLE_SECONDS if not results else (1 if failures == 0 else
                                                     BACKOFF_SECONDS[min(failures, len(BACKOFF_SECONDS)) - 1])
        except Exception:  # noqa: BLE001
            failures += 1
            log.exception("phone interpretation sweep failed")
            wait = BACKOFF_SECONDS[min(failures, len(BACKOFF_SECONDS)) - 1]
        stop.wait(wait)
