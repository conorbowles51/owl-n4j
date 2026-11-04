"""Where a phone record was read from: its source database file and row (05 section 17.2).

A record links to a source when

(a) one of its jump targets with ``ismodel="false"`` names a tagged file tagged ``Database`` (``phone_file_references``
    rows with mechanism ``jumptarget`` resolved to a tagged file), or
(b) an ``extraInfo`` whose ``id`` is the record's (or a record nested inside it) holds a ``nodeInfo`` naming a tagged file
    (``phone_extra_info_nodes``, resolved at capture: by id, else by path, else by sub-path, decision D38).

Each source states the table, offset and size the report gives, and the file's state from the capture's check
(01 section 7.2): verified, MD5 mismatch, absent, zero bytes, size differs or not checked. A ``nodeInfo`` that names
no tagged file is listed as unresolved, never guessed.

Only the captured tables are read; nothing here opens a file (the opener is in the evidence engine,
``app/phone/source_db.py``). Everything returned is the report's statement about where a record came from, shown as
such.
"""
from __future__ import annotations

from sqlalchemy import text

SOURCE_ROW_ABSENT = "The production does not include the app database this record was read from."
NO_ROW_NAMED = "The report does not say which row this record came from."

# capture outcome (01 section 7.2) -> file state shown by the source panel
STATE_OF_OUTCOME = {
    "match": "verified",
    "mismatch": "md5_mismatch",
    "missing": "absent",
    "no_local_path": "absent",
    "empty_placeholder": "zero_bytes",
    "size_mismatch": "size_differs",
    "no_hash": "not_checked",
}
STATE_WORDS = {
    "verified": "Present in the production; its MD5 matches the report.",
    "md5_mismatch": "The file in the production does not match the MD5 in the report.",
    "absent": "The report lists this file, but it is not in the production.",
    "zero_bytes": "The file in the production is empty (zero bytes).",
    "size_differs": "The file in the production is a different size from the one the report states.",
    "not_checked": "The report gives no hash for this file, so it could not be checked.",
    "unresolved": "The report names a source that is not one of its listed files.",
}

# SQL fragment: a phone_files row aliased ``f`` is tagged Database (Tags is a comma-separated list)
IS_DATABASE = ("'Database' = ANY (SELECT btrim(t) FROM unnest(string_to_array(coalesce(f.tags, ''), ',')) t)")


def is_database(tags) -> bool:
    return "Database" in [t.strip() for t in (tags or "").split(",")]


def file_state(outcome) -> str:
    return STATE_OF_OUTCOME.get(outcome or "", "not_checked")


def _record_ordinals(conn, ext, doc, ordinal):
    """The record and every record nested inside it (an extraInfo may name a nested model)."""
    r = conn.execute(text(
        "SELECT ordinal, top_ordinal FROM phone_records WHERE extraction_id = :e AND document_index = :d "
        "AND ordinal = :o"), {"e": ext, "d": doc, "o": ordinal}).first()
    if r is None:
        return []
    if r.ordinal == r.top_ordinal:
        q = ("SELECT ordinal, source_model_id FROM phone_records WHERE extraction_id = :e AND document_index = :d "
             "AND top_ordinal = :o")
    else:
        q = ("WITH RECURSIVE sub AS (SELECT ordinal, source_model_id FROM phone_records WHERE extraction_id = :e AND "
             "document_index = :d AND ordinal = :o UNION ALL SELECT p.ordinal, p.source_model_id FROM phone_records p "
             "JOIN sub ON p.parent_ordinal = sub.ordinal WHERE p.extraction_id = :e AND p.document_index = :d) "
             "SELECT ordinal, source_model_id FROM sub")
    return conn.execute(text(q), {"e": ext, "d": doc, "o": r.top_ordinal if r.ordinal == r.top_ordinal else ordinal}
                        ).fetchall()


def _file(row) -> dict | None:
    if row.f_ordinal is None:
        return None
    state = file_state(row.f_outcome)
    return {"file_uid": str(row.f_uid), "document_index": row.f_doc, "ordinal": row.f_ordinal,
            "original_path": row.f_path, "local_path": row.f_local, "tags": row.f_tags,
            "is_database": is_database(row.f_tags), "outcome": row.f_outcome, "state": state,
            "state_words": STATE_WORDS[state], "size": row.f_size, "md5": row.f_md5, "sha256": row.f_sha256}


_FILE_COLS = ("f.file_uid AS f_uid, f.document_index AS f_doc, f.ordinal AS f_ordinal, f.body->1->>'path' AS f_path, "
              "f.local_path AS f_local, f.tags AS f_tags, f.outcome AS f_outcome, f.disk_size AS f_size, "
              "f.disk_md5 AS f_md5, f.disk_sha256 AS f_sha256")


def record_sources(conn, extraction_id, document_index, ordinal) -> list:
    """Every source of one captured record, by both mechanisms, in a stable order."""
    ext = str(extraction_id)
    recs = _record_ordinals(conn, ext, document_index, ordinal)
    if not recs:
        return []
    ids = sorted({r.source_model_id for r in recs if r.source_model_id})
    ords = sorted({r.ordinal for r in recs})
    out = []
    if ids:
        for row in conn.execute(text(
                "SELECT x.ordinal AS x_ordinal, x.source_id, x.info_type, n.body_path, n.node_id, n.node_name, "
                "n.node_path, n.table_name, n.node_offset, n.node_size, n.resolution, " + _FILE_COLS + " "
                "FROM phone_extra_infos x JOIN phone_extra_info_nodes n ON n.extraction_id = x.extraction_id AND "
                "n.document_index = x.document_index AND n.extra_ordinal = x.ordinal LEFT JOIN phone_files f ON "
                "f.extraction_id = x.extraction_id AND f.document_index = n.file_document_index AND f.ordinal = "
                "n.file_ordinal WHERE x.extraction_id = :e AND x.document_index = :d AND x.source_id = ANY(:ids) "
                "ORDER BY x.ordinal, n.body_path"), {"e": ext, "d": document_index, "ids": ids}):
            f = _file(row)
            out.append({
                "mechanism": "extra_info", "resolution": row.resolution,
                "extra_info": {"ordinal": row.x_ordinal, "type": row.info_type, "id": row.source_id},
                "node": {"id": row.node_id, "name": row.node_name, "path": row.node_path},
                "table_name": row.table_name, "offset": row.node_offset, "size": row.node_size,
                "file": f, "state": f["state"] if f else "unresolved",
                "state_words": f["state_words"] if f else STATE_WORDS["unresolved"]})
    for row in conn.execute(text(
            "SELECT fr.record_ordinal, fr.body_path, fr.reference_text, " + _FILE_COLS + " FROM phone_file_references fr "
            "JOIN phone_files f ON f.extraction_id = fr.extraction_id AND f.document_index = fr.file_document_index AND "
            "f.ordinal = fr.file_ordinal WHERE fr.extraction_id = :e AND fr.document_index = :d AND fr.record_ordinal = "
            "ANY(:o) AND fr.mechanism = 'jumptarget' AND fr.resolution = 'tagged_file' AND " + IS_DATABASE + " "
            "ORDER BY fr.record_ordinal, fr.body_path"), {"e": ext, "d": document_index, "o": ords}):
        f = _file(row)
        out.append({"mechanism": "jump_target", "resolution": "tagged_file",
                    "extra_info": None, "node": {"id": row.reference_text, "name": None, "path": None},
                    "table_name": None, "offset": None, "size": None, "file": f, "state": f["state"],
                    "state_words": f["state_words"]})
    return out


def source_row(sources: list) -> dict:
    """What the record panel's source line says (03 section 3.6 point 6), from the record's sources."""
    db = [s for s in sources if s["file"] and s["file"]["is_database"]]
    ok = [s for s in db if s["state"] == "verified"]
    if ok:
        # the offset is a byte position in the file and names the row by itself (05 section 19); a table is optional
        named = [s for s in ok if s["offset"] not in (None, "")]
        first = (named or ok)[0]
        return {"available": True, "row_named": bool(named), "reason": None if named else NO_ROW_NAMED,
                "source_index": next(i for i, s in enumerate(sources) if s is first),
                "original_path": first["file"]["original_path"],
                "file_uid": first["file"]["file_uid"], "table_name": first["table_name"], "offset": first["offset"],
                "verified_database_files": len({s["file"]["file_uid"] for s in ok})}
    if db:
        bad = [{"file_uid": s["file"]["file_uid"], "original_path": s["file"]["original_path"],
                "state": s["state"], "state_words": s["state_words"]} for s in db]
        seen, files = set(), []
        for b in bad:
            if b["file_uid"] not in seen:
                seen.add(b["file_uid"])
                files.append(b)
        return {"available": False, "row_named": False, "reason": _unavailable_words(files), "files": files}
    return {"available": False, "row_named": False, "reason": SOURCE_ROW_ABSENT, "files": []}


def _unavailable_words(files) -> str:
    kinds = sorted({f["state"] for f in files})
    words = {"absent": "not in the production", "md5_mismatch": "does not match its MD5 in the report",
             "zero_bytes": "empty (zero bytes)", "size_differs": "a different size from the report's",
             "not_checked": "not checked (the report gives no hash)"}
    n = len(files)
    lead = "The app database this record was read from" if n == 1 else (
        "The %d app databases this record was read from" % n)
    return "%s: %s." % (lead, "; ".join("%s %s" % ("is" if n == 1 else "%d" % sum(f["state"] == k for f in files),
                                                     words.get(k, k)) for k in kinds))


def record_count(conn, extraction_id) -> dict:
    """Top-level records reaching a present, verified Database file (the 05 section 17.2 gate), by mechanism.
    Uses the same definitions as ``record_sources``: a record reaches a source through its own id or the id of a
    record nested inside it."""
    ext = str(extraction_id)
    q = ("WITH ok AS (SELECT f.document_index, f.ordinal FROM phone_files f WHERE f.extraction_id = :e AND "
         "f.outcome = 'match' AND " + IS_DATABASE + "), "
         "ei AS (SELECT DISTINCT x.document_index, x.source_id, n.resolution FROM phone_extra_info_nodes n JOIN ok ON "
         "ok.document_index = n.file_document_index AND ok.ordinal = n.file_ordinal JOIN phone_extra_infos x ON "
         "x.extraction_id = n.extraction_id AND x.document_index = n.document_index AND x.ordinal = n.extra_ordinal "
         "WHERE n.extraction_id = :e AND x.source_id IS NOT NULL), "
         "vx AS (SELECT DISTINCT r.document_index, r.top_ordinal, ei.resolution FROM ei JOIN phone_records r ON "
         "r.extraction_id = :e AND r.document_index = ei.document_index AND r.source_model_id = ei.source_id), "
         "vj AS (SELECT DISTINCT r.document_index, r.top_ordinal FROM phone_file_references fr JOIN ok ON "
         "ok.document_index = fr.file_document_index AND ok.ordinal = fr.file_ordinal JOIN phone_records r ON "
         "r.extraction_id = fr.extraction_id AND r.document_index = fr.document_index AND r.ordinal = "
         "fr.record_ordinal WHERE fr.extraction_id = :e AND fr.mechanism = 'jumptarget' AND fr.resolution = "
         "'tagged_file') "
         "SELECT (SELECT count(*) FROM ok) AS files, "
         # files reached by the records themselves (A3's figure), not by extraInfo entries that are not records
         "(SELECT count(DISTINCT (n.file_document_index, n.file_ordinal)) FROM phone_extra_info_nodes n JOIN ok ON "
         "ok.document_index = n.file_document_index AND ok.ordinal = n.file_ordinal JOIN phone_extra_infos x ON "
         "x.extraction_id = n.extraction_id AND x.document_index = n.document_index AND x.ordinal = n.extra_ordinal "
         "WHERE n.extraction_id = :e AND n.resolution = 'tagged_file_id' AND EXISTS (SELECT 1 FROM phone_records r "
         "WHERE r.extraction_id = :e AND r.document_index = x.document_index AND r.source_model_id = x.source_id)) "
         "AS files_by_id, "
         "(SELECT count(DISTINCT (document_index, top_ordinal)) FROM vx WHERE resolution = 'tagged_file_id') AS by_id, "
         "(SELECT count(DISTINCT (document_index, top_ordinal)) FROM vx) AS extra_info, "
         "(SELECT count(*) FROM vj) AS jump_target, "
         "(SELECT count(*) FROM (SELECT document_index, top_ordinal FROM vx UNION SELECT document_index, top_ordinal "
         "FROM vj) u) AS either")
    r = conn.execute(text(q), {"e": ext}).first()
    return {"verified_database_files": r.files, "verified_database_files_referenced_by_id": r.files_by_id,
            "records_by_extra_info_id": r.by_id,
            "records_by_extra_info": r.extra_info, "records_by_jump_target": r.jump_target, "records": r.either}
