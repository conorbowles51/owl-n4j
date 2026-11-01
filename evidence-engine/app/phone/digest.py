"""Row digest of one extraction (01 units 2.2 and 2.4): what a resumed or killed-and-resumed capture must reproduce.

One SHA-256 per table over every stored row in key order, as PostgreSQL renders it. Left out: the extraction's own
id and what is derived from it (``file_uid``), and wall-clock columns (``verified_at``, ``ran_at``, the reconciliation
row id). Of the reconciliation rows, the latest per document. Everything else is in, so two captures of the same report are equal only when every row is.
"""
from __future__ import annotations

import hashlib

# table -> (columns in the digest, order). Each list names every column except the excluded ones above.
TABLES = {
    "phone_extraction_documents": ("document_index, path, role, size_bytes, sha256, md5, root_element, parse_state, "
                                   "truncation, skeleton, source_counts, capture_cursor", "document_index"),
    "phone_records": ("document_index, ordinal, parent_ordinal, top_ordinal, depth, model_type, source_model_id, "
                      "deleted_state, is_partial, body", "document_index, ordinal"),
    "phone_files": ("document_index, ordinal, parent_ordinal, source_file_id, local_path, declared_size, declared_md5, "
                    "declared_sha256, tags, is_partial, body, disk_relpath, disk_size, disk_md5, disk_sha256, outcome",
                    "document_index, ordinal"),
    "phone_container_entries": ("relpath, size_bytes, sha256, md5", "relpath"),
    "phone_file_references": ("document_index, record_ordinal, body_path, mechanism, reference_text, "
                              "file_document_index, file_ordinal, container_relpath, resolution, ambiguous",
                              "document_index, record_ordinal, body_path, mechanism"),
    "phone_timestamps": ("document_index, owner_kind, owner_ordinal, body_path, model_type, field_name, value_type, "
                         "original_text, formatted_text, instant, local_wall_time, original_offset_minutes, "
                         "offset_state, parse_rule", "document_index, owner_kind, owner_ordinal, body_path"),
    "phone_extra_infos": ("document_index, ordinal, source_id, info_type, is_partial, body", "document_index, ordinal"),
    "phone_extra_info_nodes": ("document_index, extra_ordinal, body_path, node_id, node_name, node_path, table_name, "
                               "node_offset, node_size, file_document_index, file_ordinal, resolution",
                               "document_index, extra_ordinal, body_path"),
}
# A resume that re-runs the comparison adds a row; the latest per document is the result (``reconciliation_runs``
# gives the count).
RECONCILIATION_COLUMNS = ("document_index, counter_version, result, source_totals, captured_totals, differences, "
                          "difference_count")
# The extraction row itself: what the capture decided, not when or under which id.
EXTRACTION_COLUMNS = ("report_set_sha256, form, capture_state, report_version, producer_version, extraction_type, "
                      "device_zone, device_zone_source, flags - 'device_keys' - 'possible_same_device', record_count, "
                      "file_count, capture_code_version")


def extraction_digest(conn, extraction_id) -> dict:
    """{table: {"rows": n, "sha256": hex}} plus the extraction row. Streams; never holds a table in memory."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("SELECT row(%s)::text FROM phone_extractions WHERE id = %%s" % EXTRACTION_COLUMNS, (extraction_id,))
        row = cur.fetchone()
        out["phone_extractions"] = {"rows": 1 if row else 0,
                                    "sha256": hashlib.sha256((row[0] if row else "").encode()).hexdigest()}
    for table, (columns, order) in TABLES.items():
        h, n = hashlib.sha256(), 0
        with conn.transaction():
            cur = conn.cursor(name="digest_" + table)
            cur.itersize = 5000
            cur.execute("SELECT row(%s)::text FROM %s WHERE extraction_id = %%s ORDER BY %s" % (columns, table, order),
                        (extraction_id,))
            for (text,) in cur:
                h.update(text.encode())
                h.update(b"\n")
                n += 1
            cur.close()
        out[table] = {"rows": n, "sha256": h.hexdigest()}
    with conn.cursor() as cur:
        cur.execute("SELECT row(%s)::text FROM (SELECT DISTINCT ON (document_index) * FROM phone_reconciliations "
                    "WHERE extraction_id = %%s ORDER BY document_index, ran_at DESC, id) r ORDER BY document_index"
                    % RECONCILIATION_COLUMNS, (extraction_id,))
        h = hashlib.sha256()
        latest = cur.fetchall()
        for (text,) in latest:
            h.update(text.encode())
            h.update(b"\n")
    out["phone_reconciliations"] = {"rows": len(latest), "sha256": h.hexdigest()}
    return out


def reconciliation_runs(conn, extraction_id) -> int:
    """How many times the comparison ran; not part of the digest, since a resume may run it again."""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM phone_reconciliations WHERE extraction_id = %s", (extraction_id,))
        return cur.fetchone()[0]
