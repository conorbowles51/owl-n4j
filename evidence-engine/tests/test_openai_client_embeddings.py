from types import SimpleNamespace

import pytest

from app.services import openai_client


class FakeEmbeddingItem:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class FakeEmbeddingResponse:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.data = [FakeEmbeddingItem(embedding) for embedding in embeddings]
        self.usage = SimpleNamespace(total_tokens=1)


class OversizedEmbeddingRequest(Exception):
    code = "request_headers_too_large"


@pytest.fixture(autouse=True)
def no_cost_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_record_openai_cost(**_: object) -> None:
        return None

    monkeypatch.setattr(openai_client, "record_openai_cost", fake_record_openai_cost)


def _fake_client(create):
    return SimpleNamespace(embeddings=SimpleNamespace(create=create))


@pytest.mark.asyncio
async def test_embed_texts_batches_by_total_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def create(*, model: str, input: list[str]):
        calls.append(input)
        return FakeEmbeddingResponse([[float(len(calls)), float(i)] for i, _ in enumerate(input)])

    monkeypatch.setattr(openai_client.settings, "openai_embedding_batch_size", 100)
    monkeypatch.setattr(openai_client.settings, "openai_embedding_max_batch_chars", 6000)
    monkeypatch.setattr(openai_client, "get_openai_client", lambda: _fake_client(create))

    await openai_client.embed_texts(
        ["a" * 3000, "b" * 3000, "c" * 3000, "d" * 100],
        model="embedding-test",
    )

    assert [len(batch) for batch in calls] == [2, 2]
    assert [sum(len(text) for text in batch) for batch in calls] == [6000, 3100]


@pytest.mark.asyncio
async def test_embed_texts_batches_by_item_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def create(*, model: str, input: list[str]):
        calls.append(input)
        return FakeEmbeddingResponse([[float(i)] for i, _ in enumerate(input)])

    monkeypatch.setattr(openai_client.settings, "openai_embedding_batch_size", 2)
    monkeypatch.setattr(openai_client.settings, "openai_embedding_max_batch_chars", 100000)
    monkeypatch.setattr(openai_client, "get_openai_client", lambda: _fake_client(create))

    await openai_client.embed_texts(["one", "two", "three", "four", "five"])

    assert [len(batch) for batch in calls] == [2, 2, 1]


@pytest.mark.asyncio
async def test_embed_texts_retries_oversized_batch_with_smaller_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    async def create(*, model: str, input: list[str]):
        calls.append(input)
        if len(input) > 2:
            raise OversizedEmbeddingRequest("Request headers are too large")
        return FakeEmbeddingResponse([[float(text)] for text in input])

    monkeypatch.setattr(openai_client.settings, "openai_embedding_batch_size", 4)
    monkeypatch.setattr(openai_client.settings, "openai_embedding_max_batch_chars", 100000)
    monkeypatch.setattr(openai_client, "get_openai_client", lambda: _fake_client(create))

    embeddings = await openai_client.embed_texts(["0", "1", "2", "3"])

    assert [len(batch) for batch in calls] == [4, 2, 2]
    assert embeddings == [[0.0], [1.0], [2.0], [3.0]]


@pytest.mark.asyncio
async def test_embed_texts_raises_clear_error_when_single_text_is_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def create(*, model: str, input: list[str]):
        raise OversizedEmbeddingRequest("Request headers are too large")

    monkeypatch.setattr(openai_client.settings, "openai_embedding_batch_size", 1)
    monkeypatch.setattr(openai_client.settings, "openai_embedding_max_batch_chars", 10)
    monkeypatch.setattr(openai_client, "get_openai_client", lambda: _fake_client(create))

    with pytest.raises(RuntimeError, match="too large for a single text item"):
        await openai_client.embed_texts(["a" * 100], model="embedding-test")
