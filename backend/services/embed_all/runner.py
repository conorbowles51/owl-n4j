"""The sweep that keeps the embeddings of every case in step with its sources (lx-embedall E).

Each pass visits every case. For each area it reads a cheap signature of the source; when it matches the signature saved
at the last complete sync, the area is skipped. When it differs the area is reconciled (new and changed items embedded,
items gone from the source removed) and the signature is saved only if nothing was refused, so a refused run is retried.
A correction, a new statement, a new extraction, an edit or a delete changes a signature, so each reaches the index within
one pass. The backfill of existing cases is the same step: a case with no saved signature is simply all new.
"""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

from services.embed_all import phone as phone_area
from services.embed_all import sources
from services.embed_all.core import reconcile
from services.embed_all.store import PgChromaStore

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 120
BUSY_INTERVAL_SECONDS = 10  # a pass that embedded something is followed at once by the next: the backfill of a big case
FIRST_DELAY_SECONDS = 90
PASS_SECONDS = 900          # one pass stops starting new work after this long; the next pass carries on
PHONE_FILES_PER_STEP = 200
ENTITIES = "entities"  # graph entities (every kind, phone nodes included): the entity vectors of services.entity_vectors
AREAS_ALL = tuple(sources.AREAS) + (phone_area.AREA, ENTITIES)
ENTITY_PERIOD_SECONDS = 3600  # the graph is read once an hour per case: it has no cheap change signature
SWITCH = "LOUPE_EMBED_ALL"  # "0" turns the sweep off
LOCK_PATH = os.path.join(tempfile.gettempdir(), "loupe-embed-all.lock")


def release_held() -> bool:
    """True while a release has paused work to replace services. The host's release script (named in
    ``deploy/logs/.release-work-hook``) keeps ``deploy-hold.flag`` beside itself for that time. A release's Chroma step
    compares the chunk count before and after it relinks records, so a write by the sweep at that moment fails the
    release (live, 17 Nov 05:58 UTC); the sweep writes nothing while the flag exists."""
    try:
        hook = (Path(__file__).resolve().parents[3] / "deploy" / "logs" / ".release-work-hook").read_text().strip()
        return (Path(hook).parent / "deploy-hold.flag").exists()
    except OSError:
        return False


def _take_host_lock():
    try:
        handle = open(LOCK_PATH, "a")
    except OSError:
        return None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _invalid_input(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 400 or "maximum input length" in str(exc).lower() or \
        "invalid 'input" in str(exc).lower()


def default_embed() -> Callable[[list[str]], list[list[float] | None]]:
    """Vectors for the texts, in order. A text the service refuses as invalid input comes back as ``None``; any other
    failure (no credits, rate limit, outage) raises, so the run stops and tries again later."""
    from services.embed_all.core import clamp
    from services.embedding_service import EmbeddingService
    svc = EmbeddingService()

    def embed(texts: list[str]) -> list[list[float] | None]:
        texts = [clamp(t) for t in texts]
        out = svc.generate_embeddings_batch(texts, batch_size=64)
        if len(out) == len(texts):
            return out
        # the batch call hides which text failed: ask one by one, so one bad text does not hold up the rest
        single: list[list[float] | None] = []
        for t in texts:
            try:
                single.append(svc.generate_embedding(t))
            except Exception as exc:
                if not _invalid_input(exc):
                    raise
                single.append(None)
        return single
    return embed


def _saved(conn, case_id, area):
    return conn.execute(text("SELECT signature FROM embed_area_state WHERE case_id = :c AND area = :a"),
                        {"c": case_id, "a": area}).scalar()


def _save(engine, case_id, area, sig, counts):
    import json
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO embed_area_state (case_id, area, signature, synced_at, last_counts) VALUES (:c, :a, :s, now(), "
            "CAST(:j AS jsonb)) ON CONFLICT (case_id, area) DO UPDATE SET signature = EXCLUDED.signature, "
            "synced_at = now(), last_counts = EXCLUDED.last_counts"), {"c": case_id, "a": area, "s": sig, "j": json.dumps(counts)})


def sync_case(engine, case_id: str, *, store=None, chunks=None, embed=None, areas=AREAS_ALL, force=False,
              deadline: float | None = None, should_stop: Callable[[], bool] | None = None) -> list[dict[str, Any]]:
    """Sync the given areas of one case. Returns one counts dict per area that was read."""
    from postgres.models.cost_record import CostJobType
    from services.ai_costs_service import ai_cost_context
    import uuid
    embed = embed or default_embed()
    store = store or PgChromaStore(engine)
    results = []
    cuuid = uuid.UUID(str(case_id))
    for area in areas:
        if deadline is not None and time.time() > deadline:
            results.append({"area": area, "skipped": "pass time used"})
            continue
        with engine.connect() as c:
            if area == ENTITIES or area in sources.GRAPH_AREAS:
                sig = "%s|hour:%d" % (sources.SOURCES_VERSION, int(time.time()) // ENTITY_PERIOD_SECONDS)
            elif area == phone_area.AREA:
                sig = phone_area.signature(c, case_id)
            else:
                sig = sources.signature(c, case_id, area)
            if not force and _saved(c, case_id, area) == sig:
                continue
        with ai_cost_context(job_type=CostJobType.INGESTION, case_id=cuuid, description="Case search index (%s)" % area):
            if area == ENTITIES:
                from services import entity_vectors
                try:
                    r = entity_vectors.backfill_case(case_id)
                except Exception as exc:  # graph unreachable or the service refused: retried next pass
                    r = {"embedded": 0, "stopped": str(exc)[:300]}
                res = {"area": area, "embedded": r.get("embedded", 0), "stopped": r.get("stopped")}
                complete = not res["stopped"]
            elif area == phone_area.AREA:
                if chunks is None:
                    from services.vector_db_service import get_vector_db_service
                    chunks = get_vector_db_service().chunk_collection
                res = phone_area.sync(engine, case_id, chunks, embed, max_files=PHONE_FILES_PER_STEP, should_stop=should_stop)
                complete = res["stopped"] is None and res["pending"] == 0 and res["files"] < PHONE_FILES_PER_STEP
            else:
                with engine.connect() as c:
                    items = list(sources.READERS[area](c, case_id))
                res = reconcile(case_id, area, items, store, embed, should_stop=should_stop)
                complete = res["stopped"] is None
        results.append(res)
        if complete:
            _save(engine, case_id, area, sig, res)
        if res.get("stopped"):
            break  # a refusal now is a refusal for every area: try again next pass
    return results


def case_order(engine) -> list[str]:
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT c.id::text FROM cases c LEFT JOIN (SELECT f.case_id, sum(t.character_count) AS ch FROM evidence_files f "
            "JOIN evidence_document_texts t ON t.evidence_file_id = f.id WHERE f.source_type = 'phone_text' GROUP BY 1) p "
            "ON p.case_id = c.id WHERE c.deleted_at IS NULL ORDER BY coalesce(p.ch, 0), c.id")).fetchall()
    return [r[0] for r in rows]


def run_pass(engine=None, *, embed=None, budget_seconds: float = PASS_SECONDS,
             should_stop: Callable[[], bool] | None = release_held) -> dict[str, Any]:
    if engine is None:
        from postgres.session import _get_engine
        engine = _get_engine()
    deadline = time.time() + budget_seconds
    summary = {"cases": 0, "areas_read": 0, "embedded": 0, "removed": 0, "stopped": None}
    store = PgChromaStore(engine)
    for case_id in case_order(engine):
        if time.time() > deadline:
            break
        for r in sync_case(engine, case_id, store=store, embed=embed, deadline=deadline, should_stop=should_stop):
            if r.get("skipped"):
                continue
            summary["areas_read"] += 1
            summary["embedded"] += r.get("embedded", 0) + r.get("updated", 0) + r.get("windows", 0)
            summary["removed"] += r.get("removed", 0) + r.get("removed_files", 0)
            summary["stopped"] = summary["stopped"] or r.get("stopped")
        summary["cases"] += 1
        if summary["stopped"]:
            break
    return summary


async def run_forever() -> None:
    """Lifespan loop of the backend."""
    if os.environ.get(SWITCH, "1") == "0":
        return
    await asyncio.sleep(FIRST_DELAY_SECONDS)

    def once():
        try:
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 15)
        except Exception:
            pass
        return run_pass()
    lock = None
    while True:
        wait = INTERVAL_SECONDS
        try:
            if lock is None:
                lock = await asyncio.to_thread(_take_host_lock)  # one backend on the host sweeps, whatever overlap
            if lock is None or await asyncio.to_thread(release_held):
                await asyncio.sleep(wait)
                continue
            res = await asyncio.to_thread(once)
            if res.get("embedded") or res.get("removed") or res.get("stopped"):
                logger.info("embed_all pass: %s", res)
            if res.get("embedded") and not res.get("stopped"):
                wait = BUSY_INTERVAL_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.warning("embed_all pass failed: %s", err)
        await asyncio.sleep(wait)
