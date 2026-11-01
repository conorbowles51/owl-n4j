"""Time storage (01 section 9, unit 1.6).

One ``phone_timestamps`` row per ``value[type=TimeStamp]`` in a record, per ``file/accessInfo/timestamp``, and per
``metadata/item`` in the skeleton or a file body whose name ends in ``Time``, ``Date`` or ``DateTime``. The original
text and ``formattedTimestamp`` are always kept. A value written without an offset keeps its wall-clock time in
``local_wall_time`` with a NULL instant: flagged, never guessed (decision D17).

The device zone comes only from the device's own setting (metadata item ``Time zone settings (ID)``) or a recorded
decision; the examiner's display zone is stored as the examiner's, in ``flags.examiner_selected_zone`` (9.3).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.phone.files import walk_body
from app.phone.store import BufferedCopy

DEVICE_ZONE_ITEM = "Time zone settings (ID)"
PRODUCER_ITEM = "UFED_PA_Version"
HEADER_FLAGS = ("examiner_selected_zone", "device_zone_as_written", "device_zone_not_a_zone_name", "device_zone_conflict",
                "device_zone_not_stated")

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?$")
_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d{2}):(\d{2}) ?(AM|PM)"
                 r"(?: ?([+-]\d{2}:\d{2})| ?\(UTC([+-]\d{1,2})(?::(\d{2}))?\))?$")
_EXIF = re.compile(r"^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})$")
_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}):(\d{2})$")


def _micro(frac):
    return int((frac or "0")[:6].ljust(6, "0"))


def _offset(text):
    if text == "Z":
        return 0
    sign = -1 if text[0] == "-" else 1
    h, m = text[1:].split(":")
    return sign * (int(h) * 60 + int(m))


def parse(text: str) -> dict:
    """``{instant, local_wall_time, original_offset_minutes, offset_state, parse_rule}`` per 01 section 9.2."""
    t = (text or "").strip()
    out = {"instant": None, "local_wall_time": None, "original_offset_minutes": None, "offset_state": "unparsed",
           "parse_rule": "unparsed"}
    try:
        m = _ISO.match(t)
        if m:
            y, mo, d, h, mi, s, frac, off = m.groups()
            wall = dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), _micro(frac))
            if off:
                minutes = _offset(off)
                out.update(instant=wall.replace(tzinfo=dt.timezone(dt.timedelta(minutes=minutes))),
                           original_offset_minutes=minutes, offset_state="explicit", parse_rule="iso8601_offset")
            else:
                out.update(local_wall_time=wall, offset_state="absent", parse_rule="iso8601_no_offset")
            return out
        m = _US.match(t)
        if m:
            mo, d, y, h, mi, s, ampm, off, utc_h, utc_m = m.groups()
            hour = int(h) % 12 + (12 if ampm == "PM" else 0)
            wall = dt.datetime(int(y), int(mo), int(d), hour, int(mi), int(s))
            if off or utc_h:
                if off:
                    minutes = _offset(off)
                    rule = "us_ampm_offset"
                else:
                    sign = -1 if utc_h.startswith("-") else 1
                    minutes = sign * (abs(int(utc_h)) * 60 + int(utc_m or 0))
                    rule = "us_ampm_utc_label"
                out.update(instant=wall.replace(tzinfo=dt.timezone(dt.timedelta(minutes=minutes))),
                           original_offset_minutes=minutes, offset_state="explicit", parse_rule=rule)
            else:
                out.update(local_wall_time=wall, offset_state="absent", parse_rule="us_ampm_no_offset")
            return out
        m = _EXIF.match(t)
        if m:
            out.update(local_wall_time=dt.datetime(*map(int, m.groups())), offset_state="absent", parse_rule="exif")
            return out
        m = _SLASH.match(t)
        if m:
            a, b, y, h, mi, s = map(int, m.groups())
            out["offset_state"] = "absent"
            if a <= 12 and b <= 12:
                out["parse_rule"] = "slash_24h_ambiguous"  # day and month order cannot be told: no wall time
            else:
                mo, d = (a, b) if b > 12 else (b, a)
                out.update(local_wall_time=dt.datetime(y, mo, d, h, mi, s), parse_rule="slash_24h_no_offset")
            return out
    except ValueError:  # a matching shape with an impossible date
        pass
    return out


def _is_time_item(name):
    return bool(name) and (name.endswith("Time") or name.endswith("Date") or name.endswith("DateTime"))


def rows_for_record(body):
    model_type = (body[1] or {}).get("type")
    parents = {}
    for p, el in walk_body(body):
        for i, c in enumerate(el[3] or ()):
            if isinstance(c, list) and c and c[0][:1] != "@":
                parents[(p + "." if p else "") + str(i)] = el
        if el[0] == "value" and (el[1] or {}).get("type") == "TimeStamp" and el[2] is not None:
            field = parents.get(p)
            yield (p, model_type, ((field[1] or {}).get("name") if field else None), "TimeStamp", el[2],
                   (el[1] or {}).get("formattedTimestamp"))


def rows_for_items(body, parent_tags=("metadata",)):
    """accessInfo timestamps and time-named metadata items in a file body or the skeleton."""
    parents = {}
    for p, el in walk_body(body):
        for i, c in enumerate(el[3] or ()):
            if isinstance(c, list) and c and c[0][:1] != "@":
                parents[(p + "." if p else "") + str(i)] = el
        a = el[1] or {}
        parent = parents.get(p)
        if el[2] is None:
            continue
        if el[0] == "timestamp" and parent is not None and parent[0] == "accessInfo":
            yield p, None, a.get("name"), "accessInfo", el[2], a.get("formattedTimestamp")
        elif el[0] == "item" and parent is not None and parent[0] in parent_tags and _is_time_item(a.get("name")):
            yield p, None, a.get("name"), "metadata_item", el[2], a.get("formattedTimestamp")


def _row(ext, doc, kind, ordinal, r):
    p, model_type, field, vtype, text, formatted = r
    v = parse(text)
    return (ext, doc, kind, ordinal, p, model_type, (field or None) and field[:256], vtype, text, formatted,
            v["instant"], v["local_wall_time"], v["original_offset_minutes"], v["offset_state"], v["parse_rule"])


COLUMNS = ("extraction_id, document_index, owner_kind, owner_ordinal, body_path, model_type, field_name, value_type, "
           "original_text, formatted_text, instant, local_wall_time, original_offset_minutes, offset_state, parse_rule")


def store_timestamps(conn, ctx, reporter=None) -> dict:
    ext = ctx["extraction_id"]
    with conn.transaction():
        with conn.cursor() as c:
            c.execute("DELETE FROM phone_timestamps WHERE extraction_id = %s", (ext,))
        cp = BufferedCopy(conn, "COPY phone_timestamps (%s) FROM STDIN" % COLUMNS)
        n = 0
        for table, kind, fn in (("phone_records", "record", rows_for_record),
                                ("phone_files", "file", rows_for_items)):
            cur = conn.cursor(name="ts_" + kind)
            cur.itersize = 2000
            cur.execute("SELECT document_index, ordinal, body FROM %s WHERE extraction_id = %%s "
                        "ORDER BY document_index, ordinal" % table, (ext,))
            while True:
                batch = cur.fetchmany(2000)
                if not batch:
                    break
                for doc, ordinal, body in batch:
                    for r in fn(body):
                        cp.write_row(_row(ext, doc, kind, ordinal, r))
                        n += 1
                cp.flush()
            cur.close()
        with conn.cursor() as c:
            c.execute("SELECT document_index, skeleton FROM phone_extraction_documents WHERE extraction_id = %s "
                      "AND skeleton IS NOT NULL ORDER BY document_index", (ext,))
            skeletons = c.fetchall()
        for doc, sk in skeletons:
            for r in rows_for_items(sk):
                cp.write_row(_row(ext, doc, "skeleton", 0, r))
                n += 1
        cp.flush()
    header = extraction_header(skeletons)
    with conn.transaction():
        with conn.cursor() as c:
            c.execute("UPDATE phone_extractions SET device_zone = %s, device_zone_source = %s, report_version = %s, "
                      "producer_version = %s, extraction_type = %s, flags = (flags - %s::text[]) || %s::jsonb WHERE id = %s",
                      (header["device_zone"], header["device_zone_source"], header["report_version"],
                       header["producer_version"], header["extraction_type"], list(HEADER_FLAGS), json.dumps(header["flags"]),
                       ext))
            c.execute("SELECT owner_kind, value_type, offset_state, count(*) FROM phone_timestamps "
                      "WHERE extraction_id = %s GROUP BY 1, 2, 3", (ext,))
            counts = {"%s/%s/%s" % r[:3]: r[3] for r in c.fetchall()}
    return {"rows": n, "counts": counts, "device_zone": header["device_zone"],
            "device_zone_source": header["device_zone_source"]}


def _valid_zone(name):
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def extraction_header(skeletons) -> dict:
    """Report version, producer, extraction type, the device zone (device setting only) and the examiner's zone."""
    out = {"report_version": None, "producer_version": None, "extraction_type": None, "device_zone": None,
           "device_zone_source": None, "flags": {}}
    device_zones = []
    for _, sk in skeletons:
        if sk[0] == "project":
            a = sk[1] or {}
            out["report_version"] = out["report_version"] or (a.get("reportVersion") or None)
            out["extraction_type"] = out["extraction_type"] or (a.get("extractionType") or None)
        for p, el in walk_body(sk):
            a = el[1] or {}
            if el[0] == "item" and a.get("name") == PRODUCER_ITEM and el[2] and not out["producer_version"]:
                out["producer_version"] = el[2].strip()[:64]
            elif el[0] == "item" and a.get("name") == DEVICE_ZONE_ITEM and el[2] and el[2].strip():
                device_zones.append(el[2].strip())
            elif el[0] == "timeZoneConfigurations":
                sel = (a.get("selectedTimeZone") or "").lstrip("_")
                out["flags"]["examiner_selected_zone"] = {
                    "zone": sel if sel and _valid_zone(sel) else None, "as_written": a.get("selectedTimeZone"),
                    "enableAutomaticallyConvertToUTC": a.get("enableAutomaticallyConvertToUTC"),
                    "enableDaylightSavings": a.get("enableDaylightSavings"),
                    "meaning": "The examiner's display zone in the analysis software, not the phone's setting."}
    distinct = sorted(set(device_zones))
    if len(distinct) == 1:
        written = distinct[0]
        # the setting is written like the examiner's zone, an IANA name behind '_' (decision D27)
        zone = written.lstrip("_") if _valid_zone(written.lstrip("_")) else written
        out["device_zone"] = zone[:64]
        out["device_zone_source"] = "device_metadata"
        out["flags"]["device_zone_as_written"] = written
        if not _valid_zone(zone):
            out["flags"]["device_zone_not_a_zone_name"] = True
    elif len(distinct) > 1:
        out["flags"]["device_zone_conflict"] = distinct  # never picked silently; a decision settles it
    if not distinct:
        out["flags"]["device_zone_not_stated"] = True
    return out
