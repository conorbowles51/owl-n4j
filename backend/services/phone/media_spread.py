"""Media spread across phones, exact tier (docs/cellebrite/05 section 11, approach 8; unit 05-S13).

Which media files occur on more than one phone of the case, in what order each phone came to hold them, whether
each copy was sent or received, which copy may be the camera original, and where the photo says it was taken.

Rules carried here:

- **Population (11.3 step 1).** A file is considered only if it is (a) linked to a message by a resolved,
  unambiguous attachment reference, or (b) in a camera or screenshot folder (``CAMERA_DIRS``, matched on the
  file's original ``path`` attribute or its ``Local Path``), or (c) its tagged-file metadata names a camera make or
  model (``EXIFCameraMaker`` / ``EXIFCameraModel``). Everything else is left out, because system files dominate
  whole-index overlap. Files with no MD5, an empty placeholder or the MD5 of zero bytes are never grouped.
- **Exact tier (step 2).** Copies are grouped by MD5 (lower case). A group whose population copies sit on two or
  more phones is a spread item. Where two copies both carry a SHA-256 and the SHA-256 values differ, the group is
  kept (the MD5 is equal) and flagged. The perceptual tier (step 3) is not built here: it waits on its own gate.
- **Order (step 4).** Per copy and per phone, the earliest of the message time, the file-system modify time and
  the EXIF capture time that has a real instant, with the field named. A time the report wrote without an offset
  is shown as written and never placed in a zone (01 decision D17), so it does not take part in the order.
  No clock difference between phones is established (approach 2's offsets are not built), so every group says the
  order across phones is by each phone's own clock (``clock_offset_unknown``).
- **Sent and received (step 5)** come from the direction of the message that carried the copy. A copy whose
  carrying message is marked deleted, or a copy in a messaging app's media folder that no message carries, says so.
- **Camera original candidate (step 5).** A copy with a camera make or model in its EXIF, in a camera folder, whose
  EXIF capture time precedes every message time in the group. A capture time with no offset is compared by its
  widest bounds (every real offset lies between UTC-12 and UTC+14): it counts as earlier only if it is earlier
  whatever the zone, as not earlier only if it is not earlier whatever the zone; otherwise the answer is "cannot
  tell", in words.
- **Place (step 6).** EXIF GPS items as written, source "photo EXIF". 04's place model is not joined here.
- **Common file (11.5).** A hash found on more than half the case's phones (any copy, not only the population)
  carries the "common file" flag: stickers and forwarded images are common across unrelated people.

Every count is a true count; groups are paged with the total stated; the copies of one phone in one group are
listed up to ``COPIES_PER_PHONE`` with the full count stated. Every query is scoped to the case.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta, timezone

from sqlalchemy import text

from services.phone import labels as L
from services.phone import time_display as T
from services.phone.media import OUTCOME_WORDS
from services.phone.streams import case_zone

WINDOW_MAX = 100
COPIES_PER_PHONE = 20
EMPTY_MD5 = "d41d8cd98f00b204e9800998ecf8427e"  # the MD5 of zero bytes: an empty file is not media

# Reviewed list of camera and screenshot folders (11.3 step 1 (b)). Matched as a whole path component, either
# case: Android ``DCIM/Camera``, iOS ``DCIM/100APPLE``, ``Pictures/Screenshots``, ``DCIM/Screenshots``. The same
# ``dcim`` / ``camera`` components are the ones the A3 measurement (11.6, M-8a) counted; ``screenshots`` is added
# because the spec names screenshot folders.
CAMERA_DIRS = ("dcim", "camera", "screenshots")
CAMERA_RE = r"(^|/)(%s)(/|$)" % "|".join(CAMERA_DIRS)
# Reviewed list of messaging apps whose media folders hold received and sent files (11.3 step 5: "a file in a
# messaging app's media folder with no message"). Whole path component, either case.
MESSAGING_DIRS = ("whatsapp", "telegram", "signal", "viber")
MESSAGING_RE = r"(^|/)(%s)(/|$)" % "|".join(MESSAGING_DIRS)

EXIF_CAMERA_ITEMS = ("EXIFCameraMaker", "EXIFCameraModel")
EXIF_TIME_FIELD = "EXIFCaptureTime"
# file-system modify time: the metadata item 04 section 6 names, and the accessInfo timestamp of the same meaning
FS_MODIFY_FIELDS = ("CoreFileSystemFileSystemNodeModifyTime", "ModifyTime")
GPS_ITEMS = ("ExifEnumGPSLatitude", "ExifEnumGPSLongitude", "MetaDataLatitudeAndLongitude")

SOURCE_WORDS = {"message_time": "time of the message that carried it",
                "file_modified": "file modified time (file system)",
                "exif_capture": "photo capture time (EXIF)"}
REASON_WORDS = {"attachment": "carried by a message", "camera_path": "in a camera or screenshot folder",
                "exif_camera": "the photo's EXIF names a camera"}
CLOCK_WORDS = ("Times are each phone's own clock. No clock difference between these phones has been established, "
               "so the order across phones can be off by any such difference.")
COMMON_WORDS = ("Common file: the same file is on {n} of the case's {total} phones. Stickers and forwarded images "
                "are often shared by people with no link to each other.")
SHA_WORDS = "The copies have the same MD5 but different SHA-256 values. They may not be the same file."
DELETED_MESSAGE_WORDS = "The message that carried this file is marked deleted on this phone; the file remains."
NO_MESSAGE_WORDS = "In a messaging app's media folder, but no message on this phone carries it."
POPULATION_WORDS = ("Only files sent or received in a message, in a camera or screenshot folder, or whose EXIF names "
                    "a camera are compared; other files on the phones (mostly system files) are left out. Copies "
                    "match only when their MD5 hashes are equal, so a picture an app re-compressed is not found "
                    "here.")
# every real UTC offset lies in [-12:00, +14:00], so a time written without an offset is within these bounds
EARLIEST_SHIFT, LATEST_SHIFT = timedelta(hours=14), timedelta(hours=12)


# The camera-folder and EXIF-camera parts of the population (11.3 step 1 (b) and (c)), written once and used by
# image search too (17.6). ``f`` is the pv_file row, ``pf`` its phone_files row; parameters :cam and :exif_cam.
CAMERA_PATH_SQL = ("(lower(replace(coalesce(pf.body -> 1 ->> 'path', ''), '\\', '/')) ~ :cam "
                   "OR lower(replace(coalesce(f.local_path, ''), '\\', '/')) ~ :cam)")
EXIF_CAMERA_SQL = ("EXISTS (SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(pf.body -> 3) = 'array' "
                   "THEN pf.body -> 3 ELSE '[]'::jsonb END) m, jsonb_array_elements(CASE WHEN jsonb_typeof(m -> 3) = "
                   "'array' THEN m -> 3 ELSE '[]'::jsonb END) it WHERE m ->> 0 = 'metadata' AND it ->> 0 = 'item' AND "
                   "it -> 1 ->> 'name' = ANY(:exif_cam) AND coalesce(it ->> 2, '') <> '')")


def _sql(only_md5: bool) -> str:
    """The population and its exact groups. ``member``: every population copy in a group spanning 2+ phones;
    ``grp``: one row per group. With ``only_md5`` the files are limited to the hashes in ``:only`` (a group is
    decided by its own hash alone, so the result for those hashes is unchanged)."""
    return """
WITH f AS (
  SELECT v.file_uid, v.extraction_id, lower(v.md5) AS md5, lower(nullif(v.sha256, '')) AS sha256, v.local_path,
         v.category, v.verification, v.size
    FROM pv_file v
   WHERE v.case_id = :c AND coalesce(v.md5, '') <> '' AND lower(v.md5) <> :empty_md5
     AND coalesce(v.verification, '') <> 'empty_placeholder' %(only)s
), held AS (
  SELECT md5, count(DISTINCT extraction_id) AS phones_with_hash FROM f GROUP BY md5
  HAVING count(DISTINCT extraction_id) >= 2
), linked AS (
  SELECT DISTINCT l.file_uid FROM pv_attachment_link l
   WHERE l.case_id = :c AND l.file_uid IS NOT NULL AND l.resolved AND NOT coalesce(l.ambiguous, false)
), pop AS (
  SELECT f.*, h.phones_with_hash, pf.document_index, pf.ordinal, pf.body -> 1 ->> 'path' AS original_path,
         (k.file_uid IS NOT NULL) AS by_attachment,
         %(camera_path)s AS by_camera_path,
         %(exif_camera)s AS by_exif
    FROM f JOIN held h ON h.md5 = f.md5
    JOIN phone_files pf ON pf.file_uid = f.file_uid
    LEFT JOIN linked k ON k.file_uid = f.file_uid
), member AS (
  SELECT * FROM pop WHERE by_attachment OR by_camera_path OR by_exif
), grp AS (
  SELECT md5, count(DISTINCT extraction_id) AS phone_count, count(*) AS copy_count,
         max(phones_with_hash) AS phones_with_hash, count(DISTINCT sha256) AS sha256_count,
         array_agg(DISTINCT extraction_id::text) AS phones,
         max(phones_with_hash) * 2 > :case_phones AS common
    FROM member GROUP BY md5 HAVING count(DISTINCT extraction_id) >= 2
)
""" % {"only": "AND lower(v.md5) = ANY(:only)" if only_md5 else "", "camera_path": CAMERA_PATH_SQL,
       "exif_camera": EXIF_CAMERA_SQL}


def _params(conn, case_id, **extra) -> dict:
    p = {"c": str(case_id), "empty_md5": EMPTY_MD5, "cam": CAMERA_RE, "exif_cam": list(EXIF_CAMERA_ITEMS),
         "case_phones": case_phone_count(conn, case_id)}
    p.update(extra)
    return p


def case_phone_count(conn, case_id) -> int:
    """The case's phones for the common-file rule: every active extraction (the phones whose files are listed)."""
    return int(conn.execute(text(
        "SELECT count(*) FROM phone_extractions WHERE case_id = :c AND standing = 'active'"), {"c": str(case_id)}
    ).scalar())


def _group_where(f: dict, p: dict) -> str:
    w = ["true"]
    if f.get("phones"):
        w.append("g.phones @> CAST(:phones AS text[])")
        p["phones"] = [str(x) for x in f["phones"]]
    common = f.get("common") or "all"
    if common == "hide":
        w.append("NOT g.common")
    elif common == "only":
        w.append("g.common")
    elif common != "all":
        raise ValueError("common must be all, hide or only")
    return " AND ".join(w)


def index(conn, case_id) -> dict:
    """Totals for the whole case: groups, copies, common-file groups, SHA-256 disagreements, groups per phone and
    per pair of phones (each pair with the number of groups both phones hold)."""
    p = _params(conn, case_id)
    base = _sql(False)
    total, copies, common, sha = conn.execute(text(
        base + "SELECT count(*), coalesce(sum(copy_count), 0), count(*) FILTER (WHERE common), "
               "count(*) FILTER (WHERE sha256_count > 1) FROM grp"), p).one()
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)

    def ph(e):
        return {"extraction_id": str(e), "label": labels.get(str(e), "A phone")}

    by_phone = [dict(ph(r[0]), groups=int(r[1])) for r in conn.execute(text(
        base + "SELECT m.extraction_id, count(DISTINCT m.md5) FROM member m JOIN grp g ON g.md5 = m.md5 "
               "GROUP BY 1 ORDER BY 2 DESC, 1"), p)]
    by_pair = [{"a": ph(r[0]), "b": ph(r[1]), "groups": int(r[2])} for r in conn.execute(text(
        base + ", gp AS (SELECT DISTINCT m.md5, m.extraction_id FROM member m JOIN grp g ON g.md5 = m.md5) "
               "SELECT a.extraction_id, b.extraction_id, count(*) FROM gp a JOIN gp b ON a.md5 = b.md5 AND "
               "a.extraction_id::text < b.extraction_id::text GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2"), p)]
    by_phone.sort(key=lambda x: (-x["groups"], x["label"]))
    by_pair.sort(key=lambda x: (-x["groups"], x["a"]["label"], x["b"]["label"]))
    return {"case_id": str(case_id), "case_phone_count": p["case_phones"], "total_groups": int(total),
            "total_copies": int(copies), "common_file_groups": int(common), "sha256_disagreement_groups": int(sha),
            "by_phone": by_phone, "by_pair": by_pair, "population_words": POPULATION_WORDS,
            "clock_words": CLOCK_WORDS, "tier": "exact"}


def window(conn, case_id, f: dict | None = None, offset: int = 0, limit: int = 50) -> dict:
    """One page of groups, most phones first, each with every phone holding it in order and its copies."""
    f = dict(f or {})
    p = _params(conn, case_id, o=max(0, int(offset)), l=max(1, min(WINDOW_MAX, int(limit))))
    where = _group_where(f, p)
    base = _sql(False)
    total = int(conn.execute(text(base + "SELECT count(*) FROM grp g WHERE " + where), p).scalar())
    rows = conn.execute(text(
        base + "SELECT g.* FROM grp g WHERE " + where +
        " ORDER BY g.phone_count DESC, g.copy_count DESC, g.md5 OFFSET :o LIMIT :l"), p).fetchall()
    items = _groups(conn, case_id, rows, p["case_phones"]) if rows else []
    return {"case_id": str(case_id), "total": total, "offset": p["o"], "limit": p["l"], "items": items,
            "clock_words": CLOCK_WORDS}


def _items(body, names) -> dict:
    """``{name: text}`` of the named metadata items of a file body (any section), first non-empty value."""
    out = {}
    if not isinstance(body, list) or len(body) < 4:
        return out
    for m in body[3] or ():
        if not (isinstance(m, list) and m and m[0] == "metadata"):
            continue
        for it in (m[3] if len(m) > 3 else None) or ():
            if isinstance(it, list) and len(it) > 2 and it[0] == "item":
                name = (it[1] or {}).get("name")
                if name in names and it[2] not in (None, "") and name not in out:
                    out[name] = it[2].strip()
    return out


def _filename(path) -> str:
    return (path or "").replace("\\", "/").rsplit("/", 1)[-1] or "File not named in the report"


def _groups(conn, case_id, grows, case_phones) -> list:
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    zone = case_zone(conn, case_id)["name"]
    md5s = [r.md5 for r in grows]
    p = _params(conn, case_id, only=md5s)
    copies = [dict(r._mapping) for r in conn.execute(text(
        _sql(True) + "SELECT m.*, pf.body FROM member m JOIN grp g ON g.md5 = m.md5 "
                     "JOIN phone_files pf ON pf.file_uid = m.file_uid "
                     "ORDER BY m.md5, m.extraction_id, m.document_index, m.ordinal"), p)]
    uids = [c["file_uid"] for c in copies]
    messages = _messages(conn, case_id, uids)
    times = _times(conn, case_id, copies)
    ctx = L.LabelContext(conn, case_id)
    lines = _lines(conn, ctx, [m for ms in messages.values() for m in ms])
    by_md5 = defaultdict(list)
    for c in copies:
        by_md5[c["md5"]].append(c)
    out = []
    for g in grows:
        out.append(_group(g, by_md5[g.md5], messages, times, lines, labels, zone, case_phones))
    return out


def _messages(conn, case_id, uids) -> dict:
    """``{file_uid: [message dict]}``: every message that carried each copy (resolved, unambiguous links), at the
    phone's current reading."""
    out = defaultdict(list)
    if not uids:
        return out
    seen = set()
    for r in conn.execute(text(
            "SELECT l.file_uid, l.extraction_id, coalesce(s.root_record_uid, l.record_uid) AS message_uid, ev.kind, "
            "ev.direction, ev.sort_instant, ev.app, ev.deleted_state AS ev_deleted, s.deleted_state AS rec_deleted "
            "FROM pv_attachment_link l "
            "JOIN phone_record_summaries s ON s.record_uid = l.record_uid "
            "JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation "
            "LEFT JOIN phone_comm_events ev ON ev.record_uid = coalesce(s.root_record_uid, l.record_uid) "
            "     AND ev.generation = s.generation "
            "WHERE l.case_id = :c AND l.file_uid = ANY(CAST(:u AS uuid[])) AND l.resolved "
            "  AND NOT coalesce(l.ambiguous, false) "
            "ORDER BY ev.sort_instant NULLS LAST, 3"), {"c": str(case_id), "u": [str(u) for u in uids]}):
        key = (str(r.file_uid), str(r.message_uid))
        if key in seen:
            continue
        seen.add(key)
        deleted = r.ev_deleted if r.kind else r.rec_deleted
        out[str(r.file_uid)].append({
            "message_record_uid": str(r.message_uid), "extraction_id": str(r.extraction_id), "kind": r.kind,
            "direction": r.direction if r.kind else None, "instant": r.sort_instant, "app": r.app,
            "deleted": bool(deleted) and deleted != "Intact", "deleted_state": deleted})
    return out


def _lines(conn, ctx, msgs) -> dict:
    """``{message_record_uid: "Sender -> Recipient"}`` with the case's labels (the same words as Conversations)."""
    uids = sorted({m["message_record_uid"] for m in msgs})
    if not uids:
        return {}
    parties = defaultdict(list)
    for p in conn.execute(text(
            "SELECT p.record_uid, p.identity_key, p.role, p.implied_role, p.name_in_record, p.identifier_raw, "
            "p.is_phone_owner, p.extraction_id FROM phone_participations p JOIN phone_interpretation_state st ON "
            "st.extraction_id = p.extraction_id AND st.generation = p.generation WHERE p.case_id = :c AND "
            "p.record_uid = ANY(CAST(:u AS uuid[])) ORDER BY p.record_uid, p.ordinal, p.participation_uid"),
            {"c": ctx.case_id, "u": uids}):
        parties[str(p.record_uid)].append(p)
    ctx.load([p.identity_key for ps in parties.values() for p in ps])
    out = {}
    for uid, ps in parties.items():
        ext = str(ps[0].extraction_id)
        senders = [p for p in ps if p.role in L.SENDER_ROLES or p.implied_role in ("sender", "caller")]
        recips = [p for p in ps if p.role in L.RECIPIENT_ROLES or p.implied_role in ("recipient", "callee")]
        others = [p for p in ps if p not in senders and p not in recips]

        def lab(p):
            return ctx.label(ext, identity_key=p.identity_key, name_in_record=p.name_in_record,
                             identifier_raw=p.identifier_raw, is_phone_owner=p.is_phone_owner, role=p.role)
        frm = lab(senders[0]) if senders else None
        to = [lab(p) for p in recips] or ([lab(p) for p in others] if not senders else [])
        out[uid] = L.line_text(frm, to)
    return out


def _times(conn, case_id, copies) -> dict:
    """``{file_uid: {"file_modified": [...], "exif_capture": [...]}}`` from the file's stored timestamps."""
    out = defaultdict(lambda: defaultdict(list))
    if not copies:
        return out
    key = {(str(c["extraction_id"]), int(c["document_index"]), int(c["ordinal"])): str(c["file_uid"]) for c in copies}
    exts, docs, ords = zip(*key)
    for r in conn.execute(text(
            "SELECT t.extraction_id, t.document_index, t.owner_ordinal, t.field_name, t.instant, t.local_wall_time, "
            "t.original_text FROM phone_timestamps t "
            "JOIN unnest(CAST(:e AS uuid[]), CAST(:d AS smallint[]), CAST(:o AS integer[])) AS k(e, d, o) "
            "  ON t.extraction_id = k.e AND t.document_index = k.d AND t.owner_ordinal = k.o "
            "JOIN phone_extractions x ON x.id = t.extraction_id AND x.case_id = :c "
            "WHERE t.owner_kind = 'file' AND t.field_name = ANY(:fields)"),
            {"c": str(case_id), "e": list(exts), "d": list(docs), "o": list(ords),
             "fields": list(FS_MODIFY_FIELDS) + [EXIF_TIME_FIELD]}):
        uid = key[(str(r.extraction_id), int(r.document_index), int(r.owner_ordinal))]
        source = "exif_capture" if r.field_name == EXIF_TIME_FIELD else "file_modified"
        out[uid][source].append({"field": r.field_name, "instant": r.instant, "wall": r.local_wall_time,
                                 "original_text": r.original_text})
    return out


def _time(source, field, instant, zone, wall=None) -> dict:
    return {"source": source, "source_words": SOURCE_WORDS[source], "field": field, "instant": T.iso(instant),
            "full": T.format_full(instant, zone) if instant is not None else T.format_wall(wall),
            "has_offset": instant is not None}


def _candidate(c, exif_times, group_msg_instants):
    """(candidate True/False/None, words) per 11.3 step 5 from captured fields only."""
    if not c["camera"]:
        return False, None
    if not c["by_camera_path"]:
        return False, None
    if not exif_times:
        return None, "The photo's EXIF names a camera but gives no capture time, so it cannot be compared."
    first_msg = min(group_msg_instants) if group_msg_instants else None
    with_instant = [t for t in exif_times if t["instant"] is not None]
    if with_instant:
        cap = min(t["instant"] for t in with_instant)
        if first_msg is None:
            return True, ("Camera original candidate: camera EXIF, in a camera folder; no message in this group "
                          "carries a time to compare against.")
        if cap < first_msg:
            return True, "Camera original candidate: taken before every message in this group carrying it."
        return False, None
    walls = [t["wall"] for t in exif_times if t["wall"] is not None]
    if not walls:
        return None, "The photo's capture time could not be read, so it cannot be compared."
    wall = min(walls)
    if first_msg is None:
        return True, ("Camera original candidate: camera EXIF, in a camera folder; no message in this group "
                      "carries a time to compare against.")
    first_wall = first_msg.astimezone(timezone.utc).replace(tzinfo=None)  # UTC wall clock of the first message
    if wall + LATEST_SHIFT < first_wall:
        return True, ("Camera original candidate: the capture time has no time zone, but it is before every "
                      "message in this group in any time zone.")
    if wall - EARLIEST_SHIFT >= first_wall:
        return False, None
    return None, ("Cannot tell: the capture time has no time zone, and it is too close to the first message in this "
                  "group to say which came first.")


def _group(g, copies, messages, times, lines, labels, zone, case_phones) -> dict:
    group_msg_instants = [m["instant"] for c in copies for m in messages.get(str(c["file_uid"]), ())
                          if m["instant"] is not None]
    phones = defaultdict(list)
    shown = []
    for c in copies:
        uid = str(c["file_uid"])
        ext = str(c["extraction_id"])
        exif = _items(c["body"], EXIF_CAMERA_ITEMS + GPS_ITEMS)
        c["camera"] = {"make": exif.get("EXIFCameraMaker"), "model": exif.get("EXIFCameraModel")} \
            if (exif.get("EXIFCameraMaker") or exif.get("EXIFCameraModel")) else None
        msgs = messages.get(uid, [])
        tlist = []
        for m in msgs:
            if m["instant"] is not None:
                tlist.append(_time("message_time", "message", m["instant"], zone))
        for src in ("file_modified", "exif_capture"):
            for t in times[uid][src] if uid in times else ():
                tlist.append(_time(src, t["field"], t["instant"], zone, t["wall"]))
        placed = [t for t in tlist if t["has_offset"]]
        earliest = min(placed, key=lambda t: t["instant"]) if placed else None
        roles = sorted({{"outgoing": "sent", "incoming": "received"}.get(m["direction"], "direction_unknown")
                        for m in msgs if m["kind"]})
        cand, cand_words = _candidate(c, times[uid]["exif_capture"] if uid in times else [], group_msg_instants)
        path = (c["original_path"] or c["local_path"] or "").replace("\\", "/").lower()
        note = None
        if msgs and all(m["deleted"] for m in msgs):
            note = DELETED_MESSAGE_WORDS
        elif not msgs and re.search(MESSAGING_RE, path):
            note = NO_MESSAGE_WORDS
        place = None
        if any(k in exif for k in GPS_ITEMS):
            place = {"latitude": exif.get("ExifEnumGPSLatitude"), "longitude": exif.get("ExifEnumGPSLongitude"),
                     "combined": exif.get("MetaDataLatitudeAndLongitude"), "source": "photo EXIF",
                     "words": "Place in the photo's EXIF, as written: %s" % (
                         exif.get("MetaDataLatitudeAndLongitude") or ", ".join(
                             x for x in (exif.get("ExifEnumGPSLatitude"), exif.get("ExifEnumGPSLongitude")) if x))}
        copy = {
            "file_uid": uid, "extraction_id": ext, "phone_label": labels.get(ext, "A phone"),
            "filename": _filename(c["local_path"] or c["original_path"]), "local_path": c["local_path"],
            "original_path": c["original_path"], "category": c["category"], "size": c["size"],
            "sha256": c["sha256"], "verification": c["verification"],
            "verification_words": OUTCOME_WORDS.get(c["verification"] or "", "Not checked"),
            "missing": c["verification"] == "missing",
            "included_because": [w for k, w in (("by_attachment", REASON_WORDS["attachment"]),
                                                ("by_camera_path", REASON_WORDS["camera_path"]),
                                                ("by_exif", REASON_WORDS["exif_camera"])) if c[k]],
            "times": sorted(tlist, key=lambda t: (not t["has_offset"], t["instant"] or "")),
            "earliest": earliest, "roles": roles,
            "messages": [{"message_record_uid": m["message_record_uid"], "kind": m["kind"],
                          "direction": m["direction"],
                          "role": {"outgoing": "sent", "incoming": "received"}.get(m["direction"],
                                                                                    "direction_unknown"),
                          "instant": T.iso(m["instant"]),
                          "full": T.format_full(m["instant"], zone) if m["instant"] is not None else T.NO_TIME,
                          "app": m["app"], "deleted": m["deleted"],
                          "line": lines.get(m["message_record_uid"])} for m in msgs],
            "note": note, "camera": c["camera"], "in_camera_folder": bool(c["by_camera_path"]),
            "camera_original_candidate": cand, "camera_original_words": cand_words, "place": place,
        }
        phones[ext].append(copy)
        shown.append(copy)
    order = []
    for ext, cs in phones.items():
        placed = [c["earliest"] for c in cs if c["earliest"]]
        earliest = min(placed, key=lambda t: t["instant"]) if placed else None
        order.append({
            "extraction_id": ext, "phone_label": labels.get(ext, "A phone"), "earliest": earliest,
            "roles": sorted({r for c in cs for r in c["roles"]}),
            "camera_original_candidate": any(c["camera_original_candidate"] is True for c in cs),
            "copy_count": len(cs), "copies_shown": min(len(cs), COPIES_PER_PHONE),
            "copies_words": (None if len(cs) <= COPIES_PER_PHONE else
                             "%d of %d copies on this phone shown; open the phone's Media to see every one."
                             % (COPIES_PER_PHONE, len(cs))),
            "copies": cs[:COPIES_PER_PHONE]})
    order.sort(key=lambda o: (o["earliest"] is None, o["earliest"]["instant"] if o["earliest"] else "",
                              o["phone_label"]))
    pos, last = 0, object()
    for o in order:
        if o["earliest"] is None:
            o["position"] = None
            continue
        if o["earliest"]["instant"] != last:
            pos += 1
            last = o["earliest"]["instant"]
        o["position"] = pos
    thumb = next((c for c in shown if not c["missing"] and (
        "image" in (c["category"] or "").lower())), None) or next((c for c in shown if not c["missing"]), None)
    first = shown[0]
    common = bool(g.common)
    return {
        "group_key": g.md5, "md5": g.md5, "phone_count": int(g.phone_count), "copy_count": int(g.copy_count),
        "phones_with_hash": int(g.phones_with_hash), "case_phone_count": int(case_phones),
        "common_file": common,
        "common_words": COMMON_WORDS.format(n=int(g.phones_with_hash), total=int(case_phones)) if common else None,
        "sha256_disagrees": int(g.sha256_count) > 1, "sha256_words": SHA_WORDS if int(g.sha256_count) > 1 else None,
        "category": first["category"], "filename": first["filename"], "size": first["size"],
        "thumbnail_file_uid": thumb["file_uid"] if thumb else None,
        "clock_offset_unknown": True, "clock_words": CLOCK_WORDS,
        "camera_original_candidates": sum(1 for c in shown if c["camera_original_candidate"] is True),
        "phones": order, "tier": "exact",
    }
