"""Reconciliation (01 section 8.3 and 8.4): captured equals source on every path and every measure, no tolerance.

``reconcile(source, captured)`` returns ``(result, differences)``. Every difference is listed, sorted by path.
Beyond the counter's measures, a stored row that no marker reaches (``rows_unreached``) and any non-whitespace
tail on the source side are differences too (8.3).
"""
from __future__ import annotations

import json
import uuid

from app.phone.counts import compare

READABLE_MEASURE = {"elements": "elements", "attributes": "attributes", "attr_hash": "attribute values",
                    "texts": "texts", "text_chars": "text length", "text_hash": "text values",
                    "bad_tails": "text between elements"}


def reconcile(source: dict, captured: dict):
    diffs = compare(source, captured)
    for path, c in source["paths"].items():
        if c["bad_tails"] and not any(d["path"] == path and d["measure"] == "bad_tails" for d in diffs):
            diffs.append({"path": path, "measure": "bad_tails", "attribute": None, "source": c["bad_tails"],
                          "captured": 0})
    unreached = captured.get("rows_unreached", 0)
    if unreached:
        diffs.append({"path": "(stored rows)", "measure": "rows_unreached", "attribute": None, "source": 0,
                      "captured": unreached})
    diffs.sort(key=lambda d: (d["path"], d["measure"], d["attribute"] or ""))
    return ("exact" if not diffs else "differs"), diffs


def failure_message(diffs) -> str:
    first = diffs[0]["path"]
    return ("The check found %d differences between the report and what was read, starting at %s. The report has "
            "not been added to the case views. Nothing read has been deleted." % (len(diffs), readable_path(first)))


def readable_path(path: str) -> str:
    return " / ".join(path.split("/")[-3:])


def store_reconciliation(conn, extraction_id, document_index, source, captured, result, diffs):
    rid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO phone_reconciliations (id, extraction_id, document_index, counter_version, result, "
            "source_totals, captured_totals, differences, difference_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (rid, extraction_id, document_index, source.get("counter_version", "phone-counter-1"), result,
             json.dumps(source["totals"]), json.dumps(dict(captured["totals"], rows=captured.get("rows"))),
             json.dumps(diffs), len(diffs)))
    return rid


def accepted_differences(conn, extraction_id) -> dict:
    """``{document_index: differences}`` a person accepted with ``accept_phone_reconciliation_difference`` (02
    decision 37, 07 J-1): for each document, the differences of the reconciliation the latest such decision names.
    The check itself is never loosened: a reading whose differences are not exactly the accepted ones stays held."""
    with conn.cursor() as cur:
        cur.execute("SELECT after FROM adjudications WHERE subject_type = 'phone_extraction' AND subject_id = %s AND "
                    "decision = 'accept_phone_reconciliation_difference' ORDER BY subject_sequence", (extraction_id,))
        named = {}
        for (after,) in cur.fetchall():
            for a in (after or {}).get("accepted_documents") or []:
                named[int(a["document_index"])] = a["reconciliation_id"]
        if not named:
            return {}
        cur.execute("SELECT id::text, document_index, differences FROM phone_reconciliations WHERE extraction_id = %s "
                    "AND id::text = ANY(%s)", (extraction_id, list(named.values())))
        return {d: diffs for rid, d, diffs in cur.fetchall() if named.get(d) == rid}


def is_accepted(accepted: dict, document_index: int, diffs: list) -> bool:
    """A document passes only when a person accepted exactly these differences on it (same paths, measures and
    counts); any change in what differs needs a new decision."""
    key = lambda d: (d["path"], d["measure"], d.get("attribute") or "", d["source"], d["captured"])  # noqa: E731
    got = accepted.get(document_index)
    return got is not None and sorted(map(key, got)) == sorted(map(key, diffs))
