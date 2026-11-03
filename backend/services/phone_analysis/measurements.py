"""Gate measurements of the approaches (docs/cellebrite/05 sections 4.7 to 16c, "Measurement first"; 05-S1).

Each measure is a read-only function over one case: counts only, never content, never identifiers. ``record`` runs
an approach's measure and stores it in ``phone_analysis_measurements`` with the gate computed from the thresholds in
the approach's section. ``MEASURES`` maps an approach code to ``(version, fn(conn, case_id) -> (result, gate))``.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from services.phone_analysis.framework import AnalysisError

MEASURES: dict = {}


def measure(code, version):
    def wrap(fn):
        MEASURES[code] = (version, fn)
        return fn
    return wrap


def run(conn, case_id, code) -> tuple:
    if code not in MEASURES:
        raise AnalysisError("There is no measurement for %s yet." % code)
    version, fn = MEASURES[code]
    result, gate = fn(conn, str(case_id))
    return version, result, gate


def record(conn, scope, case_id, code, by) -> dict:
    version, result, gate = run(conn, case_id, code)
    mid = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_analysis_measurements (id, scope, case_id, approach, measure_version, result, gate, "
        "recorded_by) VALUES (:i, :s, :c, :a, :v, CAST(:r AS jsonb), :g, :b)"),
        {"i": mid, "s": scope, "c": str(case_id) if case_id else None, "a": code, "v": version,
         "r": json.dumps(result, sort_keys=True, default=str), "g": gate, "b": by})
    return {"id": str(mid), "scope": scope, "case_id": str(case_id) if case_id else None, "approach": code,
            "measure_version": version, "result": result, "gate": gate}


def rows(conn, case_id=None, code=None) -> list:
    q, p = "SELECT * FROM phone_analysis_measurements WHERE true", {}
    if case_id:
        q += " AND case_id = :c"
        p["c"] = str(case_id)
    else:
        q += " AND scope = 'corpus'"
    if code:
        q += " AND approach = :a"
        p["a"] = code
    return [{"id": str(r.id), "scope": r.scope, "case_id": str(r.case_id) if r.case_id else None,
             "approach": r.approach, "measure_version": r.measure_version, "result": r.result, "gate": r.gate,
             "recorded_at": r.recorded_at.isoformat(), "recorded_by": r.recorded_by}
            for r in conn.execute(text(q + " ORDER BY recorded_at DESC, id"), p)]
