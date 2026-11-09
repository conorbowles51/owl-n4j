"""The header job tray's one list (07 section 4.7): every long phone job of a case, in words, with true counts.

One read answers for every kind, so a tab asks once however many kinds are running, and the list survives a reload
because it is read from the rows each job already writes. Running jobs are always listed. Finished ones stay for
``KEEP_FINISHED`` so their notice and link are not lost, at most ``MOST_FINISHED`` of them, newest first; the count of
the rest is stated. A kind that cannot be read is named in ``unavailable``, never left out silently.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

KEEP_FINISHED = timedelta(hours=12)
# Phones are read again by themselves after a decision or a release: their finished lines stay only a short while.
KEEP_READING = timedelta(hours=1)
MOST_FINISHED = 30
# A bulk add is sent from the page; a page that goes this long without reporting is gone (closed or reloaded).
COLLECT_SILENT = timedelta(seconds=120)
# Together answers at once for a small run: only one that really took a while is a job.
TOGETHER_JOB = timedelta(seconds=5)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _when(value) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else _utc(value)


def _iso(value):
    value = _when(value)
    return value.isoformat() if value else None


def _job(kind, ident, title, state, *, step, done=None, total=None, unit=None, started=None, moved=None, ended=None,
         note=None, error=None, reference=None, href=None, **extra):
    return dict(id="%s:%s" % (kind, ident), kind=kind, title=title, state=state, step=step, done=done, total=total,
                unit=unit, started_at=_iso(started), moved_at=_iso(moved or started), ended_at=_iso(ended), note=note,
                error=error, reference=reference, href=href, **extra)


def _intake(conn, case_id, since, user):
    rows = conn.execute(text(
        "SELECT id, file_name, status::text AS status, error_message, paused, pipeline_state -> 'phone' AS phone, "
        "created_at, updated_at FROM jobs WHERE case_id = :c AND job_type = 'phone_capture' AND "
        "(status::text NOT IN ('completed', 'failed') OR updated_at >= :s) ORDER BY created_at DESC"),
        {"c": str(case_id), "s": since.astimezone(timezone.utc).replace(tzinfo=None)})  # the engine stores naive UTC
    out = []
    for r in rows:
        phone = r.phone or {}
        state = "done" if r.status == "completed" else "failed" if r.status == "failed" else "running"
        out.append(_job(
            "intake", r.id, "Adding %s" % (r.file_name or "a phone report"), state, step="Adding the phone report",
            started=r.created_at, moved=phone.get("changed_at"),
            ended=r.updated_at if state != "running" else None, error=r.error_message or phone.get("message")
            if state == "failed" else None, reference=phone.get("reference") or str(r.id),
            note=phone.get("message") if state == "done" else "Paused." if r.paused else None,
            href="/cases/%s/evidence" % case_id, stage=phone.get("stage"), counts=phone.get("counts") or {}))
    return out


def _reading(conn, case_id, since, user):
    from services.phone import readings
    out = []
    for p in readings.progress(conn, case_id):
        name = p["phone"] or "a phone"
        ended = _when(p.get("finished_at"))
        if p["state"] == "done" and (ended is None or ended < since + KEEP_FINISHED - KEEP_READING):
            continue  # a phone read a while ago is not a job
        state = "done" if p["state"] == "done" else "running"
        out.append(_job(
            "interpretation", p["extraction_id"], "Reading %s" % name, state,
            step="Waiting to be read again" if p["state"] == "waiting" else "Reading the records",
            done=p["records_done"] if p["state"] == "re-reading" else None,
            total=p["records_total"] if p["state"] == "re-reading" else None, unit="records",
            started=p.get("started_at"), moved=p.get("updated_at"), ended=ended,
            note="%s records read." % format(p["records_total"], ",") if state == "done" else None,
            href="/cases/%s/phones/%s" % (case_id, p["extraction_id"])))
    return out


EXPORT_WORDS = {"stream": "messages and calls", "timeline_lens": "the Timeline", "collection": "a collection",
                "finding": "a finding", "dossier": "a dossier", "statement_check": "a statement check"}


def _export(conn, case_id, since, user):
    rows = conn.execute(text(
        "SELECT export_id, format, source, state, progress, counts, error, filename, created_at, started_at, "
        "finished_at, options FROM phone_exports WHERE case_id = :c AND (state IN ('queued', 'rendering') OR "
        "finished_at >= :s) ORDER BY created_at DESC"), {"c": str(case_id), "s": since})
    out = []
    for r in rows:
        title = (r.options or {}).get("title") or EXPORT_WORDS.get(r.source, "phone records")
        state = {"queued": "running", "rendering": "running", "done": "done"}.get(r.state, "failed")
        out.append(_job(
            "export", r.export_id, "Export: %s (%s)" % (title, r.format.upper()), state,
            step="Waiting to start" if r.state == "queued" else "Drawing the export",
            # an export stores how far it has drawn, not a count, until it is done
            done=round(float(r.progress or 0) * 100) if r.state == "rendering" else None,
            total=100 if r.state == "rendering" else None, unit="percent", started=r.started_at or r.created_at,
            ended=r.finished_at, error=r.error if state == "failed" else None, reference=str(r.export_id),
            note=r.filename if state == "done" else None,
            href="/api/phones/exports/%s/file?case_id=%s" % (r.export_id, case_id) if state == "done" else None))
    return out


def _together(conn, case_id, since, user):
    # the run is the reader's own (a person needs only case view to ask): it is listed to them alone
    rows = conn.execute(text(
        "SELECT id, status, counts, error, started_at, finished_at FROM pol_colocation_run WHERE case_id = :c AND "
        "requested_by = :u AND (status IN ('queued', 'running') OR finished_at >= :s) ORDER BY started_at DESC"),
        {"c": str(case_id), "u": user.email, "s": since})
    out = []
    for r in rows:
        took = (r.finished_at - r.started_at) if r.finished_at and r.started_at else None
        if r.status == "done" and took is not None and took < TOGETHER_JOB:
            continue
        state = "done" if r.status == "done" else "failed" if r.status == "failed" else "running"
        out.append(_job(
            "together", r.id, "Together and apart", state, step="Comparing where two people were",
            started=r.started_at, ended=r.finished_at, error=r.error if state == "failed" else None,
            reference=str(r.id), href="/cases/%s/phone-patterns" % case_id))
    return out


def _approach(conn, case_id, since, user):
    from services.phone_analysis.approaches import TITLES
    rows = conn.execute(text(
        "SELECT id, approach, status, progress, error, created_at, started_at, finished_at FROM phone_analysis_runs "
        "WHERE case_id = :c AND (status IN ('queued', 'running') OR finished_at >= :s) ORDER BY created_at DESC"),
        {"c": str(case_id), "s": since})
    out = []
    for r in rows:
        prog = r.progress or {}
        state = {"queued": "running", "running": "running", "failed": "failed",
                 "cancelled": "cancelled"}.get(r.status, "done")
        out.append(_job(
            "approach", r.id, TITLES.get(r.approach, "Phone analysis"), state,
            step="Waiting to start" if r.status == "queued" else prog.get("phone") or "Analysing the phones",
            done=prog.get("read"), total=prog.get("total"), unit="records", started=r.started_at or r.created_at,
            ended=r.finished_at, error=r.error if state == "failed" else None, reference=str(r.id),
            note="Cancelled before it finished." if state == "cancelled" else None,
            href="/cases/%s/phone-analyses" % case_id))
    return out


def _media(conn, case_id, since, user):
    from services.phone import derive_batch, image_search
    out = []
    for b in derive_batch.status(conn, case_id):
        ended = _when(b["last_finished_at"])
        if b["state"] != "running" and (ended is None or ended < since):
            continue
        what = "Transcribing" if b["kind"] == "transcript" else "Reading text in"
        state = b["state"]
        left = "%s could not be read." % format(b["failed"], ",") if b["failed"] else None
        if state == "cancelled":
            left = "Cancelled; %s finished readings were kept. %s" % (format(b["done"], ","), left or "")
        out.append(_job(
            "media", b["id"], "%s %s" % (what, b["scope_words"] or b["noun"]), state, step="%s %s" % (what, b["noun"]),
            done=b["done"] + b["failed"], total=b["total"], unit=b["noun"],
            started=b["first_started_at"] or b["created_at"], moved=ended, ended=ended if state != "running" else None,
            note=left and left.strip()))
    for j in image_search.status(conn, case_id):
        ended = _when(j["last_finished_at"])
        if j["state"] != "running" and (ended is None or ended < since):
            continue
        state = j["state"]
        note = "%s could not be indexed." % format(j["failed"], ",") if j["failed"] else None
        if state == "cancelled":
            note = "Cancelled; %s indexed images were kept." % format(j["done"], ",")
        out.append(_job(
            "media", j["id"], "Getting images ready for search", state, step="Indexing images",
            done=j["done"] + j["failed"], total=j["total"], unit="images",
            started=j["first_started_at"] or j["created_at"], moved=ended, ended=ended if state != "running" else None,
            note=note))
    bundles = conn.execute(text(
        "SELECT bundle_id, scope_words, state, files_done, files_total, error, created_at, started_at, finished_at "
        "FROM phone_original_bundles WHERE case_id = :c AND (state IN ('queued', 'running') OR finished_at >= :s) "
        "ORDER BY created_at DESC"), {"c": str(case_id), "s": since})
    for b in bundles:
        state = {"queued": "running", "running": "running", "done": "done", "cancelled": "cancelled"}.get(b.state, "failed")
        out.append(_job(
            "media", b.bundle_id, "Download originals: %s" % b.scope_words, state, step="Gathering the original files",
            done=b.files_done, total=b.files_total, unit="files", started=b.started_at or b.created_at,
            ended=b.finished_at, error=b.error if state == "failed" else None, reference=str(b.bundle_id),
            note="Cancelled; nothing was kept." if state == "cancelled" else None))
    return out


def _reparse(conn, case_id, since, user):
    from services.phone import readings
    labels = readings.phone_labels(conn, case_id)
    rows = conn.execute(text(
        "SELECT id, extraction_id, tool, status, error, created_at, started_at, finished_at FROM phone_reparse_runs "
        "WHERE case_id = :c AND (status IN ('queued', 'running') OR finished_at >= :s) ORDER BY created_at DESC"),
        {"c": str(case_id), "s": since})
    out = []
    for r in rows:
        state = {"queued": "running", "running": "running", "failed": "failed",
                 "cancelled": "cancelled"}.get(r.status, "done")
        out.append(_job(
            "reparse", r.id, "Reading %s with an independent tool" % labels.get(str(r.extraction_id), "a phone"), state,
            step="Waiting to start" if r.status == "queued" else "Running %s" % r.tool,
            started=r.started_at or r.created_at, ended=r.finished_at, error=r.error if state == "failed" else None,
            reference=str(r.id), href="/cases/%s/phone-analyses/read-again" % case_id))
    return out


def _collect(conn, case_id, since, user):
    now = conn.execute(text("SELECT now()")).scalar()
    rows = conn.execute(text(
        "SELECT * FROM phone_collect_runs WHERE case_id = :c AND user_id = :u AND (state = 'running' OR "
        "coalesce(finished_at, updated_at) >= :s) ORDER BY created_at DESC"),
        {"c": str(case_id), "u": user.id, "s": since})
    out = []
    for r in rows:
        silent = r.state == "running" and now - r.updated_at > COLLECT_SILENT
        state = "failed" if r.state == "failed" or silent else "done" if r.state == "done" else "running"
        counts = "Added %s; %s were already there" % (format(r.added, ","), format(r.skipped, ","))
        if r.refused:
            counts += "; %s were refused" % format(r.refused, ",")
        error = r.error
        if silent:
            error = ("The page sending them closed. %s of %s were sent; the rest were not added." %
                     (format(r.sent, ","), format(r.total, ",")))
        out.append(_job(
            "collect", r.id, "Adding %s %s to %s" % (format(r.total, ","), r.noun, r.target_words), state,
            step="Linking %s" % r.noun, done=r.sent, total=r.total, unit=r.noun, started=r.created_at,
            moved=r.updated_at, ended=r.finished_at or (r.updated_at if silent else None), error=error,
            reference=str(r.id), note="%s." % counts if state != "running" else None))
    return out


# Words for ``unavailable``, one source per kind a person would recognise.
SOURCES = (("adding phones", _intake), ("reading phones", _reading), ("exports", _export), ("Together", _together),
           ("analyses", _approach), ("media jobs", _media), ("independent re-reads", _reparse), ("bulk adds", _collect))


def read(conn, case_id, user, now=None) -> dict:
    """Every job of the case, running first, then finished newest first. ``active`` says a tab should keep asking."""
    now = now or conn.execute(text("SELECT now()")).scalar()
    since = now - KEEP_FINISHED
    jobs, unavailable = [], []
    for words, source in SOURCES:
        try:
            with conn.begin_nested():
                jobs.extend(source(conn, case_id, since, user))
        except Exception:
            logger.exception("Job tray could not read %s", words)
            unavailable.append(words)
    running = [j for j in jobs if j["state"] == "running"]
    finished = sorted((j for j in jobs if j["state"] != "running"), key=lambda j: j["ended_at"] or "", reverse=True)
    return {"case_id": str(case_id), "items": running + finished[:MOST_FINISHED],
            "older_finished": max(0, len(finished) - MOST_FINISHED), "unavailable": unavailable,
            "active": bool(running), "read_at": _iso(now)}


def start_collect(conn, *, case_id, user_id, target_words, noun, total) -> str:
    run = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_collect_runs (id, case_id, user_id, target_words, noun, total) VALUES (:i, :c, :u, :t, :n, "
        ":o)"), {"i": run, "c": str(case_id), "u": str(user_id), "t": target_words, "n": noun, "o": total})
    return str(run)


def report_collect(conn, *, run_id, case_id, user_id, sent, added, skipped, refused, refused_reason, finished,
                   error) -> bool:
    """One part's true counts from the page sending them. A finished run is not reopened; False when not this
    person's run in this case."""
    state = "failed" if error else "done" if finished else "running"
    return conn.execute(text(
        "UPDATE phone_collect_runs SET sent = :s, added = :a, skipped = :k, refused = :r, refused_reason = :w, "
        "state = :st, error = :e, updated_at = now(), finished_at = CASE WHEN :st = 'running' THEN NULL ELSE now() END "
        "WHERE id = :i AND case_id = :c AND user_id = :u AND state = 'running'"),
        {"s": sent, "a": added, "k": skipped, "r": refused, "w": refused_reason, "st": state, "e": error,
         "i": str(run_id), "c": str(case_id), "u": str(user_id)}).rowcount == 1


MARKS = ("phones_new_hidden", "first_phone_card_seen")


def marks(conn, user_id) -> dict:
    return {r.mark: r.at.isoformat() for r in conn.execute(
        text("SELECT mark, at FROM phone_user_marks WHERE user_id = :u AND mark = ANY(:m)"),
        {"u": str(user_id), "m": list(MARKS)})}


def set_mark(conn, user_id, mark) -> dict:
    conn.execute(text("INSERT INTO phone_user_marks (user_id, mark) VALUES (:u, :m) ON CONFLICT DO NOTHING"),
                 {"u": str(user_id), "m": mark})
    return marks(conn, user_id)
