"""The record behind a line, and the case's phone list (docs/cellebrite/03 sections 3.6, 4.4).

``record_detail`` gives the record panel everything the report holds for one record: every field in capture order
with every value (not only the first), nested records to any depth, attributes, every time with its original text,
linked files by all three mechanisms with their verification state, the source-row statement, corrections with the
original beside the corrected value, and the record's state. A record of another case is not found (3.11: 404, so
ids do not leak existence across matters).

``phones`` is ``GET /api/phones``: one ``PhoneSummary`` per phone in the case.
"""
from __future__ import annotations

import os

from sqlalchemy import text

from services.phone import body as B
from services.phone import corrections, readings
from services.phone import time_display as T
from services.phone.labels import LabelContext

SOURCE_ROW_ABSENT = "The production does not include the app database this record was read from."
ABSENCE = {
    "no_reference": "This record does not refer to a file.",
    "missing": "The report refers to a file that is not in the production.",
    "mismatch": "The file in the production does not match the hash in the report.",
    "no_hash": "The report gave no hash for this file, so it could not be checked.",
    "not_interpreted": "Captured, not yet interpreted.",
}
VERIFICATION_WORDS = {
    "missing": "File missing from production", "no_local_path": "No file path in report",
    "empty_placeholder": "Empty placeholder in production", "size_mismatch": "File size differs from report",
    "mismatch": "File does not match its hash", "no_hash": "File not checked", "match": None,
}


class NotFound(LookupError):
    pass


def _locate(conn, case_id, record_uid):
    return conn.execute(text(
        "SELECT s.extraction_id, s.document_index, s.ordinal, s.model_type, s.deleted_state, s.decoding_confidence, "
        "s.source_index, s.interpretation_level, s.parent_record_uid, s.root_record_uid, s.title FROM "
        "phone_record_summaries s JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND "
        "st.generation = s.generation JOIN phone_extractions e ON e.id = s.extraction_id AND e.standing = 'active' "
        "WHERE s.record_uid = CAST(:u AS uuid) AND s.case_id = CAST(:c AS uuid)"),
        {"u": str(record_uid), "c": str(case_id)}).first()


def record_detail(conn, case_id, record_uid, zone="UTC") -> dict:
    loc = _locate(conn, case_id, record_uid)
    if loc is None:
        raise NotFound("record not in this case")
    ext = str(loc.extraction_id)
    doc = conn.execute(text(
        "SELECT path, sha256 FROM phone_extraction_documents WHERE extraction_id = :e AND document_index = :d"),
        {"e": ext, "d": loc.document_index}).first()
    label = readings.phone_labels(conn, case_id).get(ext, "Phone")
    bodies = {}

    def body_of(ordinal):
        if ordinal not in bodies:
            r = conn.execute(text(
                "SELECT ordinal, model_type, source_model_id, deleted_state, body FROM phone_records WHERE "
                "extraction_id = :e AND document_index = :d AND ordinal = :o"),
                {"e": ext, "d": loc.document_index, "o": ordinal}).first()
            bodies[ordinal] = r
        return bodies[ordinal]

    times = {}
    for t in conn.execute(text(
            "SELECT record_uid, field_path, value_index, instant, original_text, offset_present, local_wall_time "
            "FROM pv_time WHERE extraction_id = :e AND (record_uid = CAST(:u AS uuid) OR record_uid IN (SELECT "
            "record_uid FROM phone_record_summaries WHERE root_record_uid = CAST(:u AS uuid) OR parent_record_uid = "
            "CAST(:u AS uuid)))"), {"e": ext, "u": str(record_uid)}):
        times[(str(t.record_uid), t.field_path, t.value_index)] = t

    from services.phone import ids

    def detail(ordinal, depth=0):
        r = body_of(ordinal)
        if r is None:
            return None
        uid = str(ids.record_uid(ext, loc.document_index, ordinal))
        fields = []
        for fv in B.fields(r.body):
            vals = []
            for v in fv.values:
                item = {"index": v.index, "type": v.type, "text": v.text, "empty": v.is_empty}
                t = times.get((uid, fv.name, v.index)) or times.get((uid, fv.body_path, v.index))
                if v.type == "TimeStamp" or t is not None:
                    item["time"] = {
                        "original_text": t.original_text if t else v.text,
                        "offset_present": bool(t.offset_present) if t else None,
                        "full": T.format_full(t.instant, zone) if t and t.instant else
                        (T.format_wall(t.local_wall_time) if t and t.local_wall_time else T.NO_TIME),
                        "instant": T.iso(t.instant) if t and t.instant else None,
                    }
                vals.append(item)
            fields.append({"name": fv.name, "kind": fv.kind, "data_type": ", ".join(fv.value_types) or None,
                           "values": vals, "attributes": fv.attrs,
                           "children": [c for c in (detail(o, depth + 1) for o in fv.children) if c],
                           "file_ordinals": fv.files})
        return {"record_uid": uid, "model_type": r.model_type, "cellebrite_id": r.source_model_id,
                "deleted_state": r.deleted_state, "attributes": B.model_attrs(r.body), "fields": fields}

    root = detail(loc.ordinal)
    files = []
    for a in conn.execute(text(
            "SELECT a.record_uid, a.mechanism, a.reference_text, a.resolved, a.ambiguous, f.file_uid, f.local_path, "
            "f.category, f.size, f.verification, f.declared_md5, f.declared_sha256, f.disk_md5, f.disk_sha256, "
            "f.declared_size, f.disk_size FROM pv_attachment_link a LEFT JOIN pv_file f ON f.file_uid = a.file_uid "
            "WHERE a.extraction_id = :e AND (a.record_uid = CAST(:u AS uuid) OR a.record_uid IN (SELECT record_uid FROM "
            "phone_record_summaries WHERE parent_record_uid = CAST(:u AS uuid) OR root_record_uid = CAST(:u AS uuid)))"),
            {"e": ext, "u": str(record_uid)}):
        if a.file_uid is None:
            absence = ABSENCE["missing"]
        elif a.verification in ("missing", "no_local_path"):
            absence = ABSENCE["missing"]
        elif a.verification == "mismatch":
            absence = ABSENCE["mismatch"]
        elif a.verification == "no_hash":
            absence = ABSENCE["no_hash"]
        else:
            absence = None
        files.append({"record_uid": str(a.record_uid), "file_uid": str(a.file_uid) if a.file_uid else None,
                      "mechanism": a.mechanism, "reference": a.reference_text, "path": a.local_path,
                      "category": a.category, "size": a.size, "verification": a.verification,
                      "badge": VERIFICATION_WORDS.get(a.verification) if a.verification else None,
                      "hashes": {"stated_md5": a.declared_md5, "stated_sha256": a.declared_sha256,
                                 "computed_md5": a.disk_md5, "computed_sha256": a.disk_sha256},
                      "sizes": {"stated": a.declared_size, "on_disk": a.disk_size}, "absence": absence})
    corr = [{"field_path": c["field_path"], "value_index": c["value_index"], "original": c["machine_text"],
             "corrected": c["corrected_text"], "current": c["current"], "is_undo": c["is_undo"],
             "reason": c["reason"], "by": c["by"], "at": c["at"]}
            for c in corrections.chain(conn, str(record_uid))]
    return {
        "record_uid": str(record_uid),
        "extraction": {"id": ext, "label": label,
                       "report_filename": os.path.basename((doc.path if doc else "").replace("\\", "/")) or None,
                       "report_sha256": doc.sha256 if doc else None},
        "model_type": loc.model_type, "cellebrite_id": root["cellebrite_id"] if root else None,
        "title": loc.title,
        "state": {"deleted_state": loc.deleted_state, "is_carved": False, "decoding_confidence": loc.decoding_confidence,
                  "source_index": loc.source_index, "interpretation_level": loc.interpretation_level},
        "fields": root["fields"] if root else [], "attributes": root["attributes"] if root else {},
        "times": [{"record_uid": k[0], "field_path": k[1], "value_index": k[2], "instant": T.iso(t.instant),
                   "full": T.format_full(t.instant, zone) if t.instant else
                   (T.format_wall(t.local_wall_time) if t.local_wall_time else T.NO_TIME),
                   "original_text": t.original_text, "offset_present": bool(t.offset_present)}
                  for k, t in sorted(times.items(), key=lambda kv: (kv[0][0] != str(record_uid), kv[0][1], kv[0][2]))],
        "files": files, "files_absence": None if files else ABSENCE["no_reference"],
        "source_row": {"available": False, "reason": SOURCE_ROW_ABSENT},
        "corrections": corr, "interpretation_level": loc.interpretation_level, "zone": zone,
    }


def record_text(detail: dict) -> str:
    """``Copy record as text`` (3.7): every field as ``name: value`` lines, nested records indented."""
    lines = ["%s %s, record id %s" % (detail["extraction"]["label"], detail["model_type"], detail["cellebrite_id"])]

    def walk(fields, depth):
        pad = "  " * depth
        for f in fields:
            vals = []
            for v in f["values"]:
                if v.get("time"):
                    vals.append("%s (in the report: %s)" % (v["time"]["full"], v["time"]["original_text"]))
                elif not v["empty"]:
                    vals.append(v["text"] or "")
            if vals:
                lines.append("%s%s: %s" % (pad, f["name"], " | ".join(vals)))
            elif f["children"]:
                lines.append("%s%s:" % (pad, f["name"]))
            for ch in f["children"]:
                lines.append("%s  %s" % (pad, ch["model_type"]))
                walk(ch["fields"], depth + 2)

    walk(detail["fields"], 0)
    return "\n".join(lines)


# ---- phones --------------------------------------------------------------------------------------------------------

def phones(conn, case_id) -> list:
    """``PhoneSummary`` for every phone in the case (4.4), active first, in capture order."""
    ctx = LabelContext(conn, case_id)
    rows = conn.execute(text(
        "SELECT x.*, (SELECT count(*) FROM pv_comm_event ev WHERE ev.extraction_id = x.extraction_id AND ev.kind = "
        "'message') AS messages, (SELECT count(*) FROM pv_comm_event ev WHERE ev.extraction_id = x.extraction_id AND "
        "ev.kind = 'call') AS calls, (SELECT count(*) FROM pv_comm_event ev WHERE ev.extraction_id = x.extraction_id "
        "AND ev.kind = 'email') AS emails, (SELECT count(*) FROM pv_location_point p WHERE p.extraction_id = "
        "x.extraction_id) AS locations, (SELECT count(*) FROM pv_file f WHERE f.extraction_id = x.extraction_id) AS "
        "files, (SELECT count(*) FROM pv_timeline_entry t WHERE t.extraction_id = x.extraction_id) AS "
        "timeline_entries, (SELECT path FROM phone_extraction_documents d WHERE d.extraction_id = x.extraction_id AND "
        "d.document_index = 0) AS report_path FROM pv_extraction x WHERE x.case_id = :c ORDER BY x.standing <> "
        "'active', x.created_at, x.extraction_id"), {"c": case_id}).fetchall()
    out = []
    for r in rows:
        ext = str(r.extraction_id)
        keys = ctx.owner_keys(ext)
        owner = ctx.label(ext, identity_key=keys[0] if keys else None, role="owner_implicit")
        device = _device(conn, ext)
        out.append({"extraction_id": ext, "label": ctx.phone_label(ext), "owner": owner, "device": device,
                    "state": r.state, "standing": r.standing, "ingest_progress": None if r.state == "ingested" else
                    _progress(conn, ext), "device_zone": r.device_zone, "device_zone_basis": r.device_zone_basis,
                    "examiner_zone": r.examiner_zone, "report_version": r.report_version, "form": r.form,
                    "report_filename": os.path.basename((r.report_path or "").replace("\\", "/")) or None,
                    "ingested_at": T.iso(r.ingested_at),
                    "counts": {"messages": int(r.messages), "calls": int(r.calls), "emails": int(r.emails),
                               "locations": int(r.locations), "files": int(r.files),
                               "timeline_entries": int(r.timeline_entries)}})
    return out


def _device(conn, ext) -> dict:
    from services.phone import identities
    try:
        items = identities.header_items(conn, ext)
    except Exception:  # pragma: no cover - a skeleton without metadata
        items = {}

    def first(*names):
        for n in names:
            v = items.get(n)
            if isinstance(v, (list, tuple)):
                v = v[0] if v else None
            if v:
                return v
        return None
    return {"manufacturer": first("DeviceInfoSelectedManufacturer", "DeviceInfoDetectedManufacturer"),
            "model": first("DeviceInfoSelectedDeviceName", "DeviceInfoDetectedModel"),
            "os": first("DeviceInfoOSType", "DeviceInfoOSVersion"),
            "extraction_start": first("DeviceInfoExtractionStartDateTime")}


def _progress(conn, ext):
    r = conn.execute(text("SELECT * FROM phone_interpretation_progress WHERE extraction_id = :e"), {"e": ext}).first()
    if r is None:
        return None
    return round(float(r.records_done) / float(r.records_total), 3) if r.records_total else None
