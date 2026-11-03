"""Export the records behind an analysis result, a statement check or an incident window (07 J-14b; 03 section 12.2
sources ``analysis_result``, ``statement_check`` and ``incident_window``).

Each source's records are frozen as one ``phone_selection`` (``entry_export.store_selection``), and the export draws
that selection, every copy kept, so its total is the count frozen. The export draws messages, calls and other
communications; records of other kinds behind the source (a learned word, a location, a device event) are not in it,
and the sentence returned says how many, so the dialog states it. A source with no communication record behind it is
refused with that reason, never exported empty.

- ``analysis_result``: the records a result rests on (``phone_analysis_result_records``), of the case; or, with
  ``kept_id``, the records of a kept result as they were frozen.
- ``statement_check``: every record a saved check lists, including every event of its context groups (04 decision
  37), not only the first page.
- ``incident_window``: every communication on the case's active phones from ``start`` to ``end`` (or only on
  ``extraction_ids``), as the window shows them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from services.phone.entry_export import EntryExportError, store_selection

SOURCES = ("analysis_result", "statement_check", "incident_window")
MAX_WINDOW_HOURS = 24 * 7


class SourceExportError(EntryExportError):
    pass


def _result_records(conn, case_id, ref) -> tuple:
    from services.phone_analysis.approaches import TITLES
    if ref.get("kept_id"):
        from services.phone_analysis import keep
        records, label = keep.kept_records(conn, case_id, ref["kept_id"])
        return records, "The records behind the kept result “%s”" % label
    rid = ref.get("result_id")
    head = conn.execute(text(
        "SELECT r.kind, u.approach FROM phone_analysis_results r JOIN phone_analysis_runs u ON u.id = r.run_id WHERE "
        "r.id = CAST(:i AS uuid) AND r.case_id = CAST(:c AS uuid)"), {"i": str(rid), "c": str(case_id)}).first()
    if head is None:
        raise LookupError("That analysis result is not in this case.")
    records = [str(r[0]) for r in conn.execute(text(
        "SELECT DISTINCT record_uid FROM phone_analysis_result_records WHERE result_id = CAST(:i AS uuid) AND "
        "record_uid IS NOT NULL ORDER BY 1"), {"i": str(rid)})]
    title = TITLES.get(head.approach, head.approach.replace("_", " "))
    return records, "The records behind a result of “%s” (%s)" % (title, head.kind.replace("_", " "))


def _check_records(conn, case_id, ref) -> tuple:
    from services.pattern_of_life import claims, evaluation
    eid = ref.get("evaluation_id")
    try:
        ev = evaluation.read(conn, case_id, eid)
    except claims.ClaimError as exc:
        raise LookupError(str(exc))
    records = []
    for it in ev.get("items") or []:
        if it.get("record_uid"):
            records.append(str(it["record_uid"]))
        if it.get("ref_kind") == "event_group":
            cursor = 0
            while cursor is not None:
                page = evaluation.group_events(conn, case_id, eid, it["ordinal"], cursor)
                records += [str(e["record_uid"]) for e in page.get("items") or [] if e.get("record_uid")]
                cursor = page.get("next_cursor")
    return sorted(set(records)), "The records of a statement check"


def _window_records(conn, case_id, ref) -> tuple:
    try:
        a = datetime.fromisoformat(str(ref.get("start")).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(ref.get("end")).replace("Z", "+00:00"))
    except ValueError:
        raise SourceExportError("A window export needs its start and end.")
    if a.tzinfo is None or b.tzinfo is None or b <= a:
        raise SourceExportError("A window export needs a start before its end, each with a time zone.")
    if (b - a).total_seconds() > MAX_WINDOW_HOURS * 3600:
        raise SourceExportError("A window export covers at most 7 days; choose a shorter window.")
    exts = [str(e) for e in ref.get("extraction_ids") or []]
    records = [str(r[0]) for r in conn.execute(text(
        "SELECT DISTINCT ev.record_uid FROM pv_comm_event ev JOIN phone_extractions e ON e.id = ev.extraction_id AND "
        "e.standing = 'active' WHERE ev.case_id = CAST(:c AS uuid) AND ev.sort_instant >= :a AND ev.sort_instant < :b"
        + (" AND ev.extraction_id::text = ANY(:x)" if exts else "") + " ORDER BY 1"),
        {"c": str(case_id), "a": a, "b": b, "x": exts})]
    return records, "Every message and call on the phones from %s to %s UTC" % (
        a.strftime("%Y-%m-%d %H:%M"), b.strftime("%Y-%m-%d %H:%M"))


def freeze_source(db, case_id, source, ref, user) -> dict:
    """``{selection_id, filter, collected, events, words, sentence}`` as ``entry_export.freeze_entry``."""
    if source not in SOURCES:
        raise SourceExportError("Exporting a %s this way is not built." % source.replace("_", " "))
    conn = db.connection()
    reader = {"analysis_result": _result_records, "statement_check": _check_records,
              "incident_window": _window_records}[source]
    records, words = reader(conn, case_id, ref or {})
    comm = {str(r[0]) for r in conn.execute(text(
        "SELECT DISTINCT record_uid FROM pv_comm_event WHERE case_id = CAST(:c AS uuid) AND record_uid::text = "
        "ANY(:r)"), {"c": str(case_id), "r": records})} if records else set()
    left = len(records) - len(comm)
    sentence = None
    if left:
        sentence = "%s behind it %s not a message or call and %s not in the export; open them on the screen." % (
            "1 record" if left == 1 else "%s records" % format(left, ","), "is" if left == 1 else "are",
            "is" if left == 1 else "are")
    if not comm:
        raise SourceExportError(sentence or "There are no messages or calls to export here.")
    sid, filter_body, events = store_selection(db, str(case_id), sorted(comm), words, user)
    db.commit()
    return {"selection_id": str(sid), "filter": filter_body, "collected": len(comm), "events": events,
            "words": words, "sentence": sentence}
