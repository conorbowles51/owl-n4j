"""Batch transcription and text reading of phone media (07 5 Media, M-5): "Transcribe all 312 voice notes in this
scope".

- ``describe`` counts, for a Media scope and a kind, the files a batch would read and the ones it leaves out, by
  reason: already read (a finished or waiting reading of that kind exists), not in the production, or an empty
  placeholder. Counts are true counts from the database.
- ``create`` queues one reading per eligible file, each naming the batch, in one statement; the total stored is
  the number of rows queued.
- ``status`` counts the batch's readings by state. The time left is worked out on the screen from the measured
  pace of this batch (finished readings over the time since its first one started); nothing is assumed about the
  model's speed.
- ``cancel`` removes the readings not yet started (no reading is lost: none was made) and keeps every finished one.

Readings a person asks for one at a time are drawn before batch readings (``derive._claim``). The readings run on
this server only, as every derived text does.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from services.phone import media

KINDS = {"transcript": ("Audio", "Video"), "ocr": ("Image",)}
NOUN = {"transcript": ("voice note or video", "voice notes and videos"), "ocr": ("image", "images")}


class BatchError(ValueError):
    pass


def _scope(conn, case_id, kind, scope):
    if kind not in KINDS:
        raise BatchError("Only transcription of audio and text reading of images can be run for a whole scope.")
    p = {"c": str(case_id), "kc": list(KINDS[kind]), "k": kind}
    where = media._where(dict(scope or {}), p) + " AND f.category = ANY(:kc)"
    already = ("EXISTS (SELECT 1 FROM phone_derived_texts d WHERE d.case_id = :c AND d.file_uid = f.file_uid AND "
               "d.kind = :k AND d.state IN ('queued', 'running', 'done'))")
    return media._base(where), p, already


def describe(conn, case_id, kind, scope) -> dict:
    base, p, already = _scope(conn, case_id, kind, scope)
    r = conn.execute(text(
        "SELECT count(*) AS in_scope, count(*) FILTER (WHERE coalesce(f.verification, '') = 'missing') AS missing, "
        "count(*) FILTER (WHERE f.verification = 'empty_placeholder') AS placeholder, "
        "count(*) FILTER (WHERE coalesce(f.verification, '') NOT IN ('missing', 'empty_placeholder') AND " + already +
        ") AS already, count(*) FILTER (WHERE coalesce(f.verification, '') NOT IN ('missing', 'empty_placeholder') "
        "AND NOT " + already + ") AS eligible " + base), p).one()
    return {"kind": kind, "in_scope": int(r.in_scope), "eligible": int(r.eligible),
            "left_out": {"already_read": int(r.already), "not_in_production": int(r.missing),
                         "empty_placeholder": int(r.placeholder)},
            "noun": NOUN[kind][0 if r.eligible == 1 else 1]}


def create(conn, *, case_id, kind, scope, scope_words, user_id) -> dict:
    facts = describe(conn, case_id, kind, scope)
    if not facts["eligible"]:
        raise BatchError("Every %s in this scope has already been read or cannot be read; nothing was queued."
                         % NOUN[kind][0])
    base, p, already = _scope(conn, case_id, kind, scope)
    batch = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_derive_batches (id, case_id, kind, scope, scope_words, total, left_out, created_by_user_id) "
        "VALUES (:b, :c, :k, CAST(:s AS jsonb), :w, 0, CAST(:l AS jsonb), :u)"),
        {"b": batch, "c": str(case_id), "k": kind, "s": json.dumps(scope or {}), "w": scope_words,
         "l": json.dumps(facts["left_out"]), "u": str(user_id) if user_id else None})
    queued = conn.execute(text(
        "INSERT INTO phone_derived_texts (id, case_id, extraction_id, file_uid, kind, created_by_user_id, batch_id) "
        "SELECT gen_random_uuid(), :c, f.extraction_id, f.file_uid, :k, :u, :b " + base +
        " AND coalesce(f.verification, '') NOT IN ('missing', 'empty_placeholder') AND NOT " + already +
        # one open reading per file and kind (unique partial index): a reading asked for at the same moment wins
        " ON CONFLICT (case_id, file_uid, kind) WHERE state IN ('queued', 'running') DO NOTHING"),
        dict(p, b=batch, u=str(user_id) if user_id else None)).rowcount
    conn.execute(text("UPDATE phone_derive_batches SET total = :n WHERE id = :b"), {"n": queued, "b": batch})
    return get(conn, case_id, batch)


def _row(r) -> dict:
    total, done, failed = int(r.total), int(r.done), int(r.failed)
    queued, running = int(r.queued), int(r.running)
    finished = r.cancelled_at is not None and not running or (queued + running == 0)
    return {"id": str(r.id), "kind": r.kind, "scope_words": r.scope_words, "total": total, "done": done,
            "failed": failed, "queued": queued, "running": running, "cancelled": r.cancelled_at is not None,
            "cancelled_count": int(r.cancelled_count), "left_out": r.left_out or {},
            "state": "cancelled" if r.cancelled_at is not None and finished else "done" if finished else "running",
            "created_at": r.created_at.isoformat(),
            "first_started_at": r.first_started.isoformat() if r.first_started else None,
            "last_finished_at": r.last_finished.isoformat() if r.last_finished else None,
            "noun": NOUN[r.kind][0 if total == 1 else 1]}


_STATUS = (
    "SELECT b.*, count(d.id) FILTER (WHERE d.state = 'done') AS done, count(d.id) FILTER (WHERE d.state = 'failed') "
    "AS failed, count(d.id) FILTER (WHERE d.state = 'queued') AS queued, count(d.id) FILTER (WHERE d.state = "
    "'running') AS running, min(d.started_at) AS first_started, max(d.finished_at) AS last_finished "
    "FROM phone_derive_batches b LEFT JOIN phone_derived_texts d ON d.batch_id = b.id WHERE b.case_id = :c %s "
    "GROUP BY b.id ORDER BY b.created_at DESC")


def get(conn, case_id, batch_id) -> dict | None:
    r = conn.execute(text(_STATUS % "AND b.id = :b"), {"c": str(case_id), "b": str(batch_id)}).one_or_none()
    return _row(r) if r is not None else None


def status(conn, case_id, limit=20) -> list:
    return [_row(r) for r in conn.execute(text(_STATUS % "" + " LIMIT :l"), {"c": str(case_id), "l": limit})]


def cancel(conn, case_id, batch_id) -> dict:
    b = conn.execute(text("SELECT id FROM phone_derive_batches WHERE id = :b AND case_id = :c FOR UPDATE"),
                     {"b": str(batch_id), "c": str(case_id)}).one_or_none()
    if b is None:
        raise LookupError("That batch is not in this case.")
    gone = conn.execute(text("DELETE FROM phone_derived_texts WHERE batch_id = :b AND state = 'queued'"),
                        {"b": str(batch_id)}).rowcount
    conn.execute(text("UPDATE phone_derive_batches SET cancelled_at = coalesce(cancelled_at, now()), "
                      "cancelled_count = cancelled_count + :n WHERE id = :b"), {"n": gone, "b": str(batch_id)})
    return get(conn, case_id, batch_id)
