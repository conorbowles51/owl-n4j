"""The shared framework of every investigative approach (docs/cellebrite/05 section 3).

An approach is a module registered here with:

- ``CODE`` (one of 3.3's approach codes) and ``VERSION`` (a change of algorithm is a new version);
- ``PARAMETERS``: ``{name: {"default": v, "min": a, "max": b}}`` or ``{"default": v, "choices": [...]}``; unknown names
  and out-of-range values are refused (422);
- ``KINDS`` and ``DIRECTION_CODES``: the closed sets of result kinds and of supports and undercuts codes (3.5);
- ``input_manifest(conn, case_id) -> dict``: what the run reads beyond the phones (for example a ledger snapshot);
- ``coverage(conn, case_id) -> dict``: per phone, whether it carries the signal the approach rests on (3.6);
- ``run(conn, case_id, parameters, ctx) -> list[Result]``: pure over the case's records; ``ctx.progress(read, total)``
  and ``ctx.cancelled()`` for checkpoints and cooperative cancel.

A ``Result`` is a dict ``{kind, strength, measures, directions: {supports, undercuts}, sensitive, period_start,
period_end, records: [{extraction_id, record_uid, field_path, ledger_transaction_id, role}]}``. Its ``result_key``
is sha256 over the approach code and the sorted locators and ledger ids it rests on, so equal inputs give equal
keys across runs and a person's decision carries over (3.7).

A run never writes to captured or interpreted records, the ledger or the graph: only to the analysis tables. Runs
are queued in ``phone_analysis_runs`` and drawn one at a time by their own loop in the phone worker process
(``start_worker``), beside and never behind the interpretation sweep (05 decision 19.x, C16).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

log = logging.getLogger(__name__)

APPROACHES: dict = {}
SUBJECT_NS = uuid.UUID("b4d7f1a2-6c3e-4e8b-9f05-1d2c3b4a5e6f")
RESULT_NS = uuid.UUID("0a7e2c91-5b4d-4f63-8e1a-9c2b7d6f4e30")
MAX_LIMIT = 500
LEAD_LABEL = "Lead for enquiry"
COMMON_CODES = ("synced_attribution", "clock_offset_unknown", "selective_extraction", "no_data_period",
                "decoding_confidence_low", "deleted_or_carved", "identity_unreviewed")


class AnalysisError(ValueError):
    status = 422


class NotFound(AnalysisError):
    status = 404


class Conflict(AnalysisError):
    status = 409


class Unavailable(AnalysisError):
    status = 503


def register(module) -> None:
    APPROACHES[module.CODE] = module


def approach(code):
    m = APPROACHES.get(code)
    if m is None:
        raise AnalysisError("There is no analysis called %s." % code)
    return m


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256(obj) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def validate_parameters(module, given: dict | None) -> dict:
    """Every parameter with its value: the defaults, overridden by ``given``. Unknown names and out-of-range values
    are refused."""
    given = dict(given or {})
    spec = getattr(module, "PARAMETERS", {})
    unknown = sorted(set(given) - set(spec))
    if unknown:
        raise AnalysisError("Unknown setting: %s." % ", ".join(unknown))
    out = {}
    for name, s in spec.items():
        v = given.get(name, s["default"])
        if "choices" in s and v not in s["choices"]:
            raise AnalysisError("%s must be one of %s." % (name, ", ".join(map(str, s["choices"]))))
        if "min" in s or "max" in s:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise AnalysisError("%s must be a number." % name)
            if ("min" in s and v < s["min"]) or ("max" in s and v > s["max"]):
                raise AnalysisError("%s must be between %s and %s." % (name, s.get("min"), s.get("max")))
        out[name] = v
    return out


def phones_manifest(conn, case_id) -> list:
    """The case's active phones as the run reads them: capture hash, mapping set and generation."""
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT e.id::text AS extraction_id, e.report_set_sha256 AS capture_sha256, s.mapping_set_id::text AS "
        "mapping_set_id, s.generation, s.interpreter_version FROM phone_extractions e LEFT JOIN "
        "phone_interpretation_state s ON s.extraction_id = e.id WHERE e.case_id = :c AND e.standing = 'active' "
        "ORDER BY e.id"), {"c": str(case_id)})]


def identity_log_head(conn, case_id) -> str:
    r = conn.execute(text(
        "SELECT count(*)::text || ':' || coalesce(max(created_at)::text, '') FROM adjudications WHERE case_id = :c AND "
        "subject_type = 'phone_identity'"), {"c": str(case_id)}).scalar()
    return r or "0:"


def input_manifest(conn, case_id, module) -> dict:
    extra = module.input_manifest(conn, case_id) if hasattr(module, "input_manifest") else {}
    return {"phones": phones_manifest(conn, case_id), "identity_log_head": identity_log_head(conn, case_id),
            **(extra or {})}


def result_key(code, records) -> str:
    parts = sorted("%s|%s|%s|%s" % (r.get("extraction_id") or "", r.get("record_uid") or "", r.get("field_path") or "",
                                    r.get("ledger_transaction_id") or "") for r in records)
    return hashlib.sha256((code + "\n" + "\n".join(parts)).encode("utf-8")).hexdigest()


def _run_out(r) -> dict:
    d = dict(r._mapping)
    for k in ("id", "case_id"):
        d[k] = str(d[k])
    for k in ("created_at", "started_at", "finished_at"):
        d[k] = d[k].isoformat() if d.get(k) else None
    d.pop("cancel_requested", None)
    return d


RUN_COLS = ("id, case_id, approach, approach_version, parameters, parameters_sha256, input_manifest, input_revision, "
            "status, requested_by, counts, coverage, progress, error, created_at, started_at, finished_at")


def request_run(conn, case_id, code, parameters, requested_by) -> tuple:
    """``(run, created)``. Requesting the same run twice returns the existing one (3.3). A failed or cancelled run
    with the same inputs is queued again."""
    module = approach(code)
    params = validate_parameters(module, parameters)
    manifest = input_manifest(conn, case_id, module)
    if not manifest["phones"] and not getattr(module, "RUNS_WITHOUT_PHONES", False):
        raise Unavailable("This case has no phone to analyse.")
    psha, irev = sha256(params), sha256(manifest)
    row = conn.execute(text(
        "SELECT %s FROM phone_analysis_runs WHERE case_id = :c AND approach = :a AND approach_version = :v AND "
        "input_revision = :r AND parameters_sha256 = :p" % RUN_COLS),
        {"c": str(case_id), "a": code, "v": module.VERSION, "r": irev, "p": psha}).first()
    if row is not None and row.status not in ("failed", "cancelled"):
        return _run_out(row), False
    if row is not None:
        conn.execute(text("UPDATE phone_analysis_runs SET status = 'queued', error = NULL, cancel_requested = false, "
                          "progress = '{}', started_at = NULL, finished_at = NULL, requested_by = :b WHERE id = :i"),
                     {"i": row.id, "b": requested_by})
        rid = row.id
    else:
        rid = uuid.uuid4()
        conn.execute(text(
            "INSERT INTO phone_analysis_runs (id, case_id, approach, approach_version, parameters, parameters_sha256, "
            "input_manifest, input_revision, status, requested_by, coverage) VALUES (:i, :c, :a, :v, CAST(:pa AS jsonb), "
            ":p, CAST(:m AS jsonb), :r, 'queued', :b, CAST(:cov AS jsonb))"),
            {"i": rid, "c": str(case_id), "a": code, "v": module.VERSION, "pa": canonical(params), "p": psha,
             "m": canonical(manifest), "r": irev, "b": requested_by, "cov": canonical(coverage(conn, case_id, code))})
    return get_run(conn, case_id, rid), True


def get_run(conn, case_id, run_id) -> dict:
    row = conn.execute(text("SELECT %s FROM phone_analysis_runs WHERE id = CAST(:i AS uuid) AND case_id = :c"
                            % RUN_COLS), {"i": str(run_id), "c": str(case_id)}).first()
    if row is None:
        raise NotFound("That analysis run is not in this case.")
    return _run_out(row)


def list_runs(conn, case_id, code=None) -> list:
    q = "SELECT %s FROM phone_analysis_runs WHERE case_id = :c" % RUN_COLS
    p = {"c": str(case_id)}
    if code:
        q += " AND approach = :a"
        p["a"] = code
    return [_run_out(r) for r in conn.execute(text(q + " ORDER BY created_at DESC, id"), p)]


def cancel(conn, case_id, run_id) -> dict:
    run = get_run(conn, case_id, run_id)
    if run["status"] == "queued":
        conn.execute(text("UPDATE phone_analysis_runs SET status = 'cancelled', finished_at = now() WHERE id = :i"),
                     {"i": run_id})
    elif run["status"] == "running":
        conn.execute(text("UPDATE phone_analysis_runs SET cancel_requested = true WHERE id = :i"), {"i": run_id})
    return get_run(conn, case_id, run_id)


# ---- execution ---------------------------------------------------------------------------------------------------

class _Ctx:
    def __init__(self, engine, run_id):
        self.engine, self.run_id, self._last = engine, run_id, 0.0

    def progress(self, read, total, phone=None):
        now = time.monotonic()
        if now - self._last < 1.0 and read < total:
            return
        self._last = now
        with self.engine.begin() as c:
            c.execute(text("UPDATE phone_analysis_runs SET progress = CAST(:p AS jsonb) WHERE id = :i"),
                      {"i": self.run_id, "p": canonical({"read": read, "total": total, "phone": phone})})

    def cancelled(self) -> bool:
        with self.engine.connect() as c:
            return bool(c.execute(text("SELECT cancel_requested FROM phone_analysis_runs WHERE id = :i"),
                                  {"i": self.run_id}).scalar())


class Cancelled(Exception):
    pass


def execute(engine, run_id) -> dict:
    """Run one queued run to its end: results written in one transaction with the run's completion; the previous
    completed run of the same approach in the case becomes ``superseded`` and stays readable."""
    with engine.begin() as c:
        row = c.execute(text("UPDATE phone_analysis_runs SET status = 'running', started_at = now() WHERE id = :i AND "
                             "status = 'queued' RETURNING case_id, approach, approach_version, parameters"),
                        {"i": run_id}).first()
    if row is None:
        return {"run_id": str(run_id), "status": "not_queued"}
    module, case_id = approach(row.approach), str(row.case_id)
    ctx = _Ctx(engine, run_id)
    try:
        with engine.connect() as c:
            results = module.run(c, case_id, dict(row.parameters), ctx)
            cov = coverage(c, case_id, row.approach)
        if ctx.cancelled():
            raise Cancelled()
        counts = {"results": len(results), "by_kind": {}}
        for r in results:
            counts["by_kind"][r["kind"]] = counts["by_kind"].get(r["kind"], 0) + 1
        counts.update(getattr(module, "last_counts", lambda: {})() or {})
        with engine.begin() as c:
            _write_results(c, case_id, run_id, row.approach, results)
            c.execute(text("UPDATE phone_analysis_runs SET status = 'superseded' WHERE case_id = :c AND approach = :a "
                           "AND status = 'completed' AND id <> :i"), {"c": case_id, "a": row.approach, "i": run_id})
            c.execute(text("UPDATE phone_analysis_runs SET status = 'completed', finished_at = now(), counts = "
                           "CAST(:n AS jsonb), coverage = CAST(:cov AS jsonb) WHERE id = :i"),
                      {"i": run_id, "n": canonical(counts), "cov": canonical(cov)})
        return {"run_id": str(run_id), "status": "completed", "results": len(results)}
    except Cancelled:
        with engine.begin() as c:
            c.execute(text("UPDATE phone_analysis_runs SET status = 'cancelled', finished_at = now() WHERE id = :i"),
                      {"i": run_id})
        return {"run_id": str(run_id), "status": "cancelled"}
    except Exception as exc:  # noqa: BLE001 - every failure is named on the run
        log.exception("phone analysis run %s failed", run_id)
        with engine.begin() as c:
            c.execute(text("UPDATE phone_analysis_runs SET status = 'failed', finished_at = now(), error = :e WHERE "
                           "id = :i"), {"i": run_id, "e": ("%s: %s" % (type(exc).__name__, exc))[:2000]})
        return {"run_id": str(run_id), "status": "failed"}


def _write_results(c, case_id, run_id, code, results):
    seen = set()
    for r in results:
        key = result_key(code, r["records"])
        if key in seen:
            raise AnalysisError("Two results rest on the same records (%s); an approach must merge them." % key[:12])
        seen.add(key)
        rid = uuid.uuid5(RESULT_NS, "%s|%s" % (run_id, key))
        dirs = r.get("directions") or {}
        c.execute(text(
            "INSERT INTO phone_analysis_results (id, run_id, case_id, result_key, kind, strength, measures, directions, "
            "sensitive, period_start, period_end) VALUES (:i, :r, :c, :k, :kind, :s, CAST(:m AS jsonb), CAST(:d AS "
            "jsonb), :sens, :ps, :pe)"),
            {"i": rid, "r": run_id, "c": case_id, "k": key, "kind": r["kind"], "s": r["strength"],
             "m": canonical(r.get("measures") or {}),
             "d": canonical({"supports": dirs.get("supports") or [], "undercuts": dirs.get("undercuts") or []}),
             "sens": bool(r.get("sensitive")), "ps": r.get("period_start"), "pe": r.get("period_end")})
        rows = {}
        for x in r["records"]:
            t = (x.get("extraction_id"), x.get("record_uid"), x.get("field_path"), x.get("ledger_transaction_id"),
                 x["role"])
            rows[t] = x
        for (ext, uid, fp, ledger, role) in rows:
            c.execute(text(
                "INSERT INTO phone_analysis_result_records (id, result_id, extraction_id, record_uid, field_path, "
                "ledger_transaction_id, role) VALUES (:i, :r, :e, :u, :f, :l, :role)"),
                {"i": uuid.uuid4(), "r": rid, "e": ext, "u": uid, "f": fp, "l": ledger, "role": role})


def claim_next(engine):
    """The oldest queued run, or None. Runs left ``running`` by a worker that died are queued again first."""
    with engine.begin() as c:
        c.execute(text("UPDATE phone_analysis_runs SET status = 'queued', started_at = NULL WHERE status = 'running' "
                       "AND started_at < now() - interval '6 hours'"))
        return c.execute(text("SELECT id FROM phone_analysis_runs WHERE status = 'queued' ORDER BY created_at, id "
                              "LIMIT 1")).scalar()


_worker = {}


def _loop(engine, stop):
    while not stop.is_set():
        try:
            rid = claim_next(engine)
            if rid is not None:
                execute(engine, rid)
                continue
        except Exception:  # noqa: BLE001 - the loop keeps going; the run, if any, records its failure
            log.exception("phone analysis worker loop")
        stop.wait(5.0)


def start_worker(engine):
    """One loop per process, one run at a time (``max_jobs = 1``)."""
    if _worker.get("thread") and _worker["thread"].is_alive():
        return _worker["thread"]
    stop = threading.Event()
    _worker["stop"] = stop
    _worker["thread"] = threading.Thread(target=_loop, args=(engine, stop), name="phone-analysis", daemon=True)
    _worker["thread"].start()
    return _worker["thread"]


def stop_worker():
    if _worker.get("stop"):
        _worker["stop"].set()


# ---- coverage ----------------------------------------------------------------------------------------------------

def coverage(conn, case_id, code) -> dict:
    """3.6: per phone and signal, from the approach's ``coverage``; plus the sentence built from it."""
    module = approach(code)
    cov = module.coverage(conn, case_id) if hasattr(module, "coverage") else {"phones": {}, "signals": []}
    cov["sentence"] = coverage_sentence(cov)
    return cov


def coverage_sentence(cov) -> str:
    """"Notifications exist on 2 of 14 phones (B-C1, B-C2). Results below cover those phones only." (no em dash)"""
    phones = cov.get("phones") or {}
    n = len(phones)
    if not n:
        return "This case has no phone to analyse."
    parts = []
    for sig in cov.get("signals") or []:
        carrying = sorted(p["label"] for p in phones.values() if (p.get("signals") or {}).get(sig["code"], {})
                          .get("carries_signal"))
        if len(carrying) == n:
            parts.append("%s exist on all %d phones." % (sig["label"], n))
        elif carrying:
            parts.append("%s exist on %d of %d phones (%s)." % (sig["label"], len(carrying), n, ", ".join(carrying)))
        else:
            parts.append("%s exist on none of the %d phones." % (sig["label"], n))
    any_carry = sorted({p["label"] for p in phones.values() for s in (p.get("signals") or {}).values()
                        if s.get("carries_signal")})
    if any_carry and len(any_carry) < n:
        parts.append("Results below cover those phones only.")
    return " ".join(parts)


# ---- results -----------------------------------------------------------------------------------------------------

def _filters(case_id, run_id, kind=None, strength=None, start=None, end=None, phone=None, identity=None):
    w = ["r.run_id = CAST(:run AS uuid)", "r.case_id = :c"]
    p = {"run": str(run_id), "c": str(case_id)}
    if kind:
        w.append("r.kind = :kind")
        p["kind"] = kind
    if strength:
        w.append("r.strength = :strength")
        p["strength"] = strength
    if start:
        w.append("r.period_end >= CAST(:start AS timestamptz)")
        p["start"] = start
    if end:
        w.append("r.period_start < CAST(:end AS timestamptz)")
        p["end"] = end
    if phone:
        w.append("EXISTS (SELECT 1 FROM phone_analysis_result_records x WHERE x.result_id = r.id AND x.extraction_id = "
                 "CAST(:phone AS uuid))")
        p["phone"] = phone
    if identity:
        w.append("EXISTS (SELECT 1 FROM phone_analysis_result_records x JOIN phone_participations pp ON pp.record_uid = "
                 "x.record_uid WHERE x.result_id = r.id AND pp.identity_key = :ident)")
        p["ident"] = identity
    return " AND ".join(w), p


def results(conn, case_id, run_id, *, kind=None, strength=None, start=None, end=None, phone=None, identity=None,
            offset=0, limit=100) -> dict:
    get_run(conn, case_id, run_id)
    if limit > MAX_LIMIT or limit < 1 or offset < 0:
        raise AnalysisError("limit is 1 to %d." % MAX_LIMIT)
    where, p = _filters(case_id, run_id, kind, strength, start, end, phone, identity)
    total = int(conn.execute(text("SELECT count(*) FROM phone_analysis_results r WHERE " + where), p).scalar() or 0)
    p.update({"off": offset, "lim": limit})
    rows = conn.execute(text(
        "SELECT r.* FROM phone_analysis_results r WHERE %s ORDER BY r.period_start NULLS LAST, r.id OFFSET :off "
        "LIMIT :lim" % where), p).fetchall()
    decisions = _decisions_for(conn, case_id, [(r.result_key, r) for r in rows])
    return {"total": total, "offset": offset, "limit": limit,
            "items": [_result_out(r, decisions.get(r.result_key, [])) for r in rows]}


def _result_out(r, decisions) -> dict:
    return {"id": str(r.id), "run_id": str(r.run_id), "result_key": r.result_key, "kind": r.kind,
            "strength": r.strength, "measures": r.measures, "directions": r.directions, "sensitive": r.sensitive,
            "period_start": r.period_start.isoformat() if r.period_start else None,
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "label": LEAD_LABEL, "decisions": decisions,
            "decision": decisions[-1]["decision"] if decisions else None}


def result_detail(conn, case_id, result_id) -> dict:
    r = conn.execute(text("SELECT * FROM phone_analysis_results WHERE id = CAST(:i AS uuid) AND case_id = :c"),
                     {"i": str(result_id), "c": str(case_id)}).first()
    if r is None:
        raise NotFound("That result is not in this case.")
    decisions = _decisions_for(conn, case_id, [(r.result_key, r)])
    out = _result_out(r, decisions.get(r.result_key, []))
    records = []
    for x in conn.execute(text(
            "SELECT x.extraction_id, x.record_uid, x.field_path, x.ledger_transaction_id, x.role, t.ref_id FROM "
            "phone_analysis_result_records x LEFT JOIN financial_transactions t ON t.id = x.ledger_transaction_id "
            "WHERE x.result_id = :i ORDER BY x.role, x.record_uid, x.ledger_transaction_id"), {"i": r.id}):
        item = {"extraction_id": str(x.extraction_id) if x.extraction_id else None,
                "record_uid": str(x.record_uid) if x.record_uid else None, "field_path": x.field_path,
                "ledger_transaction_id": str(x.ledger_transaction_id) if x.ledger_transaction_id else None,
                "ledger_ref_id": x.ref_id, "role": x.role}
        if x.record_uid:
            item["link"] = "rec://%s%s" % (x.record_uid, ("#" + x.field_path) if x.field_path else "")
        records.append(item)
    out["records"] = records
    run = conn.execute(text("SELECT status, approach FROM phone_analysis_runs WHERE id = :r"), {"r": r.run_id}).first()
    out["run_status"], out["approach"] = run.status, run.approach
    return out


def subject_id(case_id, code, key) -> uuid.UUID:
    return uuid.uuid5(SUBJECT_NS, "%s|%s|%s" % (case_id, code, key))


def _decisions_for(conn, case_id, keyed) -> dict:
    if not keyed:
        return {}
    approach_of = {}
    for key, r in keyed:
        if key not in approach_of:
            approach_of[key] = conn.execute(text("SELECT approach FROM phone_analysis_runs WHERE id = :r"),
                                            {"r": r.run_id}).scalar()
    ids = {str(subject_id(case_id, approach_of[k], k)): k for k in approach_of}
    out = {}
    for d in conn.execute(text(
            "SELECT subject_id, decision, reason, actor_name, actor_email, created_at, after FROM adjudications WHERE "
            "case_id = :c AND subject_type = 'phone_analysis_result' AND subject_id = ANY(CAST(:ids AS uuid[])) "
            "ORDER BY subject_id, subject_sequence"), {"c": str(case_id), "ids": list(ids)}):
        key = ids[str(d.subject_id)]
        out.setdefault(key, []).append({
            "decision": "confirmed" if d.decision == "confirm_phone_result" else "rejected", "reason": d.reason,
            "by": d.actor_name, "at": d.created_at.isoformat(),
            "reading": (d.after or {}).get("reading")})
    return out


def decide(db, case_id, result_id, decision, reason, actor) -> dict:
    """3.7: confirm or reject with a typed reason, through the case decision ledger. Never changes a computed field.
    A decision on a result of a superseded run is refused (409); the current run's result with the same key carries
    the earlier decisions."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_analysis import PhoneAnalysisResultSubject
    from services.financial import decisions as D
    if decision not in ("confirmed", "rejected"):
        raise AnalysisError("A decision is confirmed or rejected.")
    if not reason or not reason.strip():
        raise AnalysisError("Say why, in your own words.")
    conn = db.connection()
    r = conn.execute(text(
        "SELECT r.id, r.result_key, r.kind, r.strength, r.measures, x.status, x.approach FROM phone_analysis_results r "
        "JOIN phone_analysis_runs x ON x.id = r.run_id WHERE r.id = CAST(:i AS uuid) AND r.case_id = :c"),
        {"i": str(result_id), "c": str(case_id)}).first()
    if r is None:
        raise NotFound("That result is not in this case.")
    if r.status != "completed":
        raise Conflict("This result belongs to an earlier run. Reload to see the current reading.")
    sid = subject_id(case_id, r.approach, r.result_key)
    subject = db.get(PhoneAnalysisResultSubject, sid)
    if subject is None:
        subject = PhoneAnalysisResultSubject(id=sid, case_id=uuid.UUID(str(case_id)), approach=r.approach,
                                             result_key=r.result_key)
        db.add(subject)
        db.flush()
    D.record(db, case_id=uuid.UUID(str(case_id)), subject=subject,
             subject_type=AdjudicationSubject.phone_analysis_result,
             decision=(AdjudicationDecision.confirm_phone_result if decision == "confirmed"
                       else AdjudicationDecision.reject_phone_result),
             reason=reason.strip(), actor=actor, before=None,
             after={"decision": decision, "result_id": str(r.id),
                    "reading": {"kind": r.kind, "strength": r.strength, "measures": r.measures}})
    db.flush()
    return result_detail(db.connection(), case_id, result_id)


def utcnow():
    return datetime.now(timezone.utc)
