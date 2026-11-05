"""Export a finding, theory or note's phone records (07 XF-7, CO-12; 6.4 item 14 source ``finding``).

The entry's phone links are gathered into one frozen ``phone_selection`` of exactly the records collected: each
``phone_record`` link, every member of a linked ``phone_selection`` and every record of a linked ``phone_thread``.
The export then draws that selection with every copy kept (each collected copy is its own record), so the export's
total is the collected count. A link that is not a message, call or other communication record (a person, a phone,
a file, a kept result, or anything not from the phones) is not in the export and is counted by kind in the sentence;
a linked selection or thread on a replaced report is refused with the reason, never dropped silently.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from postgres import link_types

KIND_WORDS = {
    "phone_identity": ("person on the phones", "people on the phones"),
    "phone_extraction": ("phone", "phones"),
    "phone_file": ("file from a phone", "files from the phones"),
    "phone_view": ("saved view", "saved views"),
    "phone_analysis": ("kept result", "kept results"),
    "statement_check": ("statement check", "statement checks"),
}


class EntryExportError(ValueError):
    pass


def _plural(n: int, words: tuple[str, str]) -> str:
    return "%s %s" % (format(n, ","), words[0] if n == 1 else words[1])


def gather(db, case_id, entry_id) -> dict:
    """The records an entry collects, and what of it is not exportable: ``{entry, records, not_exported, replaced}``.
    Reads only."""
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    case = uuid.UUID(str(case_id))
    entry = db.get(WorkspaceEntry, uuid.UUID(str(entry_id)))
    if entry is None or entry.case_id != case or entry.deleted_at is not None:
        raise LookupError("This entry is not in this case.")
    links = db.query(WorkspaceEntryLink).filter(WorkspaceEntryLink.entry_id == entry.id).order_by(
        WorkspaceEntryLink.created_at, WorkspaceEntryLink.id).all()
    wanted: list[str] = []
    threads: list[str] = []
    not_exported: dict[str, int] = {}
    replaced = 0
    for link in links:
        kind = link.target_type
        if kind == "phone_record":
            wanted.append(str(link.target_id).lower())
        elif kind in ("phone_selection", "phone_thread"):
            try:
                target = link_types.resolve_phone_target(db, case, kind, link.target_id)
            except link_types.PhoneLinkUnavailable:
                raise
            except link_types.LinkTargetError:
                replaced += 1
                continue
            if kind == "phone_selection":
                wanted.extend(str(m).lower() for m in target.members)
            else:
                threads.append(str(link.target_id))
        else:
            not_exported[kind] = not_exported.get(kind, 0) + 1
    if threads:
        wanted.extend(str(r) for r in db.execute(text(
            "SELECT record_uid FROM pv_comm_event WHERE case_id = :c AND thread_key = ANY(:t) "
            "ORDER BY sort_instant NULLS LAST, event_uid, record_uid"), {"c": case, "t": threads}).scalars())
    records, split = split_records(db, case, wanted)
    for kind, n in split.items():
        not_exported[kind] = not_exported.get(kind, 0) + n
    return {"entry": entry, "records": records, "not_exported": not_exported, "replaced": replaced}



def split_records(db, case, wanted) -> tuple:
    """``(records, not_exported)``: the record uids of ``wanted`` (in order, each once) that are messages, calls or
    other communications of the case's read views, and by kind the count of the others: records of a phone report
    since replaced (``phone_record_replaced``) and records that are not a communication
    (``phone_record_not_communication``). Reads only."""
    not_exported: dict[str, int] = {}
    case = uuid.UUID(str(case))
    ordered = list(dict.fromkeys(str(w).lower() for w in wanted))
    found = set()
    if ordered:
        found = {str(r) for r in db.execute(text(
            "SELECT record_uid::text FROM pv_comm_event WHERE case_id = :c AND record_uid::text = ANY(:r)"),
            {"c": case, "r": ordered}).scalars()}
    records = [r for r in ordered if r in found]
    missing = [r for r in ordered if r not in found]
    if missing:
        # a record of a report since replaced is still in the raw tables but not in the case's read views
        stale = {str(r) for r in db.execute(text(
            "SELECT s.record_uid::text FROM phone_record_summaries s JOIN phone_extractions e ON e.id = "
            "s.extraction_id WHERE s.case_id = :c AND e.standing <> 'active' AND s.record_uid::text = ANY(:r)"),
            {"c": case, "r": missing}).scalars()}
        if stale:
            not_exported["phone_record_replaced"] = len(stale)
        if len(missing) > len(stale):
            not_exported["phone_record_not_communication"] = len(missing) - len(stale)
    return records, not_exported

def sentence(g: dict) -> str | None:
    parts = []
    for kind, n in sorted(g["not_exported"].items()):
        if kind == "phone_record_replaced":
            parts.append(_plural(n, ("linked record on a phone report that was replaced", "linked records on phone "
                                                                                       "reports that were replaced")))
        elif kind == "phone_record_not_communication":
            parts.append(_plural(n, ("linked phone record that is not a message or call", "linked phone records that "
                                                                                        "are not messages or calls")))
        elif kind in KIND_WORDS:
            parts.append(_plural(n, KIND_WORDS[kind]))
        else:
            parts.append(_plural(n, ("other linked item", "other linked items")))
    notes = []
    if parts:
        notes.append("Not in this export: %s." % "; ".join(parts))
    if g["replaced"]:
        notes.append("%s on a phone report that was replaced %s not exported; collect %s again on the report the "
                     "case stands on." % (_plural(g["replaced"], ("linked selection or conversation",
                                                                   "linked selections or conversations")),
                                          "is" if g["replaced"] == 1 else "are",
                                          "it" if g["replaced"] == 1 else "them"))
    return " ".join(notes) or None


def freeze_entry(db, case_id, entry_id, user) -> dict:
    """Freeze the entry's collected records as one selection and return the filter the export draws:
    ``{selection_id, filter, collected, events, words, sentence}``."""
    g = gather(db, case_id, entry_id)
    if not g["records"]:
        raise EntryExportError(sentence(g) or "This entry has no messages or calls from the phones to export.")
    entry = g["entry"]
    words = "The phone records of %s “%s”" % (entry.entry_type, (entry.title or "Untitled").strip())
    sid, filter_body, events = store_selection(db, str(entry.case_id), g["records"], words, user,
                                               collected_from={"container": "entry", "id": str(entry.id)})
    db.commit()
    return {"selection_id": str(sid), "filter": filter_body, "collected": len(g["records"]),
            "events": events, "words": words, "sentence": sentence(g)}


def store_selection(db, case, records, words, user, collected_from=None) -> tuple:
    """Freeze ``records`` (record uids) as one ``phone_selection`` of the case, every copy kept, with the mapping
    versions of the phones they come from: ``(selection_id, filter, events)``. ``collected_from`` names the finding or
    dossier they were gathered from, so the export carries the state of its links. The caller commits."""
    conn = db.connection()
    rows = conn.execute(text(
        "SELECT count(DISTINCT event_uid) AS events, array_agg(DISTINCT extraction_id::text) AS phones FROM "
        "pv_comm_event WHERE case_id = CAST(:c AS uuid) AND record_uid::text = ANY(:r)"),
        {"c": case, "r": list(records)}).one()
    phones = sorted(rows.phones or [])
    versions = [dict(r._mapping) for r in conn.execute(text(
        "SELECT st.extraction_id::text AS extraction_id, st.generation, st.mapping_set_id::text AS mapping_set_id, "
        "st.interpreter_version FROM phone_interpretation_state st WHERE st.extraction_id::text = ANY(:p) "
        "ORDER BY 1"), {"p": phones})]
    sid = uuid.uuid4()
    filter_body = {"case_id": case, "selection": str(sid), "collapse_copies": False}
    conn.execute(text(
        "INSERT INTO phone_selections (id, case_id, filter, words, record_uids, record_count, event_count, "
        "mapping_versions, created_by_user_id, collected_from) VALUES (:i, :c, CAST(:f AS jsonb), :w, :r, :n, :e, "
        "CAST(:v AS jsonb), :u, CAST(:o AS jsonb))"),
        {"i": sid, "c": case, "f": json.dumps(filter_body), "w": words, "r": list(records), "n": len(records),
         "e": int(rows.events), "v": json.dumps({"phones": versions}), "u": getattr(user, "id", None),
         "o": json.dumps(collected_from) if collected_from else None})
    return sid, filter_body, int(rows.events)
