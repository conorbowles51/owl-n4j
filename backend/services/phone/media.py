"""Media (03 section 8): the files on each phone, by phone, category and state, with the messages that carried them.

Every file of the case's active phones is listed (``pv_file``), so the grid's total equals the phone summary's file
count (M-4). A file's time is the time of the first message that carried it (``message_time``); a file no message
carried has no time (``none``) and is counted, never dropped. A file the report names but the production does not
hold (outcome ``missing``) is counted under ``missing`` and shown with the 3.6 sentence, never as a broken image
(M-2). The messages that carried a file are found by every reference mechanism, including the Attachment record's
extracted path (M-1), each with the mechanism that found it.
"""
from __future__ import annotations

import functools
import zipfile

from sqlalchemy import text

from services.phone import time_display as T

MISSING_WORDS = "The report refers to a file that is not in the production."
WINDOW_MAX = 500
OUTCOME_WORDS = {
    "match": "Intact: matches its stated hash", "mismatch": "Does not match its stated hash",
    "no_hash": "Present; no hash stated to check", "size_mismatch": "Size differs from the report",
    "empty_placeholder": "An empty placeholder in the production", "missing": MISSING_WORDS,
    "no_local_path": "The report gives no path for this file",
}
MECHANISM_WORDS = {"jump_target": "jump target", "attachment_field": "attachment field",
                   "tagged_file": "tagged file", "attachment_extracted_path": "the attachment's extracted path"}

# the time of the first message that carried each file (via every reference to it)
_CARRIED = """
SELECT l.file_uid, min(ev.sort_instant) AS first_at, count(DISTINCT coalesce(s.root_record_uid, l.record_uid)) AS messages
  FROM pv_attachment_link l
  JOIN phone_record_summaries s ON s.record_uid = l.record_uid
  LEFT JOIN phone_comm_events ev ON ev.record_uid = coalesce(s.root_record_uid, l.record_uid)
       AND ev.generation = s.generation
 WHERE l.case_id = :c AND l.file_uid IS NOT NULL AND l.resolved AND NOT coalesce(l.ambiguous, false)
 GROUP BY l.file_uid"""


# every file reference made by a thread's messages and their child records, at the current reading
_THREAD_REFS = """
SELECT l.record_uid, l.file_uid, l.resolution, l.resolved, l.reference_text, coalesce(l.ambiguous, false) AS ambiguous
  FROM pv_attachment_link l
  JOIN phone_record_summaries s ON s.record_uid = l.record_uid
  JOIN phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation
  JOIN pv_comm_event ev ON ev.record_uid = coalesce(s.root_record_uid, l.record_uid) AND ev.case_id = l.case_id
 WHERE l.case_id = :c AND ev.thread_key = :tk"""


def thread_attachments(conn, case_id, thread_key) -> dict:
    """The thread header's attachment counts (03 section 6.7): every reference to a file the thread's messages make,
    counted once per file. ``files`` are the report's files (the Media grid scoped to the thread lists exactly
    these); ``not_in_report`` are references found neither in the report nor in the production; ``in_folders_only``
    are paths found in the production's folders that the report's file list does not name; ``not_in_production``
    are files the report names that the production does not hold. References to other records (a jump target to a
    record) are not files and are not counted."""
    p = {"c": str(case_id), "tk": thread_key}
    r = conn.execute(text(
        "SELECT count(DISTINCT x.file_uid) FILTER (WHERE x.file_uid IS NOT NULL) AS files, "
        "count(DISTINCT x.reference_text) FILTER (WHERE x.resolution = 'container_entry' AND x.file_uid IS NULL) AS folders, "
        "count(DISTINCT (x.record_uid, x.reference_text)) FILTER (WHERE NOT x.resolved) AS unresolved, "
        "count(DISTINCT x.file_uid) FILTER (WHERE f.verification = 'missing') AS missing "
        "FROM (%s) x LEFT JOIN pv_file f ON f.file_uid = x.file_uid" % _THREAD_REFS), p).one()
    files, folders, unresolved, missing = (int(v or 0) for v in r)
    referenced = files + folders + unresolved
    parts = ["%s %s referenced" % ("{:,}".format(referenced), "attachment" if referenced == 1 else "attachments")]
    if unresolved:
        parts.append("%s not in the report" % "{:,}".format(unresolved))
    if folders:
        parts.append("%s only in the production's folders" % "{:,}".format(folders))
    if missing:
        parts.append("%s named in the report but not in the production" % "{:,}".format(missing))
    return {"thread_key": thread_key, "referenced": referenced, "files": files, "not_in_report": unresolved,
            "in_folders_only": folders, "not_in_production": missing, "words": ", ".join(parts)}


def with_significant(conn, case_id, f: dict) -> dict:
    """The filter with the toggle's identity keys, read once (``_where`` has no connection)."""
    if not f.get("significant_only"):
        return f
    from services.phone import significant
    return dict(f, significant_keys=significant.identity_keys(conn, case_id))


def _where(f: dict, p: dict) -> str:
    w = ["f.case_id = :c"]
    if f.get("phones"):
        w.append("f.extraction_id::text = ANY(:phones)")
        p["phones"] = [str(x) for x in f["phones"]]
    if f.get("categories"):
        w.append("coalesce(f.category, '') = ANY(:cats)")
        p["cats"] = list(f["categories"])
    if f.get("verification"):
        w.append("coalesce(f.verification, '') = ANY(:ver)")
        p["ver"] = list(f["verification"])
    if f.get("thread_key"):
        # Attachments (N) in a thread header (03 section 6.7, MD-1): the files the thread's messages carried
        w.append("f.file_uid IN (SELECT r.file_uid FROM (%s) r WHERE r.file_uid IS NOT NULL)" % _THREAD_REFS)
        p["tk"] = f["thread_key"]
    # carried by a message of one of these apps, or with one of these people (03 8.3 filter bar): the same resolved,
    # unambiguous attachment links that give a file its time
    carried = ("EXISTS (SELECT 1 FROM pv_attachment_link l2 JOIN phone_record_summaries s2 ON s2.record_uid = "
               "l2.record_uid JOIN phone_comm_events ev2 ON ev2.record_uid = coalesce(s2.root_record_uid, "
               "l2.record_uid) AND ev2.generation = s2.generation WHERE l2.case_id = :c AND l2.file_uid = f.file_uid "
               "AND l2.resolved AND NOT coalesce(l2.ambiguous, false) AND %s)")
    if f.get("apps"):
        w.append(carried % "ev2.app = ANY(:apps)")
        p["apps"] = list(f["apps"])
    if f.get("participants"):
        w.append(carried % ("EXISTS (SELECT 1 FROM phone_participations pp WHERE pp.record_uid = ev2.record_uid AND "
                            "pp.generation = ev2.generation AND pp.identity_key = ANY(:people))"))
        p["people"] = list(f["participants"])
    if f.get("significant_keys") is not None:  # the Significant toggle (07 XF-11)
        w.append(carried % ("EXISTS (SELECT 1 FROM phone_participations ps WHERE ps.record_uid = ev2.record_uid AND "
                            "ps.generation = ev2.generation AND ps.identity_key = ANY(:sig))"))
        p["sig"] = list(f["significant_keys"])
    # a file's time is its first carrying message's (``c.first_at``); a dated window leaves out files with no time,
    # and the index counts them (``outside_dates_no_time``)
    if f.get("from_instant"):
        w.append("c.first_at >= CAST(:mfrom AS timestamptz)")
        p["mfrom"] = f["from_instant"]
    if f.get("to_instant"):
        w.append("c.first_at < CAST(:mto AS timestamptz)")
        p["mto"] = f["to_instant"]
    if f.get("linked_to_message") is True:
        w.append("c.file_uid IS NOT NULL")
    elif f.get("linked_to_message") is False:
        w.append("c.file_uid IS NULL")
    return " AND ".join(w)


def _base(where):
    return ("FROM pv_file f LEFT JOIN (%s) c ON c.file_uid = f.file_uid WHERE %s" % (_CARRIED, where))


def index(conn, case_id, f: dict | None = None) -> dict:
    f, p = with_significant(conn, case_id, dict(f or {})), {"c": str(case_id)}
    base = _base(_where(f, p))
    # a file with no time was carried by no message, or only by messages that carry no time: counted apart
    total, no_time, no_message, missing = conn.execute(text(
        "SELECT count(*), count(*) FILTER (WHERE c.first_at IS NULL), count(*) FILTER (WHERE c.file_uid IS NULL), "
        "count(*) FILTER (WHERE f.verification = 'missing') " + base), p).one()
    by_cat = {r[0] or "Uncategorised": int(r[1]) for r in conn.execute(text(
        "SELECT f.category, count(*) " + base + " GROUP BY 1 ORDER BY 2 DESC, 1"), p)}
    by_ver = {r[0] or "unchecked": int(r[1]) for r in conn.execute(text(
        "SELECT f.verification, count(*) " + base + " GROUP BY 1 ORDER BY 2 DESC, 1"), p)}
    out = {"case_id": str(case_id), "total": int(total), "no_time_count": int(no_time),
           "no_message_count": int(no_message), "missing": int(missing), "by_category": by_cat, "verification": by_ver}
    if f.get("from_instant") or f.get("to_instant"):
        g = {k: v for k, v in f.items() if k not in ("from_instant", "to_instant")}
        q = {"c": str(case_id)}
        out["outside_dates_no_time"] = int(conn.execute(text(
            "SELECT count(*) " + _base(_where(g, q)) + " AND c.first_at IS NULL"), q).scalar() or 0)
    return out


def facets(conn, case_id, f: dict | None = None) -> dict:
    """The apps and the people (other than the phone's owner) whose messages carried the files in scope, each with
    its file count, for the app and participant filters (03 8.3). Every value is listed; none is cut."""
    from services.phone.graph_projection import _identity_labels
    f = with_significant(conn, case_id, {k: v for k, v in dict(f or {}).items() if k not in ("apps", "participants")})
    p = {"c": str(case_id)}
    carried = ("FROM pv_attachment_link l2 JOIN phone_record_summaries s2 ON s2.record_uid = l2.record_uid JOIN "
               "phone_comm_events ev2 ON ev2.record_uid = coalesce(s2.root_record_uid, l2.record_uid) AND "
               "ev2.generation = s2.generation JOIN (SELECT f.file_uid " + _base(_where(f, p)) + ") sc ON sc.file_uid "
               "= l2.file_uid WHERE l2.case_id = :c AND l2.resolved AND NOT coalesce(l2.ambiguous, false)")
    apps = [{"app": r[0], "files": int(r[1])} for r in conn.execute(text(
        "SELECT ev2.app, count(DISTINCT l2.file_uid) " + carried + " AND ev2.app IS NOT NULL GROUP BY 1 "
        "ORDER BY 2 DESC, 1"), p)]
    labels = _identity_labels(conn, case_id)
    people = []
    for r in conn.execute(text(
            "SELECT pp.identity_key, count(DISTINCT l2.file_uid) AS files, mode() WITHIN GROUP (ORDER BY "
            "coalesce(nullif(pp.name_in_record, ''), pp.identifier_raw)) AS seen " + carried.replace(
                " WHERE l2.case_id", " JOIN phone_participations pp ON pp.record_uid = ev2.record_uid AND "
                "pp.generation = ev2.generation WHERE l2.case_id") +
            " AND pp.identity_key IS NOT NULL AND NOT coalesce(pp.is_phone_owner, false) GROUP BY 1 "
            "ORDER BY 2 DESC, 1"), p):
        people.append({"key": r.identity_key, "label": labels.get(r.identity_key) or r.seen or r.identity_key,
                       "files": int(r.files)})
    return {"case_id": str(case_id), "apps": apps, "participants": people}


def window(conn, case_id, f: dict | None = None, offset: int = 0, limit: int = 200) -> dict:
    f, p = with_significant(conn, case_id, dict(f or {})), {"c": str(case_id), "o": max(0, int(offset)),
                                                            "l": max(1, min(WINDOW_MAX, int(limit)))}
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    zones = {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT extraction_id, device_zone FROM pv_extraction WHERE case_id = :c"), {"c": str(case_id)})}
    items = []
    found = conn.execute(text(
        "SELECT f.file_uid, f.extraction_id, f.category, f.local_path, f.size, f.verification, f.deleted_state, "
        "f.is_carved, c.first_at, coalesce(c.messages, 0) AS messages, f.md5, f.sha256 " + _base(_where(f, p)) +
        " ORDER BY c.first_at NULLS LAST, f.document_index, f.ordinal, f.file_uid OFFSET :o LIMIT :l"), p).fetchall()
    from services.phone import phone_setup
    zone_decided = phone_setup.zone_decided_files(conn, case_id, [r.file_uid for r in found])
    for r in found:
        ext = str(r.extraction_id)
        name = (r.local_path or "").replace("\\", "/").rsplit("/", 1)[-1] or "File not named in the report"
        z = zones.get(ext) or "UTC"
        items.append({
            "file_uid": str(r.file_uid), "extraction_id": ext, "phone_label": labels.get(ext, "A phone"),
            "category": r.category, "filename": name, "size": int(r.size) if r.size is not None else None,
            "taken_or_sent": {"instant": T.iso(r.first_at), "full": T.format_decided(
                r.first_at, z, "zone_decision" if str(r.file_uid) in zone_decided else None) if r.first_at else T.NO_TIME,
                "basis": "message_time" if r.first_at else "none"},
            "verification": r.verification, "verification_words": OUTCOME_WORDS.get(r.verification or "",
                                                                                     "Not checked"),
            "missing": r.verification == "missing", "deleted_state": r.deleted_state, "is_carved": bool(r.is_carved),
            "message_count": int(r.messages), "thumbnail_url": None, "machine_text": None,
            "hashes": {"md5": (r.md5 or "").strip() or None, "sha256": (r.sha256 or "").strip() or None}})
    _machine_marks(conn, case_id, items)
    return {"case_id": str(case_id), "offset": p["o"], "limit": p["l"], "items": items}


SHORT_MARK = {"machine": "Machine-generated", "confirmed": "Confirmed", "corrected": "Corrected"}


def _machine_marks(conn, case_id, items) -> None:
    """Each tile's machine text, by its one origin mark (07 4.6): the reading in use for each kind, so the grid says
    which files have a transcript or text read and whether a person stands behind it."""
    if not items:
        return
    from services.phone import derive
    by_uid = {it["file_uid"]: it for it in items}
    for r in conn.execute(text(
            "SELECT DISTINCT ON (d.file_uid, d.kind) d.* FROM phone_derived_texts d WHERE d.case_id = :c AND "
            "d.state = 'done' AND d.file_uid = ANY(CAST(:u AS uuid[])) " + derive.IN_USE_ORDER),
            {"c": str(case_id), "u": list(by_uid)}):
        d = dict(r._mapping)
        mark = derive.origin(d)
        it = by_uid[str(d["file_uid"])]
        it["machine_text"] = (it["machine_text"] or []) + [{
            "kind": d["kind"], "state": mark["state"], "short": SHORT_MARK.get(mark["state"], ""),
            "words": mark["words"]}]


def detail(conn, case_id, file_uid) -> dict | None:
    r = conn.execute(text(
        "SELECT f.*, c.first_at, coalesce(c.messages, 0) AS messages " + _base("f.case_id = :c AND f.file_uid::text = :u")),
        {"c": str(case_id), "u": str(file_uid)}).mappings().first()
    if r is None:
        return None
    links = []
    for l in conn.execute(text(
            "SELECT l.record_uid, coalesce(s.root_record_uid, l.record_uid) AS message_uid, l.mechanism, "
            "l.extracted_path, l.body_path, ev.sort_instant, ev.kind FROM pv_attachment_link l JOIN "
            "phone_record_summaries s ON s.record_uid = l.record_uid LEFT JOIN phone_comm_events ev ON "
            "ev.record_uid = coalesce(s.root_record_uid, l.record_uid) AND ev.generation = s.generation WHERE "
            "l.case_id = :c AND l.file_uid::text = :u AND l.resolved AND NOT coalesce(l.ambiguous, false) "
            "ORDER BY ev.sort_instant NULLS LAST, l.record_uid"), {"c": str(case_id), "u": str(file_uid)}):
        mech = "attachment_extracted_path" if l.extracted_path else l.mechanism
        links.append({"record_uid": str(l.record_uid), "message_record_uid": str(l.message_uid),
                      "kind": l.kind, "instant": T.iso(l.sort_instant), "mechanism": mech,
                      "mechanism_words": MECHANISM_WORDS.get(mech, mech)})
    return {"file_uid": str(r["file_uid"]), "extraction_id": str(r["extraction_id"]), "category": r["category"],
            "local_path": r["local_path"], "size": r["size"],
            "hashes": {"md5": r["md5"], "sha256": r["sha256"], "declared_md5": r["declared_md5"],
                       "declared_sha256": r["declared_sha256"], "disk_md5": r["disk_md5"],
                       "disk_sha256": r["disk_sha256"], "basis": r["hash_basis"]},
            "verification": r["verification"], "verification_words": OUTCOME_WORDS.get(r["verification"] or "",
                                                                                        "Not checked"),
            "missing": r["verification"] == "missing", "missing_words": MISSING_WORDS if r["verification"] ==
            "missing" else None, "deleted_state": r["deleted_state"], "is_carved": bool(r["is_carved"]),
            "messages": links, "message_count": int(r["messages"])}


CONTENT_MAX_BYTES = 200 * 1024 * 1024  # a file larger than this is not served inline; the viewer says so


class ContentRefused(LookupError):
    pass


def content(conn, case_id, file_uid, max_bytes=None):
    """(filename, size, opener) for one phone file's bytes, read in place from its container (01 D6): a folder
    upload from disk under the case's data root, a zip by its member. A file absent from the production, or
    larger than ``CONTENT_MAX_BYTES``, is refused with words."""
    import posixpath
    from pathlib import Path

    from config import EVIDENCE_DATA_ROOT
    r = conn.execute(text(
        "SELECT f.extraction_id, f.local_path, f.disk_relpath, f.disk_size, f.verification FROM pv_file f WHERE "
        "f.case_id = :c AND f.file_uid::text = :u"), {"c": str(case_id), "u": str(file_uid)}).first()
    if r is None:
        raise ContentRefused("This file is not in this case.")
    if r.verification == "missing" or not r.disk_relpath:
        raise ContentRefused(MISSING_WORDS)
    if r.disk_size and r.disk_size > (CONTENT_MAX_BYTES if max_bytes is None else max_bytes):
        raise ContentRefused("This file is %s MB, too large to show here. Download the original instead."
                             % "{:,}".format(int(r.disk_size) // (1024 * 1024)))
    conts = conn.execute(text(
        "SELECT c.id, c.container_kind, c.stored_path, l.root_path FROM phone_extraction_container_links l JOIN "
        "phone_extraction_containers c ON c.id = l.container_id WHERE l.extraction_id = :e AND c.case_id = :c "
        "ORDER BY l.linked_at, c.id"), {"e": r.extraction_id, "c": str(case_id)}).fetchall()
    if not conts:
        raise ContentRefused("The container holding this file is not recorded.")
    case_root = (Path(EVIDENCE_DATA_ROOT) / str(case_id)).resolve()
    name = posixpath.basename((r.local_path or "").replace("\\", "/")) or "file"
    # a phone can come in several containers (split sections, or the same production uploaded again): the file is
    # read from the first container, in the order they were linked, that holds it
    refusals = []
    for c in conts:
        try:
            size, opener = _in_container(conn, c, case_root, r.extraction_id, r.disk_relpath)
        except ContentRefused as exc:
            refusals.append(str(exc))
            continue
        return name, size, opener
    raise ContentRefused(MISSING_WORDS if MISSING_WORDS in refusals else refusals[0])


THUMB_EDGE = 256            # the grid tile is 112 px tall; 256 keeps it sharp on a 2x screen
THUMB_PASS_BYTES = 48 * 1024  # a file this small is sent as it is: a preview would not be smaller
THUMB_READ_MAX_BYTES = 25 * 1024 * 1024  # a larger file is not read into memory for a preview; it streams as before


def thumbnail(conn, case_id, file_uid, edge=THUMB_EDGE):
    """``(bytes, media_type)`` of a small JPEG preview of a phone image for the Media grid, made in memory from the
    file in its container; the original is never changed and the viewer still opens the original. ``None`` when
    the file is small enough to send whole or no preview can be made (a format the image library does not read):
    the caller then sends the original, as before. Refusals are the same as ``content``."""
    import io

    _name, size, opener = content(conn, case_id, file_uid)
    if size <= THUMB_PASS_BYTES or size > THUMB_READ_MAX_BYTES:
        return None
    try:
        from PIL import Image, ImageOps
        with opener() as fh:
            data = io.BytesIO(fh.read())
        with Image.open(data) as im:
            im.draft("RGB", (edge, edge))  # JPEG: decode at a reduced scale, much faster for large photos
            im = ImageOps.exif_transpose(im)
            im.thumbnail((edge, edge))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, "JPEG", quality=80)
        return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 (not an image the library reads, or damaged: the original is sent instead)
        return None


@functools.lru_cache(maxsize=2)
def _zip_directory(zpath, _mtime_ns, _size):
    """{member name: ZipInfo} of one archive, read once while it is unchanged: a download of many files from a large
    report would otherwise read the archive's whole directory once per file."""
    with zipfile.ZipFile(zpath) as z:
        return {i.filename: i for i in z.infolist()}


def _in_container(conn, c, case_root, extraction_id, disk_relpath):
    """(size, opener) of one file in one container, or ContentRefused with the reason."""
    import posixpath
    import zipfile
    rel = posixpath.normpath(posixpath.join(c.root_path or "", disk_relpath)).lstrip("/")
    if rel.startswith(".."):
        raise ContentRefused("The file's place in its container is not valid.")
    if c.container_kind == "folder":
        path = (case_root / c.stored_path / rel).resolve()
        if not str(path).startswith(str(case_root) + "/") or not path.is_file():
            raise ContentRefused(MISSING_WORDS)
        return path.stat().st_size, lambda: open(path, "rb")
    if c.container_kind in ("zip", "ufdr"):  # a UFDR is a zip
        zpath = (case_root / c.stored_path).resolve()
        if not str(zpath).startswith(str(case_root) + "/") or not zpath.is_file():
            raise ContentRefused("The container holding this file is not on disk.")
        # straight to the member by its recorded position in this archive (cb-media item F); the directory lookup
        # below stays for entries recorded before positions were, or a method read only by zipfile
        from services.phone import archive_member as AM
        pos = conn.execute(text(
            "SELECT header_offset, compressed_size, compress_type, crc32, size_bytes FROM phone_container_entries "
            "WHERE extraction_id = :e AND relpath = :r AND container_id = :k"),
            {"e": extraction_id, "r": disk_relpath, "k": c.id}).first()
        if pos is not None and pos.header_offset is not None:
            args = (zpath, pos.header_offset, pos.compressed_size, pos.compress_type, pos.crc32, pos.size_bytes)
            probe = AM.open_at(*args)
            if probe is not None:
                probe.close()
                def at():
                    fh = AM.open_at(*args)
                    if fh is None:
                        raise ContentRefused("This file could not be read from its container just now.")
                    return fh
                return pos.size_bytes, at
        st = zpath.stat()
        info = _zip_directory(str(zpath), st.st_mtime_ns, st.st_size).get(rel)
        if info is None:
            raise ContentRefused(MISSING_WORDS)
        size = info.file_size

        def opener():
            z = zipfile.ZipFile(zpath)
            member = z.open(info)
            close = member.close

            def closing():
                close()
                z.close()
            member.close = closing
            return member
        return size, opener
    raise ContentRefused("Files in a %s container are not shown yet." % c.container_kind)


# ---- Download originals (03 8.3): a zip of the chosen files with a manifest of hashes ----------------------------------

class DownloadRefused(ValueError):
    pass


def download_plan(conn, case_id, f: dict | None = None, file_uids=None) -> dict:
    """The files a download holds (the filter's, or the chosen files within it) and their total bytes. Missing files
    are listed in the manifest as not in the production, never left out. ``services.phone.originals`` draws them."""
    f, p = with_significant(conn, case_id, dict(f or {})), {"c": str(case_id)}
    where = _where(f, p)
    if file_uids:
        where += " AND f.file_uid::text = ANY(:uids)"
        p["uids"] = [str(u) for u in file_uids]
    rows = [dict(r._mapping) for r in conn.execute(text(
        "SELECT f.file_uid, f.extraction_id, f.category, f.local_path, coalesce(f.disk_size, f.size) AS size, "
        "f.verification, f.md5, f.sha256, f.declared_md5, f.declared_sha256, c.first_at " + _base(where) +
        " ORDER BY f.extraction_id, f.document_index, f.ordinal, f.file_uid"), p)]
    if file_uids and len(rows) != len(set(str(u) for u in file_uids)):
        raise DownloadRefused("Some chosen files are not in this case's media as filtered; choose again.")
    held = [r for r in rows if r["verification"] != "missing"]
    total_bytes = sum(int(r["size"] or 0) for r in held)
    refusal = None
    if not rows:
        refusal = "There are no files to download."
    return {"files": rows, "count": len(rows), "held": len(held), "not_in_production": len(rows) - len(held),
            "bytes": total_bytes, "refusal": refusal}
