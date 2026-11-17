"""A photo or other phone file in a Corroborate selection (Media page tiles).

A file has no time or place of its own in the store: what Corroborate can read from it are the phone records it
belongs to. ``records`` gives each file of the case:

- the place in its own metadata: the ``Media Locations`` record the report tags to the file (a resolved,
  unambiguous ``tagged_file`` reference), read when the place is on the map (``pol_place_observation``);
- every message that carried it: resolved, unambiguous attachment links at the phone's current reading, the same
  links that give the file its time on the Media page.

``expand`` turns each ``media_file`` member into those phone records, each labelled with the file's name, so the
run and the preview read the photo through records they already weigh. A file with neither is refused by name,
never dropped.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text

from services.case_selections import SelectionError

MEMBER_TYPE = "media_file"


class PhotoError(SelectionError):
    """The file cannot be read for Corroborate; the message names it and says why."""


def _uuid(value: Any) -> str | None:
    import uuid
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _name(local_path: str | None) -> str:
    return (local_path or "").replace("\\", "/").rsplit("/", 1)[-1] or "A file not named in the report"


def records(db, case_id, file_uids: list[str]) -> dict[str, dict[str, Any]]:
    """``{file_uid: {"name", "places": [record uid], "messages": [record uid], "undated_links": n}}`` for the files
    of this case's active phones (``undated_links``: references by records with no dated message above them); a file
    not in the case is absent."""
    from services.phone import ids
    wanted = [u for u in (_uuid(f) for f in file_uids) if u]
    if not wanted:
        return {}
    p = {"c": str(case_id), "u": wanted}
    out: dict[str, dict[str, Any]] = {}
    for uid, local_path in db.execute(text(
            "SELECT file_uid, local_path FROM pv_file WHERE case_id = :c AND file_uid = ANY(CAST(:u AS uuid[]))"), p):
        out[str(uid)] = {"name": _name(local_path), "places": [], "messages": [], "undated_links": 0}
    if not out:
        return out
    tagged = defaultdict(list)
    for uid, ext, doc, ordinal in db.execute(text(
            "SELECT f.file_uid, fr.extraction_id, fr.document_index, fr.record_ordinal FROM pv_file f "
            "JOIN phone_file_references fr ON fr.extraction_id = f.extraction_id AND fr.file_document_index = "
            "f.document_index AND fr.file_ordinal = f.ordinal AND fr.resolution = 'tagged_file' AND NOT fr.ambiguous "
            "JOIN phone_records r ON r.extraction_id = fr.extraction_id AND r.document_index = fr.document_index AND "
            "r.ordinal = fr.record_ordinal AND r.model_type = 'Location' "
            "WHERE f.case_id = :c AND f.file_uid = ANY(CAST(:u AS uuid[])) "
            "ORDER BY fr.document_index, fr.record_ordinal"), p):
        tagged[str(uid)].append(str(ids.record_uid(ext, doc, ordinal)))
    placed = {str(r[0]) for r in db.execute(text(
        "SELECT DISTINCT record_uid FROM pol_place_observation WHERE case_id = :c AND record_uid = ANY(CAST(:r AS "
        "uuid[]))"), {"c": str(case_id), "r": [r for rs in tagged.values() for r in rs]})} if tagged else set()
    for uid, recs in tagged.items():
        out[uid]["places"] = list(dict.fromkeys(r for r in recs if r in placed))
    # The message that carried a file is the nearest dated message record above the link: the linking record itself,
    # its parent (an Attachment under an InstantMessage), then its root. On chat-style phones the root is the Chat,
    # which is not a message and has no time, so the root alone would lose the message.
    carried = defaultdict(list)
    for uid, message, at in db.execute(text(
            "SELECT l.file_uid, m.record_uid, m.sort_instant FROM pv_attachment_link l "
            "JOIN phone_record_summaries s ON s.record_uid = l.record_uid "
            "JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation "
            "LEFT JOIN LATERAL (SELECT ev.record_uid, ev.sort_instant FROM (VALUES (0, l.record_uid), "
            "  (1, s.parent_record_uid), (2, s.root_record_uid)) AS c(n, uid) JOIN phone_comm_events ev ON "
            "  ev.record_uid = c.uid AND ev.generation = s.generation WHERE ev.sort_instant IS NOT NULL "
            "  ORDER BY c.n, ev.sort_instant LIMIT 1) m ON true "
            "WHERE l.case_id = :c AND l.file_uid = ANY(CAST(:u AS uuid[])) AND l.resolved "
            "  AND NOT coalesce(l.ambiguous, false)"), p):
        if str(uid) not in out:
            continue
        if message is None:
            out[str(uid)]["undated_links"] += 1
        else:
            carried[str(uid)].append((at, str(message)))
    for uid, msgs in carried.items():
        placed_here = set(out[uid]["places"])
        out[uid]["messages"] = [m for m in dict.fromkeys(m for _, m in sorted(msgs)) if m not in placed_here]
    return out


def expand(db, case_id, members: list[dict]) -> list[dict]:
    """Each ``media_file`` member as the phone records it belongs to, in place; every other member as it was."""
    files = [str(m.get("id")) for m in members if m.get("type") == MEMBER_TYPE]
    if not files:
        return list(members)
    found = records(db, case_id, files)
    out: list[dict] = []
    for m in members:
        if m.get("type") != MEMBER_TYPE:
            out.append(m)
            continue
        uid = _uuid(m.get("id"))
        got = found.get(uid or "")
        if got is None:
            raise PhotoError(f"{m.get('label') or 'A file'} is not on a phone in this case.")
        name = m.get("label") or got["name"]
        if not got["places"] and not got["messages"]:
            carried = ("the records that refer to it have no time" if got["undated_links"] else "no message carried it")
            raise PhotoError(f"{name} names no place in its metadata and {carried}, so Corroborate has no dated "
                             "record to read from it.")
        out += [{"type": "phone_record", "id": r, "label": f"{name}: place in its metadata"} for r in got["places"]]
        out += [{"type": "phone_record", "id": r, "label": f"{name}: message that carried it"} for r in got["messages"]]
    return out
