"""Download originals (03 section 8.3): the selected phone files in a zip with a manifest of hashes, as a job.

The zip holds each file's exact bytes, stored without compression, read in place from its container. Every hash in
the manifest is computed from the bytes that went into the zip and compared with each hash stored for the file. A
mismatch is included and reported; a file that cannot be included (absent from the production, or unreadable) is
listed with the reason. Nothing is dropped: ``manifest.csv`` has one line for every file asked for, and the job's
counts add up to the set. The set is frozen when asked for.

Bytes pass through 1 MB at a time, so a whole phone is never in memory, and the zip is written under the exports
directory beside the case data, never /tmp. It is written under a temporary name and moved into place only when
complete. A finished zip is removed after ``KEEP_DAYS``; the job says so, and the same selection makes it again.
The job runs on its own thread in the phone worker (nice 19, idle I/O), so PDF exports never wait for it. A run cut
by a restart is taken up from the start, up to ``MAX_ATTEMPTS`` times.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import re
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import text

from services.phone import media
from services.phone import time_display as T

log = logging.getLogger(__name__)
CHUNK = 1024 * 1024
PROGRESS_SECONDS = 1.0
STALE_SECONDS = 300  # no heartbeat for this long: the worker stopped
MAX_ATTEMPTS = 5
KEEP_DAYS = 7
IDLE_SECONDS = 5
SPACE_MARGIN = 2 * 1024 ** 3  # room left beside the zip for the case's other work
FILES_MAX = 200_000
STOPPED = ("This download stopped %d times before it finished. Nothing was delivered. Ask for it again, or for fewer "
           "files." % MAX_ATTEMPTS)
HASHES = (("md5", "md5"), ("sha256", "sha256"), ("declared_md5", "md5"), ("declared_sha256", "sha256"),
          ("disk_md5", "md5"), ("disk_sha256", "sha256"))
COLUMNS = ("path_in_zip", "file_uid", "phone", "path_on_phone", "category", "state", "size_recorded", "size_read",
           "md5_computed", "sha256_computed", "md5_stored", "sha256_stored", "declared_md5", "declared_sha256",
           "disk_md5", "disk_sha256", "comparison", "note")


class BundleError(ValueError):
    pass


class _Cancelled(Exception):
    pass


def bundle_dir() -> Path:
    env = os.environ.get("LOUPE_PHONE_BUNDLE_DIR")
    if env:
        return Path(env)
    from config import EVIDENCE_DATA_ROOT
    return Path(EVIDENCE_DATA_ROOT) / "phone-exports" / "originals"


def count_refusal(count: int) -> str | None:
    if count <= FILES_MAX:
        return None
    return "A download holds at most %s files; this one has %s. Nothing was started; choose fewer files." % (
        format(FILES_MAX, ","), format(count, ","))


def space_refusal(size: int) -> str | None:
    """Words when the disk cannot hold ``size`` bytes beside the case's other work: a set is refused with its numbers
    before anything is written, never clipped."""
    target = bundle_dir()
    target.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(target).free
    if int(size) + SPACE_MARGIN <= free:
        return None
    return ("These files come to %s GB and the server has %s GB free for them. Nothing was started; choose fewer files."
            % (format(int(size) // 1024 ** 3, ","), format(max(0, free - SPACE_MARGIN) // 1024 ** 3, ",")))


def create(conn, *, case_id, user_id, file_uids, scope_words) -> dict:
    """Freeze the set and queue it. Every asked-for file must be in this case."""
    uids = list(dict.fromkeys(str(u) for u in file_uids))
    if not uids:
        raise BundleError("Choose at least one file.")
    refusal = count_refusal(len(uids))
    if refusal:
        raise BundleError(refusal)
    found, size = conn.execute(text(
        "SELECT count(*), coalesce(sum(coalesce(f.disk_size, 0)), 0) FROM pv_file f WHERE f.case_id = :c AND "
        "f.file_uid::text = ANY(:u)"), {"c": str(case_id), "u": uids}).one()
    if int(found) != len(uids):
        raise BundleError("%d of the chosen files are not in this case." % (len(uids) - int(found)))
    refusal = space_refusal(int(size))
    if refusal:
        raise BundleError(refusal)
    bundle_id = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_original_bundles (bundle_id, case_id, created_by, scope_words, file_uids, files_total, "
        "bytes_total) VALUES (:i, :c, :u, :w, CAST(:f AS uuid[]), :n, :b)"),
        {"i": bundle_id, "c": str(case_id), "u": str(user_id), "w": (scope_words or "Selected files").strip()[:300],
         "f": uids, "n": len(uids), "b": int(size)})
    return get(conn, case_id, bundle_id)


def _out(r) -> dict:
    return {"bundle_id": str(r.bundle_id), "state": r.state, "scope_words": r.scope_words,
            "files_total": r.files_total, "bytes_total": int(r.bytes_total), "files_done": r.files_done,
            "bytes_done": int(r.bytes_done), "matched": r.matched, "mismatched": r.mismatched,
            "no_stored_hash": r.no_stored_hash, "not_included": r.not_included,
            "file": {"filename": r.filename, "size": int(r.size), "sha256": r.sha256} if r.state == "done" else None,
            "error": r.error, "created_at": T.iso(r.created_at), "finished_at": T.iso(r.finished_at),
            "expires_at": T.iso(r.expires_at)}


_COLS = ("bundle_id, state, scope_words, files_total, bytes_total, files_done, bytes_done, matched, mismatched, "
         "no_stored_hash, not_included, filename, size, sha256, error, created_at, finished_at, expires_at, "
         "storage_path, created_by")


def get(conn, case_id, bundle_id) -> dict | None:
    r = conn.execute(text("SELECT %s FROM phone_original_bundles WHERE bundle_id = CAST(:i AS uuid) AND case_id = "
                          "CAST(:c AS uuid)" % _COLS), {"i": str(bundle_id), "c": str(case_id)}).first()
    return _out(r) if r else None


def recent(conn, case_id, limit=10) -> list:
    return [_out(r) for r in conn.execute(text(
        "SELECT %s FROM phone_original_bundles WHERE case_id = CAST(:c AS uuid) ORDER BY created_at DESC LIMIT :l"
        % _COLS), {"c": str(case_id), "l": limit})]


def file_of(conn, case_id, bundle_id):
    return conn.execute(text("SELECT %s FROM phone_original_bundles WHERE bundle_id = CAST(:i AS uuid) AND case_id = "
                             "CAST(:c AS uuid) AND state = 'done'" % _COLS),
                        {"i": str(bundle_id), "c": str(case_id)}).first()


def cancel(conn, case_id, bundle_id, user_id) -> bool:
    return conn.execute(text(
        "UPDATE phone_original_bundles SET state = 'cancelled', finished_at = now() WHERE bundle_id = CAST(:i AS uuid) "
        "AND case_id = CAST(:c AS uuid) AND created_by = CAST(:u AS uuid) AND state IN ('queued', 'running')"),
        {"i": str(bundle_id), "c": str(case_id), "u": str(user_id)}).rowcount > 0


# ---- what goes in ---------------------------------------------------------------------------------------------------

def zip_path(phone: str, local_path: str | None, file_uid, taken: set) -> str:
    """Where a file sits in the zip: under its phone, keeping its path on the phone, never climbing out of the zip;
    two files with one path both stay, the second with its id."""
    parts = [re.sub(r'[\x00-\x1f<>:"|?*]', "_", p).strip() for p in (local_path or "").replace("\\", "/").split("/")]
    parts = [p for p in parts if p and p not in (".", "..")] or [str(file_uid)]
    folder = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", phone).strip() or "phone"
    name = "/".join(["files", folder, *parts])
    if name in taken:
        stem, dot, ext = parts[-1].rpartition(".")
        parts[-1] = "%s_%s.%s" % (stem, file_uid, ext) if dot else "%s_%s" % (parts[-1], file_uid)
        name = "/".join(["files", folder, *parts])
    taken.add(name)
    return name


def compare(computed: dict, stored: dict) -> tuple:
    """(comparison, the stored hashes that differ): each stored hash against the hash computed from the zipped bytes."""
    held = {k: v for k, v in stored.items() if v}
    if not held:
        return "no_stored_hash", []
    differs = [k for k, v in held.items() if v.strip().lower() != computed[dict(HASHES)[k]]]
    return ("mismatch", differs) if differs else ("match", [])


def _sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- the worker -----------------------------------------------------------------------------------------------------

def _claim(engine):
    while True:
        with engine.begin() as c:
            r = c.execute(text(
                "SELECT bundle_id, state, attempts FROM phone_original_bundles WHERE state = 'queued' OR (state = "
                "'running' AND heartbeat_at < now() - make_interval(secs => :s)) ORDER BY created_at FOR UPDATE SKIP "
                "LOCKED LIMIT 1"), {"s": STALE_SECONDS}).one_or_none()
            if r is None:
                return None
            if r.state == "running" and r.attempts >= MAX_ATTEMPTS:
                c.execute(text("UPDATE phone_original_bundles SET state = 'failed', error = :e, finished_at = now() "
                               "WHERE bundle_id = :i"), {"e": STOPPED, "i": r.bundle_id})
                (bundle_dir() / ("%s.zip.part" % r.bundle_id)).unlink(missing_ok=True)
                (bundle_dir() / ("%s.manifest.part" % r.bundle_id)).unlink(missing_ok=True)
                continue
            c.execute(text(
                "UPDATE phone_original_bundles SET state = 'running', started_at = now(), heartbeat_at = now(), "
                "attempts = attempts + 1, files_done = 0, bytes_done = 0, matched = 0, mismatched = 0, "
                "no_stored_hash = 0, not_included = 0, error = NULL WHERE bundle_id = :i"), {"i": r.bundle_id})
            return r.bundle_id


def _beat(engine, bundle_id, done):
    """Progress and heartbeat; a person's cancel is seen here."""
    with engine.begin() as c:
        alive = c.execute(text(
            "UPDATE phone_original_bundles SET files_done = :files, bytes_done = :bytes, matched = :match, mismatched "
            "= :mismatch, no_stored_hash = :none, not_included = :left, heartbeat_at = now() WHERE bundle_id = :i AND "
            "state = 'running'"), {**done, "i": bundle_id}).rowcount
    if not alive:
        raise _Cancelled()


def _phone_labels(conn, case_id):
    from services.phone.readings import phone_labels
    return phone_labels(conn, case_id)


def draw(engine, bundle_id) -> dict:
    target = bundle_dir()
    target.mkdir(parents=True, exist_ok=True)
    part = target / ("%s.zip.part" % bundle_id)
    sheet = target / ("%s.manifest.part" % bundle_id)
    final = target / ("%s.zip" % bundle_id)
    try:
        with engine.connect() as conn:
            b = conn.execute(text("SELECT * FROM phone_original_bundles WHERE bundle_id = :i"), {"i": bundle_id}).one()
            case_id = b.case_id
            labels = _phone_labels(conn, case_id)
            files = conn.execute(text(
                "SELECT f.file_uid, f.extraction_id, f.category, f.local_path, f.disk_size, f.size, f.verification, "
                "f.md5, f.sha256, f.declared_md5, f.declared_sha256, f.disk_md5, f.disk_sha256 FROM pv_file f WHERE "
                "f.case_id = :c AND f.file_uid = ANY(CAST(:u AS uuid[])) ORDER BY f.extraction_id, f.document_index, "
                "f.ordinal, f.file_uid"), {"c": str(case_id), "u": [str(u) for u in b.file_uids]}).fetchall()
            done = {"files": 0, "bytes": 0, "match": 0, "mismatch": 0, "none": 0, "left": 0}
            gone = sorted(set(str(u) for u in b.file_uids) - {str(f.file_uid) for f in files})
            taken, last = set(), time.monotonic()
            with open(sheet, "w", newline="", encoding="utf-8") as mf, zipfile.ZipFile(
                    part, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
                out = csv.writer(mf)
                out.writerow(COLUMNS)
                for f in files:
                    done = _add(conn, z, out, f, labels, case_id, taken, done, engine, bundle_id)
                    if time.monotonic() - last >= PROGRESS_SECONDS:
                        _beat(engine, bundle_id, done)
                        last = time.monotonic()
                for uid in gone:  # a phone replaced since the selection: said, never lost
                    out.writerow(["", uid] + [""] * (len(COLUMNS) - 4) + ["not_included", "The file is no longer in "
                                                                          "the case's active phone reports."])
                    done["left"] += 1
                    done["files"] += 1
                mf.flush()
                _beat(engine, bundle_id, done)
                z.write(sheet, "manifest.csv")
                z.writestr("summary.txt", _summary(b, done, len(files) + len(gone)))
        digest = _sha256_of(part)
        size = part.stat().st_size
        os.replace(part, final)
        name = "%s-originals-%s.zip" % (re.sub(r"[^A-Za-z0-9._-]+", "-", b.scope_words).strip("-")[:60] or "phone",
                                        str(bundle_id)[:8])
        with engine.begin() as c:
            won = c.execute(text(
                "UPDATE phone_original_bundles SET state = 'done', files_done = :files, bytes_done = :bytes, matched "
                "= :match, mismatched = :mismatch, no_stored_hash = :none, not_included = :left, filename = :n, size "
                "= :s, sha256 = :h, storage_path = :p, finished_at = now(), expires_at = now() + make_interval(days "
                "=> :k) WHERE bundle_id = :i AND state = 'running'"),
                {**done, "n": name, "s": size, "h": digest, "p": str(final), "k": KEEP_DAYS, "i": bundle_id}).rowcount
        if not won:
            raise _Cancelled()
        return {"bundle_id": str(bundle_id), "state": "done"}
    except _Cancelled:
        final.unlink(missing_ok=True)
        return {"bundle_id": str(bundle_id), "state": "cancelled"}
    finally:
        part.unlink(missing_ok=True)
        sheet.unlink(missing_ok=True)


def _summary(b, done, total) -> str:
    return "\n".join([
        "Phone originals: %s" % b.scope_words, "Asked for %d files on %s UTC." % (total, b.created_at.strftime("%Y-%m-%d %H:%M")),
        "%d included: %d match every stored hash, %d differ from a stored hash, %d have no stored hash." % (
            total - done["left"], done["match"], done["mismatch"], done["none"]),
        "%d not included; manifest.csv gives the reason for each." % done["left"],
        "Files are stored uncompressed, byte for byte. Hashes in manifest.csv are computed from the bytes in this zip.", ""])


def _add(conn, z, out, f, labels, case_id, taken, done, engine, bundle_id) -> dict:
    phone = labels.get(str(f.extraction_id), "phone")
    stored = {k: getattr(f, k) for k, _ in HASHES}
    row = lambda path, read, md5, sha, comparison, note: out.writerow(  # noqa: E731
        [path, str(f.file_uid), phone, f.local_path or "", f.category or "", f.verification or "", f.disk_size or f.size
         or "", read, md5, sha, f.md5 or "", f.sha256 or "", f.declared_md5 or "", f.declared_sha256 or "",
         f.disk_md5 or "", f.disk_sha256 or "", comparison, note])
    done["files"] += 1
    try:
        _name, _size, opener = media.content(conn, case_id, f.file_uid, max_bytes=float("inf"))  # the viewer's limit
        conn.rollback()  # no transaction stays open while one large file is read
        src = opener()
    except Exception as exc:  # noqa: BLE001 (a damaged container raises many kinds; no entry is in the zip yet)
        conn.rollback()
        row("", "", "", "", "not_included", str(exc) if isinstance(exc, media.ContentRefused) else
            "The file could not be opened (%s)." % type(exc).__name__)
        done["left"] += 1
        return done
    path = zip_path(phone, f.local_path, f.file_uid, taken)
    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))  # the date of the zip entry says nothing of the file
    info.compress_type = zipfile.ZIP_STORED
    md5, sha, read = hashlib.md5(usedforsecurity=False), hashlib.sha256(), 0  # noqa: S324 (the report's own hash kind)
    last, stopped = time.monotonic(), None
    # only a failed read of the source is this file's fault; a failed write or heartbeat ends the job, which says so
    with src, z.open(info, "w", force_zip64=True) as dst:
        while True:
            try:
                chunk = src.read(CHUNK)
            except Exception as exc:  # noqa: BLE001 (a damaged member raises many kinds; one file never ends the job)
                stopped = exc
                break
            if not chunk:
                break
            dst.write(chunk)
            md5.update(chunk)
            sha.update(chunk)
            read += len(chunk)
            done["bytes"] += len(chunk)
            if time.monotonic() - last >= PROGRESS_SECONDS:  # one large video still shows movement
                _beat(engine, bundle_id, done)
                last = time.monotonic()
    if stopped is not None:
        # a zip entry cannot be taken back: the part read stays in the zip, and the manifest says it is not the file
        row(path, read, "", "", "not_included", "Reading stopped after %d bytes (%s); what is in the zip under this "
            "name is not the whole file." % (read, type(stopped).__name__))
        done["left"] += 1
        return done
    computed = {"md5": md5.hexdigest(), "sha256": sha.hexdigest()}
    comparison, differs = compare(computed, stored)
    done[{"match": "match", "mismatch": "mismatch", "no_stored_hash": "none"}[comparison]] += 1
    row(path, read, computed["md5"], computed["sha256"], comparison,
        "Differs from: %s." % ", ".join(differs) if differs else "")
    return done


def run_pending(engine) -> list:
    got = _claim(engine)
    if got is None:
        return []
    try:
        return [draw(engine, got)]
    except Exception:  # noqa: BLE001
        ref = uuid.uuid4().hex[:8]
        log.exception("phone originals %s failed (reference %s)", got, ref)
        with engine.begin() as c:
            c.execute(text("UPDATE phone_original_bundles SET state = 'failed', error = :e, finished_at = now() WHERE "
                           "bundle_id = :i AND state = 'running'"),
                      {"e": "The download could not be finished. Nothing was delivered; ask for it again. Reference: "
                            "%s." % ref, "i": got})
        return [{"bundle_id": str(got), "state": "failed"}]


def sweep_expired(engine, now=None) -> int:
    """Finished zips past their date are removed, and the job says so. Then any file in the directory no live job owns
    goes too: a part left by a stopped worker, or the zip of a case since deleted, which is a copy of its evidence."""
    with engine.begin() as c:
        rows = c.execute(text(
            "SELECT bundle_id, storage_path FROM phone_original_bundles WHERE state = 'done' AND expires_at < "
            "coalesce(:n, now()) FOR UPDATE SKIP LOCKED"), {"n": now}).fetchall()
        for r in rows:
            if r.storage_path:
                Path(r.storage_path).unlink(missing_ok=True)
            c.execute(text("UPDATE phone_original_bundles SET state = 'removed', storage_path = NULL WHERE bundle_id "
                           "= :i"), {"i": r.bundle_id})
    target = bundle_dir()
    if target.is_dir():
        with engine.connect() as c:
            live = {str(x[0]) for x in c.execute(text(
                "SELECT bundle_id FROM phone_original_bundles WHERE state IN ('queued', 'running', 'done')"))}
        for p in target.iterdir():
            if p.is_file() and p.name.split(".", 1)[0] not in live:
                p.unlink(missing_ok=True)
    return len(rows)


_worker = {"thread": None}


def _loop(engine_factory, stop):
    swept = 0.0
    while not stop.is_set():
        busy = []
        try:
            engine = engine_factory()
            busy = run_pending(engine)
            if time.monotonic() - swept > 3600:
                sweep_expired(engine)
                swept = time.monotonic()
        except Exception:  # noqa: BLE001
            log.exception("phone originals step failed")
        stop.wait(0 if busy else IDLE_SECONDS)


def start_worker(engine, stop):
    t = _worker["thread"]
    if t is not None and t.is_alive():
        return
    _worker["thread"] = threading.Thread(target=_loop, args=(lambda: engine, stop), name="phone-originals", daemon=True)
    _worker["thread"].start()
