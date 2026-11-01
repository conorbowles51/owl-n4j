"""The phone capture job body, synchronous, run in a worker thread (01 section 10.3).

Stages, each recorded in ``phone_extractions.capture_state`` and reported through ``report``:
verifying_container, detecting, counting, capturing, reconciling, indexing_files, finishing.

Durable progress is in Postgres (plan lesson 5.4): document digests and counter results on the document rows,
the capture cursor per document, file verification per file row. A rerun after a pause, a failure or a kill
continues from there and produces the same rows (01 section 10.5, decision D26).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

from app.phone import detect
from app.phone.capture import CAPTURE_CODE_VERSION, Capture, CaptureMemoryBudgetExceeded
from app.phone.counter import count_stream
from app.phone.reconcile import failure_message, reconcile, store_reconciliation
from app.phone.recount import recount_document
from app.phone.store import CopySink, prepare_resume

HASH_CHUNK = 4 << 20
CAPTURED = ("captured", "captured_incomplete")
TERMINAL_OK = CAPTURED + ("not_readable",)


class StopRequested(Exception):
    """Pause or cancel requested; raised at a committed boundary."""


class CaptureFailed(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Reporter:
    """Progress hook. ``stage(name, progress, message, counts)``; throttled by the caller's publisher."""

    def stage(self, name, progress, message="", counts=None):
        pass

    def should_stop(self):
        return False


def _band(lo, hi, done, total):
    return lo + (hi - lo) * (min(done, total) / total if total else 1.0)


# --- hashing -------------------------------------------------------------------------------------------------

def hash_stream(fh, on_bytes=None):
    sha, md5, n = hashlib.sha256(), hashlib.md5(), 0
    while True:
        b = fh.read(HASH_CHUNK)
        if not b:
            break
        sha.update(b)
        md5.update(b)
        n += len(b)
        if on_bytes is not None:
            on_bytes(len(b))
    return sha.hexdigest(), md5.hexdigest(), n


def hash_container(path, on_bytes=None, should_stop=None):
    """Container digests (01 section 3 step 1). A folder's digest is over its sorted manifest lines
    ``"{sha256}  {size}  {relative path}\\n"`` of every non-skipped file; each member keeps its own digests.
    Returns (sha256, md5, size_bytes, members) with members {relpath: (size, sha256, md5)} for a folder."""
    if os.path.isdir(path):
        src = detect.FolderSource(path)
        members = {}
        lines = []
        total = 0
        for rel, size in src.entries():
            if detect.skip_rule(rel) is not None:
                continue
            with src.open(rel) as fh:
                s, m, n = hash_stream(fh, on_bytes)
            members[rel] = (n, s, m)
            total += n
            lines.append("%s  %d  %s\n" % (s, n, rel))
            if should_stop is not None and should_stop():
                raise StopRequested()
        manifest = "".join(lines).encode("utf-8")
        return hashlib.sha256(manifest).hexdigest(), hashlib.md5(manifest).hexdigest(), total, members
    with open(path, "rb") as fh:
        s, m, n = hash_stream(fh, on_bytes)
    return s, m, n, None


def report_set_key(documents) -> str:
    """01 section 6.3: sha256 over sorted "role:sha256" lines of the non-empty documents."""
    lines = sorted("%s:%s" % (d["role"], d["sha256"]) for d in documents if not d["empty"])
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# --- database helpers ----------------------------------------------------------------------------------------

def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _exec(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def set_state(conn, extraction_id, state):
    with conn.transaction():
        _exec(conn, "UPDATE phone_extractions SET capture_state = %s WHERE id = %s", (state, extraction_id))


def merge_flags(conn, extraction_id, flags: dict):
    with conn.transaction():
        _exec(conn, "UPDATE phone_extractions SET flags = flags || %s::jsonb WHERE id = %s",
              (json.dumps(flags), extraction_id))


def upsert_container(conn, *, case_id, stored_path, original_name, kind, sha256, md5, size, upload_sha256,
                     classification, evidence_file_id, upload_group_id, user_id):
    with conn.transaction():
        row = _one(conn, "SELECT id FROM phone_extraction_containers WHERE case_id = %s AND stored_path = %s "
                         "AND sha256 = %s", (case_id, stored_path, sha256))
        if row:
            _exec(conn, "UPDATE phone_extraction_containers SET classification = %s, intake_outcome = %s, "
                        "container_kind = %s, evidence_file_id = COALESCE(evidence_file_id, %s) WHERE id = %s",
                  (json.dumps(classification), classification["outcome"], kind, evidence_file_id, row[0]))
            return row[0]
        cid = uuid.uuid4()
        _exec(conn, "INSERT INTO phone_extraction_containers (id, case_id, evidence_file_id, upload_group_id, "
                    "container_kind, stored_path, original_name, size_bytes, sha256, md5, upload_sha256, "
                    "intake_outcome, classification, received_by_user_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
              (cid, case_id, evidence_file_id, upload_group_id, kind, stored_path, original_name[:1024], size,
               sha256, md5, upload_sha256, classification["outcome"], json.dumps(classification), user_id))
        return cid


# --- the job -------------------------------------------------------------------------------------------------

def run_capture(conn, *, data_root, case_id, container_path, root_path, original_name=None, upload_sha256=None,
                container_evidence_id=None, upload_group_id=None, user_id=None, job_id=None,
                reporter: Reporter | None = None, hooks=None):
    """Capture one report root of one container. Returns a result dict with ``state`` and ``message``.

    ``container_path`` and ``root_path`` are relative: the container to ``<data_root>/<case_id>``, the root to the
    container. ``hooks`` are the indexing_files steps (files, references, timestamps), each
    ``hook(conn, ctx, reporter)``.
    """
    rep = reporter or Reporter()
    case_root = os.path.join(data_root, str(case_id))
    full = os.path.join(case_root, container_path) if container_path else case_root
    name = original_name or os.path.basename(full.rstrip("/"))

    # verifying_container
    total_bytes = _container_bytes(full)
    seen = [0]
    last = [0.0]

    def on_bytes(n):
        seen[0] += n
        now = time.monotonic()
        if now - last[0] >= 1.0:
            last[0] = now
            rep.stage("verifying_container", _band(0.0, 0.05, seen[0], total_bytes),
                      "Checking the report: %s of %s bytes" % (format(seen[0], ","), format(total_bytes, ",")),
                      {"bytes_read": seen[0], "bytes_total": total_bytes})

    rep.stage("verifying_container", 0.0, "Checking the report", {"bytes_read": 0, "bytes_total": total_bytes})
    sha, md5, size, members = hash_container(full, on_bytes, rep.should_stop)
    if upload_sha256 and members is None and upload_sha256 != sha:
        raise CaptureFailed("container_changed_since_upload", "The stored upload no longer matches what was "
                            "received. It has not been read. Upload it again.")

    # detecting
    rep.stage("detecting", 0.05, "Checking the report: finding the report documents")
    classification = detect.classify(full, name)
    kind = classification["container_kind"]
    container_id = upsert_container(
        conn, case_id=case_id, stored_path=container_path, original_name=name, kind=kind, sha256=sha, md5=md5,
        size=size, upload_sha256=upload_sha256, classification=classification,
        evidence_file_id=container_evidence_id, upload_group_id=upload_group_id, user_id=user_id)
    if classification["outcome"] != detect.READABLE:
        return {"state": "not_readable", "container_id": str(container_id), "outcome": classification["outcome"],
                "message": classification["messages"][0]["text"] if classification["messages"] else ""}
    roots = [r for r in classification["roots"] if r["root_path"] == (root_path or "")]
    if not roots:
        raise CaptureFailed("root_not_found", "The report folder named for this reading is not in the upload.")
    root = roots[0]

    source = detect.open_source(full) if kind != "single_document" else detect.FolderSource(os.path.dirname(full))
    try:
        return _run_root(conn, rep, source, members, case_id, container_id, root, job_id, classification, hooks)
    finally:
        source.close()


def _container_bytes(full):
    if os.path.isdir(full):
        return sum(s for rel, s in detect.FolderSource(full).entries() if detect.skip_rule(rel) is None)
    return os.path.getsize(full)


def _document_digests(source, members, root):
    docs = []
    for d in root["documents"]:
        if members is not None and d["path"] in members:
            n, s, m = members[d["path"]]
        elif d["empty"]:
            n, s, m = 0, hashlib.sha256(b"").hexdigest(), hashlib.md5(b"").hexdigest()
        else:
            with source.open(d["path"]) as fh:
                s, m, n = hash_stream(fh)
        docs.append(dict(d, sha256=s, md5=m, size=n))
    return docs


def _run_root(conn, rep, source, members, case_id, container_id, root, job_id, classification, hooks):
    docs = _document_digests(source, members, root)
    key = report_set_key(docs)
    form = root["form"]
    with conn.transaction():
        row = _one(conn, "SELECT id, capture_state FROM phone_extractions WHERE case_id = %s AND "
                         "report_set_sha256 = %s FOR UPDATE", (case_id, key))
        if row is None:
            extraction_id = uuid.uuid4()
            _exec(conn, "INSERT INTO phone_extractions (id, case_id, report_set_sha256, first_container_id, form, "
                        "capture_state, engine_job_id, capture_code_version) VALUES (%s,%s,%s,%s,%s,'detecting',%s,%s)",
                  (extraction_id, case_id, key, container_id, form, job_id, CAPTURE_CODE_VERSION))
            state = "detecting"
        else:
            extraction_id, state = row
        _exec(conn, "INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) "
                    "VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (extraction_id, container_id, root["root_path"]))
        if job_id is not None:
            _exec(conn, "UPDATE phone_extractions SET engine_job_id = %s WHERE id = %s", (job_id, extraction_id))
    if state in CAPTURED:
        return {"state": state, "extraction_id": str(extraction_id), "container_id": str(container_id),
                "already_in_case": True,
                "message": "This phone report is already in the case. The new upload is recorded as a second copy "
                           "of the same report."}
    if root["nested_report_ignored"]:
        merge_flags(conn, extraction_id, {"nested_report_ignored": root["nested_report_ignored"]})
    with conn.transaction():
        for i, d in enumerate(docs):
            _exec(conn, "INSERT INTO phone_extraction_documents (extraction_id, document_index, path, role, "
                        "size_bytes, sha256, md5, root_element, parse_state) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                  (extraction_id, i, d["path"], d["role"], d["size"], d["sha256"], d["md5"], d["root_element"],
                   "empty" if d["empty"] else "pending"))
    ctx = {"extraction_id": extraction_id, "case_id": case_id, "container_id": container_id, "source": source,
           "root_path": root["root_path"], "documents": docs, "members": members, "form": form}

    # counting
    set_state(conn, extraction_id, "counting")
    data_docs = [(i, d) for i, d in enumerate(docs) if not d["empty"]]
    total = sum(d["size"] for _, d in data_docs) or 1
    done = 0
    for i, d in data_docs:
        have = _one(conn, "SELECT source_counts IS NOT NULL FROM phone_extraction_documents WHERE extraction_id = %s "
                          "AND document_index = %s", (extraction_id, i))[0]
        if not have:
            rep.stage("counting", _band(0.05, 0.20, done, total), "Checking the report: counting every element",
                      {"bytes_read": done, "bytes_total": total, "documents_done": i, "documents_total": len(docs)})
            with source.open(d["path"]) as fh:
                counts = count_stream(fh)
            if counts["document"]["sha256"] != d["sha256"]:
                raise CaptureFailed("container_changed_since_upload", "The stored upload no longer matches what was "
                                    "received. It has not been read. Upload it again.")
            with conn.transaction():
                _exec(conn, "UPDATE phone_extraction_documents SET source_counts = %s WHERE extraction_id = %s AND "
                            "document_index = %s", (json.dumps(counts), extraction_id, i))
        done += d["size"]
        if rep.should_stop():
            raise StopRequested()

    # capturing
    set_state(conn, extraction_id, "capturing")
    done = 0
    for i, d in data_docs:
        state, cursor = _one(conn, "SELECT parse_state, capture_cursor FROM phone_extraction_documents WHERE "
                                   "extraction_id = %s AND document_index = %s", (extraction_id, i))
        if state in ("complete", "truncated"):
            done += d["size"]
            continue
        prepare_resume(conn, extraction_id, i, cursor)
        conn.commit()
        sink = CopySink(conn, extraction_id, i)
        base = done
        last = [0.0]

        def on_progress(cap, base=base, i=i):
            now = time.monotonic()
            if now - last[0] >= 1.0:
                last[0] = now
                rep.stage("capturing", _band(0.20, 0.65, base + cap.bytes_read, total),
                          "Reading records: %s read" % format(cap.ordinal["r"], ","),
                          {"bytes_read": base + cap.bytes_read, "bytes_total": total, "records": cap.ordinal["r"],
                           "files": cap.ordinal["f"], "documents_done": i, "documents_total": len(docs)})

        def on_flush(cap):
            if rep.should_stop():
                raise StopRequested()

        cap = Capture(sink, cursor=cursor, on_progress=on_progress, on_flush=on_flush)
        try:
            with source.open(d["path"]) as fh:
                res = cap.run(fh)
        except CaptureMemoryBudgetExceeded as e:
            raise CaptureFailed("memory_budget", str(e))
        with conn.transaction():
            _exec(conn, "UPDATE phone_extraction_documents SET parse_state = %s, truncation = %s, skeleton = %s, "
                        "root_element = %s, capture_cursor = %s WHERE extraction_id = %s AND document_index = %s",
                  (res["parse_state"], json.dumps(res["truncation"]) if res["truncation"] else None,
                   json.dumps(res["skeleton"], ensure_ascii=False), res["root_element"],
                   json.dumps({"record_ordinal": res["counts"]["r"], "file_ordinal": res["counts"]["f"],
                               "extra_ordinal": res["counts"]["x"]}), extraction_id, i))
        if res["truncation"]:
            merge_flags(conn, extraction_id, {"incomplete_source": {
                "document": d["path"].rsplit("/", 1)[-1], "line": res["truncation"]["line"],
                "column": res["truncation"]["column"], "open_path": res["truncation"]["open_path"]}})
        ctx.setdefault("peak_rss", 0)
        ctx["peak_rss"] = max(ctx["peak_rss"], res["peak_rss"])
        done += d["size"]

    # reconciling
    set_state(conn, extraction_id, "reconciling")
    failed = []
    for n, (i, d) in enumerate(data_docs):
        rep.stage("reconciling", _band(0.65, 0.75, n, len(data_docs)), "Checking nothing is missing",
                  {"documents_done": n, "documents_total": len(data_docs)})
        source_counts = _one(conn, "SELECT source_counts FROM phone_extraction_documents WHERE extraction_id = %s "
                                   "AND document_index = %s", (extraction_id, i))[0]
        captured = recount_document(conn, extraction_id, i)
        result, diffs = reconcile(source_counts, captured)
        with conn.transaction():
            store_reconciliation(conn, extraction_id, i, source_counts, captured, result, diffs)
        if result != "exact":
            failed.append(diffs)
    if failed:
        set_state(conn, extraction_id, "reconciliation_failed")
        diffs = [d for f in failed for d in f]
        return {"state": "reconciliation_failed", "extraction_id": str(extraction_id),
                "difference_count": len(diffs), "message": failure_message(diffs)}

    # indexing_files
    set_state(conn, extraction_id, "reconciling")
    ctx["summary"] = {}
    for hook in (DEFAULT_HOOKS if hooks is None else hooks):
        ctx["summary"][hook.__name__] = hook(conn, ctx, rep)
        if rep.should_stop():
            raise StopRequested()

    # finishing
    truncated = _one(conn, "SELECT count(*) FROM phone_extraction_documents WHERE extraction_id = %s AND "
                           "parse_state = 'truncated'", (extraction_id,))[0]
    final = "captured_incomplete" if truncated else "captured"
    with conn.transaction():
        rc = _one(conn, "SELECT count(*) FROM phone_records WHERE extraction_id = %s", (extraction_id,))[0]
        fc = _one(conn, "SELECT count(*) FROM phone_files WHERE extraction_id = %s", (extraction_id,))[0]
        _exec(conn, "UPDATE phone_extractions SET capture_state = %s, standing = CASE WHEN standing = 'pending' "
                    "THEN 'active'::phone_extraction_standing ELSE standing END, record_count = %s, file_count = %s, "
                    "captured_at = now() WHERE id = %s", (final, rc, fc, extraction_id))
    rep.stage("finishing", 1.0, "Ready", {"records": rc, "files": fc})
    outcomes = (ctx["summary"].get("verify_files") or {}).get("outcomes", {})
    message = "Every record was read and checked against the report: %s records and %s files." % (
        format(rc, ","), format(fc, ","))
    if fc and outcomes.get("missing", 0) == fc:
        message += (" None of the %s files the report lists is in the production; each is marked absent."
                    % format(fc, ","))
    return {"state": final, "extraction_id": str(extraction_id), "container_id": str(container_id),
            "records": rc, "files": fc, "peak_rss": ctx.get("peak_rss"), "summary": ctx["summary"],
            "message": message}


def _default_hooks():
    from app.phone.extra_nodes import store_extra_nodes
    from app.phone.files import list_entries, resolve_references, verify_files
    from app.phone.timestamps import store_timestamps
    return (list_entries, verify_files, resolve_references, store_extra_nodes, store_timestamps)


DEFAULT_HOOKS = _default_hooks()
