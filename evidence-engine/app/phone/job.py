"""The ``phone_capture`` job (01 section 10): the async wrapper around ``runner.run_capture``.

The capture runs in a worker thread with its own synchronous psycopg connection (decision D12). Progress goes on
Loupe's channel ``job:{job_id}:progress`` with ``stage`` and ``counts``, at every stage change and every second while
a stage runs (the last state is repeated when the stage has not moved, so a quiet step is visible as quiet, 07 4.7).
Pause stops at a committed flush; cancel (10.6) stops the same way and then removes partial rows of a ``pending``
extraction only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from contextlib import suppress
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.models.job import Job, JobStatus
from app.phone import paths
from app.phone.runner import CaptureFailed, Reporter, StopRequested, run_capture
from app.phone.store import connect
from app.services.redis_client import publish_progress

logger = logging.getLogger(__name__)

STAGE_STATUS = {
    "verifying_container": JobStatus.VERIFYING_SOURCE,
    "detecting": JobStatus.VERIFYING_SOURCE,
    "counting": JobStatus.VERIFYING_SOURCE,
    "capturing": JobStatus.CAPTURING,
    "reconciling": JobStatus.RECONCILING,
    "indexing_files": JobStatus.RECONCILING,
}
CANCELLED_MESSAGE = "Reading was cancelled. The upload is kept and can be read again."
PARTIAL_TABLES = ("phone_file_references", "phone_timestamps", "phone_extra_info_nodes", "phone_extra_infos",
                  "phone_records", "phone_files", "phone_container_entries")


class ThreadReporter(Reporter):
    def __init__(self, loop, queue, boundary):
        self.loop, self.queue, self.boundary = loop, queue, boundary

    def stage(self, name, progress, message="", counts=None):
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (name, float(progress), message, dict(counts or {})))

    def should_stop(self):
        self.boundary()  # raises IngestionPaused when a pause or cancel was asked for
        return False


CANCELLED_TEXT = "Reading cancelled. The upload is kept and can be read again."


def set_evidence_status(conn, evidence_id, status, error=None) -> None:
    """The phone report's evidence row follows its reading: processing while it runs, processed when it is read in
    full, failed (with the reason the job shows) otherwise. Only a phone report row is ever touched."""
    if not evidence_id:
        return
    with conn.transaction():
        conn.execute("UPDATE evidence_files SET status = %s, last_error = %s, processed_at = CASE WHEN %s = "
                     "'processed' THEN now() ELSE processed_at END WHERE id = %s AND source_type = "
                     "'phone_extraction'", (status, error, status, evidence_id))


async def _evidence_status(job, status, error=None):
    evidence_id = (job.merge_payload or {}).get("container_evidence_id")
    if not evidence_id:
        return

    def go():
        conn = connect(settings.database_url)
        try:
            set_evidence_status(conn, evidence_id, status, error)
        finally:
            conn.close()
    with suppress(Exception):  # the reading's own result is already saved; the row catches up on the next run
        await asyncio.to_thread(go)


def cancel_rows(conn, extraction_id) -> bool:
    """Remove a pending extraction's partial capture; keep container, hashes, evidence row and job (10.6)."""
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT standing FROM phone_extractions WHERE id = %s FOR UPDATE", (extraction_id,))
            row = cur.fetchone()
            if row is None or row[0] != "pending":
                return False
            for t in PARTIAL_TABLES:
                cur.execute("DELETE FROM %s WHERE extraction_id = %%s" % t, (extraction_id,))
            cur.execute("DELETE FROM phone_reconciliations WHERE extraction_id = %s", (extraction_id,))
            cur.execute("UPDATE phone_extraction_documents SET parse_state = CASE WHEN parse_state = 'empty' THEN "
                        "'empty' ELSE 'pending' END, skeleton = NULL, truncation = NULL, "
                        "capture_cursor = '{\"record_ordinal\":0,\"file_ordinal\":0,\"extra_ordinal\":0}' "
                        "WHERE extraction_id = %s", (extraction_id,))
            cur.execute("UPDATE phone_extractions SET capture_state = 'cancelled' WHERE id = %s", (extraction_id,))
    return True


def _extraction_for_job(conn, job_id):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM phone_extractions WHERE engine_job_id = %s", (job_id,))
        row = cur.fetchone()
    return row[0] if row else None


async def _publish(job, db, status, progress, message, stage=None, counts=None, error_message=None, write=True):
    progress = max(0.0, min(float(progress), 1.0))
    if write:
        # the cancel route writes pipeline_state.phone.cancel_requested from another session: never overwrite it
        await db.refresh(job, ["pipeline_state"])
        job.status = status
        job.progress = progress
        if error_message is not None:
            job.error_message = error_message
        state = dict(job.pipeline_state or {})
        phone = dict(state.get("phone") or {})
        now = datetime.now(timezone.utc).isoformat()
        if stage:
            if phone.get("stage") != stage:
                phone["stage_started_at"] = now
            phone["stage"] = stage
        if counts is not None and counts != phone.get("counts"):
            phone["counts"] = counts
            phone["changed_at"] = now  # the stall rule's "last change" (07 4.7)
        elif stage and phone.get("stage_started_at") == now:
            phone["changed_at"] = now
        phone["message"] = message
        state["phone"] = phone
        job.pipeline_state = state
        await db.commit()
    payload = {"job_id": str(job.id), "status": status.value, "progress": progress, "message": message}
    if stage:
        payload["stage"] = stage
    if counts is not None:
        payload["counts"] = counts
    if error_message is not None:
        payload["error_message"] = error_message
    with suppress(Exception):
        await publish_progress(str(job.id), payload)


async def run_phone_capture(job_id: str, db) -> None:
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
    body = job.merge_payload or {}
    case_id = job.case_id
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()
    from app.services.ingestion_checkpoints import IngestionPaused, pause_boundary
    last_check = [0.0]

    def boundary():
        if stop.is_set():
            raise IngestionPaused()
        now = time.monotonic()
        if now - last_check[0] >= 0.25:
            asyncio.run_coroutine_threadsafe(pause_boundary(), loop).result()
            last_check[0] = now

    def work():
        conn = connect(settings.database_url)
        try:
            return run_capture(
                conn, data_root=str(paths.data_root()), case_id=case_id,
                container_path=body.get("container_path") or "", root_path=body.get("root_path") or "",
                original_name=body.get("original_name"), upload_sha256=body.get("upload_sha256"),
                container_evidence_id=body.get("container_evidence_id"),
                upload_group_id=body.get("upload_group_id"), user_id=body.get("requested_by_user_id"),
                job_id=job.id, reporter=ThreadReporter(loop, queue, boundary))
        finally:
            conn.close()

    await _evidence_status(job, "processing")
    await _publish(job, db, JobStatus.VERIFYING_SOURCE, job.progress or 0.0, "Checking the report",
                   stage="verifying_container")
    worker = asyncio.create_task(asyncio.to_thread(work))
    last = ("verifying_container", job.progress or 0.0, "Checking the report", {})
    last_write = 0.0
    try:
        while not worker.done():
            try:
                last = await asyncio.wait_for(queue.get(), timeout=1.0)
                fresh = True
            except asyncio.TimeoutError:
                fresh = False
            name, progress, message, counts = last
            now = time.monotonic()
            write = fresh and (now - last_write >= 1.0 or name != (job.pipeline_state or {}).get("phone", {}).get("stage"))
            if write:
                last_write = now
            status = STAGE_STATUS.get(name, JobStatus.RECONCILING)
            await _publish(job, db, status, progress, message, stage=name, counts=counts, write=write)
        result = await asyncio.shield(worker)
    except asyncio.CancelledError:
        stop.set()
        with suppress(IngestionPaused, Exception):
            await asyncio.shield(worker)
        job.pause_requested = True
        job.paused = True
        job.resumable = True
        await _publish(job, db, JobStatus.PENDING, job.progress or 0.0,
                       "Paused after worker interruption. Resume to continue from saved work.")
        raise
    except IngestionPaused:
        await db.refresh(job, ["pipeline_state"])
        if (job.pipeline_state or {}).get("phone", {}).get("cancel_requested"):
            await _cancel(job, db)
            return
        raise
    except CaptureFailed as exc:
        await _fail(job, db, exc.code, exc.message)
        return
    except Exception as exc:
        logger.exception("Phone capture failed for job %s", job_id)
        code = "database_error" if exc.__class__.__module__.startswith("psycopg") else "capture_error"
        message = ("Reading stopped because the database could not save it. Nothing saved so far is lost. Resume to "
                   "continue." if code == "database_error" else
                   "Reading stopped at the step shown. Nothing saved so far is lost. Resume to continue.")
        await _fail(job, db, code, message, reference=str(job.id))
        raise
    await _finish(job, db, result)


async def _fail(job, db, code, message, reference=None):
    await db.refresh(job, ["pipeline_state"])
    state = dict(job.pipeline_state or {})
    phone = dict(state.get("phone") or {})
    phone.update(failure_code=code, failure_stage=phone.get("stage"), reference=reference or str(job.id))
    state["phone"] = phone
    job.pipeline_state = state
    await db.commit()
    await asyncio.to_thread(_mark_extraction_failed, job.id, code, message, phone.get("stage"))
    await _evidence_status(job, "failed", message)
    await _publish(job, db, JobStatus.FAILED, job.progress or 0.0, message, stage=phone.get("stage"),
                   error_message=message)


def _mark_extraction_failed(job_id, code=None, message=None, stage=None):
    conn = connect(settings.database_url)
    try:
        ext = _extraction_for_job(conn, job_id)
        if ext is not None:
            with conn.transaction():
                conn.execute("UPDATE phone_extractions SET capture_state = 'failed' WHERE id = %s AND capture_state "
                             "NOT IN ('captured', 'captured_incomplete', 'reconciliation_failed')", (ext,))
                if code:
                    # the reason stays on the extraction, so a person reading it never has to open the worker log
                    conn.execute("UPDATE phone_extractions SET flags = flags || %s::jsonb WHERE id = %s AND "
                                 "capture_state = 'failed'", (json.dumps({"failure": {
                                     "code": code, "message": message, "stage": stage}}), ext))
    finally:
        conn.close()


async def _cancel(job, db):
    def go():
        conn = connect(settings.database_url)
        try:
            ext = _extraction_for_job(conn, job.id)
            return cancel_rows(conn, ext) if ext is not None else True
        finally:
            conn.close()
    await asyncio.to_thread(go)
    await _evidence_status(job, "failed", CANCELLED_TEXT)
    await db.refresh(job, ["pipeline_state"])
    state = dict(job.pipeline_state or {})
    phone = dict(state.get("phone") or {})
    phone["cancelled"] = True
    state["phone"] = phone
    job.pipeline_state = state
    job.pause_requested = False
    job.paused = False
    job.resumable = True
    await db.commit()
    await _publish(job, db, JobStatus.FAILED, job.progress or 0.0, CANCELLED_MESSAGE, stage="cancelled",
                   error_message=CANCELLED_MESSAGE)


async def _finish(job, db, result):
    await db.refresh(job, ["pipeline_state"])
    state = dict(job.pipeline_state or {})
    phone = dict(state.get("phone") or {})
    phone.update({k: result.get(k) for k in ("extraction_id", "container_id", "state", "records", "files",
                                              "already_in_case", "outcome", "difference_count")
                  if result.get(k) is not None})
    summary = result.get("summary") or {}
    if summary:
        phone["file_outcomes"] = (summary.get("verify_files") or {}).get("outcomes")
        phone["references"] = summary.get("resolve_references")
        phone["timestamps"] = (summary.get("store_timestamps") or {}).get("counts")
    phone["message"] = result.get("message")
    state["phone"] = phone
    job.pipeline_state = json.loads(json.dumps(state, default=str))
    job.entity_count = int(result.get("records") or 0)
    await db.commit()
    read = result["state"] in ("captured", "captured_incomplete")
    await _evidence_status(job, "processed" if read else "failed", None if read else (result.get("message") or ""))
    if result["state"] in ("captured", "captured_incomplete", "not_readable"):
        await _publish(job, db, JobStatus.COMPLETED, 1.0, result.get("message") or "Ready", stage="finishing",
                       counts={"records": result.get("records"), "files": result.get("files")})
    else:
        if result["state"] == "reconciliation_failed":
            # Held (07 J-1): Accept the difference resumes this job, which passes the accepted differences only
            job.resumable = True
        await _publish(job, db, JobStatus.FAILED, job.progress or 0.0, result.get("message") or "",
                       stage="reconciling", error_message=result.get("message"))
