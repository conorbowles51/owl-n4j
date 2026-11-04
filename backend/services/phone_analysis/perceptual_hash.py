"""Perceptual hashes of phone pictures, computed on this server (05 section 11.3 step 3; cb-gated-spread D).

A messaging app re-compresses a picture it forwards, so its MD5 changes and the exact tier misses the copy. A
perceptual hash describes what the picture looks like, so a re-encoded copy keeps nearly the same hash.

- **What is hashed.** Approach 8's population pictures (``image_search.POPULATION_SQL``: carried by a message, in a
  camera or screenshot folder, or EXIF names a camera), present in the production, in a case with two or more active
  phones: with one phone there is nothing to compare across phones; when a second phone is added its turn comes.
- **How.** The picture is decoded by Pillow (already a dependency; nothing leaves the server and no new library is
  installed), turned upright by its EXIF orientation, reduced to grey, and two 64-bit hashes are taken: ``dhash``
  (9 x 8 pixels, each bit says whether a pixel is brighter than its right neighbour) and ``phash`` (32 x 32 pixels,
  a two-dimensional DCT, the 8 x 8 lowest frequencies against their median). These are the standard definitions.
  JPEG pictures are decoded at reduced size (Pillow's ``draft``), which is what keeps the cost low.
- **Where and when.** One draw of ``BATCH`` pictures per turn on the phone worker's after-pass thread (the thread
  that also reads, translates and indexes media), so it never runs beside another media model. Resumable: a picture
  with a row is never read again; a failed picture keeps its reason and is not retried unless its reason is
  ``RETRY_REASONS``.
- **Bounded memory.** A file larger than ``MAX_BYTES`` or a picture larger than ``MAX_PIXELS`` is refused with its
  reason before it is decoded in full.

A near-identical pair is a lead, not proof of the same file (05 section 3; ``media_spread.perceptual_pairs``).
"""
from __future__ import annotations

import io
import logging
import time

import numpy as np
from sqlalchemy import text

log = logging.getLogger(__name__)

ALGORITHM = "phash64+dhash64/1"
BATCH = 100
MAX_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 80_000_000
RETRY_REASONS = ("read_error",)
# a case found with nothing waiting is looked at again after this long (new phones and files arrive by interpretation)
RESCAN_SECONDS = 600
_idle_until: dict = {}
REASON_WORDS = {
    "not_in_production": "The file is not in the production.",
    "too_large": "The file is larger than 40 MB, so it is not decoded here.",
    "cannot_open": "The image library could not open it (damaged, or a format it does not read, such as HEIC).",
    "empty": "The file is empty.",
    "read_error": "The file could not be read this time; it is tried again.",
}


def _dct_matrix(n):
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n)) * np.sqrt(2.0 / n)
    m[0, :] = np.sqrt(1.0 / n)
    return m


_DCT32 = _dct_matrix(32)


def _bits_to_int(bits) -> int:
    v = 0
    for b in np.asarray(bits, dtype=bool).ravel():
        v = (v << 1) | int(b)
    return v


def to_signed(v: int) -> int:
    return v - (1 << 64) if v >= (1 << 63) else v


def to_unsigned(v: int) -> int:
    return v + (1 << 64) if v < 0 else v


def hashes(data: bytes) -> tuple:
    """(phash, dhash) as unsigned 64-bit integers for one picture's bytes. Raises ``ValueError`` with a reason code."""
    from PIL import Image, ImageOps
    if not data:
        raise ValueError("empty")
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("too_large")
        img.draft("L", (128, 128))  # JPEG: decode at reduced size; other formats ignore it
        img = ImageOps.exif_transpose(img)
        grey = img.convert("L")
    except ValueError:
        raise
    except Exception:  # noqa: BLE001 - any decoder refusal is the same outcome for the person
        raise ValueError("cannot_open") from None
    d = np.asarray(grey.resize((9, 8), Image.LANCZOS), dtype=np.float64)
    dh = _bits_to_int(d[:, 1:] > d[:, :-1])
    p = np.asarray(grey.resize((32, 32), Image.LANCZOS), dtype=np.float64)
    low = (_DCT32 @ p @ _DCT32.T)[:8, :8]
    ph = _bits_to_int(low > np.median(low))
    return ph, dh


def distance(a: int, b: int) -> int:
    return bin(to_unsigned(a) ^ to_unsigned(b)).count("1")


def _eligible_sql():
    """The waiting pictures of one case (``:c``). A failed read is tried again after an hour, never in the same
    turn loop."""
    from services.phone import image_search as IS
    return ("SELECT f.file_uid, f.case_id, f.extraction_id " + IS._base() + " AND " + IS.IMAGE_SQL + " AND " +
            IS.POPULATION_SQL + " AND " + IS.PRESENT_SQL + " AND coalesce(f.verification, '') <> 'empty_placeholder' "
            "AND NOT EXISTS (SELECT 1 FROM phone_file_perceptual_hashes h WHERE h.file_uid = f.file_uid AND (h.state = "
            "'done' OR h.reason <> ALL(:retry) OR h.computed_at > now() - interval '1 hour'))")


def cases_to_hash(conn) -> list:
    return [str(r[0]) for r in conn.execute(text(
        "SELECT case_id FROM phone_extractions WHERE standing = 'active' GROUP BY case_id HAVING count(*) >= 2 "
        "ORDER BY case_id"))]


def _params(**extra):
    from services.phone import image_search as IS
    p = {"cam": IS.CAMERA_RE, "exif_cam": list(IS.EXIF_CAMERA_ITEMS), "retry": list(RETRY_REASONS)}
    p.update(extra)
    return p


def describe(conn, case_id) -> dict:
    """True counts for one case: pictures in the population and the production, hashed, waiting, could not be
    hashed by reason, and whether the case has the two phones hashing needs."""
    from services.phone import image_search as IS
    present = ("%s AND %s AND %s AND coalesce(f.verification, '') <> 'empty_placeholder'"
               % (IS.IMAGE_SQL, IS.POPULATION_SQL, IS.PRESENT_SQL))
    r = conn.execute(text(
        "SELECT count(*) FILTER (WHERE " + present + ") AS pictures, "
        "count(*) FILTER (WHERE " + present + " AND h.state = 'done') AS hashed, "
        "count(*) FILTER (WHERE " + present + " AND h.state = 'failed') AS failed " + IS._base().replace(
            "WHERE f.case_id = :c", "LEFT JOIN phone_file_perceptual_hashes h ON h.file_uid = f.file_uid WHERE "
            "f.case_id = :c")), _params(c=str(case_id))).one()
    reasons = {k: int(n) for k, n in conn.execute(text(
        "SELECT reason, count(*) FROM phone_file_perceptual_hashes WHERE case_id = :c AND state = 'failed' GROUP BY 1"),
        {"c": str(case_id)})}
    phones = int(conn.execute(text("SELECT count(*) FROM phone_extractions WHERE case_id = :c AND standing = "
                                   "'active'"), {"c": str(case_id)}).scalar() or 0)
    return {"pictures": int(r.pictures), "hashed": int(r.hashed), "failed": int(r.failed),
            "waiting": max(0, int(r.pictures) - int(r.hashed) - int(r.failed)) if phones >= 2 else 0,
            "failed_by_reason": reasons, "failed_words": {k: REASON_WORDS.get(k, k) for k in reasons},
            "case_phones": phones, "algorithm": ALGORITHM,
            "not_hashed_words": None if phones >= 2 else
            "This case has one phone, so its pictures are not compared across phones and are not hashed."}


def _store(engine, f, state, ph=None, dh=None, reason=None, cpu_ms=None):
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO phone_file_perceptual_hashes (file_uid, case_id, extraction_id, algorithm, state, phash, "
            "dhash, reason, cpu_ms) VALUES (:u, :c, :e, :a, :s, :p, :d, :r, :ms) ON CONFLICT (file_uid) DO UPDATE SET "
            "state = EXCLUDED.state, phash = EXCLUDED.phash, dhash = EXCLUDED.dhash, reason = EXCLUDED.reason, "
            "cpu_ms = EXCLUDED.cpu_ms, algorithm = EXCLUDED.algorithm, computed_at = now()"),
            {"u": f.file_uid, "c": f.case_id, "e": f.extraction_id, "a": ALGORITHM, "s": state,
             "p": to_signed(ph) if ph is not None else None, "d": to_signed(dh) if dh is not None else None,
             "r": reason, "ms": cpu_ms})


def read_bytes(conn, case_id, file_uid) -> bytes:
    from services.phone import media
    from services.phone.archive_member import MemberDamaged
    try:
        _name, size, opener = media.content(conn, case_id, file_uid)
    except media.ContentRefused as e:
        raise ValueError("too_large" if "too large" in str(e) else "not_in_production") from None
    if size and size > MAX_BYTES:
        raise ValueError("too_large")
    try:
        with opener() as src:
            data = src.read(MAX_BYTES + 1)
    except MemberDamaged:
        raise ValueError("not_in_production") from None
    except OSError:
        raise ValueError("read_error") from None
    if len(data) > MAX_BYTES:
        raise ValueError("too_large")
    return data


def run_pending(engine, limit=BATCH) -> list:
    """Hash up to ``limit`` waiting pictures (oldest cases first). Returns one entry per picture handled."""
    todo = []
    now = time.monotonic()
    with engine.connect() as c:
        for case in cases_to_hash(c):
            if _idle_until.get(case, 0) > now:
                continue  # found complete a moment ago: looked at again after RESCAN_SECONDS
            got = c.execute(text(_eligible_sql() + " ORDER BY f.extraction_id, f.file_uid LIMIT :l"),
                            _params(c=case, l=limit - len(todo))).fetchall()
            if not got:
                _idle_until[case] = now + RESCAN_SECONDS
            todo += got
            if len(todo) >= limit:
                break
    done = []
    for f in todo:
        t0 = time.process_time()
        try:
            with engine.connect() as c:
                data = read_bytes(c, f.case_id, f.file_uid)
            ph, dh = hashes(data)
            _store(engine, f, "done", ph, dh, cpu_ms=int((time.process_time() - t0) * 1000))
            done.append({"file_uid": str(f.file_uid), "state": "done"})
        except ValueError as e:
            reason = str(e) if str(e) in REASON_WORDS else "cannot_open"
            _store(engine, f, "failed", reason=reason, cpu_ms=int((time.process_time() - t0) * 1000))
            done.append({"file_uid": str(f.file_uid), "state": "failed", "reason": reason})
        except Exception:  # noqa: BLE001 - one picture never stops the turn; it is tried again next turn
            log.exception("perceptual hash of %s failed", f.file_uid)
            _store(engine, f, "failed", reason="read_error")
            done.append({"file_uid": str(f.file_uid), "state": "failed", "reason": "read_error"})
    return done
