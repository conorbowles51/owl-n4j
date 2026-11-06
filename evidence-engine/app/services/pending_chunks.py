"""Document chunks waiting for their vector while the embedding service refuses.

Chroma cannot hold a chunk without a vector, so a refused chunk is kept here with its text and Chroma metadata and the
ingestion carries on. A row is ``draft`` until the revision is published, as a staged Chroma chunk is. Publication turns
the revision's rows ``active`` and deletes the rows of the file's other revisions, so a superseded revision is never
embedded. The sweep embeds ``active`` rows only and writes them to Chroma as active: the state publication gave them.
A file in the case bin waits (its chunks would otherwise reappear in search); purging it cascades here.

Each sweep starts with one single-try call for one chunk. When that is refused the sweep ends, so an outage costs one
refused request per sweep.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Sequence

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.dependencies import async_session
from app.models.job import PendingChunkVector
from app.services.chroma_client import get_or_create_collection, upsert_embeddings
from app.services.ai_budget import limit_reached
from app.services.cost_tracking import ingestion_cost_context
from app.services.embedding_refusal import is_embedding_refusal
from app.services.openai_client import embed_texts
from app.utils.text_sanitize import sanitize_json, sanitize_text

logger = logging.getLogger(__name__)

DRAFT = "draft"
ACTIVE = "active"
REVISIONS_PER_SWEEP = 20
SWEEP_LOCK_KEY = 7310403  # next to meaning_search.BACKFILL_LOCK_KEY

_DUE_REVISIONS = text("""
    SELECT p.case_id, p.document_id, p.revision_id, count(*) AS chunks
    FROM pending_chunk_vectors p LEFT JOIN evidence_files f ON f.id = p.evidence_file_id
    WHERE p.publication_state = 'active' AND (p.evidence_file_id IS NULL OR f.deleted_at IS NULL)
    GROUP BY p.case_id, p.document_id, p.revision_id
    ORDER BY min(p.created_at), p.document_id
    LIMIT :limit
""")
_STILL_DUE = text("""
    SELECT p.chunk_id, p.content, p.chunk_metadata
    FROM pending_chunk_vectors p LEFT JOIN evidence_files f ON f.id = p.evidence_file_id
    WHERE p.chunk_id = ANY(:ids) AND p.publication_state = 'active'
      AND (p.evidence_file_id IS NULL OR f.deleted_at IS NULL)
    ORDER BY p.chunk_index
    FOR UPDATE OF p
""")


def _as_uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


async def store_pending_chunks(
    *,
    case_id: str,
    document_id: str,
    revision_id: str,
    job_id: str,
    ids: Sequence[str],
    texts: Sequence[str],
    metadatas: Sequence[dict[str, Any]],
    reason: str,
) -> int:
    """Keep refused chunks. A revision id is a content hash, so a repeat of a stored chunk changes nothing it holds
    and never takes back the state publication gave it."""
    if not ids:
        return 0
    async with async_session() as db:
        candidate = _as_uuid(document_id)
        evidence_file_id = None
        if candidate is not None:
            evidence_file_id = (await db.execute(
                text("SELECT id FROM evidence_files WHERE id = :id"), {"id": candidate})).scalar()
        rows = [
            {
                "chunk_id": chunk_id,
                "case_id": str(case_id),
                "document_id": document_id,
                "evidence_file_id": evidence_file_id,
                "revision_id": revision_id,
                "job_id": job_id,
                "chunk_index": int(metadata["chunk_index"]),
                "content": sanitize_text(content),
                "chunk_metadata": sanitize_json({k: v for k, v in metadata.items() if k != "ingestion_state"}),
                "publication_state": DRAFT,
                "reason": reason[:500],
            }
            for chunk_id, content, metadata in zip(ids, texts, metadatas)
        ]
        statement = insert(PendingChunkVector)
        for start in range(0, len(rows), 500):
            await db.execute(
                statement.on_conflict_do_update(
                    index_elements=[PendingChunkVector.chunk_id],
                    set_={"job_id": statement.excluded.job_id, "reason": statement.excluded.reason,
                          "updated_at": func.now()},
                ),
                rows[start:start + 500],
            )
        await db.commit()
    logger.warning("chunks-pending-vector document_id=%s revision_id=%s chunks=%d reason=%s",
                   document_id, revision_id, len(rows), reason[:200])
    return len(rows)


async def publish_pending_revision(*, document_id: str, revision_id: str) -> int:
    """This revision's waiting chunks become due for the sweep; the file's other revisions are dropped. Returns how
    many of this revision's chunks wait. Safe to repeat: a publication retry reads the same answer."""
    async with async_session() as db:
        await db.execute(delete(PendingChunkVector).where(
            PendingChunkVector.document_id == document_id,
            PendingChunkVector.revision_id != revision_id,
        ))
        await db.execute(update(PendingChunkVector).where(
            PendingChunkVector.document_id == document_id,
            PendingChunkVector.revision_id == revision_id,
        ).values(publication_state=ACTIVE, updated_at=func.now()))
        count = (await db.execute(select(func.count()).select_from(PendingChunkVector).where(
            PendingChunkVector.document_id == document_id,
            PendingChunkVector.revision_id == revision_id,
        ))).scalar_one()
        await db.commit()
    return int(count)


async def drop_embedded_chunks(chunk_ids: Sequence[str]) -> None:
    """A repeat embedded these after all: their vectors are in Chroma, so nothing waits for them."""
    if chunk_ids:
        async with async_session() as db:
            await db.execute(delete(PendingChunkVector).where(PendingChunkVector.chunk_id.in_(list(chunk_ids))))
            await db.commit()


async def request_gap_backfill() -> None:
    """Have the backend's gap backfill run at its next successful embedding call, even when the backend never saw
    this outage (entity vectors are embedded there). A report only: it never fails the ingestion."""
    try:
        async with async_session() as db:
            await db.execute(text("""
                INSERT INTO service_health_states (service, status, backfill_pending, updated_at)
                VALUES ('meaning_search', 'up', true, now())
                ON CONFLICT (service) DO UPDATE SET backfill_pending = true, updated_at = now()
            """))
            await db.commit()
    except Exception:
        logger.exception("Could not request the gap backfill")


async def _revision_chunk_ids(document_id: str, revision_id: str) -> list[tuple[str, str]]:
    async with async_session() as db:
        rows = (await db.execute(
            select(PendingChunkVector.chunk_id, PendingChunkVector.content)
            .where(PendingChunkVector.document_id == document_id,
                   PendingChunkVector.revision_id == revision_id,
                   PendingChunkVector.publication_state == ACTIVE)
            .order_by(PendingChunkVector.chunk_index)
        )).all()
    return [(row[0], row[1]) for row in rows]


async def _write_vectors(vectors: dict[str, list[float]]) -> int:
    """Write the vectors of the chunks still due. The row locks hold back a publication of this file until the
    write is done, so a revision superseded while its vectors were being made is retired by that publication."""
    async with async_session() as db:
        due = (await db.execute(_STILL_DUE, {"ids": list(vectors)})).all()
        if due:
            ids = [row[0] for row in due]
            await asyncio.to_thread(
                lambda: upsert_embeddings(
                    collection=get_or_create_collection("chunks"),
                    ids=ids,
                    embeddings=[vectors[chunk_id] for chunk_id in ids],
                    documents=[row[1] for row in due],
                    metadatas=[{**row[2], "ingestion_state": ACTIVE} for row in due],
                )
            )
            await db.execute(delete(PendingChunkVector).where(PendingChunkVector.chunk_id.in_(ids)))
        await db.commit()
    return len(due)


async def embed_pending_chunks(_ctx: dict | None = None) -> dict[str, Any]:
    """One sweep: one probe, then the waiting revisions, oldest first, until the service refuses."""
    summary: dict[str, Any] = {"revisions": 0, "embedded": 0, "refused": None}
    # Every general worker carries this cron; held to the end of the sweep, released by a crash.
    async with async_session() as lock_db:
        if not (await lock_db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SWEEP_LOCK_KEY})).scalar():
            return summary
        async with async_session() as db:
            revisions = (await db.execute(_DUE_REVISIONS, {"limit": REVISIONS_PER_SWEEP})).all()
        if revisions:
            await _sweep(revisions, summary)
    return summary


async def _sweep(revisions: Sequence[Any], summary: dict[str, Any]) -> None:
    probed: dict[str, list[float]] = {}
    for position, revision in enumerate(revisions):
        chunks = await _revision_chunk_ids(revision.document_id, revision.revision_id)
        if not chunks:
            continue
        if await limit_reached(revision.case_id):
            continue  # stays pending: the next sweep tries again
        async with ingestion_cost_context(
            case_id=revision.case_id,
            source_evidence_file_id=str(_as_uuid(revision.document_id) or "") or None,
            description="Search vectors for chunks kept during an embedding outage",
            extra_metadata={"pipeline_scope": "pending_chunks"},
        ):
            try:
                if position == 0:
                    chunk_id, content = chunks[0]
                    probed[chunk_id] = (await embed_texts([content], max_retries=0))[0]
                step = max(1, settings.openai_embedding_batch_size)
                for start in range(0, len(chunks), step):
                    window = chunks[start:start + step]
                    vectors = {cid: probed[cid] for cid, _ in window if cid in probed}
                    missing = [(cid, body) for cid, body in window if cid not in vectors]
                    if missing:
                        made = await embed_texts([body for _, body in missing], max_retries=0)
                        vectors.update({cid: vector for (cid, _), vector in zip(missing, made)})
                    summary["embedded"] += await _write_vectors(vectors)
            except Exception as exc:
                if not is_embedding_refusal(exc):
                    raise
                summary["refused"] = str(exc)[:300]
                logger.warning("pending-chunk-sweep refused after %d chunk(s): %s",
                               summary["embedded"], summary["refused"])
                return
        summary["revisions"] += 1
    logger.info("pending-chunk-sweep embedded=%d revisions=%d", summary["embedded"], summary["revisions"])
