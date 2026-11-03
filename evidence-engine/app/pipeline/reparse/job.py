"""One re-parse run end to end, on the phone worker (one at a time, inside its memory cap): rebuild the tree from the
phone's verified files, run the pinned tool, read its LAVA output through the reviewed mapping, store the rows.

The tool's rows go to ``phone_reparse_rows`` only, as the tool wrote them: they are never merged into captured or
interpreted rows. The scratch tree and output are removed at the end; the run keeps every output file's SHA-256.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid

from app.phone import source_db
from app.pipeline.reparse import leapp_runner as R
from app.pipeline.reparse import mapping as M

log = logging.getLogger(__name__)


def scratch_root(storage_path: str) -> str:
    return os.path.join(storage_path, "_scratch", "reparse")


def verified_files(conn, case_root, extraction_id):
    """``(original_path, opener, verified)`` for every tagged file of the phone, read from its first container that
    holds it. Unverified files are passed as such and never opened."""
    conts = conn.execute(
        "SELECT c.container_kind, c.stored_path, l.root_path FROM phone_extraction_container_links l JOIN "
        "phone_extraction_containers c ON c.id = l.container_id WHERE l.extraction_id = %s ORDER BY l.linked_at, c.id",
        (str(extraction_id),)).fetchall()
    cur = conn.cursor(name="reparse_files")
    cur.itersize = 2000
    cur.execute("SELECT body->1->>'path', disk_relpath, outcome FROM phone_files WHERE extraction_id = %s "
                "ORDER BY document_index, ordinal", (str(extraction_id),))
    for path, rel, outcome in cur:
        if outcome != "match" or not rel:
            yield path, None, False
            continue
        opener = None
        for kind, stored, root in conts:
            opener = source_db._member_opener(case_root, kind, stored, root, rel)
            if opener is not None:
                break
        yield path, opener, opener is not None
    cur.close()


def create_run(conn, case_id, extraction_id, os_family, requested_by) -> dict:
    tool = R.tool_for(os_family)
    pin = R.pinned(tool)
    run_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO phone_reparse_runs (id, case_id, extraction_id, tool, tool_version, tool_commit, tool_licence, "
        "status, mapping_version, requested_by) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', %s, %s)",
        (run_id, str(case_id), str(extraction_id), tool, pin["version"], pin.get("installed_commit") or pin["commit"],
         pin["licence"], M.VERSION, requested_by))
    return {"id": str(run_id), "tool": tool, "version": pin["version"]}


def execute(conn, run_id, case_root: str, storage_path: str, wall_seconds: int = R.DEFAULT_WALL_SECONDS) -> dict:
    row = conn.execute("UPDATE phone_reparse_runs SET status = 'running', started_at = now() WHERE id = %s AND "
                       "status IN ('queued', 'running') RETURNING extraction_id, tool", (str(run_id),)).fetchone()
    if row is None:
        return {"run_id": str(run_id), "status": "not_queued"}
    ext, tool = row
    work = os.path.join(scratch_root(storage_path), str(run_id))
    shutil.rmtree(work, ignore_errors=True)
    try:
        pin = R.pinned(tool)
        t0 = time.monotonic()
        tree_counts = R.build_tree(verified_files(conn, case_root, ext), os.path.join(work, "tree"))
        tree_counts["seconds"] = round(time.monotonic() - t0, 1)
        rec = R.run(pin, os.path.join(work, "tree"), os.path.join(work, "out"), wall_seconds=wall_seconds)
        lava = R.lava_db(os.path.join(work, "out"))
        counts, stored = {}, 0
        if lava:
            counts, rows = M.read_lava(lava, tool)
            stored = _store_rows(conn, run_id, rows)
        failed = rec["stopped"] or (rec["exit_code"] != 0 and not lava)
        error = rec["stopped"] or ("The tool ended with code %s and wrote no LAVA output." % rec["exit_code"]
                                   if failed else None)
        conn.execute(
            "UPDATE phone_reparse_runs SET status = %s, finished_at = now(), command_line = %s, tree = %s, "
            "exit_code = %s, stopped = %s, seconds = %s, peak_rss_mb = %s, output_manifest_sha256 = %s, "
            "outputs = %s, artefact_counts = %s, error = %s WHERE id = %s",
            ("failed" if failed else "completed", json.dumps(rec["command_line"]), json.dumps(tree_counts),
             rec["exit_code"], rec["stopped"], rec["seconds"], rec["peak_rss_mb"], rec["output"]["manifest_sha256"],
             json.dumps({"files": len(rec["output"]["files"]), "list": rec["output"]["files"]}),
             json.dumps(dict(counts, stored_rows=stored)), error, str(run_id)))
        return {"run_id": str(run_id), "status": "failed" if failed else "completed", "seconds": rec["seconds"],
                "peak_rss_mb": rec["peak_rss_mb"], "tree": tree_counts, "stored_rows": stored}
    except Exception as exc:  # noqa: BLE001 - every failure is named on the run
        log.exception("re-parse run %s failed", run_id)
        conn.execute("UPDATE phone_reparse_runs SET status = 'failed', finished_at = now(), error = %s WHERE id = %s",
                     (("%s: %s" % (type(exc).__name__, exc))[:2000], str(run_id)))
        return {"run_id": str(run_id), "status": "failed"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _store_rows(conn, run_id, rows) -> int:
    n = 0
    with conn.cursor() as cur:
        with cur.copy("COPY phone_reparse_rows (run_id, artefact, row_index, kind, natural_key, instant, instant_text, "
                      "source_path, values) FROM STDIN") as cp:
            for r in rows:
                cp.write_row((str(run_id), r["artefact"], r["row_index"], r["kind"], r["natural_key"], r["instant"],
                              r["instant_text"], r["source_path"], json.dumps(r["values"], default=str)))
                n += 1
    return n
