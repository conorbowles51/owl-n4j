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
    out = {"cases": [], "files": [], "skipped": None, "cutoff": cutoff.isoformat()}
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


def _engine_delete(case_id, job_id):
    from services import evidence_engine_client
    asyncio.run(evidence_engine_client.delete_file(case_id, job_id))


async def run_purge_forever():
    """Lifespan task: purge once a few minutes after start, then every PURGE_EVERY_SECONDS."""
    from postgres.session import _get_background_session_local
    await asyncio.sleep(FIRST_DELAY_SECONDS)
    while True:
        try:
            result = await asyncio.to_thread(purge_due, _get_background_session_local())
            if result["cases"] or result["files"] or result["skipped"]:
                logger.warning("Deleted items purge: %d case(s), %d file(s)%s", len(result["cases"]),
                               len(result["files"]), "; " + result["skipped"] if result["skipped"] else "")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Deleted items purge failed; it will run again")
        await asyncio.sleep(PURGE_EVERY_SECONDS)
