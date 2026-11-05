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
- ``collection``: the members of a collected selection (``selection_id``, a ``phone_selection`` held by a dossier,
  a Workspace entry or a task). When every member is a communication the export draws that selection itself, so its
  total is the collected count (E-9); otherwise the communications are frozen as one selection and the rest counted.
- ``dossier``: the phone records a dossier holds (``dossier_id``): each ``phone_record`` link, every member of a
  linked ``phone_selection`` and every record of a linked ``phone_thread``, as a finding's export gathers them. The
  dossier's other content (its other links, media, interviews and assessments) is not in a phone export; the sentence
  counts it.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from services.phone.entry_export import EntryExportError, store_selection

SOURCES = ("analysis_result", "statement_check", "incident_window", "collection", "dossier")
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


def _collection(db, case_id, ref) -> dict:
    from postgres import link_types
    from services.phone import entry_export
    sid = ref.get("selection_id")
    try:
        target = link_types.resolve_phone_target(db, case_id, "phone_selection", str(sid))
    except link_types.PhoneLinkUnavailable as exc:
        raise SourceExportError(str(exc))
    except link_types.LinkTargetError as exc:
        if "was not found" in str(exc):
            raise LookupError("That collection is not in this case.")
        raise SourceExportError(str(exc))
    records, not_exported = entry_export.split_records(db, case_id, target.members)
    return {"records": records, "members": len(dict.fromkeys(str(m).lower() for m in target.members)),
            "selection_id": str(sid), "not_exported": not_exported, "replaced": 0,
            "words": "The collection “%s”" % ((target.label or "Untitled").strip())}


def _dossier(db, case_id, ref) -> dict:
    import uuid as _uuid
    from postgres import link_types
    from services.phone import entry_export
    try:
        did, case = _uuid.UUID(str(ref.get("dossier_id"))), _uuid.UUID(str(case_id))
    except (TypeError, ValueError, AttributeError):
        raise LookupError("That dossier is not in this case.")
    head = db.execute(text("SELECT display_name FROM case_profiles WHERE id = :i AND case_id = :c"),
                      {"i": did, "c": case}).first()
    if head is None:
        raise LookupError("That dossier is not in this case.")
    wanted, threads, not_exported, replaced = [], [], {}, 0
    for kind, target_id in db.execute(text(
            "SELECT target_type, target_id FROM dossier_links WHERE dossier_id = :i AND case_id = :c "
            "ORDER BY created_at, id"), {"i": did, "c": case}).all():
        if kind == "phone_record":
            wanted.append(str(target_id).lower())
        elif kind in ("phone_selection", "phone_thread"):
            try:
                target = link_types.resolve_phone_target(db, case, kind, target_id)
            except link_types.PhoneLinkUnavailable as exc:
                raise SourceExportError(str(exc))
            except link_types.LinkTargetError:
                replaced += 1
                continue
            if kind == "phone_selection":
                wanted.extend(str(m).lower() for m in target.members)
            else:
                threads.append(str(target_id))
        else:
            k = kind if kind in entry_export.KIND_WORDS else "other"
            not_exported[k] = not_exported.get(k, 0) + 1
    if threads:
        wanted.extend(str(r) for r in db.execute(text(
            "SELECT record_uid FROM pv_comm_event WHERE case_id = :c AND thread_key = ANY(:t) "
            "ORDER BY sort_instant NULLS LAST, event_uid, record_uid"), {"c": case, "t": threads}).scalars())
    records, split = entry_export.split_records(db, case, wanted)
    for k, n in split.items():
        not_exported[k] = not_exported.get(k, 0) + n
    content = {}
    for key, table in (("media", "dossier_media"), ("interviews", "dossier_interviews"),
                       ("assessments", "dossier_assessments")):
        n = int(db.execute(text("SELECT count(*) FROM %s WHERE dossier_id = :i AND case_id = :c" % table),
                           {"i": did, "c": case}).scalar() or 0)
        if n:
            content[key] = n
    return {"records": records, "members": len(dict.fromkeys(wanted)), "selection_id": None,
            "not_exported": not_exported, "replaced": replaced, "content": content,
            "words": "The phone records of the dossier “%s”" % ((head.display_name or "Untitled").strip())}


CONTENT_WORDS = {"media": ("media file", "media files"), "interviews": ("interview", "interviews"),
                 "assessments": ("assessment", "assessments")}


def _collected_sentence(g) -> str | None:
    from services.phone import entry_export
    words = entry_export.sentence({"not_exported": {k: v for k, v in g["not_exported"].items() if k != "other"},
                                   "replaced": g["replaced"]})
    rest, n_rest = [], g["not_exported"].get("other", 0) + sum((g.get("content") or {}).values())
    if g["not_exported"].get("other"):
        n = g["not_exported"]["other"]
        rest.append(entry_export._plural(n, ("other linked item", "other linked items")))
    for key in ("media", "interviews", "assessments"):
        if (g.get("content") or {}).get(key):
            rest.append(entry_export._plural(g["content"][key], CONTENT_WORDS[key]))
    if rest:
        more = "The dossier's %s %s not in a phone export, which holds messages and calls only." % (
            "; ".join(rest), "is" if n_rest == 1 else "are")
        words = (words + " " + more) if words else more
    return words


def freeze_collected(db, case_id, source, ref, user) -> dict:
    """A collection or a dossier, as ``freeze_source`` returns, with ``members``: how many records it collects."""
    g = (_collection if source == "collection" else _dossier)(db, case_id, ref or {})
    words = _collected_sentence(g)
    if not g["records"]:
        raise SourceExportError(words or "There are no messages or calls from the phones to export here.")
    if g["selection_id"] and len(g["records"]) == g["members"]:
        # every member is a communication: the export draws the collection itself, nothing new is stored
        events = int(db.execute(text("SELECT event_count FROM phone_selections WHERE id = CAST(:i AS uuid)"),
                                {"i": g["selection_id"]}).scalar() or 0)
        sid, filter_body = g["selection_id"], {"case_id": str(case_id), "selection": g["selection_id"],
                                               "collapse_copies": False}
    else:
        # the state of the links it was gathered from travels with the export (07 CO-8)
        origin = ({"selection": g["selection_id"]} if g["selection_id"] else
                  {"container": "dossier", "id": str((ref or {}).get("dossier_id"))})
        sid, filter_body, events = store_selection(db, str(case_id), g["records"], g["words"], user,
                                                   collected_from=origin)
        db.commit()
    return {"selection_id": str(sid), "filter": filter_body, "collected": len(g["records"]),
            "members": g["members"], "events": events, "words": g["words"], "sentence": words}


def freeze_source(db, case_id, source, ref, user) -> dict:
    """``{selection_id, filter, collected, events, words, sentence}`` as ``entry_export.freeze_entry``."""
    if source not in SOURCES:
        raise SourceExportError("Exporting a %s this way is not built." % source.replace("_", " "))
    if source in ("collection", "dossier"):
        return freeze_collected(db, case_id, source, ref, user)
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
