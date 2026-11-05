"""Kept chunks reach search through publication and the sweep (needs PostgreSQL: LOUPE_TEST_ENGINE_PG_URL)."""
from __future__ import annotations

import os
import uuid

import httpx
import openai
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.pipeline import chunk_embed
from app.services import pending_chunks

URL = os.environ.get("LOUPE_TEST_ENGINE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires LOUPE_TEST_ENGINE_PG_URL (a scratch PostgreSQL)")

DDL = [
    "DROP TABLE IF EXISTS pending_chunk_vectors",
    "DROP TABLE IF EXISTS evidence_files",
    "CREATE TABLE evidence_files (id uuid PRIMARY KEY, deleted_at timestamptz)",
    """CREATE TABLE pending_chunk_vectors (
        chunk_id text PRIMARY KEY, case_id text NOT NULL, document_id text NOT NULL,
        evidence_file_id uuid REFERENCES evidence_files(id) ON DELETE CASCADE, revision_id text NOT NULL,
        job_id text NOT NULL, chunk_index integer NOT NULL, content text NOT NULL, chunk_metadata jsonb NOT NULL,
        publication_state varchar(16) NOT NULL DEFAULT 'draft', reason text,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
]


class Chroma:
    """The chunks collection, enough of it."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        for chunk_id, vector, body, metadata in zip(ids, embeddings, documents, metadatas):
            self.rows[chunk_id] = {"vector": vector, "document": body, "metadata": metadata}

    def get(self, where=None, include=None, ids=None):
        conditions = where["$and"] if where else []
        hits = [(cid, row) for cid, row in self.rows.items()
                if all(row["metadata"].get(k) == v for c in conditions for k, v in c.items())]
        return {"ids": [cid for cid, _ in hits], "metadatas": [row["metadata"] for _, row in hits]}

    def update(self, ids, metadatas) -> None:
        for chunk_id, metadata in zip(ids, metadatas):
            self.rows[chunk_id]["metadata"] = metadata


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(URL)
    async with engine.begin() as conn:
        for statement in DDL:
            await conn.execute(text(statement))
    chroma = Chroma()
    monkeypatch.setattr(pending_chunks, "async_session", async_sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(pending_chunks, "get_or_create_collection", lambda _name: chroma)
    monkeypatch.setattr(chunk_embed, "get_or_create_collection", lambda _name: chroma)
    yield chroma, engine
    await engine.dispose()


async def _file(engine) -> str:
    file_id = str(uuid.uuid4())
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO evidence_files (id) VALUES (:id)"), {"id": file_id})
    return file_id


async def _keep(file_id: str, revision: str, bodies: list[str]) -> list[str]:
    ids = [f"{file_id}:{revision}:chunk:{i}" for i in range(len(bodies))]
    await pending_chunks.store_pending_chunks(
        case_id="case-1", document_id=file_id, revision_id=revision, job_id="job-1", ids=ids, texts=bodies,
        metadatas=[{"case_id": "case-1", "evidence_file_id": file_id, "revision_id": revision, "chunk_index": i,
                    "ingestion_state": "draft"} for i in range(len(bodies))],
        reason="no credits",
    )
    return ids


async def _publish(file_id: str, revision: str, name: str = "a.txt") -> chunk_embed.ChunkActivationResult:
    return await chunk_embed.activate_chunk_revision(
        case_id="case-1", evidence_file_id=file_id, revision_id=revision, file_name=name,
    )


async def _rows(engine) -> list[tuple]:
    async with engine.connect() as conn:
        return [tuple(row) for row in await conn.execute(text(
            "SELECT revision_id, publication_state FROM pending_chunk_vectors ORDER BY chunk_id"))]


def _embed(calls: list):
    async def embed(texts: list[str], *, max_retries: int | None = None) -> list[list[float]]:
        calls.append((list(texts), max_retries))
        return [[0.5, 0.5] for _ in texts]
    return embed


def _refuse(calls: list):
    async def embed(texts: list[str], *, max_retries: int | None = None) -> list[list[float]]:
        calls.append((list(texts), max_retries))
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))
        raise openai.RateLimitError("You have no credits remaining", response=response, body=None)
    return embed


@pytest.mark.asyncio
async def test_pending_chunks_reach_active_after_the_sweep(world, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma, engine = world
    file_id = await _file(engine)
    ids = await _keep(file_id, "rev-1", ["first", "second", "third"])
    calls: list = []
    monkeypatch.setattr(pending_chunks, "embed_texts", _embed(calls))

    assert (await pending_chunks.embed_pending_chunks())["embedded"] == 0  # not published: no call made
    assert calls == []

    result = await _publish(file_id, "rev-1")
    assert (result.activated_count, result.pending_count) == (0, 3)

    summary = await pending_chunks.embed_pending_chunks()

    assert summary == {"revisions": 1, "embedded": 3, "refused": None}
    assert sorted(chroma.rows) == sorted(ids)
    assert {row["metadata"]["ingestion_state"] for row in chroma.rows.values()} == {"active"}
    assert chroma.rows[ids[0]]["document"] == "first"
    assert await _rows(engine) == []


@pytest.mark.asyncio
async def test_a_refusing_service_gets_one_single_try_probe_per_sweep(world, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma, engine = world
    for name in ("a", "b", "c"):
        file_id = await _file(engine)
        await _keep(file_id, "rev-1", [name + "1", name + "2"])
        await _publish(file_id, "rev-1")
    calls: list = []
    monkeypatch.setattr(pending_chunks, "embed_texts", _refuse(calls))

    summary = await pending_chunks.embed_pending_chunks()

    assert len(calls) == 1
    assert len(calls[0][0]) == 1 and calls[0][1] == 0
    assert "no credits" in summary["refused"]
    assert chroma.rows == {}
    assert len(await _rows(engine)) == 6


@pytest.mark.asyncio
async def test_a_superseded_revision_is_never_activated(world, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma, engine = world
    file_id = await _file(engine)
    await _keep(file_id, "old", ["old words"])
    await _publish(file_id, "old")
    new_ids = await _keep(file_id, "new", ["new words"])
    await _publish(file_id, "new")
    monkeypatch.setattr(pending_chunks, "embed_texts", _embed([]))

    await pending_chunks.embed_pending_chunks()

    assert list(chroma.rows) == new_ids
    assert await _rows(engine) == []


@pytest.mark.asyncio
async def test_publication_retires_older_chunks_while_the_new_revision_waits(
    world, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma, engine = world
    file_id = await _file(engine)
    chroma.rows["old"] = {"vector": [0.1], "document": "old words", "metadata": {
        "case_id": "case-1", "evidence_file_id": file_id, "revision_id": "old", "ingestion_state": "active"}}
    await _keep(file_id, "new", ["new words"])

    await _publish(file_id, "new")

    assert chroma.rows["old"]["metadata"]["ingestion_state"] == "inactive"
    assert await _rows(engine) == [("new", "active")]


@pytest.mark.asyncio
async def test_a_repeat_does_not_take_back_the_published_state(world, monkeypatch: pytest.MonkeyPatch) -> None:
    _chroma, engine = world
    file_id = await _file(engine)
    await _keep(file_id, "rev-1", ["words"])
    await _publish(file_id, "rev-1")

    await _keep(file_id, "rev-1", ["words"])

    assert await _rows(engine) == [("rev-1", "active")]


@pytest.mark.asyncio
async def test_a_binned_file_waits_and_a_purged_one_is_gone(world, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma, engine = world
    file_id = await _file(engine)
    await _keep(file_id, "rev-1", ["words"])
    await _publish(file_id, "rev-1")
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE evidence_files SET deleted_at = now() WHERE id = :id"), {"id": file_id})
    calls: list = []
    monkeypatch.setattr(pending_chunks, "embed_texts", _embed(calls))

    await pending_chunks.embed_pending_chunks()

    assert calls == [] and chroma.rows == {}
    assert await _rows(engine) == [("rev-1", "active")]
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM evidence_files WHERE id = :id"), {"id": file_id})
    assert await _rows(engine) == []


@pytest.mark.asyncio
async def test_a_repeat_that_embedded_leaves_nothing_waiting(world, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma, engine = world
    file_id = await _file(engine)
    [chunk_id] = await _keep(file_id, "rev-1", ["words"])  # the failed first run kept it
    chroma.rows[chunk_id] = {"vector": [0.5], "document": "words", "metadata": {  # the repeat staged it
        "case_id": "case-1", "evidence_file_id": file_id, "revision_id": "rev-1", "ingestion_state": "draft"}}
    calls: list = []
    monkeypatch.setattr(pending_chunks, "embed_texts", _embed(calls))

    await _publish(file_id, "rev-1")
    await pending_chunks.embed_pending_chunks()

    assert await _rows(engine) == [] and calls == []
    assert chroma.rows[chunk_id]["metadata"]["ingestion_state"] == "active"


@pytest.mark.asyncio
async def test_a_job_with_no_evidence_file_keeps_its_chunks(world, monkeypatch: pytest.MonkeyPatch) -> None:
    chroma, engine = world
    document_id = str(uuid.uuid4())  # the job id stands in when the job has no source evidence file
    await _keep(document_id, "rev-1", ["words"])
    await _publish(document_id, "rev-1")
    monkeypatch.setattr(pending_chunks, "embed_texts", _embed([]))

    assert (await pending_chunks.embed_pending_chunks())["embedded"] == 1
    assert len(chroma.rows) == 1


@pytest.mark.asyncio
async def test_a_chunk_superseded_while_its_vector_was_being_made_is_not_written(
    world, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chroma, engine = world
    file_id = await _file(engine)
    await _keep(file_id, "old", ["old words"])
    await _publish(file_id, "old")

    async def embed_then_supersede(texts: list[str], *, max_retries: int | None = None) -> list[list[float]]:
        await _keep(file_id, "new", ["new words"])
        await pending_chunks.publish_pending_revision(document_id=file_id, revision_id="new")
        return [[0.5] for _ in texts]

    monkeypatch.setattr(pending_chunks, "embed_texts", embed_then_supersede)

    await pending_chunks.embed_pending_chunks()

    assert chroma.rows == {}
    assert await _rows(engine) == [("new", "active")]
