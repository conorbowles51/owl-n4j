"""The sweep that keeps the embeddings of every case in step with its sources (lx-embedall E).

Each pass visits every case. For each area it reads a cheap signature of the source; when it matches the signature saved
at the last complete sync, the area is skipped. When it differs the area is reconciled (new and changed items embedded,
items gone from the source removed) and the signature is saved only if nothing was refused, so a refused run is retried.
A correction, a new statement, a new extraction, an edit or a delete changes a signature, so each reaches the index within
one pass. The backfill of existing cases is the same step: a case with no saved signature is simply all new.
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any, Callable

from sqlalchemy import text

from services.embed_all import phone as phone_area
from services.embed_all import sources
from services.embed_all.core import reconcile
from services.embed_all.store import PgChromaStore

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 120
FIRST_DELAY_SECONDS = 90
PASS_SECONDS = 900          # one pass stops starting new work after this long; the next pass carries on
PHONE_FILES_PER_STEP = 200
ENTITIES = "entities"  # graph entities (every kind, phone nodes included): the entity vectors of services.entity_vectors
AREAS_ALL = tuple(sources.AREAS) + (phone_area.AREA, ENTITIES)
ENTITY_PERIOD_SECONDS = 3600  # the graph is read once an hour per case: it has no cheap change signature
SWITCH = "LOUPE_EMBED_ALL"  # "0" turns the sweep off


def default_embed() -> Callable[[list[str]], list[list[float]]]:
    from services.embedding_service import EmbeddingService
    svc = EmbeddingService()

    def embed(texts: list[str]) -> list[list[float]]:
        out = svc.generate_embeddings_batch(texts, batch_size=64)
        if len(out) != len(texts):
            raise RuntimeError("the embedding service returned %d vectors for %d texts" % (len(out), len(texts)))
        return out
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
              deadline: float | None = None) -> list[dict[str, Any]]:
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
            if area == ENTITIES:
                sig = "hour:%d" % (int(time.time()) // ENTITY_PERIOD_SECONDS)
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
                res = phone_area.sync(engine, case_id, chunks, embed, max_files=PHONE_FILES_PER_STEP)
                complete = res["stopped"] is None and res["pending"] == 0 and res["files"] < PHONE_FILES_PER_STEP
            else:
                with engine.connect() as c:
                    items = list(sources.READERS[area](c, case_id))
                res = reconcile(case_id, area, items, store, embed)
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


def run_pass(engine=None, *, embed=None, budget_seconds: float = PASS_SECONDS) -> dict[str, Any]:
    if engine is None:
        from postgres.session import _get_engine
        engine = _get_engine()
    deadline = time.time() + budget_seconds
    summary = {"cases": 0, "areas_read": 0, "embedded": 0, "removed": 0, "stopped": None}
    store = PgChromaStore(engine)
    for case_id in case_order(engine):
        if time.time() > deadline:
            break
        for r in sync_case(engine, case_id, store=store, embed=embed, deadline=deadline):
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
    while True:
        try:
            res = await asyncio.to_thread(once)
            if res.get("embedded") or res.get("removed") or res.get("stopped"):
                logger.info("embed_all pass: %s", res)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.warning("embed_all pass failed: %s", err)
        await asyncio.sleep(INTERVAL_SECONDS)
