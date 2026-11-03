"""Image search by description over a case's phone images, on this server (05 section 17.6).

A person starts "Index this case's images for search" from the Media screen. Every image in the search population
is read once, its bytes hashed, and embedded by a local image-text model (``image_search_models``: SigLIP 2 base
at a pinned revision, Apache-2.0). A text typed into "Find images by description" is embedded by the same model
and the case's images are ranked by cosine similarity to it. A result is a pointer to an image, not a statement
about it: it is labelled "Machine-ranked by <model> <revision>", its score is shown only as a rank, and it opens to
the image, the phones holding it and the messages that carried it.

Rules carried here:

- **Population (05 17.6: approach 8's population plus camera files).** Files the report categorises as Image that
  are (a) linked to a message by a resolved, unambiguous attachment reference, or (b) in a camera or screenshot
  folder (``CAMERA_DIRS``, matched on the file's original ``path`` attribute or its local path), or (c) whose
  metadata names a camera make or model (``EXIF_CAMERA_ITEMS``). (b) and (c) are the camera files. The predicate
  is ``POPULATION_SQL``, built from approach 8's predicate in ``media_spread`` (05 section 11.3 step 1). Videos are
  not indexed: no frame is taken from a video in this build.
- **One embedding per content.** Vectors are stored per (case, SHA-256 of the bytes, model weights). A file whose
  bytes were already embedded (another copy on any phone of the case) is linked to that vector and not embedded
  again ("reused"). The hash is the file's verified ``disk_sha256`` when present, else computed while reading.
- **True counts.** ``describe`` counts the case's images and what indexing leaves out, by reason: not in the search
  population, not in the production, an empty placeholder, could not be opened by an earlier run (HEIC, not a
  picture, damaged), already indexed, already waiting. A job counts its files by state and its failures by reason.
- **Nothing leaves the server.** The model runs in a child process (``python -I``) that refuses every outbound
  connection before it loads anything (``derive.GUARD``), with a memory cap, a time limit and the Hugging Face
  offline switches set; image paths and the query text go to it on standard input. A model that is not on disk is
  refused in words and never downloaded.
- **Search time.** Loading the libraries and the text model takes about 30 s on this server, a description then
  about 1 to 2 s (measured 3 Nov under load), so the text model stays loaded in its child between searches and the
  child stops after ``LOUPE_IMAGE_QUERY_IDLE_SECONDS`` (default 600; 0 runs a child per description). A search
  waits at most ``BUSY_WAIT_SECONDS`` for its turn and the child at most ``ANSWER_TIMEOUT_SECONDS`` for an answer;
  past either the person is told in words and a stuck child is killed.
- **Scoring memory.** Every indexed picture of the case is scored, in this process, ``SCORE_CHUNK`` vectors at a
  time from a server-side cursor with a running top list, and at most ``SEARCH_SLOTS`` searches score at once per
  process. Measured on 35,000 synthetic vectors (3 Nov): peak 25.5 MB and 3.3 to 4.2 s, against 228.6 MB and
  1.5 to 1.9 s when every vector was loaded at once. The result says how many distinct pictures and files were
  scored and how many pictures are shown.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from sqlalchemy import text

from services.phone import derive
from services.phone import media_spread as S
from services.phone import image_search_models as M

log = logging.getLogger(__name__)

NO_MODEL = "The image search model is not installed on this server. Nothing was sent anywhere."
NO_PROGRAM = "The image search program is not installed on this server. Nothing was sent anywhere."
POINTER_WORDS = "a result points to an image, it does not describe it."

# Approach 8's population (05 11.3 step 1), one statement in media_spread: carried by a message (``c`` is
# media._CARRIED: resolved, unambiguous attachment links), in a camera or screenshot folder, or EXIF names a camera
CAMERA_DIRS, CAMERA_RE, EXIF_CAMERA_ITEMS = S.CAMERA_DIRS, S.CAMERA_RE, S.EXIF_CAMERA_ITEMS
POPULATION_SQL = "(c.file_uid IS NOT NULL OR %s OR %s)" % (S.CAMERA_PATH_SQL, S.EXIF_CAMERA_SQL)
IMAGE_SQL = "coalesce(f.category, '') = 'Image'"
PRESENT_SQL = "(f.disk_relpath IS NOT NULL AND coalesce(f.verification, '') <> 'missing')"
# "unreadable" is no longer given: until 3 Nov it also covered a picture the model failed on after the library had
# opened it (a picture 1 or 3 pixels high was taken for one in channels-first order), so a file left out with it is
# offered again; "cannot_open" is the library's refusal, and "model_error" the model's, which another attempt may change.
PERMANENT = ("heic", "not_image", "cannot_open", "too_large", "empty")

REASON_WORDS = {
    "heic": "Stored as HEIC, which the image library on this server cannot open.",
    "not_image": "Its contents are not a picture (its first bytes name %s).",
    "cannot_open": "The image library could not open it: it may be damaged, or in a format the library does not read.",
    "unreadable": "It could not be read by the image library or the image search model.",
    "model_error": "The image search model could not read this picture. The original is unchanged.",
    "too_large": "Too large to open safely (more pixels than the image library allows).",
    "empty": "The file holds no bytes.",
    "not_in_production": "The file could not be read from the production.",
    "no_model": NO_MODEL,
    "stopped": "Indexing this file stopped twice; it may be too large or damaged. The original is unchanged.",
    "timeout": "Indexing this file took too long and was stopped. The original is unchanged.",
    "error": "This file could not be indexed. The original is unchanged.",
}

# One child per draw: starting the child and loading the libraries and the vision model took 16 to 27 s on this
# server under load, then 0.4 to 2.5 s per 1600 x 1200 photo on 2 threads (measured 3 Nov: 32 photos in one child
# 40 to 94 s), so 32 waiting images are drawn together. A draw is about as long as a translation draw.
BATCH = 32
MAX_ATTEMPTS = 2
TIMEOUT_SECONDS = 1800
STALE_SECONDS = TIMEOUT_SECONDS + derive.STALE_MARGIN_SECONDS
QUERY_TIMEOUT_SECONDS = 600
TEXT_MAX_TOKENS = 64          # the length SigLIP 2 was trained with; longer text is cut and the result says so
QUERY_MAX_CHARS = 300
RESULTS_MAX = 200
COPIES_PER_RESULT = 20
DRAFT_EDGE = 448              # a JPEG is decoded at a reduced scale no smaller than this before the 224 px resize
THREADS = 2
# The child's address-space cap. The backend's torch is the CUDA build, which reserves about 3.2 GB of address space
# on import (resident 0.5 GB); loading the 1.5 GB vision model on top peaked at 6.43 GB for 32 photos and 6.82 GB for
# a description (measured 3 Nov on this server, resident 1.1 and 1.4 GB), over the 6 GB the other children are given,
# so the model could not be mapped. This cap is half as much again as the larger peak.
MEMORY_MB = int(os.environ.get("LOUPE_PHONE_IMAGE_MEMORY_MB", "10240"))
# the kept-warm text child: starting it loads the libraries and the text model (about 31 s measured under load), one
# description then takes 1 to 2 s; past these deadlines the child is killed and the person told in words
READY_TIMEOUT_SECONDS = 180
ANSWER_TIMEOUT_SECONDS = 60
# how long a search waits for its turn (on the text child, or for a scoring slot) before it is told to try again
BUSY_WAIT_SECONDS = 45
# scoring reads the case's vectors this many at a time and keeps a running top list, so a search holds at most one
# chunk (2,000 x 768 x 4 bytes, about 6 MB) whatever the case's size; at most this many searches score at once
SCORE_CHUNK = 2000
SEARCH_SLOTS = 2


class ImageSearchError(ValueError):
    pass


class ImageSearchBusy(ImageSearchError):
    """Too many searches at once in this server process; the person is told to try again (HTTP 503)."""


BUSY_WORDS = "Another search is running; try again in a moment."
TOO_LONG_WORDS = "The image search model took too long and was stopped. Nothing was sent anywhere."
STOPPED_WORDS = "The image search model stopped. Try the search again. Nothing was sent anywhere."
COULD_NOT_RUN = "The image search model could not run. Nothing was sent anywhere."


def parameters() -> dict:
    return {"image_size": 224, "resize": "bilinear to 224 x 224 (the model's processor)",
            "jpeg_draft_min_edge": DRAFT_EDGE, "exif_orientation": "applied", "colour": "RGB",
            "text_lowercased": True, "text_padding": "max_length", "text_max_tokens": TEXT_MAX_TOKENS,
            "similarity": "cosine of unit-length vectors", "device": "cpu", "threads": THREADS}


def identity() -> dict:
    """The installed model's identity, or ``ImageSearchError(NO_MODEL)``. The weights hash is of the file on disk,
    computed once per process (``phone_media().weights_sha256`` caches it by size and modification time)."""
    if not M.installed():
        raise ImageSearchError(NO_MODEL)
    return M.identity(derive.phone_media().weights_sha256)


def label(ident: dict) -> str:
    return "Machine-ranked by %s %s; %s" % (ident["model"], ident["revision_short"], POINTER_WORDS)


# ---- the population and its counts ----------------------------------------------------------------------------------

def _base() -> str:
    from services.phone import media
    return ("FROM pv_file f JOIN phone_files pf ON pf.file_uid = f.file_uid LEFT JOIN (%s) c ON c.file_uid = "
            "f.file_uid WHERE f.case_id = :c" % media._CARRIED)


def _params(case_id, **extra) -> dict:
    p = {"c": str(case_id), "cam": CAMERA_RE, "exif_cam": list(EXIF_CAMERA_ITEMS), "perm": list(PERMANENT)}
    p.update(extra)
    return p


_INDEXED = ("EXISTS (SELECT 1 FROM phone_image_index_items i WHERE i.case_id = f.case_id AND i.file_uid = f.file_uid "
            "AND i.state = 'done' AND i.weights_sha256 = :w)")
_WAITING = ("EXISTS (SELECT 1 FROM phone_image_index_items i WHERE i.case_id = f.case_id AND i.file_uid = f.file_uid "
            "AND i.state IN ('queued', 'running'))")
# the file's latest finished attempt failed for a reason that another attempt would not change
_LATEST_REASON = ("(SELECT i.reason FROM phone_image_index_items i WHERE i.case_id = f.case_id AND i.file_uid = "
                  "f.file_uid AND i.state IN ('done', 'failed') ORDER BY i.finished_at DESC NULLS LAST, i.id LIMIT 1)")
_COULD_NOT_OPEN = "coalesce(%s = ANY(:perm), false)" % _LATEST_REASON
# an indexed file the search ranks: in the population and the production (the "indexed" count of ``describe``)
SEARCHABLE_SQL = ("%s AND %s AND %s AND coalesce(f.verification, '') <> 'empty_placeholder'"
                  % (IMAGE_SQL, POPULATION_SQL, PRESENT_SQL))
ELIGIBLE_SQL = ("%s AND %s AND %s AND coalesce(f.verification, '') <> 'empty_placeholder' AND NOT %s AND NOT %s AND "
                "NOT %s" % (IMAGE_SQL, POPULATION_SQL, PRESENT_SQL, _INDEXED, _WAITING, _COULD_NOT_OPEN))


def describe(conn, case_id) -> dict:
    """True counts for "Index this case's images for search": the images it would index and every image it leaves
    out, by reason, plus whether the model is installed (nothing can start without it)."""
    try:
        ident = identity()
    except ImageSearchError:
        ident = None
    w = ident["weights_sha256"] if ident else "-"
    pop = "%s AND %s" % (IMAGE_SQL, POPULATION_SQL)
    present = "%s AND %s AND coalesce(f.verification, '') <> 'empty_placeholder'" % (pop, PRESENT_SQL)
    r = conn.execute(text(
        "SELECT count(*) FILTER (WHERE " + IMAGE_SQL + ") AS images, "
        "count(*) FILTER (WHERE " + IMAGE_SQL + " AND NOT " + POPULATION_SQL + ") AS not_in_population, "
        "count(*) FILTER (WHERE " + pop + " AND NOT " + PRESENT_SQL + ") AS not_in_production, "
        "count(*) FILTER (WHERE " + pop + " AND " + PRESENT_SQL + " AND f.verification = 'empty_placeholder') "
        "AS placeholder, "
        "count(*) FILTER (WHERE " + present + " AND " + _INDEXED + ") AS indexed, "
        "count(*) FILTER (WHERE " + present + " AND NOT " + _INDEXED + " AND " + _WAITING + ") AS waiting, "
        "count(*) FILTER (WHERE " + present + " AND NOT " + _INDEXED + " AND NOT " + _WAITING + " AND " +
        _COULD_NOT_OPEN + ") AS could_not_open, "
        "count(*) FILTER (WHERE " + ELIGIBLE_SQL + ") AS eligible, "
        "count(*) FILTER (WHERE coalesce(f.category, '') IN ('', 'Uncategorized')) AS uncategorised " + _base()),
        _params(case_id, w=w)).one()
    reasons = {}
    if r.could_not_open:
        # the same files as the total: in the population and the production, not indexed, not waiting
        for reason, n in conn.execute(text(
                "SELECT x.reason, count(*) FROM (SELECT " + _LATEST_REASON + " AS reason " + _base() + " AND " +
                present + " AND NOT " + _INDEXED + " AND NOT " + _WAITING + ") x WHERE x.reason = ANY(:perm) "
                "GROUP BY 1"), _params(case_id, w=w)):
            reasons[reason] = int(n)
    vectors = indexed_counts(conn, case_id, w)["pictures"]
    return {"images": int(r.images), "eligible": int(r.eligible), "indexed": int(r.indexed),
            "indexed_contents": vectors, "waiting": int(r.waiting),
            "left_out": {"not_in_population": int(r.not_in_population), "not_in_production": int(r.not_in_production),
                         "empty_placeholder": int(r.placeholder), "could_not_open": int(r.could_not_open),
                         "could_not_open_by_reason": reasons},
            "uncategorised_files": int(r.uncategorised),
            "model_installed": ident is not None, "model_words": None if ident else NO_MODEL,
            "model": ident["model"] if ident else None, "model_id": ident["model_id"] if ident else None,
            "revision_short": ident["revision_short"] if ident else None,
            "population_words": POPULATION_WORDS}


POPULATION_WORDS = ("Images sent or received in a message, in a camera or screenshot folder, or whose metadata names "
                    "a camera are indexed; other images on the phones (mostly app and system pictures) are left out. "
                    "Videos are not indexed.")


# ---- jobs ---------------------------------------------------------------------------------------------------------------

def create(conn, *, case_id, user_id) -> dict:
    """Queue one indexing row per eligible image in one statement; the job's total is the number of rows queued."""
    ident = identity()
    # one request at a time per case: a second one waits here, then finds nothing eligible and is told so
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('phone_image_index:' || :c))"), {"c": str(case_id)})
    facts = describe(conn, case_id)
    if not facts["eligible"]:
        raise ImageSearchError("Every image in this case's search population is already indexed, waiting, or "
                               "cannot be indexed; nothing was queued.")
    job = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_image_index_jobs (id, case_id, left_out, model_id, weights_sha256, created_by_user_id) "
        "VALUES (:j, :c, CAST(:l AS jsonb), :m, :w, :u)"),
        {"j": job, "c": str(case_id), "l": json.dumps(dict(facts["left_out"], already_indexed=facts["indexed"],
                                                           already_waiting=facts["waiting"])),
         "m": ident["model_id"], "w": ident["weights_sha256"], "u": str(user_id) if user_id else None})
    queued = conn.execute(text(
        "INSERT INTO phone_image_index_items (id, job_id, case_id, extraction_id, file_uid) "
        "SELECT gen_random_uuid(), :j, f.case_id, f.extraction_id, f.file_uid " + _base() + " AND " + ELIGIBLE_SQL +
        " ON CONFLICT (case_id, file_uid) WHERE state IN ('queued', 'running') DO NOTHING"),
        _params(case_id, j=job, w=ident["weights_sha256"])).rowcount
    if not queued:
        raise ImageSearchError("Every image in this case's search population is already indexed, waiting, or "
                               "cannot be indexed; nothing was queued.")
    conn.execute(text("UPDATE phone_image_index_jobs SET total = :n WHERE id = :j"), {"n": queued, "j": job})
    return get(conn, case_id, job)


_STATUS = (
    "SELECT j.*, count(i.id) FILTER (WHERE i.state = 'done') AS done, "
    "count(i.id) FILTER (WHERE i.outcome = 'reused') AS reused, "
    "count(i.id) FILTER (WHERE i.state = 'failed') AS failed, count(i.id) FILTER (WHERE i.state = 'queued') AS queued, "
    "count(i.id) FILTER (WHERE i.state = 'running') AS running, min(i.started_at) AS first_started, "
    "max(i.finished_at) AS last_finished "
    "FROM phone_image_index_jobs j LEFT JOIN phone_image_index_items i ON i.job_id = j.id WHERE j.case_id = :c %s "
    "GROUP BY j.id ORDER BY j.created_at DESC")


def _failed_by_reason(conn, job_ids) -> dict:
    out = {}
    if not job_ids:
        return out
    for j, reason, n in conn.execute(text(
            "SELECT job_id, reason, count(*) FROM phone_image_index_items WHERE job_id = ANY(:j) AND state = 'failed' "
            "GROUP BY 1, 2"), {"j": list(job_ids)}):
        out.setdefault(str(j), {})[reason] = int(n)
    return out


def _row(r, reasons) -> dict:
    total, done, failed, queued, running = int(r.total), int(r.done), int(r.failed), int(r.queued), int(r.running)
    finished = (r.cancelled_at is not None and not running) or (queued + running == 0)
    return {"id": str(r.id), "total": total, "done": done, "embedded": done - int(r.reused), "reused": int(r.reused),
            "failed": failed, "failed_by_reason": reasons.get(str(r.id), {}), "queued": queued, "running": running,
            "cancelled": r.cancelled_at is not None, "cancelled_count": int(r.cancelled_count),
            "left_out": r.left_out or {}, "model_id": r.model_id,
            "state": "cancelled" if r.cancelled_at is not None and finished else "done" if finished else "running",
            "created_at": r.created_at.isoformat(),
            "first_started_at": r.first_started.isoformat() if r.first_started else None,
            "last_finished_at": r.last_finished.isoformat() if r.last_finished else None,
            "noun": "image" if total == 1 else "images"}


def get(conn, case_id, job_id) -> dict | None:
    r = conn.execute(text(_STATUS % "AND j.id = :j"), {"c": str(case_id), "j": str(job_id)}).one_or_none()
    return _row(r, _failed_by_reason(conn, [r.id])) if r is not None else None


def status(conn, case_id, limit=20) -> list:
    rows = conn.execute(text(_STATUS % "" + " LIMIT :l"), {"c": str(case_id), "l": limit}).fetchall()
    reasons = _failed_by_reason(conn, [r.id for r in rows])
    return [_row(r, reasons) for r in rows]


def cancel(conn, case_id, job_id) -> dict:
    j = conn.execute(text("SELECT id FROM phone_image_index_jobs WHERE id = :j AND case_id = :c FOR UPDATE"),
                     {"j": str(job_id), "c": str(case_id)}).one_or_none()
    if j is None:
        raise LookupError("That indexing job is not in this case.")
    gone = conn.execute(text("DELETE FROM phone_image_index_items WHERE job_id = :j AND state = 'queued'"),
                        {"j": str(job_id)}).rowcount
    conn.execute(text("UPDATE phone_image_index_jobs SET cancelled_at = coalesce(cancelled_at, now()), "
                      "cancelled_count = cancelled_count + :n WHERE id = :j"), {"n": gone, "j": str(job_id)})
    return get(conn, case_id, job_id)


# ---- the child ----------------------------------------------------------------------------------------------------------

# One script for both uses. An image draw reads one request line and answers once. A text request either answers
# once, or (``serve``) loads the text model once, says it is ready, then answers one description per line until its
# standard input closes, so a search does not pay the libraries' load time (about 30 s on this server) each time.
_CHILD = derive.GUARD + r'''
import json, os, resource, sys
mb = int(os.environ.get("LOUPE_PHONE_IMAGE_MEMORY_MB", "10240"))
resource.setrlimit(resource.RLIMIT_AS, (mb * 1024 * 1024, mb * 1024 * 1024))
from importlib import metadata
req = json.loads(sys.stdin.readline())
import torch
torch.set_num_threads(int(os.environ.get("OMP_NUM_THREADS", "2")))
from transformers.utils import logging as hf_logging
hf_logging.set_verbosity_error()
out = {"transformers_version": metadata.version("transformers"), "torch_version": metadata.version("torch")}
if req["mode"] == "text":
    from transformers import AutoTokenizer, SiglipTextModel
    tok = AutoTokenizer.from_pretrained(req["model"], local_files_only=True)
    model = SiglipTextModel.from_pretrained(req["model"], local_files_only=True).eval()

    def embed(value):
        q = value.lower()
        n = len(tok(q, truncation=False)["input_ids"])
        enc = tok([q], padding="max_length", max_length=req["max_tokens"], truncation=True, return_tensors="pt")
        with torch.inference_mode():
            v = torch.nn.functional.normalize(model(**enc).pooler_output, dim=-1)[0]
        return dict(out, vector=[float(x) for x in v], tokens=n, truncated=n > req["max_tokens"])
    if req.get("serve"):
        print(json.dumps(dict(out, ready=True)), flush=True)
        for line in sys.stdin:
            print(json.dumps(embed(json.loads(line)["text"])), flush=True)
        sys.exit(0)
    out = embed(req["text"])
else:
    from PIL import Image, ImageOps
    from transformers import AutoImageProcessor, SiglipVisionModel
    out["pillow_version"] = metadata.version("Pillow")
    proc = AutoImageProcessor.from_pretrained(req["model"], local_files_only=True)
    model = SiglipVisionModel.from_pretrained(req["model"], local_files_only=True).eval()
    results = []
    for path in req["images"]:
        try:
            with Image.open(path) as im:
                im.draft("RGB", (req["draft"], req["draft"]))
                im = ImageOps.exif_transpose(im)
                im = im.convert("RGB")
        except Image.DecompressionBombError as e:
            results.append({"reason": "too_large", "detail": str(e)[:200]})
            continue
        except Exception as e:
            results.append({"reason": "cannot_open", "detail": ("%s: %s" % (type(e).__name__, e))[:200]})
            continue
        try:
            # an RGB picture is height x width x 3: said, not guessed from the shape (a picture 1 or 3 pixels high
            # was otherwise taken as channels-first and refused)
            px = proc(images=[im], input_data_format="channels_last", return_tensors="pt")
            with torch.inference_mode():
                v = torch.nn.functional.normalize(model(**px).pooler_output, dim=-1)[0]
            results.append({"vector": [float(x) for x in v]})
        except Exception as e:
            results.append({"reason": "model_error", "detail": ("%s: %s" % (type(e).__name__, e))[:200]})
    out["results"] = results
print(json.dumps(out))
'''


def _child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME")}
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": str(THREADS), "TOKENIZERS_PARALLELISM": "false",
                "LOUPE_PHONE_IMAGE_MEMORY_MB": str(MEMORY_MB)})
    return env


def _child_words(err: str) -> str:
    if any("No module named '%s'" % m in err for m in ("transformers", "torch", "PIL", "tokenizers")):
        return NO_PROGRAM
    log.warning("image search child failed: %s", (err.strip().splitlines() or [""])[-1][:200])
    return "The image search model could not run. Nothing was sent anywhere."


def run_child(request: dict, timeout: int) -> dict:
    """Run the model once on this server in an isolated child. ``request`` goes on standard input."""
    if not M.installed():
        raise ImageSearchError(NO_MODEL)
    payload = json.dumps(dict(request, model=str(M.model_dir())))
    r = subprocess.run([sys.executable, "-I", "-c", _CHILD], input=payload + "\n", capture_output=True, text=True,
                       timeout=timeout, env=_child_env())
    if r.returncode != 0:
        raise ImageSearchError(_child_words(r.stderr or ""))
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---- indexing (the worker) ----------------------------------------------------------------------------------------------

def _claim(engine, limit=BATCH):
    """Up to ``limit`` waiting rows of one case (one alone when it is to be drawn again by itself), marked running."""
    while True:
        with engine.begin() as c:
            rows = c.execute(text(
                "SELECT id, state, attempts, case_id, solo FROM phone_image_index_items WHERE state = 'queued' OR "
                "(state = 'running' AND started_at < now() - make_interval(secs => :s)) ORDER BY created_at, id "
                "FOR UPDATE SKIP LOCKED LIMIT :n"), {"s": STALE_SECONDS, "n": limit}).fetchall()
            if not rows:
                return []
            stopped = [r.id for r in rows if r.state == "running" and r.attempts >= MAX_ATTEMPTS]
            if stopped:
                c.execute(text("UPDATE phone_image_index_items SET state = 'failed', reason = 'stopped', error = :e, "
                               "finished_at = now() WHERE id = ANY(:i)"), {"e": REASON_WORDS["stopped"], "i": stopped})
                continue
            first = rows[0]
            take = [first.id] if first.solo else [r.id for r in rows if r.case_id == first.case_id and not r.solo]
            return c.execute(text(
                "UPDATE phone_image_index_items SET state = 'running', started_at = clock_timestamp(), error = NULL, "
                "reason = NULL, attempts = attempts + 1 WHERE id = ANY(:i) RETURNING id, case_id, file_uid, "
                "started_at"), {"i": take}).fetchall()


def _fail(engine, job, reason, words=None):
    with engine.begin() as c:
        c.execute(text("UPDATE phone_image_index_items SET state = 'failed', reason = :r, error = :e, finished_at = "
                       "now() WHERE id = :i AND state = 'running' AND started_at = :t"),
                  {"r": reason, "e": words or REASON_WORDS[reason], "i": job.id, "t": job.started_at})
    return {"id": str(job.id), "state": "failed", "reason": reason}


def _done(engine, job, sha, ident, outcome, container=None, vector=None):
    """Store the vector (once per content: a copy embedded at the same moment keeps the first) and link the file."""
    with engine.begin() as c:
        if vector is not None:
            import numpy as np
            v = np.asarray(vector, dtype="<f4")
            c.execute(text(
                "INSERT INTO phone_image_vectors (id, case_id, content_sha256, model_id, weights_sha256, dim, vector, "
                "parameters) VALUES (:i, :c, :h, :m, :w, :d, :v, CAST(:p AS jsonb)) ON CONFLICT (case_id, "
                "content_sha256, weights_sha256) DO NOTHING"),
                {"i": uuid.uuid4(), "c": str(job.case_id), "h": sha, "m": ident["model_id"],
                 "w": ident["weights_sha256"], "d": int(v.shape[0]), "v": v.tobytes(),
                 "p": json.dumps(dict(parameters(), **{k: ident.get(k) for k in ("transformers_version",
                                                                                 "torch_version", "pillow_version")}))})
        c.execute(text("UPDATE phone_image_index_items SET state = 'done', outcome = :o, content_sha256 = :h, "
                       "weights_sha256 = :w, sniffed_container = coalesce(:sc, sniffed_container), finished_at = now() "
                       "WHERE id = :i AND state = 'running' AND started_at = :t"),
                  {"o": outcome, "h": sha, "w": ident["weights_sha256"], "sc": container, "i": job.id,
                   "t": job.started_at})
    return {"id": str(job.id), "state": "done", "outcome": outcome}


def _has_vector(engine, case_id, sha, weights) -> bool:
    with engine.connect() as c:
        return c.execute(text("SELECT 1 FROM phone_image_vectors WHERE case_id = :c AND content_sha256 = :h AND "
                              "weights_sha256 = :w"), {"c": str(case_id), "h": sha, "w": weights}).first() is not None


def _read(engine, job, folder):
    """Copy one file's bytes into ``folder``, hashing them. Returns (path, sha256, container) or raises
    ``ImageSearchError`` with the reason code as its ``reason`` attribute."""
    from services.phone import media
    from services.phone.archive_member import MemberDamaged
    pm = derive.phone_media()
    path = Path(folder) / ("%s" % job.id)
    h = hashlib.sha256()
    size = 0
    try:
        with engine.connect() as c:
            name, _size, opener = media.content(c, job.case_id, job.file_uid)
        with opener() as src, open(path, "wb") as dst:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                size += len(chunk)
                dst.write(chunk)
    except (media.ContentRefused, MemberDamaged) as e:
        raise _Refused("not_in_production", str(e)) from None
    if size == 0:
        raise _Refused("empty")
    found = pm.kind_of(path, name)
    if found.recognised and found.container != "by-name":
        if found.container == "heif":
            raise _Refused("heic")
        if found.kind != "image":
            raise _Refused("not_image", REASON_WORDS["not_image"] % ("a %s file" % found.container.upper()))
    container = "unrecognised" if found.container == "by-name" else found.container
    return path, h.hexdigest(), container


class _Refused(Exception):
    def __init__(self, reason, words=None):
        super().__init__(words or REASON_WORDS[reason])
        self.reason, self.words = reason, words or REASON_WORDS[reason]


def run_pending(engine, limit=BATCH) -> list:
    """Draw up to ``limit`` waiting files of one case and index them with one child process: each file ends done
    (embedded, or linked to the vector of the same bytes already embedded) or failed with its reason."""
    jobs = _claim(engine, limit)
    if not jobs:
        return []
    derive.phone_media().provider_for("image_search")
    try:
        ident = identity()
    except ImageSearchError:
        return [_fail(engine, j, "no_model") for j in jobs]
    out, work = [], []
    disk = {}
    with engine.connect() as c:
        for r in c.execute(text("SELECT file_uid, disk_sha256 FROM phone_files WHERE file_uid = ANY(:u)"),
                           {"u": [j.file_uid for j in jobs]}):
            disk[str(r.file_uid)] = (r.disk_sha256 or "").strip().lower() or None
    with tempfile.TemporaryDirectory(prefix="loupe-imgidx-") as folder:
        for job in jobs:
            known = disk.get(str(job.file_uid))
            # the verified hash of the bytes already embedded in this case: the file is linked, not read again
            if known and _has_vector(engine, job.case_id, known, ident["weights_sha256"]):
                out.append(_done(engine, job, known, ident, "reused"))
                continue
            try:
                path, sha, container = _read(engine, job, folder)
            except _Refused as e:
                out.append(_fail(engine, job, e.reason, e.words))
                continue
            except Exception:  # noqa: BLE001
                out.append(_fail(engine, job, "error", _reference_words("reading")))
                continue
            if _has_vector(engine, job.case_id, sha, ident["weights_sha256"]):
                out.append(_done(engine, job, sha, ident, "reused", container))
                continue
            work.append((job, path, sha, container))
        if not work:
            return out
        # one embedding per content in this draw too: the first file of each content is embedded
        first = {}
        for job, path, sha, container in work:
            first.setdefault(sha, (job, path))
        paths = [p for _, p in first.values()]
        try:
            got = run_child({"mode": "image", "images": [str(p) for p in paths], "draft": DRAFT_EDGE},
                            TIMEOUT_SECONDS)
            results = got["results"]
            if len(results) != len(paths):
                raise ImageSearchError("The image search model could not run. Nothing was sent anywhere.")
        except Exception as e:  # noqa: BLE001
            return out + _child_failed(engine, work, e)
        ident = dict(ident, transformers_version=got.get("transformers_version"),
                     torch_version=got.get("torch_version"), pillow_version=got.get("pillow_version"))
        by_sha = dict(zip(first, results))
        made = set()
        for job, path, sha, container in work:
            res = by_sha[sha]
            if "vector" not in res:
                reason = res.get("reason") if res.get("reason") in REASON_WORDS else "model_error"
                if reason == "model_error":
                    log.warning("image search model failed on item %s: %s", job.id, str(res.get("detail"))[:200])
                out.append(_fail(engine, job, reason))
            elif sha in made:
                out.append(_done(engine, job, sha, ident, "reused", container))
            else:
                made.add(sha)
                out.append(_done(engine, job, sha, ident, "embedded", container, vector=res["vector"]))
    return out


def _reference_words(what) -> str:
    ref = uuid.uuid4().hex[:8]
    log.exception("phone image indexing failed while %s (reference %s)", what, ref)
    return "%s Reference: %s." % (REASON_WORDS["error"], ref)


def _child_failed(engine, work, e) -> list:
    if isinstance(e, ImageSearchError) and str(e) in (NO_MODEL, NO_PROGRAM):
        return [_fail(engine, job, "no_model", str(e)) for job, _, _, _ in work]
    if len(work) > 1:
        # one file may have stopped the whole draw: each is drawn again on its own, so a failure is stated against
        # the file that failed
        with engine.begin() as c:
            for job, _, _, _ in work:
                c.execute(text("UPDATE phone_image_index_items SET state = 'queued', solo = true, attempts = attempts - "
                               "1, started_at = NULL WHERE id = :i AND state = 'running' AND started_at = :t"),
                          {"i": job.id, "t": job.started_at})
        return [{"id": str(job.id), "state": "queued"} for job, _, _, _ in work]
    job = work[0][0]
    if isinstance(e, subprocess.TimeoutExpired):
        return [_fail(engine, job, "timeout")]
    return [_fail(engine, job, "error", _reference_words("embedding"))]


# ---- search -------------------------------------------------------------------------------------------------------------

def query_idle_seconds() -> int:
    """How long the text model stays loaded after a search, in this process. 0: a child per description."""
    try:
        return max(0, int(os.environ.get("LOUPE_IMAGE_QUERY_IDLE_SECONDS", "600")))
    except ValueError:
        return 600


class _TextServer:
    """The text half of the model, kept loaded in one isolated child per server process between searches and
    stopped after ``query_idle_seconds`` without one. It is the same child script, guard and limits as every other
    run; descriptions go to it one per line on its standard input. Searches take turns on it: a search waits at
    most ``BUSY_WAIT_SECONDS`` for its turn, and an answer is waited for at most ``ANSWER_TIMEOUT_SECONDS`` (the
    first, while the model loads, ``READY_TIMEOUT_SECONDS``). A child that misses its deadline, writes something
    that is not an answer, or has stopped is killed and discarded, and the person is told in words; the next search
    starts a fresh one."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.weights = None
        self.err = None
        self.timer = None
        self.buf = b""

    def _start(self, weights):
        import tempfile as _tf
        self._kill()
        self.err = _tf.TemporaryFile()
        self.proc = subprocess.Popen([sys.executable, "-I", "-c", _CHILD], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.err, env=_child_env())
        self.weights, self.buf = weights, b""
        self._send({"mode": "text", "serve": True, "max_tokens": TEXT_MAX_TOKENS, "model": str(M.model_dir())})
        if not self._answer(READY_TIMEOUT_SECONDS).get("ready"):
            self._kill()
            raise ImageSearchError(COULD_NOT_RUN)

    def _send(self, obj):
        try:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode("utf-8"))
            self.proc.stdin.flush()
        except (OSError, ValueError):  # the child has gone (broken pipe, closed stream)
            self._kill()
            raise ImageSearchError(STOPPED_WORDS) from None

    def _answer(self, timeout) -> dict:
        """One answer line, read in chunks with a real deadline: half a line never blocks past it."""
        import select
        import time
        deadline = time.monotonic() + timeout
        fd = self.proc.stdout.fileno()
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0:
                self._kill()
                raise ImageSearchError(TOO_LONG_WORDS)
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                continue
            chunk = os.read(fd, 1 << 16)
            if not chunk:  # the child ended
                words = self._ended_words()
                self._kill()
                raise ImageSearchError(words)
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        try:
            got = json.loads(line)
            if not isinstance(got, dict):
                raise ValueError("not an object")
        except ValueError:
            log.warning("image search text child wrote something that is not an answer (%d bytes)", len(line))
            self._kill()
            raise ImageSearchError(COULD_NOT_RUN) from None
        return got

    def _ended_words(self) -> str:
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        try:
            self.err.seek(0)
            return _child_words(self.err.read().decode("utf-8", "replace"))
        except (OSError, ValueError):
            return COULD_NOT_RUN

    def _kill(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        if self.proc is not None:
            proc, self.proc = self.proc, None
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("image search text child %s did not stop after kill", proc.pid)
            for stream in (proc.stdin, proc.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        if self.err is not None:
            self.err.close()
            self.err = None
        self.buf = b""

    def _idle(self):
        # a search under way re-arms the timer when it finishes; the idle stop never waits for it
        if self.lock.acquire(blocking=False):
            try:
                self._kill()
            finally:
                self.lock.release()

    def vector(self, value: str, weights: str) -> dict:
        idle = query_idle_seconds()
        if idle == 0:
            return run_child({"mode": "text", "text": value, "max_tokens": TEXT_MAX_TOKENS}, QUERY_TIMEOUT_SECONDS)
        if not self.lock.acquire(timeout=BUSY_WAIT_SECONDS):
            raise ImageSearchBusy(BUSY_WORDS)
        try:
            if self.timer is not None:
                self.timer.cancel()
                self.timer = None
            if self.proc is None or self.proc.poll() is not None or self.weights != weights:
                self._start(weights)
            self._send({"text": value})
            got = self._answer(ANSWER_TIMEOUT_SECONDS)
            if not isinstance(got.get("vector"), list):
                self._kill()
                raise ImageSearchError(COULD_NOT_RUN)
            self.timer = threading.Timer(idle, self._idle)
            self.timer.daemon = True
            self.timer.start()
            return got
        finally:
            self.lock.release()


_TEXT = _TextServer()


_QUERY_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_QUERY_LOCK = threading.Lock()
QUERY_CACHE_SIZE = 256


def embed_query(query: str, ident: dict) -> dict:
    """The query's vector from the child, kept in this process for the same text and weights."""
    key = (query.strip().lower(), ident["weights_sha256"])
    with _QUERY_LOCK:
        hit = _QUERY_CACHE.get(key)
        if hit is not None:
            _QUERY_CACHE.move_to_end(key)
            return hit
    got = _TEXT.vector(query.strip(), ident["weights_sha256"])
    with _QUERY_LOCK:
        _QUERY_CACHE[key] = got
        while len(_QUERY_CACHE) > QUERY_CACHE_SIZE:
            _QUERY_CACHE.popitem(last=False)
    return got


_SEARCH_SLOTS = threading.BoundedSemaphore(SEARCH_SLOTS)

# the files the search ranks, each linked to its content: finished with these weights, and still in the population
# and the production on an active phone; the same files ``describe`` counts as indexed
_LINKED = ("SELECT DISTINCT i.content_sha256, i.file_uid FROM phone_image_index_items i WHERE i.case_id = :c AND "
           "i.state = 'done' AND i.weights_sha256 = :w AND i.file_uid IN (SELECT f.file_uid " + "%s" + " AND " +
           SEARCHABLE_SQL + ")")


def _linked_sql() -> str:
    return _LINKED % _base()


def indexed_counts(conn, case_id, weights) -> dict:
    """What a search ranks: distinct pictures (contents), and the files holding them."""
    r = conn.execute(text("SELECT count(DISTINCT content_sha256) AS pictures, count(DISTINCT file_uid) AS files "
                          "FROM (" + _linked_sql() + ") x"), _params(case_id, w=weights)).one()
    return {"pictures": int(r.pictures), "files": int(r.files)}


def _vector_chunks(conn, case_id, weights, dim_check=None):
    """The ranked pictures' vectors, ``SCORE_CHUNK`` at a time in content-hash order, from a server-side cursor:
    (hashes, float32 matrix) per chunk, so only one chunk is held at once."""
    import numpy as np
    res = conn.execution_options(stream_results=True, yield_per=SCORE_CHUNK).execute(text(
        "SELECT v.content_sha256, v.dim, v.vector FROM phone_image_vectors v WHERE v.case_id = :c AND "
        "v.weights_sha256 = :w AND v.content_sha256 IN (SELECT content_sha256 FROM (" + _linked_sql() + ") x) "
        "ORDER BY v.content_sha256"), _params(case_id, w=weights))
    try:
        for part in res.partitions(SCORE_CHUNK):
            dim = int(part[0].dim)
            mat = np.empty((len(part), dim), dtype="<f4")
            for j, r in enumerate(part):
                mat[j] = np.frombuffer(r.vector, dtype="<f4", count=dim)
            yield [r.content_sha256 for r in part], mat
    finally:
        res.close()


def scores_of(mat, qv):
    """Cosine scores of unit vectors, in float64 rounded to 9 places, so equal pictures score exactly equal whichever
    chunk they are scored in (ties then go by content hash)."""
    import numpy as np
    return np.round(np.asarray(mat, dtype=np.float64) @ np.asarray(qv, dtype=np.float64), 9)


def top_k(parts, qv, k) -> list:
    """The ``k`` highest-scoring hashes over chunks given in content-hash order, highest first, equal scores in
    hash order: a running top list merged with each chunk, so memory is one chunk plus ``k``."""
    import numpy as np
    best_s, best_i, best_h = np.empty(0), np.empty(0, dtype=np.int64), []
    offset = 0
    for shas, mat in parts:
        if not len(shas):
            continue
        s = scores_of(mat, qv)
        all_s = np.concatenate([best_s, s])
        all_i = np.concatenate([best_i, np.arange(offset, offset + len(shas), dtype=np.int64)])
        all_h = best_h + list(shas)
        offset += len(shas)
        keep = np.lexsort((all_i, -all_s))[:k]
        best_s, best_i, best_h = all_s[keep], all_i[keep], [all_h[j] for j in keep]
    return best_h


def search(conn, case_id, query: str, limit: int = 24) -> dict:
    """Rank the case's indexed pictures by similarity to ``query``. Every indexed picture is scored; the first
    ``limit`` are returned with the number scored (distinct pictures, and the files holding them), so a partial
    list is never presented as the whole. Each result is one picture with every indexed copy of it (phone, file,
    messages). At most ``SEARCH_SLOTS`` searches score at once in this process; another is told to try again."""
    import numpy as np
    q = (query or "").strip()
    if not q:
        raise ImageSearchError("Type a description to search for.")
    if len(q) > QUERY_MAX_CHARS:
        raise ImageSearchError("A description is at most %d characters." % QUERY_MAX_CHARS)
    limit = max(1, min(RESULTS_MAX, int(limit)))
    ident = identity()
    if not _SEARCH_SLOTS.acquire(timeout=BUSY_WAIT_SECONDS):
        raise ImageSearchBusy(BUSY_WORDS)
    try:
        counts = indexed_counts(conn, case_id, ident["weights_sha256"])
        facts = describe(conn, case_id)
        base = {"query": q, "label": label(ident), "model": ident["model"], "model_id": ident["model_id"],
                "revision_short": ident["revision_short"], "weights_sha256": ident["weights_sha256"],
                "provider_words": derive.provider_words("local"), "scored": counts["pictures"],
                "scored_files": counts["files"], "coverage": facts, "results": [], "truncated_query": False}
        if not counts["pictures"]:
            return dict(base, shown=0)
        got = embed_query(q, ident)
        qv = np.asarray(got["vector"], dtype="<f4")
        top = top_k(_vector_chunks(conn, case_id, ident["weights_sha256"]), qv, limit)
        copies = _copies(conn, case_id, top, ident["weights_sha256"])
    finally:
        _SEARCH_SLOTS.release()
    results = []
    for rank, sha in enumerate(top, start=1):
        cs = copies.get(sha, [])
        results.append({"rank": rank, "content_sha256": sha, "copy_count": len(cs),
                        "copies": cs[:COPIES_PER_RESULT],
                        "phones": sorted({c["phone_label"] for c in cs})})
    return dict(base, shown=len(results), results=results, truncated_query=bool(got.get("truncated")),
                truncated_words=("Only the first %d word pieces of the description were used." % TEXT_MAX_TOKENS)
                if got.get("truncated") else None)


def _copies(conn, case_id, shas, weights) -> dict:
    from services.phone import media
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    out = {}
    for r in conn.execute(text(
            "SELECT DISTINCT ON (i.content_sha256, f.file_uid) i.content_sha256, f.file_uid, f.extraction_id, "
            "f.local_path, f.category, coalesce(c.messages, 0) AS messages FROM (" + _linked_sql() + ") i JOIN "
            "pv_file f ON f.file_uid = i.file_uid LEFT JOIN (" + media._CARRIED + ") c ON c.file_uid = f.file_uid "
            "WHERE i.content_sha256 = ANY(:h) ORDER BY i.content_sha256, f.file_uid"),
            _params(case_id, w=weights, h=list(shas))):
        name = (r.local_path or "").replace("\\", "/").rsplit("/", 1)[-1] or "File not named in the report"
        out.setdefault(r.content_sha256, []).append({
            "file_uid": str(r.file_uid), "extraction_id": str(r.extraction_id),
            "phone_label": labels.get(str(r.extraction_id), "A phone"), "filename": name, "category": r.category,
            "message_count": int(r.messages)})
    for cs in out.values():
        cs.sort(key=lambda x: (-x["message_count"], x["phone_label"], x["filename"], x["file_uid"]))
    return out
