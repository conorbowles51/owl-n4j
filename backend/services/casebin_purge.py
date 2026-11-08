"""The 30-day purge of Deleted items, run inside the backend (lx-casebin item E).

Jobs cannot install system timers, so the purge is a lifespan task of the backend: at start and then every
``PURGE_EVERY_SECONDS``. Every web worker runs the loop; a Postgres advisory lock lets one purge run at a time across
the host. Each purge is logged and leaves an audit row (``case_purged`` / ``evidence_purged``).

What a purge removes is exactly what the delete removed before Deleted items existed:
- a case: services/case_service.py ``purge_case`` (ChromaDB chunks and entities, then the case row and its cascade);
- an evidence file: its hidden graph is put back first (a hidden node whose key a later upload made again is removed
  instead), then services/evidence_casebin.py ``remove_for_good`` runs the old delete on exactly the Document,
  entities and chunks the delete recorded, then the evidence engine's copy and the row go.

``now`` can be given (tests use it as the clock); nothing reads the clock elsewhere.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

PURGE_EVERY_SECONDS = 6 * 3600
FIRST_DELAY_SECONDS = 300
_LOCK = "hashtext('loupe_casebin_purge')"


def due_cutoff(now=None, days=None):
    from services.case_service import DELETED_RETENTION_DAYS
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=days if days is not None else DELETED_RETENTION_DAYS)


def purge_due(session_factory, *, now=None, engine_delete=None) -> dict:
    """Purge every case and evidence file deleted more than the retention period before ``now``.

    ``engine_delete(case_id, job_id)``: removes the evidence engine's copy (default: the engine client, run to
    completion here). Returns {"cases": [...], "files": [...], "skipped": reason or None}."""
    from postgres import soft_delete
    from postgres.models.case import Case
    from postgres.models.evidence import EvidenceFile
    from services import case_service, evidence_casebin
    cutoff = due_cutoff(now)
    out = {"cases": [], "files": [], "items": [], "skipped": None, "cutoff": cutoff.isoformat()}
    if not soft_delete.enabled():
        # Switched off: deletes are immediate and whatever was left in Deleted items shows again; nothing is purged.
        out["skipped"] = "Deleted items are switched off"
        return out
    with session_factory() as db:
        # The advisory lock belongs to one database connection, and the session hands its connection back to the
        # pool at every commit, so the lock is taken and released on a connection of its own.
        engine = db.get_bind()
        lock = engine.connect() if engine.dialect.name == "postgresql" else None
        if lock is not None:
            locked = lock.execute(text(f"SELECT pg_try_advisory_lock({_LOCK})")).scalar()
            lock.commit()
            if not locked:
                lock.close()
                out["skipped"] = "another process is purging"
                return out
        try:
            with soft_delete.showing_deleted(db):
                case_ids = [c for (c,) in db.query(Case.id).filter(Case.deleted_at.is_not(None),
                                                                     Case.deleted_at < cutoff).all()]
                file_ids = [(f, c) for (f, c) in db.query(EvidenceFile.id, EvidenceFile.case_id).filter(
                    EvidenceFile.deleted_at.is_not(None), EvidenceFile.deleted_at < cutoff).all()]
            db.commit()
            for case_id in case_ids:
                try:
                    details = case_service.purge_case(db, case_id)
                    out["cases"].append(dict(case_id=str(case_id), title=details.get("case_title"),
                                             records_removed=details.get("records_removed")))
                    logger.warning("Deleted items: purged case %s (%s)", case_id, details.get("case_title"))
                except Exception:
                    db.rollback()
                    logger.exception("Deleted items: purge of case %s failed; it stays in Deleted items", case_id)
            purged_cases = {str(c) for c in case_ids}
            for file_id, case_id in file_ids:
                if str(case_id) in purged_cases:
                    continue  # went with its case
                try:
                    out["files"].append(purge_file(db, file_id, engine_delete=engine_delete))
                except Exception:
                    db.rollback()
                    logger.exception("Deleted items: purge of evidence file %s failed; it stays in Deleted items",
                                     file_id)
            # Everything else in Deleted items (services/deleted_items.py): folders, kept copies, deleted rows.
            from services import deleted_items
            out["items"] = deleted_items.purge_due_rows(db, cutoff, engine_delete=engine_delete)
        finally:
            if lock is not None:
                try:
                    lock.execute(text(f"SELECT pg_advisory_unlock({_LOCK})"))
                    lock.commit()
                finally:
                    lock.close()
    return out


def purge_file(db, file_id, *, engine_delete=None, graph_session=None, vector_db=None) -> dict:
    """Put back the file's hidden graph and chunks, then run the delete used before Deleted items."""
    from postgres import soft_delete
    from postgres.models.evidence import EvidenceFile
    from services import activity_trail, evidence_casebin
    with soft_delete.showing_deleted(db):
        record = db.get(EvidenceFile, file_id)
        if record is None or record.deleted_at is None:
            raise evidence_casebin.EvidenceNotDeleted(f"Evidence file {file_id} is not in Deleted items")
        state = record.deleted_state or {}
        own = graph_session is None
        gs = graph_session or evidence_casebin._graph_session()
        try:
            graph = evidence_casebin.purge_graph(gs, case_id=str(record.case_id), file_id=record.id)
        finally:
            if own:
                gs.close()
        # Only what the delete recorded is removed, by its own keys and chunk ids, never by filename: a file of the
        # same name uploaded while this one waited keeps its Document, entities and chunks.
        removed = set(graph["removed_keys"])
        doc_key = state.get("doc_key")
        known = dict(doc_key=None if doc_key in removed else doc_key,
                     exclusive_entities=[e for e in state.get("exclusive_entities") or [] if e.get("key") not in removed],
                     chunk_ids=sorted(state.get("chunk_states") or {}))
        job_id, info = evidence_casebin.remove_for_good(
            db, record, deleted_by_email=state.get("deleted_by_email"),
            delete_exclusive_entities=state.get("delete_exclusive_entities", True), known=known)
        info["hidden_copies_removed"] = sorted(removed)
        if job_id:
            try:
                (engine_delete or _engine_delete)(str(record.case_id), job_id)
                info["engine_copy_removed"] = True
            except Exception as e:
                info["engine_copy_error"] = str(e)[:200]
                logger.warning("Deleted items: engine copy of %s not removed: %s", file_id, e)
        details = dict(info, deleted_at=record.deleted_at.isoformat(),
                       deleted_by_user_id=str(record.deleted_by_user_id) if record.deleted_by_user_id else None,
                       size=record.size, sha256=record.sha256)
        case_id = record.case_id
        db.delete(record)
        activity_trail.record("evidence_purged", db=db, system=True, case_id=case_id, details=details)
        db.commit()
    soft_delete.forget()
    logger.warning("Deleted items: purged evidence file %s (%s)", file_id, details.get("filename"))
    return details


def _engine_request(method: str, path: str, *, missing_ok: bool = False) -> int:
    """One call to the evidence engine on a client of its own. The purge runs outside the request event loop
    (asyncio.run in a worker thread or a script, once per file), and the app's shared client belongs to the loop that
    first used it, so it is not reused here."""
    import httpx
    from config import EVIDENCE_ENGINE_API_KEY, EVIDENCE_ENGINE_TIMEOUT, EVIDENCE_ENGINE_URL

    async def call():
        headers = {"X-Evidence-Engine-Key": EVIDENCE_ENGINE_API_KEY} if EVIDENCE_ENGINE_API_KEY else None
        async with httpx.AsyncClient(base_url=EVIDENCE_ENGINE_URL, headers=headers,
                                     timeout=httpx.Timeout(EVIDENCE_ENGINE_TIMEOUT, connect=10.0)) as client:
            response = await client.request(method, path)
            if missing_ok and response.status_code == 404:
                return 404
            response.raise_for_status()
            return response.status_code
    return asyncio.run(call())


def _engine_delete(case_id, job_id):
    _engine_request("DELETE", f"/cases/{case_id}/files/{job_id}")


async def run_purge_forever():
    """Lifespan task: purge once a few minutes after start, then every PURGE_EVERY_SECONDS."""
    from postgres.session import _get_background_session_local
    await asyncio.sleep(FIRST_DELAY_SECONDS)
    while True:
        try:
            from postgres.soft_delete import enabled
            if not enabled():
                await asyncio.sleep(PURGE_EVERY_SECONDS)
                continue
            result = await asyncio.to_thread(purge_due, _get_background_session_local())
            if result["cases"] or result["files"] or result.get("items") or result["skipped"]:
                logger.warning("Deleted items purge: %d case(s), %d file(s), %d other item(s)%s",
                               len(result["cases"]), len(result["files"]), len(result.get("items") or []),
                               "; " + result["skipped"] if result["skipped"] else "")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Deleted items purge failed; it will run again")
        await asyncio.sleep(PURGE_EVERY_SECONDS)


# ------------------------------------------------------------------------------------ deleted cases' folders (D1)

_UUID_NAME = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _dir_size(path) -> tuple[int, int]:
    import os
    files = size = 0
    for root, _dirs, names in os.walk(path):
        for name in names:
            try:
                size += os.lstat(os.path.join(root, name)).st_size
                files += 1
            except OSError:
                pass
    return files, size


def _references(db, ids: list[str]) -> dict[str, list[str]]:
    """Where each id is still referenced: every uuid column named case_id and every text column whose name holds
    'path' (stored paths, disk paths, job file paths), across every table of the database. {id: ["table.column"]}."""
    from sqlalchemy import text
    found: dict[str, list[str]] = {i: [] for i in ids}
    if not ids:
        return found
    columns = db.execute(text(
        "SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c "
        "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' AND ("
        "(c.column_name = 'case_id') OR (c.column_name ILIKE '%path%' AND c.data_type IN ('text', 'character varying')))"
    )).all()
    pattern = "(" + "|".join(ids) + ")"
    for table, column, data_type in columns:
        if column == "case_id":
            rows = db.execute(text(f'SELECT DISTINCT "{column}"::text FROM "{table}" WHERE "{column}"::text = ANY(:ids)'),
                              {"ids": ids}).scalars().all()
        else:
            rows = db.execute(text(f'SELECT DISTINCT substring("{column}" from :p) FROM "{table}" WHERE "{column}" ~ :p'),
                              {"p": pattern}).scalars().all()
        for value in rows:
            if value in found:
                found[value].append(f"{table}.{column}")
    return found


# Tables that record what happened (audit trails, request timings): they name a case id as history and use no file,
# so they keep their rows and do not hold a deleted case's folder.
HISTORY_TABLES = frozenset({"activity_events", "financial_audit_events", "manual_changes", "system_logs",
                            "request_speed_hourly", "request_speed_slow", "request_speed_pages"})
# The evidence engine's job rows of a deleted case are removed through the engine's own delete (its file and its
# row; evidence_engine_client.delete_file / delete_job), the call purge_file uses for one file.
ENGINE_TABLE = "jobs"


def _blocking(refs: list[str]) -> list[str]:
    return sorted({r for r in refs if r.split(".")[0] not in HISTORY_TABLES})


def _engine_jobs(db, case_id: str) -> list[tuple[str, bool]]:
    from sqlalchemy import text
    return [(str(i), p is not None) for i, p in db.execute(
        text("SELECT id, file_path FROM jobs WHERE case_id::text = :c ORDER BY id"), {"c": case_id}).all()]


def _engine_remove(case_id: str, job_id: str, has_file: bool):
    """The engine's own delete: its file and job row (or the row alone when it has no file). Already gone is fine."""
    if has_file:
        _engine_request("DELETE", f"/cases/{case_id}/files/{job_id}", missing_ok=True)
    else:
        _engine_request("DELETE", f"/jobs/{job_id}", missing_ok=True)


def purge_deleted_case_folders(db, roots, *, apply: bool = False, user_email: str | None = None,
                               engine_remove=None) -> dict:
    """The folders left on disk by cases whose rows are gone (deleted before Deleted items existed).

    Only a folder named as a case id, directly under one of ``roots``, with no row in ``cases`` (a case waiting in
    Deleted items has its row and is kept). Every row in the database that names the case id or points a path inside
    its folder is counted: history rows (HISTORY_TABLES) stay and do not hold it; the evidence engine's own job rows
    of that case are removed first through the engine's delete; any other row keeps the folder (listed with why). A
    root that is missing or empty is refused (an unmounted disk). Dry run unless ``apply``; returns what is (or was)
    removed, with file counts and bytes, and what is kept and why."""
    import re
    import shutil
    from pathlib import Path
    from sqlalchemy import text
    out = dict(applied=apply, roots=[], remove=[], kept=[], engine_jobs_removed=0, files_removed=0, bytes_freed=0)
    candidates = []
    for root in roots:
        root = Path(root)
        if not root.is_dir() or not any(root.iterdir()):
            raise RuntimeError(f"Refused: {root} is missing or empty (is the disk mounted?). Nothing was removed.")
        out["roots"].append(str(root))
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.is_symlink() and re.match(_UUID_NAME, child.name):
                candidates.append(child)
    ids = sorted({c.name for c in candidates})
    live = set(db.execute(text("SELECT id::text FROM cases WHERE id::text = ANY(:ids)"), {"ids": ids}).scalars())
    orphan_ids = [i for i in ids if i not in live]
    refs = _references(db, orphan_ids)
    engine_jobs = {i: (_engine_jobs(db, i) if any(r.startswith(ENGINE_TABLE + ".") for r in refs.get(i, [])) else [])
                   for i in orphan_ids}
    db.rollback()
    held = {i: [r for r in _blocking(refs.get(i, [])) if not r.startswith(ENGINE_TABLE + ".")] for i in orphan_ids}
    if apply:
        for case_id in orphan_ids:
            if held[case_id]:
                continue
            for job_id, has_file in engine_jobs[case_id]:
                (engine_remove or _engine_remove)(case_id, job_id, has_file)
                out["engine_jobs_removed"] += 1
        refs = _references(db, orphan_ids)  # read again: what the engine removal left
        db.rollback()
        held = {i: _blocking(refs.get(i, [])) for i in orphan_ids}
    for folder in candidates:
        if folder.name in live:
            continue
        files, size = _dir_size(folder)
        entry = dict(path=str(folder), case_id=folder.name, files=files, bytes=size,
                     engine_jobs=len(engine_jobs.get(folder.name) or []),
                     history_rows_kept_in=sorted({r.split(".")[0] for r in refs.get(folder.name, [])
                                                  if r.split(".")[0] in HISTORY_TABLES}))
        if held.get(folder.name):
            out["kept"].append(dict(entry, why="still referenced by " + ", ".join(held[folder.name])))
            continue
        out["remove"].append(entry)
    if apply:
        for entry in out["remove"]:
            folder = Path(entry["path"])
            if str(folder.parent) not in out["roots"]:
                raise RuntimeError(f"Refused: {folder} is not directly under a named root")
            files, size = _dir_size(folder)  # what is left after the engine removed its own files
            shutil.rmtree(folder)
            out["files_removed"] += files
            out["bytes_freed"] += size
        from services import activity_trail
        activity_trail.record("deleted_case_folders_purged", db=db, system=True, details=dict(
            by=user_email, roots=out["roots"], folders=[dict(case_id=e["case_id"], path=e["path"], files=e["files"],
                                                             bytes=e["bytes"]) for e in out["remove"]],
            kept=out["kept"], engine_jobs_removed=out["engine_jobs_removed"], files_removed=out["files_removed"],
            bytes_freed=out["bytes_freed"]))
        db.commit()
    return out


def _main(argv=None):
    """python -m services.casebin_purge deleted-case-folders [--apply] [--by EMAIL] ROOT [ROOT ...]"""
    import argparse
    import json
    parser = argparse.ArgumentParser(prog="python -m services.casebin_purge")
    sub = parser.add_subparsers(dest="command", required=True)
    folders = sub.add_parser("deleted-case-folders", help="folders left on disk by deleted cases (dry run by default)")
    folders.add_argument("roots", nargs="+")
    folders.add_argument("--apply", action="store_true")
    folders.add_argument("--by", default=None)
    args = parser.parse_args(argv)
    from postgres.session import _get_background_session_local
    with _get_background_session_local()() as db:
        result = purge_deleted_case_folders(db, args.roots, apply=args.apply, user_email=args.by)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    _main()
