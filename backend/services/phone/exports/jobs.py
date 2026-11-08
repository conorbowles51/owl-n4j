"""Phone exports as jobs (03 section 12.2): queue, describe, draw and store.

``create`` stores the request with the filter and its snapshot; the phone worker's after-pass step ``run_pending``
draws one export at a time (one writer, at the worker's priority) and stores the file with its SHA-256. A failed
export keeps its choices and says what failed with a reference id; nothing is half-delivered (the file is written
under a temporary name and moved into place only when complete).

Built: the PDF and the RSMF file of a stream (a conversation, a person or a pair, any Conversations filter), and of a
finding, theory or note (source ``finding``: the frozen selection of its phone records, services.phone.entry_export),
and of an analysis result, a statement check or an incident window (the frozen selection of their records,
services.phone.source_export), and of a collection (a collected selection) or a dossier's phone records (the same
module), and of the Timeline phone lens (source ``timeline_lens``: every entry the lens shows for its filter, the
messages and calls with the other records' event times, day by day under the lens's own day headers). All eight
sources of 03 section 12.2 are built.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

from services.phone import labels as L
from services.phone import streams
from services.phone import time_display as T
from services.phone.derive import IN_USE_ORDER
from services.phone.filters import StreamFilter, snapshot

log = logging.getLogger(__name__)
BUILT_FORMATS = ("pdf", "rsmf")
LINK_SOURCES = ("collection", "finding", "dossier")
BUILT_SOURCES = ("stream", "timeline_lens", "collection", "finding", "dossier", "statement_check", "analysis_result",
                 "incident_window", "phone_profile")
# the Phone summary as a PDF (03 section 7.3 "Export profile as PDF", same renderer): filter {"phones": [one id]}
# a finding, theory or note is exported as the frozen selection of its phone records (services.phone.entry_export)
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


def _lens_filter(case_id, body: dict):
    from services.phone.timeline_lens import TimelineLensFilter
    return TimelineLensFilter.model_validate({**(body or {}), "case_id": str(case_id)})


def describe_lens(conn, case_id, filter_body: dict) -> dict:
    """``describe`` for the Timeline phone lens: the lens total (communications and the other records' event times,
    as the lens counts them), by kind, with the phones, the zone and the readings not yet confirmed."""
    from services.phone import timeline_lens as TL
    f = _lens_filter(case_id, filter_body)
    sf, other = TL._parts(conn, f)
    comm = {"total": 0, "messages": 0, "calls": 0, "unconfirmed": 0, "collapsed_copies": 0, "limits": []}
    phones = set()
    if sf is not None:
        comm = describe(conn, case_id, sf.model_dump(mode="json"))
        q, _ = streams._query(conn, sf)
        phones |= {str(p) for (p,) in conn.execute(text(
            "WITH m AS (%s) SELECT DISTINCT extraction_id FROM m WHERE %s" % (q.matched_sql(), streams._shown(sf))),
            q.params)}
    others, other_unconfirmed = 0, 0
    if other is not None:
        r = conn.execute(text(
            "SELECT count(*) AS n, count(*) FILTER (WHERE t.interpretation_level = 'applied_unconfirmed') AS u, "
            "array_agg(DISTINCT t.extraction_id::text) AS p FROM pv_timeline_entry t WHERE %s" % other.where),
            other.p).one()
        others, other_unconfirmed = int(r.n), int(r.u)
        phones |= set(r.p or []) - {None}
        other_sensitive = int(conn.execute(text(
            "SELECT count(*) FROM pv_text x WHERE x.is_sensitive AND x.record_uid IN (SELECT t.record_uid FROM "
            "pv_timeline_entry t WHERE %s)" % other.where), other.p).scalar() or 0)
    else:
        other_sensitive = 0
    zone = streams.resolve_zone(conn, f)
    total = comm["total"] + others
    return {"case_id": str(case_id), "total": total, "messages": comm["messages"], "calls": comm["calls"],
            "other": total - comm["messages"] - comm["calls"], "unconfirmed": comm["unconfirmed"] + other_unconfirmed,
            "phones": len(phones), "collapsed_copies": comm["collapsed_copies"], "zone": zone["display_name"],
            "left_out": LEFT_OUT, "sensitive_values": comm.get("sensitive_values", 0) + other_sensitive,
            "limits": comm["limits"], "snapshot": snapshot(conn, f),
            "hidden": TL.hidden_counts(conn, f)["words"]}


def describe_source(conn, case_id, source: str, filter_body: dict) -> dict:
    return describe_lens(conn, case_id, filter_body) if source == "timeline_lens" else \
        describe(conn, case_id, filter_body)


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
    # the sensitive values on the rows the export prints: left out unless Include sensitive fields is ticked (3.10)
    sens = int(conn.execute(text(
        "WITH m AS (%s) SELECT count(*) FROM pv_text x WHERE x.is_sensitive AND x.record_uid IN (SELECT record_uid "
        "FROM m WHERE %s)" % (q.matched_sql(), shown)), q.params).scalar() or 0)
    return {"case_id": str(case_id), "total": total, "messages": int(r.messages), "calls": int(r.calls),
            "other": total - int(r.messages) - int(r.calls), "unconfirmed": int(r.unconfirmed),
            "phones": int(r.phones), "collapsed_copies": int(r.collapsed), "zone": zone["display_name"],
            "left_out": LEFT_OUT, "sensitive_values": sens, "limits": streams.limits_for(conn, f),
            "snapshot": snapshot(conn, f)}


# ---- machine-generated text on the attachments in scope (07 5 Media, M-7) -------------------------------------------

_LATEST_DONE = ("SELECT DISTINCT ON (d.file_uid, d.kind) d.* FROM phone_derived_texts d WHERE d.case_id = "
                "CAST(:c AS uuid) AND d.state = 'done' " + IN_USE_ORDER)
PROMPT_ITEMS = 50  # the export dialog lists at most this many unconfirmed texts; it states the rest as a count


def machine_texts(conn, case_id, file_uids) -> dict:
    """{file_uid: [machine text with its origin mark]} for the given files: the latest finished text of each kind.
    The text printed is the corrected text where a person corrected it; the mark says which it is (07 4.6)."""
    from services.phone import derive
    uids = sorted({u for u in file_uids if u})
    if not uids:
        return {}
    out = {}
    for r in conn.execute(text("SELECT * FROM (" + _LATEST_DONE + ") d WHERE d.file_uid = ANY(CAST(:u AS uuid[])) "
                               "ORDER BY d.file_uid, d.kind"), {"c": str(case_id), "u": uids}):
        d = dict(r._mapping)
        mark = derive.origin(d)
        out.setdefault(str(d["file_uid"]), []).append({
            "id": str(d["id"]), "kind": d["kind"], "origin": mark,
            "text": d["corrected_text"] if d.get("corrected_text") is not None else (d["text"] or "")})
    # a machine translation of the text (05 17.5) prints under it with its own label
    from services.phone import translate
    tr = translate.latest_for(conn, case_id, "derived_text", [t["id"] for ts in out.values() for t in ts])
    for ts in out.values():
        for t in ts:
            t["translation"] = printable_translation(tr.get(t["id"]))
    return out


def printable_translation(t):
    """A finished translation to print, or None: what was made, with its label, or its stale words."""
    if not t or t["state"] != "done" or t["outcome"] != "translated":
        return None
    return t


def describe_machine_text(conn, case_id, filter_body: dict, lens: bool = False) -> dict:
    """Machine-generated texts on the attachments of the rows an export would print, for the prompt "This transcript
    is machine-generated. Listen and confirm, or keep it marked" (07 5 Media). Counts are true; the list is capped at
    ``PROMPT_ITEMS`` and says so."""
    none = {"total": 0, "unconfirmed": 0, "items": [], "items_cap": PROMPT_ITEMS}
    if not conn.execute(text("SELECT EXISTS (SELECT 1 FROM phone_derived_texts WHERE case_id = CAST(:c AS uuid) AND "
                             "state = 'done')"), {"c": str(case_id)}).scalar():
        return none
    from services.phone import derive
    if lens:
        from services.phone import timeline_lens as TL
        f = TL._stream_filter(_lens_filter(case_id, filter_body))
        if f is None:  # no message or call in the lens: no attachment either
            return none
    else:
        f = _filter(case_id, filter_body)
    q, _ = streams._query(conn, f)
    p = dict(q.params, dc=str(case_id))
    rows = conn.execute(text(
        "WITH m AS (%s), shown AS (SELECT record_uid FROM m WHERE %s), "
        "d AS (%s) "
        "SELECT DISTINCT d.id, d.file_uid, d.kind, d.state, d.model, d.model_version, d.finished_at, d.corrected_at, "
        "d.corrected_by_name, d.correction_reason, d.confirmed_at, d.confirmed_by_name, f.local_path FROM d "
        "JOIN pv_attachment_link a ON a.file_uid = d.file_uid LEFT JOIN pv_file f ON f.file_uid = d.file_uid "
        "LEFT JOIN (SELECT s.record_uid, s.parent_record_uid FROM phone_record_summaries s JOIN "
        "phone_interpretation_state st ON st.extraction_id = s.extraction_id AND st.generation = s.generation) s "
        "ON s.record_uid = a.record_uid "
        "WHERE a.record_uid IN (SELECT record_uid FROM shown) OR s.parent_record_uid IN (SELECT record_uid FROM shown)"
        % (q.matched_sql(), streams._shown(f), _LATEST_DONE.replace(":c", ":dc"))), p).fetchall()
    items = []
    unconfirmed = 0
    for r in rows:
        d = dict(r._mapping)
        mark = derive.origin(d)
        if mark["confirmed"]:
            continue
        unconfirmed += 1
        if len(items) < PROMPT_ITEMS:
            items.append({"id": str(d["id"]), "file_uid": str(d["file_uid"]), "kind": d["kind"],
                          "filename": (d["local_path"] or "").replace("\\", "/").rsplit("/", 1)[-1] or None,
                          "words": mark["words"]})
    return {"total": len(rows), "unconfirmed": unconfirmed, "items": items, "items_cap": PROMPT_ITEMS}


def create(conn, *, case_id, user_id, fmt, source, filter_body, options) -> dict:
    if fmt not in BUILT_FORMATS:
        raise ExportError("An export is a PDF or an RSMF file.")
    if source not in BUILT_SOURCES:
        raise ExportError("Exporting a %s is not built yet." % source.replace("_", " "))
    f = _lens_filter(case_id, filter_body) if source == "timeline_lens" else _filter(case_id, filter_body)
    if source == "phone_profile":
        if fmt != "pdf" or len(f.phones) != 1:
            raise ExportError("A phone summary is exported as a PDF of one phone.")
        if conn.execute(text("SELECT 1 FROM phone_extractions WHERE id = CAST(:e AS uuid) AND case_id = CAST(:c AS uuid)"),
                        {"e": f.phones[0], "c": str(case_id)}).first() is None:
            raise ExportError("That phone is not in this case.")
    elif source not in ("stream", "timeline_lens") and not f.selection:
        raise ExportError("A %s is exported through the selection of its phone records." % source.replace("_", " "))
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
    """Every export of the case, newest first, each with the phones it covers: the filter's phones, the phones of a
    frozen selection it exported, or none listed for a filter over the whole case (``whole_case``)."""
    rows = conn.execute(text(
        "SELECT export_id, format, source, state, progress, counts, filename, size, sha256, error, created_at, "
        "finished_at, options, filter FROM phone_exports WHERE case_id = CAST(:c AS uuid) ORDER BY created_at DESC"),
        {"c": str(case_id)}).fetchall()
    sel_ids = sorted({str((r.filter or {}).get("selection")) for r in rows if (r.filter or {}).get("selection")})
    sel_phones = {}
    if sel_ids:
        for s in conn.execute(text(
                "SELECT id::text AS i, mapping_versions FROM phone_selections WHERE case_id = CAST(:c AS uuid) AND "
                "id::text = ANY(:s)"), {"c": str(case_id), "s": sel_ids}):
            sel_phones[s.i] = sorted(p["extraction_id"] for p in (s.mapping_versions or {}).get("phones", []))
    out = []
    for r in rows:
        f = r.filter or {}
        sel = str(f["selection"]) if f.get("selection") else None
        phones = list(f.get("phones") or []) or (sel_phones.get(sel, []) if sel else [])
        out.append(dict(_out(r), phones=phones, whole_case=not phones and not sel))
    return out


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
    from services.phone import originals
    originals.start_worker(engine, stop)  # Download originals: its own thread, long jobs never hold up a PDF


def _rows(conn, f):
    """Every row the screen shows for ``f``, day by day in screen order: [(day header, rows)], the index."""
    idx = streams.index_comm_events(conn, f)
    days = [(d["day"], "%s, %s" % (d["header"], d["zone_label"]), d["count"]) for d in idx["items"]]
    if idx["no_time_count"]:
        days.append((None, "No time recorded", idx["no_time_count"]))
    return idx, days


def _lens_rows(conn, f):
    """``_rows`` for the Timeline phone lens: its own index, day headers drawn by the same formatter."""
    from services.phone import timeline_lens as TL
    idx = TL.index(conn, f)
    days = [(d["day"], "%s, %s" % (d["header"], d["zone_label"]), d["count"]) for d in idx["items"]]
    if idx["no_time_count"]:
        pos = len(days) if idx["no_time_position"] == "last" else 0
        days.insert(pos, (None, "No time recorded", idx["no_time_count"]))
    return idx, days


def draw(engine, export_id, claimed=None) -> dict:
    from services.phone.exports import pdf
    with engine.connect() as conn:
        e = conn.execute(text(
            "SELECT e.export_id, e.case_id, e.format, e.source, e.filter, e.options, e.created_by, "
            "c.title AS case_title, u.name AS who "
            "FROM phone_exports e JOIN cases c ON c.id = e.case_id LEFT JOIN users u ON u.id = e.created_by "
            "WHERE e.export_id = :i"), {"i": export_id}).one()
        options = e.options or {}
        if e.source == "phone_profile":
            return _draw_profile(engine, conn, e, export_id, options, claimed)
        g = _gather(conn, e, options, lambda v: _progress(engine, export_id, v))
    fmt = e.format or "pdf"
    contains = _contains(e, options, g, fmt)
    extra = {}
    if fmt == "rsmf":
        data, extra = _rsmf(engine, e, export_id, options, contains + ["Review coverage: " + " ".join(g.review), _generated(e),
                                                            "Export %s." % export_id], g.out_days)
    else:
        doc, missing = pdf.build_html(
            title=options.get("title") or "Phone messages", case_name=e.case_title or "", generated=_generated(e),
            export_id=str(export_id), contains=contains, days=g.out_days, participants=g.participants,
            page=options.get("page_size") or "letter", review=g.review, review_threads=g.review_cov)
        data = pdf.render_isolated(doc)
        extra = {"missing_characters": sum(missing.values())}
    counts = {"total": g.total, "messages": g.facts["messages"], "calls": g.facts["calls"],
              "unconfirmed": g.facts["unconfirmed"], "phones": g.facts["phones"], "snapshot": g.snap,
              "machine_texts": g.machine["total"], "machine_texts_unconfirmed": g.machine["unconfirmed"],
              "machine_translations": g.translations["total"], "machine_translations_stale": g.translations["stale"],
              "review": g.review_cov["counts"], "sensitive_values": g.sensitive_total,
              "sensitive_included": g.include_sensitive, "link_state_rows": g.noted_rows, **extra}
    return _store(engine, e, export_id, data, fmt, options, counts, g.snap, claimed, "phone-messages")


def _generated(e) -> str:
    return "Generated by %s on %s UTC." % (e.who or "a Loupe user", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))


PREVIEW_ROWS = 40  # more rows than one page holds; the rest are counted by the same formatter, not laid out
PREVIEW_DPI = 110


def preview(engine, case_id, user_id, source, filter_body, options) -> dict:
    """The first page of the PDF this export would make (07 J-14 step 4, test E-8): the same rows, the same cover and the
    same formatter as ``draw``, nothing stored and nothing queued. Only the first rows are laid out, so a long export
    previews in the time one page takes; the cover's counts still come from every row. Sensitive values stay out of a
    preview even when the export will print them: a preview leaves no record, and a value is shown only on the record of
    a Reveal or of the export (05 section 3.8, 03 section 3.10)."""
    import fitz

    from services.phone.exports import pdf
    if source not in BUILT_SOURCES or source == "phone_profile":
        raise ExportError("This export has no preview.")
    f = _lens_filter(case_id, filter_body) if source == "timeline_lens" else _filter(case_id, filter_body)
    if source not in ("stream", "timeline_lens") and not f.selection:
        raise ExportError("A %s is exported through the selection of its phone records." % source.replace("_", " "))
    stored = json.loads(f.model_dump_json())
    options = {k: v for k, v in (options or {}).items() if k != "include_sensitive"}
    with engine.connect() as conn:
        who = conn.execute(text("SELECT c.title AS case_title, u.name AS who FROM cases c LEFT JOIN users u ON u.id = :u "
                                "WHERE c.id = :c"), {"c": str(case_id), "u": str(user_id)}).one()
        e = SimpleNamespace(case_id=case_id, source=source, filter=stored, who=who.who, case_title=who.case_title)
        g = _gather(conn, e, options or {}, lambda v: None)
    doc, _ = pdf.build_html(
        title=(options or {}).get("title") or "Phone messages", case_name=e.case_title or "", generated=_generated(e),
        export_id="(preview)", contains=_contains(e, options or {}, g, "pdf"), days=g.out_days,
        participants=g.participants, page=(options or {}).get("page_size") or "letter", review=g.review,
        review_threads=g.review_cov, layout_rows=PREVIEW_ROWS)
    data = pdf.render_isolated(doc)
    with fitz.open(stream=data, filetype="pdf") as pages:
        first = pages[0]
        return {"image": base64.b64encode(first.get_pixmap(dpi=PREVIEW_DPI).tobytes("png")).decode(),
                "text": first.get_text(), "rows": g.total}


def _gather(conn, e, options, progress) -> SimpleNamespace:
    """Every row of an export and what its cover states; ``draw`` and ``preview`` both read through here."""
    from services.phone.readings import phone_labels
    lens = e.source == "timeline_lens"
    if lens:
        from services.phone import timeline_lens as TL
        f = _lens_filter(e.case_id, e.filter)
        facts = describe_lens(conn, e.case_id, e.filter)
        idx, days = _lens_rows(conn, f)
        window, window_max = TL.window, TL.WINDOW_MAX
    else:
        f = StreamFilter.model_validate(e.filter)
        facts = describe(conn, e.case_id, e.filter)
        idx, days = _rows(conn, f)
        window, window_max = streams.window_comm_events, streams.WINDOW_MAX
    snap = idx["snapshot"]
    total = sum(n for _, _, n in days)
    if lens and facts["total"] != total:  # the stated total is the lens total (E-4); never deliver a mismatch
        raise RuntimeError("lens export stated total %d differs from the lens total %d" % (facts["total"], total))
    out_days, seen, people = [], 0, {}
    for day, header, n in days:
        rows = []
        for off in range(0, n, window_max):
            w = window(conn, f, snapshot_token=snap, day=day, offset=off, limit=window_max)
            rows.extend(w["items"])
        out_days.append((header, rows))
        seen += len(rows)
        for r in rows:
            for lab in [r.get("from")] + list(r.get("to") or []):
                if lab:
                    ident = L.identifier_text(lab.get("identifier"))
                    people.setdefault(L.label_text(lab), set()).update([ident] if ident else [])
        if total:
            progress(0.8 * seen / total)
    if seen != total:  # the stated total and the printed rows must agree (E-4); never deliver a mismatch
        raise RuntimeError("export rows %d differ from the index total %d" % (seen, total))
    # machine text on the attachments prints under each one with its mark (07 5 Media, M-7)
    texts = machine_texts(conn, e.case_id, [a.get("file_uid") for _, rows in out_days for r in rows
                                            for a in r.get("attachments") or []])
    machine = {"total": 0, "unconfirmed": 0}
    translations = {"total": 0, "stale": 0, "stale_message": 0, "stale_derived_text": 0}
    for _, rows in out_days:
        for r in rows:
            # a message's machine translation prints under the original with its label (05 17.5)
            r["translation"] = printable_translation(r.get("translation"))
            for t in [r["translation"]] + [m.get("translation") for a in r.get("attachments") or []
                                           for m in texts.get(a.get("file_uid") or "", [])]:
                if t:
                    translations["total"] += 1
                    if t["stale"]:
                        translations["stale"] += 1
                        translations["stale_" + t["source_type"]] += 1
            for a in r.get("attachments") or []:
                a["machine_texts"] = texts.get(a.get("file_uid") or "", [])
                machine["total"] += len(a["machine_texts"])
                machine["unconfirmed"] += sum(1 for t in a["machine_texts"] if not t["origin"]["confirmed"])
    # 03 section 3.10: sensitive values stay out unless the export option Include sensitive fields is ticked,
    # which the cover and the counts record; either way their number is stated
    sens = sensitive_values(conn, e.case_id, [r.get("record_uid") for _, rows in out_days for r in rows])
    include_sensitive = bool(options.get("include_sensitive"))
    sensitive_total = sum(len(v) for v in sens.values())
    if include_sensitive:
        for _, rows in out_days:
            for r in rows:
                r["sensitive"] = sens.get(r.get("record_uid") or "", [])
    # 07 CO-8, CO-15: what was collected carries the state of its links, both values on the row
    link_notes = {}
    if e.source in LINK_SOURCES and getattr(f, "selection", None):
        from services.phone import link_states
        link_notes = link_states.export_notes(conn, e.case_id, f.selection)
        for _, rows in out_days:
            for r in rows:
                r["link_notes"] = link_notes.get(r.get("record_uid") or "", [])
    noted_rows = sum(1 for _, rows in out_days for r in rows if r.get("link_notes"))
    phones = sorted(set(phone_labels(conn, e.case_id).get(p, "") for p in (f.phones or [])) - {""})
    # the review coverage of the threads this export prints (07 J-13 step 6, CO-20): the marks' own counts
    from services.phone import review_share
    exported = {(r.get("thread") or {}).get("thread_key") or (streams.NO_THREAD_PREFIX + r["phone"]["extraction_id"])
                for _, rows in out_days for r in rows if r.get("source") != "other"}
    review_cov = review_share.coverage(conn, e.case_id, thread_keys=exported)
    review = review_share.cover_lines(review_cov)
    return SimpleNamespace(f=f, facts=facts, snap=snap, total=total, out_days=out_days, machine=machine,
                           translations=translations, sensitive_total=sensitive_total,
                           include_sensitive=include_sensitive, noted_rows=noted_rows, phones=phones,
                           review=review, review_cov=review_cov, lens=lens,
                           participants=sorted((k, sorted(v)) for k, v in people.items()))


def _contains(e, options, g, fmt) -> list:
    """The cover's "What this export contains" sentences; the dialog's preview prints the same ones."""
    f, facts, total, machine, translations = g.f, g.facts, g.total, g.machine, g.translations
    include_sensitive, sensitive_total, noted_rows = g.include_sensitive, g.sensitive_total, g.noted_rows
    out_days, phones, lens = g.out_days, g.phones, g.lens
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
        sensitive_words(include_sensitive, sensitive_total),
    ]
    if e.source in LINK_SOURCES:
        contains.insert(-1, ("%s of these %s rows changed since they were collected (corrected, read differently or "
                             "set aside as a duplicate); each such row shows what changed." % (
                                 "{:,}".format(noted_rows), "{:,}".format(total))) if noted_rows else
                        "No row was corrected, read differently or set aside since it was collected.")
        if fmt == "rsmf":  # RSMF rows hold the originals only, so every note is printed here, none clipped
            contains += ["Record %s: %s" % (r.get("record_uid"), word) for _, rows in out_days for r in rows
                         for word in r.get("link_notes") or []]
    if machine["total"] and fmt == "rsmf":
        # RSMF carries the original files only; the machine texts are named so their absence is not silent
        n = machine["total"]
        contains.insert(-1, "%s machine-generated %s (transcripts or text read from images) %s kept in Loupe for these "
                            "attachments; an RSMF file carries the original files only, so %s not in this file." % (
                                "{:,}".format(n), "text" if n == 1 else "texts", "is" if n == 1 else "are",
                                "it is" if n == 1 else "they are"))
    elif machine["total"]:
        n, u = machine["total"], machine["unconfirmed"]
        contains.insert(-1, "%s machine-generated %s (transcripts or text read from images) %s printed under %s; %s not yet confirmed by a person, and each says so." % (
                                "{:,}".format(n), "text" if n == 1 else "texts", "is" if n == 1 else "are",
                                "its attachment" if n == 1 else "their attachments", "{:,}".format(u) + (" is" if u == 1 else " are")))
    if translations["total"] and fmt == "rsmf":
        # RSMF carries the original messages only; the translations are named so their absence is not silent
        n = translations["total"]
        contains.insert(-1, "%s machine %s made on this server %s kept in Loupe for these messages; an RSMF file "
                            "carries the originals only, so %s not in this file." % (
                                "{:,}".format(n), "translation" if n == 1 else "translations",
                                "is" if n == 1 else "are", "it is" if n == 1 else "they are"))
    elif translations["total"]:
        n = translations["total"]
        contains.insert(-1, "%s machine %s made on this server %s printed under %s original%s, each labelled and "
                            "not checked by a person.%s" % (
                                "{:,}".format(n), "translation" if n == 1 else "translations",
                                "is" if n == 1 else "are", "its" if n == 1 else "their", "" if n == 1 else "s",
                                _stale_words(translations["stale_message"], translations["stale_derived_text"])))
    if lens:
        # the lens's kinds of entry, and the device events and sensor readings it is not showing (T-7)
        from services.phone import timeline_lens as TL
        contains.insert(1, "The Case Timeline phone lens: %s, one row per event time, day by day as the lens shows "
                           "them." % ", ".join(TL.KIND_WORDS[k].lower() for k in TL.KIND_WORDS if k in f.lens_kinds))
        if facts.get("hidden"):
            contains.insert(2, facts["hidden"])
        if place_words(f.lens_kinds):
            contains.insert(2, place_words(f.lens_kinds))
    if phones:
        contains.insert(1, "Phones: %s." % ", ".join(phones))
    contains += [lim["message"] for lim in facts["limits"]]
    return contains


def sensitive_values(conn, case_id, record_uids) -> dict:
    """The sensitive values (saved passwords, card numbers, autofill and the like; 05 section 3.8) of the exported
    records at their current reading: {record_uid: [{"field", "value"}]}."""
    uids = sorted({str(u) for u in record_uids if u})
    out: dict = {}
    if not uids:
        return out
    for r in conn.execute(text(
            "SELECT record_uid::text AS u, field_path, value FROM pv_text WHERE case_id = CAST(:c AS uuid) AND "
            "is_sensitive AND record_uid = ANY(CAST(:u AS uuid[])) ORDER BY record_uid, field_path"),
            {"c": str(case_id), "u": uids}):
        out.setdefault(r.u, []).append({"field": r.field_path, "value": r.value})
    return out


def sensitive_words(included: bool, n: int) -> str:
    """The cover line for sensitive fields: left out by default, included only when the option was ticked."""
    if included:
        return ("Sensitive fields included, as the export option was ticked: %s %s (saved passwords, card numbers "
                "and the like) printed under %s record." % ("{:,}".format(n), "value" if n == 1 else "values",
                                                           "its" if n == 1 else "their")) if n else \
            "Sensitive fields included, as the export option was ticked; none of these rows has one."
    if n:
        return "%s: %s %s on these rows %s not printed." % (LEFT_OUT.rstrip("."), "{:,}".format(n),
                                                               "sensitive value" if n == 1 else "sensitive values",
                                                               "is" if n == 1 else "are")
    return LEFT_OUT


def _part_path(e, export_id) -> Path:
    folder = export_dir() / str(e.case_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (".%s.part" % export_id)


def _store(engine, e, export_id, data, fmt, options, counts, snap, claimed, default_name):
    """Write the file under a temporary name, move it into place, and mark the export done (nothing half-delivered).
    ``data`` is the file's bytes, or the path of the part already written beside its final place."""
    tmp = _part_path(e, export_id)
    final = tmp.parent / ("%s.%s" % (export_id, fmt))
    if isinstance(data, Path):
        digest = hashlib.sha256()
        with open(data, "rb") as written:
            for block in iter(lambda: written.read(1024 * 1024), b""):
                digest.update(block)
        sha, size = digest.hexdigest(), data.stat().st_size
    else:
        sha, size = hashlib.sha256(data).hexdigest(), len(data)
        tmp.write_bytes(data)
    os.replace(tmp, final)
    stem = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in (options.get("title") or ""))[:80]
    filename = "%s.%s" % (stem.strip(" _") and stem.strip() or default_name, fmt)
    with engine.begin() as c:
        done = c.execute(text(
            "UPDATE phone_exports SET state = 'done', progress = 1, counts = CAST(:k AS jsonb), filename = :n, "
            "size = :s, sha256 = :h, storage_path = :p, finished_at = now(), snapshot = :snap WHERE export_id = :i AND state = 'rendering' AND "
            "(CAST(:t AS timestamptz) IS NULL OR started_at = :t)"),
            {"k": json.dumps(counts), "n": filename, "s": size, "h": sha, "p": str(final), "snap": snap,
             "i": export_id, "t": claimed}).rowcount
    if not done:  # another worker holds the claim now; it records the result
        return {"export_id": str(export_id), "state": "lost", "counts": counts}
    return {"export_id": str(export_id), "state": "done", "counts": counts}


def _draw_profile(engine, conn, e, export_id, options, claimed) -> dict:
    """Export profile as PDF (03 section 7.3): the Phone summary's sections, every number as the page shows it, drawn
    by the same renderer as the other exports."""
    from services.phone import profile as P
    from services.phone.exports import pdf
    ext = (e.filter or {}).get("phones", [None])[0]
    p = P.profile(conn, str(e.case_id), ext)
    sections = P.profile_sections(p)
    generated = "Generated by %s on %s UTC." % (e.who or "a Loupe user", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))
    doc, missing = pdf.build_sections_html(
        title=options.get("title") or "Phone summary: %s" % p["phone"]["label"], case_name=e.case_title or "",
        generated=generated, export_id=str(export_id), sections=sections, page=options.get("page_size") or "letter")
    data = pdf.render_isolated(doc)
    snap = "profile:%s:%s" % (ext, p["verdict"]["records"])
    counts = {"total": p["verdict"]["records"], "messages": None, "calls": None, "unconfirmed": None, "phones": 1,
              "sections": len(sections), "missing_characters": sum(missing.values())}
    return _store(engine, e, export_id, data, "pdf", options, counts, snap, claimed, "phone-summary")


def place_words(lens_kinds) -> str | None:
    """The investigative label on an export that prints places (the investigative-workflows report: "the label on
    every map, export and agent sentence that uses a place")."""
    from services.pattern_of_life.places import PLACE_LABEL_WORDS
    if "locations" in (lens_kinds or ()):
        return "Locations in this export: %s. A position is what the phone recorded, read by an investigator." % (
            PLACE_LABEL_WORDS.lower())
    return None


def _rsmf(engine, e, export_id, options, contains, out_days):
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
        return opener, None
    part = _part_path(e, export_id)
    with open(part, "wb") as out:
        _, counts = rsmf.build(rows, title=options.get("title") or "Phone messages", contains=contains,
                               read_file=read_file, out=out, spool_dir=part.parent)
    if counts["events"] != len(rows):
        raise RuntimeError("RSMF events %d differ from the rows %d" % (counts["events"], len(rows)))
    return part, {"rsmf": counts}


def _stale_words(messages: int, texts: int) -> str:
    """The cover's count of translations made from an earlier text, said per kind of original (05 17.5)."""
    parts = []
    for k, what in ((messages, "a message"), (texts, "a transcript or text read from an image")):
        if k:
            parts.append(" %s %s made from an earlier text of %s corrected since, and %s so." % (
                "{:,}".format(k), "was" if k == 1 else "were", what, "says" if k == 1 else "say"))
    return "".join(parts)


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
