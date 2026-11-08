"""Export as background work: a request row, one process per export, progress, cancel and expiry.

Every web worker runs ``run_forever``; the export itself is a process of its own (``python -m services.caseport
run-export <id>``), at low priority, so a large case neither holds a web worker's memory nor its event loop. A release
ends that process with the backend: its heartbeat stops, the loop queues it again (twice at most) and it starts over;
what it had written is removed first. A package is kept for ``KEEP_DAYS`` and then removed, because it is a whole copy of
a case sitting outside the case's own controls.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import package as P

log = logging.getLogger(__name__)
KEEP_DAYS = 7
HEARTBEAT_SECONDS = 15
STALE_SECONDS = 180
MAX_ATTEMPTS = 3
POLL_SECONDS = 10
ACTIVE = ("queued", "running", "cancelling")
_DEFAULT_DIR = "/mnt/owl-data/loupe-case-exports"


def export_dir() -> Path:
    """Packages are large: LOUPE_CASE_EXPORT_DIR, else the data disk, else the checkout's own folder."""
    env = os.environ.get("LOUPE_CASE_EXPORT_DIR")
    if env:
        return Path(env)
    if Path("/mnt/owl-data").is_dir():
        return Path(_DEFAULT_DIR)
    from config import DATA_HOME
    return Path(DATA_HOME) / "case-exports"


def package_path(case_id, export_id) -> Path:
    return export_dir() / str(case_id) / f"{export_id}{P.SUFFIX}"


def remove_files(path) -> None:
    p = Path(path)
    for candidate in (p, p.with_name(p.name + P.PARTIAL), p.with_name(p.name + P.PARTIAL + ".part"),
                      p.with_name(p.name + ".sha256")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _connect():
    import psycopg
    import config
    from .export import psycopg_url
    return psycopg.connect(psycopg_url(config.DATABASE_URL), application_name="loupe-case-export-job", autocommit=True)


def _trail(conn, action, *, row, details):
    conn.execute("INSERT INTO activity_events (action, user_id, user_name, user_email, case_id, source_address, details) "
                 "VALUES (%s, %s, %s, %s, %s, 'system', %s::jsonb)",
                 (action, row["user_id"], row["name"], row["email"], row["case_id"], json.dumps(details, default=str)))


def run_one(export_id: str) -> int:
    """The export process: claim the request, write the package, record the outcome. Exit 0 for any recorded outcome."""
    import config
    from . import export as X
    from .stores import GraphStore, VectorStore
    with _connect() as conn:
        claimed = conn.execute(
            "UPDATE case_exports SET status = 'running', attempts = attempts + 1, heartbeat_at = now(), error = NULL "
            "WHERE id = %s AND status = 'queued' RETURNING case_id, requested_by_user_id, requested_by_email, "
            "requested_by_name, whole, attempts", (export_id,)).fetchone()
        if claimed is None:
            return 0
        case_id, user_id, email, name, whole, attempts = claimed
        row = dict(user_id=user_id, email=email, name=name, case_id=case_id)
        target = package_path(case_id, export_id)
        remove_files(target)
        beat = dict(at=0.0)

        def heartbeat(phase=None, done=None, total=None):
            now = time.monotonic()
            if now - beat["at"] < HEARTBEAT_SECONDS:
                return
            beat["at"] = now
            conn.execute("UPDATE case_exports SET heartbeat_at = now(), phase = coalesce(%s, phase), "
                         "done = coalesce(%s, done), total = coalesce(%s, total) WHERE id = %s",
                         (phase, done, total, export_id))

        def cancelled():
            heartbeat()
            state = conn.execute("SELECT status FROM case_exports WHERE id = %s", (export_id,)).fetchone()
            return state is None or state[0] == "cancelling"

        graph = vectors = None
        try:
            graph, vectors = GraphStore.from_config(), VectorStore.from_config()
            out = X.run_export(config.DATABASE_URL, case_id, exporter=dict(id=str(user_id), email=email, name=name),
                               target=target, evidence_root=config.EVIDENCE_DATA_ROOT, graph=graph, vectors=vectors,
                               progress=lambda phase, done, total: heartbeat(phase, done, total),
                               should_stop=cancelled, whole=whole)
            expires = datetime.now(timezone.utc) + timedelta(days=KEEP_DAYS)
            summary = {k: v for k, v in out["summary"].items()}
            conn.execute("UPDATE case_exports SET status = 'complete', phase = NULL, done = total, path = %s, "
                         "size_bytes = %s, sha256 = %s, summary = %s::jsonb, finished_at = now(), expires_at = %s "
                         "WHERE id = %s", (out["path"], out["size"], out["sha256"], json.dumps(summary, default=str),
                                           expires, export_id))
            _trail(conn, "case_export_finished", row=row,
                   details=dict(export_id=export_id, sha256=out["sha256"], size_bytes=out["size"], **{
                       k: summary[k] for k in ("tables", "rows", "evidence_files", "graph", "vectors",
                                               "rows_private_to_others_left_out")}))
        except X.Cancelled:
            conn.execute("UPDATE case_exports SET status = 'cancelled', phase = NULL, finished_at = now() WHERE id = %s",
                         (export_id,))
            _trail(conn, "case_export_cancelled", row=row, details=dict(export_id=export_id))
        except X.ExportRefused as exc:
            _fail(conn, export_id, row, str(exc))
        except Exception as exc:  # noqa: BLE001 - recorded with its reference for whoever asked
            log.exception("Case export %s failed", export_id)
            _fail(conn, export_id, row, f"The export stopped. Nothing was kept. Reference {export_id}. "
                  f"{type(exc).__name__}: {str(exc)[:300]}")
        finally:
            if graph is not None:
                graph.close()
    return 0


def _fail(conn, export_id, row, reason):
    conn.execute("UPDATE case_exports SET status = 'failed', phase = NULL, error = %s, finished_at = now() WHERE id = %s",
                 (reason, export_id))
    _trail(conn, "case_export_failed", row=row, details=dict(export_id=export_id, reason=reason))


def tick(spawn=None) -> dict:
    """One pass: requeue exports whose process died, expire old packages, remove orphans, start what is queued."""
    spawn = spawn or _spawn
    out = dict(requeued=0, failed=0, expired=0, started=0)
    with _connect() as conn:
        got = conn.execute("SELECT pg_try_advisory_lock(hashtext('loupe_case_exports'))").fetchone()[0]
        if not got:
            return out
        try:
            for export_id, case_id, attempts, user_id, name, email in conn.execute(
                    "SELECT id, case_id, attempts, requested_by_user_id, requested_by_name, requested_by_email "
                    "FROM case_exports WHERE status IN ('running', 'cancelling') "
                    "AND heartbeat_at < now() - make_interval(secs => %s)", (STALE_SECONDS,)).fetchall():
                remove_files(package_path(case_id, export_id))
                row = dict(user_id=user_id, name=name, email=email, case_id=case_id)
                state = conn.execute("SELECT status FROM case_exports WHERE id = %s", (export_id,)).fetchone()[0]
                if state == "cancelling":
                    conn.execute("UPDATE case_exports SET status = 'cancelled', finished_at = now() WHERE id = %s",
                                 (export_id,))
                elif attempts >= MAX_ATTEMPTS:
                    _fail(conn, export_id, row, f"The export stopped {attempts} times and nothing was kept. Try again; "
                          f"if it stops again, quote reference {export_id}.")
                    out["failed"] += 1
                else:
                    conn.execute("UPDATE case_exports SET status = 'queued' WHERE id = %s", (export_id,))
                    out["requeued"] += 1
            for export_id, path, case_id, user_id, name, email in conn.execute(
                    "SELECT id, path, case_id, requested_by_user_id, requested_by_name, requested_by_email "
                    "FROM case_exports WHERE status = 'complete' AND expires_at < now()").fetchall():
                if path:
                    remove_files(path)
                conn.execute("UPDATE case_exports SET status = 'expired', path = NULL WHERE id = %s", (export_id,))
                _trail(conn, "case_export_removed", row=dict(user_id=user_id, name=name, email=email, case_id=case_id),
                       details=dict(export_id=export_id, reason="kept for %d days" % KEEP_DAYS))
                out["expired"] += 1
            _remove_orphans(conn)
            running = conn.execute("SELECT count(*) FROM case_exports WHERE status IN ('running', 'cancelling')").fetchone()[0]
            if not running:
                row = conn.execute("SELECT id FROM case_exports WHERE status = 'queued' ORDER BY created_at LIMIT 1").fetchone()
                if row:
                    spawn(str(row[0]))
                    out["started"] = 1
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext('loupe_case_exports'))")
    return out


def _remove_orphans(conn):
    """A package whose request is gone (its case was purged) has no owner left: it goes."""
    root = export_dir()
    if not root.is_dir():
        return
    live = {str(r[0]) for r in conn.execute("SELECT id FROM case_exports WHERE status IN ('queued', 'running', "
                                            "'cancelling', 'complete')").fetchall()}
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for item in folder.iterdir():
            if item.name.split(".", 1)[0] not in live and time.time() - item.stat().st_mtime > 3600:
                item.unlink(missing_ok=True)


def _spawn(export_id: str) -> None:
    backend = Path(__file__).resolve().parents[2]
    subprocess.Popen(["nice", "-n", "10", sys.executable, "-m", "services.caseport", "run-export", export_id],
                     cwd=str(backend), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=False, env={**os.environ, "LOUPE_DB_ROLE": "case-export"})


async def run_forever():
    """Lifespan task of every web worker; the advisory lock lets one pass run at a time."""
    while True:
        try:
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Case export pass failed; it will run again")
        await asyncio.sleep(POLL_SECONDS)
