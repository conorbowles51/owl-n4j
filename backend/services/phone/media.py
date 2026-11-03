"""Media (03 section 8): the files on each phone, by phone, category and state, with the messages that carried them.

Every file of the case's active phones is listed (``pv_file``), so the grid's total equals the phone summary's file
count (M-4). A file's time is the time of the first message that carried it (``message_time``); a file no message
carried has no time (``none``) and is counted, never dropped. A file the report names but the production does not
hold (outcome ``missing``) is counted under ``missing`` and shown with the 3.6 sentence, never as a broken image
(M-2). The messages that carried a file are found by every reference mechanism, including the Attachment record's
extracted path (M-1), each with the mechanism that found it.
"""
from __future__ import annotations

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
    if f.get("linked_to_message") is True:
        w.append("c.file_uid IS NOT NULL")
    elif f.get("linked_to_message") is False:
        w.append("c.file_uid IS NULL")
    return " AND ".join(w)


def _base(where):
    return ("FROM pv_file f LEFT JOIN (%s) c ON c.file_uid = f.file_uid WHERE %s" % (_CARRIED, where))


def index(conn, case_id, f: dict | None = None) -> dict:
    f, p = dict(f or {}), {"c": str(case_id)}
    base = _base(_where(f, p))
    total, no_time, missing = conn.execute(text(
        "SELECT count(*), count(*) FILTER (WHERE c.first_at IS NULL), count(*) FILTER (WHERE f.verification = "
        "'missing') " + base), p).one()
    by_cat = {r[0] or "Uncategorised": int(r[1]) for r in conn.execute(text(
        "SELECT f.category, count(*) " + base + " GROUP BY 1 ORDER BY 2 DESC, 1"), p)}
    by_ver = {r[0] or "unchecked": int(r[1]) for r in conn.execute(text(
        "SELECT f.verification, count(*) " + base + " GROUP BY 1 ORDER BY 2 DESC, 1"), p)}
    return {"case_id": str(case_id), "total": int(total), "no_time_count": int(no_time), "missing": int(missing),
            "by_category": by_cat, "verification": by_ver}


def window(conn, case_id, f: dict | None = None, offset: int = 0, limit: int = 200) -> dict:
    f, p = dict(f or {}), {"c": str(case_id), "o": max(0, int(offset)), "l": max(1, min(WINDOW_MAX, int(limit)))}
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    zones = {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT extraction_id, device_zone FROM pv_extraction WHERE case_id = :c"), {"c": str(case_id)})}
    items = []
    for r in conn.execute(text(
            "SELECT f.file_uid, f.extraction_id, f.category, f.local_path, f.size, f.verification, f.deleted_state, "
            "f.is_carved, c.first_at, coalesce(c.messages, 0) AS messages " + _base(_where(f, p)) +
            " ORDER BY c.first_at NULLS LAST, f.document_index, f.ordinal, f.file_uid OFFSET :o LIMIT :l"), p):
        ext = str(r.extraction_id)
        name = (r.local_path or "").replace("\\", "/").rsplit("/", 1)[-1] or "File not named in the report"
        z = zones.get(ext) or "UTC"
        items.append({
            "file_uid": str(r.file_uid), "extraction_id": ext, "phone_label": labels.get(ext, "A phone"),
            "category": r.category, "filename": name, "size": int(r.size) if r.size is not None else None,
            "taken_or_sent": {"instant": T.iso(r.first_at), "full": T.format_full(r.first_at, z) if r.first_at
                              else T.NO_TIME, "basis": "message_time" if r.first_at else "none"},
            "verification": r.verification, "verification_words": OUTCOME_WORDS.get(r.verification or "",
                                                                                     "Not checked"),
            "missing": r.verification == "missing", "deleted_state": r.deleted_state, "is_carved": bool(r.is_carved),
            "message_count": int(r.messages), "thumbnail_url": None})
    return {"case_id": str(case_id), "offset": p["o"], "limit": p["l"], "items": items}


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


def content(conn, case_id, file_uid):
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
    if r.disk_size and r.disk_size > CONTENT_MAX_BYTES:
        raise ContentRefused("This file is %s MB, too large to show here. Download the original instead."
                             % "{:,}".format(int(r.disk_size) // (1024 * 1024)))
    conts = conn.execute(text(
        "SELECT c.container_kind, c.stored_path, l.root_path FROM phone_extraction_container_links l JOIN "
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
            size, opener = _in_container(c, case_root, r.disk_relpath)
        except ContentRefused as exc:
            refusals.append(str(exc))
            continue
        return name, size, opener
    raise ContentRefused(MISSING_WORDS if MISSING_WORDS in refusals else refusals[0])


THUMB_EDGE = 256            # the grid tile is 112 px tall; 256 keeps it sharp on a 2x screen
THUMB_PASS_BYTES = 48 * 1024  # a file this small is sent as it is: a preview would not be smaller


def thumbnail(conn, case_id, file_uid, edge=THUMB_EDGE):
    """``(bytes, media_type)`` of a small JPEG preview of a phone image for the Media grid, made in memory from the
    file in its container; the original is never changed and the viewer still opens the original. ``None`` when
    the file is small enough to send whole or no preview can be made (a format the image library does not read):
    the caller then sends the original, as before. Refusals are the same as ``content``."""
    import io

    _name, size, opener = content(conn, case_id, file_uid)
    if size <= THUMB_PASS_BYTES:
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


def _in_container(c, case_root, disk_relpath):
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
        with zipfile.ZipFile(zpath) as z:
            try:
                info = z.getinfo(rel)
            except KeyError:
                raise ContentRefused(MISSING_WORDS) from None
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
