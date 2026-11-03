"""Phone exports as jobs (03 section 12.2): queue, describe, draw and store.

``create`` stores the request with the filter and its snapshot; the phone worker's after-pass step ``run_pending``
draws one export at a time (one writer, at the worker's priority) and stores the file with its SHA-256. A failed
export keeps its choices and says what failed with a reference id; nothing is half-delivered (the file is written
under a temporary name and moved into place only when complete).

Built: the PDF and the RSMF file of a stream (a conversation, a person or a pair, any Conversations filter). The
other sources (timeline lens, collection, finding, dossier, and the cb-approaches sources) answer that they are not
built yet rather than producing something partial.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from services.phone import labels as L
from services.phone import streams
from services.phone import time_display as T
from services.phone.filters import StreamFilter, snapshot

log = logging.getLogger(__name__)
BUILT_FORMATS = ("pdf", "rsmf")
BUILT_SOURCES = ("stream",)
STALE_RENDER_SECONDS = 2 * 3600  # a render claimed this long ago by a worker that died is queued again
MAX_ATTEMPTS = 2  # a render that stopped this many times is failed with a reason, never claimed forever
STOPPED = ("The export stopped twice while it was being drawn; it may be too large to draw at once. Your choices "
           "are kept: choose fewer rows, or try again.")
IDLE_SECONDS = 5
LEFT_OUT = "Saved passwords and card numbers left out."


class ExportError(ValueError):
    pass


def export_dir() -> Path:
    env = os.environ.get("LOUPE_PHONE_EXPORT_DIR")
    if env:
        return Path(env)
    from config import EVIDENCE_DATA_ROOT
    return Path(EVIDENCE_DATA_ROOT) / "phone-exports"


def _filter(case_id, body: dict) -> StreamFilter:
    f = StreamFilter.model_validate({**(body or {}), "case_id": str(case_id)})
    return f


def describe(conn, case_id, filter_body: dict) -> dict:
    """What the dialog states before anything is drawn (12.2 steps 1 and 2): totals by kind, phones, the zone, how
    many rows rely on readings not yet confirmed, and any incomplete phone. The same counts print on the cover."""
    f = _filter(case_id, filter_body)
    q, _ = streams._query(conn, f)
    shown = streams._shown(f)
    r = conn.execute(text(
        "WITH m AS (%s) SELECT count(*) FILTER (WHERE %s) AS total, count(*) FILTER (WHERE %s AND kind = 'message') "
        "AS messages, count(*) FILTER (WHERE %s AND kind = 'call') AS calls, count(*) FILTER (WHERE %s AND "
        "interpretation_level = 'applied_unconfirmed') AS unconfirmed, count(DISTINCT extraction_id) FILTER (WHERE "
        "%s) AS phones, count(*) - count(*) FILTER (WHERE %s) AS collapsed FROM m"
        % (q.matched_sql(), shown, shown, shown, shown, shown, shown)), q.params).one()
    zone = streams.resolve_zone(conn, f)
    total = int(r.total)
    return {"case_id": str(case_id), "total": total, "messages": int(r.messages), "calls": int(r.calls),
            "other": total - int(r.messages) - int(r.calls), "unconfirmed": int(r.unconfirmed),
            "phones": int(r.phones), "collapsed_copies": int(r.collapsed), "zone": zone["display_name"],
            "left_out": LEFT_OUT, "limits": streams.limits_for(conn, f), "snapshot": snapshot(conn, f)}


def create(conn, *, case_id, user_id, fmt, source, filter_body, options) -> dict:
    if fmt not in BUILT_FORMATS:
        raise ExportError("An export is a PDF or an RSMF file.")
    if source not in BUILT_SOURCES:
        raise ExportError("Exporting a %s is not built yet." % source.replace("_", " "))
    f = _filter(case_id, filter_body)
    export_id = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO phone_exports (export_id, case_id, created_by, format, source, filter, options, snapshot) "
        "VALUES (:i, :c, :u, :fmt, :src, CAST(:f AS jsonb), CAST(:o AS jsonb), :s)"),
        {"i": export_id, "c": str(case_id), "u": str(user_id), "fmt": fmt, "src": source,
         "f": f.model_dump_json(), "o": json.dumps(options or {}), "s": snapshot(conn, f)})
    return {"export_id": str(export_id)}


def get(conn, case_id, export_id) -> dict | None:
    r = conn.execute(text(
        "SELECT export_id, format, source, state, progress, counts, filename, size, sha256, error, created_at, "
        "finished_at, options FROM phone_exports WHERE export_id = CAST(:i AS uuid) AND case_id = CAST(:c AS uuid)"),
        {"i": str(export_id), "c": str(case_id)}).one_or_none()
    return _out(r) if r is not None else None


def history(conn, case_id) -> list:
    return [_out(r) for r in conn.execute(text(
        "SELECT export_id, format, source, state, progress, counts, filename, size, sha256, error, created_at, "
        "finished_at, options FROM phone_exports WHERE case_id = CAST(:c AS uuid) ORDER BY created_at DESC"),
        {"c": str(case_id)})]


def file_of(conn, case_id, export_id):
    r = conn.execute(text(
        "SELECT filename, storage_path, sha256 FROM phone_exports WHERE export_id = CAST(:i AS uuid) AND case_id = "
        "CAST(:c AS uuid) AND state = 'done'"), {"i": str(export_id), "c": str(case_id)}).one_or_none()
    return r


def _out(r) -> dict:
    return {"export_id": str(r.export_id), "format": r.format, "source": r.source, "state": r.state,
            "progress": float(r.progress or 0), "counts": r.counts or {},
            "file": {"filename": r.filename, "size": r.size, "sha256": r.sha256} if r.state == "done" else None,
            "error": r.error, "created_at": T.iso(r.created_at), "finished_at": T.iso(r.finished_at),
            "title": (r.options or {}).get("title")}


# ---- drawing (the worker) --------------------------------------------------------------------------------------

def _claim(engine):
    """The next export to draw, as (export_id, claimed_at); a render whose worker stopped is taken again until
    ``MAX_ATTEMPTS``, then failed with ``STOPPED``."""
    while True:
        with engine.begin() as c:
            r = c.execute(text(
                "SELECT export_id, state, attempts FROM phone_exports WHERE state = 'queued' OR (state = 'rendering' "
                "AND started_at < now() - make_interval(secs => :stale)) ORDER BY created_at FOR UPDATE SKIP LOCKED "
                "LIMIT 1"), {"stale": STALE_RENDER_SECONDS}).one_or_none()
            if r is None:
                return None
            if r.state == "rendering" and r.attempts >= MAX_ATTEMPTS:
                c.execute(text("UPDATE phone_exports SET state = 'failed', error = :e, finished_at = now() WHERE "
                               "export_id = :i"), {"e": STOPPED, "i": r.export_id})
                continue
            claimed = c.execute(text(
                "UPDATE phone_exports SET state = 'rendering', started_at = clock_timestamp(), progress = 0, "
                "error = NULL, attempts = attempts + 1 WHERE export_id = :i RETURNING started_at"),
                {"i": r.export_id}).scalar()
            return r.export_id, claimed


def _progress(engine, export_id, value):
    with engine.begin() as c:
        c.execute(text("UPDATE phone_exports SET progress = :p WHERE export_id = :i"),
                  {"p": round(min(max(value, 0.0), 0.99), 3), "i": export_id})


def run_pending(engine, limit=1) -> list:
    """Draw up to ``limit`` queued exports. A failure is recorded only by the worker that still holds the claim."""
    done = []
    for _ in range(limit):
        got = _claim(engine)
        if got is None:
            break
        export_id, claimed = got
        try:
            done.append(draw(engine, export_id, claimed=claimed))
        except Exception:  # noqa: BLE001
            ref = uuid.uuid4().hex[:8]
            log.exception("phone export %s failed (reference %s)", export_id, ref)
            with engine.begin() as c:
                c.execute(text(
                    "UPDATE phone_exports SET state = 'failed', error = :e, finished_at = now() WHERE export_id = :i "
                    "AND state = 'rendering' AND started_at = :t"),
                    {"e": "The export could not be drawn. Your choices are kept; try again. Reference: %s." % ref,
                     "i": export_id, "t": claimed})
            done.append({"export_id": str(export_id), "state": "failed"})
    return done


_worker = {"thread": None}


def _export_loop(engine_factory, stop):
    while not stop.is_set():
        try:
            busy = run_pending(engine_factory())
        except Exception:  # noqa: BLE001
            log.exception("phone export step failed")
            busy = []
        stop.wait(0 if busy else IDLE_SECONDS)


def start_worker(engine):
    """The sweep's after-pass hook: starts, once per process, the thread that draws exports. Exports are drawn on
    their own thread (so reading phones never waits for a PDF) and each PDF in a child process with a memory cap
    (``pdf.render_isolated``), so a very large export fails with a reason instead of stopping the server."""
    import threading
    t = _worker["thread"]
    if t is not None and t.is_alive():
        return
    from services.phone import sweep
    stop = sweep._STOP.get("event") or threading.Event()
    _worker["thread"] = threading.Thread(target=_export_loop, args=(lambda: engine, stop), name="phone-exports",
                                         daemon=True)
    _worker["thread"].start()


def _rows(conn, f):
    """Every row the screen shows for ``f``, day by day in screen order: [(day header, rows)], the index."""
    idx = streams.index_comm_events(conn, f)
    days = [(d["day"], "%s, %s" % (d["header"], d["zone_label"]), d["count"]) for d in idx["items"]]
    if idx["no_time_count"]:
        days.append((None, "No time recorded", idx["no_time_count"]))
    return idx, days


def draw(engine, export_id, claimed=None) -> dict:
    from services.phone.exports import pdf
    from services.phone.readings import phone_labels
    with engine.connect() as conn:
        e = conn.execute(text(
            "SELECT e.export_id, e.case_id, e.format, e.filter, e.options, e.created_by, c.title AS case_title, "
            "u.name AS who "
            "FROM phone_exports e JOIN cases c ON c.id = e.case_id LEFT JOIN users u ON u.id = e.created_by "
            "WHERE e.export_id = :i"), {"i": export_id}).one()
        f = StreamFilter.model_validate(e.filter)
        options = e.options or {}
        facts = describe(conn, e.case_id, e.filter)
        idx, days = _rows(conn, f)
        snap = idx["snapshot"]
        total = sum(n for _, _, n in days)
        out_days, seen, people = [], 0, {}
        for day, header, n in days:
            rows = []
            for off in range(0, n, streams.WINDOW_MAX):
                w = streams.window_comm_events(conn, f, snapshot_token=snap, day=day, offset=off,
                                               limit=streams.WINDOW_MAX)
                rows.extend(w["items"])
            out_days.append((header, rows))
            seen += len(rows)
            for r in rows:
                for lab in [r.get("from")] + list(r.get("to") or []):
                    if lab:
                        ident = L.identifier_text(lab.get("identifier"))
                        people.setdefault(L.label_text(lab), set()).update([ident] if ident else [])
            if total:
                _progress(engine, export_id, 0.8 * seen / total)
        if seen != total:  # the stated total and the printed rows must agree (E-4); never deliver a mismatch
            raise RuntimeError("export rows %d differ from the index total %d" % (seen, total))
        phones = sorted(set(phone_labels(conn, e.case_id).get(p, "") for p in (f.phones or [])) - {""})
    words = (options.get("words") or "").strip()
    contains = [
        "All %s%s." % (_kinds_words(facts), (" %s" % words) if words else ""),
        "Times in %s." % facts["zone"],
        ("Repeated copies of a message are collapsed: %s copies are not printed again." % "{:,}".format(
            facts["collapsed_copies"])) if f.collapse_copies and facts["collapsed_copies"] else
        ("Every copy of a message is printed." if not f.collapse_copies else "No message had repeated copies."),
        "%s of these %s rows rely on readings not yet confirmed by a person; each such row says so."
        % ("{:,}".format(facts["unconfirmed"]), "{:,}".format(total)) if facts["unconfirmed"] else
        "Every row rests on readings confirmed by a person.",
        LEFT_OUT,
    ]
    if phones:
        contains.insert(1, "Phones: %s." % ", ".join(phones))
    contains += [lim["message"] for lim in facts["limits"]]
    generated = "Generated by %s on %s UTC." % (e.who or "a Loupe user",
                                                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    fmt = e.format or "pdf"
    extra = {}
    if fmt == "rsmf":
        data, extra = _rsmf(engine, e, options, contains + [generated, "Export %s." % export_id], out_days)
    else:
        doc, missing = pdf.build_html(
            title=options.get("title") or "Phone messages", case_name=e.case_title or "", generated=generated,
            export_id=str(export_id), contains=contains, days=out_days,
            participants=sorted((k, sorted(v)) for k, v in people.items()), page=options.get("page_size") or "letter")
        data = pdf.render_isolated(doc)
        extra = {"missing_characters": sum(missing.values())}
    sha = hashlib.sha256(data).hexdigest()
    folder = export_dir() / str(e.case_id)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / ("%s.%s" % (export_id, fmt))
    tmp = folder / (".%s.part" % export_id)
    tmp.write_bytes(data)
    os.replace(tmp, final)
    stem = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in (options.get("title") or ""))[:80]
    filename = "%s.%s" % (stem.strip(" _") and stem.strip() or "phone-messages", fmt)
    counts = {"total": total, "messages": facts["messages"], "calls": facts["calls"],
              "unconfirmed": facts["unconfirmed"], "phones": facts["phones"], "snapshot": snap, **extra}
    with engine.begin() as c:
        done = c.execute(text(
            "UPDATE phone_exports SET state = 'done', progress = 1, counts = CAST(:k AS jsonb), filename = :n, "
            "size = :s, sha256 = :h, storage_path = :p, finished_at = now(), snapshot = :snap WHERE export_id = :i AND state = 'rendering' AND "
            "(CAST(:t AS timestamptz) IS NULL OR started_at = :t)"),
            {"k": json.dumps(counts), "n": filename, "s": len(data), "h": sha, "p": str(final), "snap": snap,
             "i": export_id, "t": claimed}).rowcount
    if not done:  # another worker holds the claim now; it records the result
        return {"export_id": str(export_id), "state": "lost", "counts": counts}
    return {"export_id": str(export_id), "state": "done", "counts": counts}


def _rsmf(engine, e, options, contains, out_days):
    """One RSMF file for the whole filtered period (12.4): every row in screen order, attachments read in place.
    Its event count must equal the rows drawn (E-6, E-4)."""
    from services.phone import media
    from services.phone.exports import rsmf
    rows = [r for _, day_rows in out_days for r in day_rows]

    def read_file(file_uid):
        with engine.connect() as c:
            try:
                name, size, opener = media.content(c, e.case_id, file_uid)
            except media.ContentRefused as exc:
                return None, str(exc)
        try:
            with opener() as fh:
                return fh.read(), None
        except OSError:
            return None, "The file could not be read from the production."
    data, counts = rsmf.build(rows, title=options.get("title") or "Phone messages", contains=contains,
                              read_file=read_file)
    if counts["events"] != len(rows):
        raise RuntimeError("RSMF events %d differ from the rows %d" % (counts["events"], len(rows)))
    return data, {"rsmf": counts}


def _kinds_words(facts) -> str:
    parts = ["%s %s" % ("{:,}".format(facts["messages"]), "message" if facts["messages"] == 1 else "messages")]
    if facts["calls"]:
        parts.append("%s %s" % ("{:,}".format(facts["calls"]), "call" if facts["calls"] == 1 else "calls"))
    if facts["other"]:
        parts.append("%s other %s" % ("{:,}".format(facts["other"]),
                                      "record" if facts["other"] == 1 else "records"))
    return " and ".join(parts)


def install():
    """Called by the sweep worker: queued exports are drawn after each pass (one writer)."""
    from services.phone import sweep
    sweep.register_after_pass(start_worker)
